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
  heard. That is worked out once per tile (Cover), not every frame.
  Birds sing from dawn to dusk (BIRDS_BY_HOUR);
- crickets in nature by night: nature is wherever the town is not, the
  buildings (not fences or decorations) within TOWN_RADIUS_TILES counting,
  the nearer the more, also worked out once per tile; TOWN_FULL_COVER of
  them silence the crickets. They sing from dusk to dawn (CRICKETS_BY_HOUR),
  up to CRICKETS_VOLUME out in the fields and woods;
- the river and the sea, by the distance to the nearest water of each
  (RIVER_VOLUME_BY_DISTANCE, SEA_VOLUME_BY_DISTANCE). The map's water is one
  body, so which is which is read off its shape (split_water): open water
  is the sea, with the bay; narrow water the rivers and streams. The
  distances are worked out once per tile too (Distance);
- the market's crowd, by the distance to the nearest open booth
  (MARKET_VOLUME_BY_DISTANCE): a booth is open while one of its traders
  minds it, so the crowd is there by day, thins as the booths pack up, and
  is gone once the last one is shut.

Every loop glides towards the volume it is given (LOOP_GLIDE_PER_S) rather
than jumping, as when the nearest booth shuts, and it starts from silence.
"""

import datetime
import heapq
from typing import Iterable, Optional, Sequence, Set, Tuple

import pygame

from ..config.constants import (
    BIRDS_BY_HOUR, CRICKETS_BY_HOUR, CRICKETS_VOLUME, FOREST_BIRDS_VOLUME, FOREST_FULL_COVER,
    FOREST_RADIUS_TILES, MARKET_VOLUME_BY_DISTANCE, MILL_VOLUME_BY_DISTANCE, RIVER_VOLUME_BY_DISTANCE,
    SEA_VOLUME_BY_DISTANCE, TOWN_FULL_COVER, TOWN_RADIUS_TILES,
)
from .institutions.market import Market

LOOP_GLIDE_PER_S = 0.5         # how fast a loop's volume may change, per second (1.0 is all of it)
AMBIENCE_FIRST_CHANNEL = 1      # channel 0 is the player's footsteps'
#: Objects on the houses' layer that do not make a place a town: fences, decorations, bare collision boxes, stumps
NOT_TOWN_BUILDINGS = ('Fence', 'Deco', 'Collision Box', 'Stomp')
#: Water is open - sea - where at least SEA_OPENNESS of the square SEA_REACH tiles around a tile is water;
#: narrower water is river. Water within SEA_REACH of open water is sea too: its shores and the harbour.
SEA_REACH = 6
SEA_OPENNESS = 0.75
RIVER_MIN_TILES = 100           # narrow water in pieces smaller than this is the sea's too
OPEN_SEA_TILES = 24             # the sea with waves: this far from the map's edge through the water, not the bay


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


class TileField:
    """A number per tile of the map, read at any world point blended from the tile centres around it."""

    def __init__(self, tile_size: int, tiles_wide: int, tiles_high: int, fill: float) -> None:
        self.tile_size = tile_size
        self.wide = tiles_wide
        self.high = tiles_high
        self.cells = [fill] * (tiles_wide * tiles_high)

    def at(self, x: float, y: float) -> float:
        """The value at a world point, blended from the tile centres around it."""
        fx = min(max(x / self.tile_size - 0.5, 0.0), self.wide - 1.0)
        fy = min(max(y / self.tile_size - 0.5, 0.0), self.high - 1.0)
        x0, y0 = int(fx), int(fy)
        x1, y1 = min(x0 + 1, self.wide - 1), min(y0 + 1, self.high - 1)
        tx, ty = fx - x0, fy - y0
        c = self.cells
        top = c[y0 * self.wide + x0] * (1 - tx) + c[y0 * self.wide + x1] * tx
        bottom = c[y1 * self.wide + x0] * (1 - tx) + c[y1 * self.wide + x1] * tx
        return top * (1 - ty) + bottom * ty


class Cover(TileField):
    """How much of something (trees, buildings) is around every spot of the map, worked out once.

    Each tile's centre gets the sum over the points within *radius_tiles*,
    each counting 1 - distance / radius (so 1 on the spot, nothing at the
    edge). A point only touches the tiles within its radius, so building it
    takes a fraction of a second; asking is a lookup of the four tiles around
    the point, blended, so a loop swells smoothly rather than tile by tile.
    """

    def __init__(self, points: Iterable[Tuple[float, float]], radius_tiles: float,
                 tile_size: int, tiles_wide: int, tiles_high: int) -> None:
        super().__init__(tile_size, tiles_wide, tiles_high, 0.0)
        reach = int(radius_tiles) + 1
        for x, y in points:
            sx, sy = x / tile_size, y / tile_size   # in tiles
            for ty in range(max(0, int(sy) - reach), min(tiles_high, int(sy) + reach + 1)):
                for tx in range(max(0, int(sx) - reach), min(tiles_wide, int(sx) + reach + 1)):
                    dist = ((tx + 0.5 - sx) ** 2 + (ty + 0.5 - sy) ** 2) ** 0.5
                    if dist < radius_tiles:
                        self.cells[ty * tiles_wide + tx] += 1.0 - dist / radius_tiles


class Distance(TileField):
    """How far, in tiles, every tile is from the nearest of some tiles, worked out once; *beyond* where farther.

    A search outwards from those tiles (8 neighbours, diagonals costing their
    length) that stops at *beyond*, so only the land near them is visited.
    """

    def __init__(self, tiles: Set[Tuple[int, int]], beyond: float,
                 tile_size: int, tiles_wide: int, tiles_high: int) -> None:
        super().__init__(tile_size, tiles_wide, tiles_high, beyond)
        cells = self.cells
        queue = []
        for tx, ty in tiles:
            if 0 <= tx < tiles_wide and 0 <= ty < tiles_high:
                cells[ty * tiles_wide + tx] = 0.0
                queue.append((0.0, tx, ty))
        heapq.heapify(queue)
        steps = [(dx, dy, (dx * dx + dy * dy) ** 0.5) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy]
        while queue:
            dist, tx, ty = heapq.heappop(queue)
            if dist > cells[ty * tiles_wide + tx]:
                continue
            for dx, dy, cost in steps:
                nx, ny = tx + dx, ty + dy
                if 0 <= nx < tiles_wide and 0 <= ny < tiles_high:
                    near = dist + cost
                    if near < cells[ny * tiles_wide + nx] and near < beyond:
                        cells[ny * tiles_wide + nx] = near
                        heapq.heappush(queue, (near, nx, ny))


def split_water(water: Set[Tuple[int, int]], tiles_wide: int,
                tiles_high: int) -> Tuple[Set[Tuple[int, int]], Set[Tuple[int, int]]]:
    """(sea, river) water tiles: see SEA_REACH, SEA_OPENNESS and RIVER_MIN_TILES."""
    def window_counts(marked: Set[Tuple[int, int]]):
        """How many marked tiles are in the square of SEA_REACH around a tile, by a summed-area table."""
        table = [[0] * (tiles_wide + 1) for _ in range(tiles_high + 1)]
        for y in range(tiles_high):
            row = 0
            above, here = table[y], table[y + 1]
            for x in range(tiles_wide):
                row += (x, y) in marked
                here[x + 1] = above[x + 1] + row

        def count(x: int, y: int) -> int:
            x0, y0 = max(0, x - SEA_REACH), max(0, y - SEA_REACH)
            x1, y1 = min(tiles_wide, x + SEA_REACH + 1), min(tiles_high, y + SEA_REACH + 1)
            return table[y1][x1] - table[y0][x1] - table[y1][x0] + table[y0][x0]
        return count

    water_near = window_counts(water)
    full = (2 * SEA_REACH + 1) ** 2
    open_water = {tile for tile in water if water_near(*tile) >= SEA_OPENNESS * full}
    open_near = window_counts(open_water)
    sea = {tile for tile in water if open_near(*tile) > 0}
    # A river is long: what is left over in small pieces (the water between the piers) is the sea's
    left = water - sea
    while left:
        stack, piece = [left.pop()], []
        while stack:
            x, y = stack.pop()
            piece.append((x, y))
            for near in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if near in left:
                    left.remove(near)
                    stack.append(near)
        if len(piece) < RIVER_MIN_TILES:
            sea.update(piece)
    return sea, water - sea


def open_sea(sea: Set[Tuple[int, int]], tiles_wide: int, tiles_high: int) -> Set[Tuple[int, int]]:
    """The sea's tiles out at sea: within OPEN_SEA_TILES of the map's edge, going through the sea.

    The bay is open water too, but reaches far inland from the edge; it and
    the harbour in it are calm, without the waves.
    """
    edge = [(x, y) for x, y in sea if x in (0, tiles_wide - 1) or y in (0, tiles_high - 1)]
    reached = set(edge)
    ring = edge
    for _ in range(OPEN_SEA_TILES):
        ring = [near for x, y in ring for near in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1))
                if near in sea and near not in reached]
        reached.update(ring)
    return reached


class AmbientLoop:
    """One looping sound on a channel of its own, gliding towards the volume it is given.

    The volume is the sound's own, not the channel's: play() resets a
    channel to full volume, and a mixer fade-in (fade_ms) fades towards that
    full volume whatever is set meanwhile, so either would blare for a moment
    at the start. The sound's volume is set before it plays; from there it
    glides, by LOOP_GLIDE_PER_S, from silence to the volume asked for.
    """

    def __init__(self, sound: Optional[pygame.mixer.Sound], channel_id: int) -> None:
        self.sound = sound
        self.channel = pygame.mixer.Channel(channel_id)
        self.level = 0.0          # the volume it plays at now
        self.last_tick = 0        # pygame ticks of the last update

    def update(self, volume: float, audible: bool) -> None:
        """Play on, gliding to *volume*; paused while not *audible*. Starts again if something stopped every sound."""
        if not self.sound:
            return
        now = pygame.time.get_ticks()
        elapsed = (now - self.last_tick) / 1000
        self.last_tick = now
        if not audible:
            self.channel.pause()
            return
        if self.channel.get_sound() is not self.sound:
            self.level = 0.0
            self.sound.set_volume(0.0)
            self.channel.play(self.sound, loops=-1)
            self.channel.set_volume(1.0)
        step = LOOP_GLIDE_PER_S * min(elapsed, 0.25)   # a long gap (loading, paused) is no excuse to jump
        self.level = min(volume, self.level + step) if volume > self.level else max(volume, self.level - step)
        self.sound.set_volume(self.level)
        self.channel.unpause()

    def stop(self) -> None:
        self.channel.stop()


class Ambience:
    """The map's ambient loops; channels from *first_channel* on, which Game.init_pygame() reserves.

    Made while the game loads, which is when the trees' and the buildings'
    cover and the distances to the water are worked out.
    """

    CHANNELS = 6

    def __init__(self, sounds: dict, first_channel: int, tmx_map) -> None:
        self.mill = AmbientLoop(sounds.get('amb_mill_interior_loop'), first_channel)
        self.forest_birds = AmbientLoop(sounds.get('amb_birds_day_loop'), first_channel + 1)
        self.crickets = AmbientLoop(sounds.get('amb_crickets_night_loop'), first_channel + 2)
        self.river = AmbientLoop(sounds.get('amb_river_loop'), first_channel + 3)
        self.sea = AmbientLoop(sounds.get('amb_sea_waves_loop'), first_channel + 4)
        self.market = AmbientLoop(sounds.get('amb_market_dense_loop'), first_channel + 5)
        self.booths = [house for house in tmx_map.houses if isinstance(house, Market)]
        ts = tmx_map.tile_size
        size = (ts, tmx_map.tmx_data.width, tmx_map.tmx_data.height)
        stems = [(tree.x + tree.stem_position * ts, tree.y) for tree in tmx_map.trees]
        self.trees = Cover(stems, FOREST_RADIUS_TILES, *size)
        buildings = [house.collision_rect.center for house in tmx_map.houses
                     if not (house.name or '').startswith(NOT_TOWN_BUILDINGS)]
        self.town = Cover(buildings, TOWN_RADIUS_TILES, *size)
        sea, river = split_water(tmx_map.water_tiles, tmx_map.tmx_data.width, tmx_map.tmx_data.height)
        self.to_river = Distance(river, RIVER_VOLUME_BY_DISTANCE[-1][0], *size)
        waves = open_sea(sea, tmx_map.tmx_data.width, tmx_map.tmx_data.height)
        self.to_sea = Distance(waves, SEA_VOLUME_BY_DISTANCE[-1][0], *size)

    def update(self, tmx_map, player, date: datetime.datetime, audible: bool) -> None:
        """Set every loop's volume for where the player stands and the time of day."""
        px = player.x + player.width / 2
        py = player.y + player.height / 2

        mill = 0.0
        if tmx_map.mills:
            tiles = min(distance_to_rect(px, py, m.collision_rect) for m in tmx_map.mills) / tmx_map.tile_size
            mill = by_steps(MILL_VOLUME_BY_DISTANCE, tiles)
        self.mill.update(mill, audible)

        hour = date.hour + date.minute / 60.0
        birds = 0.0
        daylight = by_steps(BIRDS_BY_HOUR, hour)
        if daylight > 0:
            wooded = min(1.0, self.trees.at(px, py) / FOREST_FULL_COVER)
            birds = FOREST_BIRDS_VOLUME * wooded * daylight
        self.forest_birds.update(birds, audible)

        crickets = 0.0
        night = by_steps(CRICKETS_BY_HOUR, hour)
        if night > 0:
            nature = 1.0 - min(1.0, self.town.at(px, py) / TOWN_FULL_COVER)
            crickets = CRICKETS_VOLUME * nature * night
        self.crickets.update(crickets, audible)

        self.river.update(by_steps(RIVER_VOLUME_BY_DISTANCE, self.to_river.at(px, py)), audible)
        self.sea.update(by_steps(SEA_VOLUME_BY_DISTANCE, self.to_sea.at(px, py)), audible)

        # Only booths in earshot are asked whether they are open
        earshot = MARKET_VOLUME_BY_DISTANCE[-1][0] * tmx_map.tile_size
        booths = ((distance_to_rect(px, py, booth.collision_rect), booth) for booth in self.booths)
        open_near = [d for d, booth in booths if d < earshot and not booth.is_closed_at(date)]
        market = by_steps(MARKET_VOLUME_BY_DISTANCE, min(open_near) / tmx_map.tile_size) if open_near else 0.0
        self.market.update(market, audible)

    def stop(self) -> None:
        for loop in (self.mill, self.forest_birds, self.crickets, self.river, self.sea, self.market):
            loop.stop()
