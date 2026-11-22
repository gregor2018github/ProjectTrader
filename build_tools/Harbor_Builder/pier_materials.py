"""The harbour piers' materials, wood and stone, painted by code as pieces one tile square.

A pier is laid from *pieces*, like an autotile set: the middle of its deck,
its two long edges, its end out in the water and the end's two corners. Each
piece is painted for one orientation (the pier's long axis running left to
right, its water end on the right, its "top" side at the top) and turned or
mirrored into place, so one piece serves all four sides. There are several
variants of each, and every variant of a kind keeps the same pixels along
its borders (the boards' tones and grain at the tile edge, the cobbles that
straddle it), so any mix of variants lies without a seam.

A piece is not colour alone but colour plus a height map (``Piece``): the
light is applied only once the whole pier is laid and turned the way it
points on the map (``shade``), so every stone and board is lit from the same
side, the upper left and mostly from above, as the map's sprites are, whatever
way the pier runs.

The front face of a pier (only a south edge shows one: the camera looks down
from the south) is painted along the whole edge at once (``wood_face``,
``stone_face``), in the map's own orientation.

Nothing here touches the map; ``lay_piers.py`` lays the pieces.
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass
from typing import List, Sequence, Tuple

import numpy as np

RGB = Tuple[int, int, int]

#: The map's tile, in pixels
TILE = 32

# --- light ------------------------------------------------------------------
#: Where the light comes from: a little from the left (-x) and from the top of
#: the picture (-y), mostly from above (+z), as the sprites are lit
LIGHT = np.array([-0.30, -0.50, 1.0]) / np.linalg.norm([-0.30, -0.50, 1.0])
#: How much a slope of one pixel per pixel tilts the surface: heights are in pixels
RELIEF = 0.9
#: A surface is never lit darker or brighter than this, flat being 1
SHADE_RANGE = (0.55, 1.40)
#: Grain: a few pixels a little darker or lighter, as stone and wood are
SPECKLE_DARK = (0.05, 0.93)      # share of pixels, factor
SPECKLE_LIGHT = (0.03, 1.05)


#: What a pixel of a piece is; joints and gaps are NONE. ``lay_piers`` gives every
#: connected stone, board and beam its own colour, so one straddling two tiles is one thing
NONE, COBBLE, FLAGSTONE, BOARD, BEAM = range(5)


@dataclass
class Piece:
    """One tile of a material, before it is lit.

    Attributes:
        albedo: (TILE, TILE, 3) colour, 0..1, in each material's neutral
            colours; the pier colours each stone and board after laying.
        height: (TILE, TILE) height in pixels; joints and gaps lie low.
        kind: (TILE, TILE) what each pixel is: ``COBBLE``, ``FLAGSTONE``,
            ``BOARD``, ``BEAM`` or ``NONE`` for a joint or gap.
    """

    albedo: np.ndarray
    height: np.ndarray
    kind: np.ndarray

    def turned(self, quarter_turns: int = 0, flip_v: bool = False) -> Piece:
        """The piece mirrored top to bottom (first) and turned anticlockwise.

        Args:
            quarter_turns: Quarter turns anticlockwise, as ``np.rot90``.
            flip_v: Mirror it top to bottom before turning.

        Returns:
            A new piece.
        """
        arrays = [self.albedo, self.height, self.kind]
        if flip_v:
            arrays = [a[::-1] for a in arrays]
        arrays = [np.ascontiguousarray(np.rot90(a, quarter_turns % 4)) for a in arrays]
        return Piece(*arrays)


# --- helpers ----------------------------------------------------------------
def rng_for(*keys: object) -> np.random.Generator:
    """A generator seeded by names, the same in every run (``hash`` is not)."""
    return np.random.default_rng(zlib.crc32("/".join(map(str, keys)).encode()))


def colour(rgb: Sequence[float]) -> np.ndarray:
    """A palette colour as floats 0..1."""
    return np.asarray(rgb, np.float64) / 255


def smoothstep(lo: float, hi: float, x: np.ndarray) -> np.ndarray:
    """0 below ``lo``, 1 above ``hi``, smooth between (``lo`` may be above ``hi``)."""
    t = np.clip((x - lo) / (hi - lo), 0, 1)
    return t * t * (3 - 2 * t)


def periodic_noise(rng: np.random.Generator, size: int, waves: int, freq_x: Tuple[int, int],
                   freq_y: Tuple[int, int]) -> np.ndarray:
    """Smooth noise in 0..1 that tiles: a sum of waves fitting the square a whole number of times.

    Args:
        rng: Where the waves' phases come from.
        size: The square's side in pixels.
        waves: How many waves are summed.
        freq_x: Lowest and highest number of waves across the square.
        freq_y: The same, down the square. Few across and many down make
            streaks running across, as a board's grain.

    Returns:
        A (size, size) array.
    """
    ys, xs = np.mgrid[0:size, 0:size].astype(np.float64) + 0.5
    out = np.zeros((size, size))
    for _ in range(waves):
        kx = rng.integers(freq_x[0], freq_x[1] + 1) * rng.choice((-1, 1))
        ky = rng.integers(freq_y[0], freq_y[1] + 1)
        out += np.cos(2 * np.pi * (kx * xs + ky * ys) / size + rng.uniform(0, 2 * np.pi)) / np.hypot(kx, ky)
    return (out - out.min()) / max(out.max() - out.min(), 1e-9)


def value_noise(rng: np.random.Generator, shape: Tuple[int, int], cell: float) -> np.ndarray:
    """Smooth noise in 0..1 over any (h, w), one random value per ``cell`` pixels, eased between."""
    h, w = shape
    gh, gw = int(h / cell) + 2, int(w / cell) + 2
    grid = rng.random((gh, gw))
    ys, xs = np.mgrid[0:h, 0:w] / cell
    x0, y0 = xs.astype(int), ys.astype(int)
    tx, ty = xs - x0, ys - y0
    tx, ty = tx * tx * (3 - 2 * tx), ty * ty * (3 - 2 * ty)
    top = grid[y0, x0] * (1 - tx) + grid[y0, x0 + 1] * tx
    bottom = grid[y0 + 1, x0] * (1 - tx) + grid[y0 + 1, x0 + 1] * tx
    return top * (1 - ty) + bottom * ty


def jitter(rgb: np.ndarray, rng: np.random.Generator, spread: float = 0.035) -> np.ndarray:
    """A colour a little lighter or darker and warmer or cooler, never another colour."""
    k = rng.uniform(1 - spread, 1 + spread)
    warm = rng.uniform(-spread, spread) * 0.5
    return np.clip(rgb * k * np.array([1 + warm, 1 + warm * 0.4, 1 - warm * 0.6]), 0, 1)


def _blank() -> Piece:
    return Piece(np.zeros((TILE, TILE, 3)), np.zeros((TILE, TILE)), np.zeros((TILE, TILE), np.uint8))


def shade(albedo: np.ndarray, height: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Light a laid surface: each pixel's colour times how squarely the light falls on it.

    Args:
        albedo: (h, w, 3) colour, 0..1, already in the map's orientation.
        height: (h, w) heights in pixels.
        rng: For the grain's speckle.

    Returns:
        The lit colour, (h, w, 3), 0..1.
    """
    dy, dx = np.gradient(height * RELIEF)
    normal = np.dstack([-dx, -dy, np.ones_like(height)])
    normal /= np.linalg.norm(normal, axis=-1, keepdims=True)
    light = np.clip((normal @ LIGHT) / LIGHT[2], *SHADE_RANGE)
    lit = albedo * light[..., None]
    roll = rng.random(height.shape)
    speckle = np.where(roll < SPECKLE_DARK[0], SPECKLE_DARK[1],
                       np.where(roll > 1 - SPECKLE_LIGHT[0], SPECKLE_LIGHT[1], 1.0))
    return np.clip(lit * speckle[..., None], 0, 1)


# ============================================================================
# Wood
# ============================================================================
@dataclass(frozen=True)
class WoodPalette:
    """Weathered oak, grey-brown; never orange or fresh pine."""

    oak: RGB = (126, 114, 98)
    oak_bleached: RGB = (156, 149, 135)     # a board worn pale by feet, salt and sun
    patch: RGB = (124, 100, 74)              # a newer board put in, browner
    beam: RGB = (106, 94, 80)                # the edge beams and the end's header, heavier timber
    gap: RGB = (22, 32, 38)                  # between the boards: dark, the water glinting through
    nail: RGB = (50, 48, 50)
    tar: RGB = (38, 33, 30)
    salt: RGB = (206, 202, 192)
    wet: RGB = (74, 70, 60)                  # soaked, at the water end
    algae: RGB = (66, 98, 50)
    pile: RGB = (92, 80, 66)


WOOD = WoodPalette()

#: Boards across a middle tile, top row and bottom row of each (inclusive); the
#: row under each is the gap. Three boards a tile: a board is about 0.3 of a tile.
DECK_BOARDS = ((0, 8), (10, 19), (21, 30))
#: An edge tile: the heavy beam along the outside, then a deeper gap, then two boards
EDGE_BEAM = (0, 10)
EDGE_BOARDS = ((13, 21), (23, 30))
#: The end tile: the boards stop at END_BOARDS_TO and the header runs across from END_HEADER_FROM
END_BOARDS_TO = 18
END_HEADER_FROM = 21
#: Where the edge beam of the third edge variant has a joint: beams are long, but not endless
BEAM_JOINT = 14

BOARD_TOP = 1.0          # px a board stands above its gap
BOARD_CROWN = 0.7        # px a board is rounded up across its width
BEAM_TOP = 2.2           # px a beam stands above the gaps: proud of the boards
GAP_DEPTH = -1.6
JOINT_MARGIN = 6         # px a board's end keeps from the tile's edge, so variants match there
JOINT_STAGGER = 7        # px joints in neighbouring rows keep apart, so they never line up
JOINTS_PER_ROW = (0, 0, 0, 1, 1)             # drawn per row: boards about two and a half tiles long
REPAIR_VARIANT = 3                            # the middle variant with a short board put in
REPAIR_LENGTH = (10, 15)
END_DARKEN = 0.12        # a board's end grain soaks water: this much darker at the joint
END_DARKEN_PX = 5.0
PATCH_CHANCE = 0.5       # a board wholly inside a tile is a repair, browner and nailed at both ends;
                         # otherwise it is worn pale and rough
GRAIN = 0.12             # how strongly the grain shows


def _wood_grain(rng: np.random.Generator) -> np.ndarray:
    """Streaks running along the boards (across the tile), 0..1, tiling."""
    return periodic_noise(rng, TILE, 7, (1, 2), (3, 9))


def _edge_weight() -> np.ndarray:
    """0 within a few pixels of the tile's left and right edges, 1 inside: where variants may differ."""
    xs = np.arange(TILE) + 0.5
    w = smoothstep(2, JOINT_MARGIN + 1, np.minimum(xs, TILE - xs))
    return np.broadcast_to(w, (TILE, TILE))


def _place_joints(rng: np.random.Generator, rows: int, x_max: int, repair: bool = False) -> List[List[int]]:
    """Joint columns per board row, staggered against the row above; with ``repair``, one short board."""
    if repair:
        joints: List[List[int]] = [[] for _ in range(rows)]
        start = int(rng.integers(JOINT_MARGIN, x_max - JOINT_MARGIN - REPAIR_LENGTH[1]))
        joints[int(rng.integers(rows))] = [start, start + int(rng.integers(*REPAIR_LENGTH))]
        return joints
    joints = []
    for r in range(rows):
        wanted = int(rng.choice(JOINTS_PER_ROW))
        chosen: List[int] = []
        for _ in range(40):
            if len(chosen) == wanted:
                break
            x = int(rng.integers(JOINT_MARGIN, x_max - JOINT_MARGIN))
            above = joints[r - 1] if r else []
            if all(abs(x - o) >= JOINT_STAGGER for o in above) and \
                    all(abs(x - o) >= 2 * JOINT_STAGGER for o in chosen):
                chosen.append(x)
        joints.append(sorted(chosen))
    return joints


def _nail(piece: Piece, x: int, y: int) -> None:
    """A nail head: a dark pixel, a little proud, its rim lit by the shading."""
    if 0 <= x < TILE and 0 <= y < TILE:
        piece.albedo[y, x] = colour(WOOD.nail)
        piece.height[y, x] += 0.5


def _gap(piece: Piece, rows: slice, cols: slice) -> None:
    piece.albedo[rows, cols] = colour(WOOD.gap)
    piece.height[rows, cols] = GAP_DEPTH
    piece.kind[rows, cols] = NONE


def _boards(piece: Piece, rng: np.random.Generator, rows: Sequence[Tuple[int, int]], x_max: int,
            grain: np.ndarray, own_grain: np.ndarray, repair: bool = False) -> None:
    """Paint board rows into a piece, up to column ``x_max`` (exclusive), with joints, repairs and wear.

    The grain at the tile's left and right edges is the shared ``grain``, so
    every variant meets every other; inside, the variant's ``own_grain``.
    """
    weight = _edge_weight()
    g = grain * (1 - weight) + own_grain * weight
    xs = np.arange(TILE) + 0.5
    for (y0, y1), row_joints in zip(rows, _place_joints(rng, len(rows), x_max, repair)):
        width = y1 - y0 + 1
        band = slice(y0, y1 + 1)
        across = np.sin(np.pi * (np.arange(width) + 0.5) / width)[:, None]
        piece.albedo[band, :x_max] = colour(WOOD.oak) * (1 + GRAIN * (g[band, :x_max] - 0.5) * 2)[..., None]
        piece.height[band, :x_max] = BOARD_TOP + BOARD_CROWN * across
        piece.kind[band, :x_max] = BOARD
        bounds = [-1] + row_joints + [x_max]
        for i, (a, b) in enumerate(zip(bounds, bounds[1:])):
            if 0 < i < len(bounds) - 2:              # a board wholly inside the tile: a repair, or worn
                seg = slice(a + 1, b)
                if rng.random() < PATCH_CHANCE:
                    piece.albedo[band, seg] = piece.albedo[band, seg] * 0.45 + colour(WOOD.patch) * 0.55
                    for x in (a + 2, b - 2):
                        _nail(piece, x, y0 + 2)
                        _nail(piece, x, y1 - 2)
                else:
                    piece.albedo[band, seg] = piece.albedo[band, seg] * 0.45 + colour(WOOD.oak_bleached) * 0.55
                    piece.height[band, seg] += (rng.random((width, b - a - 1)) - 0.5) * 0.6
        for x in row_joints:
            dark = 1 - END_DARKEN * np.exp(-np.abs(xs - (x + 0.5)) / END_DARKEN_PX)
            piece.albedo[band, :x_max] *= dark[None, :x_max, None]
            _gap(piece, band, slice(x, x + 1))
            for side in (-2, 2):
                _nail(piece, x + side, y0 + 2)
                _nail(piece, x + side, y1 - 2)
        if y1 + 1 < TILE:
            _gap(piece, slice(y1 + 1, y1 + 2), slice(0, x_max))


def _beam(piece: Piece, y0: int, y1: int, x0: int, x1: int, grain: np.ndarray, along_x: bool = True) -> None:
    """A heavy timber, proud of the boards, rounded across its width."""
    width = (y1 - y0 + 1) if along_x else (x1 - x0 + 1)
    cols = np.arange(x0, x1 + 1)
    for y in range(y0, y1 + 1):
        if along_x:
            across = np.full(len(cols), np.sin(np.pi * (y - y0 + 0.5) / width))
        else:
            across = np.sin(np.pi * (cols - x0 + 0.5) / width)
        g = grain[y, x0:x1 + 1]
        piece.albedo[y, x0:x1 + 1] = colour(WOOD.beam)[None, :] * (1 + GRAIN * 1.3 * (g - 0.5) * 2)[:, None]
        piece.height[y, x0:x1 + 1] = BEAM_TOP + 0.8 * across
        piece.kind[y, x0:x1 + 1] = BEAM


def wood_middle(variant: int) -> Piece:
    """The deck's middle: three boards across, joints staggered, now and then a repair or a worn board."""
    piece = _blank()
    _boards(piece, rng_for("wood", "middle", variant), DECK_BOARDS, TILE,
            _wood_grain(rng_for("wood", "grain")), _wood_grain(rng_for("wood", "middle", variant, "grain")),
            repair=variant == REPAIR_VARIANT)
    return piece


def wood_edge(variant: int) -> Piece:
    """A long edge: the heavy edge beam along the top, its shadow, then two boards."""
    piece = _blank()
    _beam(piece, *EDGE_BEAM, 0, TILE - 1, _wood_grain(rng_for("wood", "beam")))
    if variant == 2:
        _gap(piece, slice(EDGE_BEAM[0], EDGE_BEAM[1] + 1), slice(BEAM_JOINT, BEAM_JOINT + 1))
    _gap(piece, slice(EDGE_BEAM[1] + 1, EDGE_BEAM[1] + 3), slice(0, TILE))
    _boards(piece, rng_for("wood", "edge", variant), EDGE_BOARDS, TILE,
            _wood_grain(rng_for("wood", "grain")), _wood_grain(rng_for("wood", "edge", variant, "grain")))
    return piece


def _header(piece: Piece) -> None:
    """The end's header beam, running down the right of the tile, the boards stopping short of it."""
    grain = _wood_grain(rng_for("wood", "header")).T          # its grain runs down
    _gap(piece, slice(0, TILE), slice(END_BOARDS_TO + 1, END_HEADER_FROM))
    _beam(piece, 0, TILE - 1, END_HEADER_FROM, TILE - 1, grain, along_x=False)


def wood_end(variant: int) -> Piece:
    """The water end: the boards stop against a header beam running across the pier."""
    piece = _blank()
    _boards(piece, rng_for("wood", "end", variant), DECK_BOARDS, END_BOARDS_TO + 1,
            _wood_grain(rng_for("wood", "grain")), _wood_grain(rng_for("wood", "end", variant, "grain")))
    _header(piece)
    return piece


def wood_corner(variant: int) -> Piece:
    """Where an edge beam meets the end's header: the header runs through, the beam butts against it."""
    piece = wood_edge(0)
    _header(piece)
    return piece


# ============================================================================
# Stone
# ============================================================================
@dataclass(frozen=True)
class StonePalette:
    """Grey and brown stone, a little of the town's brick red among it."""

    # Close together on purpose: paving is background, it must not read as a built structure
    cobbles: Tuple[RGB, ...] = ((136, 130, 120), (130, 124, 114), (140, 133, 120), (132, 125, 116),
                                (127, 123, 115), (137, 128, 116))
    brick: RGB = (140, 108, 92)
    kerb: RGB = (140, 135, 123)              # dressed flagstones, barely paler than the cobbles
    kerb_red: RGB = (142, 126, 114)
    joint: RGB = (98, 93, 85)                # the grime in the joints, soft
    face: RGB = (140, 131, 116)              # the front wall's blocks
    mortar: RGB = (78, 72, 63)
    algae: RGB = (64, 96, 56)
    barnacle: RGB = (188, 184, 170)
    fender: RGB = (92, 74, 58)               # the timber fender a ship lies against


STONE = StonePalette()
#: What the pieces are painted in; the pier gives each stone its own colour from the palette
COBBLE_NEUTRAL = STONE.cobbles[0]
KERB_NEUTRAL = STONE.kerb

#: Cobbles: points along each tile edge (shared by every variant, so the
#: stones straddling the edge match), about EDGE_STEP apart
COBBLE_EDGE_STEP = 8
COBBLE_EDGE_JITTER = 1.6
#: and points inside, different per variant, kept this far from the edges
#: so they never reach a neighbour's pixels
COBBLE_INNER_MARGIN = 7.0
COBBLE_INNER_GAP = 6.5            # px between inner points
COBBLE_INNER_TRIES = 60
COBBLE_DOME = 0.9                 # px a cobble's middle stands above its joint
COBBLE_ROUND = 2.6                # px from its edge to where it is full height
JOINT_HALF = 0.7                  # half a joint's width, px
STONE_TEXTURE = 0.05              # the grain within a stone

#: Kerb flagstones: the joints along a kerb tile, per variant. There is none at
#: the tile's edges, so stones run on into the next tile: about two tiles long
KERB_JOINTS = ((16,), (), (24,), ())
KERB_TOP = 1.3
KERB_BEVEL = 2.2                  # px over which a flagstone's edge rounds off
KERB_OUTER_BEVEL = 3.2            # its outer edge, to the water, worn more
KERB_CORNER_RADIUS = 3.0
CORNER_STONE_RADIUS = 7.0         # the pier's own corner, rounded off
KERB_CRACK_CHANCE = 0.05


def _cobble_edge_points() -> np.ndarray:
    """The points on the tile's edges, the same for every variant; edge points stand for both sides."""
    rng = rng_for("stone", "edge-points")
    pts = []
    for along in np.arange(COBBLE_EDGE_STEP / 2, TILE, COBBLE_EDGE_STEP):
        pts.append((along + rng.uniform(-COBBLE_EDGE_JITTER, COBBLE_EDGE_JITTER), rng.uniform(-1.2, 1.2)))
    for along in np.arange(COBBLE_EDGE_STEP, TILE, COBBLE_EDGE_STEP):
        pts.append((rng.uniform(-1.2, 1.2), along + rng.uniform(-COBBLE_EDGE_JITTER, COBBLE_EDGE_JITTER)))
    pts.append((rng.uniform(-0.8, 0.8), rng.uniform(-0.8, 0.8)))       # the corner
    return np.array(pts)


def _cobble_inner_points(rng: np.random.Generator) -> np.ndarray:
    pts: List[Tuple[float, float]] = []
    lo, hi = COBBLE_INNER_MARGIN, TILE - COBBLE_INNER_MARGIN
    for _ in range(COBBLE_INNER_TRIES):
        p = (rng.uniform(lo, hi), rng.uniform(lo, hi))
        if all(np.hypot(p[0] - q[0], p[1] - q[1]) >= COBBLE_INNER_GAP for q in pts):
            pts.append(p)
    return np.array(pts).reshape(-1, 2)


def _texture(name: str) -> np.ndarray:
    """A stone's grain, 1 give or take STONE_TEXTURE; it tiles, and every variant shares it."""
    return 1 + STONE_TEXTURE * (periodic_noise(rng_for("stone", name), TILE, 8, (2, 7), (2, 7)) - 0.5) * 2


def stone_middle(variant: int) -> Piece:
    """Cobbles, uneven in size, grime in the joints, each stone domed."""
    piece = _blank()
    rng = rng_for("stone", "middle", variant)
    edge = _cobble_edge_points()
    shifts = [(dx, dy) for dx in (-TILE, 0, TILE) for dy in (-TILE, 0, TILE)]
    points = np.concatenate([edge + s for s in shifts] + [_cobble_inner_points(rng)])
    ys, xs = np.mgrid[0:TILE, 0:TILE] + 0.5
    d = np.hypot(xs[..., None] - points[:, 0], ys[..., None] - points[:, 1])
    d.sort(axis=-1)
    edge_dist = (d[..., 1] - d[..., 0]) / 2
    piece.albedo[:] = colour(COBBLE_NEUTRAL) * _texture("cobble")[..., None]
    piece.height = COBBLE_DOME * smoothstep(JOINT_HALF, COBBLE_ROUND, edge_dist)
    joint = edge_dist < JOINT_HALF
    piece.albedo[joint] = colour(STONE.joint)
    piece.kind[~joint] = COBBLE
    return piece


def _rounded_box_distance(xs: np.ndarray, ys: np.ndarray, box: Tuple[float, float, float, float],
                          radius: float) -> np.ndarray:
    """Distance inwards from the edge of a box with rounded corners (negative outside)."""
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    hx, hy = (x1 - x0) / 2 - radius, (y1 - y0) / 2 - radius
    qx, qy = np.abs(xs - cx) - hx, np.abs(ys - cy) - hy
    outside = np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0)
    return radius - outside


def _flagstone(piece: Piece, rng: np.random.Generator, box: Tuple[float, float, float, float],
               outer_y: float = None, outer_x: float = None, round_corner: bool = False) -> None:
    """One dressed stone into a piece, its edges bevelled and its corners worn round.

    Args:
        piece: Painted into.
        rng: For a crack.
        box: x0, y0, x1, y1 in the piece's pixels; it may reach past the
            tile, for a stone running on into the next one.
        outer_y: The row of its edge to the water, worn more (or None).
        outer_x: The column of such an edge (or None).
        round_corner: Cut its top right corner round: the pier's own corner.
    """
    ys, xs = np.mgrid[0:TILE, 0:TILE] + 0.5
    inside = _rounded_box_distance(xs, ys, box, KERB_CORNER_RADIUS)
    if round_corner:
        r = CORNER_STONE_RADIUS
        ox, oy = box[2] - r, box[1] + r
        in_corner = (xs > ox) & (ys < oy)
        inside = np.where(in_corner, np.minimum(inside, r - np.hypot(xs - ox, ys - oy)), inside)
    mask = inside > 0
    bevel = smoothstep(0, KERB_BEVEL, inside)
    if outer_y is not None:
        bevel = np.minimum(bevel, smoothstep(0, KERB_OUTER_BEVEL, np.abs(ys - outer_y)))
    if outer_x is not None:
        bevel = np.minimum(bevel, smoothstep(0, KERB_OUTER_BEVEL, np.abs(xs - outer_x)))
    piece.albedo[mask] = (colour(KERB_NEUTRAL) * _texture("kerb")[..., None])[mask]
    piece.height[mask] = (KERB_TOP * bevel)[mask]
    piece.kind[mask] = FLAGSTONE
    if rng.random() < KERB_CRACK_CHANCE:                     # a hairline crack across it
        x = rng.uniform(max(box[0], 0) + 4, min(box[2], TILE) - 4)
        for y in range(max(int(box[1]), 0) + 3, min(int(box[3]), TILE) - 2):
            x += rng.choice((-1, 0, 0, 1)) * 0.7
            xi = int(x)
            if 0 <= xi < TILE and mask[y, xi]:
                piece.albedo[y, xi] *= 0.7
                piece.height[y, xi] -= 0.6
    piece.albedo[~(piece.kind > 0)] = colour(STONE.joint)


def stone_kerb(variant: int) -> Piece:
    """A long edge: large flagstones, the water at the top, a joint under them to the cobbles."""
    piece = _blank()
    rng = rng_for("stone", "kerb", variant)
    bounds = [-TILE - 1] + list(KERB_JOINTS[variant]) + [2 * TILE]
    for a, b in zip(bounds, bounds[1:]):
        _flagstone(piece, rng, (a + 1, 0, b, TILE - 1), outer_y=0)
    return piece


def stone_inner_corner(variant: int) -> Piece:
    """Where a kerb turns inwards (a pier meeting the quay): water only at the top left corner point.

    The kerb along the water to the left runs in from the left, the one along
    the water above from the top; each stops at a joint, and one square stone
    fills the rest.
    """
    piece = _blank()
    rng = rng_for("stone", "inner-corner", variant)
    _flagstone(piece, rng, (-TILE, 0, 1, TILE - 1))                 # the left kerb's tail
    _flagstone(piece, rng, (2, -TILE, TILE - 1, 1))                 # the upper kerb's tail
    _flagstone(piece, rng, (2, 2, TILE - 1, TILE - 1))
    return piece


def stone_corner(variant: int) -> Piece:
    """The end's outer corner (top right): one large stone, its corner cut round, between the kerbs' tails.

    The side kerb's last stone runs in from the left and the end kerb's from
    below; each stops here at a joint, its end bevelled.
    """
    piece = _blank()
    rng = rng_for("stone", "corner", variant)
    _flagstone(piece, rng, (-TILE, 0, 1, TILE - 1), outer_y=0)                 # the side kerb's tail
    _flagstone(piece, rng, (1, TILE - 1, TILE, 2 * TILE), outer_x=TILE)        # the end kerb's
    _flagstone(piece, rng, (2, 0, TILE, TILE - 2), outer_y=0, outer_x=TILE, round_corner=True)
    return piece


# ============================================================================
# Front faces, in the map's own orientation
# ============================================================================
#: How tall a pier's front face shows, px (a third to half a tile)
WOOD_FACE_HEIGHT = 14
STONE_FACE_HEIGHT = 16
#: Wood: the edge beam's front, then two courses of planking between the piles, the lower one wet
WOOD_FACE_BEAM = 4
WOOD_FACE_BOARDS = ((5, 8), (10, 12))
WOOD_FACE_WET_FROM = 9
PILE_SPACING = (36, 46)           # px between piles: one to one and a half tiles
PILE_ACROSS = (0.62, 1.12, 1.05, 0.97, 0.88, 0.76, 0.58)     # across a round pile, lit from the left
PILE_HALF = len(PILE_ACROSS) // 2
PILE_BELOW = 4                    # px a pile shows on below the waterline, fading
#: Stone: a coping course (the kerbs' fronts), then courses of blocks in stretcher bond
STONE_FACE_COPING = 3
STONE_COURSE = 5                  # px a course, its mortar row included
STONE_BLOCK = (13, 21)            # a block's length
STONE_FACE_WET = 5                # px of waterline stain, algae and barnacles at the bottom
FENDER_ROWS = (3, 5)              # the timber fender's rows on the face, under the coping
#: The face is in the pier's shadow: this much darker than its top
FACE_LIGHT = 0.80


def piles_along(length: int, rng: np.random.Generator) -> List[int]:
    """Where piles stand along a front ``length`` px long: at both ends and about every tile and a bit."""
    xs = [PILE_HALF]
    while xs[-1] + PILE_SPACING[1] < length - PILE_HALF:
        xs.append(xs[-1] + int(rng.integers(*PILE_SPACING)))
    if length - 1 - PILE_HALF - xs[-1] < PILE_SPACING[0] * 0.6 and len(xs) > 1:
        xs.pop()
    xs.append(length - 1 - PILE_HALF)
    return xs


def wood_face(length: int, rng: np.random.Generator) -> np.ndarray:
    """A timber pier's front: the beam's face, planking between piles, a dark wet band, an algae line.

    Args:
        length: Its width in px.
        rng: The pier's own.

    Returns:
        (WOOD_FACE_HEIGHT + PILE_BELOW, length, 4) RGBA, 0..1, lit.
    """
    h = WOOD_FACE_HEIGHT
    out = np.zeros((h + PILE_BELOW, length, 4))
    grain = value_noise(rng, (h, length), 3.0)
    streak = value_noise(rng, (h, length), 9.0)
    # The edge beam's front, its top arris catching the light
    beam = colour(WOOD.beam) * FACE_LIGHT
    for y in range(WOOD_FACE_BEAM):
        k = (1.22, 1.0, 0.95, 0.80)[min(y, 3)]
        out[y, :, :3] = beam * k * (0.94 + 0.12 * grain[y])[:, None]
    out[WOOD_FACE_BEAM:h, :, :3] = colour(WOOD.gap)
    for y0, y1 in WOOD_FACE_BOARDS:
        for y in range(y0, y1 + 1):
            k = 1.08 if y == y0 else 0.84 if y == y1 else 1.0
            out[y, :, :3] = colour(WOOD.oak) * FACE_LIGHT * k * (0.92 + 0.16 * grain[y])[:, None]
    # Wet and dark towards the water, the algae line at it
    wet = smoothstep(WOOD_FACE_WET_FROM - 1, h - 1, np.arange(h))[:, None, None]
    out[:h, :, :3] = out[:h, :, :3] * (1 - wet * 0.40) + colour(WOOD.wet) * FACE_LIGHT * wet * 0.25
    algae = streak[h - 2] > 0.4
    out[h - 2, algae, :3] = colour(WOOD.algae) * 0.8
    out[h - 1, :, :3] = colour(WOOD.algae) * 0.5
    out[:h, :, 3] = 1
    # The piles, under the beam and proud of the planking, on down into the water
    for x in piles_along(length, rng):
        tone = rng.uniform(0.92, 1.05)
        for i, k in enumerate(PILE_ACROSS):
            col = x - PILE_HALF + i
            if not 0 <= col < length:
                continue
            c = colour(WOOD.pile) * FACE_LIGHT * k * tone
            for y in range(WOOD_FACE_BEAM, h):
                out[y, col, :3] = c * (1 - wet[y, 0, 0] * 0.35) * (0.95 + 0.1 * grain[y, col])
            out[h - 2:h, col, :3] = colour(WOOD.algae) * 0.55 * k
            for j in range(PILE_BELOW):
                out[h + j, col, :3] = c * 0.5
                out[h + j, col, 3] = 0.6 * (1 - (j + 1) / (PILE_BELOW + 1))
        out[WOOD_FACE_BEAM, max(0, x - PILE_HALF):x + PILE_HALF + 1, :3] *= 0.7     # in the beam's shadow
    return out


def stone_face(length: int, rng: np.random.Generator, fender: bool = False) -> np.ndarray:
    """A stone pier's front: a coping, big blocks in stretcher bond, waterline stain, algae, barnacles.

    Args:
        length: Its width in px.
        rng: The pier's own.
        fender: Hang a timber fender beam along it, where ships lie.

    Returns:
        (STONE_FACE_HEIGHT, length, 4) RGBA, 0..1, lit.
    """
    h = STONE_FACE_HEIGHT
    out = np.zeros((h, length, 4))
    out[..., 3] = 1
    out[..., :3] = colour(STONE.mortar)
    # The coping: the kerbs' front faces, lit at the arris
    cop = colour(STONE.kerb) * FACE_LIGHT
    out[:STONE_FACE_COPING, :, :3] = cop
    out[0, :, :3] = cop * 1.2
    out[STONE_FACE_COPING - 1, :, :3] = cop * 0.78
    # Courses of blocks, each course's joints halfway along the one above's blocks
    y = STONE_FACE_COPING
    offset = int(rng.integers(0, STONE_BLOCK[0]))
    course = 0
    while y < h:
        rows = min(STONE_COURSE - 1, h - y)
        x = -offset if course % 2 == 0 else -offset - STONE_BLOCK[0] // 2
        while x < length:
            n = int(rng.integers(*STONE_BLOCK))
            a, b = max(0, x), min(length, x + n - 1)
            if b > a:
                c = jitter(colour(STONE.face), rng, 0.05) * FACE_LIGHT
                if rng.random() < 0.12:
                    c = c * 0.86
                for r in range(rows):
                    k = 1.1 if r == 0 else 0.9 if r == rows - 1 else 1.0
                    out[y + r, a:b, :3] = c * k
                out[y:y + rows, a, :3] *= 1.06          # lit on its left, shaded on its right
                out[y:y + rows, b - 1, :3] *= 0.9
            x += n
        y += STONE_COURSE
        course += 1
    # Darker towards the water, the waterline stain, algae and barnacles
    depth = smoothstep(STONE_FACE_COPING, h, np.arange(h))[:, None, None]
    out[..., :3] *= 1 - 0.18 * depth
    wet_from = h - STONE_FACE_WET
    stain = value_noise(rng, (h, length), 4.0)
    for yy in range(wet_from, h):
        t = (yy - wet_from + 1) / STONE_FACE_WET
        green = (stain[yy] < 0.25 + 0.6 * t)
        out[yy, green, :3] = out[yy, green, :3] * (1 - 0.7 * t) + colour(STONE.algae) * 0.75 * (0.7 * t)
        out[yy, ~green, :3] *= 1 - 0.35 * t
        barn = rng.random(length) < 0.10 * (1 - t)
        out[yy, barn, :3] = colour(STONE.barnacle) * 0.85
    out[h - 1, :, :3] = colour(STONE.algae) * 0.45
    if fender:
        f0, f1 = FENDER_ROWS
        wood = colour(STONE.fender) * FACE_LIGHT
        out[f0:f1 + 1, :, :3] = wood
        out[f0, :, :3] = wood * 1.2
        out[f1, :, :3] = wood * 0.7
        out[f1 + 1, :, :3] *= 0.7                       # its shadow on the blocks
    return out
