"""Fog hanging over the map: a veil over everything, banks drifting through it, and loose wisps.

How thick it is overall follows Weather.fog (0 to 1), which glides in and
out over game hours; this only draws it, in layers:

- the veil: an even haze over the whole view (VEIL_ALPHA at full fog);
- the banks: three layers of smooth, seamlessly tiling noise (NOISE_LAYERS),
  large slow ones and smaller faster ones, each drifting its own way with
  the wind, so where they meet the fog thickens and the banks change shape
  as they pass through each other. Over water it gathers more (WATER_BIAS,
  blurred out over the banks). How much of that shows depends on the level:
  a thin fog has banks only where the layers are thickest, a thick one
  everywhere but where they are thinnest (a threshold falling with the level);
- round the player it is thinner (FOG_CLEAR_RADIUS_TILES), so you can still
  see where you go;
- the wisps: loose soft streaks drifting faster than the banks, each fading
  in and out over its few seconds, mostly where the banks are thick
  (FOG_WISPS_PER_MEGAPIXEL);
- and lit windows glow through it in a wider halo (HALO_*).

Cheap, the way WetGround is: the veil, banks and clearing are worked out in
gray, PX_PER_TILE pixels a tile, for the part in view only, then smoothed up
to the screen in one piece and laid over it as a multiply and an add (fog
colour * a + scene * (1 - a), without a per-pixel alpha surface). That is
made again only REFRESH_SECONDS apart, or when the camera crosses one of its
pixels or the zoom changes; in between it is only blitted where the camera
has it. The layers' drift is shifted by fractions of a pixel (four weighted
blits), so the banks glide rather than step.

Drawn after the day/night lighting, lit by it instead: the fog's colour is
multiplied by the scene's light (no darker than NIGHT_LIGHT_MIN), so it is
white by day, rosy at dawn and a dim blue-grey at night.

The game map's fog of war (what the player has explored, for the Town Plan)
is another thing, in models/map_fog.py.
"""

import math
import random
from typing import Dict, List, Optional, Tuple

import pygame

from ..config.constants import (
    FOG_CLEAR_RADIUS_TILES, FOG_DRIFT_TILES_PER_S, FOG_WISPS_PER_MEGAPIXEL, TILE_SIZE,
)

PX_PER_TILE = 2                 # resolution of the fog's gray map
REFRESH_SECONDS = 1 / 15        # how often the drifting banks are worked out anew
FOG_COLOUR = (226, 230, 236)    # a pale cool grey, white in sunshine
NIGHT_LIGHT_MIN = 0.13          # the fog is lit no darker than this share of daylight
VEIL_ALPHA = 0.28               # the even haze at full fog (1.0 would hide everything)
BANK_ALPHA = 0.6                # what the banks add over it at their thickest, at full fog
MAX_ALPHA = 0.82                # nowhere thicker than this, so the map always shows through
CLEAR_DEPTH = 0.45              # how much thinner the fog is right round the player
# The bank layers: (cells across one tiling, tiles per cell, weight, drift (x, y) as a share of
# FOG_DRIFT_TILES_PER_S; x is turned with the wind). Big and slow first.
NOISE_LAYERS = (
    (7, 14, 0.55, (1.0, 0.18)),
    (12, 6, 0.36, (1.55, -0.12)),
    (20, 2.5, 0.2, (2.3, 0.32)),
)
THRESHOLD = (0.8, 0.42)         # the banks start this far up the noise at no fog, and this much lower at full fog
BANK_GAIN_DOUBLINGS = 1         # how sharply a bank thickens past the threshold (x2 each)
WATER_BIAS = 0.22               # how much more fog gathers over water, at the water itself
WATER_SPREAD_TILES = 5          # and how far out over the banks that reaches
WIND_DRIFT = 4.0                # the wind (Weather.wind) speeds the drift up by this much of itself
# The wisps: (width, height) in tiles, and how opaque at their middle (0-255)
WISP_KINDS = ((6.0, 1.8, 46), (8.0, 2.3, 42), (10.0, 2.8, 38), (13.0, 3.4, 34))
WISP_SECONDS = (6.0, 13.0)      # how long one is seen, fading in and out
WISP_SPEED = (1.6, 2.6)         # as many times the drift of the big banks
WISP_FADE_STEPS = 8             # opacities each wisp's sprite is kept in
SPAWN_MARGIN_TILES = 4          # wisps may start this far outside the view, so they drift in
HALO_GROW = 3.2                 # a lit window's halo in fog, as many times the window's size
HALO_STRENGTH = 0.8             # and how bright it is at full fog, as a share of the window's light


def _scale_of(camera) -> float:
    """The camera's world-to-screen scale, as Camera.apply() works it out."""
    return round(TILE_SIZE * camera.zoom) / float(TILE_SIZE)


def _gray(v: float) -> Tuple[int, int, int]:
    v = max(0, min(255, round(v)))
    return (v, v, v)


def _bump(diameter: int) -> pygame.Surface:
    """A round gray bump, white in the middle easing smoothly to black at its edge (no crease anywhere)."""
    base = pygame.Surface((64, 64))
    base.fill((0, 0, 0))
    for ring in range(32, 0, -1):
        pygame.draw.circle(base, _gray(255 * (1 - (ring / 32) ** 2) ** 2), (32, 32), ring)
    return pygame.transform.smoothscale(base, (max(2, diameter), max(2, diameter)))


def _tiling_noise(cells: int, cell_px: int, weight: float, rng: random.Random) -> pygame.Surface:
    """Smooth lumpy noise about *cells* lumps across, *cell_px* pixels apart, tiling without a seam.

    Soft round bumps of random size and strength summed up (each laid in again
    a tile over on every side, so they wrap), its average then brought to
    half of *weight* of white. Unlike interpolated value noise it has no grid
    whose creases the banks' steep threshold would show as straight edges.
    """
    side = cells * cell_px
    tile = pygame.Surface((side, side))
    tile.fill((0, 0, 0))
    bumps = {}
    for _ in range(cells * cells):
        diameter = round(cell_px * rng.uniform(1.2, 2.6))
        bump = bumps.get(diameter) or bumps.setdefault(diameter, _bump(diameter))
        strong = bump.copy()
        strong.fill(_gray(255 * rng.uniform(0.25, 0.6)), special_flags=pygame.BLEND_RGB_MULT)
        x, y = rng.random() * side - diameter / 2, rng.random() * side - diameter / 2
        for dy in (-side, 0, side):
            for dx in (-side, 0, side):
                tile.blit(strong, (round(x + dx), round(y + dy)), special_flags=pygame.BLEND_RGB_ADD)
    # Its average to half of weight: doubled until that is in reach, then multiplied down
    target = 255 * weight / 2
    mean = max(1.0, pygame.transform.average_color(tile)[0])
    while mean < target:
        tile.blit(tile.copy(), (0, 0), special_flags=pygame.BLEND_RGB_ADD)
        mean *= 2
    tile.fill(_gray(255 * target / mean), special_flags=pygame.BLEND_RGB_MULT)
    return tile


def _blit_tiled(dst: pygame.Surface, tile: pygame.Surface, ox: int, oy: int) -> None:
    """Fill *dst* with *tile* repeated, *dst*'s (0, 0) showing the tile's (ox, oy) (any integers)."""
    tw, th = tile.get_size()
    w, h = dst.get_size()
    y = -(oy % th)
    while y < h:
        x = -(ox % tw)
        while x < w:
            dst.blit(tile, (x, y))
            x += tw
        y += th


def _soft_blob(w: int, h: int, colour: Tuple[int, int, int], alpha: int) -> pygame.Surface:
    """A soft oval of *colour*, *alpha* in the middle fading to nothing at its edge."""
    base = pygame.Surface((64, 64), pygame.SRCALPHA)
    for ring in range(32, 0, -1):
        a = round(alpha * (1 - (ring / 32) ** 2) ** 1.5)
        pygame.draw.circle(base, (*colour, a), (32, 32), ring)
    return pygame.transform.smoothscale(base, (max(2, w), max(2, h)))


def _clearing(radius_px: int) -> pygame.Surface:
    """White, darkening softly towards the middle: multiplied in, it thins the fog round the player."""
    size = radius_px * 2 + 1
    hole = pygame.Surface((size, size))
    hole.fill((255, 255, 255))
    for ring in range(radius_px, 0, -1):
        t = 1 - ring / radius_px                      # 0 at the edge, 1 in the middle
        depth = CLEAR_DEPTH * t * t * (3 - 2 * t)
        pygame.draw.circle(hole, _gray(255 * (1 - depth)), (radius_px, radius_px), ring)
    return hole


class Fog:
    """The fog's bank layers, its water map and the wisps, drawn as thick as the weather has it.

    Args:
        tiles_wide, tiles_high: The map's size in tiles.
        water_tiles: The (column, row) of every water tile, where fog gathers.
        rng: Where the noise and the wisps are drawn from (seed one in tests).
    """

    def __init__(self, tiles_wide: int, tiles_high: int, water_tiles=(), rng: Optional[random.Random] = None) -> None:
        self.rng = rng or random.Random()
        self.size = (tiles_wide * PX_PER_TILE, tiles_high * PX_PER_TILE)
        self.layers = [_tiling_noise(cells, round(tiles * PX_PER_TILE), weight, self.rng)
                       for cells, tiles, weight, _drift in NOISE_LAYERS]
        # Each layer's drift so far, in fog pixels (started anywhere, so the layers do not line up)
        self.offsets: List[List[float]] = [[self.rng.random() * layer.get_width(), self.rng.random() * layer.get_height()]
                                           for layer in self.layers]
        self._water = self._make_water(water_tiles)
        self._clearing = _clearing(round(FOG_CLEAR_RADIUS_TILES * PX_PER_TILE))
        # Each wisp: [x, y, vx, vy, age, seconds, kind], (x, y) its middle in world px
        self.wisps: List[list] = []
        self._since_refresh = REFRESH_SECONDS
        self._view_key = None
        self._small: Optional[pygame.Surface] = None    # the last gray map, over the fog pixels _small_src
        self._small_src: Optional[pygame.Rect] = None
        self._mult: Optional[pygame.Surface] = None     # 255 - a, multiplied over the scene
        self._add: Optional[pygame.Surface] = None      # fog colour * a, added on
        self._wisp_sprites: Dict[tuple, list] = {}
        self._halos: Dict[tuple, pygame.Surface] = {}

    def _make_water(self, water_tiles) -> pygame.Surface:
        """The water bias: WATER_BIAS over water, fading out over WATER_SPREAD_TILES round it."""
        tiles_w, tiles_h = self.size[0] // PX_PER_TILE, self.size[1] // PX_PER_TILE
        mask = pygame.Surface((tiles_w, tiles_h))
        mask.fill((0, 0, 0))
        level = _gray(255 * WATER_BIAS)
        for x, y in water_tiles:
            if 0 <= x < tiles_w and 0 <= y < tiles_h:
                mask.set_at((x, y), level)
        # Spread out by going down to a pixel per WATER_SPREAD_TILES and back up, twice, so it has no edge
        small = (max(1, tiles_w // WATER_SPREAD_TILES), max(1, tiles_h // WATER_SPREAD_TILES))
        spread = mask
        for _ in range(2):
            spread = pygame.transform.smoothscale(pygame.transform.smoothscale(spread, small), (tiles_w, tiles_h))
            spread.blit(spread.copy(), (0, 0), special_flags=pygame.BLEND_RGB_ADD)   # x2: the averaging thins it
        return pygame.transform.smoothscale(spread, self.size)

    # -- advancing ---------------------------------------------------------------

    def update(self, dt: float, level: float, wind: float, camera) -> None:
        """Let *dt* seconds of drift pass (only call while the game runs) at fog *level*, the wind *wind*."""
        side = -1.0 if wind < 0 else 1.0
        speed = FOG_DRIFT_TILES_PER_S * PX_PER_TILE * (1.0 + WIND_DRIFT * abs(wind))
        for offset, (_cells, _tiles, _weight, (dx, dy)) in zip(self.offsets, NOISE_LAYERS):
            offset[0] += dx * side * speed * dt
            offset[1] += dy * speed * dt
        self._since_refresh += dt
        self._update_wisps(dt, level, side, camera)

    def _update_wisps(self, dt: float, level: float, side: float, camera) -> None:
        scale = _scale_of(camera)
        view = pygame.Rect(camera.x, camera.y, camera.screen_width / scale, camera.screen_height / scale)
        margin = SPAWN_MARGIN_TILES * TILE_SIZE
        keep_in = view.inflate(margin * 4, margin * 4)
        kept = []
        for wisp in self.wisps:
            wisp[4] += dt
            wisp[0] += wisp[2] * dt
            wisp[1] += wisp[3] * dt
            if wisp[4] < wisp[5] and keep_in.collidepoint(wisp[0], wisp[1]):
                kept.append(wisp)
        self.wisps = kept
        wanted = round(FOG_WISPS_PER_MEGAPIXEL * camera.screen_width * camera.screen_height / 1e6 * level)
        rng = self.rng
        for _ in range(8):   # a few tries a frame at most: they come in over time
            if len(self.wisps) >= wanted:
                break
            x = view.x - margin + rng.random() * (view.width + 2 * margin)
            y = view.y - margin + rng.random() * (view.height + 2 * margin)
            if rng.random() > max(0.2, self._density_at(x, y)):
                continue   # mostly where the banks are thick
            speed = FOG_DRIFT_TILES_PER_S * TILE_SIZE * rng.uniform(*WISP_SPEED)
            self.wisps.append([x, y, side * speed, speed * rng.uniform(-0.15, 0.15), 0.0,
                               rng.uniform(*WISP_SECONDS), rng.randrange(len(WISP_KINDS))])

    def _density_at(self, x: float, y: float) -> float:
        """How thick the fog is at world (*x*, *y*), 0 to 1, as last worked out; 0.5 where that is not known."""
        if self._small is None:
            return 0.5
        px = int(x / TILE_SIZE * PX_PER_TILE) - self._small_src.x
        py = int(y / TILE_SIZE * PX_PER_TILE) - self._small_src.y
        if 0 <= px < self._small_src.width and 0 <= py < self._small_src.height:
            return self._small.get_at((px, py))[0] / (255 * MAX_ALPHA)
        return 0.5

    # -- drawing -----------------------------------------------------------------

    def _gray_map(self, src: pygame.Rect, level: float, centre: Optional[Tuple[float, float]]) -> pygame.Surface:
        """How opaque the fog is (0-255) over the fog pixels *src*, at *level*, thinned round *centre* (world px)."""
        small = pygame.Surface(src.size)
        small.fill((0, 0, 0))
        tap = pygame.Surface(src.size)
        for layer, (ox, oy) in zip(self.layers, self.offsets):
            # Where the layer has drifted to, between whole pixels: four blits, weighted bilinearly.
            # It moved by (ox, oy), so a fog pixel shows what lay that far back on it.
            fx, fy = math.floor(ox), math.floor(oy)
            ax, ay = ox - fx, oy - fy
            for (sx, sy), weight in (((0, 0), (1 - ax) * (1 - ay)), ((1, 0), ax * (1 - ay)),
                                     ((0, 1), (1 - ax) * ay), ((1, 1), ax * ay)):
                if weight < 0.02:
                    continue
                _blit_tiled(tap, layer, src.x - fx - sx, src.y - fy - sy)
                tap.fill(_gray(255 * weight), special_flags=pygame.BLEND_RGB_MULT)
                small.blit(tap, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
        on_map = src.clip(pygame.Rect((0, 0), self.size))
        if on_map.width > 0 and on_map.height > 0:
            small.blit(self._water, (on_map.x - src.x, on_map.y - src.y), on_map, special_flags=pygame.BLEND_RGB_ADD)
        # The banks: what is past the threshold, steepened, as opaque as the level allows
        high, drop = THRESHOLD
        small.fill(_gray(255 * (high - drop * level)), special_flags=pygame.BLEND_RGB_SUB)
        for _ in range(BANK_GAIN_DOUBLINGS):
            small.blit(small.copy(), (0, 0), special_flags=pygame.BLEND_RGB_ADD)
        small.fill(_gray(255 * BANK_ALPHA * math.sqrt(level)), special_flags=pygame.BLEND_RGB_MULT)
        # Over the even veil, and no thicker than MAX_ALPHA anywhere
        small.fill(_gray(255 * VEIL_ALPHA * level), special_flags=pygame.BLEND_RGB_ADD)
        excess = small.copy()
        excess.fill(_gray(255 * MAX_ALPHA), special_flags=pygame.BLEND_RGB_SUB)
        small.blit(excess, (0, 0), special_flags=pygame.BLEND_RGB_SUB)
        if centre is not None:
            r = self._clearing.get_width() // 2
            small.blit(self._clearing, (round(centre[0] / TILE_SIZE * PX_PER_TILE) - src.x - r,
                                        round(centre[1] / TILE_SIZE * PX_PER_TILE) - src.y - r),
                       special_flags=pygame.BLEND_RGB_MULT)
        return small

    def draw(self, screen: pygame.Surface, camera, offset_x: int, offset_y: int, level: float,
             ambient: Tuple[int, int, int], centre: Optional[Tuple[float, float]] = None,
             render_queue=None) -> None:
        """Lay the fog over the view at *level* (Weather.fog), lit by the scene's *ambient* light.

        *centre* (world px) is where it thins, round the player; the lights in
        *render_queue* (its BLEND_ADD entries) glow through it.
        """
        if level <= 0.005:
            self._small = None
            return
        tile_px = round(TILE_SIZE * camera.zoom)
        per_px = max(1, tile_px // PX_PER_TILE)   # tiles are 16 to 56 px: always a whole number
        scale = tile_px / float(TILE_SIZE)
        cam_x, cam_y = round(camera.x * scale), round(camera.y * scale)
        # The fog pixels in view, and one more all round so the smoothing has no edge in sight
        src = pygame.Rect(cam_x // per_px - 1, cam_y // per_px - 1,
                          camera.screen_width // per_px + 3, camera.screen_height // per_px + 3)
        colour = tuple(round(f * max(NIGHT_LIGHT_MIN, c / 255)) for f, c in zip(FOG_COLOUR, ambient))
        key = (src.topleft, src.size, per_px)
        if key != self._view_key or self._since_refresh >= REFRESH_SECONDS or self._mult is None:
            self._view_key = key
            self._since_refresh = 0.0
            self._small = self._gray_map(src, level, centre)
            self._small_src = src
            # Inverted and coloured while small (a flagged fill over the whole screen is slow), then smoothed up
            size = (src.width * per_px, src.height * per_px)
            inverse = pygame.Surface(src.size)
            inverse.fill((255, 255, 255))
            inverse.blit(self._small, (0, 0), special_flags=pygame.BLEND_RGB_SUB)
            tinted = self._small.copy()
            tinted.fill(colour, special_flags=pygame.BLEND_RGB_MULT)
            if self._mult is None or self._mult.get_size() != size:
                self._mult = pygame.Surface(size)
                self._add = pygame.Surface(size)
            pygame.transform.smoothscale(inverse, size, self._mult)
            pygame.transform.smoothscale(tinted, size, self._add)
        src = self._small_src
        pos = (src.x * per_px - cam_x + offset_x, src.y * per_px - cam_y + offset_y)
        screen.blit(self._mult, pos, special_flags=pygame.BLEND_MULT)
        screen.blit(self._add, pos, special_flags=pygame.BLEND_ADD)
        self._draw_wisps(screen, camera, offset_x, offset_y, scale, colour)
        if render_queue:
            self._draw_halos(screen, render_queue, level)

    def _sprites_for(self, scale: float, colour: Tuple[int, int, int]) -> list:
        """Per wisp kind, its sprite in WISP_FADE_STEPS opacities, at *scale* in *colour*."""
        key = (scale, tuple(c // 8 for c in colour))
        sprites = self._wisp_sprites.get(key)
        if sprites is None:
            if len(self._wisp_sprites) > 12:
                self._wisp_sprites.clear()
            sprites = []
            for w, h, alpha in WISP_KINDS:
                base = _soft_blob(round(w * TILE_SIZE * scale), round(h * TILE_SIZE * scale), colour, alpha)
                steps = []
                for step in range(1, WISP_FADE_STEPS + 1):
                    faded = base.copy()
                    faded.set_alpha(round(255 * step / WISP_FADE_STEPS))
                    steps.append(faded)
                sprites.append(steps)
            self._wisp_sprites[key] = sprites
        return sprites

    def _draw_wisps(self, screen, camera, offset_x, offset_y, scale, colour) -> None:
        if not self.wisps:
            return
        sprites = self._sprites_for(scale, colour)
        ox = offset_x - round(camera.x * scale)
        oy = offset_y - round(camera.y * scale)
        batch = []
        for x, y, _vx, _vy, age, seconds, kind in self.wisps:
            step = round(math.sin(math.pi * min(1.0, age / seconds)) * WISP_FADE_STEPS)
            if step <= 0:
                continue
            sprite = sprites[kind][step - 1]
            batch.append((sprite, (round(x * scale) + ox - sprite.get_width() // 2,
                                   round(y * scale) + oy - sprite.get_height() // 2)))
        screen.blits(batch, doreturn=False)

    def _draw_halos(self, screen, render_queue, level: float) -> None:
        """A soft round glow in each light's colour round it, for the light it spreads in the fog."""
        strength = HALO_STRENGTH * level
        if strength <= 0.02:
            return
        if len(self._halos) > 128:
            self._halos.clear()
        batch = []
        for obj in render_queue:
            if obj.get('flags') != pygame.BLEND_ADD:
                continue
            sprite = obj['sprite']
            w, h = sprite.get_size()
            r, g, b, a = pygame.transform.average_color(sprite)
            glow = tuple(round(c * a / 255 * strength / 16) * 16 for c in (r, g, b))   # as the light adds, in steps
            if not any(glow):
                continue
            size = (round(w * HALO_GROW) // 4 * 4 + 4, round(h * HALO_GROW) // 4 * 4 + 4)
            key = (size, glow)
            halo = self._halos.get(key)
            if halo is None:
                halo = _bump(64)
                halo.fill(glow, special_flags=pygame.BLEND_RGB_MULT)
                halo = self._halos[key] = pygame.transform.smoothscale(halo, size)
            batch.append((halo, (round(obj['pos'][0] + w / 2 - size[0] / 2), round(obj['pos'][1] + h / 2 - size[1] / 2)),
                          None, pygame.BLEND_ADD))
        if batch:
            screen.blits(batch, doreturn=False)
