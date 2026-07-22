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
