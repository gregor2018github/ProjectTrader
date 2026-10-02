"""The sheet of old paper the town plan is drawn on.

The paper stays put while the plan underneath it is zoomed and moved, the
way a magnifying glass moves over a sheet, so it is made once per size of
the module and kept.
"""

import random
from typing import Dict, Tuple

import pygame

from .style import PAPER, PAPER_DARK, PAPER_STAIN, PAPER_EDGE_DEPTH

_cache: Dict[Tuple[int, int], pygame.Surface] = {}


def get_paper(size: Tuple[int, int]) -> pygame.Surface:
    """The parchment for a module of this size, made on first use."""
    if size not in _cache:
        _cache[size] = _make_paper(size)
    return _cache[size]


def _make_paper(size: Tuple[int, int]) -> pygame.Surface:
    width, height = size
    rng = random.Random(1271)  # Same sheet every time

    paper = _mottled(size, rng, cell=70, spread=9)
    finer = _mottled(size, rng, cell=14, spread=6)
    finer.set_alpha(90)
    paper.blit(finer, (0, 0))

    marks = pygame.Surface(size, pygame.SRCALPHA)
    area = width * height

    # Fibres: short, faint, mostly lying one way like laid paper
    for _ in range(area // 900):
        x, y = rng.uniform(0, width), rng.uniform(0, height)
        length = rng.uniform(4, 16)
        dx = length * rng.uniform(0.7, 1.0) * rng.choice((-1, 1))
        dy = length * rng.uniform(-0.35, 0.35)
        pygame.draw.line(marks, (*PAPER_DARK, rng.randint(18, 45)), (x, y), (x + dx, y + dy))

    # Specks of dirt and of the rag the paper was made from
    for _ in range(area // 320):
        x, y = rng.randrange(width), rng.randrange(height)
        alpha = rng.randint(20, 70)
        if rng.random() < 0.85:
            marks.set_at((x, y), (*PAPER_DARK, alpha))
        else:
            pygame.draw.circle(marks, (*PAPER_STAIN, alpha // 2), (x, y), rng.randint(1, 2))
    paper.blit(marks, (0, 0))

    # A few old water stains, each a cluster of soft overlapping pools
    for _ in range(max(2, area // 300_000)):
        cx, cy = rng.randrange(width), rng.randrange(height)
        for _ in range(rng.randint(2, 5)):
            r = rng.randint(30, 90)
            _soft_blot(paper, (cx + rng.randint(-60, 60), cy + rng.randint(-40, 40)), r, PAPER_STAIN, rng.randint(10, 18))

    _brown_edges(paper, rng)
    return paper.convert()


def _mottled(size: Tuple[int, int], rng: random.Random, cell: int, spread: int) -> pygame.Surface:
    """Paper colour wandering a little, smoothly, over cells of ``cell`` px."""
    small_w = max(2, size[0] // cell + 2)
    small_h = max(2, size[1] // cell + 2)
    small = pygame.Surface((small_w, small_h))
    for y in range(small_h):
        for x in range(small_w):
            shift = rng.randint(-spread, spread)
            small.set_at((x, y), tuple(max(0, min(255, c + shift)) for c in PAPER))
    return pygame.transform.smoothscale(small, size)


def _brown_edges(paper: pygame.Surface, rng: random.Random) -> None:
    """Darken the paper towards its edges, unevenly, as handled paper does."""
    width, height = paper.get_size()
    edge = pygame.Surface((width, height), pygame.SRCALPHA)
    depth = PAPER_EDGE_DEPTH
    for i in range(depth):
        fade = (1.0 - i / depth) ** 2.2
        pygame.draw.rect(edge, (*PAPER_STAIN, int(110 * fade)), (i, i, width - 2 * i, height - 2 * i), 1)

    paper.blit(edge, (0, 0))

    # Soft blotches along the edge so the browning is not ruler-straight
    for _ in range((width + height) // 22):
        side = rng.randrange(4)
        r = rng.randint(10, 30)
        if side == 0:
            pos = (rng.randrange(width), rng.randint(0, 8))
        elif side == 1:
            pos = (rng.randrange(width), height - rng.randint(0, 8))
        elif side == 2:
            pos = (rng.randint(0, 8), rng.randrange(height))
        else:
            pos = (width - rng.randint(0, 8), rng.randrange(height))
        _soft_blot(paper, pos, r, PAPER_STAIN, rng.randint(25, 45))


def _soft_blot(surface: pygame.Surface, center: Tuple[int, int], radius: int, color, alpha: int) -> None:
    """A round stain fading out towards its rim."""
    blot = pygame.Surface((2 * radius, 2 * radius), pygame.SRCALPHA)
    steps = max(4, radius // 3)
    for i in range(steps):
        r = radius * (1 - i / steps)
        pygame.draw.circle(blot, (*color, int(alpha * ((i + 1) / steps) ** 1.5)), (radius, radius), max(1, round(r)))
    surface.blit(blot, (center[0] - radius, center[1] - radius))
