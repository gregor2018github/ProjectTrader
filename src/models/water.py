"""Water body model.

Stores a polygon-shaped water body parsed from the TMX "Water" object layer.
Provides collision testing so the player cannot walk over water.
Future extensions (boats, fishing spots, river flow, etc.) should be added here.
"""

import math
import random
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING
import pygame

from ..config.constants import SPLASH_VOLUME, TILE_SIZE

if TYPE_CHECKING:
    from ..game_state import GameState
    from .map import Camera


def _point_segment_distance(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
    """Shortest distance from (px, py) to the segment (x1, y1)-(x2, y2)."""
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
    proj_x, proj_y = x1 + t * dx, y1 + t * dy
    return math.hypot(px - proj_x, py - proj_y)


# Surface cache keyed by (radius_px, alpha_quantized) — same pattern as smoke.py
_ripple_surf_cache: Dict[Tuple[int, int], pygame.Surface] = {}


def _get_ripple_surf(radius_px: int, alpha: int) -> pygame.Surface:
    alpha_q = (alpha // 8) * 8  # quantize to 32 levels
    key = (radius_px, alpha_q)
    if key not in _ripple_surf_cache:
        size = radius_px * 2 + 4
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.circle(surf, (230, 245, 255, alpha_q), (size // 2, size // 2), radius_px, 2)
        _ripple_surf_cache[key] = surf
    return _ripple_surf_cache[key]


class Ripple:
    """A small expanding, fading ring — the splash left behind by a thrown stone.

    ``delay`` lets a second ring be spawned at the same spot that only starts
    growing a moment after the first one, mimicking a real splash's second pulse.
    """

    __slots__ = ('x', 'y', 'age', 'delay', 'duration', 'max_radius')

    def __init__(self, x: float, y: float, delay: float = 0.0, radius_cap: float = 18.0) -> None:
        self.x = x
        self.y = y
        self.age = 0.0
        self.delay = delay
        self.duration = random.uniform(1.0, 1.4)
        # world units — kept small, and capped further so it never outgrows a tight spot
        self.max_radius = min(random.uniform(12.0, 18.0), radius_cap)

    def update(self, dt: float) -> bool:
        """Age the ripple. Returns False once its lifetime has expired."""
        self.age += dt
        return self.age < self.delay + self.duration

    @property
    def is_visible(self) -> bool:
        return self.age >= self.delay

    def get_render_data(self, camera: 'Camera', zoom: float) -> Tuple[pygame.Surface, Tuple[float, float]]:
        t = min(1.0, (self.age - self.delay) / self.duration)
        radius = self.max_radius * t
        alpha = int(200 * (1.0 - t))
        radius_px = max(1, round(radius * zoom))
        surf = _get_ripple_surf(radius_px, alpha)
        sx, sy = camera.apply(self.x, self.y)
        half = surf.get_width() / 2.0
        return surf, (sx - half, sy - half)


class Water:
    """A polygon-shaped water body on the game map."""

    def __init__(self, name: str, points: List[Tuple[float, float]]) -> None:
        """
        Args:
            name: Object name from Tiled (e.g. "Water").
            points: World-space polygon vertices in order.
        """
        self.name = name
        self.points = points
        self._bounding_rect = self._compute_bounding_rect()

    def _compute_bounding_rect(self) -> pygame.Rect:
        xs = [p[0] for p in self.points]
        ys = [p[1] for p in self.points]
        x_min, x_max = min(xs), max(xs)
        y_min, y_max = min(ys), max(ys)
        return pygame.Rect(int(x_min), int(y_min), int(x_max - x_min), int(y_max - y_min))

    def contains_point(self, px: float, py: float) -> bool:
        """Ray casting point-in-polygon test."""
        n = len(self.points)
        inside = False
        j = n - 1
        for i in range(n):
            xi, yi = self.points[i]
            xj, yj = self.points[j]
            if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi) + xi):
                inside = not inside
            j = i
        return inside

    def collides_with_rect(self, rect: pygame.Rect) -> bool:
        """Return True if any corner of rect lies inside this water polygon."""
        if not self._bounding_rect.colliderect(rect):
            return False
        corners = [
            (rect.left, rect.top),
            (rect.right, rect.top),
            (rect.left, rect.bottom),
            (rect.right, rect.bottom),
        ]
        return any(self.contains_point(cx, cy) for cx, cy in corners)

    def _boundary_distance(self, px: float, py: float) -> float:
        """Distance from (px, py) to the nearest polygon edge, regardless of in/out."""
        n = len(self.points)
        min_dist = float("inf")
        for i in range(n):
            x1, y1 = self.points[i]
            x2, y2 = self.points[(i + 1) % n]
            min_dist = min(min_dist, _point_segment_distance(px, py, x1, y1, x2, y2))
        return min_dist

    def distance_to_point(self, px: float, py: float) -> float:
        """Shortest distance from (px, py) to this polygon's boundary (0 if inside)."""
        if self.contains_point(px, py):
            return 0.0
        return self._boundary_distance(px, py)

    def _nearest_interior_point(self, px: float, py: float, max_radius: float = 300.0, step: float = 16.0) -> Tuple[float, float]:
        """Expanding local search for the closest point to (px, py) that's inside this polygon.

        Only used as a last resort when nothing sampled by random_point_near landed
        inside the water at all. Search stays local (capped radius) so the result is
        always near the player — unlike a polygon-wide vertex-average, which can land
        far off-screen for a large or oddly-shaped lake, making the ripple invisible.
        """
        if self.contains_point(px, py):
            return px, py
        r = step
        while r <= max_radius:
            steps = max(8, int(2 * math.pi * r / step))
            for i in range(steps):
                angle = 2 * math.pi * i / steps
                x, y = px + math.cos(angle) * r, py + math.sin(angle) * r
                if self.contains_point(x, y):
                    return x, y
            r += step
        # Should not happen for a water body the player is standing next to.
        cx = sum(p[0] for p in self.points) / len(self.points)
        cy = sum(p[1] for p in self.points) / len(self.points)
        return cx, cy

    def random_point_near(
        self, px: float, py: float,
        min_dist: float = 24.0, max_dist: float = 64.0,
        edge_margin: float = TILE_SIZE, attempts: int = 32,
    ) -> Tuple[float, float]:
        """A random point within this polygon, roughly min_dist-max_dist from (px, py).

        Prefers a point at least ``edge_margin`` away from the water's edge, so a
        ripple doesn't grow out over the bank onto grass. In a tight spot (e.g. a
        narrow river) where nothing clears that margin, it settles for the closest
        sampled point that's still inside the water rather than reaching for a
        distant fallback. Callers should check ``_boundary_distance`` on the
        result to cap the ripple's own radius so it still fits.
        """
        best: Optional[Tuple[float, float]] = None
        best_margin = -1.0
        for dist_cap in (max_dist, max(self._bounding_rect.width, self._bounding_rect.height, max_dist)):
            for _ in range(attempts):
                angle = random.uniform(0, 2 * math.pi)
                dist = random.uniform(min_dist, dist_cap)
                x, y = px + math.cos(angle) * dist, py + math.sin(angle) * dist
                if not self.contains_point(x, y):
                    continue
                bd = self._boundary_distance(x, y)
                if bd >= edge_margin:
                    return x, y
                if bd > best_margin:
                    best_margin, best = bd, (x, y)
            if best is not None:
                return best
        return self._nearest_interior_point(px, py)

    def throw_rock(self, game_state: 'GameState') -> None:
        """Play a splash sound and spawn a pair of ripples. No cost, no other effect (yet)."""
        if not game_state.game:
            return
        splash_num = random.randint(1, 4)
        channel = game_state.game.play_sound(f"splash_{splash_num}")
        if channel:
            channel.set_volume(SPLASH_VOLUME)

        game_map = getattr(game_state.game, 'game_map', None)
        if game_map is not None:
            player = game_map.map_player
            px = player.x + player.width / 2
            py = player.y + player.height / 2
            rx, ry = self.random_point_near(px, py)
            # Cap the ripple's radius to the space actually available at this
            # spot, so it can't grow out over the bank in a tight/narrow area.
            radius_cap = max(6.0, min(18.0, self._boundary_distance(rx, ry)))
            game_map.add_ripple(rx, ry, radius_cap=radius_cap)
            # A second ring from the same point, a beat behind the first.
            game_map.add_ripple(rx, ry, delay=random.uniform(0.15, 0.25), radius_cap=radius_cap)

        game_state.log_event("SYSTEM", "Threw a stone into the water")
        game_state.info_window = None


# --- Animated water surface --------------------------------------------------
#
# Water is rendered tile-by-tile, in lockstep with the "Ground" TMX layers
# (see map_view._render_map_layers): only tiles inside the current camera
# viewport are ever touched, and the animation frames themselves are baked
# once per (zoom, variant) and cached forever, so a visible water tile costs
# exactly one extra blit (same as a normal ground tile) and an off-screen or
# water-less map costs nothing at all. This mirrors the caching pattern
# TMXMap._get_scaled_tile already uses for ordinary tiles.
#
# For now every water polygon is rendered with the same "ocean" look; river
# variants can be layered on top of this later by branching on Water.name.

WATER_FRAME_COUNT = 6
WATER_FRAME_INTERVAL = 0.22  # seconds per animation frame

_WATER_VARIANT_COUNT = 3

_water_tile_cache: Dict[Tuple[float, int], List[pygame.Surface]] = {}
_water_edge_cache: Dict[Tuple[float, int], List[pygame.Surface]] = {}

_WATER_DEEP = (26, 70, 116)
_WATER_LIGHT = (96, 160, 196)
_WATER_FOAM = (235, 248, 255)

# Layered sine components that make up the shimmer field, each written as
# (cycles_x, cycles_y, phase_speed, weight). ``cycles_x``/``cycles_y`` MUST be
# integers: a sine whose argument advances by an integer multiple of 2*pi
# across one tile is exactly periodic over that tile, which is what makes
# neighbouring (identically-baked) tiles line up with no visible seam,
# regardless of tile pixel size. Three components at different orientations
# and speeds keep the shimmer from reading as "everything scrolling the same
# way" the way a single diagonal stripe family did.
_WAVE_COMPONENTS = (
    (2, 1, 1.0, 0.45),
    (-1, 2, 0.6, 0.30),
    (3, -2, 1.4, 0.25),
)


def water_tile_variant(grid_x: int, grid_y: int) -> int:
    """Deterministic pseudo-random variant for a grid cell.

    Used only for a subtle per-tile brightness nudge — never for the wave
    geometry itself, which must stay identical across every tile so that
    adjacent tiles (literally the same baked image) line up perfectly.

    Any *linear* combination of grid_x/grid_y (e.g. ``gx*A + gy*B``) is still
    periodic mod 3 along each axis on its own — that's exactly what produced
    hard periodic stripes here before (one prime happened to be divisible by
    3, so the pattern depended only on grid_y). A bit-mixing integer hash
    (xorshift-multiply, same family as "wang hash") has no such linear
    structure to alias against.
    """
    h = (grid_x * 374761393 + grid_y * 668265263) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    h ^= h >> 16
    return h % _WATER_VARIANT_COUNT


def get_water_tile_frames(tile_size: int, zoom: float, variant: int) -> List[pygame.Surface]:
    """Return the (lazily baked, cached) animation frames for a water tile variant.

    The tile is filled with a smooth, per-pixel shimmer field built from a
    few sine waves rather than drawn shapes — drawn rectangles/lines have
    hard square caps that leave a visible notch where each tile repeats;
    a continuous periodic function has no such edge to see. Baking is a
    one-off cost per (zoom, variant, frame) combination (a few thousand
    pixels, done with plain Python since this project has no numpy
    dependency); every subsequent lookup is a cache hit, and blitting an
    already-baked, fully opaque frame costs the same as an ordinary tile.

    ``variant`` is currently unused for the geometry/colour on purpose: an
    earlier version nudged the palette per variant, but that nudge is a hard
    step at the tile's edge (unlike the wave field, which is seamless by
    construction), and it read as faint rectangular patches. It's kept as a
    parameter — and grid cells are still hashed into a variant in
    ``water_tile_variant`` — so a future per-variant *pattern* (e.g. a
    distinct river look) has a slot to plug into without touching callers.
    """
    zoom_key = round(float(zoom), 3)
    # variant intentionally excluded from the cache key: it doesn't affect
    # the baked output yet (see docstring), so keying on it would just bake
    # (and store) the same image _WATER_VARIANT_COUNT times over.
    cache_key = (zoom_key, tile_size)
    cached = _water_tile_cache.get(cache_key)
    if cached is not None:
        return cached

    size = max(1, int(round(tile_size * zoom)))
    deep = _WATER_DEEP
    light = _WATER_LIGHT
    two_pi = 2.0 * math.pi

    frames: List[pygame.Surface] = []
    for i in range(WATER_FRAME_COUNT):
        phase = two_pi * i / WATER_FRAME_COUNT
        surf = pygame.Surface((size, size))
        pixels = pygame.PixelArray(surf)
        for y in range(size):
            fy = y / size
            for x in range(size):
                fx = x / size
                v = 0.0
                for cx, cy, speed, weight in _WAVE_COMPONENTS:
                    v += weight * math.sin(two_pi * (cx * fx + cy * fy) + phase * speed)
                # v is in roughly [-1, 1]; raise to an odd power to keep the
                # highlight sparse (soft glints) instead of a smooth 50/50
                # gradient, which read as too strong/opaque at full spread.
                t = max(0.0, min(1.0, (v + 1.0) / 2.0))
                t = t ** 3
                r = int(deep[0] + (light[0] - deep[0]) * t)
                g = int(deep[1] + (light[1] - deep[1]) * t)
                b = int(deep[2] + (light[2] - deep[2]) * t)
                pixels[x, y] = (r, g, b)
        pixels.close()
        frames.append(surf.convert())

    _water_tile_cache[cache_key] = frames
    return frames


def get_water_edge_overlay_frames(tile_size: int, zoom: float, variant: int = 0) -> List[pygame.Surface]:
    """Return a soft, gently pulsing foam-speckle overlay for shoreline tiles.

    Blitted on top of a normal water tile only for cells that border
    non-water tiles, so the extra alpha-blit cost is limited to the
    coastline. ``variant`` just reseeds the speckle layout so the shoreline
    doesn't repeat an identical dot pattern tile after tile.
    """
    zoom_key = (round(float(zoom), 3), variant)
    cached = _water_edge_cache.get(zoom_key)
    if cached is not None:
        return cached

    size = max(1, int(round(tile_size * zoom)))
    rng = random.Random(1234 + variant)  # fixed seed per variant: stable layout, varies by tile
    dots = [(rng.uniform(0, size), rng.uniform(0, size), rng.uniform(1.0, 2.0)) for _ in range(4)]

    frames: List[pygame.Surface] = []
    for i in range(WATER_FRAME_COUNT):
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
        pulse = 35 + int(30 * abs((i / WATER_FRAME_COUNT) - 0.5) * 2)
        for dx, dy, r in dots:
            pygame.draw.circle(surf, (*_WATER_FOAM, pulse), (int(dx), int(dy)), max(1, int(r * zoom)))
        frames.append(surf)

    _water_edge_cache[zoom_key] = frames
    return frames
