"""Finds the things standing in part of the map without looking at all of them.

The map view draws a few dozen of the 400-odd trees, 300 crop sprites and
150 window lights at a time, but used to ask every one of them each frame
whether it was on screen. A `SpatialIndex` files each item under the grid
cells its world rectangle touches, once at load, so a frame only looks at the
items in the cells the view touches. It is for things that do not move or
change size; the caller still checks each item it gets exactly.
"""

from typing import Dict, Generic, List, Tuple, TypeVar

import pygame

T = TypeVar("T")

#: Side of a cell, in world pixels
CELL_SIZE = 256


class SpatialIndex(Generic[T]):
    """Items filed by world rectangle, looked up by world rectangle."""

    def __init__(self, cell_size: int = CELL_SIZE) -> None:
        self.cell_size = cell_size
        self._items: List[T] = []
        self._cells: Dict[Tuple[int, int], List[int]] = {}

    def __len__(self) -> int:
        return len(self._items)

    def add(self, item: T, rect: pygame.Rect) -> None:
        """File *item*, which covers *rect* in world pixels."""
        index = len(self._items)
        self._items.append(item)
        size = self.cell_size
        for cell_y in range(rect.top // size, (rect.bottom - 1) // size + 1):
            for cell_x in range(rect.left // size, (rect.right - 1) // size + 1):
                self._cells.setdefault((cell_x, cell_y), []).append(index)

    def query(self, rect: pygame.Rect) -> List[T]:
        """The items whose rectangle may touch *rect*, in the order they were added."""
        size = self.cell_size
        cells = self._cells
        found = set()
        for cell_y in range(rect.top // size, (rect.bottom - 1) // size + 1):
            for cell_x in range(rect.left // size, (rect.right - 1) // size + 1):
                indices = cells.get((cell_x, cell_y))
                if indices:
                    found.update(indices)
        items = self._items
        return [items[index] for index in sorted(found)]
