"""Fog of war: which parts of the map the player has seen, for the Town Plan.

The map is split into cells, ``FOG_CELLS_PER_TILE`` to a tile each way, and
every cell remembers how well it has been seen, from 0 (never) to 255 (fully).
Walking around reveals a small circle about the player: fully seen out to
``FOG_REVEAL_RADIUS_TILES``, then fading out over ``FOG_FADE_TILES``, so the
edge of the known world is soft rather than a staircase of cells. A cell only
ever gets better known, never forgotten.

The exploration map itself is always shown in full; only the Town Plan leaves
unexplored land blank, as not yet charted. It does so with a veil, as opaque
as the cells are unknown (``veil()``): one small surface, a pixel per cell,
scaled to the plan - scaling smoothly is what softens it between cells. The
veil is white, so multiplying blank paper into it gives paper to lay over the
plan.

What has been seen is part of the save (``to_save()`` / ``load()``). A save
without it, or one made for a map of another size, starts with nothing seen.
"""

import base64
import math
import zlib
from typing import Any, Dict, Optional, Tuple

import pygame

from ..config.constants import FOG_CELLS_PER_TILE, FOG_REVEAL_RADIUS_TILES, FOG_FADE_TILES

# How well a cell is known, mapped to how opaque its veil is
_UNSEEN_ALPHA = bytes(255 - seen for seen in range(256))


class FogOfWar:
    """The explored cells of one map and the veil drawn over the rest."""

    def __init__(self, map_width: int, map_height: int, tile_size: int) -> None:
        """Start with nothing explored.

        Args:
            map_width: Map width in tiles.
            map_height: Map height in tiles.
            tile_size: Tile size in world pixels.
        """
        self.cells_per_tile = FOG_CELLS_PER_TILE
        self.cell_size = tile_size / self.cells_per_tile
        self.width = map_width * self.cells_per_tile
        self.height = map_height * self.cells_per_tile
        self.explored = bytearray(self.width * self.height)
        self._cells_veil = self._veil_from(self.explored)
        self._last_cell: Optional[Tuple[int, int]] = None
        # Bumped whenever the cells change, so the scaled veil is redone
        self._version = 0
        self._scaled_key: Optional[Tuple[Any, ...]] = None
        self._scaled: Optional[pygame.Surface] = None

    def _veil_from(self, explored: bytearray) -> pygame.Surface:
        """White pixels, each as opaque as its cell is unexplored."""
        pixels = bytearray([255]) * (4 * len(explored))
        pixels[3::4] = explored.translate(_UNSEEN_ALPHA)
        image = pygame.image.frombytes(bytes(pixels), (self.width, self.height), "RGBA")
        # Copied into the usual alpha format: blitting that one is many times faster.
        # On an all-zero surface, MAX blending copies every channel as it is.
        veil = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        veil.blit(image, (0, 0), special_flags=pygame.BLEND_RGBA_MAX)
        return veil

    def reveal(self, world_x: float, world_y: float) -> None:
        """Explore the circle around a point (the player's centre).

        Cheap to call every frame: nothing happens until the point has moved
        into another cell.
        """
        cell = (int(world_x // self.cell_size), int(world_y // self.cell_size))
        if cell == self._last_cell:
            return
        self._last_cell = cell

        cx = world_x / self.cell_size
        cy = world_y / self.cell_size
        inner = FOG_REVEAL_RADIUS_TILES * self.cells_per_tile
        fade = max(1e-6, FOG_FADE_TILES * self.cells_per_tile)
        outer = inner + fade
        x0 = max(0, int(cx - outer))
        x1 = min(self.width - 1, int(cx + outer) + 1)
        y0 = max(0, int(cy - outer))
        y1 = min(self.height - 1, int(cy + outer) + 1)

        changed = False
        explored = self.explored
        veil = self._cells_veil
        veil.lock()
        try:
            for y in range(y0, y1 + 1):
                dy = y + 0.5 - cy
                row = y * self.width
                for x in range(x0, x1 + 1):
                    distance = math.hypot(x + 0.5 - cx, dy)
                    if distance >= outer:
                        continue
                    seen = 255 if distance <= inner else int(255 * (outer - distance) / fade)
                    if seen > explored[row + x]:
                        explored[row + x] = seen
                        veil.set_at((x, y), (255, 255, 255, 255 - seen))
                        changed = True
        finally:
            veil.unlock()
        if changed:
            self._version += 1

    def is_explored(self, world_x: float, world_y: float) -> bool:
        """Whether the point lies anywhere in explored land, however faintly."""
        x = int(world_x // self.cell_size)
        y = int(world_y // self.cell_size)
        if not (0 <= x < self.width and 0 <= y < self.height):
            return False
        return self.explored[y * self.width + x] > 0

    def veil(self, world_rect: Tuple[float, float, float, float],
             scale: float) -> Tuple[pygame.Surface, Tuple[float, float]]:
        """The veil over a stretch of the world, scaled for drawing.

        Args:
            world_rect: The world pixels shown, as (left, top, right, bottom).
            scale: Screen pixels per world pixel.

        Returns:
            The veil and the world point its top-left corner lies on. It
            reaches a cell or two past ``world_rect``, so its smoothed edge
            has neighbours.
        """
        left, top, right, bottom = world_rect
        cx0 = max(0, int(left // self.cell_size) - 1)
        cy0 = max(0, int(top // self.cell_size) - 1)
        cx1 = min(self.width, max(cx0 + 1, int(right // self.cell_size) + 2))
        cy1 = min(self.height, max(cy0 + 1, int(bottom // self.cell_size) + 2))
        size = (max(1, round((cx1 - cx0) * self.cell_size * scale)),
                max(1, round((cy1 - cy0) * self.cell_size * scale)))
        key = (cx0, cy0, cx1, cy1, size, self._version)
        if key != self._scaled_key:
            window = self._cells_veil.subsurface((cx0, cy0, cx1 - cx0, cy1 - cy0))
            self._scaled = pygame.transform.smoothscale(window, size)
            self._scaled_key = key
        return self._scaled, (cx0 * self.cell_size, cy0 * self.cell_size)

    def to_save(self) -> Dict[str, Any]:
        """The explored cells, compressed, for the save file."""
        return {
            "width": self.width,
            "height": self.height,
            "data": base64.b64encode(zlib.compress(bytes(self.explored), 9)).decode("ascii"),
        }

    def load(self, saved: Optional[Dict[str, Any]]) -> None:
        """Replace what has been seen with a save's, or with nothing.

        A missing entry, or one for a grid of another size (the map was
        resized, or the cells were made finer), leaves everything unexplored.
        """
        explored = bytearray(self.width * self.height)
        if saved and saved.get("width") == self.width and saved.get("height") == self.height:
            try:
                data = zlib.decompress(base64.b64decode(saved["data"]))
                if len(data) == len(explored):
                    explored = bytearray(data)
            except (KeyError, ValueError, zlib.error):
                pass
        self.explored = explored
        self._cells_veil = self._veil_from(explored)
        self._last_cell = None
        self._version += 1
