"""Paints a wooden rail fence's pieces and its gate pixel by pixel, without the image model.

A field fence (fences.py, material wood): round posts of split logs with two
rails between them, painted on exactly the rasters its pieces are saved on,
as stone_wall_painter.py paints the churchyard's wall (its Canvas, shade and
jitter are shared; the paint-pixel-sprite skill has the tricks):

- a horizontal piece: posts spread evenly along it about every Look.post_spacing
  tiles (both ends included, so a piece is closed off by a post wherever it
  ends: at a corner, a gate or its last post), the rails behind them;
- a vertical piece: seen from above, its rails show as one band running down
  the picture, the top of the rail lit and its side face east of it in shade,
  with the posts between under it. It has no end posts of its own: its ends
  meet the horizontal pieces' corner posts, at the top coming out in front of
  the post, at the bottom stopping where that post's top begins, so it looks
  right whichever of the two the game draws last.

It is "not always perfect": every post a little taller or shorter and some
leaning a pixel, the rails sagging or set askew by a pixel, now and then a
rail slipped off its nail at one end, a split or a knot, each board its own
shade of weathered wood. A piece's look is drawn from a random.Random seeded
by the style and the piece, so painting again gives the same picture.

The gate (--gate NAME) is a farm gate of two wooden leaves for a 2-tile gap
between two of its posts, shut and swung open either way, on the canvas
iron_gate_painter.py uses (place_fence.py's GATE_PROPS fit both).

    python wood_fence_painter.py field_fence --preview plan.png       # look first
    python wood_fence_painter.py field_fence --write --gate field_gate
    python wood_fence_painter.py chicken_fence --write --gate chicken_gate --side-gate chicken_side_gate

--side-gate paints a one-leaf gate for a 2-tile gap in a vertical run (paint_side_gate), shut and open
into the yard to the east; place_fence.py --side-gate lays it.

--write keeps the pieces it replaces in build_tools/output/fences/<style>/replaced/.
"""

import argparse
import math
import os
import random
import shutil
import sys
import zlib
from dataclasses import dataclass, replace
from datetime import datetime

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
import itertools

import pygame
from fences import HORIZONTAL, TILE, find_styles
from iron_gate_painter import GATES_DIR, place_leaf
from stone_wall_painter import Canvas, compose, jitter, shade

BAND = (-1, 0)          # a vertical piece's rail tops about the run's centre, its side face east of them
SIDE_FACE = 1
GROUND_SHADOW = (58, 40, 22)


@dataclass(frozen=True)
class Palette:
    rail: tuple = (150, 106, 66)
    post: tuple = (118, 82, 50)
    end_grain: tuple = (178, 146, 104)
    outline: tuple = (56, 37, 22)
    grey: tuple = (128, 117, 101)       # wood weathered silver


PALETTE = Palette()


@dataclass(frozen=True)
class Look:
    """A style's build. Heights in game pixels above (minus) the run's foot line (Raster.start's y)."""
    post_top: int = -29             # a post's top, give or take post_top_spread
    post_top_spread: int = 2
    post_across: tuple = (0.60, 1.14, 1.06, 0.98, 0.88, 0.76, 0.56)  # across a round post, lit from the left
    leans: tuple = (-1, 0, 0, 0, 1)                 # a post's lean in px, drawn from
    rails: tuple = (-24, -13)       # each rail's top row, top to bottom
    rail_rows: tuple = (1.16, 1.03, 0.93, 0.78)  # a rail's rows, lit top to its shaded underside, an outline under
    sags: tuple = (0, 0, 0, 1, 1)
    post_spacing: int = 2           # tiles between posts, about
    slip_chance: float = 0.07       # a rail slipped off its nail at one end
    crack_chance: float = 0.18
    knot_chance: float = 0.25
    grey_chance: float = 0.18       # a board weathered grey
    split_chance: float = 0.3       # a post split down its length
    palette: Palette = PALETTE

    @property
    def post_half(self):
        """A post is 2 * post_half + 1 px wide."""
        return len(self.post_across) // 2


FIELD = Look()
# A weak fence for a chicken pen: lower, thin sticks of posts, three thin rails close enough to keep
# chickens in, the wood older and greyer, sagging and slipping more often.
CHICKEN = Look(post_top=-24, post_top_spread=2, post_across=(0.62, 1.10, 0.98, 0.84, 0.60),
               leans=(-1, -1, 0, 0, 0, 1, 1), rails=(-21, -13, -6), rail_rows=(1.14, 0.98, 0.78),
               sags=(0, 0, 1, 1, 1, 2), slip_chance=0.12, crack_chance=0.22, knot_chance=0.15,
               grey_chance=0.45, split_chance=0.2,
               palette=Palette(rail=(156, 118, 80), post=(124, 92, 62), end_grain=(176, 150, 116),
                               outline=(60, 44, 30), grey=(136, 128, 114)))
LOOKS = {'field_fence': FIELD, 'chicken_fence': CHICKEN}


def _wood(pal, rng, base, grey_chance=FIELD.grey_chance):
    """A board's own colour: a little lighter or darker, warmer or cooler, now and then weathered grey."""
    colour = jitter(shade(base, rng.uniform(0.92, 1.07)), rng, 4)
    if rng.random() < grey_chance:
        g = rng.uniform(0.25, 0.5)
        colour = tuple(round(c * (1 - g) + w * g) for c, w in zip(colour, pal.grey))
    return colour


def _grain(colour, rng):
    roll = rng.random()
    if roll < 0.07:
        return shade(colour, 0.90)
    if roll < 0.10:
        return shade(colour, 1.06)
    return colour


def post_spots(length, spacing=FIELD.post_spacing):
    """Where the posts stand along a piece, in px from its first post: evenly, both ends included."""
    bays = max(1, round(length / spacing))
    return [round(i * length * TILE / bays) for i in range(bays + 1)]


# ---------------------------------------------------------------------------
# The parts
# ---------------------------------------------------------------------------

def paint_post(canvas, rng, look, cx, foot, end=False):
    """An upright post standing on (cx, foot): a round log, its cut top lighter, leaning a pixel at times.

    An end post (a corner's or a gate's) stands upright at look.post_top exactly, so the vertical pieces
    and the gate meeting it know where it is."""
    pal, half = look.palette, look.post_half
    spread = rng.randint(-look.post_top_spread, look.post_top_spread)
    lean = rng.choice(look.leans)
    if end:
        spread = lean = 0
    top = foot + look.post_top + spread
    base = _wood(pal, rng, pal.post, look.grey_chance)
    height = foot - top
    for y in range(top, foot + 1):
        shift = round(lean * (foot - y) / height)
        for i, k in enumerate(look.post_across):
            dx = i - half
            if y == top and abs(dx) == half:
                continue                                  # a rounded top
            if y == top:
                colour = pal.outline if abs(dx) == half - 1 else shade(pal.end_grain, 1.02 - 0.04 * dx)
            elif y == top + 1 and abs(dx) < half:
                colour = shade(pal.end_grain, 0.86 - 0.04 * dx)
            elif abs(dx) == half:
                colour = shade(pal.outline, 1.2 if dx < 0 else 1.0)
            else:
                colour = _grain(shade(base, k * (1.0 - 0.10 * (y - top) / height)), rng)
            canvas.put(cx + dx + shift, y, colour)
    for dx in range(-half - 1, half + 2):                  # seated in the grass
        canvas.put(cx + dx, foot + 1, pal.outline, 120 if abs(dx) > half else 200)
    if rng.random() < look.split_chance:                   # a split down the post
        x = cx + rng.choice((-1, 0, 1))
        y0 = rng.randint(top + 4, foot - 12)
        for y in range(y0, y0 + rng.randint(4, 9)):
            canvas.put(x + round(lean * (foot - y) / height), y, shade(base, 0.62))


def paint_rail(canvas, rng, look, x0, x1, top):
    """A rail between two posts' centres, its top row at `top`: sagging, askew, at times slipped."""
    pal = look.palette
    base = _wood(pal, rng, pal.rail, look.grey_chance)
    sag = rng.choice(look.sags)
    tilt = rng.choice((-1, 0, 0, 0, 0, 1))
    slip = 0
    if rng.random() < look.slip_chance:
        slip = rng.choice((-1, 1)) * rng.randint(3, 5)     # its left (-) or right (+) end come down
    crack = None
    if rng.random() < look.crack_chance and x1 - x0 > 30:
        a = rng.randint(x0 + 8, x1 - 22)
        crack = (a, a + rng.randint(7, 14), rng.choice((1, 2)))
    knot = rng.randint(x0 + 6, x1 - 6) if rng.random() < look.knot_chance else None
    span = max(1, x1 - x0)
    for x in range(x0, x1 + 1):
        u = (x - x0) / span
        dy = round(sag * 4 * u * (1 - u) + tilt * u)
        if slip > 0:
            dy += round(slip * u * u)
        elif slip < 0:
            dy += round(-slip * (1 - u) ** 2)
        for r, k in enumerate(look.rail_rows):
            colour = _grain(shade(base, k), rng)
            if crack and crack[0] <= x < crack[1] and r == min(crack[2], len(look.rail_rows) - 2):
                colour = shade(base, 0.6)
            if knot is not None and abs(x - knot) <= 1 and r in (1, 2):
                colour = shade(base, 0.7 if x == knot else 0.84)
            canvas.put(x, top + dy + r, colour)
        canvas.put(x, top + dy + len(look.rail_rows), pal.outline, 220)
        canvas.put(x, top + dy - 1, shade(pal.outline, 1.3), 150)


def ground_line(canvas, x0, x1, y, alphas=GROUND_SHADOW):
    """The rails' shadow on the grass under them, falling a little to the south-east."""
    for x in range(x0, x1 + 1):
        for i, alpha in enumerate(alphas):
            canvas.put(x, y + i, (20, 26, 12), alpha // 2)


# ---------------------------------------------------------------------------
# Pieces
# ---------------------------------------------------------------------------

def paint_horizontal(raster, rng, look):
    canvas = Canvas(raster.pixels)
    sx, sy = raster.start
    left, foot = round(sx * TILE), round(sy * TILE)
    spots = [left + s for s in post_spots(raster.length, look.post_spacing)]
    ground_line(canvas, spots[0], spots[-1], foot + 2)
    for a, b in itertools.pairwise(spots):
        for rail in look.rails:
            paint_rail(canvas, rng, look, a, b, foot + rail)
    for i, x in enumerate(spots):
        paint_post(canvas, rng, look, x, foot, end=i in (0, len(spots) - 1))
    return canvas.surface


def paint_vertical(raster, rng, look):
    """The rails' band down the picture with the posts between its ends over it; no end posts of its own.

    Seen from above the two rails of a north-south run fall on one line, so they show as one narrow band,
    its top lit and a pixel of side face east of it. The posts are drawn over it, whole, so the run reads as
    posts and rails; it keeps off its corner posts' pixels at both ends (Canvas.skip) and shows from their
    feet on, whichever of the pieces the game draws last. Beside a gap in the run the side gate's
    gateposts stand where its end posts would (paint_side_gate)."""
    pal = look.palette
    canvas = Canvas(raster.pixels)
    sx, sy = raster.start
    cx, first = round(sx * TILE), round(sy * TILE)
    spots = [first + s for s in post_spots(raster.length, look.post_spacing)]
    last = spots[-1]
    # Its shadow on the grass, east of the run
    for y in range(first + 3, last - 2):
        for i, alpha in enumerate(GROUND_SHADOW):
            canvas.put(cx + BAND[1] + SIDE_FACE + 2 + i, y, (20, 26, 12), alpha)
    corner = look.post_half + 2
    canvas.skip = lambda x, y: abs(x - cx) <= corner and (
        y <= first + 1 or y >= last + look.post_top)
    high, low = look.rails[0], look.rails[-1]
    top, bottom = first + high, last + low
    bays = list(itertools.pairwise(spots))
    for i, (a, b) in enumerate(bays):
        base = _wood(pal, rng, pal.rail, look.grey_chance)
        wobble = rng.choice((0, 0, 0, -1, 1))
        y0 = top if i == 0 else a + high
        y1 = bottom if i == len(bays) - 1 else b + low
        crack = None
        if rng.random() < look.crack_chance:
            c = rng.randint(y0 + 30, max(y0 + 31, y1 - 16))
            crack = (c, c + rng.randint(6, 12))
        for y in range(y0, y1):
            for x in range(cx + BAND[0] - 1, cx + BAND[1] + SIDE_FACE + 2):
                if x == cx + BAND[0] - 1:
                    colour = pal.outline
                elif x == cx + BAND[1] + SIDE_FACE + 1:
                    colour = shade(pal.outline, 1.1)
                elif x > cx + BAND[1]:                       # the rail's side face, in shade
                    colour = shade(base, 0.68)
                else:
                    colour = _grain(shade(base, 1.16 if x == cx + BAND[0] else 1.0), rng)
                    if crack and crack[0] <= y < crack[1]:
                        colour = shade(base, 0.62)
                canvas.put(x + wobble, y, colour)
    canvas.skip = None
    for foot in spots[1:-1]:
        paint_post(canvas, rng, look, cx, foot)
    return canvas.surface


def look_of(style_name):
    return LOOKS.get(style_name, FIELD)


def paint(piece):
    look = look_of(piece.style.name)
    rng = random.Random(zlib.crc32(f'{piece.style.name}/{piece.key}'.encode()))
    if piece.orientation == HORIZONTAL:
        return paint_horizontal(piece.raster, rng, look)
    # Beside a gap in a vertical run the gate's own gateposts stand (paint_side_gate), not the run's
    return paint_vertical(piece.raster, rng, look)


# ---------------------------------------------------------------------------
# The gate: two wooden leaves between two posts 2 tiles apart
# ---------------------------------------------------------------------------

GATE_SIZE = (64, 96)
GATE_FOOT = 64                       # the run's foot line on the gate's canvas
GATE_RAILS = (-22, -14, -6)          # each rail's top row, 3 rows deep
GATE_TOP = -23
OPEN_ANGLE = 80


def hinges(look=FIELD):
    """x of each leaf's hinge on the gate's canvas, just inside its post."""
    return look.post_half + 1, GATE_SIZE[0] - look.post_half - 2


def leaf_length(look=FIELD):
    """px, hinge to where the leaves meet (28 for the field gate)."""
    a, b = hinges(look)
    return (b - a + 1) // 2


def gate_leaf(pal, seed, look=FIELD, length=None):
    """One leaf flat, as the left one: {(along, y): colour}, along 0 at the hinge. Stiles at both ends,
    three rails and a brace from the hinge's foot up to the far top, as on a farm gate. `length` in px,
    hinge to its far end; by default half the gateway."""
    GATE_LEAF = length or leaf_length(look)
    rng = random.Random(seed)
    base = _wood(pal, rng, pal.rail, look.grey_chance)
    px = {}
    for u in range(GATE_LEAF):
        stile = u < 2 or u >= GATE_LEAF - 2
        if stile:
            for y in range(GATE_FOOT + GATE_TOP, GATE_FOOT):
                k = 1.08 if u in (0, GATE_LEAF - 2) else 0.80
                px[(u, y)] = _grain(shade(base, k * 0.95), rng)
            px[(u, GATE_FOOT + GATE_TOP)] = shade(pal.end_grain, 0.95)
            continue
        for top in GATE_RAILS:
            for r, k in enumerate((1.14, 0.98, 0.80)):
                px[(u, GATE_FOOT + top + r)] = _grain(shade(base, k), rng)
            px[(u, GATE_FOOT + top + 3)] = pal.outline
    # The brace, two px thick, over the rails
    y_low, y_high = GATE_FOOT - 4, GATE_FOOT + GATE_TOP + 2
    for u in range(2, GATE_LEAF - 2):
        y = round(y_low + (y_high - y_low) * (u - 2) / (GATE_LEAF - 5))
        px[(u, y)] = shade(base, 1.1)
        px[(u, y + 1)] = shade(base, 0.86)
        px[(u, y + 2)] = pal.outline
    for top in (GATE_RAILS[0], GATE_RAILS[2]):              # iron hinge straps
        for u in range(5):
            px[(u, GATE_FOOT + top + 1)] = (52, 50, 54) if u else (96, 94, 100)
    px[(GATE_LEAF - 3, GATE_FOOT - 15)] = (96, 94, 100)    # the latch
    px[(GATE_LEAF - 3, GATE_FOOT - 14)] = (52, 50, 54)
    return px


def paint_gate(state, look=FIELD):
    """'closed', 'open_down' or 'open_up'."""
    pal = look.palette
    HINGES = hinges(look)
    surface = pygame.Surface(GATE_SIZE, pygame.SRCALPHA)
    leaves = (gate_leaf(pal, 11, look), gate_leaf(pal, 23, look))
    if state == 'closed':
        for x in range(HINGES[0], HINGES[1] + 1):
            for i, alpha in enumerate(GROUND_SHADOW[:2]):
                surface.set_at((x, GATE_FOOT + 1 + i), (20, 26, 12, alpha))
        place_leaf(surface, leaves[0], HINGES[0], +1, 0, 0)
        place_leaf(surface, leaves[1], HINGES[1], -1, 0, 0)
    else:
        swing = 1 if state == 'open_down' else -1
        place_leaf(surface, leaves[0], HINGES[0], +1, OPEN_ANGLE, swing)
        place_leaf(surface, leaves[1], HINGES[1], -1, OPEN_ANGLE, swing)
    return surface


GATE_STATES = ('closed', 'open_down', 'open_up')


# ---------------------------------------------------------------------------
# A side gate: one leaf in a 2-tile gap of a vertical run
# ---------------------------------------------------------------------------
# Seen from above a north-south run's leaf shut shows only as a band down the picture, like the run;
# swung open into the yard (east) it shows its face. It is one leaf, hinged on the north post, so its
# drawing order can be that post's foot line: whoever walks through the gap is south of the open leaf
# and drawn over it (two leaves would want two orders).

SIDE_GATE_SIZE = (96, 128)           # 3 x 4 tiles
SIDE_HINGE = (16, 48)                # the north post's foot on the canvas (the run's centre line)
SIDE_GAP = 2 * TILE                  # post foot to post foot
SIDE_OPEN_ANGLE = 80                 # from shut (along the run) towards the east
SIDE_STATES = ('closed', 'open')
GATEPOST_RISE = 8                    # px a gatepost stands above the run's posts
IRON, IRON_LIT = (52, 50, 54), (112, 110, 118)


def side_leaf_length(look=FIELD):
    """px from just south of the north post to just north of the south one."""
    return SIDE_GAP - 2 * (look.post_half + 1)


def gatepost_look(look):
    """A gatepost: stouter than the run's posts (the field fence's girth) and GATEPOST_RISE taller, of
    wood less weathered, so from above the gap reads as a gateway even where the shut leaf is a band."""
    pal = look.palette
    return replace(look, post_across=FIELD.post_across, post_top=look.post_top - GATEPOST_RISE,
                   split_chance=0.0, palette=replace(pal, post=shade(pal.post, 0.92)))


def paint_gateposts(canvas, look):
    """The gap's two posts, on the run's centre line at the hinge's foot and SIDE_GAP south of it."""
    hx, hy = SIDE_HINGE
    big = gatepost_look(look)
    rng = random.Random(53)
    for foot in (hy, hy + SIDE_GAP):
        paint_post(canvas, rng, big, hx, foot, end=True)
        top = foot + big.post_top
        for dx in range(-big.post_half, big.post_half + 1):        # an iron band under the cut top
            canvas.put(hx + dx, top + 4, IRON_LIT if dx < 0 else IRON)


def paint_side_gate(state, look=FIELD):
    """'closed' (a band down the gap) or 'open' (its face, swung east), between two gateposts.

    Shut, the leaf seen from above falls on one line like the rails, so it is told from them otherwise:
    a band a pixel wider than the rails, of fresher wood and outlined darker, with iron hinge straps on its
    face at the north end and a latch at the south, between gateposts that stand out of the run."""
    pal = look.palette
    canvas = Canvas(SIDE_GATE_SIZE)
    hx, hy = SIDE_HINGE
    start = look.post_half + 1                       # the leaf's hinge end, just clear of the post
    length = side_leaf_length(look)
    px = gate_leaf(pal, 37, look, length)
    if state == 'closed':
        rng = random.Random(41)
        base = jitter(shade(pal.rail, 1.08), rng, 3)                    # fresher than the weathered run
        left, face = hx + BAND[0] - 1, hx + BAND[1] + 1                 # outline, then the lit tops to face
        right = face + 2                                                # a two-px side face, then outline
        y0, y1 = hy + start + GATE_TOP, hy + start + length + GATE_RAILS[-1]
        for y in range(hy + start + 3, hy + start + length - 2):      # its shadow, east of it
            for i, alpha in enumerate(GROUND_SHADOW):
                canvas.put(right + 1 + i, y, (20, 26, 12), alpha)
        for y in range(y0, y1):
            for x in range(left, right + 1):
                if x == left:
                    colour = shade(pal.outline, 0.8)
                elif x == right:
                    colour = shade(pal.outline, 0.9)
                elif x >= face:
                    colour = shade(base, 0.74 if x == face else 0.62)
                else:
                    colour = _grain(shade(base, 1.2 if x == left + 1 else 1.04), rng)
                canvas.put(x, y, colour)
        # The stiles' cut tops at both ends, lighter, a dark joint under each
        for u in (0, length - 2):
            for x in range(left + 1, face):
                canvas.put(x, hy + start + u + GATE_TOP, shade(pal.end_grain, 1.02))
            for x in range(left + 1, right):
                canvas.put(x, hy + start + u + GATE_TOP + 2, shade(base, 0.55))
        # Iron hinge straps on its face at the top and bottom rails, from the hinge end, and the latch
        for rail in (GATE_RAILS[0], GATE_RAILS[2]):
            for u in range(6):
                y = hy + start + u + rail + 1
                canvas.put(face, y, IRON_LIT)
                canvas.put(face + 1, y, IRON)
        ly = hy + start + length - 15
        for x, y, c in ((face, ly, IRON_LIT), (face + 1, ly, IRON_LIT), (right, ly, IRON_LIT),
                        (right + 1, ly, IRON), (face + 1, ly + 1, IRON), (right, ly + 1, IRON)):
            canvas.put(x, y, c)
        paint_gateposts(canvas, look)
        return canvas.surface
    cos, sin = math.cos(math.radians(SIDE_OPEN_ANGLE)), math.sin(math.radians(SIDE_OPEN_ANGLE))
    for u in range(length):                          # nearer (farther south) columns last
        x, dy = hx + start + round(u * sin), round(u * cos)
        for i, alpha in enumerate(GROUND_SHADOW[:2]):
            canvas.put(x, hy + dy + 1 + i, (20, 26, 12), alpha // 2)
        for (cu, y), colour in px.items():
            if cu == u:
                canvas.put(x, hy + dy + (y - GATE_FOOT), colour)
    paint_gateposts(canvas, look)
    return canvas.surface


# ---------------------------------------------------------------------------
# Preview and saving
# ---------------------------------------------------------------------------

def plan_pieces(style):
    """Every piece the style's plan names, else the lengths of its fence.json."""
    if style.plan:
        return sorted({style.piece(o, n) for o, n, _, _ in style.plan}, key=lambda p: p.key)
    return list(style.pieces())


def gaps(style):
    """(x, y) in tiles of every 2-tile gap between the horizontal pieces of a row."""
    rows = {}
    for o, n, x, y in style.plan:
        if o == HORIZONTAL:
            rows.setdefault(y, []).append((x, n))
    out = []
    for y, pieces in rows.items():
        pieces.sort()
        out += [(ax + an, y) for (ax, an), (bx, _) in itertools.pairwise(pieces) if bx - (ax + an) == 2]
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('style', help="the style's folder name, e.g. field_fence")
    parser.add_argument('--preview', help='write the plan laid out with the painted pieces to this PNG')
    parser.add_argument('--zoom', type=int, default=2, help="the preview's scale (default 2)")
    parser.add_argument('--open', action='store_true', help='show the gates open in the preview')
    parser.add_argument('--write', action='store_true', help="save the pieces into the style's folder")
    parser.add_argument('--gate', help='also paint a gate of this name into houses/gates/ (with --write)')
    parser.add_argument('--side-gate', help='also paint a one-leaf gate for a gap in a vertical run, '
                        'houses/gates/<name>_closed.png and _open.png (with --write)')
    args = parser.parse_args(argv)
    pygame.init()
    pygame.display.set_mode((1, 1))
    style = next((s for s in find_styles() if s.name == args.style), None)
    if style is None:
        sys.exit(f'No fence style {args.style!r}')
    if style.material.key != 'wood':
        sys.exit(f'{style.title} is not a wooden fence')
    pieces = plan_pieces(style)
    sprites = {p.key: paint(p) for p in pieces}
    gate_pictures = {s: paint_gate(s, look_of(style.name)) for s in GATE_STATES}
    if args.preview:
        plan = compose(style, sprites)
        # The gates, on the plan as the game puts them: the canvas's left edge on the left post
        margin = TILE
        laid = [((round((x - p.raster.start[0]) * TILE), round((y - p.raster.start[1]) * TILE)))
                for p, (x, y) in [(style.piece(o, n), (x, y)) for o, n, x, y in style.plan]]
        left = min(x for x, _ in laid) - margin
        top = min(y for _, y in laid) - margin
        picture = gate_pictures['open_down' if args.open else 'closed']
        for gx, gy in gaps(style):
            plan.blit(picture, (gx * TILE - left, gy * TILE - GATE_FOOT - top))
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
        if args.gate:
            GATES_DIR.mkdir(parents=True, exist_ok=True)
            for state, picture in gate_pictures.items():
                path = GATES_DIR / f'{args.gate}_{state}.png'
                pygame.image.save(picture, str(path))
                print(f'Saved {path.name}')
        if args.side_gate:
            GATES_DIR.mkdir(parents=True, exist_ok=True)
            for state in SIDE_STATES:
                path = GATES_DIR / f'{args.side_gate}_{state}.png'
                pygame.image.save(paint_side_gate(state, look_of(style.name)), str(path))
                print(f'Saved {path.name}')


if __name__ == '__main__':
    main()
