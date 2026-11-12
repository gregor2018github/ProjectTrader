"""Snow lying on the ground: broken flecks at first, in uneven clumps, and only later a white blanket.

Drawn over the ground layers (after the wet ground, under the bridges, the
puddles and everyone else) as white at an alpha per pixel. How white each
spot is follows Weather.snow_cover through a threshold per spot (snow_flecks.py):
a first snowfall lies as scattered flecks gathering in clumps, unevenly over
the map (smooth noise of two sizes, NOISE_TILES, moves whole areas earlier or
later); from BLANKET_FROM on the gaps between them fill in, in drifts first,
and a thaw takes it back the same way. By the kind of ground (PENALTY, from
the Town Plan's reading of the map, as for the wet ground) a spot whitens
later: grass and sand first, the forest floor under the trees later, the
roads and the paving, trodden all day, later still and never quite all;
water never.

Cheap: the snow is worked out in chunks of CHUNK_TILES square, at
DUST_PX_PER_TILE pixels a tile (a few blends on a small surface), scaled to
the zoom without smoothing and kept (least recently used, at most
CACHE_PIXELS) until the snow has deepened or thawed a LEVEL_STEPS step.
Chunks are made a few each frame within BUILD_BUDGET_S, those in view first
and the ring around it next, and a chunk is drawn as it was until its new
look is ready; drawing is one blit per chunk in view, none for a bare one.
"""

import random
import time
from collections import OrderedDict
from typing import Dict, Optional, Tuple

import pygame

from ..config.constants import TILE_SIZE
from . import snow_flecks

PX_PER_TILE = 4             # resolution of the smooth maps (noise, kinds of ground)
DUST_PX_PER_TILE = 16       # resolution the flecks are drawn at: 2 world px each
CHUNK_TILES = 16
NOISE_TILES = (5, 1.2)      # the size of the patches and drifts, large and small, in tiles
NOISE_SHARES = (0.65, 0.35)
NOISE_DUST = 0.4            # the noise moves where the flecks lie first by up to this much depth
BLANKET_FROM = 0.42         # the blanket between the flecks starts at this much depth...
NOISE_BLANKET = 0.45        # ...and later by up to this much more, by the noise
SNOW_COLOUR = (238, 242, 250)
SNOW_OPACITY = 0.93         # even deep snow lets a trace of the ground through, so it does not look flat
ROOM_SOFTEN = 4             # the kinds of ground shade into each other over about this many pixels (a tile)
# How much later (in 255ths of full depth) each kind of ground whitens; grass is 0
PENALTY = {
    "sand": 10,
    "wood": 40,
    "road": 62,
    "plaza": 72,
    "water": 255,
}
LEVEL_STEPS = 64            # the depths a chunk is made for
BUILD_BUDGET_S = 0.004      # time per frame for making chunks...
MISSING_BUDGET_S = 0.012    # ...more while one in view has none to show yet
CACHE_PIXELS = 14_000_000   # screen pixels of chunks kept

_MARGIN = 2                 # smooth-map pixels taken around a chunk, so neighbouring chunks meet without a seam


class SnowCover:
    """The map's snow on the ground, made once from its kinds of ground and drawn by chunks as it deepens or thaws."""

    def __init__(self, tiles_wide: int, tiles_high: int, rng: Optional[random.Random] = None) -> None:
        self.size = (tiles_wide * PX_PER_TILE, tiles_high * PX_PER_TILE)
        self.tiles = (tiles_wide, tiles_high)
        self.rng = rng or random.Random()
        self._noise = self._make_noise()
        self._dust: Optional[pygame.Surface] = None      # where the flecks lie first (alpha: threshold offset)
        self._blanket: Optional[pygame.Surface] = None   # where the blanket lies first (alpha: threshold)
        self._flecks = snow_flecks.fleck_tile(random.Random(self.rng.random()))
        self._chunks: "OrderedDict[Tuple[int, int, int], list]" = OrderedDict()   # -> [step, surface or None]
        self._cached_px = 0

    def set_ground(self, masks: Dict[str, pygame.Mask]) -> None:
        """Take over the kinds of ground: masks of "water", "sand", "road", "plaza" and "wood", self.size large."""
        penalty = pygame.Surface(self.size, pygame.SRCALPHA)
        penalty.fill((0, 0, 0, 0))
        for kind, value in PENALTY.items():
            if kind in masks:
                penalty.blit(masks[kind].to_surface(setcolor=(0, 0, 0, value), unsetcolor=(0, 0, 0, 0)),
                             (0, 0), special_flags=pygame.BLEND_RGBA_MAX)
        # Softened, so a road or the paving shades into the fields rather than ending at a tile's edge
        small = pygame.transform.smoothscale(penalty, (max(1, self.size[0] // ROOM_SOFTEN), max(1, self.size[1] // ROOM_SOFTEN)))
        penalty = pygame.transform.smoothscale(small, self.size)
        self._dust = self._scaled_noise(NOISE_DUST, 0)
        self._dust.blit(penalty, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
        self._blanket = self._scaled_noise(NOISE_BLANKET, round(255 * BLANKET_FROM))
        self._blanket.blit(penalty, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
        self._drop_chunks()

    def _make_noise(self) -> pygame.Surface:
        """Smooth patches of two sizes, in the alpha of a black surface, 0 to 255."""
        noise = pygame.Surface(self.size, pygame.SRCALPHA)
        noise.fill((0, 0, 0, 0))
        for tiles, share in zip(NOISE_TILES, NOISE_SHARES):
            layer = snow_flecks.smooth_noise(self.size, tiles * PX_PER_TILE, self.rng, round(255 * share))
            noise.blit(layer, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
        # Smoothed noise bunches round its middle: stretched twice as far from it, so the patches show
        noise.fill((0, 0, 0, 64), special_flags=pygame.BLEND_RGBA_SUB)
        noise.blit(noise.copy(), (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
        return noise

    def _scaled_noise(self, share: float, offset: int) -> pygame.Surface:
        out = self._noise.copy()
        out.fill((255, 255, 255, round(255 * share)), special_flags=pygame.BLEND_RGBA_MULT)
        if offset:
            out.fill((0, 0, 0, offset), special_flags=pygame.BLEND_RGBA_ADD)
        return out

    def _drop_chunks(self) -> None:
        self._chunks.clear()
        self._cached_px = 0

    # Making a chunk

    def _region(self, smooth: pygame.Surface, cx: int, cy: int) -> pygame.Surface:
        """*smooth*'s part under chunk (cx, cy), at the flecks' resolution; off the map nothing whitens."""
        side = CHUNK_TILES * PX_PER_TILE + 2 * _MARGIN
        region = pygame.Surface((side, side), pygame.SRCALPHA)
        region.fill((0, 0, 0, 255))
        src = pygame.Rect(cx * CHUNK_TILES * PX_PER_TILE - _MARGIN, cy * CHUNK_TILES * PX_PER_TILE - _MARGIN, side, side)
        part = src.clip(smooth.get_rect())
        region.blit(smooth, (part.x - src.x, part.y - src.y), part, special_flags=pygame.BLEND_RGBA_MIN)
        factor = DUST_PX_PER_TILE // PX_PER_TILE
        up = pygame.transform.smoothscale(region, (side * factor, side * factor))
        dust = CHUNK_TILES * DUST_PX_PER_TILE
        return up.subsurface(pygame.Rect(_MARGIN * factor, _MARGIN * factor, dust, dust)).copy()

    def _build(self, cx: int, cy: int, level: int, tile_px: int) -> Optional[pygame.Surface]:
        """Chunk (cx, cy) at depth *level* (0-255) for tiles of *tile_px*, or None if nothing in it is white."""
        dust = CHUNK_TILES * DUST_PX_PER_TILE
        threshold = snow_flecks.tiled(self._flecks, (dust, dust), (cx * dust, cy * dust))
        threshold.blit(self._region(self._dust, cx, cy), (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
        threshold.blit(self._region(self._blanket, cx, cy), (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        white = snow_flecks.whiteness(threshold, level)
        if not pygame.mask.from_surface(white, 1).count():
            return None
        white.fill((*SNOW_COLOUR, 0), special_flags=pygame.BLEND_RGBA_ADD)
        white.fill((255, 255, 255, round(255 * SNOW_OPACITY)), special_flags=pygame.BLEND_RGBA_MULT)
        side = CHUNK_TILES * tile_px
        return pygame.transform.scale(white, (side, side))

    def _store(self, key, step: int, surface: Optional[pygame.Surface]) -> None:
        old = self._chunks.pop(key, None)
        if old is not None and old[1] is not None:
            self._cached_px -= old[1].get_width() * old[1].get_height()
        self._chunks[key] = [step, surface]
        if surface is not None:
            self._cached_px += surface.get_width() * surface.get_height()
        while self._cached_px > CACHE_PIXELS and len(self._chunks) > 1:
            _key, (_step, dropped) = self._chunks.popitem(last=False)
            if dropped is not None:
                self._cached_px -= dropped.get_width() * dropped.get_height()

    # Drawing

    def draw(self, screen: pygame.Surface, camera, offset_x: int, offset_y: int, cover: float) -> None:
        """Lay the snow on the ground in view by how deep it lies (*cover*, Weather.snow_cover)."""
        step = round(max(0.0, min(1.0, cover)) * LEVEL_STEPS)
        if self._dust is None or step <= 0:
            if self._chunks:
                self._drop_chunks()
            return
        level = round(step * 255 / LEVEL_STEPS)
        tile_px = round(TILE_SIZE * camera.zoom)
        chunk_px = CHUNK_TILES * tile_px
        scale = tile_px / float(TILE_SIZE)
        cam_x, cam_y = round(camera.x * scale), round(camera.y * scale)
        last_x = (self.tiles[0] - 1) // CHUNK_TILES
        last_y = (self.tiles[1] - 1) // CHUNK_TILES
        x0, y0 = max(0, cam_x // chunk_px), max(0, cam_y // chunk_px)
        x1 = min(last_x, (cam_x + camera.screen_width) // chunk_px)
        y1 = min(last_y, (cam_y + camera.screen_height) // chunk_px)

        # Make what is missing or out of date: in view first, then the ring around it
        in_view = [(cx, cy) for cy in range(y0, y1 + 1) for cx in range(x0, x1 + 1)]
        ring = [(cx, cy) for cy in range(max(0, y0 - 1), min(last_y, y1 + 1) + 1)
                for cx in range(max(0, x0 - 1), min(last_x, x1 + 1) + 1)
                if not (x0 <= cx <= x1 and y0 <= cy <= y1)]
        chunks = self._chunks
        todo = [c for c in in_view if (*c, tile_px) not in chunks]
        missing = bool(todo)
        todo += [c for c in in_view if (*c, tile_px) in chunks and chunks[(*c, tile_px)][0] != step]
        todo += [c for c in ring if chunks.get((*c, tile_px), (None,))[0] != step]
        if todo:
            budget = MISSING_BUDGET_S if missing else BUILD_BUDGET_S
            start = time.perf_counter()
            for cx, cy in todo:
                self._store((cx, cy, tile_px), step, self._build(cx, cy, level, tile_px))
                if time.perf_counter() - start > budget:
                    break

        batch = []
        for cx, cy in in_view:
            entry = chunks.get((cx, cy, tile_px))
            if entry is None:
                continue
            chunks.move_to_end((cx, cy, tile_px))
            if entry[1] is not None:
                batch.append((entry[1], (cx * chunk_px - cam_x + offset_x, cy * chunk_px - cam_y + offset_y)))
        if batch:
            screen.blits(batch, doreturn=False)
