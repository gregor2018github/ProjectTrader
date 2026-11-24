"""The chicken, painted by code pixel by pixel from modular parts.

A chicken frame is put together from parts (a head, the body, a tail, the legs), each a
small grid of characters, one per pixel, laid onto a FRAME x FRAME canvas at an
offset. Later parts are painted over earlier ones; '.' is see-through. So a
walk frame is the same head and body with other legs and a pixel of bob, and an
eating frame swaps in a lowered head, without redrawing the rest.

Frames face left (as the sheep's do); the right-facing ones are mirrored.

    python build_tools/Sprite_Manager/chicken_painter.py --preview out.png

draws every head on the body, enlarged, for comparing them (`--parts tails`
the tails, `--parts colours` the colour variants).
"""

import argparse
import colorsys
import os
import zlib

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame  # noqa: E402

FRAME = 16  # the frame's width and height in pixels

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
# and head are painted over it, the legs under it.
BODY = Part([
    ".........OOOO...",
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


def compose(parts, colour=COLOUR):
    """Lays the parts in order onto a see-through frame, facing left, in one
    of the COLOURS."""
    variant = COLOURS[colour]
    palette = {**PALETTE, **{k: v for k, v in variant.items() if k in PALETTE}}
    pattern = PATTERNS[variant["pattern"]](variant) if "pattern" in variant else None
    surface = pygame.Surface((FRAME, FRAME), pygame.SRCALPHA)
    for part in parts:
        for dy, row in enumerate(part.rows):
            for dx, c in enumerate(row):
                x, y = part.x + dx, part.y + dy
                if c != "." and 0 <= x < FRAME and 0 <= y < FRAME:
                    colour_here = palette[c]
                    if pattern:
                        hx, hy = part.home
                        colour_here = pattern(hx + dx, hy + dy, c, colour_here)
                    surface.set_at((x, y), colour_here)
    return surface


def standing(head=HEAD, tail=TAIL, colour=COLOUR):
    return compose([BODY, TAILS[tail], LEGS["stand"], HEADS[head]], colour)


def mirrored(surface):
    """The right-facing frame of a left-facing one."""
    return pygame.transform.flip(surface, True, False)


def preview(path, what="heads", scale=14, per_row=6):
    """Every head (on the chosen tail), every tail (under the chosen head) or
    every colour, enlarged and labelled."""
    pygame.init()
    names = list({"heads": HEADS, "tails": TAILS, "colours": COLOURS}[what])
    cell = FRAME * scale
    columns = min(per_row, len(names))
    rows = (len(names) + per_row - 1) // per_row
    sheet = pygame.Surface((columns * (cell + scale) + scale,
                            rows * (cell + 2 * scale) + scale))
    sheet.fill((150, 190, 110))
    font = pygame.font.SysFont(None, 40)
    for i, name in enumerate(names):
        frame = standing(**{what[:-1]: name})
        x = scale + (i % per_row) * (cell + scale)
        y = scale + (i // per_row) * (cell + 2 * scale)
        sheet.blit(pygame.transform.scale(frame, (cell, cell)), (x, y + scale))
        sheet.blit(font.render(name, True, (0, 0, 0)), (x + 4, y))
    pygame.image.save(sheet, path)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--preview", help="write the parts compared, enlarged, to this PNG")
    parser.add_argument("--parts", choices=("heads", "tails", "colours"), default="heads",
                        help="which parts --preview compares")
    args = parser.parse_args()
    if args.preview:
        preview(args.preview, args.parts)
        print(f"wrote {args.preview}")


if __name__ == "__main__":
    main()
