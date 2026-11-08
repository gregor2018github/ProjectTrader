"""The fishing minigame's scene: a pond in cross-section, drawn as pixel art.

Everything is drawn into a small picture of ``LOW_W`` x ``LOW_H`` pixels (see
``fishing_pond.py`` for the pond's shape) and scaled up ``PX`` times without
smoothing, so every pixel shows as a crisp block: the look of hand-made pixel
art, at almost no cost a frame.

Above the water: the sky of the hour (sun, moon, stars, drifting clouds), far
hills, the mountain from the sketch, the far shore with its larches, a bush and
the reeds, a heron and a paddling duck, and the player's bank with its pines,
the player and the rod. The trees, bush, grass and reeds go with the season
(golden larches in Autumn, bare ones and snow in Winter).

Below it: the water's cross-section, the bottom from the shelf under the bank
to the deep hollow and the far shallows, roots on the slope (they snag a bait
dragged over them), an old cart wheel in the hollow, weeds swaying. It is dark
down there: only a soft, dithered circle round the bait (``PondView.focus``)
shows what is near it, and the first few feet under the surface, where the
light still reaches, show a little; a fish further off is two glinting eyes at
the edge of the light, bubbles rise over the bottom feeders. By day, shafts of
light slant down from the surface.

The light of the hour (the map's ``ambient_light``, dimmed by clouds and storm,
lifted a little at night) is multiplied into everything but the sky; rain, snow,
fog and lightning (with thunder, returned by ``update``) are the game's weather.
"""

import datetime
import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import pygame

from .fishing_pond import LOW_W, LOW_H, WATER_Y, BANK_EDGE, SNAGS, Fish, Species, bottom_y
from .outdoors import Conditions
from .woodhacking_scene import (
    _PLAYER_FILE, _ARMS_CLEAR, _FRONT_SHOULDER, _NEAR_SHOULDER, _HIP,
    _SLEEVE, _SLEEVE_LIGHT, _ARM_OUTLINE, _CUFF, _SKIN,
)
from ..daylight import ambient_light, overcast, sun_hour
from ...sim.calendar import game_date

Colour = Tuple[int, int, int]

PX = 4                                   # each low pixel is this many screen pixels
SCENE_W, SCENE_H = LOW_W * PX, LOW_H * PX
ROD_LEN = 40.0
BANK_TOP = 60                            # the player's bank, where his feet stand
_SHAFT_TOP, _SHAFT_H = WATER_Y + 1, 70   # the band the shafts of light are drawn in
NIGHT_LIFT = 0.32                        # the night lifted this far towards daylight, to keep it playable
_SCENERY_SEED = 1517                     # the pond looks the same every time

_BAYER = ((0, 8, 2, 10), (12, 4, 14, 6), (3, 11, 1, 9), (15, 7, 13, 5))

# The sky by sun hour: top and bottom of its gradient
_SKY = (
    (0.0, (12, 18, 36), (26, 38, 60)),
    (4.6, (12, 18, 36), (26, 38, 60)),
    (5.8, (40, 46, 84), (150, 102, 110)),
    (6.9, (88, 118, 150), (236, 170, 122)),
    (8.5, (96, 144, 164), (176, 206, 200)),
    (16.8, (96, 144, 164), (176, 206, 200)),
    (18.4, (108, 106, 140), (242, 168, 108)),
    (19.9, (48, 46, 86), (146, 92, 104)),
    (21.2, (12, 18, 36), (26, 38, 60)),
    (24.0, (12, 18, 36), (26, 38, 60)),
)
_STORM_SKY = (88, 96, 104)

# By season (0 Spring, 1 Summer, 2 Autumn, 3 Winter): light and shade
_LARCH = {0: ((134, 176, 78), (92, 136, 60)), 1: ((96, 146, 60), (66, 110, 48)),
          2: ((232, 176, 58), (190, 122, 40)), 3: None}
_BUSH = {0: ((118, 156, 70), (84, 120, 54)), 1: ((90, 132, 56), (64, 100, 44)),
         2: ((222, 102, 46), (150, 56, 36)), 3: ((122, 96, 70), (88, 68, 52))}
_GRASS = {0: (112, 156, 72), 1: (118, 148, 64), 2: (156, 136, 66), 3: (138, 132, 102)}
_REEDS = {0: ((118, 158, 74), (84, 120, 56)), 1: ((96, 142, 60), (70, 110, 46)),
          2: ((186, 156, 88), (146, 116, 64)), 3: ((166, 146, 108), (128, 110, 80))}
_WEED = {0: (66, 112, 70), 1: (60, 116, 66), 2: (84, 104, 60), 3: (60, 84, 66)}
_PINE = ((38, 70, 60), (58, 96, 74))
_SNOW = (232, 236, 242)

_WATER_TOP, _WATER_LOW = (76, 130, 134), (20, 44, 58)
_DARK = (6, 14, 22)                      # the murk the deep water fades into

# The player: the game's own right-facing standing sprite (the woodhacking's), scaled
# down to the pond's pixels, its painted arms taken out and drawn again holding the rod.
# As in the woodhacking, one angle poses him: there the axe's, here the rod's. It turns
# the far arm about its shoulder (``_ARM_BY_THETA``), its fist holds the rod (so the rod
# starts where the fist is, ``grip_at``), the near hand takes the handle behind it, and
# the upper body leans back to cast and forward after it (``_LEAN_BY_THETA``).
_PLAYER_H = 34                           # low pixels tall
_PLAYER_LEFT = 17
_PLAYER_SCALE = _PLAYER_H / 336          # the sprite is 208 x 336
_PLAYER_TOP = BANK_TOP - _PLAYER_H
_HIP_ROW = round(_HIP[1] * _PLAYER_SCALE)   # the upper body leans over the legs from here
_EYE_SEARCH = (110, 110, 62, 40)         # in the sprite's pixels: where its eyes are looked for
_EYE_SKIN = (140, 105)                   # and a spot of bare skin between them
_ART = _PLAYER_H / 230                   # the woodhacking's arm lengths are for a player 230 pixels tall
_UPPER, _FORE = 21.0 * _ART, 20.0 * _ART
_NEAR_UPPER, _NEAR_FORE = 30.0 * _ART, 28.0 * _ART
_ARM_REACH = 0.9                         # the fist's distance from the shoulder, of the arm's full length
_NEAR_GRIP = (8.0 * _ART, 24.0 * _ART)  # how far behind the fist the near hand may hold the handle
# The far arm's direction (screen degrees: 0 forward, 90 up) by the rod's angle from upright
_ARM_BY_THETA = ((-90.0, 118.0), (-45.0, 78.0), (0.0, 30.0), (26.0, -8.0), (75.0, -42.0))
# How far the upper body leans, in pixels (back is negative)
_LEAN_BY_THETA = ((-90.0, -1.6), (-30.0, -0.6), (10.0, 0.0), (45.0, 0.9), (75.0, 1.5))


def _on_player(point: Tuple[float, float]) -> Tuple[float, float]:
    """A point in the sprite's own pixels, in the scene's."""
    return _PLAYER_LEFT + point[0] * _PLAYER_SCALE, _PLAYER_TOP + point[1] * _PLAYER_SCALE


def _interp(x: float, points: Sequence[Tuple[float, float]]) -> float:
    if x <= points[0][0]:
        return points[0][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return points[-1][1]


def player_lean(theta: float) -> int:
    return round(_interp(theta, _LEAN_BY_THETA))


def _shoulders(theta: float) -> Tuple[Tuple[float, float], Tuple[float, float]]:
    """The far and the near shoulder, moved with the upper body's lean."""
    lean = player_lean(theta)
    far, near = _on_player(_FRONT_SHOULDER), _on_player(_NEAR_SHOULDER)
    return (far[0] + lean, far[1]), (near[0] + lean, near[1])


def grip_at(theta: float) -> Tuple[float, float]:
    """Where the fist holds the rod with the rod at that angle."""
    far, _ = _shoulders(theta)
    a = math.radians(_interp(theta, _ARM_BY_THETA))
    reach = (_UPPER + _FORE) * _ARM_REACH
    return far[0] + math.cos(a) * reach, far[1] - math.sin(a) * reach

_DUCK = (
    ".......gg..",
    "......gegyy",
    "......gg...",
    "bb...wbb...",
    ".bbbbbbbbb.",
    "..BBBBBBB..",
)
_DUCK_PAL = {"g": (44, 98, 66), "e": (12, 12, 12), "y": (230, 186, 64), "w": (228, 228, 216),
             "b": (132, 112, 90), "B": (86, 74, 60)}

_HERON = (
    "...dd....",
    "yyyGgd...",
    "...gg....",
    "....g....",
    "...gg....",
    "...g.....",
    "...gg....",
    "..gggg...",
    "..gGGGg..",
    "..gGGGGd.",
    "...gGGGdd",
    "....gGd..",
    ".....l...",
    ".....l...",
    ".....l...",
    ".....l...",
    ".....l...",
    "....ll...",
)
_HERON_PAL = {"g": (160, 170, 174), "G": (104, 114, 122), "d": (52, 56, 66), "y": (222, 192, 92),
              "l": (122, 112, 82)}
_HERON_POS = (250, 56 - len(_HERON))


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _mix(a: Colour, b: Colour, t: float) -> Colour:
    t = max(0.0, min(1.0, t))
    return (round(a[0] + (b[0] - a[0]) * t), round(a[1] + (b[1] - a[1]) * t), round(a[2] + (b[2] - a[2]) * t))


def _shade(c: Colour, k: float) -> Colour:
    return (max(0, min(255, round(c[0] * k))), max(0, min(255, round(c[1] * k))), max(0, min(255, round(c[2] * k))))


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if x < lo else hi if x > hi else x


def _pixmap(rows: Sequence[str], palette: Dict[str, Colour]) -> pygame.Surface:
    surf = pygame.Surface((max(len(r) for r in rows), len(rows)), pygame.SRCALPHA)
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch in palette:
                surf.set_at((x, y), palette[ch])
    return surf


def _px(surf: pygame.Surface, x: float, y: float, colour) -> None:
    xi, yi = int(round(x)), int(round(y))
    if 0 <= xi < surf.get_width() and 0 <= yi < surf.get_height():
        surf.set_at((xi, yi), colour)


# ----------------------------------------------------------------------
# Fish sprites
# ----------------------------------------------------------------------

_fish_cache: Dict[Tuple[str, int, int], pygame.Surface] = {}


def _body_profile(shape: str, t: float) -> float:
    """Half the body's height along it, 0 at the tail's root to 1 at the snout, as a share of the most."""
    if shape == "pike":
        return 0.78 + 0.22 * math.sin(math.pi * t) if t < 0.78 else 0.95 - 2.2 * (t - 0.78)
    if shape == "eel":
        return min(1.0, 0.4 + 2.5 * t, 1.0 - 2.0 * max(0.0, t - 0.75))
    return max(0.25, math.sin(math.pi * (0.12 + 0.8 * t)) ** 0.6)


def fish_sprite(species: Species, length: int, frame: int = 0) -> pygame.Surface:
    """The fish facing right, ``length`` low pixels long; frames 1 and 2 have the tail flicked up and down."""
    key = (species.key, length, frame)
    cached = _fish_cache.get(key)
    if cached is not None:
        return cached
    back, side, belly, fin, mark = species.colours
    shape = species.shape
    L = length
    H = max(2, round(L * species.height))
    tail = 1 if species.minnow else (max(1, round(L * 0.08)) if shape == "eel" else max(2, round(L * 0.2)))
    w, h = L + 2, H + 6
    cy = h / 2
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    solid = set()

    def put(x, y, c):
        xi, yi = int(x), int(round(y))
        if 0 <= xi < w and 0 <= yi < h:
            surf.set_at((xi, yi), c)
            solid.add((xi, yi))

    body_len = max(1, L - tail - 1)
    eye_c = L - max(1, round(L * 0.13))
    for c in range(tail, L):
        t = (c - tail) / body_len
        hh = H / 2 * _body_profile(shape, t)
        top, bot = cy - hh, cy + hh * 0.95
        for row in range(int(math.floor(top + 0.5)), int(math.floor(bot + 0.5)) + 1):
            rel = (row - top) / max(0.5, bot - top)
            col = back if rel < 0.36 else side if rel < 0.72 else belly
            if shape == "perch" and rel < 0.7 and (c - tail) % max(3, L // 5) == 1:
                col = mark
            elif shape == "pike" and 0.25 < rel < 0.75 and (c * 7 + row * 5) % 6 == 0:
                col = mark
            elif shape == "carp" and rel < 0.7 and (c + row) % 3 == 0:
                col = _mix(col, back, 0.5)
            elif shape == "bream" and 0.3 < rel < 0.8 and (c + 2 * row) % 4 == 0:
                col = _mix(side, (230, 220, 180), 0.35)
            put(c + 1, row, col)
        # The dorsal fin, and the perch's spiky one
        if 0.3 < t < 0.6 and shape not in ("eel",):
            if shape != "perch" or (c % 2 == 0):
                put(c + 1, math.floor(top + 0.5) - 1, fin if shape in ("perch", "roach") else _shade(back, 0.8))
        if shape == "pike" and 0.08 < t < 0.2:
            put(c + 1, math.floor(top + 0.5) - 1, _shade(back, 0.85))
        # The fins under it
        if 0.4 < t < 0.52 and shape != "eel":
            put(c + 1, math.floor(bot + 0.5) + 1, fin)
    # The tail: forked, flicking up or down by frame
    flick = {0: 0, 1: -1, 2: 1}.get(frame, 0)
    for c in range(0, tail):
        u = 1 - c / max(1, tail)              # 1 at its end, 0 at its root
        spread = H * (0.18 + 0.36 * u) if shape != "eel" else H * 0.3 * (1 - u * 0.6)
        notch = spread * 0.5 * u if shape != "eel" and not species.minnow else 0
        shift = flick * u * 1.2
        for row in range(int(cy - spread), int(cy + spread) + 1):
            if abs(row - cy) < notch:
                continue
            put(c + 1, row + shift, fin if shape not in ("eel",) else side)
    # The eye, and the pike's long mouth
    eh = H / 2 * _body_profile(shape, (eye_c - tail) / body_len)
    eye_y = round(cy - eh * 0.25)
    put(eye_c + 1, eye_y, (18, 18, 16))
    if L >= 14:
        put(eye_c, eye_y - 1, _mix(side, (255, 255, 255), 0.5))
    if shape == "pike":
        for c in range(L - 4, L):
            put(c + 1, round(cy + 0.6), _shade(back, 0.6))
    # A dark outline, as pixel art has
    edge = _shade(back, 0.42)
    for (x, y) in list(solid):
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if (nx, ny) not in solid and 0 <= nx < w and 0 <= ny < h:
                surf.set_at((nx, ny), edge)
    _fish_cache[key] = surf
    return surf


def fish_frame(fish: Fish) -> int:
    return (0, 1, 0, 2)[int(fish.tail) % 4]


# ----------------------------------------------------------------------
# What the game hands the scene to draw
# ----------------------------------------------------------------------

@dataclass
class PondView:
    rod_theta: float = 30.0                  # the rod's angle from upright, in degrees, towards the water
    rod_bend: float = 0.0                    # how far its tip curves (degrees, towards the water)
    line: Optional[List[Tuple[float, float]]] = None    # the line from the rod's tip, low pixels
    hook: Optional[Tuple[float, float]] = None
    worm: bool = True
    float_at: Optional[Tuple[float, float]] = None
    float_under: bool = False
    fish: Sequence[Fish] = ()
    focus: Optional[Tuple[float, float, float]] = None  # the light circle round the bait: x, y, radius
    tension: float = 0.0                     # the line's tension in a fight: it glints when near breaking
    net: Optional[Tuple[float, float]] = None
    sweet_theta: Optional[float] = None      # while casting: a faint mark where the rod should be let go
    rod_kick: float = 0.0


def rod_points(theta: float, bend: float, steps: int = 10) -> List[Tuple[float, float]]:
    """The rod from the grip to the tip: theta degrees from upright towards the water, its tip curving by bend."""
    grip = grip_at(theta)
    pts = [grip]
    x, y = grip
    seg = ROD_LEN / steps
    for i in range(1, steps + 1):
        s = i / steps
        a = math.radians(theta + bend * s * s)
        x += math.sin(a) * seg
        y -= math.cos(a) * seg
        pts.append((x, y))
    return pts


def curve(a: Tuple[float, float], b: Tuple[float, float], sag: float, steps: int = 24) -> List[Tuple[float, float]]:
    """A line from a to b hanging by sag low pixels in the middle."""
    mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2 + sag * 2
    pts = []
    for i in range(steps + 1):
        t = i / steps
        u = 1 - t
        pts.append((u * u * a[0] + 2 * u * t * mx + t * t * b[0], u * u * a[1] + 2 * u * t * my + t * t * b[1]))
    return pts


# ----------------------------------------------------------------------
# The scene
# ----------------------------------------------------------------------

class PondScene:
    """The pond at a moment and in a weather (see the module)."""

    def __init__(self, when: Optional[datetime.datetime] = None, conditions: Optional[Conditions] = None,
                 rng: Optional[random.Random] = None) -> None:
        self.rng = rng or random.Random()
        self.c = conditions or Conditions()
        c = self.c
        if when is None:
            self.hour, self.season, light = 12.0, 1, (255, 255, 255)
        else:
            self.hour, self.season, light = sun_hour(when), game_date(when).season, ambient_light(when)
        light = overcast(light, c.clouds, c.storm)
        self.brightness = sum(light) / (3 * 255)
        self.night = _clamp((0.62 - self.brightness) / 0.42)
        self.light = tuple(round(ch + (255 - ch) * NIGHT_LIFT * (1 - self.brightness)) for ch in light)
        self.lit = self.light != (255, 255, 255)
        self.snowy = self.season == 3 and c.snow_cover > 0.05 or c.snow_cover > 0.3

        scenery = random.Random(_SCENERY_SEED)
        self.sky = self._build_sky(scenery)
        self.backdrop = self._build_backdrop(scenery)
        self.under = self._build_under(scenery)
        self.player = self._build_player()
        self.duck_img = _pixmap(_DUCK, _DUCK_PAL)
        self.heron_img = _pixmap(_HERON, _HERON_PAL)
        # Murky: a little light in the first feet under the surface, then dark
        a_top = _lerp(192, 220, self.night)
        a_mid = _lerp(232, 244, self.night)
        a_low = _lerp(248, 252, self.night)
        self.darkness = pygame.Surface((LOW_W, LOW_H - WATER_Y - 1), pygame.SRCALPHA)
        for y in range(self.darkness.get_height()):
            t = y / self.darkness.get_height()
            alpha = _lerp(a_top, a_mid, min(1.0, t / 0.16)) if t < 0.16 else _lerp(a_mid, a_low, (t - 0.16) / 0.84)
            self.darkness.fill((*_DARK, round(alpha)), (0, y, LOW_W, 1))
        self._holes: Dict[int, pygame.Surface] = {}
        # How far one sees round the bait
        self.sight = max(12.0, 25.0 * (1 - 0.2 * c.clouds) * (1 - 0.25 * min(1.0, c.rain + c.storm))
                         * _lerp(1.0, 0.62, self.night))

        self.t = 0.0
        # Weeds: x, height, phase
        self.weeds = []
        for x0, x1, n in ((228, 298, 26), (88, 112, 6), (60, 70, 3), (190, 214, 4)):
            for _ in range(n):
                x = scenery.uniform(x0, x1)
                self.weeds.append((x, scenery.uniform(6, 22) if x0 >= 228 else scenery.uniform(5, 13),
                                   scenery.uniform(0, 6.28)))
        self.reeds = [(scenery.uniform(238, 299), scenery.uniform(6, 17), scenery.uniform(0, 6.28),
                       scenery.random() < 0.35) for _ in range(30)]
        self.reeds += [(scenery.uniform(48, 56), scenery.uniform(4, 9), scenery.uniform(0, 6.28), False) for _ in range(5)]
        self.silt = [[self.rng.uniform(BANK_EDGE, LOW_W), self.rng.uniform(WATER_Y, LOW_H), self.rng.uniform(0, 6.28)]
                     for _ in range(70)]
        self.stars = [(scenery.randint(0, LOW_W - 1), scenery.randint(0, 40), scenery.uniform(0, 6.28)) for _ in range(46)]
        self.clouds = [self._new_cloud(anywhere=True) for _ in range(int(1 + 6 * c.clouds + 3 * c.storm))]
        self.shafts = [scenery.uniform(40, LOW_W) for _ in range(4)]
        self._shaft_water = self._build_shaft_water()
        self.fireflies = [[self.rng.uniform(20, 70) if i % 2 else self.rng.uniform(232, 296),
                           self.rng.uniform(38, 62), self.rng.uniform(0, 6.28)] for i in range(10)]
        self.duck_x, self.duck_dir = 236.0, -1
        self.heron_face, self._heron_t = -1, self.rng.uniform(4, 10)
        self.splashes: List[List[float]] = []     # x, y, vx, vy, life
        self.rings: List[List[float]] = []        # x, age, size
        self.bubbles: List[List[float]] = []      # x, y, speed
        self.puffs: List[List[float]] = []        # mud stirred up off the bottom: x, y, vx, vy, life
        self.drops = [self._new_drop(anywhere=True) for _ in range(int(150 * c.rain))]
        self.flakes = [self._new_flake(anywhere=True) for _ in range(int(110 * c.snow))]
        self.flash = 0.0
        self._flickers: List[float] = []
        self._thunder_in: Optional[float] = None
        self._next_strike = self.rng.uniform(4, 12)

    # ------------------------------------------------------------------
    # Built once
    # ------------------------------------------------------------------

    def _sky_colours(self) -> Tuple[Colour, Colour]:
        h = self.hour
        top, low = _SKY[0][1], _SKY[0][2]
        for (h0, t0, l0), (h1, t1, l1) in zip(_SKY, _SKY[1:]):
            if h0 <= h <= h1:
                k = (h - h0) / (h1 - h0) if h1 > h0 else 0
                top, low = _mix(t0, t1, k), _mix(l0, l1, k)
                break
        grey = 0.65 * self.c.clouds + 0.3 * self.c.storm
        dim = max(0.25, 1 - self.night)
        top = _mix(top, _shade(_STORM_SKY, dim + 0.1), grey)
        low = _mix(low, _shade(_STORM_SKY, dim + 0.2), grey)
        return top, low

    def _build_sky(self, rng: random.Random) -> pygame.Surface:
        top, low = self._sky_colours()
        self.sky_top, self.sky_low = top, low
        sky = pygame.Surface((LOW_W, WATER_Y + 2))
        for y in range(WATER_Y + 2):
            sky.fill(_mix(top, low, (y / (WATER_Y + 1)) ** 1.3), (0, y, LOW_W, 1))
        # The sun by day, the moon by night, low in the sky at the day's ends
        h = self.hour
        if 5.6 < h < 20.4 and self.c.clouds < 0.85:
            p = (h - 5.6) / 14.8
            sx, sy = 30 + 240 * p, 50 - 40 * math.sin(math.pi * p)
            warm = _mix((255, 244, 214), (255, 170, 100), 1 - math.sin(math.pi * p) ** 0.5)
            glow = pygame.Surface((LOW_W, WATER_Y + 2), pygame.SRCALPHA)
            for r, a in ((9, 26), (6, 50)):
                pygame.draw.circle(glow, (*warm, round(a * (1 - self.c.clouds))), (sx, sy), r)
            sky.blit(glow, (0, 0))
            pygame.draw.circle(sky, _mix(warm, top, 0.6 * self.c.clouds), (sx, sy), 3)
        elif (h < 5.6 or h > 20.4) and self.c.clouds < 0.85:
            p = ((h - 20.4) % 24) / 9.2
            mx, my = 40 + 220 * p, 34 - 22 * math.sin(math.pi * min(1, p))
            pygame.draw.circle(sky, (230, 228, 206), (mx, my), 3)
            pygame.draw.circle(sky, _mix(top, (200, 198, 180), 0.4), (mx + 1, my - 1), 2)
            pygame.draw.circle(sky, (230, 228, 206), (mx - 1, my), 2)
        return sky

    def _ridge(self, rng: random.Random, base: float, amp: float, freq: float) -> List[float]:
        a = [(rng.uniform(0.5, 1.0) * amp, rng.uniform(0.6, 1.4) * freq, rng.uniform(0, 6.28)) for _ in range(3)]
        return [base + sum(k * math.sin(x * f + p) for k, f, p in a) for x in range(LOW_W)]

    def _pine(self, surf: pygame.Surface, rng: random.Random, x0: float, base: float, height: int,
              colours: Optional[Tuple[Colour, Colour]], snow: bool) -> None:
        """A tiered conifer (a pine, or a larch in its season's colours; a bare larch in Winter)."""
        trunk = (84, 62, 44)
        for row in range(4):
            _px(surf, x0, base - row, trunk)
        if colours is None:          # bare: a trunk and twigs
            for row in range(height):
                _px(surf, x0, base - row, _shade(trunk, 0.9))
                if row > 3 and row % 3 == 0:
                    span = (height - row) * 0.28
                    for k in range(1, int(span) + 1):
                        _px(surf, x0 - k, base - row - k * 0.4, (104, 84, 64))
                        _px(surf, x0 + k, base - row - k * 0.5, (96, 76, 58))
            return
        light, dark = colours
        tier = max(4, height // 6)
        maxw = height * 0.3
        for row in range(2, height):
            frac = row / height
            w = (1 - frac) * maxw * (0.55 + 0.45 * (1 - (row % tier) / tier)) + 0.5
            y = base - row
            for dx in range(-int(w), int(w) + 1):
                c = light if dx < -w * 0.15 else dark
                if rng.random() < 0.18:
                    c = _mix(c, dark if c == light else light, 0.5)
                if snow and row % tier == tier - 1 and rng.random() < 0.8:
                    c = _SNOW
                _px(surf, x0 + dx, y, c)
        _px(surf, x0, base - height, dark)

    def _blob(self, surf: pygame.Surface, rng: random.Random, cx: float, cy: float, rx: float, ry: float,
              colours: Tuple[Colour, Colour], snow: bool) -> None:
        light, dark = colours
        for y in range(int(cy - ry - 2), int(cy + ry + 1)):
            for x in range(int(cx - rx - 2), int(cx + rx + 2)):
                d = ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2
                if d < 1.0 - rng.uniform(0, 0.25):
                    c = light if (x - cx) * 0.6 + (y - cy) < 0 else dark
                    if (x + y) % 3 == 0 and rng.random() < 0.5:
                        c = _mix(light, dark, 0.5)
                    if snow and y < cy - ry * 0.4:
                        c = _SNOW
                    _px(surf, x, y, c)

    def _build_backdrop(self, rng: random.Random) -> pygame.Surface:
        """All above the water that does not move, on a see-through layer."""
        s = pygame.Surface((LOW_W, WATER_Y + 1), pygame.SRCALPHA)
        winter = self.season == 3
        snow = self.snowy
        haze = _mix((92, 118, 126), self.sky_low, 0.35)
        # Far hills, then nearer ones with a fringe of conifers
        far = self._ridge(rng, 40, 5, 0.035)
        for x, top in enumerate(far):
            s.fill(haze, (x, int(top), 1, WATER_Y + 1 - int(top)))
            if snow and rng.random() < 0.7:
                _px(s, x, top, _mix(_SNOW, haze, 0.3))
        near = self._ridge(rng, 50, 3.5, 0.06)
        near_c = _mix((64, 92, 98), self.sky_low, 0.15)
        for x, top in enumerate(near):
            s.fill(near_c, (x, int(top), 1, WATER_Y + 1 - int(top)))
        for x in range(0, LOW_W, 3):
            h = rng.randint(2, 4)
            base = int(near[x]) + 1
            for k in range(h):
                for dx in range(-((h - k) // 2), (h - k) // 2 + 1):
                    _px(s, x + dx, base - k, _shade(near_c, 0.8) if not snow else _mix(_SNOW, near_c, 0.4))
        # The mountain (the sketch's), lit from the left, its foot in the water
        peak_x, peak_y = 150, 13
        for x in range(92, 224):
            span = (peak_x - 92) if x < peak_x else (224 - peak_x)
            k = abs(x - peak_x) / span
            top = peak_y + (k ** 0.85) * (WATER_Y - peak_y) + rng.uniform(-1.2, 1.2) + 2.5 * math.sin(x * 0.4) * k
            ridge_x = peak_x + 3 * math.sin(x * 0.2)
            for y in range(int(top), WATER_Y + 1):
                lit = x < ridge_x + (y - top) * 0.25
                c = (128, 134, 128) if lit else (88, 96, 100)
                if (x * 3 + y * 7) % 11 == 0:
                    c = _shade(c, 0.82)
                depth = y - top
                if winter and y < 34 + rng.uniform(-2, 2):
                    c = _SNOW if lit else (196, 204, 214)
                elif depth < 1.5 and lit and not winter:
                    c = _shade(c, 1.12)
                if y > WATER_Y - 12 + 3 * math.sin(x * 0.3):
                    c = (56, 88, 70) if lit else (44, 72, 60)
                    if snow and rng.random() < 0.3:
                        c = _SNOW
                _px(s, x, y, c)
        # Little conifers along the mountain's foot
        for x in range(96, 222, 4):
            self._pine(s, rng, x + rng.uniform(-1, 1), WATER_Y - 1, rng.randint(5, 9), _PINE, snow)
        # The far shore on the right: rocks, larches, a bush
        for x in range(232, LOW_W):
            top = 58 - min(1.0, (x - 232) / 30) * 6 + rng.uniform(-0.8, 0.8)
            for y in range(int(top), WATER_Y + 1):
                c = (86, 92, 96) if y - top > 1 else (124, 128, 126)
                if (x + 2 * y) % 5 == 0:
                    c = _shade(c, 0.85)
                if snow and y - top < 1:
                    c = _SNOW
                _px(s, x, y, c)
        larch = _LARCH[self.season]
        self._pine(s, rng, 262, 54, 34, larch, snow)
        self._blob(s, rng, 292, 46, 11, 7, _BUSH[self.season], snow)
        self._pine(s, rng, 278, 53, 46, larch, snow)
        self._pine(s, rng, 300, 52, 40, _PINE, snow)
        # The player's bank: two pines, grass over earth
        self._pine(s, rng, 6, BANK_TOP, 58, _PINE, snow)
        self._pine(s, rng, 18, BANK_TOP, 44, _PINE, snow)
        grass = _SNOW if snow else _GRASS[self.season]
        for x in range(0, BANK_EDGE + 1):
            top = BANK_TOP if x <= 46 else BANK_TOP + (x - 46) / (BANK_EDGE - 46) * (WATER_Y - BANK_TOP)
            top += 0.6 * math.sin(x * 1.3)
            for y in range(int(top), WATER_Y + 1):
                d = y - int(top)
                c = grass if d < 2 else (98, 74, 52) if d < 6 else (80, 60, 44)
                if d >= 2 and (x * 5 + y * 3) % 9 == 0:
                    c = (120, 104, 86)
                _px(s, x, y, c)
            if x % 2 == 0 and not snow:
                _px(s, x, int(top) - 1, _shade(grass, 0.85))
        return s

    @staticmethod
    def _build_shaft_water() -> pygame.Surface:
        """White where a shaft of light may show: the water, not the bank or the bottom."""
        s = pygame.Surface((LOW_W, _SHAFT_H), pygame.SRCALPHA)
        for x in range(LOW_W):
            depth = int(bottom_y(x)) - _SHAFT_TOP
            if depth > 0:
                s.fill((255, 255, 255, 255), (x, 0, 1, depth))
        return s

    def _shaft_layer(self, day: float) -> pygame.Surface:
        """The shafts of light under the surface, cut to the water; its top row is _SHAFT_TOP."""
        shaft = pygame.Surface((LOW_W, _SHAFT_H), pygame.SRCALPHA)
        for x0 in self.shafts:
            for k in range(0, 60, 2):
                a = round(30 * day * (1 - k / 60))
                shaft.fill((214, 236, 222, a), (x0 - 20 + k * 0.5, k, 5 + k * 0.08, 2))
        shaft.blit(self._shaft_water, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        return shaft

    def _build_under(self, rng: random.Random) -> pygame.Surface:
        """The water's cross-section and the bottom, without what moves."""
        s = pygame.Surface((LOW_W, LOW_H), pygame.SRCALPHA)
        top = _WATER_TOP if self.season != 1 else (74, 134, 128)
        for y in range(WATER_Y, LOW_H):
            s.fill(_mix(top, _WATER_LOW, ((y - WATER_Y) / (LOW_H - WATER_Y)) ** 0.8), (0, y, LOW_W, 1))
        # A far slope behind, for depth
        for x in range(LOW_W):
            back = bottom_y(x) - 16 - 5 * math.sin(x * 0.05) - 3 * math.sin(x * 0.17)
            back = max(back, WATER_Y + 12)
            base = s.get_at((x, int(back)))[:3]
            for y in range(int(back), LOW_H):
                s.set_at((x, y), _mix(s.get_at((x, y))[:3], (34, 66, 72), 0.45))
        # The bottom: silt over earth, pebbles and moss
        for x in range(LOW_W):
            b = bottom_y(x)
            for y in range(int(b), LOW_H):
                d = y - int(b)
                c = (104, 100, 78) if d < 2 else (58, 60, 50) if d < 9 else (44, 46, 40)
                r = (x * 7 + y * 13) % 17
                if d >= 2 and r == 0:
                    c = (110, 108, 92)
                elif d < 4 and r == 5:
                    c = (64, 92, 60)
                s.set_at((x, y), c)
        # Stones lying on it
        for _ in range(22):
            x = rng.uniform(BANK_EDGE + 4, LOW_W - 4)
            y = bottom_y(x)
            r = rng.choice((1, 1, 2))
            pygame.draw.ellipse(s, (96, 100, 96), (x - r, y - r, 2 * r + 1, r + 1))
            _px(s, x - r + 1, y - r, (130, 134, 126))
        # The roots on the slope (they snag a bait dragged over them)
        root, root_lit = (66, 50, 36), (98, 76, 52)
        for pts in (((56, 70), (64, 74), (72, 77), (78, 76)), ((60, 78), (70, 84), (80, 88), (86, 87)),
                    ((66, 86), (74, 93), (82, 99)), ((72, 90), (76, 95), (79, 102))):
            pygame.draw.lines(s, root, False, pts, 1)
            for (x, y) in pts[1:]:
                _px(s, x, y - 1, root_lit)
        # An old cart wheel, half sunk in the hollow
        cx, cy = 176, 149
        pygame.draw.circle(s, (78, 62, 44), (cx, cy), 6, 1)
        for a in range(0, 360, 60):
            pygame.draw.line(s, (70, 56, 40), (cx, cy), (cx + 5 * math.cos(math.radians(a)), cy + 5 * math.sin(math.radians(a))))
        pygame.draw.circle(s, (92, 74, 52), (cx, cy), 1)
        for x in range(cx - 8, cx + 9):
            for y in range(int(bottom_y(x)) + 1, int(bottom_y(x)) + 3):
                s.set_at((x, y), (104, 100, 78) if y == int(bottom_y(x)) + 1 else (58, 60, 50))
        return s

    @staticmethod
    def _build_player() -> pygame.Surface:
        """The player's sprite without its painted arms, at the pond's pixel size, its edge kept crisp."""
        try:
            sprite = pygame.image.load(_PLAYER_FILE)
            sprite = sprite.convert_alpha() if pygame.display.get_surface() else sprite
        except (pygame.error, FileNotFoundError):
            return pygame.Surface((1, 1), pygame.SRCALPHA)
        sprite = sprite.copy()
        for rect in _ARMS_CLEAR:
            sprite.fill((0, 0, 0, 0), rect)
        size = (round(sprite.get_width() * _PLAYER_SCALE), _PLAYER_H)
        small = pygame.transform.smoothscale(sprite, size)
        for y in range(size[1]):
            for x in range(size[0]):
                r, g, b, a = small.get_at((x, y))
                if a < 110:
                    small.set_at((x, y), (0, 0, 0, 0))
                else:
                    k = 255 / a          # undo the edge's blending with the see-through
                    small.set_at((x, y), (min(255, round(r * k)), min(255, round(g * k)), min(255, round(b * k)), 255))
        PondScene._crisp_eyes(sprite, small)
        return small

    @staticmethod
    def _crisp_eyes(sprite: pygame.Surface, small: pygame.Surface) -> None:
        """Shrunk to a tenth, the eyes blur into grey (the far one is a stroke three pixels
        wide): find each in the sprite and set it again as two dark pixels on clean skin."""
        face = pygame.Rect(_EYE_SEARCH)
        dark = [(x, y) for y in range(face.top, face.bottom) for x in range(face.left, face.right)
                if sprite.get_at((x, y))[3] > 200 and sum(sprite.get_at((x, y))[:3]) < 150]
        if not dark:
            return
        skin = small.get_at((round(_EYE_SKIN[0] * _PLAYER_SCALE), round(_EYE_SKIN[1] * _PLAYER_SCALE)))
        ink = min((sprite.get_at(p) for p in dark), key=lambda c: sum(c[:3]))
        # Group the dark pixels into eyes by gaps across
        eyes, xs = [], sorted({x for x, _ in dark})
        group = [xs[0]]
        for x in xs[1:]:
            if x - group[-1] > 4:
                eyes.append(group)
                group = []
            group.append(x)
        eyes.append(group)
        for cols in eyes:
            ys = [y for x, y in dark if cols[0] <= x <= cols[-1]]
            cx = round((cols[0] + cols[-1]) / 2 * _PLAYER_SCALE)
            top = round(min(ys) * _PLAYER_SCALE)
            for x in (cx - 1, cx, cx + 1):      # the grey smear under it back to skin
                y = top + 2
                if 0 <= x < small.get_width() and small.get_at((x, y))[3] \
                        and sum(small.get_at((x, y))[:3]) < sum(skin[:3]) - 12:
                    small.set_at((x, y), skin)
            for y in (top, top + 1):
                # The grey smear beside the eye back to skin, then the eye
                for x in (cx - 1, cx + 1):
                    if 0 <= x < small.get_width() and small.get_at((x, y))[3] \
                            and sum(small.get_at((x, y))[:3]) < sum(skin[:3]) - 12:
                        small.set_at((x, y), skin)
                small.set_at((cx, y), ink)

    def _hole(self, r: int) -> pygame.Surface:
        """What the light round the bait takes off the dark: full in the middle, dithered at the edge."""
        hole = self._holes.get(r)
        if hole is not None:
            return hole
        size = 2 * r + 3
        hole = pygame.Surface((size, size), pygame.SRCALPHA)
        c = size / 2
        for y in range(size):
            for x in range(size):
                d = math.hypot(x + 0.5 - c, y + 0.5 - c)
                v = _clamp((r - d) / (r * 0.55))
                v = v * v * (3 - 2 * v)
                level = math.floor(v * 4 + _BAYER[y % 4][x % 4] / 16) / 4
                if level > 0:
                    hole.set_at((x, y), (0, 0, 0, round(255 * min(1.0, level))))
        self._holes[r] = hole
        return hole

    # ------------------------------------------------------------------
    # What moves
    # ------------------------------------------------------------------

    def _new_cloud(self, anywhere: bool = False) -> List:
        rng = self.rng
        parts = [(rng.uniform(-10, 10), rng.uniform(-2, 2), rng.uniform(6, 14), rng.uniform(3, 6)) for _ in range(rng.randint(3, 5))]
        x = rng.uniform(-30, LOW_W) if anywhere else (-30 if self.c.wind >= 0 else LOW_W + 30)
        return [x, rng.uniform(6, 34), parts, rng.uniform(1.5, 4.0)]

    def _new_drop(self, anywhere: bool = False) -> List[float]:
        return [self.rng.uniform(-20, LOW_W + 20), self.rng.uniform(-LOW_H, LOW_H) if anywhere else self.rng.uniform(-30, 0),
                self.rng.uniform(170, 230)]

    def _new_flake(self, anywhere: bool = False) -> List[float]:
        return [self.rng.uniform(-10, LOW_W + 10), self.rng.uniform(0, WATER_Y) if anywhere else -2,
                self.rng.uniform(8, 18), self.rng.uniform(0, 6.28)]

    def add_splash(self, x: float, strength: float) -> None:
        """Water thrown up where something hits it (strength 0 to 1)."""
        n = int(4 + 18 * strength)
        for _ in range(n):
            self.splashes.append([x + self.rng.uniform(-1.5, 1.5), WATER_Y - 1, self.rng.uniform(-24, 24) * (0.4 + strength),
                                  -self.rng.uniform(20, 70) * (0.4 + strength), 1.0])
        self.add_ring(x, 2 + 5 * strength)

    def add_drops(self, x: float, y: float, n: int = 3) -> None:
        for _ in range(n):
            self.splashes.append([x, y, self.rng.uniform(-14, 14), -self.rng.uniform(10, 30), 0.6])

    def add_ring(self, x: float, size: float = 3.0) -> None:
        self.rings.append([x, 0.0, size])

    def add_puff(self, x: float, y: float) -> None:
        """A puff of mud off the bottom, where a hook digs in."""
        for _ in range(7):
            self.puffs.append([x + self.rng.uniform(-1, 1), y, self.rng.uniform(-9, 9), -self.rng.uniform(3, 12),
                               self.rng.uniform(0.6, 1.3)])

    def add_bubble(self, x: float, y: float) -> None:
        for k in range(self.rng.randint(1, 3)):
            self.bubbles.append([x + self.rng.uniform(-1, 1), y - k * 2, self.rng.uniform(8, 14)])

    def update(self, dt: float) -> List[str]:
        """Move what moves; returns the sounds to play ("thunder")."""
        sounds: List[str] = []
        self.t += dt
        rng = self.rng
        c = self.c
        # The duck paddles to and fro over the far side; the heron looks about
        self.duck_x += self.duck_dir * 2.6 * dt
        if self.duck_x < 196 or self.duck_x > 288:
            self.duck_dir *= -1
            self.duck_x = min(max(self.duck_x, 196), 288)
        if rng.random() < dt * 0.6:
            self.add_ring(self.duck_x - self.duck_dir * 5, 2)
        self._heron_t -= dt
        if self._heron_t <= 0:
            self.heron_face *= -1
            self._heron_t = rng.uniform(4, 12)
        for cl in self.clouds:
            cl[0] += (c.wind * 6 + 1.0) * cl[3] * dt * (1 if c.wind >= 0 else -1)
        self.clouds = [cl for cl in self.clouds if -40 < cl[0] < LOW_W + 40]
        while len(self.clouds) < int(1 + 6 * c.clouds + 3 * c.storm):
            self.clouds.append(self._new_cloud())
        for p in self.silt:
            p[2] += dt
            p[0] += math.sin(p[2] * 0.5) * 1.2 * dt + 0.6 * dt
            p[1] += math.cos(p[2] * 0.7) * 0.8 * dt
            if p[0] > LOW_W:
                p[0] = BANK_EDGE
        for i in range(len(self.shafts)):
            self.shafts[i] = (self.shafts[i] + 1.8 * dt) % (LOW_W + 40)
        for f in self.fireflies:
            f[2] += dt
            f[0] += math.sin(f[2] * 0.9) * 4 * dt
            f[1] += math.cos(f[2] * 1.3) * 3 * dt
        for sp in self.splashes:
            sp[0] += sp[2] * dt
            sp[1] += sp[3] * dt
            sp[3] += 180 * dt
            sp[4] -= dt * 1.4
        self.splashes = [s for s in self.splashes if s[4] > 0 and not (s[1] > WATER_Y + 1 and s[3] > 0)]
        for r in self.rings:
            r[1] += dt
        self.rings = [r for r in self.rings if r[1] < 1.2]
        for b in self.bubbles:
            b[1] -= b[2] * dt
            b[0] += math.sin(b[1] * 0.8) * 0.3
            if b[1] <= WATER_Y + 1:
                self.add_ring(b[0], 1.2)
        self.bubbles = [b for b in self.bubbles if b[1] > WATER_Y + 1]
        for m in self.puffs:
            m[0] += m[2] * dt
            m[1] += m[3] * dt
            m[2] *= 1 - 2.5 * dt
            m[3] = m[3] * (1 - 2.5 * dt) + 2 * dt
            m[4] -= dt
        self.puffs = [m for m in self.puffs if m[4] > 0]
        # Rain and snow
        slant = c.wind * 40
        for d in self.drops:
            d[1] += d[2] * dt
            d[0] += slant * dt
            if d[1] >= WATER_Y:
                if d[0] > BANK_EDGE and rng.random() < 0.6:
                    self.rings.append([d[0], 0.4, 1.4])
                d[:] = self._new_drop()
        for f in self.flakes:
            f[3] += dt
            f[1] += f[2] * dt
            f[0] += (math.sin(f[3] * 1.5) * 6 + c.wind * 14) * dt
            if f[1] >= WATER_Y + 1:
                f[:] = self._new_flake()
        # Lightning, and its thunder
        self.flash = 0.0
        if c.storm >= 0.45:
            self._next_strike -= dt
            if self._next_strike <= 0:
                self._next_strike = rng.uniform(7, 16) / c.storm
                self._flickers = [0.0] + [rng.uniform(0.08, 0.35) for _ in range(rng.randint(0, 2))]
                self._thunder_in = rng.uniform(0.6, 2.4)
        if self._flickers:
            self._flickers = [f - dt for f in self._flickers]
            for f in self._flickers:
                if -0.09 < f <= 0:
                    self.flash = max(self.flash, 1 + f / 0.09)
            self._flickers = [f for f in self._flickers if f > -0.09]
        if self._thunder_in is not None:
            self._thunder_in -= dt
            if self._thunder_in <= 0:
                self._thunder_in = None
                sounds.append("thunder")
        return sounds

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _draw_sky(self, frame: pygame.Surface) -> None:
        frame.blit(self.sky, (0, 0))
        if self.night > 0.2 and self.c.clouds < 0.8:
            for x, y, ph in self.stars:
                tw = 0.5 + 0.5 * math.sin(self.t * 2.2 + ph)
                a = self.night * (1 - self.c.clouds) * (0.4 + 0.6 * tw)
                frame.set_at((x, y), _mix(self.sky_top, (236, 236, 220), a))
        light = _mix(_mix(self.sky_low, (255, 255, 255), 0.35), (60, 64, 76), 0.6 * self.night + 0.3 * self.c.storm)
        shade = _shade(light, 0.84)
        for x, y, parts, _ in self.clouds:
            for dx, dy, w, h in parts:
                pygame.draw.ellipse(frame, shade, (x + dx - w / 2, y + dy - h / 2 + 1, w, h))
            for dx, dy, w, h in parts:
                pygame.draw.ellipse(frame, light, (x + dx - w / 2, y + dy - h / 2 - 0.5, w, h * 0.8))

    def _draw_reeds(self, s: pygame.Surface) -> None:
        light, dark = _REEDS[self.season]
        for x, h, ph, head in self.reeds:
            sway = math.sin(self.t * 1.1 + ph) * 0.9 + self.c.wind * 1.5
            for k in range(int(h)):
                f = k / h
                _px(s, x + sway * f * f, WATER_Y + 2 - k, light if k % 3 else dark)
            if head:
                tx = x + sway
                _px(s, tx, WATER_Y + 2 - h, (98, 64, 40))
                _px(s, tx, WATER_Y + 3 - h, (98, 64, 40))

    def _draw_weeds(self, s: pygame.Surface) -> None:
        col = _WEED[self.season]
        for x, h, ph in self.weeds:
            base = bottom_y(x)
            for k in range(int(h)):
                f = k / h
                sway = math.sin(self.t * 1.3 + ph + k * 0.3) * f * 1.6
                _px(s, x + sway, base - k, col if k % 4 else _shade(col, 1.2))

    @staticmethod
    def _draw_arm(s: pygame.Surface, shoulder: Tuple[float, float], hand: Tuple[float, float],
                  upper: float, fore: float, shade: float) -> None:
        """An arm from the shoulder to a hand on the rod, its elbow bent downwards (as the
        woodhacking's: found from the two lengths; a hand beyond reach stretches it straight)."""
        sh = pygame.Vector2(shoulder)
        h = pygame.Vector2(hand)
        d = h - sh
        dist = d.length()
        if dist < 1e-6:
            elbow = sh + pygame.Vector2(0, upper)
        elif dist >= upper + fore:
            elbow = sh + d * (upper / (upper + fore))
        else:
            cos_turn = (upper * upper + dist * dist - fore * fore) / (2 * upper * dist)
            turn = math.degrees(math.acos(max(-1.0, min(1.0, cos_turn))))
            one = sh + d.normalize().rotate(turn) * upper
            two = sh + d.normalize().rotate(-turn) * upper
            elbow = one if one.y > two.y else two

        def col(c):
            return tuple(round(v * shade) for v in c)

        # A sleeve two pixels thick, dark along its underside, then the hand
        for a, b in ((sh, elbow), (elbow, h)):
            pygame.draw.line(s, col(_ARM_OUTLINE), a + (0, 1), b + (0, 1), 1)
            pygame.draw.line(s, col(_SLEEVE), a, b, 1)
        _px(s, sh.x, sh.y - 1, col(_SLEEVE_LIGHT))
        _px(s, h.x, h.y, col(_SKIN))

    def _draw_player(self, s: pygame.Surface, v: PondView) -> List[Tuple[float, float]]:
        """The far arm, the legs, the leaning upper body, the rod in the fist, then the near arm."""
        theta = v.rod_theta
        pts = rod_points(theta, v.rod_bend)
        fist = pygame.Vector2(pts[0])
        far, near = _shoulders(theta)
        a = math.radians(theta)
        along = pygame.Vector2(math.sin(a), -math.cos(a))
        # The near hand takes the handle behind the fist, as far down it as it can reach
        lo, hi = _NEAR_GRIP
        grips = [fist - along * (lo + (hi - lo) * i / 6) for i in range(7)]
        reach = _NEAR_UPPER + _NEAR_FORE
        near_hand = next((g for g in reversed(grips) if g.distance_to(near) <= reach),
                         min(grips, key=lambda g: g.distance_to(near)))
        # As the woodhacking's axe: the rod and the far arm behind the body, the near arm over it
        butt = fist - along * (hi + 2)
        pygame.draw.line(s, (92, 64, 40), butt, fist, 1)
        for i, (p, q) in enumerate(zip(pts, pts[1:])):
            pygame.draw.line(s, (120, 86, 52) if i < 4 else (164, 134, 88), p, q, 1)
        self._draw_arm(s, far, fist, _UPPER, _FORE, 0.82)
        lean = player_lean(theta)
        w = self.player.get_width()
        s.blit(self.player, (_PLAYER_LEFT, _PLAYER_TOP + _HIP_ROW), (0, _HIP_ROW, w, _PLAYER_H - _HIP_ROW))
        s.blit(self.player, (_PLAYER_LEFT + lean, _PLAYER_TOP), (0, 0, w, _HIP_ROW))
        self._draw_arm(s, near, near_hand, _NEAR_UPPER, _NEAR_FORE, 1.0)
        return pts

    def _draw_fish(self, s: pygame.Surface, fish: Fish) -> None:
        img = fish_sprite(fish.species, fish.length, fish_frame(fish))
        if fish.facing < 0:
            img = pygame.transform.flip(img, True, False)
        if fish.tired:
            img = pygame.transform.flip(img, False, True)
        if fish.angle:
            img = pygame.transform.rotate(img, fish.angle)
        s.blit(img, img.get_rect(center=(round(fish.x), round(fish.y))))

    def _draw_line(self, s: pygame.Surface, pts: List[Tuple[float, float]], tension: float, under: bool) -> None:
        """The line's stretches under the water (drawn before the dark, so it fades into it) or over it."""
        colour = (214, 214, 196)
        if tension > 0.8:
            colour = _mix(colour, (255, 236, 150), (tension - 0.8) / 0.3)
        for p, q in zip(pts, pts[1:]):
            wet = p[1] > WATER_Y + 0.5 and q[1] > WATER_Y + 0.5
            if wet == under:
                pygame.draw.line(s, (150, 176, 172) if wet else colour, p, q, 1)

    def _draw_hook(self, s: pygame.Surface, v: PondView) -> None:
        if v.hook is None:
            return
        x, y = v.hook
        _px(s, x, y, (180, 184, 186))
        _px(s, x, y + 1, (150, 154, 156))
        _px(s, x - 1, y + 1, (150, 154, 156))
        _px(s, x - 1, y, (150, 154, 156))
        if v.worm:
            w = math.sin(self.t * 6)
            _px(s, x + 1, y + 1 + w * 0.5, (220, 120, 120))
            _px(s, x + 1, y + 2, (200, 96, 104))
            _px(s, x, y + 2 + w * 0.6, (220, 120, 120))

    def _draw_float(self, s: pygame.Surface, v: PondView) -> None:
        if v.float_at is None:
            return
        x, y = v.float_at
        if v.float_under:
            _px(s, x, y, (150, 70, 60))
            _px(s, x, y + 1, (160, 160, 150))
            return
        light = self.light
        red = tuple(min(255, round(c * max(l, 170) / 255)) for c, l in zip((222, 64, 44), light))
        white = tuple(min(255, round(c * max(l, 170) / 255)) for c, l in zip((238, 232, 214), light))
        _px(s, x, y - 2, red)
        _px(s, x, y - 1, red)
        _px(s, x, y, white)

    def draw(self, v: PondView) -> pygame.Surface:
        """The scene, SCENE_W x SCENE_H."""
        frame = pygame.Surface((LOW_W, LOW_H))
        self._draw_sky(frame)
        world = pygame.Surface((LOW_W, LOW_H), pygame.SRCALPHA)
        world.blit(self.backdrop, (0, 0))
        # The heron and the duck
        heron = self.heron_img if self.heron_face < 0 else pygame.transform.flip(self.heron_img, True, False)
        world.blit(heron, _HERON_POS)
        duck = self.duck_img if self.duck_dir > 0 else pygame.transform.flip(self.duck_img, True, False)
        world.blit(duck, (round(self.duck_x) - 5, WATER_Y - 4 + round(math.sin(self.t * 2.0) * 0.4)))
        # Under the water
        world.blit(self.under, (0, WATER_Y + 1), (0, WATER_Y + 1, LOW_W, LOW_H - WATER_Y - 1))
        self._draw_weeds(world)
        for x, y, ph in self.silt:
            if y > WATER_Y + 1:
                _px(world, x, y, (128, 160, 150))
        for b in self.bubbles:
            _px(world, b[0], b[1], (178, 218, 216))
        for x, y, _vx, _vy, life in self.puffs:
            _px(world, x, y, _mix((70, 76, 60), (128, 120, 92), min(1.0, life)))
        under_fish = [f for f in v.fish if f.y > WATER_Y + 1 and not f.above_water]
        for fish in under_fish:
            self._draw_fish(world, fish)
        if v.float_under:
            self._draw_float(world, v)
        self._draw_hook(world, v)
        if v.line:
            self._draw_line(world, v.line, v.tension, under=True)
        # The dark, with the light round the bait
        dark = self.darkness.copy()
        if v.focus is not None:
            fx, fy, fr = v.focus
            hole = self._hole(max(4, int(fr)))
            dark.blit(hole, hole.get_rect(center=(round(fx), round(fy) - WATER_Y - 1)), special_flags=pygame.BLEND_RGBA_SUB)
        world.blit(dark, (0, WATER_Y + 1))
        # Shafts of light under the surface, by day
        day = (1 - self.night) * (1 - 0.7 * self.c.clouds) * (1 - 0.5 * self.c.rain)
        if day > 0.1:
            world.blit(self._shaft_layer(day), (0, _SHAFT_TOP))
        # The surface, rippling, and the rings on it
        for x in range(BANK_EDGE - 1, LOW_W):
            off = math.sin(x * 0.35 + self.t * 1.7) * 0.5 + math.sin(x * 0.13 - self.t * 1.1) * 0.5
            world.set_at((x, WATER_Y + round(off * 0.8)), (198, 228, 222))
            world.set_at((x, WATER_Y + 1), (116, 168, 168))
        for x, age, size in self.rings:
            r = size * min(1.0, age * 2.5)
            a = 1 - age / 1.2
            col = _mix((116, 168, 168), (232, 244, 240), a)
            for dx in (-r, r):
                _px(world, x + dx, WATER_Y, col)
            if r > 1.5:
                _px(world, x - r * 0.5, WATER_Y - 1, col)
                _px(world, x + r * 0.5, WATER_Y - 1, col)
        # Over the water: the player, rod, reeds, fish in the air, the net
        self._draw_reeds(world)
        rod = self._draw_player(world, v)
        if v.sweet_theta is not None:
            # The rod tip's path, dotted, and where to let go on it, bright
            for deg in range(-84, 72, 6):
                tx, ty = rod_points(deg, 0.0, 4)[-1]
                _px(world, tx, ty - 2, (232, 220, 180))
            mx, my = rod_points(v.sweet_theta, 0.0, 4)[-1]
            my -= 2
            glow = 0.5 + 0.5 * math.sin(self.t * 8)
            for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1), (2, 0), (-2, 0), (0, 2), (0, -2)):
                _px(world, mx + dx, my + dy, _mix((236, 176, 60), (255, 246, 190), glow if (dx, dy) == (0, 0) else 0.3))
        for fish in v.fish:
            if fish.above_water or fish.y <= WATER_Y + 1:
                self._draw_fish(world, fish)
        if v.net is not None:
            nx, ny = v.net
            gx, gy = grip_at(v.rod_theta)
            pygame.draw.line(world, (110, 80, 50), (gx - 2, gy + 2), (nx, ny), 1)
            pygame.draw.ellipse(world, (130, 104, 70), (nx - 4, ny - 1, 8, 4), 1)
            for k in range(-3, 4, 2):
                _px(world, nx + k, ny + 3, (170, 160, 130))
        if v.line:
            self._draw_line(world, v.line, v.tension, under=False)
        for sp in self.splashes:
            _px(world, sp[0], sp[1], (220, 238, 238))
        # The light of the hour on all but the sky
        if self.lit:
            world.fill(self.light, special_flags=pygame.BLEND_RGB_MULT)
        frame.blit(world, (0, 0))

        # Not lit: the float, eyes glinting at the edge of the light, fireflies, weather
        if not v.float_under:
            self._draw_float(frame, v)
        if v.focus is not None:
            fx, fy, fr = v.focus
            for fish in v.fish:
                if fish.above_water or fish.y < WATER_Y + 4:
                    continue
                d = math.hypot(fish.x - fx, fish.y - fy)
                if fr * 0.9 < d < fr + 26:
                    blink = math.sin(self.t * 1.7 + fish.cm) > -0.6
                    if blink:
                        ex, ey = fish.mouth[0] - fish.facing * max(1, fish.length * 0.13), fish.y - 1
                        k = 1 - (d - fr * 0.9) / 30
                        _px(frame, ex, ey, _mix(_DARK, (226, 214, 150), 0.25 + 0.6 * k))
        if self.night > 0.5 and self.season in (0, 1, 2) and self.c.rain < 0.2:
            for x, y, ph in self.fireflies:
                if math.sin(self.t * 2.0 + ph * 3) > 0.3:
                    _px(frame, x, y, (214, 236, 120))
        if self.drops:
            col = _mix((150, 170, 186), (210, 220, 232), 1 - self.night)
            for x, y, _sp in self.drops:
                if y < WATER_Y:
                    pygame.draw.line(frame, col, (x, y), (x - self.c.wind * 1.2, y - 3))
        for x, y, _s, _p in self.flakes:
            _px(frame, x, y, (236, 240, 244))
        if self.c.fog > 0.05:
            veil = pygame.Surface((LOW_W, LOW_H), pygame.SRCALPHA)
            fog = _mix((210, 216, 220), (40, 46, 60), self.night)
            veil.fill((*fog, round(120 * self.c.fog)), (0, 0, LOW_W, WATER_Y + 2))
            for k in range(4):
                x = (self.t * (3 + k) + k * 90) % (LOW_W + 120) - 60
                pygame.draw.ellipse(veil, (*fog, round(70 * self.c.fog)), (x, WATER_Y - 12 + k * 3, 90, 10))
            frame.blit(veil, (0, 0))
        if self.flash > 0:
            frame.fill((round(150 * self.flash),) * 3, special_flags=pygame.BLEND_RGB_ADD)
        return pygame.transform.scale(frame, (SCENE_W, SCENE_H))
