"""The player's silhouette, shown while a building or other structure hides him.

When the scenery drawn in front of the player (buildings, trees, railings, roof
snow...) covers at least ``SILHOUETTE_FROM`` of his painted pixels, a faint
whitish outline of him, with a fainter fill, fades in over everything, so the
player always knows where he is; it fades out again once he steps clear.
Coverage is counted in painted pixels with ``pygame.mask``, as ``NavGrid`` counts
what hides a walker. Other figures walking in front of him do not count.
"""

from typing import Any, Dict, List, Optional, Sequence, Tuple

import pygame

# Share of the player's painted pixels that must be hidden for the silhouette to show
SILHOUETTE_FROM = 0.9
# He must stay hidden this long (real seconds) before the silhouette starts to fade in,
# so it does not flash up while he only passes behind something
SILHOUETTE_DELAY_S = 0.6
# At night the silhouette is dimmed with the light, down to this share of its opacity in
# the dark (it scales with the brightest channel of the map's light, 1 by full day)
SILHOUETTE_NIGHT_FLOOR = 0.5
# Fade speed, in full alpha ranges per real second (in about 0.4 s, out about 0.5 s)
SILHOUETTE_FADE_IN_PER_S = 2.5
SILHOUETTE_FADE_OUT_PER_S = 2.0
# Opacity of the outline and of the fill inside it, at full fade (0-255): subtle
SILHOUETTE_OUTLINE_ALPHA = 140
SILHOUETTE_FILL_ALPHA = 38
SILHOUETTE_COLOUR = (240, 244, 250)
# Outline thickness in screen pixels at zoom 1 (at least 1)
SILHOUETTE_OUTLINE_PX = 1.0
# A real frame longer than this does not fade further than this much time would
_MAX_DT = 0.1
# Render-queue entries just over a figure that belong to it (its rain splashes: + 0.01)
_OWN_LAYER = 0.02

_CACHE_LIMIT = 64


class PlayerSilhouette:
    """Fades the player's outline in while he is hidden and draws it."""

    def __init__(self) -> None:
        self.alpha: float = 0.0          # 0 (gone) to 1 (fully shown)
        self.hidden: bool = False        # whether he was hidden on the last measure
        self.hidden_for: float = 0.0     # real seconds he has been hidden without a break
        self._last_ticks: Optional[int] = None
        self._masks: Dict[int, Tuple[pygame.Surface, pygame.Mask]] = {}
        self._outlines: Dict[Tuple[int, int], Tuple[pygame.Surface, pygame.Surface]] = {}
        self._where: Optional[Tuple[pygame.Surface, float, float]] = None

    # --- measuring -------------------------------------------------------------------

    def _mask(self, sprite: pygame.Surface) -> pygame.Mask:
        """The painted pixels of *sprite*, cached (scaled sprites are cached surfaces)."""
        cached = self._masks.get(id(sprite))
        if cached is None or cached[0] is not sprite:
            if len(self._masks) > _CACHE_LIMIT:
                self._masks.clear()
            cached = (sprite, pygame.mask.from_surface(sprite))
            self._masks[id(sprite)] = cached
        return cached[1]

    def hidden_share(self, render_queue: Sequence[Dict[str, Any]], player: Any) -> float:
        """How much of the player's sprite (0 to 1) the entries drawn after him cover.

        *render_queue* must be sorted as it is drawn. Additive entries (lights), other
        figures and what belongs to the player himself are left out.
        """
        self._where = None
        index = next((i for i, obj in enumerate(render_queue) if obj.get('owner') is player), None)
        if index is None:
            return 0.0
        entry = render_queue[index]
        sprite = entry['sprite']
        px, py = round(entry['pos'][0]), round(entry['pos'][1])
        self._where = (sprite, px, py)
        own = self._mask(sprite)
        painted = own.count()
        if painted == 0:
            return 0.0
        box = pygame.Rect(px, py, *sprite.get_size())
        cover = pygame.Mask(sprite.get_size())
        limit = getattr(player, 'y_sort', entry['y_sort']) + _OWN_LAYER
        for obj in render_queue[index + 1:]:
            if obj.get('flags', 0) or obj['y_sort'] <= limit:
                continue
            owner = obj.get('owner')
            if owner is not None and hasattr(owner, '_get_scaled_sprite'):
                continue   # another figure walking in front
            other = obj['sprite']
            ox, oy = round(obj['pos'][0]), round(obj['pos'][1])
            if not box.colliderect(pygame.Rect(ox, oy, *other.get_size())):
                continue
            cover.draw(self._mask(other), (ox - px, oy - py))
        return own.overlap_area(cover, (0, 0)) / painted

    def update(self, render_queue: Sequence[Dict[str, Any]], player: Any,
               now_ms: Optional[int] = None) -> None:
        """Measure this frame's cover and glide the fade towards shown or gone."""
        now_ms = pygame.time.get_ticks() if now_ms is None else now_ms
        dt = 0.0 if self._last_ticks is None else max(0.0, min(_MAX_DT, (now_ms - self._last_ticks) / 1000.0))
        self._last_ticks = now_ms
        self.hidden = self.hidden_share(render_queue, player) >= SILHOUETTE_FROM
        if self.hidden:
            before = self.hidden_for
            self.hidden_for += dt
            fading = self.hidden_for - max(before, SILHOUETTE_DELAY_S)
            if fading > 0:
                self.alpha = min(1.0, self.alpha + SILHOUETTE_FADE_IN_PER_S * fading)
        else:
            self.hidden_for = 0.0
            self.alpha = max(0.0, self.alpha - SILHOUETTE_FADE_OUT_PER_S * dt)

    # --- drawing ---------------------------------------------------------------------

    def _outline(self, sprite: pygame.Surface, thickness: int) -> Tuple[pygame.Surface, pygame.Surface]:
        """(outline, fill) surfaces for *sprite*, the outline *thickness* pixels round it."""
        key = (id(sprite), thickness)
        cached = self._outlines.get(key)
        if cached is not None:
            return cached
        if len(self._outlines) > _CACHE_LIMIT:
            self._outlines.clear()
        mask = self._mask(sprite)
        w, h = sprite.get_size()
        pad = thickness
        grown = pygame.Mask((w + 2 * pad, h + 2 * pad))
        for dx in range(-thickness, thickness + 1):
            for dy in range(-thickness, thickness + 1):
                if dx * dx + dy * dy <= thickness * thickness + thickness:
                    grown.draw(mask, (pad + dx, pad + dy))
        grown.erase(mask, (pad, pad))
        colour = (*SILHOUETTE_COLOUR, 255)
        outline = grown.to_surface(setcolor=colour, unsetcolor=(0, 0, 0, 0))
        fill = mask.to_surface(setcolor=colour, unsetcolor=(0, 0, 0, 0))
        cached = (outline, fill)
        self._outlines[key] = cached
        return cached

    def draw(self, screen: pygame.Surface, zoom: float,
             light: Optional[Sequence[int]] = None) -> None:
        """Draw the silhouette where the player was drawn this frame, as faded in, dimmed
        by the map's *light* (its colour, 0-255 a channel) towards ``SILHOUETTE_NIGHT_FLOOR``."""
        if self.alpha <= 0.0 or self._where is None:
            return
        sprite, px, py = self._where
        thickness = max(1, round(SILHOUETTE_OUTLINE_PX * zoom))
        outline, fill = self._outline(sprite, thickness)
        fade = self.alpha * self.alpha * (3 - 2 * self.alpha)   # smoothstep, so it eases in and out
        if light is not None:
            bright = max(0.0, min(1.0, max(light) / 255))
            fade *= SILHOUETTE_NIGHT_FLOOR + (1 - SILHOUETTE_NIGHT_FLOOR) * bright
        fill.set_alpha(round(SILHOUETTE_FILL_ALPHA * fade))
        screen.blit(fill, (px, py))
        outline.set_alpha(round(SILHOUETTE_OUTLINE_ALPHA * fade))
        screen.blit(outline, (px - thickness, py - thickness))
