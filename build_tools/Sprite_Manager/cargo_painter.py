"""Paints the harbour cranes' cargo pixel by pixel: the loads, the hook block and the barge.

The cranes (src/models/crane_hoist.py) hoist loads between a barge under the
jib and the jib (or the Great Crane's hood). Their pictures are painted here,
deterministic, at twice their world size (``RES``), and drawn by the game at
half that, as the upscaled buildings are, so they stay crisp zoomed in:

- ``crate``, ``sacks`` (three sacks in a cargo net), ``barrel``, ``bale``: one
  picture each, as big as ``LOAD_SIZES`` says, the load's top edge at the
  picture's top, where the sling's two ropes meet it;
- ``hook``: the hook block (two wooden cheeks on an iron strap) and the iron
  hook under it, its top centre where the rope ends;
- ``barge_back`` and ``barge_front``: a lighter, a small open cargo barge,
  seen from the side as everything on the map is. The back holds the inside
  of its far side (and its floor's shadow), the front its near side with the
  waterline; the game draws the loads standing in it between the two, so the
  near side hides their feet. Its waterline is ``BARGE_WATERLINE`` px from the
  picture's top, its middle at the picture's middle.

Light comes from the upper left, every colour is a palette colour times a
shade, and each picture's grain is drawn from a random.Random seeded by its
name, so painting again gives the same bytes.

    python build_tools/Sprite_Manager/cargo_painter.py --preview out.png   # look first
    python build_tools/Sprite_Manager/cargo_painter.py --write             # into assets/map_sprites/cranes/
"""

import argparse
import math
import os
import random
import sys
import zlib

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
import pygame  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, ROOT)
from src.models.crane_hoist import BARGE_FLOOR_ABOVE_WATER, LOAD_SIZES  # noqa: E402

OUT_DIR = os.path.join(ROOT, 'assets', 'map_sprites', 'cranes')
RES = 2                      # picture pixels per world pixel

OUTLINE = (30, 20, 15)
PINE = (156, 112, 66)        # the crate's boards
OAK = (122, 80, 46)          # the barrel's staves
IRON = (66, 66, 76)
BURLAP = (176, 150, 120)
BURLAP_DARK = (150, 112, 78)
NET = (92, 70, 44)
CLOTH = (188, 170, 134)      # the bale's wrapping
CORD = (104, 74, 44)
TAR = (64, 44, 32)           # the barge's hull
TAR_LIGHT = (92, 66, 44)
GUNWALE = (112, 80, 50)
INNER = (96, 68, 44)

#: The barge, world px: its length, how high its sides stand and where its waterline is in the picture
BARGE_LENGTH = 150
BARGE_SIDE = 13              # the near side's top above the waterline, amidships
BARGE_FAR_SIDE = 25          # the far side's top above the waterline (seen higher, being further off)
BARGE_SHEER = 6              # how much higher the ends rise
BARGE_WATERLINE = 34         # the waterline, px from the picture's top (world)
BARGE_HEIGHT = 40


def shade(colour, k):
    return tuple(max(0, min(255, round(v * k))) for v in colour)


def jitter(colour, rng, spread=4):
    warm = rng.uniform(-spread, spread)
    return tuple(max(0, min(255, round(v + d))) for v, d in zip(colour, (warm, warm * 0.6, -warm * 0.4)))


class Canvas:
    """A picture painted pixel by pixel; outline() rings what is painted in a dark line."""

    def __init__(self, w, h):
        self.surface = pygame.Surface((w, h), pygame.SRCALPHA)
        self.w, self.h = w, h

    def put(self, x, y, colour, alpha=255):
        x, y = int(x), int(y)
        if 0 <= x < self.w and 0 <= y < self.h:
            if alpha >= 255:
                self.surface.set_at((x, y), (*colour, 255))
            else:
                r, g, b, a = self.surface.get_at((x, y))
                k = alpha / 255
                if a == 0:
                    self.surface.set_at((x, y), (*colour, alpha))
                else:
                    self.surface.set_at((x, y), (round(r + (colour[0] - r) * k), round(g + (colour[1] - g) * k),
                                                 round(b + (colour[2] - b) * k), max(a, alpha)))

    def get(self, x, y):
        return self.surface.get_at((x, y))

    def painted(self, x, y):
        return 0 <= x < self.w and 0 <= y < self.h and self.surface.get_at((x, y))[3] > 0

    def darken(self, x, y, k):
        if self.painted(x, y):
            r, g, b, a = self.surface.get_at((x, y))
            self.surface.set_at((x, y), (*shade((r, g, b), k), a))

    def outline(self, colour=OUTLINE):
        edge = [(x, y) for y in range(self.h) for x in range(self.w) if self.painted(x, y) and any(
            not self.painted(x + dx, y + dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))]
        for x, y in edge:
            self.put(x, y, colour)

    def speckle(self, rng, dark=0.06, light=0.03):
        for y in range(self.h):
            for x in range(self.w):
                if self.painted(x, y):
                    r = rng.random()
                    if r < dark:
                        self.darken(x, y, 0.92)
                    elif r < dark + light:
                        self.darken(x, y, 1.06)


def rng_for(name):
    return random.Random(zlib.crc32(name.encode()))


# --- the loads -------------------------------------------------------------------------------------

def paint_crate():
    rng = rng_for('crate')
    w, h = (v * RES for v in LOAD_SIZES['crate'])
    c = Canvas(w, h)
    top = 7                                   # the lid seen from above
    boards = 4
    board_h = (h - top) / boards
    for b in range(boards):
        tone = jitter(shade(PINE, rng.uniform(0.92, 1.05)), rng)
        y0, y1 = round(top + b * board_h), round(top + (b + 1) * board_h)
        for y in range(y0, y1):
            k = 1.08 if y == y0 else (0.86 if y == y1 - 1 else 1.0)
            k *= 1.0 - 0.10 * (y - top) / (h - top)          # darker towards the bottom
            for x in range(w):
                kx = 1.05 if x < 3 else (0.88 if x > w - 4 else 1.0)
                c.put(x, y, shade(tone, k * kx))
    for y in range(top):                                     # the lid, lit
        for x in range(w):
            c.put(x, y, shade(PINE, 1.18 - 0.03 * y))
    # The frame: battens down both ends and a brace across
    batten = 5
    for x0 in (0, w - batten):
        for y in range(top, h):
            for x in range(x0, x0 + batten):
                c.put(x, y, shade(PINE, (0.80 if x0 else 0.95) - 0.08 * (y - top) / h + (0.08 if x == x0 else 0)))
    for i in range(w - 2 * batten):
        t = i / (w - 2 * batten)
        y = round(h - 3 - t * (h - top - 6))
        for d in range(-2, 2):
            c.put(batten + i, y + d, shade(PINE, 0.84 if d == 1 else 0.98))
    # Nails in the battens
    for x0 in (2, w - 3):
        for y in (top + 3, h - 4):
            c.put(x0, y, IRON)
    for y in range(top, top + 2):                            # the lid's shadow on the front
        for x in range(w):
            c.darken(x, y, 0.80)
    c.speckle(rng)
    c.outline()
    return c.surface


def _sack(c, cx, cy, rx, ry, colour, rng):
    """A sack lying on its side: an oval lit from the upper left, a seam and a tied neck."""
    for y in range(round(cy - ry), round(cy + ry) + 1):
        for x in range(round(cx - rx), round(cx + rx) + 1):
            dx, dy = (x - cx) / rx, (y - cy) / ry
            d = dx * dx + dy * dy
            if d <= 1.0:
                k = 1.12 - 0.22 * (dx * 0.5 + dy * 0.8 + 0.6) - 0.15 * d
                c.put(x, y, shade(colour, k))
    for y in range(round(cy - ry * 0.6), round(cy + ry * 0.6)):  # a seam
        c.darken(round(cx + rx * 0.55), y, 0.85)


def paint_sacks():
    rng = rng_for('sacks')
    w, h = (v * RES for v in LOAD_SIZES['sacks'])
    c = Canvas(w, h)
    _sack(c, w * 0.30 + 2, h * 0.70, w * 0.26, h * 0.25, jitter(BURLAP, rng), rng)
    _sack(c, w * 0.72, h * 0.70, w * 0.25, h * 0.25, jitter(BURLAP_DARK, rng), rng)
    _sack(c, w * 0.52, h * 0.34, w * 0.30, h * 0.26, jitter(BURLAP, rng), rng)
    c.speckle(rng, 0.10, 0.05)
    c.outline()
    # The cargo net over them: a mesh of diamonds, its cords drawn over the sacks only
    mesh = 10
    for y in range(4, h):
        for x in range(w):
            if c.painted(x, y) and c.get(x, y)[:3] != OUTLINE and ((x + y) % mesh == 0 or (x - y) % mesh == 0):
                c.put(x, y, NET)
                c.darken(x + 1, y + 1, 0.9)       # the cord's shadow on the sackcloth
    for x in range(w // 2 - 1, w // 2 + 2):     # the net's gathered top, up to the sling
        for y in range(3, round(h * 0.2)):
            if c.painted(x, y) or y < 6:
                c.put(x, y, shade(NET, 1.0 if x < w // 2 + 1 else 0.8))
    for x in range(w // 2 - 3, w // 2 + 4):            # the knot where the sling takes it
        for y in range(0, 4):
            c.put(x, y, shade(NET, 0.85 if y > 1 else 1.0))
    return c.surface


def paint_barrel():
    rng = rng_for('barrel')
    w, h = (v * RES for v in LOAD_SIZES['barrel'])
    c = Canvas(w, h)
    staves = 7
    top = 6                                            # the head, seen from above
    for y in range(h):
        bulge = 1.0 - 0.13 * ((y - h / 2) / (h / 2)) ** 2
        half = (w / 2) * bulge
        for x in range(round(w / 2 - half), round(w / 2 + half)):
            u = (x - (w / 2 - half)) / (2 * half)      # 0 to 1 across
            stave = int(u * staves)
            k = 1.12 - 0.36 * u + (0.04 if stave % 2 else 0)
            if y < top:
                k = 1.20 - 0.04 * y
            c.put(x, y, shade(OAK, k))
        if y >= top:
            for s in range(1, staves):
                x = round(w / 2 - half + s * 2 * half / staves)
                c.darken(x, y, 0.82)
    for hy in (top + 3, h // 2 - 3, h // 2 + 3, h - 5):  # iron hoops
        for x in range(w):
            for d in range(2):
                if c.painted(x, hy + d):
                    u = x / w
                    c.put(x, hy + d, shade(IRON, (1.25 if d == 0 else 0.95) - 0.3 * u))
    c.put(w // 2 + 3, top + 7, shade(OAK, 0.5))       # the bung
    c.speckle(rng)
    c.outline()
    return c.surface


def paint_bale():
    rng = rng_for('bale')
    w, h = (v * RES for v in LOAD_SIZES['bale'])
    c = Canvas(w, h)
    r = 6
    for y in range(h):
        for x in range(w):
            cx = min(max(x, r), w - 1 - r)
            cy = min(max(y, r), h - 1 - r)
            if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                k = 1.12 - 0.20 * (x / w) - 0.18 * (y / h)
                if y < 7:
                    k += 0.08
                c.put(x, y, shade(CLOTH, k))
    # Folds of the wrapping
    for i in range(6):
        x0 = rng.randrange(8, w - 8)
        y0 = rng.randrange(10, h - 6)
        for d in range(rng.randrange(4, 9)):
            c.darken(x0 + d, y0 + (d // 3), 0.88)
    c.speckle(rng, 0.07, 0.04)
    c.outline()
    # Two cords round it and one along
    for xc in (w // 3, 2 * w // 3):
        for y in range(h):
            for d in (0, 1):
                if c.painted(xc + d, y):
                    c.put(xc + d, y, shade(CORD, 1.1 if d == 0 else 0.85))
    for x in range(w):
        if c.painted(x, 7):
            c.put(x, 7, shade(CORD, 1.0))
    return c.surface


def paint_hook():
    """The hook block and the hook, its top centre where the rope ends: 8 x 13 world px."""
    w, h = 8 * RES + 2, 13 * RES
    c = Canvas(w, h)
    cx = w // 2
    # The block: two wooden cheeks on an iron strap, a sheave's axle in the middle
    for y in range(1, 13):
        for x in range(cx - 6, cx + 6):
            k = 1.10 - 0.25 * (x - cx + 6) / 12 - 0.1 * y / 13
            c.put(x, y, shade((120, 84, 50), k))
    for y in range(0, 14):
        c.put(cx - 1, y, shade(IRON, 1.2))
        c.put(cx, y, shade(IRON, 0.9))
    c.put(cx - 1, 6, (30, 30, 34))
    c.put(cx, 6, (30, 30, 34))
    # The hook: a shank down and a curve back up to its point
    for y in range(13, 19):
        c.put(cx - 1, y, shade(IRON, 1.15))
        c.put(cx, y, shade(IRON, 0.85))
    for a in range(0, 200, 8):
        t = math.radians(a)
        x = cx - 0.5 + 4 * math.cos(math.pi - t)
        y = 20.5 + 4 * math.sin(t)
        c.put(round(x), round(y), shade(IRON, 1.1 - a / 400))
        c.put(round(x), round(y) + 1, shade(IRON, 0.7))
    c.outline()
    return c.surface


# --- the barge -------------------------------------------------------------------------------------

def _sheer(u):
    """How much higher than amidships the barge's sides stand at u (-1 bow to 1 stern), 0 to 1."""
    return abs(u) ** 3


def _hull_bottom(u):
    """How far above the waterline the hull's bottom edge is at u: it rises out of the water at the ends."""
    return max(0.0, (abs(u) - 0.80) / 0.20) * 7


def paint_barge():
    """The barge's back (inner far side) and front (near side), each BARGE_LENGTH x BARGE_HEIGHT world px."""
    rng = rng_for('barge')
    w, h = (BARGE_LENGTH + 4) * RES, BARGE_HEIGHT * RES
    water = BARGE_WATERLINE * RES
    floor = water - BARGE_FLOOR_ABOVE_WATER * RES
    back, front = Canvas(w, h), Canvas(w, h)
    half = BARGE_LENGTH * RES / 2
    mid = w / 2
    planks_back = [jitter(shade(INNER, rng.uniform(0.92, 1.04)), rng) for _ in range(8)]
    planks_front = [jitter(shade(TAR, rng.uniform(0.92, 1.06)), rng) for _ in range(8)]
    for x in range(w):
        u = (x - mid) / half
        if abs(u) > 1.0:
            continue
        # The ends taper: the far and near sides meet in a stem at bow and stern
        taper = min(1.0, (1.0 - abs(u)) / 0.12)
        far_top = water - round((BARGE_FAR_SIDE * taper + BARGE_SIDE * (1 - taper) + BARGE_SHEER * _sheer(u)) * RES)
        near_top = water - round((BARGE_SIDE + BARGE_SHEER * _sheer(u)) * RES)
        bottom = water - round(_hull_bottom(u) * RES)
        # Back: the far side's inside from its gunwale down to the floor, then the floor's shadow
        for y in range(far_top, floor + 1):
            band = int((y - far_top) / (2.4 * RES))
            tone = planks_back[band % len(planks_back)]
            k = 1.0 - 0.22 * (y - far_top) / max(1, floor - far_top)
            if (y - far_top) % round(2.4 * RES) == 0:
                k *= 0.85
            back.put(x, y, shade(tone, k * (0.93 if abs(u) > 0.85 else 1.0)))
        for y in range(far_top, far_top + RES + 1):        # its gunwale's top, lit
            back.put(x, y, shade(GUNWALE, 1.18))
        for y in range(floor - RES, floor + 1):
            back.put(x, y, shade(INNER, 0.62))
        # Front: the near side from its gunwale down to the water
        for y in range(near_top, bottom):
            band = int((y - near_top) / (2.2 * RES))
            tone = planks_front[band % len(planks_front)]
            k = 1.06 - 0.30 * (y - near_top) / max(1, bottom - near_top) - 0.06 * u
            if (y - near_top) % round(2.2 * RES) == 0:
                k *= 0.78
            front.put(x, y, shade(tone, k))
        for y in range(near_top, near_top + 2 * RES):      # its gunwale, a lighter rail
            front.put(x, y, shade(GUNWALE, 1.12 if y < near_top + RES else 0.92))
        # Where it sits in the water: a dark line, the hull's reflection and a pale ripple under it
        if bottom == water:
            for d in range(RES * 3):
                front.put(x, water + d, (24, 40, 56), round(120 * (1 - d / (RES * 3))))
            if (x // 5) % 3 != 0:
                front.put(x, water + RES * 3, (196, 222, 236), 120)
    # Ribs inside the far side, and the stems at both ends
    for i in range(1, 8):
        x = round(mid - half * 0.8 + i * half * 1.6 / 8)
        u = (x - mid) / half
        far_top = water - round((BARGE_FAR_SIDE + BARGE_SHEER * _sheer(u)) * RES)
        for y in range(far_top + RES, floor):
            back.put(x, y, shade(INNER, 0.72))
            back.put(x + 1, y, shade(INNER, 1.10))
    # Iron cleats on the near gunwale, and the strakes' nails
    for u in (-0.72, 0.72):
        x = round(mid + u * half)
        near_top = water - round((BARGE_SIDE + BARGE_SHEER * _sheer(u)) * RES)
        for dx in range(-3, 4):
            front.put(x + dx, near_top - 1, shade(IRON, 1.1 if dx < 0 else 0.8))
    for x in range(round(mid - half * 0.9), round(mid + half * 0.9), 14):
        u = (x - mid) / half
        near_top = water - round((BARGE_SIDE + BARGE_SHEER * _sheer(u)) * RES)
        for k in range(1, 5):
            y = near_top + round(k * 2.2 * RES) + 2
            if y < water - 2:
                front.put(x, y, shade(TAR, 0.6))
    back.speckle(rng)
    front.speckle(rng, 0.05, 0.03)
    _outline_hull(front, water)
    _outline_hull(back, floor + 1)
    return back.surface, front.surface


def _outline_hull(c, below):
    """Outline what is painted, except along the bottom row (in the water, or the floor's edge)."""
    edge = [(x, y) for y in range(c.h) for x in range(c.w) if c.painted(x, y) and c.get(x, y)[3] == 255 and any(
        not c.painted(x + dx, y + dy) or c.get(x + dx, y + dy)[3] < 255
        for dx, dy in ((1, 0), (-1, 0), (0, -1)))]
    for x, y in edge:
        if y < below - 1:
            c.put(x, y, OUTLINE)


def paint_all():
    back, front = paint_barge()
    return {
        'crate': paint_crate(),
        'sacks': paint_sacks(),
        'barrel': paint_barrel(),
        'bale': paint_bale(),
        'hook': paint_hook(),
        'barge_back': back,
        'barge_front': front,
    }


def preview(pictures, path):
    """The pictures at 1x and 4x over water and grass, the barge laden."""
    w, h = 900, 520
    out = pygame.Surface((w, h))
    out.fill((44, 104, 160))
    pygame.draw.rect(out, (98, 150, 60), (0, 330, w, h - 330))
    x = 10
    for name in ('crate', 'sacks', 'barrel', 'bale', 'hook'):
        big = pygame.transform.scale_by(pictures[name], 2)
        out.blit(big, (x, 340))
        out.blit(pygame.transform.smoothscale_by(pictures[name], 0.5 * 1.75), (x, 470))
        x += big.get_width() + 20
    # The barge laden, at 2x (picture size) and as the game draws it at zoom 1.75
    for zoom, ox, oy in ((1.0, 10, 20), (0.875, 360, 200)):
        def put(surf, wx, wy):
            out.blit(pygame.transform.smoothscale_by(surf, zoom), (ox + wx * RES * zoom, oy + wy * RES * zoom))
        put(pictures['barge_back'], 0, 0)
        centre = (BARGE_LENGTH + 4) / 2
        floor = BARGE_WATERLINE - BARGE_FLOOR_ABOVE_WATER
        for off, kind in ((-46, 'barrel'), (-23, 'crate'), (23, 'sacks'), (46, 'bale')):
            lw, lh = LOAD_SIZES[kind]
            put(pictures[kind], centre + off - lw / 2, floor - lh)
        put(pictures['barge_front'], 0, 0)
    pygame.image.save(out, path)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--preview', metavar='PNG', help='save a preview sheet there')
    parser.add_argument('--write', action='store_true', help=f'save the pictures into {OUT_DIR}')
    args = parser.parse_args()
    pygame.display.init()
    pygame.display.set_mode((1, 1))
    pictures = paint_all()
    if args.preview:
        preview(pictures, args.preview)
        print('Preview in', args.preview)
    if args.write:
        os.makedirs(OUT_DIR, exist_ok=True)
        for name, surf in pictures.items():
            pygame.image.save(surf, os.path.join(OUT_DIR, f'{name}.png'))
        print(f'{len(pictures)} pictures in {OUT_DIR}')


if __name__ == '__main__':
    main()
