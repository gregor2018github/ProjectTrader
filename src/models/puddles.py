"""Puddles on open ground, growing while it rains and drying away after.

Where: random spots, picked anew for every wet spell (once the ground has
dried out completely, the next rain finds other spots). A spot is only taken
if the puddle keeps PUDDLE_CLEARANCE tiles clear of every house, fence,
stall and tree: of its collision box and of its drawn sprite (its painted
pixels), so a puddle never touches a wall nor lies under a roof or a tree
crown. Those rectangles are filed by tile once, at load (_Blockers).
It also keeps off water, bridges and fields, and away from other puddles
(PUDDLE_SPACING). Puddles gather where the ground is trodden: about one per
PUDDLE_PATH_TILES_EACH tiles of road and paving (the tiles the Town Plan
reads as such, handed over with set_trodden()), whose spots are tried on
those tiles, and only PUDDLE_OFF_PATH_SHARE of that on grass and sand, tried
anywhere. Placing them is spread over
a few ticks (PLACE_ATTEMPTS_PER_TICK), so the rain setting in never stalls a
frame; they only start growing then anyway.

How big: each puddle has a threshold of Weather.wetness it starts to show
at, and grows to its full size over PUDDLE_GROW_SPAN more; drying, it
shrinks back the same way, so the puddles come one by one and go in the
reverse order.

What it looks like: a main ellipse with a few smaller lobes overlapping it
(so no two are the same shape, but all stay rounded and flat, as seen from
above). The ground under it is multiplied darker and cooler, a damp rim
and the water, so its own texture shows through as it would under shallow
water; over that go a faint reflection of the sky and a thin glint. Each is
drawn once per zoom and size step (GROWTH_STEPS) and kept; it lies flat on
the ground, under every walker, and the day/night lighting darkens it with
the rest.
"""

import random
from typing import Dict, Iterator, List, Optional, Set, Tuple

import pygame

from ..config.constants import PUDDLE_OFF_PATH_SHARE, PUDDLE_PATH_TILES_EACH, PUDDLE_SIZE_TILES, TILE_SIZE

PUDDLE_CLEARANCE = 0.3     # tiles a puddle keeps from every building and tree
PUDDLE_SPACING = 2.5       # tiles at least between two puddles' centres
PUDDLE_GROW_SPAN = 0.25    # wetness over a puddle's threshold it takes to reach its full size
THRESHOLDS = (0.03, 0.7)   # the wetness the puddles start to show at, the first and the last
GROWTH_STEPS = 6           # sizes a puddle is drawn in on its way to full
RING_SIZE_MIN = 0.4        # how grown a puddle must be for raindrops on it to make rings
PLACE_ATTEMPTS_PER_TICK = 600   # spots tried per update while placing
TRIES_PER_PUDDLE = 6       # spots tried for each puddle wanted, most near something they must keep clear of
CHUNK_TILES = 8            # puddles are filed in squares of this many tiles, to find those in view

# The ground is multiplied by these, so its own texture shows through: darker and cooler where wet
RIM_MULTIPLY = (196, 190, 184)       # the damp ground round the water
WATER_MULTIPLY = (132, 146, 166)     # the water
SKY_COLOUR = (172, 188, 210, 70)     # the overcast sky mirrored in it, laid over
GLINT_COLOUR = (232, 240, 248, 150)  # a thin glint of light on its far side


class Puddle:
    """One puddle: where it is, its shape (ellipses in tiles, relative to its centre) and when it shows."""

    __slots__ = ('x', 'y', 'lobes', 'width', 'height', 'threshold')

    def __init__(self, x: float, y: float, rng: random.Random) -> None:
        self.x = x
        self.y = y
        width = rng.uniform(*PUDDLE_SIZE_TILES)
        height = width * rng.uniform(0.42, 0.58)
        # (centre x, centre y, width, height): the main body, then lobes swelling out of it
        self.lobes: List[Tuple[float, float, float, float]] = [(0.0, 0.0, width, height)]
        for _ in range(rng.randint(2, 4)):
            scale = rng.uniform(0.4, 0.7)
            self.lobes.append((rng.uniform(-0.32, 0.32) * width, rng.uniform(-0.18, 0.18) * height,
                               width * scale, height * scale * rng.uniform(0.85, 1.15)))
        self.width = max(abs(cx) * 2 + w for cx, _cy, w, _h in self.lobes)
        self.height = max(abs(cy) * 2 + h for _cx, cy, _w, h in self.lobes)
        self.threshold = rng.uniform(*THRESHOLDS)

    def growth(self, wetness: float) -> float:
        """How grown it is (0 not there, 1 full) at a wetness."""
        return min(1.0, max(0.0, (wetness - self.threshold) / PUDDLE_GROW_SPAN))

    def covers(self, x: float, y: float, growth: float) -> bool:
        """Whether a world point is in it, grown so far."""
        for cx, cy, w, h in self.lobes:
            dx = (x - self.x) / TILE_SIZE - cx * growth
            dy = (y - self.y) / TILE_SIZE - cy * growth
            rx, ry = w * growth / 2, h * growth / 2
            if (dx * dx) / (rx * rx) + (dy * dy) / (ry * ry) <= 1.0:
                return True
        return False


class _Blockers:
    """Everything a puddle must keep clear of, filed by the tiles it covers.

    Each is a rectangle and, for a sprite, the mask of its painted pixels: a
    fence round a yard or an L-shaped house has a bounding box over open
    ground, which only the mask tells from the building.
    """

    def __init__(self, tmx_map) -> None:
        self.by_tile: Dict[Tuple[int, int], List[Tuple[pygame.Rect, Optional[pygame.Mask]]]] = {}
        masks: Dict[int, pygame.Mask] = {}   # sprites shared by many trees share one
        for thing in list(tmx_map.houses) + list(tmx_map.trees):
            entries = [(thing.collision_rect, None)]
            image = getattr(thing, 'image', None)
            if image is not None:
                if id(image) not in masks:
                    masks[id(image)] = pygame.mask.from_surface(image)
                entries.append((pygame.Rect(round(thing.x), round(thing.y) - image.get_height(),
                                            image.get_width(), image.get_height()), masks[id(image)]))
            for rect, mask in entries:
                if rect.width <= 0 or rect.height <= 0:
                    continue
                for ty in range(rect.top // TILE_SIZE, (rect.bottom - 1) // TILE_SIZE + 1):
                    for tx in range(rect.left // TILE_SIZE, (rect.right - 1) // TILE_SIZE + 1):
                        self.by_tile.setdefault((tx, ty), []).append((rect, mask))

    def hit(self, area: pygame.Rect) -> bool:
        """Whether *area* touches any of them."""
        area_mask = None
        for ty in range(area.top // TILE_SIZE, (area.bottom - 1) // TILE_SIZE + 1):
            for tx in range(area.left // TILE_SIZE, (area.right - 1) // TILE_SIZE + 1):
                for rect, mask in self.by_tile.get((tx, ty), ()):
                    if not rect.colliderect(area):
                        continue
                    if mask is None:
                        return True
                    if area_mask is None:
                        area_mask = pygame.Mask(area.size, fill=True)
                    if mask.overlap(area_mask, (area.x - rect.x, area.y - rect.y)):
                        return True
        return False


def _render(puddle: Puddle, growth: float, scale: float) -> Tuple[pygame.Surface, pygame.Surface]:
    """The puddle grown to *growth*, at a screen scale, both centred on surfaces of one size:
    what to multiply the ground with (white is no change) and what to lay over it."""
    px = TILE_SIZE * scale * growth   # screen pixels per tile of the puddle's shape
    pixel = max(1, round(scale))      # one pixel of the art at this scale
    w = int(puddle.width * px) + 4 * pixel + 4
    h = int(puddle.height * px) + 4 * pixel + 4
    cx, cy = w / 2, h / 2

    def lobes(target, colour, grow: float = 0.0, shrink: float = 1.0, lift: float = 0.0) -> None:
        for lx, ly, lw, lh in puddle.lobes:
            rw, rh = lw * px * shrink + 2 * grow, lh * px * shrink + 2 * grow
            if rw >= 1 and rh >= 1:
                pygame.draw.ellipse(target, colour, (round(cx + lx * px * shrink - rw / 2),
                                                     round(cy + ly * px * shrink - lift - rh / 2),
                                                     round(rw), round(rh)))

    multiply = pygame.Surface((w, h))
    multiply.fill((255, 255, 255))
    lobes(multiply, RIM_MULTIPLY, grow=pixel)
    lobes(multiply, WATER_MULTIPLY)
    # The sky: the shape smaller and a little further up, all of it in one go so overlaps do not double up
    over = pygame.Surface((w, h), pygame.SRCALPHA)
    lobes(over, SKY_COLOUR, shrink=0.65, lift=0.12 * puddle.height * px)
    if growth > 0.5:
        _lx, ly, mw, mh = puddle.lobes[0]
        length = max(2 * pixel, round(mw * px * 0.22))
        over.fill(GLINT_COLOUR, (round(cx - mw * px * 0.12 - length / 2), round(cy + ly * px - mh * px * 0.26),
                                 length, pixel))
    return multiply, over


class Puddles:
    """The map's puddles for the current wet spell, sized by the ground's wetness."""

    def __init__(self, tmx_map, rng: Optional[random.Random] = None) -> None:
        self.tmx_map = tmx_map
        self.rng = rng or random.Random()
        self.puddles: List[Puddle] = []
        self.wetness = 0.0
        self._dried = True           # the ground has been dry since the puddles were placed
        self._by_tile: Dict[Tuple[int, int], List[Puddle]] = {}
        self._sprites: Dict[tuple, Tuple[pygame.Surface, pygame.Surface]] = {}
        self._by_chunk: Dict[Tuple[int, int], List[Puddle]] = {}
        self._blockers = _Blockers(tmx_map)
        self._trodden: Set[Tuple[int, int]] = set()
        self._placing: Optional[Iterator[None]] = None

    def set_trodden(self, tiles: Set[Tuple[int, int]]) -> None:
        """The tiles of road and paving, where puddles gather."""
        self._trodden = tiles

    def update(self, wetness: float) -> None:
        """Follow the ground's wetness; the first wet moment after a dry one places new puddles."""
        self.wetness = wetness
        if wetness <= 0:
            self._dried = True
        elif self._dried:
            self._dried = False
            self._placing = self._place()
        if self._placing is not None and next(self._placing, StopIteration) is StopIteration:
            self._placing = None

    def place(self) -> None:
        """Scatter new puddles all at once."""
        for _ in self._place():
            pass

    def _place(self) -> Iterator[None]:
        """Scatter new puddles over the open ground (see the module's docstring), yielding now and then."""
        tmx = self.tmx_map
        cols, rows = tmx.width, tmx.height
        water = tmx.water_tiles
        fields = [(f.x, f.y, f.x + f.width, f.y + f.height) for f in tmx.fields]
        bridges = [b.rect for b in tmx.bridges]
        rng = self.rng
        self.puddles = []
        self._by_tile = {}
        self._by_chunk = {}
        self._sprites.clear()
        trodden = self._trodden
        taken: Dict[Tuple[int, int], List[Tuple[float, float]]] = {}
        spacing = PUDDLE_SPACING * TILE_SIZE

        def spots() -> Iterator[Tuple[Puddle, bool]]:
            """Candidate puddles, each with whether it is one on the roads: those first, then the rest."""
            path_tiles = sorted(trodden)
            wanted = len(path_tiles) // PUDDLE_PATH_TILES_EACH
            for _ in range(wanted * TRIES_PER_PUDDLE if path_tiles else 0):
                tx, ty = rng.choice(path_tiles)
                yield Puddle((tx + rng.random()) * TILE_SIZE, (ty + rng.random()) * TILE_SIZE, rng), True
            wanted = int((cols * rows - len(path_tiles)) / PUDDLE_PATH_TILES_EACH * PUDDLE_OFF_PATH_SHARE)
            for _ in range(wanted * TRIES_PER_PUDDLE):
                puddle = Puddle(rng.uniform(0, cols * TILE_SIZE), rng.uniform(0, rows * TILE_SIZE), rng)
                if (int(puddle.x // TILE_SIZE), int(puddle.y // TILE_SIZE)) not in trodden:
                    yield puddle, False

        path_wanted = len(trodden) // PUDDLE_PATH_TILES_EACH
        off_wanted = int((cols * rows - len(trodden)) / PUDDLE_PATH_TILES_EACH * PUDDLE_OFF_PATH_SHARE)
        placed = {True: 0, False: 0}
        for attempt, (puddle, on_path) in enumerate(spots()):
            if attempt % PLACE_ATTEMPTS_PER_TICK == PLACE_ATTEMPTS_PER_TICK - 1:
                yield
            if placed[on_path] >= (path_wanted if on_path else off_wanted):
                continue
            half_w = (puddle.width / 2 + PUDDLE_CLEARANCE) * TILE_SIZE
            half_h = (puddle.height / 2 + PUDDLE_CLEARANCE) * TILE_SIZE
            left, right = puddle.x - half_w, puddle.x + half_w
            top, bottom = puddle.y - half_h, puddle.y + half_h
            x0, x1 = int(left // TILE_SIZE), int(right // TILE_SIZE)
            y0, y1 = int(top // TILE_SIZE), int(bottom // TILE_SIZE)
            if x0 < 0 or y0 < 0 or x1 >= cols or y1 >= rows:
                continue
            if any((x, y) in water for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)):
                continue
            if any(fl < right and left < fr and ft < bottom and top < fb for fl, ft, fr, fb in fields):
                continue
            area = pygame.Rect(round(left), round(top), round(right - left), round(bottom - top))
            if any(b.colliderect(area) for b in bridges) or self._blockers.hit(area):
                continue
            home = (int(puddle.x // spacing), int(puddle.y // spacing))
            near = [p for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                    for p in taken.get((home[0] + dx, home[1] + dy), ())]
            if any((px - puddle.x) ** 2 + (py - puddle.y) ** 2 < spacing ** 2 for px, py in near):
                continue
            placed[on_path] += 1
            taken.setdefault(home, []).append((puddle.x, puddle.y))
            self.puddles.append(puddle)
            chunk = CHUNK_TILES * TILE_SIZE
            self._by_chunk.setdefault((int(puddle.x // chunk), int(puddle.y // chunk)), []).append(puddle)
            for ty in range(int((puddle.y - puddle.height * TILE_SIZE / 2) // TILE_SIZE),
                            int((puddle.y + puddle.height * TILE_SIZE / 2) // TILE_SIZE) + 1):
                for tx in range(int((puddle.x - puddle.width * TILE_SIZE / 2) // TILE_SIZE),
                                int((puddle.x + puddle.width * TILE_SIZE / 2) // TILE_SIZE) + 1):
                    self._by_tile.setdefault((tx, ty), []).append(puddle)

    def puddle_at(self, x: float, y: float) -> bool:
        """Whether a world point is in a puddle grown enough for raindrops to ring on it."""
        for puddle in self._by_tile.get((int(x // TILE_SIZE), int(y // TILE_SIZE)), ()):
            growth = puddle.growth(self.wetness)
            if growth >= RING_SIZE_MIN and puddle.covers(x, y, growth):
                return True
        return False

    def draw(self, screen: pygame.Surface, camera, offset_x: int, offset_y: int) -> None:
        """Lay the puddles in view on the ground."""
        if self.wetness <= 0 or not self.puddles:
            return
        scale = round(TILE_SIZE * camera.zoom) / float(TILE_SIZE)
        cam_x, cam_y = round(camera.x * scale), round(camera.y * scale)
        view_w, view_h = camera.screen_width, camera.screen_height
        reach = PUDDLE_SIZE_TILES[1] * TILE_SIZE * scale
        if len(self._sprites) > 4000:
            self._sprites.clear()
        chunk = CHUNK_TILES * TILE_SIZE * scale
        cx0, cy0 = int((cam_x - reach) // chunk), int((cam_y - reach) // chunk)
        cx1, cy1 = int((cam_x + view_w + reach) // chunk), int((cam_y + view_h + reach) // chunk)
        in_view = [puddle for cy in range(cy0, cy1 + 1) for cx in range(cx0, cx1 + 1)
                   for puddle in self._by_chunk.get((cx, cy), ())]
        batch = []
        for puddle in in_view:
            growth = puddle.growth(self.wetness)
            if growth <= 0:
                continue
            sx, sy = puddle.x * scale - cam_x, puddle.y * scale - cam_y
            if sx < -reach or sy < -reach or sx > view_w + reach or sy > view_h + reach:
                continue
            step = max(1, round(growth * GROWTH_STEPS))
            key = (id(puddle), step, scale)
            sprites = self._sprites.get(key)
            if sprites is None:
                sprites = self._sprites[key] = _render(puddle, step / GROWTH_STEPS, scale)
            multiply, over = sprites
            pos = (round(sx - multiply.get_width() / 2) + offset_x, round(sy - multiply.get_height() / 2) + offset_y)
            batch.append((multiply, pos, None, pygame.BLEND_MULT))
            batch.append((over, pos, None, 0))
        screen.blits(batch, doreturn=False)
