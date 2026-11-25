"""Paints the chicken pen's trough, empty and at every fill of water or grain, pixel by pixel.

A low wooden trough two tiles long, of the chicken fence's weathered boards
(wood_fence_painter.py's palette; stone_wall_painter.py's Canvas, shade and
jitter): two end boards standing a little proud, a back board whose inner face
shows over the front board's rim, and the front face of two planks nailed to
the ends. The map is drawn from above at a slant, so the inside shows as a band
between the back board's top and the front rim: what is poured in shows as a
surface rising up that band, the inner face of the back board above it.

The pictures, all on one 64 x 32 canvas (2 x 1 tiles, the trough's foot on
FOOT_Y, so they swap in place in the game, models/trough.py):

    troughs/trough_empty.png             a little old straw and dirt on its floor
    troughs/trough_water_<1..4>.png      water a quarter full to brim full
    troughs/trough_feed_<1..4>.png       grain, heaped above the rim when full,
                                         a few grains pecked out onto the ground

Each picture is drawn from a random.Random seeded by its name, so painting
again gives the same pixels.

    python trough_painter.py --preview out.png     # all of them side by side, 1x and 4x
    python trough_painter.py --write
"""

import argparse
import math
import os
import random
import sys
import zlib

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
import pygame
from stone_wall_painter import Canvas, shade
from wood_fence_painter import PALETTE, _grain, _wood

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
OUT_DIR = os.path.join(ROOT, 'assets', 'map_sprites', 'houses', 'troughs')

SIZE = (64, 32)
FOOT_Y = 28                 # the row it stands on; under it its shadow and spilt grain
LEFT, RIGHT = 3, 60         # the end boards' outer columns
END_W = 4                   # an end board's thickness, seen edge on
END_TOP = 10                # the end boards' tops, standing proud of the sides
BACK_TOP = 12              # the back board's top edge, two rows deep
INSIDE = (14, 19)           # the inside's rows: the back board's inner face down to the floor
RIM = 20                    # the front board's top edge, two rows deep
FACE = (22, 27)             # the front face's rows
SEAM = 25                   # where its two planks meet
INNER = (LEFT + END_W, RIGHT - END_W)   # the boards' columns between the end boards
LEVELS = 4                  # fills drawn: a quarter to brim full
#: The topmost row of the contents' surface at each fill
SURFACE_TOP = {1: 18, 2: 17, 3: 16, 4: 14}
#: Grain heaps up in the middle when the trough is well filled, by up to this many rows
HEAP = {1: 0, 2: 0, 3: 1, 4: 3}

WATER = (78, 112, 122)      # dull, holding the sky's grey; lighter towards the front
WATER_SHINE = (128, 158, 164)
GRAIN = (204, 166, 88)
GRAIN_DARK = (160, 120, 60)
GRAIN_LIGHT = (234, 206, 132)
STRAW = (176, 150, 92)
DIRT = (96, 74, 50)
GROUND_SHADOW = (62, 44, 30)


def _ink(canvas, x, y, colour, k=1.0, alpha=255):
    canvas.put(x, y, shade(colour, k), alpha)


def _boards(canvas, rng):
    """The trough itself: end boards, back board, inside, rim and front face."""
    pal = PALETTE
    inner_l, inner_r = INNER
    back = _wood(pal, rng, pal.rail)
    front_planks = (_wood(pal, rng, pal.rail), _wood(pal, rng, pal.rail))

    # Back board: its top edge, lit, then its inner face in the trough's shade, darker down to the floor
    for x in range(inner_l, inner_r + 1):
        _ink(canvas, x, BACK_TOP, _grain(back, rng), 1.16)
        _ink(canvas, x, BACK_TOP + 1, _grain(back, rng), 0.98)
        for y in range(INSIDE[0], INSIDE[1] + 1):
            depth = (y - INSIDE[0]) / (INSIDE[1] - INSIDE[0])
            _ink(canvas, x, y, _grain(back, rng), 0.66 - 0.22 * depth)
    # The floor's front row, under the rim's shadow
    for x in range(inner_l, inner_r + 1):
        _ink(canvas, x, INSIDE[1], back, 0.40)

    # Front board: its rim lit from above, then two planks, darker towards the ground
    for x in range(inner_l, inner_r + 1):
        _ink(canvas, x, RIM, _grain(front_planks[0], rng), 1.18)
        _ink(canvas, x, RIM + 1, _grain(front_planks[0], rng), 1.04)
    for y in range(FACE[0], FACE[1] + 1):
        plank = front_planks[0] if y < SEAM else front_planks[1]
        down = (y - FACE[0]) / (FACE[1] - FACE[0])
        for x in range(inner_l, inner_r + 1):
            k = 1.0 - 0.14 * down
            if y == SEAM:
                k *= 0.62                                   # the joint between the planks
            elif y == SEAM + 1 or y == FACE[0]:
                k *= 1.07                                   # each plank's upper arris catches the light
            _ink(canvas, x, y, _grain(plank, rng), k)
    # A long split in the lower plank and a knot in the upper one
    split_x = rng.randint(inner_l + 14, inner_r - 20)
    for i in range(rng.randint(5, 8)):
        canvas.darken(split_x + i, SEAM + 2 + (i // 4), 0.74)
    knot_x = rng.randint(inner_l + 6, inner_r - 10)
    canvas.darken(knot_x, FACE[0] + 2, 0.70)
    canvas.darken(knot_x + 1, FACE[0] + 2, 0.82)
    canvas.darken(knot_x, FACE[0] + 1, 0.88)

    # End boards, seen edge on: end grain on top, lit on the left board's left, shaded on the right's right
    for x0, side in ((LEFT, -1), (RIGHT - END_W + 1, 1)):
        board = _wood(pal, rng, pal.post)
        for i, x in enumerate(range(x0, x0 + END_W)):
            across = (1.12, 1.02, 0.94, 0.84)[i] if side < 0 else (1.02, 0.96, 0.88, 0.74)[i]
            _ink(canvas, x, END_TOP, pal.end_grain, 1.06 * across)
            _ink(canvas, x, END_TOP + 1, pal.end_grain, 0.90 * across)
            for y in range(END_TOP + 2, FOOT_Y):
                _ink(canvas, x, y, _grain(board, rng), across * (1.0 - 0.12 * (y - END_TOP) / (FOOT_Y - END_TOP)))
        # The nails holding the front planks, one in each plank
        nail_x = inner_l + 2 if side < 0 else inner_r - 2
        for y in (FACE[0] + 1, SEAM + 2):
            _ink(canvas, nail_x, y, (54, 50, 48))
            _ink(canvas, nail_x - side, y - 1, (150, 146, 138))
    # The end boards cast a little shade onto the inside next to them
    for y in range(INSIDE[0], INSIDE[1] + 1):
        canvas.darken(inner_l, y, 0.78)
        canvas.darken(inner_r, y, 0.86)

    # Outline round the whole, seating it on the ground
    outline = pal.outline
    for y in range(END_TOP, FOOT_Y + 1):
        _ink(canvas, LEFT - 1, y, outline)
        _ink(canvas, RIGHT + 1, y, outline)
    for x in range(LEFT, RIGHT + 1):
        _ink(canvas, x, FOOT_Y, outline)
    for x in range(LEFT, LEFT + END_W):
        _ink(canvas, x, END_TOP - 1, outline)
    for x in range(RIGHT - END_W + 1, RIGHT + 1):
        _ink(canvas, x, END_TOP - 1, outline)
    for x in range(inner_l, inner_r + 1):
        _ink(canvas, x, BACK_TOP - 1, outline)


def _ground_shadow(canvas):
    """A little translucent shade on the grass under its front and east, the light being from the upper left."""
    for x in range(LEFT, RIGHT + 4):
        for i, alpha in enumerate((70, 44)):
            canvas.put(x, FOOT_Y + 1 + i, GROUND_SHADOW, alpha)
    for y in range(END_TOP + 3, FOOT_Y + 1):
        for i, alpha in enumerate((58, 30)):
            canvas.put(RIGHT + 2 + i, y, GROUND_SHADOW, alpha)


def _empty_floor(canvas, rng):
    """Old straw and a crust of dirt on the floor of an empty trough."""
    inner_l, inner_r = INNER
    for x in range(inner_l, inner_r + 1):
        roll = rng.random()
        if roll < 0.18:
            _ink(canvas, x, INSIDE[1], STRAW, rng.uniform(0.62, 0.80))
        elif roll < 0.30:
            _ink(canvas, x, INSIDE[1], DIRT, rng.uniform(0.8, 1.0))
    for _ in range(4):                                     # a few straws lying across
        x, y = rng.randint(inner_l + 2, inner_r - 6), INSIDE[1] - rng.randint(0, 1)
        for i in range(rng.randint(2, 4)):
            _ink(canvas, x + i, y, STRAW, 0.78)


def _water(canvas, rng, level):
    """Still water from SURFACE_TOP up to the rim: dark where it meets the back board, the sky's shine
    towards the front, a few lighter streaks."""
    inner_l, inner_r = INNER
    top = SURFACE_TOP[level]
    rows = INSIDE[1] - top + 1
    for y in range(top, INSIDE[1] + 1):
        towards_front = (y - top) / max(1, rows - 1)
        k = 0.80 if y == top else 0.92 + 0.16 * towards_front
        for x in range(inner_l, inner_r + 1):
            _ink(canvas, x, y, WATER, k * (0.88 if x in (inner_l, inner_r) else 1.0))
    # Streaks of shine along the surface, never on its back row
    for _ in range(1 + level // 2):
        if rows < 2:
            break
        y = rng.randint(top + 1, INSIDE[1])
        x = rng.randint(inner_l + 3, inner_r - 8)
        for i in range(rng.randint(2, 4)):
            _ink(canvas, x + i, y, WATER_SHINE, rng.uniform(0.92, 1.0))
    # A wet dark line on the back board just over the water: where it stood higher before
    if top - 1 >= INSIDE[0]:
        for x in range(inner_l, inner_r + 1):
            if rng.random() < 0.7:
                canvas.darken(x, top - 1, 0.86)


def _grain_pixel(rng, k=1.0):
    roll = rng.random()
    colour = GRAIN_DARK if roll < 0.22 else GRAIN_LIGHT if roll < 0.34 else GRAIN
    return shade(colour, k * rng.uniform(0.95, 1.04))


def _feed(canvas, rng, level):
    """Grain from the floor up: patchy at a quarter, heaped in the middle when well filled, its top lit,
    and a few grains pecked out onto the ground in front."""
    inner_l, inner_r = INNER
    base, heap = SURFACE_TOP[level], HEAP[level]
    span = inner_r - inner_l
    for x in range(inner_l, inner_r + 1):
        rise = heap * math.sin(math.pi * (x - inner_l) / span)
        top = base - int(rise + rng.uniform(-0.35, 0.35))
        if level == 1 and rng.random() < 0.25:
            top = INSIDE[1]                                 # a quarter full: the floor shows through in places
        for y in range(top, INSIDE[1] + 1):
            k = 1.12 if y == top else 1.0 - 0.10 * (y - top) / 6
            if y < BACK_TOP + 2 and y != top:
                k *= 0.96
            canvas.put(x, y, _grain_pixel(rng, k))
        if top < BACK_TOP:                                  # heaped over the back board: an outline behind
            canvas.put(x, top - 1, shade(GRAIN_DARK, 0.72))
    # Grains the chickens have pecked out, on the ground in front
    for _ in range(2 + 2 * level):
        x = rng.randint(LEFT + 2, RIGHT + 2)
        y = rng.randint(FOOT_Y + 1, SIZE[1] - 1)
        canvas.put(x, y, _grain_pixel(rng, 0.96))


def paint(name):
    """The picture called `name` (trough_empty, trough_water_<n>, trough_feed_<n>)."""
    canvas = Canvas(SIZE)
    rng = random.Random(zlib.crc32(b'trough'))              # the trough is the same in every picture
    _ground_shadow(canvas)
    _boards(canvas, rng)
    fill = random.Random(zlib.crc32(name.encode()))
    if name == 'trough_empty':
        _empty_floor(canvas, fill)
    else:
        kind, level = name.split('_')[1], int(name.rsplit('_', 1)[1])
        (_water if kind == 'water' else _feed)(canvas, fill, level)
    return canvas.surface


def names():
    return ['trough_empty'] + [f'trough_{kind}_{n}' for kind in ('water', 'feed') for n in range(1, LEVELS + 1)]


def preview(path):
    pictures = [paint(n) for n in names()]
    grass = (104, 140, 64)
    pad = 8
    w, h = SIZE
    sheet = pygame.Surface((pad + len(pictures) * (w * 4 + pad), pad * 3 + h + h * 4))
    sheet.fill(grass)
    for i, picture in enumerate(pictures):
        x = pad + i * (w * 4 + pad)
        sheet.blit(picture, (x, pad))
        sheet.blit(pygame.transform.scale(picture, (w * 4, h * 4)), (x, pad * 2 + h))
    pygame.image.save(sheet, path)
    print(f'saved {path}')


def write():
    os.makedirs(OUT_DIR, exist_ok=True)
    for name in names():
        path = os.path.join(OUT_DIR, f'{name}.png')
        pygame.image.save(paint(name), path)
        print(f'wrote {os.path.relpath(path, ROOT)}')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--preview', metavar='PNG')
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args(argv)
    pygame.init()
    if args.preview:
        preview(args.preview)
    if args.write:
        write()
    if not (args.preview or args.write):
        parser.print_help()
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
