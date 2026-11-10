"""Where on a building the rain may splash: its roofs, and nowhere else on it.

The roofs are polygons on the map's `Roofs` object layer, one or more per
building, named after it (as building lights are on `Lights`); they are not
tied to their building otherwise. A polygon of Tiled type `Hole` on that
layer is where a roof is open (a courtyard, a gap between two wings): it
cuts the roofs named after the same building that it lies on
(`match_holes`), and nobody else's. A raindrop landing where a building's
sprite is painted only splashes inside a roof; on a wall, a window, a door,
a fence or a cart it just ends unseen. Where no building is painted it
splashes on the ground, drawn under everything standing (a tree's crown, a
person), which hides it there; a roof's splashes are drawn over everything.

Both the buildings' painted pixels (`pygame.mask` of each sprite, shared by
buildings that share a sprite) and the roofs are filed by the tiles they
cover, so asking about a point looks at only the few things over its tile.
"""

from typing import Dict, List, Optional, Sequence, Tuple

import pygame

from ..config.constants import TILE_SIZE

Point = Tuple[float, float]


def _inside(points: Sequence[Point], x: float, y: float) -> bool:
    """Whether a point lies inside a polygon (even-odd rule)."""
    inside = False
    for (ax, ay), (bx, by) in zip(points, list(points[1:]) + [points[0]]):
        if (ay > y) != (by > y) and x < ax + (y - ay) * (bx - ax) / (by - ay):
            inside = not inside
    return inside


def _box(points: Sequence[Point]) -> Tuple[float, float, float, float]:
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


Shape = Tuple[List[Point], List[List[Point]]]   # a roof's points and the holes in it


def match_holes(roofs: Sequence[Tuple[str, List[Point]]], holes: Sequence[Tuple[str, List[Point]]]) -> List[Shape]:
    """Each roof's points with its holes: those named after the same building that overlap it."""
    shapes = []
    for name, points in roofs:
        left, top, right, bottom = _box(points)
        cut = []
        for hole_name, hole in holes:
            hl, ht, hr, hb = _box(hole)
            if hole_name == name and hl < right and left < hr and ht < bottom and top < hb:
                cut.append(hole)
        shapes.append((points, cut))
    return shapes


def _tiles(rect: pygame.Rect):
    for ty in range(rect.top // TILE_SIZE, (rect.bottom - 1) // TILE_SIZE + 1):
        for tx in range(rect.left // TILE_SIZE, (rect.right - 1) // TILE_SIZE + 1):
            yield tx, ty


class Roofs:
    """The buildings' painted pixels and their roofs, to ask whether rain may splash at a point."""

    def __init__(self, houses, roofs: List[Shape]) -> None:
        """*roofs*: each roof's points and its holes (match_holes())."""
        self.shapes = roofs
        self._sprites: Dict[Tuple[int, int], List[Tuple[pygame.Rect, pygame.Mask]]] = {}
        self._roofs: Dict[Tuple[int, int], List[Shape]] = {}
        masks: Dict[int, pygame.Mask] = {}
        for house in houses:
            image: Optional[pygame.Surface] = getattr(house, 'image', None)
            if image is None:
                continue
            if id(image) not in masks:
                masks[id(image)] = pygame.mask.from_surface(image)
            rect = pygame.Rect(round(house.x), round(house.y) - image.get_height(), *image.get_size())
            for tile in _tiles(rect):
                self._sprites.setdefault(tile, []).append((rect, masks[id(image)]))
        for shape in roofs:
            left, top, right, bottom = _box(shape[0])
            box = pygame.Rect(int(left), int(top), int(right - left) + 1, int(bottom - top) + 1)
            for tile in _tiles(box):
                self._roofs.setdefault(tile, []).append(shape)

    def on_building(self, x: float, y: float) -> bool:
        """Whether a building's sprite is painted at a world point."""
        for rect, mask in self._sprites.get((int(x // TILE_SIZE), int(y // TILE_SIZE)), ()):
            if rect.collidepoint(x, y) and mask.get_at((int(x) - rect.x, int(y) - rect.y)):
                return True
        return False

    def on_roof(self, x: float, y: float) -> bool:
        """Whether a world point is inside a roof, and not in one of its holes."""
        return any(_inside(points, x, y) and not any(_inside(hole, x, y) for hole in holes)
                   for points, holes in self._roofs.get((int(x // TILE_SIZE), int(y // TILE_SIZE)), ()))
