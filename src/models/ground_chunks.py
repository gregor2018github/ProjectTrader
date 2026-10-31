"""The map's ground tiles, drawn ahead in chunks instead of one by one each frame.

The `Ground*` tile layers never change while playing, so a square of
CHUNK_TILES x CHUNK_TILES tiles is drawn once per zoom level into a surface of
its own and the view blits a few dozen of those rather than thousands of tiles.

The ground comes in two passes because the animated water goes between them
(map_view._draw_animated_water): *below* is every layer up to and including
`Ground_Mid`, whose water cells are left out for the water to fill, *above* is
the shoreline and the rest. Below is opaque (black where no layer has a tile,
as the view's background was); above is see-through and left out where empty.
Above is laid together and drawn with premultiplied alpha: soft-edged tiles
overlap there, and straight alpha laid onto a see-through surface first comes
out different from each tile laid onto the ground in turn, premultiplied not.

Chunks are kept in a least-recently-used cache per pass, CHUNK_CACHE_BYTES
each, so walking the whole map at every zoom level does not hold it all.
"""

from collections import OrderedDict
from itertools import chain
from typing import TYPE_CHECKING, Dict, Iterator, List, Optional, Tuple

import pygame
import pytmx

if TYPE_CHECKING:
    from .map import Camera, TMXMap

#: Tiles along each side of a chunk
CHUNK_TILES = 8
#: Memory the cached chunks of one pass may take, at 4 bytes a pixel
CHUNK_CACHE_BYTES = 96 * 1024 * 1024

ChunkKey = Tuple[float, int, int]  # (zoom key, chunk column, chunk row)


class _ChunkCache:
    """Chunk surfaces of one pass, the least recently drawn dropped first."""

    def __init__(self) -> None:
        self.surfaces: "OrderedDict[ChunkKey, Optional[pygame.Surface]]" = OrderedDict()
        self.bytes = 0

    def get(self, key: ChunkKey) -> Tuple[bool, Optional[pygame.Surface]]:
        if key in self.surfaces:
            self.surfaces.move_to_end(key)
            return True, self.surfaces[key]
        return False, None

    def put(self, key: ChunkKey, surface: Optional[pygame.Surface]) -> None:
        self.surfaces[key] = surface
        if surface is not None:
            self.bytes += surface.get_width() * surface.get_height() * 4
        while self.bytes > CHUNK_CACHE_BYTES and len(self.surfaces) > 1:
            _, old = self.surfaces.popitem(last=False)
            if old is not None:
                self.bytes -= old.get_width() * old.get_height() * 4


class GroundChunks:
    """Draws the ground tile layers of a TMXMap from cached chunks."""

    def __init__(self, tmx_map: "TMXMap") -> None:
        self.tmx_map = tmx_map
        layers = [layer for layer in tmx_map.tmx_data.visible_layers
                  if isinstance(layer, pytmx.TiledTileLayer) and layer.name.startswith("Ground")]
        names = [layer.name for layer in layers]
        # Without a Ground_Mid everything is below and the water goes on top of it
        split = names.index("Ground_Mid") + 1 if "Ground_Mid" in names else len(layers)
        self.below_layers: List[pytmx.TiledTileLayer] = layers[:split]
        self.above_layers: List[pytmx.TiledTileLayer] = layers[split:]
        self._below = _ChunkCache()
        self._above = _ChunkCache()
        # Premultiplied copies of the scaled tiles, for the pass above
        self._premultiplied: Dict[Tuple[float, int], pygame.Surface] = {}
        # Tiled hangs a tile bigger than the grid up and to the right of its
        # cell, so a chunk must also look that far below and left of itself
        self._reach_x, self._reach_y = self._overhang(layers)

    def _overhang(self, layers: List[pytmx.TiledTileLayer]) -> Tuple[int, int]:
        """Whole tiles the biggest ground tile reaches past its own cell."""
        tile = self.tmx_map.tile_size
        reach_x = reach_y = 0
        for gid in set(chain.from_iterable(chain.from_iterable(layer.data for layer in layers))):
            image = self.tmx_map.tmx_data.get_tile_image_by_gid(gid) if gid else None
            if image:
                reach_x = max(reach_x, -(-image.get_width() // tile) - 1)
                reach_y = max(reach_y, -(-image.get_height() // tile) - 1)
        return reach_x, reach_y

    # --- Drawing ---------------------------------------------------------

    def visible_chunks(self, camera: "Camera") -> Iterator[Tuple[int, int]]:
        """The chunks (column, row) the camera's view touches."""
        tmx = self.tmx_map
        tile = tmx.tile_size
        start_x = max(0, int(camera.x // tile))
        start_y = max(0, int(camera.y // tile))
        end_x = min(tmx.width, int((camera.x + camera.screen_width / camera.zoom) // tile) + 2)
        end_y = min(tmx.height, int((camera.y + camera.screen_height / camera.zoom) // tile) + 2)
        for cy in range(start_y // CHUNK_TILES, (end_y - 1) // CHUNK_TILES + 1):
            for cx in range(start_x // CHUNK_TILES, (end_x - 1) // CHUNK_TILES + 1):
                yield cx, cy

    def draw_below(self, screen: pygame.Surface, camera: "Camera", offset_x: int, offset_y: int) -> None:
        """The layers under the water, opaque."""
        self._draw(screen, camera, offset_x, offset_y, self._below, below=True)

    def draw_above(self, screen: pygame.Surface, camera: "Camera", offset_x: int, offset_y: int) -> None:
        """The layers over the water."""
        if self.above_layers:
            self._draw(screen, camera, offset_x, offset_y, self._above, below=False)

    def _draw(self, screen: pygame.Surface, camera: "Camera", offset_x: int, offset_y: int,
              cache: _ChunkCache, below: bool) -> None:
        zoom_key = round(float(camera.zoom), 3)
        span = CHUNK_TILES * self.tmx_map.tile_size
        blits = []
        for cx, cy in self.visible_chunks(camera):
            surface = self._chunk(cache, (zoom_key, cx, cy), below)
            if surface is not None:
                # The camera's origin is whole pixels and so is every chunk's corner
                screen_x, screen_y = camera.apply(cx * span, cy * span)
                position = (round(screen_x) + offset_x, round(screen_y) + offset_y)
                blits.append((surface, position) if below else
                             (surface, position, None, pygame.BLEND_PREMULTIPLIED))
        screen.blits(blits, doreturn=False)

    def has_chunk(self, zoom: float, cx: int, cy: int) -> bool:
        """Whether both passes of a chunk are ready at this zoom."""
        key = (round(float(zoom), 3), cx, cy)
        return key in self._below.surfaces and (not self.above_layers or key in self._above.surfaces)

    def build_chunk(self, zoom: float, cx: int, cy: int) -> None:
        """Draw both passes of a chunk ahead of time, if not done already."""
        key = (round(float(zoom), 3), cx, cy)
        self._chunk(self._below, key, below=True)
        if self.above_layers:
            self._chunk(self._above, key, below=False)

    def _chunk(self, cache: _ChunkCache, key: ChunkKey, below: bool) -> Optional[pygame.Surface]:
        found, surface = cache.get(key)
        if not found:
            surface = self._render(key, below)
            cache.put(key, surface)
        return surface

    def _premultiplied_tile(self, gid: int, zoom: float) -> Optional[pygame.Surface]:
        key = (zoom, gid)
        if key not in self._premultiplied:
            image = self.tmx_map._get_scaled_tile(gid, zoom)
            self._premultiplied[key] = image.convert_alpha().premul_alpha() if image else None
        return self._premultiplied[key]

    def _render(self, key: ChunkKey, below: bool) -> Optional[pygame.Surface]:
        """One chunk of one pass, or None where it has nothing to show."""
        zoom, cx, cy = key
        tmx = self.tmx_map
        scaled = round(tmx.tile_size * zoom)
        x0, y0 = cx * CHUNK_TILES, cy * CHUNK_TILES
        x1, y1 = min(tmx.width, x0 + CHUNK_TILES), min(tmx.height, y0 + CHUNK_TILES)
        if x1 <= x0 or y1 <= y0:
            return None
        size = ((x1 - x0) * scaled, (y1 - y0) * scaled)
        water_tiles = tmx.water_tiles
        layers = self.below_layers if below else self.above_layers

        blits = []
        for layer in layers:
            skip_water = below and layer.name == "Ground_Mid"
            for y in range(y0, min(tmx.height, y1 + self._reach_y)):
                row = layer.data[y]
                for x in range(max(0, x0 - self._reach_x), x1):
                    gid = row[x]
                    if not gid or (skip_water and (x, y) in water_tiles):
                        continue
                    image = tmx._get_scaled_tile(gid, zoom) if below else self._premultiplied_tile(gid, zoom)
                    if image:
                        # Tiled aligns tiles to the bottom-left of the grid cell
                        position = ((x - x0) * scaled, (y - y0) * scaled - (image.get_height() - scaled))
                        blits.append((image, position) if below else
                                     (image, position, None, pygame.BLEND_PREMULTIPLIED))
        if not blits and not below:
            return None
        if below:
            surface = pygame.Surface(size).convert()
            surface.fill((0, 0, 0))
        else:
            surface = pygame.Surface(size, pygame.SRCALPHA).convert_alpha()
            surface.fill((0, 0, 0, 0))
        surface.blits(blits, doreturn=False)
        return surface
