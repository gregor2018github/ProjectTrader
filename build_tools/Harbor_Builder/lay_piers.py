"""Lay the harbour's piers onto the map: a timber jetty and paved stone piers, as ground tiles.

    python build_tools/Harbor_Builder/lay_piers.py --sheet     # the pieces and two sample piers, to look at
    python build_tools/Harbor_Builder/lay_piers.py --preview   # render the piers, leave the map alone
    python build_tools/Harbor_Builder/lay_piers.py             # write them into Map1.tmx (Tiled closed)

Each pier is an entry of ``PIERS``: its material, its footprint in tiles (the
land cells the Water polygon goes round), the side it joins the land on and a
seed. It is laid from the pieces of ``pier_materials`` (the middle, the two
long edges, the end and its corners, several variants of each, picked by the
seed), then given what belongs to the whole pier: wetter wood towards the
water end, salt and a tar stain on the timber; a cart track, puddles in its
ruts and each stone's own tint on the stone; a ragged end on the land side
fading into the grass. Then it is lit (``pier_materials.shade``) and, round
it on the water, given its front face where the camera sees one (a south
edge), a thin dark lip on its other sides and a band of shadow on the water.

Whatever the tool changes on the map (a cell's tile on any layer) it first
writes down as it was in ``underlay.json``, and every run puts those tiles
back before laying anything; so a cell that had something of its own under
the paving (a road's ragged edge) keeps it however often the tool runs.

It is painted like the churchyard's ground (``paint_ground.py``): the canvas
is cut into tiles of a tileset of its own, ``harbor_piers``, by
``floor_painter.FloorPainter``, onto ``Ground_High``, which the game draws
over the animated water and the Placing Helper shows as it is. The grass
fringe tiles the piers had on the water round them are taken off that layer.
Every run starts the tileset afresh and lays every pier and paving again,
from the tiles as they were before the tool ever ran, so it can be run as
often as wanted; two runs write the same bytes.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, Iterable, List, Optional, Set, Tuple

os.environ["SDL_VIDEODRIVER"] = "dummy"
import numpy as np  # noqa: E402
import pygame  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "Forest_Builder"))
sys.path.insert(0, HERE)
import grow_forest as forest_tool  # noqa: E402  (sets up pygame and the game's import path)
from floor_baker import FloorBaker  # noqa: E402
from floor_painter import FloorPainter, _over  # noqa: E402
import pier_materials as pm  # noqa: E402
from parts import Parts, colour_parts, find_parts  # noqa: E402
import stone_paving  # noqa: E402
from stone_paving import PAVINGS, Paving  # noqa: E402
from pier_materials import BEAM, FLAGSTONE, TILE, Piece, colour, rng_for, smoothstep, value_noise  # noqa: E402

TMX = forest_tool.TMX
PREVIEW_TMX = "assets/tiles/_piers_preview.tmx"
OUTPUT_DIR = "build_tools/output/piers"
LAYER = "Ground_High"
DECO_LAYER = "Ground_Flowers_Mushrooms"      # FloorPainter wants one; nothing goes on it
TILESET = "harbor_piers"
#: The tiles as they were before the tool changed them: {layer: {"x,y": gid}}
UNDERLAY = os.path.join(HERE, "underlay.json")


@dataclass(frozen=True)
class Pier:
    """One pier to lay.

    Attributes:
        name: What it is called here.
        material: ``"wood"`` or ``"stone"``.
        box: Its footprint in tiles, x0, y0, x1, y1 (exclusive): the land
            cells the Water polygon goes round.
        root: The side it joins the land on: ``"W"``, ``"E"``, ``"S"`` or ``"N"``.
            Its water end is the opposite side.
        seed: Picks the variants and everything else left to chance.
        fender: A stone pier's front face gets a timber fender beam.
        abuts_quay: Its land end meets a paved quay (``PAVINGS``) instead of
            grass: it does not fray out but ends on a sill beam against the
            quay's kerb, and the quay treats it as water for its kerb.
    """

    name: str
    material: str
    box: Tuple[int, int, int, int]
    root: str
    seed: int
    fender: bool = False
    abuts_quay: bool = False


#: The harbour basin's piers standing on their own: A, the short timber jetty off the
#: west shore. The stone piers B and C are part of the south quay's paving
#: (``stone_paving.PAVINGS``), so they run into it without a seam.
PIERS = [
    Pier("A_fishing_jetty", "wood", (133, 61, 140, 66), "W", seed=11, abuts_quay=True),
]
#: The layers drawn over LAYER: what they have on paved cells comes off
ABOVE_LAYER = ("Ground_High_Plus", "Ground_Flowers_Mushrooms")

# --- the pieces ---------------------------------------------------------------
#: How many variants of each piece there are; the seed picks among them
VARIANTS: Dict[str, Dict[str, int]] = {
    "wood": {"middle": 4, "edge": 3, "end": 2, "corner": 1},
    "stone": {"middle": 4, "edge": len(pm.KERB_JOINTS), "end": len(pm.KERB_JOINTS), "corner": 2},
}
#: How often each variant is drawn, where not all alike: the middle with a repair in it and the
#: edge with a joint in its beam are rarer
VARIANT_WEIGHTS: Dict[Tuple[str, str], Tuple[float, ...]] = {("wood", "middle"): (1, 1, 1, 0.3),
                                                             ("wood", "edge"): (1, 1, 0.25)}
PAINTERS = {
    "wood": {"middle": pm.wood_middle, "edge": pm.wood_edge, "end": pm.wood_end, "corner": pm.wood_corner},
    # The stone end is a kerb turned with its outer edge to the right
    "stone": {"middle": pm.stone_middle, "edge": pm.stone_kerb,
              "end": lambda v: pm.stone_kerb(v).turned(3), "corner": pm.stone_corner},
}
#: Quarter turns anticlockwise from the pieces' own orientation (water end on the right) to the map's
TURNS = {"W": 0, "S": 1, "E": 2, "N": 3}

# --- what belongs to the whole pier -------------------------------------------
ROOT_BLEND_PX = TILE              # how far the pier frays out onto the land
ROOT_COBBLE_FALLOFF = 1.3         # how fast the cobbles thin out onto it
ROOT_KERB_KEEP = 0.75 * TILE      # a kerb stone stays if its middle is this far towards the pier
ROOT_DIRT = (138, 114, 80)        # worn ground round its land end
ROOT_DIRT_ALPHA = 0.42
GRIME = 0.06                      # the surface a little uneven in tone, over tiles
GRIME_CELL = 22.0
# Wood
WET_END_PX = 2 * TILE             # the boards darken and soak over this much of the water end
WET_DARKEN = 0.32
WET_TINT = 0.25
BOARD_ONTO_LAND = (3, 24)         # px each board runs on past the shore line
BEAM_ONTO_LAND = (0, 4)
SALT_PER_TILE = 1.6               # pale specks of salt
SALT_ALPHA = 0.45
TAR_STAINS = 1
TAR_SIZE = ((7, 12), (3, 6))      # half axes, px
TAR_ALPHA = 0.55
# Stone
RUT_HALF_GAP = 18                 # half the wheels' track, px
RUT_HALF_WIDTH = 2.2
RUT_DEPTH = 1.3
RUT_DARKEN = 0.24
RUT_WOBBLE = 1.6                  # px the ruts wander
TRACK_HALF_WIDTH = 26             # the darker trodden band about the ruts
TRACK_DARKEN = 0.09
TRACK_STOPS_PX = 20               # short of the end kerb
PUDDLES = (2, 3)                  # in the ruts, near the water end
PUDDLE_SIZE = ((7, 13), (3.5, 5.0))
PUDDLE_ZONE_PX = 3 * TILE         # how far from the water end they lie
PUDDLE_DARKEN = 0.40
SKY = (150, 170, 186)             # what a puddle mirrors
SKY_SHARE = 0.30
DAMP_PATCHES = 2
DAMP_DARKEN = 0.14
# On the water round it
SHADOW_PX = 6                     # the band of darker water along the pier
SHADOW_ALPHA = 0.40
SHADOW_COLOUR = (6, 20, 34)
LIP_ALPHA = 0.55                  # the pier's edge, one pixel, on its sides without a face
LIP_COLOUR = (40, 36, 32)


# ============================================================================
# Laying a pier
# ============================================================================
@lru_cache(maxsize=None)
def piece(material: str, kind: str, variant: int) -> Piece:
    """One variant of one piece, painted once."""
    return PAINTERS[material][kind](variant)


def _choose(material: str, i: int, j: int, length: int, width: int, rng: np.random.Generator,
            sill: bool = False) -> Piece:
    """The piece for cell (i along, j across) of a pier in the pieces' orientation.

    With ``sill``, the first column on the pier (i = 0) is the end's pieces
    mirrored: a header beam across the land end, against a quay.
    """
    top, bottom, end = j == 0, j == width - 1, i == length - 1
    if sill and i == 0:
        kind = "corner" if (top or bottom) else "end"
        weights = np.asarray(VARIANT_WEIGHTS.get((material, kind), [1] * VARIANTS[material][kind]), float)
        variant = int(rng.choice(len(weights), p=weights / weights.sum()))
        # Mirrored left to right: top to bottom, then half a turn
        return piece(material, kind, variant).turned(2, flip_v=not bottom)
    kind = "corner" if end and (top or bottom) else "end" if end else "edge" if (top or bottom) else "middle"
    if i < 0:                     # the land end, fraying out
        kind = "edge" if (top or bottom) else "middle"
    weights = np.asarray(VARIANT_WEIGHTS.get((material, kind), [1] * VARIANTS[material][kind]), float)
    variant = int(rng.choice(len(weights), p=weights / weights.sum()))
    return piece(material, kind, variant).turned(0, flip_v=bottom and kind != "middle")


def _compose(pier: Pier, rng: np.random.Generator) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Lay a pier's pieces in their own orientation, its land end one tile to the left.

    Returns:
        Colour (h, w, 3), height (h, w) and what each pixel is (h, w).
    """
    x0, y0, x1, y1 = pier.box
    length, width = (x1 - x0, y1 - y0) if pier.root in "WE" else (y1 - y0, x1 - x0)
    if width < 3:
        raise ValueError(f"{pier.name}: a pier must be at least 3 tiles wide, for its two edges and a middle")
    h, w = width * TILE, (length + 1) * TILE
    albedo, height, kind = np.zeros((h, w, 3)), np.zeros((h, w)), np.zeros((h, w), np.uint8)
    for i in range(-1, length):
        for j in range(width):
            p = _choose(pier.material, i, j, length, width, rng, sill=pier.abuts_quay)
            ox, oy = (i + 1) * TILE, j * TILE
            albedo[oy:oy + TILE, ox:ox + TILE] = p.albedo
            height[oy:oy + TILE, ox:ox + TILE] = p.height
            kind[oy:oy + TILE, ox:ox + TILE] = p.kind
    return albedo, height, kind


def _fray_root(pier: Pier, kind: np.ndarray, parts: Parts, rng: np.random.Generator) -> Tuple[np.ndarray, np.ndarray]:
    """The land end: boards running on unevenly, or the paving thinning out stone by stone; dirt round it.

    Returns:
        The surface's alpha and the worn ground's alpha under it, (h, w) each.
    """
    h, w = kind.shape
    alpha = np.ones((h, w))
    if pier.abuts_quay:                       # nothing on the land: the quay is there
        alpha[:, :TILE] = 0
        return alpha, np.zeros((h, w))
    xs = np.arange(w) + 0.5
    onto_land = np.clip(TILE - xs, 0, None)[None, :].repeat(h, 0)        # px past the shore line
    if pier.material == "wood":
        # Each board (a run of rows between gaps in the first tile on the pier) runs on its own length
        column = kind[:, TILE + TILE // 2]
        y = 0
        while y < h:
            if not column[y]:
                y += 1
                continue
            start = y
            while y < h and column[y]:
                y += 1
            reach = rng.integers(*(BEAM_ONTO_LAND if column[start] == BEAM else BOARD_ONTO_LAND))
            alpha[start:y] = (onto_land[start:y] <= reach)
        gaps = column == 0
        alpha[gaps] = (onto_land[gaps] <= BOARD_ONTO_LAND[0])
    else:
        keep = np.array([x >= ROOT_KERB_KEEP if k == FLAGSTONE else
                         rng_for(pier.name, "root", round(x, 1), round(y, 1)).random()
                         < np.clip(x / ROOT_BLEND_PX, 0, 1) ** ROOT_COBBLE_FALLOFF
                         for (x, y), k in zip(parts.centres, parts.kinds)], bool)
        solid = parts.labels >= 0
        alpha[solid] = keep[parts.labels[solid]]
        alpha[~solid & (onto_land > 0)] = 0
    alpha[onto_land >= ROOT_BLEND_PX] = 0
    ragged = value_noise(rng, (h, w), 6.0)
    dirt = ROOT_DIRT_ALPHA * smoothstep(ROOT_BLEND_PX, 4, onto_land) * (0.55 + 0.6 * ragged) * (onto_land > 0)
    return alpha, dirt


def _wood_touches(pier: Pier, albedo: np.ndarray, height: np.ndarray, rng: np.random.Generator) -> None:
    """Wet boards towards the water end, salt specks, a tar stain."""
    h, w = height.shape
    xs = np.arange(w) + 0.5
    wet = smoothstep(w - WET_END_PX, w, xs)[None, :, None]
    albedo *= 1 - WET_DARKEN * wet
    albedo[:] = albedo * (1 - WET_TINT * wet) + colour(pm.WOOD.wet) * WET_TINT * wet * 0.9
    boards = height > 0
    for _ in range(int(SALT_PER_TILE * (w / TILE) * (h / TILE))):
        x = int(w - 1 - abs(rng.normal(0, w / 3)) % (w - TILE)) if rng.random() < 0.6 else int(rng.integers(TILE, w))
        y = int(rng.integers(h))
        if boards[y, x]:
            albedo[y, x] = albedo[y, x] * (1 - SALT_ALPHA) + colour(pm.WOOD.salt) * SALT_ALPHA
    ys, xs2 = np.mgrid[0:h, 0:w] + 0.5
    for _ in range(TAR_STAINS):
        cx, cy = rng.uniform(2 * TILE, w - 2 * TILE), rng.uniform(TILE, h - TILE)
        rx, ry = rng.uniform(*TAR_SIZE[0]), rng.uniform(*TAR_SIZE[1])
        blot = smoothstep(1.0, 0.6, np.hypot((xs2 - cx) / rx, (ys - cy) / ry) + 0.25 * value_noise(rng, (h, w), 2.5))
        a = (TAR_ALPHA * blot * boards)[..., None]
        albedo[:] = albedo * (1 - a) + colour(pm.WOOD.tar) * a


def _stone_touches(pier: Pier, albedo: np.ndarray, height: np.ndarray, rng: np.random.Generator) -> None:
    """A cart track down the middle, puddles in its ruts near the water end, damp patches."""
    h, w = height.shape
    ys, xs = np.mgrid[0:h, 0:w] + 0.5
    centre = h / 2
    stop = smoothstep(w - TILE - TRACK_STOPS_PX + 10, w - TILE - TRACK_STOPS_PX, xs)
    wobble = (value_noise(rng, (1, w), 40.0)[0] - 0.5) * 2 * RUT_WOBBLE
    band = smoothstep(TRACK_HALF_WIDTH + 5, TRACK_HALF_WIDTH - 5, np.abs(ys - centre - wobble))
    albedo *= (1 - TRACK_DARKEN * band * stop)[..., None]
    ruts = np.zeros((h, w))
    for side in (-1, 1):
        line = centre + side * RUT_HALF_GAP + wobble + (value_noise(rng, (1, w), 13.0)[0] - 0.5) * 1.2
        ruts = np.maximum(ruts, smoothstep(RUT_HALF_WIDTH + 1.2, RUT_HALF_WIDTH - 1.0, np.abs(ys - line)))
    ruts *= stop
    height -= RUT_DEPTH * ruts
    albedo *= (1 - RUT_DARKEN * ruts)[..., None]

    # Damp patches and puddles towards the water end, the puddles in the ruts
    end = w - TILE
    for _ in range(DAMP_PATCHES):
        cx, cy = rng.uniform(end - PUDDLE_ZONE_PX, end), rng.uniform(TILE, h - TILE)
        r = rng.uniform(10, 18)
        damp = smoothstep(1.0, 0.3, np.hypot(xs - cx, (ys - cy) * 1.4) / r + 0.4 * value_noise(rng, (h, w), 5.0))
        albedo *= (1 - DAMP_DARKEN * damp)[..., None]
    for _ in range(int(rng.integers(PUDDLES[0], PUDDLES[1] + 1))):
        side = rng.choice((-1, 1))
        cx = rng.uniform(end - PUDDLE_ZONE_PX, end - TRACK_STOPS_PX - 10)
        cy = centre + side * RUT_HALF_GAP + wobble[int(cx)]
        rx, ry = rng.uniform(*PUDDLE_SIZE[0]), rng.uniform(*PUDDLE_SIZE[1])
        edge = np.hypot((xs - cx) / rx, (ys - cy) / ry) + 0.35 * (value_noise(rng, (h, w), 3.0) - 0.5)
        water = edge < 1.0
        if not water.any():
            continue
        height[water] = height[water].min()               # standing water lies flat
        a = smoothstep(1.0, 0.7, edge)[..., None]
        wet = albedo * (1 - PUDDLE_DARKEN) * (1 - SKY_SHARE) + colour(SKY) * SKY_SHARE * 0.55
        albedo[:] = albedo * (1 - a) + wet * a
        rim = (edge >= 1.0) & (edge < 1.35)                # wet stone round it
        albedo[rim] *= 0.88


def _to_map(arrays: Iterable[np.ndarray], root: str) -> List[np.ndarray]:
    """Turn arrays from the pieces' orientation into the map's."""
    return [np.ascontiguousarray(np.rot90(a, TURNS[root])) for a in arrays]


def _laid_rect(pier: Pier) -> Tuple[int, int, int, int]:
    """The tiles the laid pier covers: its footprint and one more on its land side."""
    x0, y0, x1, y1 = pier.box
    return {"W": (x0 - 1, y0, x1, y1), "E": (x0, y0, x1 + 1, y1),
            "S": (x0, y0, x1, y1 + 1), "N": (x0, y0 - 1, x1, y1)}[pier.root]


def _rect_distance(xs: np.ndarray, ys: np.ndarray, rect: Tuple[float, float, float, float]) -> np.ndarray:
    """Distance from a rectangle (x0, y0, x1, y1), 0 inside it."""
    x0, y0, x1, y1 = rect
    return np.hypot(np.maximum.reduce([x0 - xs, np.zeros_like(xs), xs - x1]),
                    np.maximum.reduce([y0 - ys, np.zeros_like(ys), ys - y1]))


def paint_pier(pier: Pier, water: Set[Tuple[int, int]]) -> Tuple[np.ndarray, int, int]:
    """Paint one pier and its edges on the water.

    Args:
        pier: What to paint.
        water: The map's water cells (``TMXMap.water_tiles``): only there does
            it get a front face, a lip or a shadow.

    Returns:
        The RGBA canvas (0..1) and the tile it starts at: it covers the
        footprint and one tile all round.
    """
    rng = np.random.default_rng(pier.seed)
    x0, y0, x1, y1 = pier.box
    rx0, ry0 = x0 - 1, y0 - 1
    canvas = np.zeros(((y1 - y0 + 2) * TILE, (x1 - x0 + 2) * TILE, 4))

    # The surface, in the pieces' orientation, then turned and lit
    albedo, height, kind = _compose(pier, rng)
    parts = find_parts(kind)
    colour_parts(albedo, parts, pier.name)
    alpha, dirt = _fray_root(pier, kind, parts, rng)
    grime = value_noise(rng, height.shape, GRIME_CELL)
    albedo *= (1 + GRIME * (grime - 0.5) * 2)[..., None]
    if pier.material == "wood":
        _wood_touches(pier, albedo, height, rng)
    else:
        _stone_touches(pier, albedo, height, rng)
    albedo, height, alpha, dirt = _to_map([albedo, height, alpha, dirt], pier.root)
    lit = pm.shade(albedo, height, rng)
    lx0, ly0, lx1, ly1 = _laid_rect(pier)
    ox, oy = (lx0 - rx0) * TILE, (ly0 - ry0) * TILE
    region = (slice(oy, oy + lit.shape[0]), slice(ox, ox + lit.shape[1]))
    under = np.zeros(lit.shape[:2] + (4,))
    under[..., :3] = colour(ROOT_DIRT)
    under[..., 3] = dirt
    surface = np.dstack([lit, alpha])
    canvas[region] = _over(under, surface)

    # The front face, under a south edge over water
    ch, cw = canvas.shape[:2]
    fx0, fy0, fx1, fy1 = TILE, TILE, cw - TILE, ch - TILE          # the footprint on the canvas
    faces = []
    south = [x for x in range(x0, x1) if (x, y1) in water]
    if south:
        a, b = (min(south) - x0 + 1) * TILE, (max(south) - x0 + 2) * TILE
        face = (pm.wood_face(b - a, rng) if pier.material == "wood"
                else pm.stone_face(b - a, rng, pier.fender))
        tall = min(face.shape[0], TILE)
        canvas[fy1:fy1 + tall, a:b] = _over(canvas[fy1:fy1 + tall, a:b], face[:tall])
        faces.append((a, fy1, b, fy1 + (pm.WOOD_FACE_HEIGHT if pier.material == "wood" else pm.STONE_FACE_HEIGHT)))

    # Darker water along it, and a dark lip at its edge: only on water cells
    ys, xs = np.mgrid[0:ch, 0:cw] + 0.5
    d = _rect_distance(xs, ys, (fx0, fy0, fx1, fy1))
    for rect in faces:
        d = np.minimum(d, _rect_distance(xs, ys, rect))
    on_water = np.zeros((ch, cw), bool)
    for ty in range(ch // TILE):
        for tx in range(cw // TILE):
            if (rx0 + tx, ry0 + ty) in water:
                on_water[ty * TILE:(ty + 1) * TILE, tx * TILE:(tx + 1) * TILE] = True
    shadow = np.zeros((ch, cw, 4))
    shadow[..., :3] = colour(SHADOW_COLOUR)
    shadow[..., 3] = SHADOW_ALPHA * np.clip(1 - d / SHADOW_PX, 0, 1) ** 1.4 * (d > 0) * on_water
    lip = (d > 0) & (d <= 1.0) & on_water
    shadow[lip, :3] = colour(LIP_COLOUR)
    shadow[lip, 3] = LIP_ALPHA
    return _over(shadow, canvas), rx0, ry0


# ============================================================================
# Onto the map
# ============================================================================
def _ring(pier: Pier) -> Iterable[Tuple[int, int]]:
    x0, y0, x1, y1 = pier.box
    for y in range(y0 - 1, y1 + 1):
        for x in range(x0 - 1, x1 + 1):
            if not (x0 <= x < x1 and y0 <= y < y1):
                yield x, y


class Underlay:
    """The map's tiles as they were before the tool touched them, kept in UNDERLAY."""

    def __init__(self, tmx: forest_tool.Map) -> None:
        self.tmx = tmx
        self.tiles: Dict[str, Dict[str, int]] = {}
        if os.path.exists(UNDERLAY):
            with open(UNDERLAY, encoding="utf-8") as f:
                self.tiles = json.load(f)

    def restore(self) -> None:
        """Put every tile the tool ever changed back as it was."""
        for layer, cells in self.tiles.items():
            for key, gid in cells.items():
                x, y = map(int, key.split(","))
                self.tmx.layers[layer][y * self.tmx.width + x] = gid

    def touch(self, layer: str, x: int, y: int) -> None:
        """Note a tile before it is changed, the first time only."""
        cells = self.tiles.setdefault(layer, {})
        cells.setdefault(f"{x},{y}", self.tmx.layers[layer][y * self.tmx.width + x])

    def save(self) -> None:
        ordered = {layer: dict(sorted(cells.items(), key=lambda kv: tuple(map(int, kv[0].split(",")))))
                   for layer, cells in sorted(self.tiles.items())}
        with open(UNDERLAY, "w", encoding="utf-8", newline="\n") as f:
            json.dump(ordered, f, indent=0, separators=(",", ":"))
            f.write("\n")


def lay(piers: List[Pier], pavings: List[Paving], tmx: forest_tool.Map, water: Set[Tuple[int, int]],
        underlay: Underlay) -> FloorPainter:
    """Lay piers and pavings into the map's ground layer through a fresh ``harbor_piers`` tileset."""
    underlay.restore()
    painter = FloorPainter(tmx, LAYER, DECO_LAYER, TILESET, FloorBaker(tmx, LAYER))
    data = tmx.layers[LAYER]
    # Start afresh: whatever an earlier run laid comes off, and the tileset is made anew
    if painter.existing:
        ours = range(painter.first_gid, painter.first_gid + len(painter.tiles))
        for spot, gid in enumerate(data):
            if (gid & 0x1FFFFFFF) in ours:
                data[spot] = 0
        painter.tiles, painter.known = [], {}
    for pier in piers:
        # The grass fringe hanging over the water round it goes; the pier brings its own edge
        for x, y in _ring(pier):
            if (x, y) in water:
                underlay.touch(LAYER, x, y)
                data[y * tmx.width + x] = 0
        canvas, rx0, ry0 = paint_pier(pier, water)
        for ty in range(canvas.shape[0] // TILE):
            for tx in range(canvas.shape[1] // TILE):
                underlay.touch(LAYER, rx0 + tx, ry0 + ty)
        covered = painter._cut(canvas, LAYER, rx0, ry0)
        print(f"{pier.name}: {pier.material}, tiles {pier.box[:2]} to {(pier.box[2] - 1, pier.box[3] - 1)}, "
              f"{covered} tiles laid")
    against = {(x, y) for p in piers if p.abuts_quay
               for x in range(p.box[0], p.box[2]) for y in range(p.box[1], p.box[3])}
    for paving in pavings:
        covered = stone_paving.lay_paving(paving, tmx, water, painter, LAYER, ABOVE_LAYER, underlay.touch,
                                          against)
        print(f"{paving.name}: {stone_paving.describe(paving, water, against)}, {covered} tiles laid")
    painter.added = max(painter.added, len(painter.tiles))      # always written, even if the same
    return painter


# ============================================================================
# The sheet: every piece, and a sample pier of each material
# ============================================================================
SHEET_SCALE = 3
SHEET_WATER = (26, 108, 172)
SHEET_GRASS = (110, 150, 48)
SAMPLE_BOX = (2, 1, 8, 5)          # a horizontal sample pier, 6 by 4 tiles, joined to land on its left


def _sheet_row(material: str) -> pygame.Surface:
    kinds = VARIANTS[material]
    tiles = [(kind, v) for kind, n in kinds.items() for v in range(n)]
    gap = 6
    row = pygame.Surface((len(tiles) * (TILE + gap), TILE + 14), pygame.SRCALPHA)
    font = pygame.font.SysFont(None, 14)
    for n, (kind, v) in enumerate(tiles):
        p = piece(material, kind, v)
        albedo = p.albedo.copy()
        colour_parts(albedo, find_parts(p.kind), "sheet")
        rgb = pm.shade(albedo, p.height, rng_for("sheet"))
        surf = pygame.surfarray.make_surface((rgb.transpose(1, 0, 2) * 255).astype(np.uint8))
        row.blit(surf, (n * (TILE + gap), 0))
        row.blit(font.render(f"{kind[:3]}{v}", True, (230, 230, 230)), (n * (TILE + gap), TILE + 2))
    return row


def _sample(material: str) -> pygame.Surface:
    """A sample pier over flat water, land on its left, laid exactly as the map's are."""
    x0, y0, x1, y1 = SAMPLE_BOX
    pier = Pier(f"sample_{material}", material, SAMPLE_BOX, "W", seed=5, fender=material == "stone")
    w, h = x1 + 2, y1 + 2
    water = {(x, y) for x in range(x0 - 1, w) for y in range(h)} - {(x, y) for x in range(x0, x1)
                                                                    for y in range(y0, y1)}
    water -= {(x, y) for x in range(x0) for y in range(h)}
    base = pygame.Surface((w * TILE, h * TILE))
    base.fill(SHEET_WATER)
    base.fill(SHEET_GRASS, (0, 0, x0 * TILE, h * TILE))
    base.fill(SHEET_GRASS, (x0 * TILE, y0 * TILE, (x1 - x0) * TILE, (y1 - y0) * TILE))
    canvas, rx0, ry0 = paint_pier(pier, water)
    surf = pygame.surfarray.make_surface((canvas[..., :3].transpose(1, 0, 2) * 255).astype(np.uint8)).convert_alpha()
    pygame.surfarray.pixels_alpha(surf)[:] = (canvas[..., 3].T * 255).astype(np.uint8)
    base.blit(surf, (rx0 * TILE, ry0 * TILE))
    return base


def sheet(path: str) -> None:
    """Save every piece and a sample of each material, at SHEET_SCALE."""
    parts = [_sheet_row("wood"), _sheet_row("stone"), _sample("wood"), _sample("stone")]
    width = max(p.get_width() for p in parts[:2]) + 0
    width = max(width, parts[2].get_width() + parts[3].get_width() + 12)
    height = parts[0].get_height() + parts[1].get_height() + parts[2].get_height() + 24
    out = pygame.Surface((width, height))
    out.fill((40, 40, 44))
    out.blit(parts[0], (0, 0))
    out.blit(parts[1], (0, parts[0].get_height() + 8))
    top = parts[0].get_height() + parts[1].get_height() + 20
    out.blit(parts[2], (0, top))
    out.blit(parts[3], (parts[2].get_width() + 12, top))
    out = pygame.transform.scale(out, (width * SHEET_SCALE, height * SHEET_SCALE))
    pygame.image.save(out, path)


# ============================================================================
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--preview", action="store_true",
                        help=f"only render the piers to {OUTPUT_DIR}/, leave the map alone")
    parser.add_argument("--sheet", action="store_true", help=f"save the pieces to {OUTPUT_DIR}/pieces.png and stop")
    args = parser.parse_args()
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    if args.sheet:
        sheet(os.path.join(OUTPUT_DIR, "pieces.png"))
        print(f"Pieces in {OUTPUT_DIR}/pieces.png")
        return

    from src.models.map import TMXMap
    water = TMXMap(TMX).water_tiles
    tmx = forest_tool.Map(TMX)
    painter = FloorPainter(tmx, LAYER, DECO_LAYER, TILESET, FloorBaker(tmx, LAYER))
    saved = {path: open(path, "rb").read() if os.path.exists(path) else None for path in painter.files()}
    underlay = Underlay(tmx)
    painter = lay(PIERS, PAVINGS, tmx, water, underlay)
    painter.save()
    print(f"{len(painter.tiles)} tiles in {TILESET}.png")
    target = PREVIEW_TMX if args.preview else TMX
    tmx.save(target, [])
    if not args.preview:
        underlay.save()
    shown = [(p.name, (p.box[0] - 3, p.box[1] - 3, p.box[2] + 3, p.box[3] + 3)) for p in PIERS]
    shown += [(p.name, (min(q[0] for q in p.quays) - 2, min(q[1] for q in p.quays) - 3,
                        max(q[2] for q in p.quays) + 2, max(q[3] for q in p.quays) + 3)) for p in PAVINGS]
    for name, region in shown:
        forest_tool.render(target, OUTPUT_DIR, region, scale=1.0)
        os.replace(os.path.join(OUTPUT_DIR, "forest_game.png"), os.path.join(OUTPUT_DIR, f"{name}.png"))
        os.remove(os.path.join(OUTPUT_DIR, "forest_tiled.png"))
    print(f"Pictures in {OUTPUT_DIR}/")
    if args.preview:
        os.remove(PREVIEW_TMX)
        for path, content in saved.items():
            if content is None:
                if os.path.exists(path):
                    os.remove(path)
            else:
                with open(path, "wb") as f:
                    f.write(content)


if __name__ == "__main__":
    main()
