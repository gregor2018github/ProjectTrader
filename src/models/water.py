"""Water body model.

Stores a polygon-shaped water body parsed from the TMX "Water" object layer.
Provides collision testing so the player cannot walk over water.
Future extensions (boats, fishing spots, river flow, etc.) should be added here.
"""

from typing import List, Tuple
import pygame


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
