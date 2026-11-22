"""The harbour's stone paving: the quay along the water and the stone piers off it, one surface.

A ``Paving`` is a set of cells paved alike: the land within ``depth`` tiles of
the water inside its ``quays`` boxes, and its ``piers``, paved whole. A wooden
pier standing against it (``blocked``) is not paved over; its kerb runs along
the pier's root as if it were water, and the pier's sill beam lies against it. It is laid
in the map's own orientation, each cell's piece chosen by its neighbours,
like an autotile set:

* a kerb along every edge on the water, its outer side to the water;
* an outer corner where two such edges meet (a pier's tip);
* an inner corner where the kerb turns inwards (where a pier meets the quay),
  with water only at the cell's corner;
* cobbles everywhere else.

Since quay and piers are one surface on one tile grid, the piers' cobbles run
on into the quay's without a seam, and every stone gets its colour where it
lies (``parts``). Away from the water the quay frays out into the grass stone
by stone over the last half tile and the first of the grass beyond, a little
worn ground round the stones left; a kerb running out of the paving ends on a
bevelled joint. The piers' cart tracks fade out on the quay.

The stone is kept quiet (``pier_materials``' stone palette): paving is the
ground under the town, it must not read as a building.

``lay_piers.py`` lays the pavings with the wooden piers.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from typing import Callable, Dict, Iterable, List, Set, Tuple

import numpy as np

import pier_materials as pm
from floor_painter import FloorPainter, _over
from parts import colour_parts, find_parts
from pier_materials import FLAGSTONE, NONE, TILE, Piece, colour, rng_for, smoothstep, value_noise

Cell = Tuple[int, int]


@dataclass(frozen=True)
class Paving:
    """A stretch of quay and the stone piers off it.

    Attributes:
        name: What it is called here; also keys its stones' colours.
        quays: Boxes in tiles, x0, y0, x1, y1 (exclusive), in which the land
            within ``depth`` tiles of the water is paved.
        depth: How far from the water the quay reaches, in tiles (the kerb's
            row counts as the first).
        piers: Boxes of land paved whole, the piers.
        tracks: Straight cart tracks, (start, end) in world px; worn deepest
            at the start (a pier's tip) and fading out at both ends.
        seed: Picks the variants and everything else left to chance.
    """

    name: str
    quays: Tuple[Tuple[int, int, int, int], ...]
    depth: int
    piers: Tuple[Tuple[int, int, int, int], ...]
    tracks: Tuple[Tuple[Tuple[float, float], Tuple[float, float]], ...]
    seed: int


#: The harbour basin's quay and piers B (west) and C (east) off it. The quay runs
#: up the west shore from under the northern crane (row 54; above it the coast turns
#: diagonal) past jetty A to the south-west corner, along the south shore, round the
#: eastern crane's tongue (its north edge at row 85, the step at x 183) and along the
#: north shore east of it to x 205, where the coast turns diagonal again
PAVINGS = [
    Paving("harbour_quay", quays=((126, 54, 134, 94), (126, 85, 184, 94), (168, 74, 206, 94)), depth=3,
           piers=((146, 79, 150, 91), (158, 79, 162, 91)),
           tracks=(((4736, 2575), (4736, 2995)), ((5120, 2575), (5120, 2995))),
           seed=23),
]

#: The pieces and how many variants each has
PIECES = {"middle": (pm.stone_middle, 4), "edge": (pm.stone_kerb, len(pm.KERB_JOINTS)),
          "corner": (pm.stone_corner, 2), "inner": (pm.stone_inner_corner, 2)}
#: Quarter turns anticlockwise from each piece's own orientation: a kerb has
#: the water above it, a corner above and to the right, an inner corner at
#: its top left corner
SIDES = {"N": (0, -1), "E": (1, 0), "S": (0, 1), "W": (-1, 0)}
EDGE_TURNS = {"N": 0, "W": 1, "S": 2, "E": 3}
CORNER_TURNS = {("N", "E"): 0, ("N", "W"): 1, ("S", "W"): 2, ("S", "E"): 3}
DIAGONALS = {"NW": (-1, -1), "SW": (-1, 1), "SE": (1, 1), "NE": (1, -1)}
INNER_TURNS = {"NW": 0, "SW": 1, "SE": 2, "NE": 3}

# The look
FRAY_POWER = 1.6                  # how fast the stones thin out where the quay meets the grass
JOINT_FADE = (0.72, 0.95)         # between stones, the grass shows through below this much paving
DIRT = (138, 116, 84)             # worn ground among the last stones
DIRT_ALPHA = 0.30
GRIME = 0.04
GRIME_CELL = 26.0
KERB_END_PX = 1                   # the joint a kerb ends on, where the paving stops
# Cart tracks (on the piers)
RUT_HALF_GAP = 18
RUT_HALF_WIDTH = 2.0
RUT_DEPTH = 0.8
RUT_DARKEN = 0.12
TRACK_HALF_WIDTH = 26
TRACK_DARKEN = 0.04
TRACK_FADE_IN = 30                # px from its start
TRACK_FADE_OUT = 70               # px before its end
RUT_WOBBLE = 1.4
PUDDLES_PER_TRACK = (1, 2)        # in the ruts, within the first tiles
PUDDLE_ZONE = (20, 3 * TILE)
PUDDLE_SIZE = ((7, 12), (3.5, 5.0))
PUDDLE_DARKEN = 0.32
SKY = (150, 170, 186)
SKY_SHARE = 0.25
# On the water
SHADOW_PX = 6
SHADOW_ALPHA = 0.36
SHADOW_COLOUR = (6, 20, 34)
LIP_ALPHA = 0.45
LIP_COLOUR = (52, 50, 46)


# ============================================================================
def paved_cells(paving: Paving, water: Set[Cell], blocked: Set[Cell] = frozenset()) -> Set[Cell]:
    """The quay's land within ``depth`` tiles of the water, and the piers; never ``blocked`` cells."""
    reach = range(-paving.depth, paving.depth + 1)
    cells: Set[Cell] = set()
    for x0, y0, x1, y1 in paving.quays:
        cells |= {(x, y) for x in range(x0, x1) for y in range(y0, y1)
                  if (x, y) not in water and (x, y) not in blocked
                  and any((x + dx, y + dy) in water for dx in reach for dy in reach)}
    for px0, py0, px1, py1 in paving.piers:
        cells |= {(x, y) for x in range(px0, px1) for y in range(py0, py1)}
    return cells


def classify(cell: Cell, water: Set[Cell]) -> Tuple[str, int]:
    """Which piece a paved cell gets, and its quarter turns, by where the water is round it."""
    x, y = cell
    wet = [side for side, (dx, dy) in SIDES.items() if (x + dx, y + dy) in water]
    if len(wet) == 1:
        return "edge", EDGE_TURNS[wet[0]]
    if len(wet) == 2:
        key = tuple(sorted(wet, key="NSEW".index))
        return ("corner", CORNER_TURNS[key]) if key in CORNER_TURNS else ("middle", 0)
    if wet:
        return "middle", 0
    for name, (dx, dy) in DIAGONALS.items():
        if (x + dx, y + dy) in water:
            return "inner", INNER_TURNS[name]
    return "middle", 0


@lru_cache(maxsize=None)
def _piece(kind: str, variant: int, turns: int) -> Piece:
    return PIECES[kind][0](variant).turned(turns)


def _kerb_ends(cell: Cell, wet_side: str, paved: Set[Cell], water: Set[Cell]) -> List[str]:
    """The sides a kerb runs out of the paving on (not into more paving, not into water)."""
    along = ("E", "W") if wet_side in "NS" else ("N", "S")
    x, y = cell
    return [s for s in along if (x + SIDES[s][0], y + SIDES[s][1]) not in paved | water]


def _end_kerb(height: np.ndarray, kind: np.ndarray, albedo: np.ndarray, ox: int, oy: int, side: str) -> None:
    """End a kerb on a bevelled joint at one side of its cell (canvas px ``ox``, ``oy``)."""
    cell = (slice(oy, oy + TILE), slice(ox, ox + TILE))
    h, k, a = height[cell], kind[cell], albedo[cell]
    ys, xs = np.mgrid[0:TILE, 0:TILE] + 0.5
    dist = {"W": xs, "E": TILE - xs, "N": ys, "S": TILE - ys}[side]
    h *= smoothstep(KERB_END_PX, KERB_END_PX + pm.KERB_BEVEL, dist)
    joint = dist < KERB_END_PX
    k[joint] = NONE
    a[joint] = colour(pm.STONE.joint)


def _track(albedo: np.ndarray, height: np.ndarray, start: Tuple[float, float], end: Tuple[float, float],
           origin: Tuple[int, int], rng: np.random.Generator) -> None:
    """Two ruts and a trodden band along a straight track, and puddles in the ruts near its start."""
    h, w = height.shape
    ys, xs = np.mgrid[0:h, 0:w] + 0.5
    xs, ys = xs + origin[0], ys + origin[1]
    (ax, ay), (bx, by) = start, end
    length = float(np.hypot(bx - ax, by - ay))
    ux, uy = (bx - ax) / length, (by - ay) / length
    along = (xs - ax) * ux + (ys - ay) * uy
    across = -(xs - ax) * uy + (ys - ay) * ux
    inside = (along > 0) & (along < length)
    fade = smoothstep(0, TRACK_FADE_IN, along) * smoothstep(length, length - TRACK_FADE_OUT, along) * inside
    wobble_line = (value_noise(rng, (1, int(length) + 2), 40.0)[0] - 0.5) * 2 * RUT_WOBBLE
    wobble = wobble_line[np.clip(along, 0, length).astype(int)]
    off = np.abs(across - wobble)
    ruts = smoothstep(RUT_HALF_WIDTH + 1.2, RUT_HALF_WIDTH - 1.0, np.abs(off - RUT_HALF_GAP)) * fade
    band = smoothstep(TRACK_HALF_WIDTH + 5, TRACK_HALF_WIDTH - 5, off) * fade
    albedo *= (1 - TRACK_DARKEN * band - RUT_DARKEN * ruts)[..., None]
    height -= RUT_DEPTH * ruts
    for _ in range(int(rng.integers(PUDDLES_PER_TRACK[0], PUDDLES_PER_TRACK[1] + 1))):
        t = rng.uniform(*PUDDLE_ZONE)
        side = rng.choice((-1, 1)) * RUT_HALF_GAP
        cx, cy = ax + ux * t - uy * side, ay + uy * t + ux * side
        ra, rb = rng.uniform(*PUDDLE_SIZE[0]), rng.uniform(*PUDDLE_SIZE[1])
        # long along the track
        pa = (xs - cx) * ux + (ys - cy) * uy
        pb = -(xs - cx) * uy + (ys - cy) * ux
        edge = np.hypot(pa / ra, pb / rb) + 0.3 * (value_noise(rng, (h, w), 3.0) - 0.5)
        pool = edge < 1.0
        if not pool.any():
            continue
        height[pool] = height[pool].min()
        a = smoothstep(1.0, 0.7, edge)[..., None]
        wet = albedo * (1 - PUDDLE_DARKEN) * (1 - SKY_SHARE) + colour(SKY) * SKY_SHARE * 0.55
        albedo[:] = albedo * (1 - a) + wet * a


def _near(mask: np.ndarray, radius: float) -> np.ndarray:
    """Each pixel's distance to the mask, up to ``radius`` (beyond: ``radius + 1``)."""
    h, w = mask.shape
    r = int(np.ceil(radius))
    best = np.where(mask, 0.0, radius + 1)
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            d = float(np.hypot(dx, dy))
            if d == 0 or d > radius:
                continue
            shifted = np.zeros_like(mask)
            shifted[max(0, dy):h + min(0, dy), max(0, dx):w + min(0, dx)] = \
                mask[max(0, -dy):h - max(0, dy), max(0, -dx):w - max(0, dx)]
            best = np.where(shifted & (best > d), d, best)
    return best


def paint_paving(paving: Paving, water: Set[Cell],
                 blocked: Set[Cell] = frozenset()) -> Tuple[np.ndarray, int, int, Set[Cell]]:
    """Paint a paving and its edges on the water.

    Args:
        paving: What to paint.
        water: The map's water cells.
        blocked: Cells of wooden piers against the quay: kerbed like water,
            but neither paved nor shaded.

    Returns:
        The RGBA canvas (0..1), the tile it starts at, and the paved cells.
    """
    paved = paved_cells(paving, water, blocked)
    edge_of = water | blocked                     # what the kerb faces
    ring = {(x + dx, y + dy) for x, y in paved for dx in (-1, 0, 1) for dy in (-1, 0, 1)} - paved
    grass = {c for c in ring if c not in edge_of}
    cells = paved | ring
    rx0, ry0 = min(x for x, _ in cells), min(y for _, y in cells)
    tw, th = max(x for x, _ in cells) - rx0 + 1, max(y for _, y in cells) - ry0 + 1
    h, w = th * TILE, tw * TILE
    albedo, height = np.zeros((h, w, 3)), np.zeros((h, w))
    kind = np.zeros((h, w), np.uint8)
    painted = np.zeros((h, w), bool)
    ends = []
    for cell in sorted(paved | grass):
        x, y = cell
        piece_kind, turns = classify(cell, edge_of) if cell in paved else ("middle", 0)
        count = PIECES[piece_kind][1]
        variant = int(rng_for(paving.name, "variant", x, y).integers(count))
        p = _piece(piece_kind, variant, turns)
        ox, oy = (x - rx0) * TILE, (y - ry0) * TILE
        block = (slice(oy, oy + TILE), slice(ox, ox + TILE))
        albedo[block], height[block], kind[block] = p.albedo, p.height, p.kind
        painted[block] = True
        if piece_kind == "edge":
            wet_side = next(s for s, t in EDGE_TURNS.items() if t == turns)
            ends += [(ox, oy, side) for side in _kerb_ends(cell, wet_side, paved, edge_of)]
    for ox, oy, side in ends:
        _end_kerb(height, kind, albedo, ox, oy, side)

    rng = np.random.default_rng(paving.seed)
    parts = find_parts(kind)
    colour_parts(albedo, parts, paving.name, (rx0 * TILE, ry0 * TILE))
    albedo *= (1 + GRIME * (value_noise(rng, (h, w), GRIME_CELL) - 0.5) * 2)[..., None]
    for start, end in paving.tracks:
        _track(albedo, height, start, end, (rx0 * TILE, ry0 * TILE), rng)

    # Where the quay meets the grass: how much paving each spot is, eased from cell to cell
    weights = np.array([[1.0 if (rx0 + i, ry0 + j) in paved or (rx0 + i, ry0 + j) in edge_of else 0.0
                         for i in range(tw)] for j in range(th)])
    gy = (np.arange(h) + 0.5) / TILE - 0.5
    gx = (np.arange(w) + 0.5) / TILE - 0.5
    iy, ix = np.clip(np.floor(gy).astype(int), 0, th - 2), np.clip(np.floor(gx).astype(int), 0, tw - 2)
    fy, fx = np.clip(gy - iy, 0, 1)[:, None], np.clip(gx - ix, 0, 1)[None, :]
    fy, fx = fy * fy * (3 - 2 * fy), fx * fx * (3 - 2 * fx)
    weight = (weights[iy][:, ix] * (1 - fy) * (1 - fx) + weights[iy + 1][:, ix] * fy * (1 - fx)
              + weights[iy][:, ix + 1] * (1 - fy) * fx + weights[iy + 1][:, ix + 1] * fy * fx)
    alpha = smoothstep(*JOINT_FADE, weight) * painted
    keep = np.array([k == FLAGSTONE or rng_for(paving.name, "fray", round(cx + rx0 * TILE, 1),
                                                round(cy + ry0 * TILE, 1)).random()
                     < weight[min(int(cy), h - 1), min(int(cx), w - 1)] ** FRAY_POWER
                     for (cx, cy), k in zip(parts.centres, parts.kinds)], bool)
    solid = parts.labels >= 0
    alpha[solid] = keep[parts.labels[solid]] * painted[solid]
    ragged = value_noise(rng, (h, w), 6.0)
    dirt = DIRT_ALPHA * 4 * weight * (1 - weight) * (0.5 + 0.7 * ragged) * painted

    lit = pm.shade(albedo, height, rng)
    under = np.zeros((h, w, 4))
    under[..., :3], under[..., 3] = colour(DIRT), dirt
    canvas = _over(under, np.dstack([lit, alpha]))

    # On the water: a front face under any edge facing the camera, a lip, a band of shadow
    on_water = np.zeros((h, w), bool)
    for x, y in ring & water:
        on_water[(y - ry0) * TILE:(y - ry0 + 1) * TILE, (x - rx0) * TILE:(x - rx0 + 1) * TILE] = True
    caster = (alpha > 0.5) & ~on_water
    for x, y in sorted(c for c in paved if (c[0], c[1] + 1) in water):
        ox, oy = (x - rx0) * TILE, (y + 1 - ry0) * TILE
        face = pm.stone_face(TILE, rng_for(paving.name, "face", x, y))
        canvas[oy:oy + face.shape[0], ox:ox + TILE] = _over(canvas[oy:oy + face.shape[0], ox:ox + TILE], face)
        caster[oy:oy + face.shape[0], ox:ox + TILE] = True
    d = _near(caster, SHADOW_PX)
    shadow = np.zeros((h, w, 4))
    shadow[..., :3] = colour(SHADOW_COLOUR)
    shadow[..., 3] = SHADOW_ALPHA * np.clip(1 - d / SHADOW_PX, 0, 1) ** 1.4 * (d > 0) * on_water
    lip = (d > 0) & (d <= 1.0) & on_water
    shadow[lip, :3] = colour(LIP_COLOUR)
    shadow[lip, 3] = LIP_ALPHA
    return _over(shadow, canvas), rx0, ry0, paved


def plain_water_gid(tmx, water: Set[Cell]) -> int:
    """The gid of open water: the commonest in Ground_Mid among cells with water all round."""
    mid = tmx.layers["Ground_Mid"]
    counts = Counter(mid[y * tmx.width + x] for x, y in water
                     if all((x + dx, y + dy) in water for dx in (-1, 0, 1) for dy in (-1, 0, 1)))
    return counts.most_common(1)[0][0]


def lay_paving(paving: Paving, tmx, water: Set[Cell], painter: FloorPainter, layer: str,
               cleared_layers: Iterable[str], touch: Callable[[str, int, int], None],
               blocked: Set[Cell] = frozenset()) -> int:
    """Lay a paving onto the map through ``painter``.

    The water round it loses the shore's grass: its fringe tiles on ``layer``
    come off, and its bank tiles in Ground_Mid become open water (it stays
    water). Whatever ``cleared_layers`` (the layers drawn above ``layer``) have
    on the paved cells comes off, or it would show on the stone. ``touch``
    is told of every cell of every layer before it is changed.

    Returns:
        The tiles laid.
    """
    canvas, rx0, ry0, paved = paint_paving(paving, water, blocked)
    plain = plain_water_gid(tmx, water)
    shore = {(x + dx, y + dy) for x, y in paved for dx in (-1, 0, 1) for dy in (-1, 0, 1)} & water
    for x, y in shore:
        touch(layer, x, y)
        touch("Ground_Mid", x, y)
        spot = y * tmx.width + x
        tmx.layers[layer][spot] = 0
        tmx.layers["Ground_Mid"][spot] = plain
    for name in cleared_layers:
        for x, y in paved:
            touch(name, x, y)
            tmx.layers[name][y * tmx.width + x] = 0
    for ty in range(canvas.shape[0] // TILE):
        for tx in range(canvas.shape[1] // TILE):
            touch(layer, rx0 + tx, ry0 + ty)
    return painter._cut(canvas, layer, rx0, ry0)


def describe(paving: Paving, water: Set[Cell], blocked: Set[Cell] = frozenset()) -> Dict[str, int]:
    """How many cells of each piece a paving has, for the log."""
    paved = paved_cells(paving, water, blocked)
    return dict(Counter(classify(c, water | blocked)[0] for c in paved))
