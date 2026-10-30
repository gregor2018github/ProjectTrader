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
above); PUDDLE_WIDE_SHARE of them are drawn longer (PUDDLE_WIDE_TILES), but
none taller than MAX_HEIGHT_TILES. The ground under it is multiplied darker
and cooler, so its own texture shows through as it would under shallow
water; in it is mirrored whatever stands behind it or in it (houses, trees,
people, animals: the render queue's sprites, flipped about their base line,
cooled and see-through), and over that go a faint reflection of the sky, a
thin pale rim and a glint. Each is
drawn once per zoom and size step (GROWTH_STEPS) and kept; it lies flat on
the ground, under every walker, and the day/night lighting darkens it with
the rest.
"""

import math
import random
from typing import Dict, Iterator, List, Optional, Sequence, Set, Tuple

import pygame

from ..config.constants import (
    PUDDLE_OFF_PATH_SHARE, PUDDLE_PATH_TILES_EACH, PUDDLE_SIZE_TILES, PUDDLE_WIDE_SHARE, PUDDLE_WIDE_TILES, TILE_SIZE,
)

PUDDLE_CLEARANCE = 0.3     # tiles a puddle keeps from every building and tree
PUDDLE_SPACING = 2.5       # tiles at least between two puddles' centres
PUDDLE_GAP = 1.0           # tiles at least between two puddles' edges
ASPECT = (0.34, 0.5)       # a puddle's height for its width, flattest and roundest
MAX_HEIGHT_TILES = 0.93       # no puddle is taller than this, however wide
PUDDLE_GROW_SPAN = 0.25    # wetness over a puddle's threshold it takes to reach its full size
THRESHOLDS = (0.03, 0.7)   # the wetness the puddles start to show at, the first and the last
GROWTH_STEPS = 6           # sizes a puddle is drawn in on its way to full
RING_SIZE_MIN = 0.4        # how grown a puddle must be for raindrops on it to make rings
PLACE_ATTEMPTS_PER_TICK = 600   # spots tried per update while placing
TRIES_PER_PUDDLE = 6       # spots tried for each puddle wanted, most near something they must keep clear of
CHUNK_TILES = 8            # puddles are filed in squares of this many tiles, to find those in view

WATER_MULTIPLY = (160, 172, 190)     # the ground is multiplied by this, so it shows through: darker and cooler
SKY_COLOUR = (172, 188, 210, 48)     # the overcast sky mirrored in it, laid evenly over the whole water
RIM_COLOUR = (214, 228, 242, 140)    # the thin pale edge of the water, catching the light...
RIM_FAR_SHARE = 0.35                 # ...on its near side; on the far side only this much of it
GLINT_COLOUR = (232, 240, 248, 150)  # a thin glint of light on its far side
RIPPLE_COLOUR = (236, 244, 252)      # the rings (alpha fading from 230) round the feet of whoever wades through
RIPPLE_STEP_PX = 14                  # world pixels walked in a puddle between two steps' rings
RIPPLE_SECONDS = 1.0                 # how long a step's rings spread before they are gone
RIPPLE_WIDTH_TILES = (0.2, 1.6)      # the outer ring's width, as it starts and as it fades
RIPPLE_RINGS = (1.0, 0.68, 0.4)      # the rings of a step, as shares of the outer one
WOBBLE_PX = 3.0                      # how far a fresh step shakes the reflection sideways, in art pixels
SPLASH_SECONDS = 0.22                # the droplets a step throws up, flying...
SPLASH_REACH_TILES = 0.35            # ...this far out
SPLASH_COLOUR = (230, 240, 250, 210)
RIPPLE_FLAT = 0.42                   # its height for its width, as the puddles are seen
REFLECTION_TINT = (222, 234, 248)    # what stands over a puddle, mirrored in it: cooled by this...
REFLECTION_ALPHA = 115               # ...and this see-through (255 is a perfect mirror)


class Puddle:
    """One puddle: where it is, its shape (ellipses in tiles, relative to its centre) and when it shows."""

    __slots__ = ('x', 'y', 'lobes', 'width', 'height', 'threshold')

    def __init__(self, x: float, y: float, rng: random.Random) -> None:
        self.x = x
        self.y = y
        wide = rng.random() < PUDDLE_WIDE_SHARE
        width = rng.uniform(*(PUDDLE_WIDE_TILES if wide else PUDDLE_SIZE_TILES))
        height = min(width * rng.uniform(*ASPECT), MAX_HEIGHT_TILES)
        # (centre x, centre y, width, height). A flat core off the middle...
        core_w = width * rng.uniform(0.42, 0.58)
        self.lobes: List[Tuple[float, float, float, float]] = [
            (rng.uniform(-0.1, 0.1) * width, 0.0, core_w, height * rng.uniform(0.7, 0.9))]
        # ...arms running out to both sides, flatter the further out, drifting up or down...
        for side in (-1, 1):
            reach, drift, last_h = 0.0, 0.0, self.lobes[0][3]
            for _ in range(rng.randint(2, 3)):
                arm_w = width * rng.uniform(0.22, 0.42)
                arm_h = height * rng.uniform(0.4, 0.75) * (1 - reach / width)
                reach = min(width / 2 - arm_w / 2, reach + arm_w * rng.uniform(0.45, 0.8))
                # it may drift up or down, but not off the one before it
                drift += rng.uniform(-0.3, 0.3) * min(last_h, arm_h)
                self.lobes.append((side * reach, drift, arm_w, arm_h))
                last_h = arm_h
        # ...and small nubs bulging out of the edge here and there
        for _ in range(rng.randint(2, 4)):
            bx, by, bw, bh = rng.choice(self.lobes)
            nub_w = width * rng.uniform(0.1, 0.2)
            self.lobes.append((bx + rng.uniform(-0.45, 0.45) * bw, by + rng.choice((-1, 1)) * bh * rng.uniform(0.3, 0.45),
                               nub_w, nub_w * rng.uniform(0.5, 0.8)))
        self.width = max(abs(cx) * 2 + w for cx, _cy, w, _h in self.lobes)
        self.height = max(abs(cy) * 2 + h for _cx, cy, _w, h in self.lobes)
        if self.height > MAX_HEIGHT_TILES:   # the lobes stuck out: flatten the whole of it
            squash = MAX_HEIGHT_TILES / self.height
            self.lobes = [(cx, cy * squash, w, h * squash) for cx, cy, w, h in self.lobes]
            self.height = MAX_HEIGHT_TILES
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


def _render(puddle: Puddle, growth: float, scale: float) -> Tuple[pygame.Surface, ...]:
    """The puddle grown to *growth*, at a screen scale, all centred on surfaces of one size:
    what to multiply the ground with (white is no change), the sky in it, what to lay over
    the reflections (rim, glint), and the water's shape as alpha twice: REFLECTION_ALPHA
    inside to cut a reflection to, and 255 inside to cut the rings of who wades through to."""
    px = TILE_SIZE * scale * growth   # screen pixels per tile of the puddle's shape
    pixel = max(1, round(scale))      # one pixel of the art at this scale
    w = int(puddle.width * px) + 4 * pixel + 4
    h = int(puddle.height * px) + 4 * pixel + 4
    cx, cy = w / 2, h / 2

    def lobes(colour, grow: float = 0.0, shrink: float = 1.0, lift: float = 0.0,
              target: Optional[pygame.Surface] = None) -> pygame.Surface:
        """All the lobes in one colour, so where they overlap it does not double up."""
        if target is None:
            target = pygame.Surface((w, h), pygame.SRCALPHA)
        for lx, ly, lw, lh in puddle.lobes:
            rw, rh = lw * px * shrink + 2 * grow, lh * px * shrink + 2 * grow
            if rw >= 1 and rh >= 1:
                pygame.draw.ellipse(target, colour, (round(cx + lx * px * shrink - rw / 2),
                                                     round(cy + ly * px * shrink - lift - rh / 2),
                                                     round(rw), round(rh)))
        return target

    multiply = pygame.Surface((w, h))
    multiply.fill((255, 255, 255))
    lobes(WATER_MULTIPLY, target=multiply)
    # The sky, under the reflections: evenly over all the water, so its edge is no darker than its middle
    sky = lobes(SKY_COLOUR)
    # The rim: one pixel of the art round the water (the shape grown less the shape),
    # catching the light on the near side and fading out towards the far one
    rim = lobes(RIM_COLOUR, grow=pixel)
    rim.blit(lobes((255, 255, 255, 255)), (0, 0), special_flags=pygame.BLEND_RGBA_SUB)
    for row in range(h):
        fade = RIM_FAR_SHARE + (1 - RIM_FAR_SHARE) * row / max(1, h - 1)
        rim.fill((255, 255, 255, round(255 * fade)), (0, row, w, 1), special_flags=pygame.BLEND_RGBA_MULT)
    over = rim
    if growth > 0.5:
        _lx, ly, mw, mh = puddle.lobes[0]
        length = max(2 * pixel, round(mw * px * 0.22))
        over.fill(GLINT_COLOUR, (round(cx - mw * px * 0.12 - length / 2), round(cy + ly * px - mh * px * 0.26),
                                 length, pixel))
    mirror = pygame.Surface((w, h), pygame.SRCALPHA)
    mirror.fill((255, 255, 255, 0))
    lobes((255, 255, 255, REFLECTION_ALPHA), target=mirror)
    water = lobes((255, 255, 255, 255))
    return multiply, sky, over, mirror, water


class Puddles:
    """The map's puddles for the current wet spell, sized by the ground's wetness."""

    def __init__(self, tmx_map, rng: Optional[random.Random] = None) -> None:
        self.tmx_map = tmx_map
        self.rng = rng or random.Random()
        self.puddles: List[Puddle] = []
        self.placed: List[Puddle] = []   # the puddles once all of them are placed; a new list each wet spell
        self.wetness = 0.0
        self._dried = True           # the ground has been dry since the puddles were placed
        self._by_tile: Dict[Tuple[int, int], List[Puddle]] = {}
        self._sprites: Dict[tuple, Tuple[pygame.Surface, ...]] = {}
        self._flips: Dict[int, Tuple[pygame.Surface, pygame.Surface]] = {}
        self._walked: Dict[int, Tuple[float, float, float]] = {}   # per figurine: feet, distance since its last ring
        self.ripples: List[list] = []   # each [puddle, x, y, age]: rings round the feet of who walks through
        self._clock = 0.0               # seconds the walkers have been updated for, to move the wobble
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
        taken: Dict[Tuple[int, int], List[Puddle]] = {}
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
            near = [p for dx in (-2, -1, 0, 1, 2) for dy in (-2, -1, 0, 1, 2)
                    for p in taken.get((home[0] + dx, home[1] + dy), ())]
            if any((o.x - puddle.x) ** 2 + (o.y - puddle.y) ** 2 < spacing ** 2
                   or (abs(o.x - puddle.x) < ((o.width + puddle.width) / 2 + PUDDLE_GAP) * TILE_SIZE
                       and abs(o.y - puddle.y) < ((o.height + puddle.height) / 2 + PUDDLE_GAP) * TILE_SIZE)
                   for o in near):
                continue
            placed[on_path] += 1
            taken.setdefault(home, []).append(puddle)
            self.puddles.append(puddle)
            chunk = CHUNK_TILES * TILE_SIZE
            self._by_chunk.setdefault((int(puddle.x // chunk), int(puddle.y // chunk)), []).append(puddle)
            for ty in range(int((puddle.y - puddle.height * TILE_SIZE / 2) // TILE_SIZE),
                            int((puddle.y + puddle.height * TILE_SIZE / 2) // TILE_SIZE) + 1):
                for tx in range(int((puddle.x - puddle.width * TILE_SIZE / 2) // TILE_SIZE),
                                int((puddle.x + puddle.width * TILE_SIZE / 2) // TILE_SIZE) + 1):
                    self._by_tile.setdefault((tx, ty), []).append(puddle)
        self.placed = list(self.puddles)

    def puddle_under(self, x: float, y: float) -> Optional[Puddle]:
        """The puddle at a world point, if it is grown enough for anything to ring on it."""
        for puddle in self._by_tile.get((int(x // TILE_SIZE), int(y // TILE_SIZE)), ()):
            growth = puddle.growth(self.wetness)
            if growth >= RING_SIZE_MIN and puddle.covers(x, y, growth):
                return puddle
        return None

    def puddle_at(self, x: float, y: float) -> bool:
        """Whether a world point is in a puddle grown enough for raindrops to ring on it."""
        return self.puddle_under(x, y) is not None

    def _wobble(self, layer: pygame.Surface, amplitude: float, pixel: int) -> pygame.Surface:
        """The reflection shaken sideways in bands of a few pixels, as a disturbed surface breaks it up."""
        if amplitude < 0.5:
            return layer
        out = pygame.Surface(layer.get_size(), pygame.SRCALPHA)
        band = 2 * pixel
        for top in range(0, layer.get_height(), band):
            shift = round(amplitude * math.sin(top / pixel * 0.9 + self._clock * 14.0))
            out.blit(layer, (shift, top), pygame.Rect(0, top, layer.get_width(), band))
        return out

    def update_walkers(self, dt: float, figurines) -> None:
        """Ring the water round the feet of every figurine walking through a puddle (call while the game runs).

        A ring every RIPPLE_STEP_PX walked in the water, and one at once on
        stepping in; standing still makes none.
        """
        self._clock += dt
        self.ripples = [ripple for ripple in self.ripples if ripple[3] + dt < RIPPLE_SECONDS]
        for ripple in self.ripples:
            ripple[3] += dt
        if self.wetness <= 0:
            self._walked.clear()
            return
        walked = {}
        for figurine in figurines:
            off_x, off_y = figurine.sprite_draw_offset
            fx = figurine.x + off_x + figurine.sprite_width / 2
            fy = figurine.y + off_y + figurine.sprite_height - 2
            last = self._walked.get(id(figurine))
            distance = RIPPLE_STEP_PX
            if last is not None:
                moved = ((fx - last[0]) ** 2 + (fy - last[1]) ** 2) ** 0.5
                distance = last[2] + moved
                puddle = self.puddle_under(fx, fy) if moved > 0 else None
                if puddle is None:
                    distance = RIPPLE_STEP_PX if moved > 0 else last[2]   # ready to ring on stepping in
                elif distance >= RIPPLE_STEP_PX:
                    self.ripples.append([puddle, fx, fy, 0.0])
                    distance = 0.0
            walked[id(figurine)] = (fx, fy, distance)
        self._walked = walked

    def _flipped(self, sprite: pygame.Surface) -> pygame.Surface:
        """The sprite upside down, kept (sprites themselves are kept per zoom, so they come again)."""
        entry = self._flips.get(id(sprite))
        if entry is None or entry[0] is not sprite:
            if len(self._flips) > 1500:
                self._flips.clear()
            entry = self._flips[id(sprite)] = (sprite, pygame.transform.flip(sprite, False, True))
        return entry[1]

    def draw(self, screen: pygame.Surface, camera, offset_x: int, offset_y: int,
             render_queue: Sequence[Dict] = ()) -> None:
        """Lay the puddles in view on the ground, with what stands over them mirrored in them.

        Call it before the render queue is drawn: the queue's sprites (every
        house, tree and figurine in view) are what the puddles mirror, each
        flipped about its base line (the bottom of its sprite, where it meets
        the ground), so only what stands behind or in a puddle shows in it.
        Lights and other blended entries are left out.
        """
        if self.wetness <= 0 or not self.puddles:
            return
        scale = round(TILE_SIZE * camera.zoom) / float(TILE_SIZE)
        cam_x, cam_y = round(camera.x * scale), round(camera.y * scale)
        view_w, view_h = camera.screen_width, camera.screen_height
        reach = max(PUDDLE_SIZE_TILES[1], PUDDLE_WIDE_TILES[1]) * TILE_SIZE * scale
        if len(self._sprites) > 4000:
            self._sprites.clear()
        chunk = CHUNK_TILES * TILE_SIZE * scale
        cx0, cy0 = int((cam_x - reach) // chunk), int((cam_y - reach) // chunk)
        cx1, cy1 = int((cam_x + view_w + reach) // chunk), int((cam_y + view_h + reach) // chunk)
        in_view = [puddle for cy in range(cy0, cy1 + 1) for cx in range(cx0, cx1 + 1)
                   for puddle in self._by_chunk.get((cx, cy), ())]
        shown = []
        rects = {}   # the puddles shown, each to its (rect, sprites)
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
            w, h = sprites[0].get_size()
            shown.append((pygame.Rect(round(sx - w / 2) + offset_x, round(sy - h / 2) + offset_y, w, h), sprites))
            rects[puddle] = shown[-1]
        if not shown:
            return
        screen.blits([(multiply, rect, None, pygame.BLEND_MULT) for rect, (multiply, *_rest) in shown],
                     doreturn=False)
        screen.blits([(sky, rect) for rect, (_m, sky, *_rest) in shown], doreturn=False)

        # What may be mirrored: (left, base line, width, height, sprite), in drawing order
        standing = []
        for item in render_queue:
            if item.get('flags'):
                continue
            sprite = item['sprite']
            x, y = round(item['pos'][0]), round(item['pos'][1])
            standing.append((x, y + sprite.get_height(), sprite.get_width(), sprite.get_height(), sprite))
        # How hard each puddle's surface is being stirred, by the freshest step in it
        stirred: Dict[Puddle, float] = {}
        for puddle, _x, _y, age in self.ripples:
            stirred[puddle] = max(stirred.get(puddle, 0.0), 1 - age / RIPPLE_SECONDS)
        pixel = max(1, round(scale))
        for puddle, (rect, (_m, _s, _o, mirror, _w)) in rects.items():
            layer = None
            for x, base, w, h, sprite in standing:
                if base >= rect.bottom or base + h <= rect.top or x >= rect.right or x + w <= rect.left:
                    continue
                if layer is None:
                    layer = pygame.Surface(rect.size, pygame.SRCALPHA)
                layer.blit(self._flipped(sprite), (x - rect.x, base - rect.y))
            if layer is not None:
                layer.fill(REFLECTION_TINT, special_flags=pygame.BLEND_RGB_MULT)
                layer.blit(mirror, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
                if puddle in stirred:
                    layer = self._wobble(layer, WOBBLE_PX * pixel * stirred[puddle] ** 1.5, pixel)
                screen.blit(layer, rect)

        # Rings round the feet of who wades through, spreading and fading, cut to the water
        rings: Dict[Puddle, pygame.Surface] = {}
        drops = []
        for puddle, x, y, age in self.ripples:
            if puddle not in rects:
                continue
            rect, sprites = rects[puddle]
            layer = rings.get(puddle)
            if layer is None:
                layer = rings[puddle] = pygame.Surface(rect.size, pygame.SRCALPHA)
            progress = age / RIPPLE_SECONDS
            alpha = 230 * (1 - progress) ** 1.3
            thick = 2 * pixel if progress < 0.45 else pixel
            centre = (x * scale - cam_x + offset_x - rect.x, y * scale - cam_y + offset_y - rect.y)
            for share in RIPPLE_RINGS:   # the outer ring, and smaller ones inside it
                spread = RIPPLE_WIDTH_TILES[0] + (RIPPLE_WIDTH_TILES[1] - RIPPLE_WIDTH_TILES[0]) * progress ** 0.7
                width = spread * share * TILE_SIZE * scale
                height = max(2 * pixel, width * RIPPLE_FLAT)
                pygame.draw.ellipse(layer, (*RIPPLE_COLOUR, round(alpha * (0.5 + 0.5 * share))),
                                    (round(centre[0] - width / 2), round(centre[1] - height / 2),
                                     round(width), round(height)), min(thick, max(1, round(height / 2))))
            if age < SPLASH_SECONDS:
                drops.append((rect.x + centre[0], rect.y + centre[1], age / SPLASH_SECONDS))
        for puddle, layer in rings.items():
            rect, (*_layers, water) = rects[puddle]
            layer.blit(water, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
            screen.blit(layer, rect)
        # The droplets a step throws up: out to the sides and up, falling back, not cut to the water
        reach = SPLASH_REACH_TILES * TILE_SIZE * scale
        for sx, sy, t in drops:
            for dx, lift in ((-1.0, 0.55), (-0.55, 0.9), (0.55, 0.9), (1.0, 0.55), (-0.2, 1.1), (0.25, 1.0)):
                px = sx + dx * reach * t
                py = sy - lift * reach * 4 * t * (1 - t) * 0.8 - reach * 0.1 * t
                screen.fill(SPLASH_COLOUR, (round(px), round(py), pixel, pixel))

        screen.blits([(over, rect) for rect, (_m, _s, over, *_rest) in shown], doreturn=False)
