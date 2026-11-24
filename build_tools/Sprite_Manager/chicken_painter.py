"""The chicken, painted by code pixel by pixel from modular parts.

A chicken frame is put together from parts (a head, the body, a tail, the legs), each a
small grid of characters, one per pixel, laid onto a FRAME x FRAME canvas at an
offset. Later parts are painted over earlier ones; '.' is see-through. So a
walk frame is the same head and body with other legs and a pixel of bob, and an
eating frame swaps in a lowered head, without redrawing the rest.

Frames face left (as the sheep's do); the right-facing ones are mirrored.

    python build_tools/Sprite_Manager/chicken_painter.py --preview out.png

draws every head on the body, enlarged, for comparing them (`--parts tails`
the tails).
"""

import argparse
import os

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
    """A grid of pixels to be laid at (x, y) on the frame."""

    def __init__(self, rows, x=0, y=0):
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

    def at(self, dx=0, dy=0):
        """The same part moved by (dx, dy)."""
        return Part(self.rows, self.x + dx, self.y + dy)


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


def compose(parts):
    """Lays the parts in order onto a see-through frame, facing left."""
    surface = pygame.Surface((FRAME, FRAME), pygame.SRCALPHA)
    for part in parts:
        for dy, row in enumerate(part.rows):
            for dx, c in enumerate(row):
                x, y = part.x + dx, part.y + dy
                if c != "." and 0 <= x < FRAME and 0 <= y < FRAME:
                    surface.set_at((x, y), PALETTE[c])
    return surface


def standing(head=HEAD, tail=TAIL):
    return compose([BODY, TAILS[tail], LEGS["stand"], HEADS[head]])


def mirrored(surface):
    """The right-facing frame of a left-facing one."""
    return pygame.transform.flip(surface, True, False)


def preview(path, what="heads", scale=14):
    """Every head (on the chosen tail) or every tail (under the chosen head),
    enlarged and labelled."""
    pygame.init()
    names = list(HEADS if what == "heads" else TAILS)
    cell = FRAME * scale
    sheet = pygame.Surface((len(names) * (cell + scale) + scale, cell + 2 * scale))
    sheet.fill((150, 190, 110))
    font = pygame.font.SysFont(None, 40)
    for i, name in enumerate(names):
        frame = standing(head=name) if what == "heads" else standing(tail=name)
        x = scale + i * (cell + scale)
        sheet.blit(pygame.transform.scale(frame, (cell, cell)), (x, scale))
        sheet.blit(font.render(name, True, (0, 0, 0)), (x + 4, 4))
    pygame.image.save(sheet, path)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--preview", help="write the parts compared, enlarged, to this PNG")
    parser.add_argument("--parts", choices=("heads", "tails"), default="heads",
                        help="which parts --preview compares")
    args = parser.parse_args()
    if args.preview:
        preview(args.preview, args.parts)
        print(f"wrote {args.preview}")


if __name__ == "__main__":
    main()
