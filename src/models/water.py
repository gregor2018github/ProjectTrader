"""Water body model.

Stores a polygon-shaped water body parsed from the TMX "Water" object layer.
Provides collision testing so the player cannot walk over water.
Future extensions (boats, fishing spots, river flow, etc.) should be added here.
"""

import math
import random
from typing import List, Tuple, TYPE_CHECKING
import pygame

from ..config.constants import SPLASH_VOLUME

if TYPE_CHECKING:
    from ..game_state import GameState


def _point_segment_distance(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
    """Shortest distance from (px, py) to the segment (x1, y1)-(x2, y2)."""
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
    proj_x, proj_y = x1 + t * dx, y1 + t * dy
    return math.hypot(px - proj_x, py - proj_y)


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

    def distance_to_point(self, px: float, py: float) -> float:
        """Shortest distance from (px, py) to this polygon's boundary (0 if inside)."""
        if self.contains_point(px, py):
            return 0.0
        n = len(self.points)
        min_dist = float("inf")
        for i in range(n):
            x1, y1 = self.points[i]
            x2, y2 = self.points[(i + 1) % n]
            min_dist = min(min_dist, _point_segment_distance(px, py, x1, y1, x2, y2))
        return min_dist

    def throw_rock(self, game_state: 'GameState') -> None:
        """Play a splash sound. No cost, no other effect (yet)."""
        if not game_state.game:
            return
        splash_num = random.randint(1, 4)
        channel = game_state.game.play_sound(f"splash_{splash_num}")
        if channel:
            channel.set_volume(SPLASH_VOLUME)
        game_state.log_event("SYSTEM", "Threw a stone into the water")
        game_state.info_window = None
