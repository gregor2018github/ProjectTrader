"""Old paper: the parchment under the town plan, the loading screen and charts.

The paper has two parts. Its grain (mottling, fibres, specks, stains) is a
seamless tile laid down from an anchor point, so on the town plan it moves
with the land when dragged, as ink and paper would. Its edges, browned by
handling, belong to the sheet and stay with the rect it is drawn into.

Any base colour can be made into paper: grain and stains keep the same
proportion to it as they have to the plain parchment, so a darker sheet
gets darker marks.
"""

import random
from typing import Dict, Tuple

import pygame

from ..config.colors import PARCHMENT, PARCHMENT_DARK, PARCHMENT_STAIN

Color = Tuple[int, int, int]

#: How strongly the grain shows: 1.0 faint, 2.0 heavy
PAPER_GRAIN = 1.6
#: How far in from the edge the paper browns, unless told otherwise
PAPER_EDGE_DEPTH = 56
#: Browning of the chart backgrounds: shallower, to stay clear of the axes
CHART_PAPER_EDGE = 24

#: Size of the repeating grain tile: wider and taller than the widest
#: module, so the same stain is never seen twice at once
TILE_W, TILE_H = 1792, 1152

_tiles: Dict[Color, pygame.Surface] = {}
_edges: Dict[Tuple[Tuple[int, int], Color, int], pygame.Surface] = {}


def draw_paper(screen: pygame.Surface, rect: pygame.Rect, anchor: Tuple[int, int],
               base: Color = PARCHMENT, edge_depth: int = PAPER_EDGE_DEPTH) -> None:
    """Lay paper over ``rect``, its grain fixed to the screen point ``anchor``.

    Args:
        anchor: A screen point the grain keeps its place relative to; pass
            ``rect.topleft`` for paper that does not move.
        base: The paper's own colour.
        edge_depth: How far the browning reaches in from ``rect``'s edges.
    """
    tile = _grain_tile(base)
    old_clip = screen.get_clip()
    screen.set_clip(rect.clip(old_clip) if old_clip else rect)
    start_x = rect.left - (rect.left - anchor[0]) % TILE_W
    start_y = rect.top - (rect.top - anchor[1]) % TILE_H
    for y in range(start_y, rect.bottom, TILE_H):
        for x in range(start_x, rect.right, TILE_W):
            screen.blit(tile, (x, y))
    if edge_depth > 0:
        screen.blit(_edge_overlay(rect.size, base, edge_depth), rect.topleft)
    screen.set_clip(old_clip)


def prepare_paper(*bases: Color) -> None:
    """Make the grain of each base colour now, rather than when it is first drawn."""
    for base in bases:
        _grain_tile(base)


def _tinted(color: Color, base: Color) -> Color:
    """``color`` moved onto ``base`` in the proportion it has to parchment."""
    return tuple(max(0, min(255, round(c * b / p))) for c, b, p in zip(color, base, PARCHMENT))


def _grain_tile(base: Color) -> pygame.Surface:
    if base not in _tiles:
        _tiles[base] = _make_grain(random.Random(1271), base)  # Same sheet every time
    return _tiles[base]


def _make_grain(rng: random.Random, base: Color) -> pygame.Surface:
    """A tile of paper grain whose opposite edges meet without a seam.

    Every mark is drawn wrapped round the tile's edges, so tiles laid side
    by side continue each other.
    """
    dark = _tinted(PARCHMENT_DARK, base)
    stain = _tinted(PARCHMENT_STAIN, base)
    light = _tinted((255, 250, 230), base)

    paper = pygame.Surface((TILE_W, TILE_H))
    paper.fill(base)
    area = TILE_W * TILE_H

    # Mottling: broad, faint patches a little lighter or darker
    for _ in range(area // 2600):
        color = light if rng.random() < 0.5 else dark
        _wrapped_blot(paper, (rng.randrange(TILE_W), rng.randrange(TILE_H)), rng.randint(20, 70),
                      color, _strong(rng.randint(4, 9)))

    marks = pygame.Surface((TILE_W, TILE_H), pygame.SRCALPHA)

    # Fibres: short, faint, mostly lying one way like laid paper
    for _ in range(area // 900):
        x, y = rng.uniform(0, TILE_W), rng.uniform(0, TILE_H)
        length = rng.uniform(4, 16)
        dx = length * rng.uniform(0.7, 1.0) * rng.choice((-1, 1))
        dy = length * rng.uniform(-0.35, 0.35)
        color = (*dark, _strong(rng.randint(18, 45)))
        for ox, oy in _wraps(x, y, 16):
            pygame.draw.line(marks, color, (x + ox, y + oy), (x + ox + dx, y + oy + dy))

    # Specks of dirt and of the rag the paper was made from
    for _ in range(area // 320):
        x, y = rng.randrange(TILE_W), rng.randrange(TILE_H)
        alpha = _strong(rng.randint(20, 70))
        if rng.random() < 0.85:
            marks.set_at((x, y), (*dark, alpha))
        else:
            r = rng.randint(1, 2)
            for ox, oy in _wraps(x, y, r):
                pygame.draw.circle(marks, (*stain, alpha // 2), (x + ox, y + oy), r)
    paper.blit(marks, (0, 0))

    # A few old water stains, each a cluster of soft overlapping pools
    for _ in range(round(3 * PAPER_GRAIN)):
        cx, cy = rng.randrange(TILE_W), rng.randrange(TILE_H)
        for _ in range(rng.randint(2, 5)):
            _wrapped_blot(paper, (cx + rng.randint(-60, 60), cy + rng.randint(-40, 40)),
                          rng.randint(30, 90), stain, _strong(rng.randint(10, 18)))
    return paper.convert()


def _edge_overlay(size: Tuple[int, int], base: Color, depth: int) -> pygame.Surface:
    """The browning along a sheet's edges, for a rect of this size."""
    key = (size, base, depth)
    if key not in _edges:
        width, height = size
        stain = _tinted(PARCHMENT_STAIN, base)
        rng = random.Random(4099)
        edge = pygame.Surface(size, pygame.SRCALPHA)
        for i in range(depth):
            fade = (1.0 - i / depth) ** 2.2
            pygame.draw.rect(edge, (*stain, _strong(int(110 * fade))), (i, i, width - 2 * i, height - 2 * i), 1)

        # Soft blotches along the edge so the browning is not ruler-straight,
        # sized to how deep the browning reaches
        reach = depth / PAPER_EDGE_DEPTH
        for _ in range((width + height) // 22):
            side = rng.randrange(4)
            r = max(4, round(rng.randint(10, 30) * reach))
            inset = round(rng.randint(0, 8) * reach)
            if side == 0:
                pos = (rng.randrange(width), inset)
            elif side == 1:
                pos = (rng.randrange(width), height - inset)
            elif side == 2:
                pos = (inset, rng.randrange(height))
            else:
                pos = (width - inset, rng.randrange(height))
            _soft_blot(edge, pos, r, stain, _strong(rng.randint(25, 45)))
        _edges[key] = edge
    return _edges[key]


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
