"""The sheet of old paper the town plan is drawn on.

The paper has two parts. Its grain (mottling, fibres, specks, stains) is a
seamless tile laid down from the land's corner, so it moves with the plan
when it is dragged, as ink and paper would. Its edges, browned by handling,
belong to the sheet and stay with the frame.
"""

import random
from typing import Dict, Optional, Tuple

import pygame

from .style import PAPER, PAPER_DARK, PAPER_EDGE_DEPTH, PAPER_GRAIN, PAPER_STAIN

#: Size of the repeating grain tile: wider and taller than the widest
#: module, so the same stain is never seen twice at once
TILE_W, TILE_H = 1792, 1152

_tile: Optional[pygame.Surface] = None
_edges: Dict[Tuple[int, int], pygame.Surface] = {}


def draw_paper(screen: pygame.Surface, rect: pygame.Rect, anchor: Tuple[int, int]) -> None:
    """Lay paper over ``rect``, its grain fixed to the screen point ``anchor``.

    Args:
        anchor: Where the land's top-left corner is on screen; the grain
            keeps its place relative to it.
    """
    tile = _grain_tile()
    old_clip = screen.get_clip()
    screen.set_clip(rect.clip(old_clip) if old_clip else rect)
    start_x = rect.left - (rect.left - anchor[0]) % TILE_W
    start_y = rect.top - (rect.top - anchor[1]) % TILE_H
    for y in range(start_y, rect.bottom, TILE_H):
        for x in range(start_x, rect.right, TILE_W):
            screen.blit(tile, (x, y))
    screen.blit(_edge_overlay(rect.size), rect.topleft)
    screen.set_clip(old_clip)


def _grain_tile() -> pygame.Surface:
    global _tile
    if _tile is None:
        _tile = _make_grain(random.Random(1271))  # Same sheet every time
    return _tile


def _make_grain(rng: random.Random) -> pygame.Surface:
    """A square of paper grain whose opposite edges meet without a seam.

    Every mark is drawn wrapped round the tile's edges, so tiles laid side
    by side continue each other.
    """
    paper = pygame.Surface((TILE_W, TILE_H))
    paper.fill(PAPER)
    area = TILE_W * TILE_H

    # Mottling: broad, faint patches a little lighter or darker
    for _ in range(area // 2600):
        lighter = rng.random() < 0.5
        color = (255, 250, 230) if lighter else PAPER_DARK
        _wrapped_blot(paper, (rng.randrange(TILE_W), rng.randrange(TILE_H)), rng.randint(20, 70),
                      color, _strong(rng.randint(4, 9)))

    marks = pygame.Surface((TILE_W, TILE_H), pygame.SRCALPHA)

    # Fibres: short, faint, mostly lying one way like laid paper
    for _ in range(area // 900):
        x, y = rng.uniform(0, TILE_W), rng.uniform(0, TILE_H)
        length = rng.uniform(4, 16)
        dx = length * rng.uniform(0.7, 1.0) * rng.choice((-1, 1))
        dy = length * rng.uniform(-0.35, 0.35)
        color = (*PAPER_DARK, _strong(rng.randint(18, 45)))
        for ox, oy in _wraps(x, y, 16):
            pygame.draw.line(marks, color, (x + ox, y + oy), (x + ox + dx, y + oy + dy))

    # Specks of dirt and of the rag the paper was made from
    for _ in range(area // 320):
        x, y = rng.randrange(TILE_W), rng.randrange(TILE_H)
        alpha = _strong(rng.randint(20, 70))
        if rng.random() < 0.85:
            marks.set_at((x, y), (*PAPER_DARK, alpha))
        else:
            r = rng.randint(1, 2)
            for ox, oy in _wraps(x, y, r):
                pygame.draw.circle(marks, (*PAPER_STAIN, alpha // 2), (x + ox, y + oy), r)
    paper.blit(marks, (0, 0))

    # A few old water stains, each a cluster of soft overlapping pools
    for _ in range(round(3 * PAPER_GRAIN)):
        cx, cy = rng.randrange(TILE_W), rng.randrange(TILE_H)
        for _ in range(rng.randint(2, 5)):
            _wrapped_blot(paper, (cx + rng.randint(-60, 60), cy + rng.randint(-40, 40)),
                          rng.randint(30, 90), PAPER_STAIN, _strong(rng.randint(10, 18)))
    return paper.convert()


def _edge_overlay(size: Tuple[int, int]) -> pygame.Surface:
    """The browning along the sheet's edges, for a module of this size."""
    if size not in _edges:
        width, height = size
        rng = random.Random(4099)
        edge = pygame.Surface(size, pygame.SRCALPHA)
        depth = PAPER_EDGE_DEPTH
        for i in range(depth):
            fade = (1.0 - i / depth) ** 2.2
            pygame.draw.rect(edge, (*PAPER_STAIN, _strong(int(110 * fade))), (i, i, width - 2 * i, height - 2 * i), 1)

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
            _soft_blot(edge, pos, r, PAPER_STAIN, _strong(rng.randint(25, 45)))
        _edges[size] = edge
    return _edges[size]


def _strong(alpha: int) -> int:
    """An alpha scaled by how strongly the paper's grain should show."""
    return max(0, min(255, round(alpha * PAPER_GRAIN)))


def _wraps(x: float, y: float, reach: float):
    """Offsets at which a mark near (x, y) must also be drawn to wrap round."""
    xs = [0] + ([TILE_W] if x < reach else []) + ([-TILE_W] if x > TILE_W - reach else [])
    ys = [0] + ([TILE_H] if y < reach else []) + ([-TILE_H] if y > TILE_H - reach else [])
    return [(ox, oy) for ox in xs for oy in ys]


def _wrapped_blot(surface: pygame.Surface, center: Tuple[int, int], radius: int, color, alpha: int) -> None:
    cx, cy = center[0] % TILE_W, center[1] % TILE_H
    for ox, oy in _wraps(cx, cy, radius):
        _soft_blot(surface, (cx + ox, cy + oy), radius, color, alpha)


def _soft_blot(surface: pygame.Surface, center: Tuple[int, int], radius: int, color, alpha: int) -> None:
    """A round stain fading out towards its rim."""
    blot = pygame.Surface((2 * radius, 2 * radius), pygame.SRCALPHA)
    steps = max(4, radius // 3)
    for i in range(steps):
        r = radius * (1 - i / steps)
        pygame.draw.circle(blot, (*color, int(alpha * ((i + 1) / steps) ** 1.5)), (radius, radius), max(1, round(r)))
    surface.blit(blot, (center[0] - radius, center[1] - radius))
