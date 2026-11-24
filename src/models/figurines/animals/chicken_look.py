"""How a chicken looks: painted pixel by pixel from modular parts, in one of its colours.

A frame is put together from parts (the body, a tail, the legs, a head), each a
small grid of characters, one per pixel, drawn on a FRAME x FRAME grid and
laid onto a FRAME_W x FRAME_H canvas at an offset, LEFT_ROOM in from its left
edge, so a pecking head can reach down to the ground in front of the body. Later parts are painted over earlier ones; '.' is see-through. A walk
frame is the same head and body with other legs and the head a pixel forward,
a pecking frame has the whole chicken but its legs tipped forward, the beak to
the ground.

Frames face left; the right-facing ones are mirrored. A chicken's look is a
head, a tail and a colour (random_chicken, the colours by COLOUR_ODDS). The
heads, tails and colours are the iterations tried in
build_tools/Sprite_Manager/chicken_painter.py, which previews them.

Only compose() and the frames need pygame.
"""

import colorsys
import zlib

FRAME = 16  # the grid the parts are drawn on, pixels each way
LEFT_ROOM = 4  # the canvas's room in front of the grid, for the head bent down to peck
FRAME_W, FRAME_H = FRAME + LEFT_ROOM + 2, FRAME  # the frame's size; its feet in the middle

PALETTE = {
    "O": (92, 52, 30),     # outline, dark brown
    "H": (255, 238, 204),  # feathers, highlight
    "W": (246, 212, 158),  # feathers
    "w": (230, 178, 118),  # wing
    "s": (196, 136, 82),   # feathers, shade
    "R": (214, 48, 34),    # comb
    "d": (172, 36, 28),    # comb's base, in the shade
    "r": (150, 28, 22),    # wattle
    "Y": (250, 196, 50),   # beak
    "y": (214, 138, 30),   # beak's underside
    "E": (28, 18, 16),     # eye
    "F": (232, 150, 40),   # legs and feet
}


class Part:
    """A grid of pixels to be laid at (x, y) on the frame. `home` is where it
    was first put: patterns go by it, so they move with the part."""

    def __init__(self, rows, x=0, y=0, home=None):
        width = len(rows[0])
        for row in rows:
            if len(row) != width:
                raise ValueError(f"ragged part row {row!r}")
            for c in row:
                if c != "." and c not in PALETTE:
                    raise ValueError(f"unknown colour {c!r} in {row!r}")
        self.rows = rows
        self.x = x
        self.y = y
        self.home = home or (x, y)

    def at(self, dx=0, dy=0):
        """The same part moved by (dx, dy)."""
        return Part(self.rows, self.x + dx, self.y + dy, self.home)


# The body from the back line down to the belly, without its tail; the tail
# and head are painted over it, the legs under it. Its back line runs on to
# the front, under the head, for when the head is lowered to peck.
BODY = Part([
    "....OOOOOOOOO...",
    "...OWWWWWWWWWO..",
    "...OWHsssssWWsO.",
    "...OWHswwwwsssO.",
    "...OWWWsswwssO..",
    "....OWWWWsssO...",
    ".....OOOOOOO....",
], y=7)

# Tails, over the body's rear (columns 10 to 15): the iterations tried, all
# kept as possible versions to build a chicken from. "short" is the one
# chosen for now (TAIL).
TAILS = {
    # A short upright tuft.
    "short": Part([
        "..OO.",
        ".OWWO",
        "OOWsO",
        "WWsO.",
        "WWsO.",
    ], x=11, y=5),
    # Tall and pointed, standing straight up.
    "tall": Part([
        "...O.",
        "..OWO",
        ".OWsO",
        ".OWsO",
        "OOWsO",
        "WWsO.",
        "WWsO.",
    ], x=11, y=3),
    # A rounded fan, lit on top.
    "fan": Part([
        "..OO.",
        ".OHWO",
        "OWWsO",
        "OWWsO",
        "WWsO.",
        "WWsO.",
    ], x=11, y=4),
    # A big plume, taller than "tall" and wider than "fan", the wing's
    # feathers down its middle.
    "plume": Part([
        "...OO.",
        "..OHWO",
        ".OHWsO",
        ".OWWsO",
        "OWWwsO",
        "OWWwsO",
        "OWWsO.",
        ".WWsO.",
        ".WWsO.",
    ], x=10, y=1),
    # A feather curling over at the top, like a cock's sickle.
    "sickle": Part([
        ".OOO.",
        "OWWsO",
        "O.OsO",
        "..OsO",
        "OOWsO",
        "WWsO.",
        "WWsO.",
    ], x=11, y=3),
    # Low, swept back rather than up, as a hen carries it.
    "swept": Part([
        "...OO",
        "OOOWO",
        "WWWsO",
        "WWsO.",
    ], x=11, y=6),
}

TAIL = "short"

LEGS = {
    "stand": Part([
        "......F..F......",
        ".....FF.FF......",
    ], y=14),
    # Walking: the front leg forward, then the back leg back
    "front": Part([
        ".....F...F......",
        "....FF..FF......",
    ], y=14),
    "back": Part([
        "......F...F.....",
        ".....FF..FF.....",
    ], y=14),
}

# Heads, each with its neck and breast down to the body's top. The ones
# kept as possible versions; "F" is the one chosen for now.
HEADS = {
    # Square head, comb of two lobes on a shaded base, wattle under the beak.
    "A": Part([
        "....RR.R..",
        "...RRRRRR.",
        "...OddddO.",
        "..OHHHHWWO",
        ".OHHEHHWWO",
        "YYYHHHHWWO",
        ".yrOHHWWWO",
        "..rOWWWWW.",
        "...OWWHH..",
    ]),
    # Square head, comb of three spikes.
    "B": Part([
        "...R.R.R..",
        "...RRRRR..",
        "..OdddddO.",
        ".OHHHHHWWO",
        ".OHEHHHWWO",
        "YYHHHHHWWO",
        "yyOrHHWWWO",
        "..OrWWWWW.",
        "...OWWHH..",
    ]),
    # Round head, domed comb, a stubby one-pixel beak.
    "D": Part([
        "....RRR...",
        "...RRRRR..",
        "..ORdddRO.",
        ".OHHHHHWWO",
        "OYHEHHHWWO",
        "OyHHHHHWWO",
        ".OrHHHWWW.",
        "..rOWWWWW.",
    ], y=1),
    # Round head, domed comb, a two-pixel beak.
    "E": Part([
        "....RRR...",
        "...RRRRR..",
        "..ORdddRO.",
        ".OHHHHHWWO",
        "YYHEHHHWWO",
        "yOHHHHHWWO",
        ".OrHHHWWW.",
        "..rOWWWWW.",
    ], y=1),
    # Round head, notched comb of two lobes, a two-pixel beak.
    "F": Part([
        "...RR.R...",
        "...RRRRR..",
        "..ORdddRO.",
        ".OHHHHHWWO",
        "YYHEHHHWWO",
        "yyOHHHHWWO",
        ".OrHHHWWW.",
        "..rOWWWWW.",
    ], y=1),
}

HEAD = "F"


FEATHERS = "HWws"  # the letters a breed's pattern may paint over

# How light each feather letter is, for the patterns that make their own colour.
FEATHER_LIGHT = {"H": 1.0, "W": 0.9, "w": 0.78, "s": 0.64}


def _barred(variant):
    """Dark bars across the feathers, every other row (Plymouth Rock)."""
    def paint(x, y, c, colour):
        return variant["bar"] if c in FEATHERS and y % 2 == 0 else colour
    return paint


def _speckled(variant, every=6):
    """A light speck on one feather pixel in `every` (Sussex)."""
    def paint(x, y, c, colour):
        if c in FEATHERS and zlib.crc32(f"{x},{y}".encode()) % every == 0:
            return variant["speck"]
        return colour
    return paint


def _rainbow(variant):
    """The feathers through the hues, front to back."""
    def paint(x, y, c, colour):
        if c not in FEATHERS:
            return colour
        r, g, b = colorsys.hsv_to_rgb(((x + y * 0.5) / 14) % 1.0, 0.45, FEATHER_LIGHT[c])
        return (round(r * 255), round(g * 255), round(b * 255))
    return paint


def _calico(variant):
    """Patches of three colours, in 3 x 3 blocks."""
    patches = variant["patches"]
    def paint(x, y, c, colour):
        if c not in FEATHERS:
            return colour
        base = patches[zlib.crc32(f"{x // 3},{y // 3}".encode()) % len(patches)]
        return tuple(round(v * FEATHER_LIGHT[c]) for v in base)
    return paint


PATTERNS = {"barred": _barred, "speckled": _speckled, "rainbow": _rainbow,
            "calico": _calico}


def _feathers(h, w, wing, shade, outline):
    return {"H": h, "W": w, "w": wing, "s": shade, "O": outline}


# Colour variants: palette letters replaced, and perhaps a pattern. "buff" is
# PALETTE itself; the first ones are real breeds' colours, the rest for fun.
COLOURS = {
    "buff": {},
    "white": _feathers((255, 255, 255), (238, 236, 230), (214, 210, 202),
                       (180, 174, 168), (84, 76, 74)),
    "black": {**_feathers((92, 104, 112), (52, 56, 64), (38, 62, 58),
                          (28, 30, 36), (14, 12, 16)),
              "E": (214, 140, 40), "F": (70, 68, 72)},
    "red": _feathers((222, 134, 82), (182, 84, 40), (150, 62, 30),
                     (118, 44, 22), (60, 26, 14)),
    "blue": _feathers((204, 214, 224), (152, 164, 178), (120, 134, 150),
                      (96, 106, 122), (48, 52, 64)),
    "barred": {**_feathers((236, 236, 236), (214, 214, 214), (190, 190, 190),
                           (160, 160, 160), (52, 52, 58)),
               "pattern": "barred", "bar": (118, 120, 128)},
    "speckled": {**_feathers((208, 116, 64), (170, 78, 38), (142, 60, 30),
                             (112, 44, 22), (56, 24, 14)),
                 "pattern": "speckled", "speck": (250, 246, 236)},
    "lavender": _feathers((240, 228, 255), (210, 192, 236), (184, 162, 216),
                          (150, 126, 186), (72, 56, 96)),
    "mint": _feathers((230, 255, 240), (184, 236, 206), (150, 214, 180),
                      (112, 182, 148), (40, 86, 66)),
    "rose": _feathers((255, 226, 236), (246, 186, 206), (230, 150, 180),
                      (198, 112, 146), (100, 40, 64)),
    "golden": {**_feathers((255, 250, 190), (250, 214, 70), (226, 168, 30),
                           (184, 120, 20), (96, 56, 10)),
               "F": (250, 220, 110)},
    "midnight": {**_feathers((92, 110, 180), (52, 62, 128), (40, 46, 104),
                             (28, 32, 78), (12, 12, 32)),
                 "E": (255, 230, 120), "R": (250, 200, 60), "d": (210, 150, 40),
                 "r": (190, 120, 30)},
    "lava": {**_feathers((70, 66, 66), (44, 40, 40), (34, 30, 30), (24, 20, 20),
                         (10, 8, 8)),
             "E": (255, 140, 40), "pattern": "speckled", "speck": (255, 120, 30)},
    "ghost": {**_feathers((250, 254, 255), (224, 238, 248), (200, 220, 238),
                          (170, 196, 222), (110, 140, 176)),
              "E": (90, 150, 230), "R": (190, 220, 245), "d": (160, 196, 230),
              "r": (150, 186, 222), "F": (196, 214, 232), "Y": (230, 236, 244),
              "y": (196, 206, 222)},
    "rainbow": {"pattern": "rainbow"},
    "calico": {"pattern": "calico",
               "patches": [(255, 250, 240), (232, 140, 60), (60, 52, 50)],
               "O": (52, 34, 26)},
}

COLOUR = "buff"

# How often a chicken is born in each colour, in 10,000. The farmyard breeds
# are common, the other breeds less so, the odd colours rare, the uncanny ones
# a once-in-a-lifetime find. Heads and tails are all equally likely.
COLOUR_ODDS = {
    # common: 22 % each
    "buff": 2200, "white": 2200, "red": 2200,
    # uncommon: other real breeds, 5 to 9 %
    "black": 900, "speckled": 700, "barred": 600, "blue": 500,
    # rare: odd but still natural-looking, 1 to 2 %
    "golden": 200, "calico": 150, "lavender": 100, "rose": 100, "mint": 100,
    # very rare: 0.3 %
    "lava": 30,
    # legendary: 1 in 1,250 to 1 in 2,500
    "midnight": 8, "ghost": 8, "rainbow": 4,
}
assert sum(COLOUR_ODDS.values()) == 10_000 and set(COLOUR_ODDS) == set(COLOURS)


def random_chicken(rng):
    """(head, tail, colour) drawn for a chicken born, from a random.Random."""
    colours = list(COLOUR_ODDS)
    return (rng.choice(list(HEADS)), rng.choice(list(TAILS)),
            rng.choices(colours, weights=[COLOUR_ODDS[c] for c in colours])[0])


def palette_of(colour):
    """PALETTE with a colour variant's own colours in."""
    variant = COLOURS[colour]
    return {**PALETTE, **{k: v for k, v in variant.items() if k in PALETTE}}


# A chick's down, and how far the young are drawn towards it by their youth (1 a chick, 0 grown up)
CHICK_DOWN = (252, 246, 224)
CHICK_COMB = (238, 178, 150)
CHICK_OUTLINE = (150, 128, 100)
YOUTH_PULL = {**{c: (CHICK_DOWN, 0.9) for c in FEATHERS}, "O": (CHICK_OUTLINE, 0.55),
              "R": (CHICK_COMB, 0.7), "d": (CHICK_COMB, 0.6), "r": (CHICK_COMB, 0.6)}


def _young(colour, letter, youth):
    """A colour drawn towards the chick's by its youth."""
    if not youth or letter not in YOUTH_PULL:
        return colour
    target, pull = YOUTH_PULL[letter]
    k = youth * pull
    return tuple(round(a + (b - a) * k) for a, b in zip(colour, target))


def compose(parts, colour=COLOUR, youth=0.0):
    """Lays the parts in order onto a see-through frame, facing left, in one
    of the COLOURS; a young one's (youth 1 a chick, 0 grown up) paler."""
    import pygame
    variant = COLOURS[colour]
    palette = palette_of(colour)
    pattern = PATTERNS[variant["pattern"]](variant) if "pattern" in variant else None
    surface = pygame.Surface((FRAME_W, FRAME_H), pygame.SRCALPHA)
    for part in parts:
        for dy, row in enumerate(part.rows):
            for dx, c in enumerate(row):
                x, y = LEFT_ROOM + part.x + dx, part.y + dy
                if c != "." and 0 <= x < FRAME_W and 0 <= y < FRAME_H:
                    colour_here = palette[c]
                    if pattern:
                        hx, hy = part.home
                        colour_here = pattern(hx + dx, hy + dy, c, colour_here)
                    surface.set_at((x, y), _young(colour_here, c, youth))
    return surface


def standing(head=HEAD, tail=TAIL, colour=COLOUR, youth=0.0):
    return compose([BODY, TAILS[tail], LEGS["stand"], HEADS[head]], colour, youth)


def mirrored(surface):
    """The right-facing frame of a left-facing one."""
    import pygame
    return pygame.transform.flip(surface, True, False)


# Legs straightened, the body a pixel up: the walk's passing frames
LEGS["long"] = Part([
    "......F..F......",
    "......F..F......",
    ".....FF.FF......",
], y=13)

# Pecking: the whole chicken but its legs tipped forward about its hips (PIVOT, on the grid), head down
PECK_DOWN = 40      # degrees, the beak at the ground
PECK_UP = 22        # degrees, between pecks and stepping on
PIVOT = (8.5, 13.0)
TILT_SAMPLES = 4    # each pixel of a tipped frame is the most of this many squared samples
# The walk, frame by frame: the legs, how far the head jerks forward, the bob (body up a pixel)
WALK = (("long", 0, -1), ("front", -1, 0), ("long", 0, -1), ("back", -1, 0))


def tipped_spot(spot, degrees, pivot=PIVOT):
    """Where a pixel at `spot` (x, y on the canvas) lands once the frame is tipped `degrees`."""
    import math
    cos, sin = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    px, py = LEFT_ROOM + pivot[0], pivot[1]
    dx, dy = spot[0] + 0.5 - px, spot[1] + 0.5 - py
    return math.floor(cos * dx + sin * dy + px), math.floor(-sin * dx + cos * dy + py)


def eye_spot(head):
    """The eye's pixel on the canvas, as the head stands."""
    part = HEADS[head]
    row = next(i for i, r in enumerate(part.rows) if "E" in r)
    return LEFT_ROOM + part.x + part.rows[row].index("E"), part.y + row


def tipped(surface, degrees, pivot=PIVOT):
    """The frame turned `degrees` forward (head down) about `pivot` on the grid, as pixel art.

    Each pixel is the colour most of its TILT_SAMPLES x TILT_SAMPLES samples fall on, taken from
    the frame blown up without smoothing (no colours mixed, so it stays sharp), not one sample each,
    which would break its outlines up."""
    import math

    import pygame
    k = TILT_SAMPLES
    width, height = surface.get_size()
    big = pygame.transform.scale(surface, (width * k, height * k))
    out = pygame.Surface((width, height), pygame.SRCALPHA)
    cos, sin = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    px, py = (LEFT_ROOM + pivot[0]) * k, pivot[1] * k
    for y in range(height):
        for x in range(width):
            votes = {}
            for j in range(k):
                for i in range(k):
                    dx, dy = x * k + i + 0.5 - px, y * k + j + 0.5 - py
                    sx, sy = math.floor(cos * dx - sin * dy + px), math.floor(sin * dx + cos * dy + py)
                    colour = (tuple(big.get_at((sx, sy))) if 0 <= sx < width * k and 0 <= sy < height * k
                              else (0, 0, 0, 0))
                    votes[colour] = votes.get(colour, 0) + 1
            colour = max(votes, key=votes.get)
            if colour[3]:
                out.set_at((x, y), colour)
    return out


def frames(head=HEAD, tail=TAIL, colour=COLOUR, youth=0.0):
    """Every frame of a chicken, facing left: {"stand": surface, "walk": [4 surfaces],
    "peck": [head down, head up, a step forward with it up]}."""
    body, tail_part, head_part = BODY, TAILS[tail], HEADS[head]
    walk = [compose([body.at(0, bob), tail_part.at(0, bob), LEGS[legs], head_part.at(dx, bob)], colour, youth)
            for legs, dx, bob in WALK]
    upright = compose([body, tail_part, head_part], colour, youth)
    peck = []
    for legs, degrees in (("stand", PECK_DOWN), ("stand", PECK_UP), ("front", PECK_UP)):
        frame = compose([LEGS[legs]], colour, youth)
        frame.blit(tipped(upright, degrees), (0, 0))
        # The eye is one pixel, which the feathers round it outvote when tipped: put it back
        frame.set_at(tipped_spot(eye_spot(head), degrees), _young(palette_of(colour)["E"], "E", youth))
        peck.append(frame)
    return {"stand": standing(head, tail, colour, youth), "walk": walk, "peck": peck}
