"""Bridges: a walkable deck laid over the water.

A bridge is a rectangle on the "Bridges" object layer of the map. Across its
full length runs the *deck*, the band a walker's feet may stand on, given in
tiles from the top of the rectangle by ``Deck_top`` and ``Deck_bottom``. The
bands above and below the deck are the railings: solid, so the only ways on
and off are the two ends. Over the deck the water does not count, which is
all it takes for the player and the townsfolk to cross.

Its sprite (``File_name``, in assets/map_sprites/houses/) is one *module*
of the bridge, a short span with a post at either end; whatever transparent
margin is around it is cut off. The module is scaled to the height of the
rectangle and laid side by side, each one's first post on the last one's,
until the row is at least as long as the rectangle: the bridge then spans
that row, centred on the rectangle, so it may come out a little longer than
drawn in Tiled. It lies flat on the ground, under everyone walking over it.
Only the railing on the near side may be drawn over them, from an optional
``<name>_front.png`` of the same canvas size that holds nothing but that
railing, in the same place, sorted on the rectangle's bottom edge. Without a
sprite, a plain plank bridge the size of the rectangle stands in for it.

A rectangle taller than it is wide is a bridge crossed north to south. Its
deck runs down it, given in tiles from its left edge by ``Deck_left`` and
``Deck_right``, with the railings left and right of it. Its sprite is drawn
upright, each module a span running down the picture, scaled to the width of
the rectangle and stacked downwards.
"""

import math
import os
from typing import Dict, List, Optional, Sequence, Tuple

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


def _end_post_width(module: pygame.Surface) -> int:
    """How wide the post at the left end of a bridge module is, in its own pixels.

    Modules are laid with this much overlap, so where two meet there is one
    post, not two side by side. The post is the run of columns, from the left
    edge, as solid as the first one.

    Args:
        module: One span of a bridge, cropped to what is drawn on it.
    """
    width, height = module.get_size()

    def solid(x: int) -> int:
        return sum(1 for y in range(height) if module.get_at((x, y)).a > 128)

    first = solid(0)
    post = 1
    while post < width // 2 and abs(solid(post) - first) <= max(2, first // 50):
        post += 1
    return post


class Bridge:
    """A bridge from the map's "Bridges" object layer."""

    def __init__(self, name: str, rect: pygame.Rect, deck_start: float, deck_end: float,
                 file_name: str = '') -> None:
        """
        Args:
            name: Object name from Tiled.
            rect: The whole bridge, railings included, in world pixels.
            deck_start: Where the walkable deck begins, in tiles below ``rect``'s
                top (in from its left edge, if the bridge runs north to south).
            deck_end: Where it ends, measured the same way.
            file_name: The sprite in assets/map_sprites/houses/; '' or a file
                not there yet for the stand-in.
        """
        self.name = name
        self.rect = pygame.Rect(rect)
        #: Crossed north to south: the deck runs down the rectangle.
        self.vertical = self.rect.height > self.rect.width
        self.file_name = file_name
        self.image: Optional[pygame.Surface] = None
        self.front_image: Optional[pygame.Surface] = None
        self.is_placeholder = False
        self._scaled: Dict[float, pygame.Surface] = {}
        self._scaled_front: Dict[float, pygame.Surface] = {}
        # A sprite may lengthen the rectangle to a whole number of modules
        self._load_images()
        r = self.rect
        if self.vertical:
            left = max(r.left, min(r.left + round(deck_start * TILE_SIZE), r.right))
            right = max(left, min(r.left + round(deck_end * TILE_SIZE), r.right))
            #: The band feet may stand in, the full length of the bridge.
            self.deck = pygame.Rect(left, r.top, right - left, r.height)
            #: The railings either side of the deck; nothing walks through them.
            self.rails: List[pygame.Rect] = [
                rail for rail in (
                    pygame.Rect(r.left, r.top, left - r.left, r.height),
                    pygame.Rect(right, r.top, r.right - right, r.height),
                ) if rail.width > 0
            ]
        else:
            top = max(r.top, min(r.top + round(deck_start * TILE_SIZE), r.bottom))
            bottom = max(top, min(r.top + round(deck_end * TILE_SIZE), r.bottom))
            self.deck = pygame.Rect(r.left, top, r.width, bottom - top)
            self.rails = [
                rail for rail in (
                    pygame.Rect(r.left, r.top, r.width, top - r.top),
                    pygame.Rect(r.left, bottom, r.width, r.bottom - bottom),
                ) if rail.height > 0
            ]
        if self.is_placeholder:
            self.image, self.front_image = self._make_placeholder()

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
                module = pygame.image.load(path).convert_alpha()
                front = path[:-4] + '_front.png'
                front_module = pygame.image.load(front).convert_alpha() if os.path.exists(front) else None
                self._lay_modules(module, front_module)
                return
            except pygame.error as e:
                print(f"Failed to load bridge image: {path} - {e}")
        # Drawn once the deck is known
        self.is_placeholder = True

    def _lay_modules(self, module: pygame.Surface, front_module: Optional[pygame.Surface]) -> None:
        """Build the bridge from as many modules as it takes to span the rectangle.

        Sets the images and lengthens ``rect`` to the row of modules, centred
        on it. The upright modules of a bridge crossed north to south are
        turned on their side, laid in a row like any other bridge's, and the
        row turned back.

        Args:
            module: One span of the bridge, transparent margins and all.
            front_module: Its near railing alone, on a canvas of the same size,
                or None.
        """
        if not self.vertical:
            self.image, self.front_image, length = self._row(module, front_module, self.rect.size)
            centre = self.rect.centerx
            self.rect.width = length
            self.rect.centerx = centre
            return
        module = pygame.transform.rotate(module, 90)
        if front_module is not None:
            front_module = pygame.transform.rotate(front_module, 90)
        image, front, length = self._row(module, front_module, (self.rect.height, self.rect.width))
        self.image = pygame.transform.rotate(image, -90)
        self.front_image = pygame.transform.rotate(front, -90) if front is not None else None
        centre = self.rect.centery
        self.rect.height = length
        self.rect.centery = centre

    @staticmethod
    def _row(module: pygame.Surface, front_module: Optional[pygame.Surface],
             size: Tuple[int, int]) -> Tuple[pygame.Surface, Optional[pygame.Surface], int]:
        """Modules side by side, scaled to the height ``size`` gives, at least its width long.

        Args:
            module: One span of the bridge, transparent margins and all, lying
                the way the row runs.
            front_module: Its near railing alone, on a canvas of the same size,
                or None.
            size: Length and thickness the bridge is drawn at in Tiled, in
                world pixels.

        Returns:
            The row, its front railings (or None) and how long it came out.
        """
        length, thickness = size
        crop = module.get_bounding_rect()
        if not crop.width or not crop.height:
            raise pygame.error("the sprite is empty")
        module = module.subsurface(crop).copy()
        if front_module is not None:
            # Cut from the same place, so it lies exactly on the module's railing
            front_crop = pygame.Surface(crop.size, pygame.SRCALPHA)
            front_crop.blit(front_module, (-crop.x, -crop.y))
            front_module = front_crop
        scale = thickness / crop.height
        step = crop.width - _end_post_width(module)
        count = 1 + max(0, math.ceil((length / scale - crop.width) / step))
        native_width = crop.width + (count - 1) * step
        size = (max(1, round(native_width * scale)), thickness)

        def row(piece: pygame.Surface) -> pygame.Surface:
            strip = pygame.Surface((native_width, crop.height), pygame.SRCALPHA)
            for i in range(count):
                strip.blit(piece, (i * step, 0))
            return pygame.transform.smoothscale(strip, size)

        return row(module), (row(front_module) if front_module is not None else None), size[0]

    def _make_placeholder(self):
        """A plain plank bridge filling the rectangle, and its near railing.

        Planks lie across the way over, so they stand upright on screen.
        """
        if self.vertical:
            return self._make_upright_placeholder(), None
        w, h = self.rect.size
        deck_top = self.deck.top - self.rect.top
        deck_bottom = self.deck.bottom - self.rect.top
        base = pygame.Surface((w, h), pygame.SRCALPHA)
        front = pygame.Surface((w, h), pygame.SRCALPHA)

        # Beams under the deck, showing below its near edge
        beam_top = max(0, deck_bottom - 4)
        pygame.draw.rect(base, _BEAM, (0, beam_top, w, max(0, h - 6 - beam_top)))

        # The planks, from just under the far railing to the near edge
        plank_top = max(0, deck_top - 8)
        plank = 8
        for i, start in enumerate(range(0, w, plank)):
            colour = _PLANK_LIGHT if (i * 7) % 3 else _PLANK_DARK
            rect = pygame.Rect(start, plank_top, plank - 1, deck_bottom - plank_top)
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

    def _make_upright_placeholder(self) -> pygame.Surface:
        """The plank stand-in for a bridge crossed north to south.

        Planks lie across the deck, under a railing down either side. Seen from
        above, neither railing reaches over the deck, so it has no front image.
        """
        w, h = self.rect.size
        deck_left = self.deck.left - self.rect.left
        deck_right = self.deck.right - self.rect.left
        base = pygame.Surface((w, h), pygame.SRCALPHA)

        # Beams along the sides, showing just past the planks
        pygame.draw.rect(base, _BEAM, (max(0, deck_left - 5), 0, deck_right - deck_left + 10, h))

        # The planks, reaching a little under the railings
        plank = 8
        left, right = max(0, deck_left - 3), min(w, deck_right + 3)
        for i, start in enumerate(range(0, h, plank)):
            colour = _PLANK_LIGHT if (i * 7) % 3 else _PLANK_DARK
            pygame.draw.rect(base, colour, pygame.Rect(left, start, right - left, plank - 1).clip((0, 0, w, h)))
            pygame.draw.line(base, _PLANK_GAP, (left, start + plank - 1), (right - 1, start + plank - 1))

        # A railing over each side: a bar along it, a post every tile
        for x in (max(0, deck_left - 7), min(w - 7, deck_right + 1)):
            pygame.draw.rect(base, _RAIL, (x + 1, 0, 5, h))
            pygame.draw.rect(base, _OUTLINE, (x + 1, 0, 5, h), 1)
            for py in range(4, h, TILE_SIZE):
                pygame.draw.rect(base, _POST, (x, py, 7, 7))
                pygame.draw.rect(base, _OUTLINE, (x, py, 7, 7), 1)
        return base
