"""Gets the map's drawing ready ahead of time, so nothing is made mid-frame.

Most of what the map view draws is scaled or baked once per zoom level and
then kept: tiles and ground chunks, trees, houses, bridges, the crops at each
angle they sway to, the water's frames and its cut-out shoreline. Left to the
first frame that needs them, they made the game stutter for its first seconds
and on every new zoom level (40 to 110 ms a frame here, far more on a slow PC).

`MapWarmup` (owned by GameMap as `warmup`) does that work instead:
`prepare()` while the game loads, everything at the starting zoom and the
ground around the player; then `step()` every frame, for at most
WARMUP_BUDGET_S, keeps the ground ready just outside the view (so walking never
waits for a chunk) and works through the other zoom levels a small job at a
time, the nearest ones first. The hidden farthest-out levels are only warmed
once the player has been to one.
"""

import time
from typing import TYPE_CHECKING, Iterator, List, Optional, Set, Tuple

from .field import _AMBIENT_AMP, _ANGLE_STEP, _GUST_AMP
from .ground_chunks import CHUNK_TILES
from .water import (
    WATER_FRAME_COUNT,
    bake_water_frame,
    get_masked_water_surface,
    get_water_edge_overlay_frames,
    get_water_tile_frames,
)

if TYPE_CHECKING:
    from .map import GameMap

#: Time each frame may spend on getting ahead
WARMUP_BUDGET_S = 0.0015
#: Chunks kept ready beyond each edge of the view
CHUNK_MARGIN = 1


class MapWarmup:
    """Scales and bakes the map's drawing before it is needed."""

    def __init__(self, game_map: "GameMap") -> None:
        self.game_map = game_map
        #: Zoom levels whose sprites, crops and water are all made
        self.warm_zooms: Set[float] = set()
        self._background: Optional[Iterator[None]] = None

    # --- Entry points ------------------------------------------------------

    def prepare(self, view_size: Tuple[int, int]) -> None:
        """Make all of the starting zoom level and the ground around the player.

        Called while the game loads, with the size the map view will have.
        """
        camera = self.game_map.camera
        camera.screen_width, camera.screen_height = view_size
        player = self.game_map.map_player
        tmx = self.game_map.tmx_map
        camera.update(player.x + player.width / 2.0, player.y + player.height / 2.0,
                      tmx.width * tmx.tile_size, tmx.height * tmx.tile_size)
        for _ in self._zoom_jobs(camera.zoom):
            pass
        for _ in self._chunk_jobs(camera.zoom, self._view_chunks(camera.zoom)):
            pass

    def step(self, budget_s: float = WARMUP_BUDGET_S) -> None:
        """Get ahead for at most *budget_s* seconds."""
        deadline = time.perf_counter() + budget_s
        zoom = self.game_map.camera.zoom
        # The ground about to come into view first: walking must never wait for it
        for _ in self._chunk_jobs(zoom, self._view_chunks(zoom, CHUNK_MARGIN)):
            if time.perf_counter() >= deadline:
                return
        if self._background is None:
            self._background = self._next_zoom_jobs()
        for _ in self._background:
            if time.perf_counter() >= deadline:
                return
        self._background = None

    # --- Jobs -------------------------------------------------------------

    def _next_zoom_jobs(self) -> Iterator[None]:
        """The next zoom level not warmed yet, nearest to the current one first."""
        game_map = self.game_map
        levels = game_map.zoom_levels
        current = game_map.zoom_index
        # The hidden levels only once the player has gone out that far
        lowest = min(game_map.min_normal_zoom_index, current)
        candidates = sorted(range(lowest, len(levels)), key=lambda index: abs(index - current))
        for index in candidates:
            zoom = levels[index]
            if round(zoom, 3) in self.warm_zooms:
                continue
            yield from self._zoom_jobs(zoom)
            # And the ground the view would show if the player zoomed there now
            yield from self._chunk_jobs(zoom, self._view_chunks(zoom))
            return

    def _zoom_jobs(self, zoom: float) -> Iterator[None]:
        """Everything at one zoom level but the ground, one small job per yield."""
        tmx = self.game_map.tmx_map
        for house in tmx.houses:
            house.get_scaled_sprite(zoom)
            yield
        for tree in tmx.trees:
            tree.get_scaled_sprite(zoom)
            yield
        for bridge in tmx.bridges:
            bridge.get_scaled_sprite(zoom)
            bridge.get_scaled_front(zoom)
            yield
        for mill in tmx.mills:
            mill.get_blade_sprite(zoom)
            yield
        yield from self._crop_jobs(zoom)
        yield from self._water_jobs(zoom)
        self.warm_zooms.add(round(zoom, 3))

    def _crop_jobs(self, zoom: float) -> Iterator[None]:
        """Each crop sprite at every angle the wind sways it to."""
        lowest = -(_GUST_AMP + _AMBIENT_AMP)
        bins = [step * _ANGLE_STEP for step in range(round(lowest / _ANGLE_STEP) - 1,
                                                      round(_AMBIENT_AMP / _ANGLE_STEP) + 2)]
        for field in self.game_map.tmx_map.fields:
            for sprite_idx in range(len(field.images)):
                for angle in bins:
                    field.get_sway_sprite(sprite_idx, zoom, angle)
                yield

    def _water_jobs(self, zoom: float) -> Iterator[None]:
        """The water's frames, then every shoreline tile's cut-out of them."""
        tmx = self.game_map.tmx_map
        if not tmx.water_tiles:
            return
        tile = tmx.tile_size
        for index in range(WATER_FRAME_COUNT):
            bake_water_frame(tile, zoom, index)
            yield
        frames = get_water_tile_frames(tile, zoom, 0)
        ground_mid = next((layer for layer in tmx.tmx_data.visible_layers
                           if getattr(layer, "name", None) == "Ground_Mid"
                           and hasattr(layer, "data")), None)
        if ground_mid is None:
            return
        gids: Set[int] = set()
        edges: Set[Tuple[int, int]] = set()
        for (x, y) in tmx.water_tiles:
            gid = ground_mid.data[y][x]
            if gid:
                gids.add(gid)
                if (x, y) in tmx.water_edge_tiles:
                    edges.add((gid, tmx.water_tile_variant.get((x, y), 0)))
        for gid in gids:
            for index in range(WATER_FRAME_COUNT):
                get_masked_water_surface(tmx.tmx_data, gid, frames[index], "water", index)
            yield
        for gid, variant in edges:
            overlays = get_water_edge_overlay_frames(tile, zoom, variant)
            for index in range(WATER_FRAME_COUNT):
                get_masked_water_surface(tmx.tmx_data, gid, overlays[index], f"edge{variant}", index)
            yield

    def _chunk_jobs(self, zoom: float, chunks: List[Tuple[int, int]]) -> Iterator[None]:
        ground = self.game_map.tmx_map.ground_chunks
        for cx, cy in chunks:
            if not ground.has_chunk(zoom, cx, cy):
                ground.build_chunk(zoom, cx, cy)
                yield

    def _view_chunks(self, zoom: float, margin: int = 0) -> List[Tuple[int, int]]:
        """The chunks a view centred where the camera is would show at *zoom*,
        *margin* more on each side, nearest the middle first."""
        camera = self.game_map.camera
        tmx = self.game_map.tmx_map
        span = CHUNK_TILES * tmx.tile_size
        # The camera's middle, the same at any zoom unless it is held at the map's edge
        middle_x = camera.x + camera.screen_width / camera.zoom / 2.0
        middle_y = camera.y + camera.screen_height / camera.zoom / 2.0
        half_w = camera.screen_width / zoom / 2.0
        half_h = camera.screen_height / zoom / 2.0
        last_x = (tmx.width - 1) // CHUNK_TILES
        last_y = (tmx.height - 1) // CHUNK_TILES
        first_cx = max(0, int((middle_x - half_w) // span) - margin)
        first_cy = max(0, int((middle_y - half_h) // span) - margin)
        end_cx = min(last_x, int((middle_x + half_w) // span) + margin)
        end_cy = min(last_y, int((middle_y + half_h) // span) + margin)
        chunks = [(cx, cy) for cy in range(first_cy, end_cy + 1) for cx in range(first_cx, end_cx + 1)]
        mid_cx, mid_cy = middle_x / span, middle_y / span
        chunks.sort(key=lambda c: (c[0] + 0.5 - mid_cx) ** 2 + (c[1] + 0.5 - mid_cy) ** 2)
        return chunks
