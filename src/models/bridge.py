"""Bridges: a walkable deck laid over the water.

A bridge is a rectangle on the "Bridges" object layer of the map. Across its
full length runs the *deck*, the band a walker's feet may stand on, given in
tiles from the top of the rectangle by ``Deck_top`` and ``Deck_bottom``. The
bands above and below the deck are the railings: solid, so the only ways on
and off are the two ends. Over the deck the water does not count, which is
all it takes for the player and the townsfolk to cross.

It is drawn like a house, its sprite (``File_name``, in
assets/map_sprites/houses/) standing on the rectangle's bottom-left corner,
but flat on the ground: under everyone walking over it. Only the railing on
the near side may be drawn over them, from an optional ``<name>_front.png``
of the same size that holds nothing but that railing, sorted on the
rectangle's bottom edge. Without a sprite, a plain plank bridge the size of
the rectangle stands in for it.
"""

import os
from typing import Dict, List, Optional, Sequence

import pygame

from ..config.constants import TILE_SIZE

BRIDGE_SPRITE_DIR = os.path.join('assets', 'map_sprites', 'houses')

#: Deck band used when the Tiled object does not say, in tiles from the top:
#: one tile of railing on either side.
DEFAULT_RAIL_TILES = 1.0

#: How far the near railing of the stand-in reaches up over the deck, in world
#: pixels, so it hides a walker's feet and shows the front sprite at work.
PLACEHOLDER_RAIL_RISE = 10

# Colours of the stand-in bridge
_PLANK_LIGHT = (156, 112, 66)
_PLANK_DARK = (128, 88, 50)
_PLANK_GAP = (70, 46, 26)
_BEAM = (92, 62, 34)
_POST = (78, 52, 28)
_RAIL = (118, 82, 46)
_OUTLINE = (40, 26, 14)


def subtract_rect(rect: pygame.Rect, hole: pygame.Rect) -> List[pygame.Rect]:
    """The parts of ``rect`` lying outside ``hole``, as up to four rectangles.

    Args:
        rect: The rectangle to cut.
        hole: What to cut out of it.
    """
    clip = rect.clip(hole)
    if not clip.width or not clip.height:
        return [rect]
    parts = []
    if clip.top > rect.top:
        parts.append(pygame.Rect(rect.left, rect.top, rect.width, clip.top - rect.top))
    if clip.bottom < rect.bottom:
        parts.append(pygame.Rect(rect.left, clip.bottom, rect.width, rect.bottom - clip.bottom))
    if clip.left > rect.left:
        parts.append(pygame.Rect(rect.left, clip.top, clip.left - rect.left, clip.height))
    if clip.right < rect.right:
        parts.append(pygame.Rect(clip.right, clip.top, rect.right - clip.right, clip.height))
    return parts


def off_deck_parts(rect: pygame.Rect, bridges: Sequence['Bridge']) -> List[pygame.Rect]:
    """The parts of ``rect`` not standing on any bridge deck.

    Args:
        rect: A walker's feet box, in world pixels.
        bridges: The map's bridges.
    """
    parts = [rect]
    for bridge in bridges:
        if bridge.deck.colliderect(rect):
            parts = [piece for part in parts for piece in subtract_rect(part, bridge.deck)]
    return parts


class Bridge:
    """A bridge from the map's "Bridges" object layer."""

    def __init__(self, name: str, rect: pygame.Rect, deck_top: float, deck_bottom: float,
                 file_name: str = '') -> None:
        """
        Args:
            name: Object name from Tiled.
            rect: The whole bridge, railings included, in world pixels.
            deck_top: Where the walkable deck begins, in tiles below ``rect``'s top.
            deck_bottom: Where it ends, in tiles below ``rect``'s top.
            file_name: The sprite in assets/map_sprites/houses/; '' or a file
                not there yet for the stand-in.
        """
        self.name = name
        self.rect = pygame.Rect(rect)
        top = self.rect.top + round(deck_top * TILE_SIZE)
        bottom = self.rect.top + round(deck_bottom * TILE_SIZE)
        top = max(self.rect.top, min(top, self.rect.bottom))
        bottom = max(top, min(bottom, self.rect.bottom))
        #: The band feet may stand in, the full length of the bridge.
        self.deck = pygame.Rect(self.rect.left, top, self.rect.width, bottom - top)
        #: The railings either side of the deck; nothing walks through them.
        self.rails: List[pygame.Rect] = [
            r for r in (
                pygame.Rect(self.rect.left, self.rect.top, self.rect.width, top - self.rect.top),
                pygame.Rect(self.rect.left, bottom, self.rect.width, self.rect.bottom - bottom),
            ) if r.height > 0
        ]
        self.file_name = file_name
        self.image: Optional[pygame.Surface] = None
        self.front_image: Optional[pygame.Surface] = None
        self.is_placeholder = False
        self._scaled: Dict[float, pygame.Surface] = {}
        self._scaled_front: Dict[float, pygame.Surface] = {}
        self._load_images()

    # ------------------------------------------------------------------
    # Walking
    # ------------------------------------------------------------------

    def blocks(self, rect: pygame.Rect) -> bool:
        """Whether a feet box would run into one of the railings."""
        return any(rail.colliderect(rect) for rail in self.rails)

    def covers(self, x: float, y: float) -> bool:
        """Whether a world point is on the bridge rather than the water below."""
        return self.rect.collidepoint(x, y)

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    @property
    def x(self) -> int:
        """Left edge of the sprite, which stands on the bottom-left corner."""
        return self.rect.left

    @property
    def y(self) -> int:
        """Foot of the sprite."""
        return self.rect.bottom

    @property
    def y_sort(self) -> int:
        """Where the near railing sorts among the walkers: everyone on the deck is behind it."""
        return self.rect.bottom

    def get_scaled_sprite(self, zoom: float) -> Optional[pygame.Surface]:
        """The bridge, drawn under the walkers, at the given zoom."""
        return self._scale(self.image, self._scaled, zoom)

    def get_scaled_front(self, zoom: float) -> Optional[pygame.Surface]:
        """The near railing, drawn over the walkers on the deck, at the given zoom."""
        return self._scale(self.front_image, self._scaled_front, zoom)

    @staticmethod
    def _scale(image: Optional[pygame.Surface], cache: Dict[float, pygame.Surface],
               zoom: float) -> Optional[pygame.Surface]:
        if image is None:
            return None
        key = round(float(zoom), 3)
        if key not in cache:
            size = (max(1, round(image.get_width() * zoom)), max(1, round(image.get_height() * zoom)))
            if size[0] >= image.get_width():
                cache[key] = pygame.transform.scale(image, size)
            else:
                cache[key] = pygame.transform.smoothscale(image, size)
        return cache[key]

    def _load_images(self) -> None:
        """Load the sprite and its front railing, or make the stand-in."""
        path = os.path.join(BRIDGE_SPRITE_DIR, self.file_name) if self.file_name else ''
        if path and not path.lower().endswith('.png'):
            path += '.png'
        if path and os.path.exists(path):
            try:
                self.image = pygame.image.load(path).convert_alpha()
                front = path[:-4] + '_front.png'
                if os.path.exists(front):
                    self.front_image = pygame.image.load(front).convert_alpha()
                return
            except pygame.error as e:
                print(f"Failed to load bridge image: {path} - {e}")
        self.image, self.front_image = self._make_placeholder()
        self.is_placeholder = True

    def _make_placeholder(self):
        """A plain plank bridge filling the rectangle, and its near railing.

        Planks lie across the way over, so a bridge longer than it is wide is
        crossed sideways and its planks stand upright on screen.
        """
        w, h = self.rect.size
        deck_top = self.deck.top - self.rect.top
        deck_bottom = self.deck.bottom - self.rect.top
        across = w >= h
        base = pygame.Surface((w, h), pygame.SRCALPHA)
        front = pygame.Surface((w, h), pygame.SRCALPHA)

        # Beams under the deck, showing below its near edge
        beam_top = max(0, deck_bottom - 4)
        pygame.draw.rect(base, _BEAM, (0, beam_top, w, max(0, h - 6 - beam_top)))

        # The planks, from just under the far railing to the near edge
        plank_top = max(0, deck_top - 8)
        plank = 8
        for i, start in enumerate(range(0, w if across else h, plank)):
            colour = _PLANK_LIGHT if (i * 7) % 3 else _PLANK_DARK
            if across:
                rect = pygame.Rect(start, plank_top, plank - 1, deck_bottom - plank_top)
            else:
                rect = pygame.Rect(0, plank_top + start, w, plank - 1)
            pygame.draw.rect(base, colour, rect.clip((0, plank_top, w, deck_bottom - plank_top)))
        pygame.draw.line(base, _PLANK_GAP, (0, plank_top), (w, plank_top))
        pygame.draw.line(base, _OUTLINE, (0, deck_bottom - 1), (w, deck_bottom - 1))

        # Far railing: posts along the top band, a bar on top
        far_bar = max(2, plank_top - 12)
        for px in range(2, w, TILE_SIZE):
            pygame.draw.rect(base, _POST, (px, far_bar, 5, plank_top - far_bar + 4))
        pygame.draw.rect(base, _RAIL, (0, far_bar, w, 4))
        pygame.draw.rect(base, _OUTLINE, (0, far_bar, w, 4), 1)

        # Near railing, in its own layer: posts on the deck's near edge,
        # reaching up over it, and a bar
        rise = PLACEHOLDER_RAIL_RISE
        near_bar = max(0, deck_bottom - rise)
        post_bottom = min(h - 2, deck_bottom + (h - deck_bottom) // 2)
        for px in range(2, w, TILE_SIZE):
            pygame.draw.rect(front, _POST, (px, near_bar, 5, post_bottom - near_bar))
            pygame.draw.rect(front, _OUTLINE, (px, near_bar, 5, post_bottom - near_bar), 1)
        pygame.draw.rect(front, _RAIL, (0, near_bar, w, 4))
        pygame.draw.rect(front, _OUTLINE, (0, near_bar, w, 4), 1)
        base.blit(front, (0, 0))
        return base, front
