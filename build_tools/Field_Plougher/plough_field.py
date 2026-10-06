"""Bake a ploughed field (furrows running up-down) into ground_tiles.png and Map1.tmx.

Run from the repo root with Tiled closed: python build_tools/Field_Plougher/plough_field.py
(--rebake to redo a field already baked, e.g. after changing the furrows).

The field is an L: an upper block and a lower-left block. Each field cell gets
a tile of its own, cut from the dirt square (ground_tiles cells 0..21) so the
texture stays continuous, with a furrow down its middle. The half-dirt edge
cells of the square make the headland; the first and last full rows close the
furrows off with a rounded end. The baked tiles go on Ground_High into a
free block of the atlas (rows 90-99, cols 50-99, room for 500), and flowers
on the field are cleared. The field's "Ploughed" object on the Fields layer
(for the Town Plan) is drawn in Tiled by hand to match UPPER/LOWER.
"""
import math
import random
import sys

import pygame

sys.path.insert(0, '.claude/skills/place-building')
import place_building as pb  # noqa: E402

ATLAS = 'assets/tiles/ground_tiles.png'
FIRSTGID = 50087
COLS = 100
FREE_ROW, FREE_COL = 90, 50          # free atlas block: rows 90-99, cols 50-99

# Field blocks, inclusive tile ranges (cols, rows). Edge cells are included.
REBAKE = '--rebake' in sys.argv
UPPER = (129, 151, 190, 201)
LOWER = (129, 142, 202, 209)


def in_field(c, r):
    return any(c0 <= c <= c1 and r0 <= r <= r1 for c0, c1, r0, r1 in (UPPER, LOWER))


cells = sorted({(c, r) for c0, c1, r0, r1 in (UPPER, LOWER)
                for c in range(c0, c1 + 1) for r in range(r0, r1 + 1)})


def edges(c, r):
    return (not in_field(c - 1, r), not in_field(c + 1, r),
            not in_field(c, r - 1), not in_field(c, r + 1))


def src_cell(c, r):
    left, right, top, bottom = edges(c, r)
    sc = 0 if left else 21 if right else 1 + (c - UPPER[0] - 1) % 20
    sr = 0 if top else 21 if bottom else 1 + (r - UPPER[2] - 1) % 20
    return sc, sr


def shade(d):
    """Brightness factor across a furrow, d = px from its centre line."""
    groove = 0.40 * math.exp(-(d / 2.7) ** 2)             # the dark bottom
    wall = 0.12 * (d / 3.5) * math.exp(-(d / 3.5) ** 2)    # lit east wall, shaded west wall
    ridge = 0.09 * math.exp(-((abs(d) - 9.5) / 3.0) ** 2)  # the turned-up soil either side
    return 1.0 - groove + wall + ridge


def main():
    pygame.init()
    pygame.display.set_mode((1, 1))
    atlas = pygame.image.load(ATLAS).convert_alpha()
    rng = random.Random(7)
    text, layers = pb.load_tmx()
    high = layers['Ground_High']
    flowers = layers['Ground_Flowers_Mushrooms']
    assert len(cells) <= 500, len(cells)

    for k, (c, r) in enumerate(cells):
        left, right, top, bottom = edges(c, r)
        sc, sr = src_cell(c, r)
        tile = atlas.subsurface((sc * 32, sr * 32, 32, 32)).copy()
        # Inner corner of the L: dirt everywhere but the corner diagonally
        # off, which gets the square's ragged edge from both sides
        if not (left or right or top or bottom):
            for dc, dr in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
                if not in_field(c + dc, r + dr):
                    ex = atlas.subsurface(((21 if dc > 0 else 0) * 32, sr * 32, 32, 32))
                    ey = atlas.subsurface((sc * 32, (21 if dr > 0 else 0) * 32, 32, 32))
                    for y in range(32):
                        for x in range(32):
                            a = 1 - (1 - ex.get_at((x, y)).a / 255) * (1 - ey.get_at((x, y)).a / 255)
                            px = tile.get_at((x, y))
                            tile.set_at((x, y), (px.r, px.g, px.b, int(px.a * a)))
        full_col = not (left or right)
        full_row = not (top or bottom)
        if full_col and full_row:
            first = edges(c, r - 1)[2]   # the row above is the headland
            last = edges(c, r + 1)[3]
            phase = c * 1.7
            for y in range(32):
                wy = r * 32 + y
                cx = 15.5 + 0.8 * math.sin(wy / 23.0 + phase)
                # Rounded ends: past the end, the groove fades as if measured from a cap
                past = max(0.0, 9 - y) if first else max(0.0, y - 22) if last else 0.0
                for x in range(32):
                    d = x - cx
                    if past:
                        dist = math.hypot(d, past * 1.3)
                        f = shade(dist)
                        # a little heap where the plough came out
                        f += 0.06 * math.exp(-((dist - 6.5) / 2.0) ** 2) * min(1.0, past / 3)
                    else:
                        f = shade(d)
                    f *= 1.0 + rng.uniform(-0.03, 0.03)
                    if abs(d) < 3 and rng.random() < 0.04 and not past:
                        f *= 0.8                                   # clods in the groove
                    rr, gg, bb, aa = tile.get_at((x, y))
                    tile.set_at((x, y), (min(255, int(rr * f)), min(255, int(gg * f)),
                                         min(255, int(bb * f)), aa))
        ar, ac = FREE_ROW + k // 50, FREE_COL + k % 50
        # Copied, not blended: a rebake must not lay its edges over the old ones
        atlas.fill((0, 0, 0, 0), (ac * 32, ar * 32, 32, 32))
        atlas.blit(tile, (ac * 32, ar * 32), special_flags=pygame.BLEND_RGBA_ADD)
        if high[r][c] and not REBAKE:
            raise SystemExit(f'Ground_High {c},{r} already used')
        high[r][c] = FIRSTGID + ar * COLS + ac
        flowers[r][c] = 0

    pygame.image.save(atlas, ATLAS)
    pb.save_tmx(text, layers)
    print(f'baked {len(cells)} tiles')


if __name__ == '__main__':
    main()
