"""Ambient loops on the map: sounds that run on and on, only louder or softer.

Each runs on a mixer channel of its own, reserved in Game.init_pygame() so
that one-off sounds never take it. How loud each is comes from where the
player stands (and when):

- the mill's gears, by the distance from the mill's walls
  (MILL_VOLUME_BY_DISTANCE);
- birdsong in the woods by day: there is no "forest" object, the trees
  themselves say where the woods are, so a wood grown with the Forest
  Builder sings without more ado. Every tree's stem within
  FOREST_RADIUS_TILES counts, the nearer the more, and FOREST_FULL_COVER of
  them make a wood (FOREST_BIRDS_VOLUME); a lone tree in a field is hardly
  heard. That is worked out once per tile (TreeCover), not every frame.
  Birds sing from dawn to dusk (BIRDS_BY_HOUR).
"""

import datetime
from typing import Iterable, Optional, Sequence, Tuple

import pygame

from ..config.constants import (
    BIRDS_BY_HOUR, FOREST_BIRDS_VOLUME, FOREST_FULL_COVER, FOREST_RADIUS_TILES, MILL_VOLUME_BY_DISTANCE,
)

LOOP_FADE_IN_MS = 1500
AMBIENCE_FIRST_CHANNEL = 1      # channel 0 is the player's footsteps'


def by_steps(steps: Sequence[Tuple[float, float]], x: float) -> float:
    """The value at *x* in a table of (x, value) steps, blended linearly between them, held beyond the ends."""
    if x <= steps[0][0]:
        return steps[0][1]
    for (x0, v0), (x1, v1) in zip(steps, steps[1:]):
        if x < x1:
            return v0 + (v1 - v0) * (x - x0) / (x1 - x0)
    return steps[-1][1]


def distance_to_rect(x: float, y: float, rect: pygame.Rect) -> float:
    """How far the point is from the rect's edge; 0 inside it."""
    dx = max(rect.left - x, 0, x - rect.right)
    dy = max(rect.top - y, 0, y - rect.bottom)
    return (dx * dx + dy * dy) ** 0.5


class TreeCover:
    """How wooded every spot of the map is, worked out once from the trees.

    Each tile's centre gets the sum over the stems within FOREST_RADIUS_TILES,
    each counting 1 - distance / radius (so 1 on the spot, nothing at the
    edge). A tree only touches the tiles within its radius, so building it
    takes a fraction of a second; asking is a lookup of the four tiles around
    the point, blended, so the birds swell smoothly rather than tile by tile.
    """

    def __init__(self, trees: Iterable, tile_size: int, tiles_wide: int, tiles_high: int) -> None:
        self.tile_size = tile_size
        self.wide = tiles_wide
        self.high = tiles_high
        self.cells = [0.0] * (tiles_wide * tiles_high)
        reach = int(FOREST_RADIUS_TILES) + 1
        for tree in trees:
            sx = (tree.x + tree.stem_position * tile_size) / tile_size   # stem, in tiles
            sy = tree.y / tile_size
            for ty in range(max(0, int(sy) - reach), min(tiles_high, int(sy) + reach + 1)):
                for tx in range(max(0, int(sx) - reach), min(tiles_wide, int(sx) + reach + 1)):
                    dist = ((tx + 0.5 - sx) ** 2 + (ty + 0.5 - sy) ** 2) ** 0.5
                    if dist < FOREST_RADIUS_TILES:
                        self.cells[ty * tiles_wide + tx] += 1.0 - dist / FOREST_RADIUS_TILES

    def at(self, x: float, y: float) -> float:
        """The cover at a world point, blended from the tile centres around it."""
        fx = min(max(x / self.tile_size - 0.5, 0.0), self.wide - 1.0)
        fy = min(max(y / self.tile_size - 0.5, 0.0), self.high - 1.0)
        x0, y0 = int(fx), int(fy)
        x1, y1 = min(x0 + 1, self.wide - 1), min(y0 + 1, self.high - 1)
        tx, ty = fx - x0, fy - y0
        c = self.cells
        top = c[y0 * self.wide + x0] * (1 - tx) + c[y0 * self.wide + x1] * tx
        bottom = c[y1 * self.wide + x0] * (1 - tx) + c[y1 * self.wide + x1] * tx
        return top * (1 - ty) + bottom * ty


class AmbientLoop:
    """One looping sound on a channel of its own, kept going at the volume it is given.

    The volume is the sound's own, not the channel's: play() resets a
    channel to full volume, and a mixer fade-in (fade_ms) fades towards that
    full volume whatever is set meanwhile, so either would blare for a moment
    at the start. The sound's volume is set before it plays and stays put; the
    fade-in is done here, over LOOP_FADE_IN_MS, towards the volume asked for.
    """

    def __init__(self, sound: Optional[pygame.mixer.Sound], channel_id: int) -> None:
        self.sound = sound
        self.channel = pygame.mixer.Channel(channel_id)
        self.started = 0          # pygame ticks when it last began playing

    def update(self, volume: float, audible: bool) -> None:
        """Play on at *volume*; paused while not *audible*. Starts again if something stopped every sound."""
        if not self.sound:
            return
        if not audible:
            self.channel.pause()
            return
        now = pygame.time.get_ticks()
        if self.channel.get_sound() is not self.sound:
            self.sound.set_volume(0.0)
            self.channel.play(self.sound, loops=-1)
            self.channel.set_volume(1.0)
            self.started = now
        fade_in = min(1.0, (now - self.started) / LOOP_FADE_IN_MS)
        self.sound.set_volume(volume * fade_in)
        self.channel.unpause()

    def stop(self) -> None:
        self.channel.stop()


class Ambience:
    """The map's ambient loops; channels from *first_channel* on, which Game.init_pygame() reserves.

    Made while the game loads, which is when the trees' cover is worked out.
    """

    CHANNELS = 2

    def __init__(self, sounds: dict, first_channel: int, tmx_map) -> None:
        self.mill = AmbientLoop(sounds.get('amb_mill_interior_loop'), first_channel)
        self.forest_birds = AmbientLoop(sounds.get('amb_birds_day_loop'), first_channel + 1)
        data = tmx_map.tmx_data
        self.cover = TreeCover(tmx_map.trees, tmx_map.tile_size, data.width, data.height)

    def update(self, tmx_map, player, date: datetime.datetime, audible: bool) -> None:
        """Set every loop's volume for where the player stands and the time of day."""
        px = player.x + player.width / 2
        py = player.y + player.height / 2
        tile_size = tmx_map.tile_size

        mill = 0.0
        if tmx_map.mills:
            tiles = min(distance_to_rect(px, py, m.collision_rect) for m in tmx_map.mills) / tile_size
            mill = by_steps(MILL_VOLUME_BY_DISTANCE, tiles)
        self.mill.update(mill, audible)

        hour = date.hour + date.minute / 60.0
        daylight = by_steps(BIRDS_BY_HOUR, hour)
        birds = 0.0
        if daylight > 0:
            wooded = min(1.0, self.cover.at(px, py) / FOREST_FULL_COVER)
            birds = FOREST_BIRDS_VOLUME * wooded * daylight
        self.forest_birds.update(birds, audible)

    def stop(self) -> None:
        self.mill.stop()
        self.forest_birds.stop()
