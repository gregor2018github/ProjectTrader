"""How snow builds up on a surface: first broken flecks in clumps, later a blanket filling in between.

Shared by the snow on the ground (snow_cover.py) and on the roofs (roof_snow.py).
Every spot of a surface has a *threshold*, the depth of snow (0-255) at
which it turns white; both work it out in the alpha channel of a surface
whose colour is black, with pygame's channel-wise blends, and then:

    whiteness = (level - threshold) * GAIN, cut to 0..255   (whiteness())

The threshold is the lower of two:

* the flecks: a tiling pattern (fleck_tile()) of little broken clusters of
  pixels, gathered in clumps, each pixel with its own threshold, so a first
  snowfall lies as scattered crumbs that join into uneven patches. The
  clumps are not even over the surface: a smooth noise pushes whole areas
  earlier or later.
* the blanket: smooth noise from BLANKET_FROM upwards, so the gaps between
  the flecks only fill in once the snow lies deeper, in drifts first.
"""

import random
from typing import Optional

import pygame

FLECK_TILE = 256                # the pattern's size in its own pixels; it tiles seamlessly
FLECK_CLUMPS = 360              # clumps of flecks per tile
FLECKS_PER_CLUMP = (6, 26)
CLUMP_SIGMA = (1.5, 6.0)        # how far a clump's flecks scatter, in pattern pixels
LOOSE_FLECKS = 2800             # single flecks scattered anywhere in the tile
FLECK_PIXELS = (1, 5)           # pixels in a fleck: a short broken walk
FLECK_SPREAD = 0.36             # a fleck's own threshold lies within this share of full depth
CLUMP_SPREAD = 0.3              # ...this much around its clump's
PIXEL_LAG = 0.05                # each further pixel of a fleck comes this much later, so a fleck grows
GAIN_DOUBLINGS = 3              # whiteness rises 2**3 = 8 times as fast as the level past a threshold
NO_FLECK = 255


def fleck_tile(rng: Optional[random.Random] = None, size: int = FLECK_TILE) -> pygame.Surface:
    """The flecks' thresholds in the alpha of a black, tiling *size* square (NO_FLECK where there is none)."""
    rng = rng or random.Random(7)
    tile = pygame.Surface((size, size), pygame.SRCALPHA)
    tile.fill((0, 0, 0, NO_FLECK))
    steps = ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, 1), (1, -1), (-1, -1))

    def fleck(x: float, y: float, t: float) -> None:
        px, py = int(x) % size, int(y) % size
        for i in range(rng.randint(*FLECK_PIXELS)):
            value = max(0, min(NO_FLECK - 1, round(255 * FLECK_SPREAD * min(1.0, t + i * PIXEL_LAG))))
            tile.fill((0, 0, 0, value), (px, py, 1, 1), special_flags=pygame.BLEND_RGBA_MIN)
            dx, dy = rng.choice(steps)
            px, py = (px + dx) % size, (py + dy) % size

    for _ in range(FLECK_CLUMPS):
        cx, cy, base = rng.random() * size, rng.random() * size, rng.random()
        sigma = rng.uniform(*CLUMP_SIGMA)
        for _ in range(rng.randint(*FLECKS_PER_CLUMP)):
            t = min(1.0, max(0.0, base + rng.uniform(-CLUMP_SPREAD, CLUMP_SPREAD) / 2))
            fleck(cx + rng.gauss(0, sigma), cy + rng.gauss(0, sigma), t)
    for _ in range(LOOSE_FLECKS):
        fleck(rng.random() * size, rng.random() * size, rng.random())
    return tile


def tiled(tile: pygame.Surface, size, origin=(0, 0)) -> pygame.Surface:
    """*tile* repeated over a surface of *size* whose top left lies at *origin* in the tile's endless plane."""
    out = pygame.Surface(size, pygame.SRCALPHA)
    tw, th = tile.get_size()
    start_x, start_y = -(origin[0] % tw), -(origin[1] % th)
    for y in range(start_y, size[1], th):
        for x in range(start_x, size[0], tw):
            out.blit(tile, (x, y), special_flags=pygame.BLEND_RGBA_ADD)   # onto (0, 0, 0, 0): a plain copy
    return out


def whiteness(threshold: pygame.Surface, level: int) -> pygame.Surface:
    """A black surface with alpha (level - threshold) * 2**GAIN_DOUBLINGS, cut to 0..255."""
    out = pygame.Surface(threshold.get_size(), pygame.SRCALPHA)
    out.fill((0, 0, 0, level))
    out.blit(threshold, (0, 0), special_flags=pygame.BLEND_RGBA_SUB)
    for _ in range(GAIN_DOUBLINGS):
        out.blit(out.copy(), (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
    return out


def smooth_noise(size, cell_px: float, rng: random.Random, amount: int = 255) -> pygame.Surface:
    """Smooth noise in the alpha of a black *size* surface, bumps about *cell_px* apart, 0 to *amount*."""
    cells = (max(2, round(size[0] / cell_px) + 1), max(2, round(size[1] / cell_px) + 1))
    small = pygame.Surface(cells, pygame.SRCALPHA)
    for y in range(cells[1]):
        for x in range(cells[0]):
            small.set_at((x, y), (0, 0, 0, round(amount * rng.random())))
    return pygame.transform.smoothscale(small, size)
