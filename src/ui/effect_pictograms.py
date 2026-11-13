"""Pictograms for what is acting on the player: the meals' effects and the weather slowing the walk.

Each is drawn with pygame's shapes on a square canvas `SUPERSAMPLE` times the size
asked for, in coordinates of a 100 by 100 box, and smoothed down, so the edges are
soft without any picture files. Flat colours with an ink outline, like the game's
other small icons:

- Strong Hand: a woodcutter's axe
- Steady Hand: a fishhook under its float
- Well Fed: a steaming bowl of stew
- Light Step: a winged boot with speed lines
- the weather: a rain cloud, a snowflake, or a boot sunk in mud

They are toned down `MUTED` of the way towards grey, so they sit with the game's
parchment and ink rather than standing out from it.

`pictogram(key, size)` gives the picture, made once per key and size.
"""

import math
from typing import Callable, Dict, List, Sequence, Tuple

import pygame

SUPERSAMPLE = 4
#: How far the colours are taken towards grey
MUTED = 0.35

Point = Tuple[float, float]

INK = (52, 36, 24)
WOOD = (166, 110, 58)
WOOD_DARK = (112, 70, 36)
STEEL = (170, 178, 186)
STEEL_LIGHT = (226, 232, 236)
STEW = (176, 96, 42)
STEW_LIGHT = (214, 140, 70)
BOWL = (132, 80, 40)
BOWL_LIGHT = (170, 112, 62)
STEAM = (150, 136, 120)
LEATHER = (128, 76, 40)
LEATHER_LIGHT = (168, 112, 64)
FEATHER = (246, 236, 206)
FLOAT_RED = (196, 52, 40)
FLOAT_WHITE = (244, 240, 230)
CLOUD = (198, 204, 214)
CLOUD_SHADE = (160, 168, 182)
DROP = (64, 118, 196)
ICE = (92, 140, 200)
ICE_DARK = (40, 70, 120)
MUD = (112, 80, 48)
MUD_DARK = (78, 54, 30)


class _Pen:
    """Draws in a 100 by 100 box onto a surface of any size."""

    def __init__(self, surf: pygame.Surface) -> None:
        self.surf = surf
        self.k = surf.get_width() / 100.0

    def p(self, point: Point) -> Tuple[int, int]:
        return round(point[0] * self.k), round(point[1] * self.k)

    def w(self, width: float) -> int:
        return max(1, round(width * self.k))

    def polygon(self, colour, points: Sequence[Point], outline: float = 0.0) -> None:
        pts = [self.p(q) for q in points]
        if outline:
            # The outline as a fatter polygon behind: its corners stay round
            self.polyline(INK, list(points) + [points[0]], outline * 2)
        pygame.draw.polygon(self.surf, colour, pts)

    def polyline(self, colour, points: Sequence[Point], width: float) -> None:
        """A thick line through the points, with round joints and ends."""
        w = self.w(width)
        pts = [self.p(q) for q in points]
        for a, b in zip(pts, pts[1:]):
            pygame.draw.line(self.surf, colour, a, b, w)
        for q in pts:
            pygame.draw.circle(self.surf, colour, q, w / 2)

    def circle(self, colour, centre: Point, radius: float, outline: float = 0.0) -> None:
        if outline:
            pygame.draw.circle(self.surf, INK, self.p(centre), round((radius + outline) * self.k))
        pygame.draw.circle(self.surf, colour, self.p(centre), round(radius * self.k))

    def ellipse(self, colour, box: Tuple[float, float, float, float], outline: float = 0.0) -> None:
        x, y, w, h = box
        if outline:
            o = outline
            pygame.draw.ellipse(self.surf, INK, pygame.Rect(*self.p((x - o, y - o)), *self.p((w + 2 * o, h + 2 * o))))
        pygame.draw.ellipse(self.surf, colour, pygame.Rect(*self.p((x, y)), *self.p((w, h))))


def _rotated(points: Sequence[Point], degrees: float, centre: Point) -> List[Point]:
    a = math.radians(degrees)
    c, s = math.cos(a), math.sin(a)
    return [(centre[0] + x * c - y * s, centre[1] + x * s + y * c) for x, y in points]


def _arc(centre: Point, rx: float, ry: float, start: float, end: float, steps: int = 24) -> List[Point]:
    """Points along an ellipse from `start` to `end` degrees (0 to the right, 90 down)."""
    return [(centre[0] + rx * math.cos(math.radians(start + (end - start) * i / steps)),
             centre[1] + ry * math.sin(math.radians(start + (end - start) * i / steps)))
            for i in range(steps + 1)]


# ── The pictures ─────────────────────────────────────────────────────────────

def _axe(pen: _Pen) -> None:
    """Strong Hand: an axe, the handle slanting up to the right and the blade at its top."""
    centre, turn, k = (52.0, 64.0), 32.0, 0.8
    def place(points):
        return _rotated([(x * k, y * k) for x, y in points], turn, centre)
    handle = place([(0, 44), (0, -40)])
    pen.polyline(INK, handle, 15)
    pen.polyline(WOOD, handle, 8)
    pen.polyline(WOOD_DARK, place([(0, 30), (0, 42)]), 8)   # the grip
    # The head: a block round the handle and a blade flaring out to a curved edge
    edge = [(-36 + 4 * math.sin(math.radians(t)), y) for t, y in zip(range(0, 181, 30), range(-60, -11, 8))]
    head = [(7, -44), (7, -24), (-6, -24), (-18, -18)] + list(reversed(edge)) + [(-18, -52), (-6, -44)]
    pen.polygon(STEEL, place(head), outline=3.5)
    pen.polyline(STEEL_LIGHT, place([(x + 4, y) for x, y in edge[1:-1]]), 5)   # the honed edge
    pen.polyline(INK, place([(7, -44), (7, -24)]), 3)


def _hook(pen: _Pen) -> None:
    """Steady Hand: a fishhook on its line, a red and white float above it."""
    pen.polyline(INK, [(58, 0), (58, 34)], 3)
    # The float: red over white
    pen.ellipse(FLOAT_WHITE, (48, 8, 20, 26), outline=3)
    clip = pen.surf.get_clip()
    pen.surf.set_clip(pygame.Rect(0, 0, pen.surf.get_width(), pen.p((0, 21))[1]))   # the red top half only
    pen.ellipse(FLOAT_RED, (48, 8, 20, 26))
    pen.surf.set_clip(clip)
    pen.polyline(INK, [(48, 21), (68, 21)], 2.5)
    pen.polyline(INK, [(58, 4), (58, 9)], 3)
    # The hook: eye, shank, bend and point with its barb
    shank = [(58, 44), (58, 72)]
    bend = _arc((44, 72), 14, 14, 0, 180)
    point = [(30, 72), (30, 58)]
    hook = shank + bend[1:] + point[1:]
    pen.polyline(INK, hook, 11)
    pen.polyline(INK, [(30, 58), (38, 66)], 9)
    pen.circle(INK, (58, 41), 7)
    pen.polyline(STEEL, hook, 5)
    pen.polyline(STEEL, [(30, 58), (38, 66)], 4)
    pen.circle(STEEL, (58, 41), 4)
    pen.circle(INK, (58, 41), 1.8)
    pen.polyline(STEEL_LIGHT, _arc((44, 72), 14, 14, 30, 110, 8), 2)


def _bowl(pen: _Pen) -> None:
    """Well Fed: a wooden bowl of stew with steam rising off it."""
    for x, phase in ((34, 0.0), (50, 1.6), (66, 3.2)):
        steam = [(x + 5 * math.sin(phase + y / 6.0), y) for y in range(42, 5, -3)]
        pen.polyline(STEAM, steam, 4.5)
    body = _arc((50, 54), 38, 32, 0, 180)
    pen.polygon(BOWL, body, outline=3.5)
    pen.polygon(BOWL_LIGHT, _arc((50, 54), 30, 24, 20, 70, 10) + [(58, 62), (78, 56)])   # a sheen on its side
    pen.polygon(BOWL, [(36, 84), (64, 84), (60, 92), (40, 92)], outline=3)               # its foot
    pen.ellipse(STEW, (14, 46, 72, 16), outline=3.5)
    pen.circle(STEW_LIGHT, (36, 53), 4)
    pen.circle(STEW_LIGHT, (56, 51), 3.5)
    pen.circle((120, 150, 70), (66, 55), 3)        # a leaf of herbs


_BOOT = [(38, 14), (64, 14), (64, 52), (78, 58), (90, 66), (92, 78), (34, 78), (34, 60)]


def _boot(pen: _Pen, dx: float = 0.0, dy: float = 0.0, wing: bool = True) -> None:
    boot = [(x + dx, y + dy) for x, y in _BOOT]
    if wing:
        # Three broad feathers fanning back from the ankle, the top one longest
        for i, (tip_x, tip_y) in enumerate(((6, 10), (10, 24), (18, 38))):
            base = 24 + 9 * i
            feather = [(40 + dx, base - 5 + dy), (tip_x + dx, tip_y + dy), (tip_x + 8 + dx, tip_y + 9 + dy),
                       (40 + dx, base + 6 + dy)]
            pen.polygon(FEATHER, feather, outline=2.5)
    pen.polygon(LEATHER, boot, outline=3.5)
    pen.polygon(LEATHER_LIGHT, [(38 + dx, 14 + dy), (64 + dx, 14 + dy), (64 + dx, 24 + dy), (38 + dx, 24 + dy)])
    pen.polyline(INK, [(36 + dx, 24 + dy), (64 + dx, 24 + dy)], 2.5)
    pen.polygon(INK, [(32 + dx, 76 + dy), (94 + dx, 76 + dy), (94 + dx, 86 + dy), (32 + dx, 86 + dy)])
    pen.polyline(LEATHER_LIGHT, [(66 + dx, 60 + dy), (84 + dx, 70 + dy)], 3)


def _winged_boot(pen: _Pen) -> None:
    """Light Step: a boot with a wing at its ankle and lines of speed behind it."""
    for y, x0, x1 in ((58, 2, 24), (68, 8, 28), (78, 2, 22)):
        pen.polyline(INK, [(x0, y), (x1, y)], 4.5)
    _boot(pen, dx=4)


def _rain(pen: _Pen) -> None:
    """Rain slowing the walk: a grey cloud and slanting drops."""
    lumps = ((32, 44, 16), (54, 34, 21), (74, 46, 15), (50, 50, 16))
    for x, y, r in lumps:
        pen.circle(INK, (x, y), r + 3.5)
    pen.polygon(INK, [(16, 46), (88, 46), (88, 64), (16, 64)])
    for x, y, r in lumps:
        pen.circle(CLOUD, (x, y), r)
    pen.polygon(CLOUD, [(18, 46), (86, 46), (86, 60), (18, 60)])
    pen.polyline(CLOUD_SHADE, [(22, 56), (82, 56)], 4)
    for x in (30, 50, 70):
        pen.polyline(INK, [(x, 72), (x - 7, 92)], 9)
        pen.polyline(DROP, [(x, 72), (x - 7, 92)], 4.5)


def _snowflake(pen: _Pen) -> None:
    """Snow slowing the walk: a six-armed snowflake."""
    centre = (50.0, 50.0)
    arms = []
    for k in range(6):
        arm = [(0, 0), (0, -40)]
        twig_l = [(0, -24), (-12, -36)]
        twig_r = [(0, -24), (12, -36)]
        arms.append([_rotated(part, 60 * k, centre) for part in (arm, twig_l, twig_r)])
    for parts in arms:
        for part in parts:
            pen.polyline(ICE_DARK, part, 10)
    for parts in arms:
        for part in parts:
            pen.polyline(ICE, part, 5)
    pen.circle(ICE_DARK, centre, 8)
    pen.circle(FEATHER, centre, 4.5)


def _mud(pen: _Pen) -> None:
    """Mud slowing the walk: a boot sunk to the ankle in a brown puddle, splashing."""
    _boot(pen, dx=-8, dy=-6, wing=False)
    pen.ellipse(MUD, (4, 58, 92, 34), outline=3.5)
    pen.ellipse(MUD_DARK, (22, 66, 52, 12))
    pen.polygon(LEATHER, [(30, 46), (56, 46), (58, 70), (28, 70)])   # the shaft going under
    pen.polyline(INK, [(28, 46), (28, 70)], 3.5)
    pen.polyline(INK, [(58, 46), (58, 70)], 3.5)
    pen.ellipse(MUD, (20, 64, 46, 10))
    for x, y, r in ((14, 50, 3.5), (74, 46, 4.5), (84, 54, 3)):
        pen.circle(MUD, (x, y), r, outline=2)


PICTOGRAMS: Dict[str, Callable[[_Pen], None]] = {
    "strong_hand": _axe,
    "steady_hand": _hook,
    "well_fed": _bowl,
    "light_step": _winged_boot,
    "rain": _rain,
    "snow": _snowflake,
    "mud": _mud,
}

_cache: Dict[Tuple[str, int], pygame.Surface] = {}


def pictogram(key: str, size: int) -> pygame.Surface:
    """The pictogram for `key` (a meal's effect or a weather hindrance), `size` pixels square."""
    cached = _cache.get((key, size))
    if cached is None:
        big = pygame.Surface((size * SUPERSAMPLE, size * SUPERSAMPLE), pygame.SRCALPHA)
        PICTOGRAMS[key](_Pen(big))
        cached = pygame.transform.smoothscale(big, (size, size))
        grey = pygame.transform.grayscale(cached)
        grey.set_alpha(round(255 * MUTED))
        cached.blit(grey, (0, 0))
        _cache[(key, size)] = cached
    return cached
