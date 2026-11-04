"""Snow lying on the ground, in drifts and patches, thinner where it is trodden.

Drawn over the ground layers (after the wet ground, under the bridges, the
puddles and everyone else) as a blend towards SNOW_COLOUR: a multiply by
what is left of the ground, then an add of the snow. How much each spot
takes follows Weather.snow_cover, unevenly: every spot has a depth of cover
it whitens at (smooth noise of two sizes, NOISE_TILES), so a first snowfall
lies in patches, which join as it deepens, and a thaw leaves them again. And
by the kind of ground (ROOM, the Town Plan's reading of the map, as for the
wet ground): grass and sand take it all, the forest floor under the trees
less, the roads and the paving, trodden all day, less still; water none.

Cheap, as WetGround is (models/wet_ground.py): the map is kept at PX_PER_TILE
pixels a tile, the part in view worked out on that small scale and smoothed
up in one piece, and kept until the camera has moved a pixel of the small
map or the cover has changed; drawing is two blits.
"""

import random
from typing import Dict, Optional, Tuple

import pygame

from ..config.constants import TILE_SIZE

PX_PER_TILE = 4             # resolution of the snow map
NOISE_TILES = (5, 1.2)      # the size of the drifts, large and small, in tiles
NOISE_SPREAD = 0.55         # the spots whiten from 0 to this much cover
FULL_OVER = 0.12            # cover over a spot's threshold it takes to look fully white (crisp patches)
SNOW_COLOUR = (238, 242, 250)
SNOW_OPACITY = 0.93         # even deep snow lets a trace of the ground through, so it does not look flat
ROOM_SOFTEN = 4             # the kinds of ground shade into each other over about this many pixels (a tile)
# How much of the snow each kind of ground takes (255 all of it; anything else is grass)
ROOM = {
    "grass": 255,
    "sand": 245,
    "wood": 215,
    "road": 195,
    "plaza": 185,
    "water": 0,
}


class SnowCover:
    """The map's snowy look, made once from its kinds of ground and redrawn as the snow deepens or thaws."""

    def __init__(self, tiles_wide: int, tiles_high: int, rng: Optional[random.Random] = None) -> None:
        self.size = (tiles_wide * PX_PER_TILE, tiles_high * PX_PER_TILE)
        self.rng = rng or random.Random()
        self._room: Optional[pygame.Surface] = None
        self._threshold = self._make_noise()
        self._view_key = None
        self._view_surfaces: Optional[Tuple[pygame.Surface, pygame.Surface]] = None

    def set_ground(self, masks: Dict[str, pygame.Mask]) -> None:
        """Take over the kinds of ground: masks of "water", "sand", "road", "plaza" and "wood", self.size large."""
        room = pygame.Surface(self.size)
        room.fill((ROOM["grass"],) * 3)
        for kind in ("wood", "sand", "road", "plaza", "water"):
            if kind in masks:
                room.blit(masks[kind].to_surface(setcolor=(*(ROOM[kind],) * 3, 255), unsetcolor=(0, 0, 0, 0)), (0, 0))
        # Softened, so a road or the paving shades into the fields rather than ending at a tile's edge
        small = pygame.transform.smoothscale(room, (max(1, self.size[0] // ROOM_SOFTEN), max(1, self.size[1] // ROOM_SOFTEN)))
        self._room = pygame.transform.smoothscale(small, self.size)
        self._view_key = None

    def _make_noise(self) -> pygame.Surface:
        """Smooth drifts of two sizes, scaled to 0..NOISE_SPREAD of full."""
        noise = pygame.Surface(self.size)
        noise.fill((0, 0, 0))
        for tiles, share in zip(NOISE_TILES, (0.65, 0.35)):
            cells = (max(2, round(self.size[0] / PX_PER_TILE / tiles)), max(2, round(self.size[1] / PX_PER_TILE / tiles)))
            small = pygame.Surface(cells)
            for y in range(cells[1]):
                for x in range(cells[0]):
                    v = round(255 * share * self.rng.random())
                    small.set_at((x, y), (v, v, v))
            noise.blit(pygame.transform.smoothscale(small, self.size), (0, 0), special_flags=pygame.BLEND_RGB_ADD)
        spread = round(255 * NOISE_SPREAD)
        noise.fill((spread, spread, spread), special_flags=pygame.BLEND_RGB_MULT)
        return noise

    def _view(self, src: pygame.Rect, level: int, per_px: int) -> Tuple[pygame.Surface, pygame.Surface]:
        """The multiply and the add for the snow map's pixels *src* at *level* (0-255), *per_px* screen pixels each."""
        # How white each pixel is: (level - threshold), steepened to full over FULL_OVER, times the ground's room
        amount = pygame.Surface(src.size)
        amount.fill((level, level, level))
        amount.blit(self._threshold, (0, 0), src, special_flags=pygame.BLEND_RGB_SUB)
        for _ in range(2):   # x4: FULL_OVER past its threshold a spot is fully white
            amount.blit(amount.copy(), (0, 0), special_flags=pygame.BLEND_RGB_ADD)
        amount.blit(self._room, (0, 0), src, special_flags=pygame.BLEND_RGB_MULT)
        opacity = round(255 * SNOW_OPACITY)
        amount.fill((opacity, opacity, opacity), special_flags=pygame.BLEND_RGB_MULT)
        # Ground * (1 - amount) + snow * amount
        keep = pygame.Surface(src.size)
        keep.fill((255, 255, 255))
        keep.blit(amount, (0, 0), special_flags=pygame.BLEND_RGB_SUB)
        add = amount.copy()
        add.fill(SNOW_COLOUR, special_flags=pygame.BLEND_RGB_MULT)
        size = (src.width * per_px, src.height * per_px)
        return pygame.transform.smoothscale(keep, size), pygame.transform.smoothscale(add, size)

    def draw(self, screen: pygame.Surface, camera, offset_x: int, offset_y: int, cover: float) -> None:
        """Whiten the ground in view by how deep the snow lies (*cover*, Weather.snow_cover)."""
        if self._room is None or cover <= 0:
            return
        tile_px = round(TILE_SIZE * camera.zoom)
        per_px = max(1, tile_px // PX_PER_TILE)   # tiles are 16 to 56 px: always a whole number
        scale = tile_px / float(TILE_SIZE)
        cam_x, cam_y = round(camera.x * scale), round(camera.y * scale)
        # The snow map's pixels in view, and one more all round so the smoothing has no edge in sight
        src = pygame.Rect(cam_x // per_px - 1, cam_y // per_px - 1,
                          camera.screen_width // per_px + 3, camera.screen_height // per_px + 3)
        src = src.clip(pygame.Rect((0, 0), self.size))
        if src.width <= 0 or src.height <= 0:
            return
        level = round(cover * 255)
        if level <= 0:
            return
        key = (src.topleft, src.size, level, per_px)
        if key != self._view_key:
            self._view_key = key
            self._view_surfaces = self._view(src, level, per_px)
        keep, add = self._view_surfaces
        pos = (src.x * per_px - cam_x + offset_x, src.y * per_px - cam_y + offset_y)
        screen.blit(keep, pos, special_flags=pygame.BLEND_MULT)
        screen.blit(add, pos, special_flags=pygame.BLEND_RGB_ADD)
