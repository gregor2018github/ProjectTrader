"""Paints a dressed-stone wall's pieces pixel by pixel, without the image model.

The model's answers for walls came back crooked or in perspective too often, so
a stone wall with pillars at its ends (fences.py, posts_every 0) can be painted
here instead, on exactly the raster its pieces are saved on:

- a horizontal piece: courses of ashlar under a coping of flat slabs, a pillar
  at each end (a plinth, blocks, a cap and a low pyramid on it), the pillar's
  shadow on the wall to its right;
- a vertical piece: the coping's top seen from above, slabs one under the
  other down a straight band, a strip of shaded side face to the east and the
  wall's shadow on the grass. It has no pillars of its own: at its top it comes
  out of the corner pillar's front face (it stands in front of it, so it is
  drawn over it), at its bottom it stops where that pillar's cap begins, its
  pyramid left out, so whichever of the two the game draws last, it looks right.

Every pixel's colour is a palette colour times a shade, so light comes from the
upper left throughout. A piece's stones are drawn from a random.Random seeded
by the style and the piece, so painting again gives the same picture.

    python stone_wall_painter.py churchyard_wall --preview plan.png   # look first
    python stone_wall_painter.py churchyard_wall --write              # into the style's folder

--write keeps the pieces it replaces in build_tools/output/fences/<style>/replaced/.
"""

import argparse
import os
import random
import shutil
import sys
import zlib
from dataclasses import dataclass
from datetime import datetime

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
import itertools

import pygame

from fences import HORIZONTAL, TILE, find_styles

# Heights in game pixels above (minus) or below the run's foot line (Raster.start's y)
WALL_TOP = -37          # the coping's back edge
COPING_ROWS = 6
COURSE_ROWS = 6         # stone rows of a course, a mortar row under each
COURSES = 5
BASE = 3                # the wall's outline along the ground; its front face stands here
CAP_TOP = -43           # the pillar's cap
FINIAL_ROWS = 4         # the pyramid on the cap
SHAFT_TOP = -37
PLINTH_TOP = -1
TOP_TO_GROUND = 34      # how far up the coping's top is drawn from the ground under it

PILLAR_HALF = 8         # the shaft is 2 * 8 + 1 px wide
CAP_HALF = 10
PLINTH_HALF = 9
BAND_LEFT, BAND_RIGHT = -5, 4     # a vertical piece's coping, about the run's centre
SIDE_FACE = 2                     # px of shaded side face east of it
GROUND_SHADOW = (62, 46, 30)      # alpha of the shadow on the grass, px by px away from the face


@dataclass(frozen=True)
class Palette:
    stone: tuple = (146, 135, 113)
    coping: tuple = (162, 151, 130)
    pillar: tuple = (160, 149, 127)
    mortar: tuple = (94, 86, 72)
    outline: tuple = (78, 70, 58)
    lichen: tuple = (128, 134, 100)


PALETTE = Palette()


def shade(colour, k):
    return tuple(max(0, min(255, round(v * k))) for v in colour)


def jitter(colour, rng, spread=3):
    """A stone's own tint: a little warmer or cooler, never another colour."""
    warm = rng.uniform(-spread, spread)
    return tuple(max(0, min(255, round(v + d))) for v, d in zip(colour, (warm, warm * 0.6, -warm * 0.4)))


class Canvas:
    def __init__(self, size):
        self.surface = pygame.Surface(size, pygame.SRCALPHA)
        self.w, self.h = size
        self.skip = None                  # (x, y) -> True for pixels to leave alone

    def put(self, x, y, colour, alpha=255):
        if 0 <= x < self.w and 0 <= y < self.h and not (self.skip and self.skip(x, y)):
            self.surface.set_at((x, y), (*colour, alpha))

    def darken(self, x, y, k):
        if 0 <= x < self.w and 0 <= y < self.h:
            r, g, b, a = self.surface.get_at((x, y))
            if a:
                self.surface.set_at((x, y), (*shade((r, g, b), k), a))


def _speckle(colour, rng):
    roll = rng.random()
    if roll < 0.05:
        return shade(colour, 0.92)
    if roll < 0.08:
        return shade(colour, 1.05)
    return colour


def _joints(rng, left, right, shortest, longest, avoid=(), clear=3):
    """Where the vertical joints of a course fall, none within `clear` px of those of the course above."""
    joints, x = [], left - rng.randint(0, longest)
    while x < right:
        x += rng.randint(shortest, longest)
        for _ in range(3):
            if all(abs(x - a) >= clear for a in avoid):
                break
            x += clear + 1
        joints.append(x)
    return joints


# ---------------------------------------------------------------------------
# Horizontal pieces
# ---------------------------------------------------------------------------

def _paint_coping(canvas, rng, left, right, top, pal):
    rows = (0.82, 1.10, 1.20, 1.0, 0.97, 0.86)
    joints = _joints(rng, left, right, 22, 34)
    edges = [left - 40] + joints
    for a, b in itertools.pairwise(edges):
        base = jitter(shade(pal.coping, rng.uniform(0.95, 1.04)), rng)
        for x in range(max(a, left), min(b, right)):
            for r, k in enumerate(rows):
                if x == b - 1 and r:
                    colour = shade(pal.mortar, 0.95)
                elif x == a and r in (1, 2):
                    colour = shade(base, k * 1.05)
                else:
                    colour = _speckle(shade(base, k), rng)
                canvas.put(x, top + r, colour)


COURSE_LIGHT = (0.70, 1.0, 0.97, 0.92, 0.87)    # in the coping's shadow, then darker towards the ground


def _paint_courses(canvas, rng, left, right, top, pal):
    above = ()
    for course, light in enumerate(COURSE_LIGHT):
        y0 = top + course * (COURSE_ROWS + 1)
        joints = _joints(rng, left, right, 13, 20, above)
        above = joints
        edges = [left - 40] + joints
        for a, b in itertools.pairwise(edges):
            base = jitter(shade(pal.stone, light * rng.uniform(0.92, 1.06)), rng)
            if rng.random() < 0.12:
                base = shade(base, 0.9)                 # a weathered stone
            chipped = rng.random() < 0.15
            lichen = course >= 3 and rng.random() < 0.18
            for x in range(max(a, left), min(b, right)):
                for r in range(COURSE_ROWS):
                    if x == b - 1:
                        canvas.put(x, y0 + r, shade(pal.mortar, 0.88))
                        continue
                    k = 1.10 if r == 0 else 0.94 if r == COURSE_ROWS - 1 else 1.0
                    if course == 0:
                        k *= 0.85 + 0.03 * r            # the overhang's shadow, lightest low down
                    if x == a:
                        k *= 1.06
                    elif x == b - 2:
                        k *= 0.9
                    colour = _speckle(shade(base, k), rng)
                    if chipped and x == b - 2 and r == 0:
                        colour = pal.mortar
                    canvas.put(x, y0 + r, colour)
            if lichen and b - a > 6:
                lx, ly = rng.randint(a + 1, b - 4), y0 + rng.randint(2, COURSE_ROWS - 2)
                for dx, dy in ((0, 0), (1, 0), (1, 1)):
                    canvas.put(lx + dx, ly + dy, jitter(pal.lichen, rng, 4))
            if course < COURSES - 1:
                for x in range(max(a, left), min(b, right)):
                    canvas.put(x, y0 + COURSE_ROWS, pal.mortar)


def _finial_half(row):
    """Half the pyramid's width on its row (0 = apex)."""
    return 2 + 2 * row


def _paint_pillar(canvas, rng, cx, foot, pal):
    pillar = jitter(pal.pillar, rng, 2)
    # The low pyramid on the cap, its left faces lit
    top = foot + CAP_TOP - FINIAL_ROWS
    for row in range(FINIAL_ROWS):
        half = _finial_half(row)
        for x in range(cx - half, cx + half + 1):
            k = 1.16 if x < cx else 1.0 if x == cx else 0.82
            if abs(x - cx) == half:
                k *= 0.8
            canvas.put(x, top + row, shade(pillar, k * (1.06 if row == 0 else 1.0)))
    # The cap: back edge, lit top, front face
    for r, k in enumerate((0.92, 1.18, 1.06, 0.84)):
        for x in range(cx - CAP_HALF, cx + CAP_HALF + 1):
            edge = 0.85 if x == cx - CAP_HALF else 0.75 if x == cx + CAP_HALF else 1.0
            canvas.put(x, foot + CAP_TOP + r, _speckle(shade(pillar, k * edge), rng))
    # The shadow under the cap
    for y in range(foot + CAP_TOP + 4, foot + SHAFT_TOP):
        for x in range(cx - PILLAR_HALF, cx + PILLAR_HALF + 1):
            canvas.put(x, y, shade(pillar, 0.62))
    # The shaft, four blocks of 8 rows and a mortar row, every other block split in two
    y = foot + SHAFT_TOP
    block = 0
    while y < foot + PLINTH_TOP:
        rows = min(8, foot + PLINTH_TOP - y)
        splits = [] if block % 2 == 0 else [cx + rng.choice((-2, 0, 1, 2))]
        edges = [cx - PILLAR_HALF] + splits + [cx + PILLAR_HALF + 1]
        for a, b in itertools.pairwise(edges):
            base = shade(pillar, rng.uniform(0.95, 1.04))
            for x in range(a, b):
                for r in range(rows):
                    if x == b - 1 and b != edges[-1]:
                        canvas.put(x, y + r, pal.mortar)
                        continue
                    k = 1.1 if r == 0 else 0.92 if r == rows - 1 else 1.0
                    if x <= cx - PILLAR_HALF + 1:
                        k *= 1.12
                    elif x >= cx + PILLAR_HALF - 2:
                        k *= 0.84
                    if x in (cx - PILLAR_HALF, cx + PILLAR_HALF):
                        k *= 0.78
                    canvas.put(x, y + r, _speckle(shade(base, k), rng))
        y += rows
        if y < foot + PLINTH_TOP:
            for x in range(cx - PILLAR_HALF, cx + PILLAR_HALF + 1):
                canvas.put(x, y, pal.mortar)
            y += 1
        block += 1
    # The plinth, a little wider
    for r, k in enumerate((1.15, 0.98, 0.95, 0.92)):
        for x in range(cx - PLINTH_HALF, cx + PLINTH_HALF + 1):
            edge = 0.8 if x == cx + PLINTH_HALF else 1.0
            canvas.put(x, foot + PLINTH_TOP + r, _speckle(shade(pillar, k * edge), rng))
    for x in range(cx - PLINTH_HALF, cx + PLINTH_HALF + 1):
        canvas.put(x, foot + BASE, pal.outline)


def paint_horizontal(raster, rng, pal=PALETTE):
    canvas = Canvas(raster.pixels)
    foot = round(raster.start[1] * TILE)
    posts = [round(x * TILE) for x, _ in raster.posts()]
    left, right = posts[0], posts[-1] + 1
    _paint_coping(canvas, rng, left, right, foot + WALL_TOP, pal)
    _paint_courses(canvas, rng, left, right, foot + WALL_TOP + COPING_ROWS, pal)
    for x in range(left, right):
        canvas.put(x, foot + BASE, pal.outline)
    for cx in posts:                                     # each pillar's shadow on the wall to its right
        for i, k in enumerate((0.74, 0.8, 0.87, 0.93)):
            for y in range(foot + WALL_TOP + COPING_ROWS, foot + BASE):
                canvas.darken(cx + PILLAR_HALF + 1 + i, y, k)
    for cx in posts:
        _paint_pillar(canvas, rng, cx, foot, pal)
    return canvas.surface


# ---------------------------------------------------------------------------
# Vertical pieces
# ---------------------------------------------------------------------------

def paint_vertical(raster, rng, pal=PALETTE):
    canvas = Canvas(raster.pixels)
    cx = round(raster.start[0] * TILE)
    first = round(raster.start[1] * TILE)
    last = round(raster.end()[1] * TILE)
    top = first + BASE - TOP_TO_GROUND                   # out of the first corner pillar's front face
    bottom = last + CAP_TOP - 1                          # gone behind the last one's cap

    finial_top = last + CAP_TOP - FINIAL_ROWS

    def behind_finial(x, y):
        return finial_top <= y < last + CAP_TOP and abs(x - cx) <= _finial_half(y - finial_top)

    canvas.skip = behind_finial
    # The shadow on the grass east of it
    for i, alpha in enumerate(GROUND_SHADOW):
        for y in range(top + 4, bottom + 1):
            canvas.put(cx + BAND_RIGHT + SIDE_FACE + 1 + i, y, (20, 24, 12), alpha)
    # The coping's slabs, one under the other
    joints = _joints(rng, top, bottom + 1, 20, 30)
    edges = [top - 40] + joints
    width = BAND_RIGHT - BAND_LEFT
    for a, b in itertools.pairwise(edges):
        base = jitter(shade(pal.coping, rng.uniform(0.94, 1.04)), rng)
        for y in range(max(a, top), min(b, bottom + 1)):
            for x in range(cx + BAND_LEFT - 1, cx + BAND_RIGHT + SIDE_FACE + 1):
                if x == cx + BAND_LEFT - 1:
                    colour = pal.outline                 # the west edge
                elif x > cx + BAND_RIGHT:                # the side face, in shade, its courses showing
                    k = 0.72 - 0.05 * (x - cx - BAND_RIGHT)
                    colour = pal.mortar if y == b - 1 or (y - top) % 7 == 6 else shade(base, k)
                elif y == b - 1:
                    colour = shade(pal.mortar, 0.95)
                else:
                    across = (x - cx - BAND_LEFT) / width
                    k = 1.12 - 0.17 * across
                    if y == a:
                        k *= 1.08
                    elif y == b - 2:
                        k *= 0.92
                    if x == cx + BAND_LEFT:
                        k *= 1.06
                    elif x == cx + BAND_RIGHT:
                        k *= 0.85                        # the coping's east arris
                    colour = _speckle(shade(base, k), rng)
                canvas.put(x, y, colour)
    # Where it comes out of the pillar's face: a line of shadow
    for x in range(cx + BAND_LEFT - 1, cx + BAND_RIGHT + SIDE_FACE + 1):
        canvas.put(x, top, shade(pal.mortar, 0.85))
    return canvas.surface


# ---------------------------------------------------------------------------
# Pieces, preview and saving
# ---------------------------------------------------------------------------

def paint(piece, pal=PALETTE):
    rng = random.Random(zlib.crc32(f'{piece.style.name}/{piece.key}'.encode()))
    if piece.orientation == HORIZONTAL:
        return paint_horizontal(piece.raster, rng, pal)
    return paint_vertical(piece.raster, rng, pal)


def planned(style):
    """[(piece, (x, y) of its first post in tiles)], as the style's plan or one of each piece side by side."""
    if style.plan:
        return [(style.piece(o, n), (x, y)) for o, n, x, y in style.plan]
    placed, x = [], 0
    for piece in style.pieces():
        placed.append((piece, (x, 2)))
        x += piece.raster.size[0] + 1
    return placed


def compose(style, sprites, grass=(96, 140, 70), line=(88, 130, 64)):
    """The pieces laid as planned, sorted as the game sorts buildings: lower bottom edge in front."""
    laid = []
    for piece, (x, y) in planned(style):
        sx, sy = piece.raster.start
        laid.append(((round((x - sx) * TILE), round((y - sy) * TILE)), sprites[piece.key]))
    margin = TILE
    left = min(at[0] for at, _ in laid) - margin
    top = min(at[1] for at, _ in laid) - margin
    w = max(at[0] + s.get_width() for at, s in laid) + margin - left
    h = max(at[1] + s.get_height() for at, s in laid) + margin - top
    out = pygame.Surface((w, h))
    out.fill(grass)
    for gx in range(-left % TILE, w, TILE):
        pygame.draw.line(out, line, (gx, 0), (gx, h))
    for gy in range(-top % TILE, h, TILE):
        pygame.draw.line(out, line, (0, gy), (w, gy))
    for (x, y), sprite in sorted(laid, key=lambda e: (e[0][1] + e[1].get_height(), e[0][0])):
        out.blit(sprite, (x - left, y - top))
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('style', help="the style's folder name, e.g. churchyard_wall")
    parser.add_argument('--preview', help='write the plan laid out with the painted pieces to this PNG')
    parser.add_argument('--zoom', type=int, default=3, help="the preview's scale (default 3)")
    parser.add_argument('--write', action='store_true', help="save the pieces into the style's folder")
    args = parser.parse_args(argv)
    pygame.init()
    pygame.display.set_mode((1, 1))
    style = next((s for s in find_styles() if s.name == args.style), None)
    if style is None:
        sys.exit(f'No fence style {args.style!r}')
    if style.material.key != 'stone' or style.posts_every > 0:
        sys.exit(f'{style.title} is not a stone wall with pillars at its ends only')
    pieces = list(style.pieces())
    sprites = {p.key: paint(p) for p in pieces}
    if args.preview:
        plan = compose(style, sprites)
        plan = pygame.transform.scale(plan, (plan.get_width() * args.zoom, plan.get_height() * args.zoom))
        pygame.image.save(plan, args.preview)
        print(f'Preview: {args.preview}')
    if args.write:
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        for piece in pieces:
            old = piece.sprite() if piece.exists() else None
            if old is not None and pygame.image.tobytes(old, 'RGBA') == pygame.image.tobytes(
                    sprites[piece.key], 'RGBA'):
                print(f'{piece.path.name} is as painted')
                continue
            if old is not None:
                kept = style.out_dir / 'replaced' / f'{piece.path.stem}_{stamp}.png'
                kept.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(piece.path, kept)
            piece.save(sprites[piece.key])
            print(f'Saved {piece.path.name}')


if __name__ == '__main__':
    main()
