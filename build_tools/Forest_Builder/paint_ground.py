"""Paint ground of its own somewhere on the map: worn paths and uneven grass, as the woods have a floor.

    python build_tools/Forest_Builder/paint_ground.py --preview   # look first
    python build_tools/Forest_Builder/paint_ground.py             # write it into Map1.tmx

The map's grass is one even tile everywhere. A place people walk and tend,
like the churchyard, wants more: paths trodden into it, where the grass is
worn through to the dirt in the middle and only thins at the sides, and the
grass round about uneven, darker and lusher in patches, paler and drier in
others, greener over the graves and mossy at the foot of a wall, with tufts,
clover, moss and a few daisies (whole motifs of non_collision_deco,
plant_catalog.json) scattered over it, kept off the paths and the stones.

Each place is an entry of GROUNDS: the box it is painted in (in tiles), the
part of it that is its own (`inside`, world pixels, the edge faded), its
paths (polylines in world pixels, each with its half width and strength, the
main ways strong and the side ways faint), its walls (lines along which moss
gathers) and what it scatters. It is painted like a broadleaf wood's floor
(floor_painter.FloorPainter): the ground over whatever ``Ground_High_Plus``
has there, the tufts on ``Ground_Flowers_Mushrooms``, cut into new tiles of
the ``painted_ground`` tileset (made the first time, after every other
tileset, with room to grow), which only grows. Painting the same entry
twice lays it twice, darker; to redo one, undo the map and the tileset with
git first. Close Tiled before writing.
"""

import argparse
import math
import os
import random
import sys
from typing import List, Sequence, Tuple

os.environ["SDL_VIDEODRIVER"] = "dummy"
import numpy as np  # noqa: E402
import pygame  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import grow_forest as forest_tool  # noqa: E402  (sets up pygame and the game's import path)
from floor_baker import FloorBaker  # noqa: E402
from floor_painter import FloorPainter, _noise, _over, _smoothstep  # noqa: E402
from src.models.map import TMXMap  # noqa: E402

TMX = forest_tool.TMX
PREVIEW_TMX = "assets/tiles/_ground_preview.tmx"
OUTPUT_DIR = "build_tools/output/ground"
FLOOR_LAYER = "Ground_High_Plus"
DECO_LAYER = "Ground_Flowers_Mushrooms"
#: A tileset of its own, after all the others: woodland_floor cannot grow any more, bank_diagonals
#: follows it straight on, and its new tiles would take the river banks' gids
TILESET = "painted_ground"

#: Where ground has been painted, and how. Painted so far: the churchyard (seed 3), the chicken pen (seed 5),
#: the way from the pen's side gate to the big barn (seed 7).
GROUNDS = [
    dict(
        name="churchyard",
        box=(181, 135, 197, 151),                   # tiles: x0, y0, x1, y1
        inside=(5814, 4374, 6282, 4714),            # world px: the yard within its walls
        # Paths: (points, half width, strength). The way through runs from the north gate, parts round the
        # chest tomb and meets again before the south gate, and on out of both gates a little way
        paths=[
            ([(6064, 4300), (6064, 4400), (6061, 4458), (6066, 4492)], 15, 0.9),
            ([(6066, 4492), (6046, 4522), (6043, 4562), (6062, 4600), (6116, 4614)], 13, 0.8),
            ([(6066, 4492), (6118, 4486), (6168, 4492), (6190, 4512), (6193, 4560), (6168, 4600),
              (6116, 4614)], 12, 0.7),
            ([(6116, 4614), (6126, 4660), (6128, 4712), (6129, 4800)], 15, 0.9),
            # Fainter: along the front of the top row of graves, and out to the Celtic cross
            ([(5900, 4472), (5980, 4468), (6061, 4465), (6140, 4470), (6232, 4472)], 9, 0.6),
            ([(6044, 4556), (6000, 4602), (5962, 4624)], 9, 0.6),
        ],
        # Moss and shade at the foot of the walls, on the yard's side
        walls=[((5814, 4378), (6282, 4378)), ((6280, 4378), (6280, 4712)), ((5830, 4712), (6280, 4712)),
               ((5816, 4378), (5816, 4496))],
        # Scattered motifs: (kind, subcategories, how many)
        deco=[("grass_herbs", ["grass"], 46), ("grass_herbs", ["clover"], 12),
              ("moss", ["moss"], 8), ("flowers", ["daisies"], 5), ("flowers", ["dandelions"], 4)],
        seed=3,
    ),
    dict(
        name="chicken_pen",
        box=(186, 179, 209, 197),                   # tiles: the pen and a little outside its two gates
        inside=(6066, 5812, 6638, 6254),            # world px: within the fence
        # The two ways in, trodden from the north gate and the west side gate to where the grain is thrown,
        # a little way out of each gate, and a fainter one on into the pen
        paths=[
            ([(6384, 5730), (6384, 5800), (6380, 5870), (6356, 5950), (6318, 6020)], 18, 1.0),
            ([(5975, 6032), (6064, 6032), (6140, 6038), (6230, 6044), (6318, 6020)], 17, 0.95),
            ([(6318, 6020), (6400, 6080), (6480, 6110)], 10, 0.55),
        ],
        # Greener along the fence, where the chickens do not get at the grass
        walls=[((6066, 5814), (6638, 5814)), ((6636, 5814), (6636, 6252)), ((6066, 6252), (6636, 6252)),
               ((6068, 5814), (6068, 6252))],
        deco=[("grass_herbs", ["grass"], 22), ("grass_herbs", ["clover"], 5), ("flowers", ["dandelions"], 2)],
        # What the chickens make of it: scratched-up bare earth, worst where they are fed
        bare=[(6318, 6034, 100, 62, 1.0), (6200, 5896, 40, 26, 0.55), (6524, 6170, 52, 32, 0.6),
              (6150, 6196, 34, 22, 0.5), (6560, 5896, 30, 22, 0.45)],
        scratched=0.45,          # bare patches all over, by noise, this strong
        trampled=0.22,           # the rest of the grass worn paler
        scratches=260,           # short furrows scratched into the bare earth
        droppings=70,
        feathers=18,
        seed=5,
    ),
    dict(
        name="barn_way",
        box=(178, 176, 189, 192),                   # tiles: from the pen's side gate to the big barn's doors
        inside=(0, 0, 0, 0),                        # only a path: the grass round about is left as it is
        # On from where the pen's way out of its side gate stops, bending north-west up to the barn's doors
        paths=[
            ([(5990, 6032), (5940, 6026), (5898, 6000), (5868, 5950), (5856, 5880), (5852, 5810),
              (5838, 5752), (5812, 5726)], 21, 0.95),
            # Worn in front of the doors, between the lavender and the hay
            ([(5752, 5724), (5800, 5726), (5846, 5728)], 11, 0.7),
        ],
        joins="chicken_pen",                        # its dirt is already there: add only what it lacks
        walls=[],
        deco=[],
        seed=7,
    ),
]

#: The look
MAX_MOTIF = 36                 # px: larger motifs (whole bushes of flowers) are left out
DIRT = (142, 116, 78)          # worn through, in a path's middle
DUST = (172, 150, 104)         # its paler, drier stretches
LUSH = (64, 104, 38)           # darker grass in patches, and over the graves
DRY = (168, 164, 86)           # paler, drier grass
WALL_MOSS = (70, 92, 46)       # at the foot of a wall
SCRATCHED = (128, 102, 68)     # earth the chickens have scratched bare
FURROW = (96, 74, 48)          # a scratch in it
DROPPINGS = ((226, 222, 206), (120, 106, 80))   # its white cap, its dark rest
FEATHERS = ((246, 240, 226), (196, 150, 96), (150, 96, 56))


def _segment_distance(xs: np.ndarray, ys: np.ndarray, points: Sequence[Tuple[float, float]]) -> np.ndarray:
    """Each pixel's distance to a polyline."""
    best = np.full(xs.shape, np.inf, np.float32)
    for (ax, ay), (bx, by) in zip(points, points[1:]):
        dx, dy = bx - ax, by - ay
        length = dx * dx + dy * dy or 1.0
        t = np.clip(((xs - ax) * dx + (ys - ay) * dy) / length, 0, 1)
        best = np.minimum(best, np.hypot(xs - (ax + t * dx), ys - (ay + t * dy)))
    return best


def _layer(colour, alpha: np.ndarray) -> np.ndarray:
    out = np.empty(alpha.shape + (4,), np.float32)
    out[..., :3] = np.array(colour, np.float32) / 255
    out[..., 3] = np.clip(alpha, 0, 1)
    return out


def _marks(prng: random.Random, ground: dict, bare: np.ndarray, worn: np.ndarray,
           inside: np.ndarray) -> np.ndarray:
    """What animals leave on the ground, as a layer: furrows scratched into the bare earth (each a few
    short strokes fanning back from where the foot dug), droppings and dropped feathers."""
    h, w = bare.shape
    marks = pygame.Surface((w, h), pygame.SRCALPHA)

    def spot(test, tries=400):
        for _ in range(tries):
            x, y = prng.randrange(2, w - 4), prng.randrange(2, h - 4)
            if inside[y, x] > 0.99 and test(x, y):
                return x, y
        return None

    for _ in range(ground.get("scratches", 0)):
        at = spot(lambda x, y: bare[y, x] > 0.35 + prng.random() * 0.3)
        if at is None:
            continue
        x, y = at
        back = prng.choice((-1, 1))
        for i in range(prng.randint(2, 3)):         # a chicken scratches with both feet, backwards
            length = prng.randint(3, 6)
            dy = prng.randint(-1, 1) + i - 1
            colour = (*FURROW, prng.randint(120, 200))
            pygame.draw.line(marks, colour, (x, y + i), (x + back * length, y + i + dy))
    for _ in range(ground.get("droppings", 0)):
        at = spot(lambda x, y: worn[y, x] < 0.5)
        if at is None:
            continue
        x, y = at
        dark = (*DROPPINGS[1], 230)
        for dx, dy in prng.choice(([(0, 0), (1, 0), (0, 1)], [(0, 0), (1, 0)], [(0, 0)])):
            marks.set_at((x + dx, y + dy), dark)
        marks.set_at((x + prng.randint(0, 1), y), (*DROPPINGS[0], 240))
    for _ in range(ground.get("feathers", 0)):
        at = spot(lambda x, y: True)
        if at is None:
            continue
        x, y = at
        colour = prng.choice(FEATHERS)
        length = prng.randint(3, 5)
        slope = prng.choice((-1, 0, 1))
        for i in range(length):
            marks.set_at((x + i, y + (i * slope) // 3), (*colour, 230 if i else 160))
        marks.set_at((x, y + 1), (*colour, 120))
    return np.dstack([pygame.surfarray.array3d(marks).transpose(1, 0, 2).astype(np.float32) / 255,
                      pygame.surfarray.pixels_alpha(marks).T.astype(np.float32) / 255])


def _paths(rng, ground: dict, xs: np.ndarray, ys: np.ndarray, ts: int):
    """The paths: worn to dirt in the middle, ragged at the sides, the grass breaking through here and there.

    Draws the first three noises of an entry from its rng, in the order paint() always has."""
    h, w = xs.shape
    rough = _noise(rng, (w, h), [ts * 0.9, ts * 0.35])
    fine = _noise(rng, (w, h), [5.0, 2.5])
    worn = np.zeros((h, w), np.float32)
    for points, half, strength in ground["paths"]:
        d = _segment_distance(xs, ys, points) / half
        wear = _smoothstep(1.15, 0.15, d + (rough - 0.5) * 0.7)
        worn = np.maximum(worn, wear * strength)
    blades = fine > 0.66                     # grass standing up in the path
    path_alpha = worn * np.where(blades, 0.35, 1.0)
    dust = _smoothstep(0.45, 0.75, _noise(rng, (w, h), [ts * 3, ts * 1.2]))
    return rough, blades, worn, path_alpha, dust


def _grid(ground: dict, ts: int):
    x0, y0, x1, y1 = ground["box"]
    ys, xs = np.mgrid[0:(y1 - y0) * ts, 0:(x1 - x0) * ts].astype(np.float32)
    return xs + x0 * ts, ys + y0 * ts


def _dirt_alpha(ground: dict, ts: int) -> np.ndarray:
    """How strongly an entry's paths laid their dirt, over its box, exactly as paint() laid it."""
    xs, ys = _grid(ground, ts)
    return _paths(np.random.default_rng(ground["seed"]), ground, xs, ys, ts)[3] * 0.82


def paint(painter: FloorPainter, game_map: TMXMap, ground: dict) -> Tuple[int, int]:
    """Paint one entry of GROUNDS; returns the floor tiles and deco tiles it covers."""
    ts = painter.ts
    rng = np.random.default_rng(ground["seed"])
    prng = random.Random(ground["seed"])
    x0, y0, x1, y1 = ground["box"]
    w, h = (x1 - x0) * ts, (y1 - y0) * ts
    xs, ys = _grid(ground, ts)

    # The yard itself, its edge faded over a few pixels
    ix0, iy0, ix1, iy1 = ground["inside"]
    edge = np.minimum.reduce([xs - ix0, ix1 - xs, ys - iy0, iy1 - ys])
    inside = _smoothstep(0, 14, edge)

    rough, blades, worn, path_alpha, dust = _paths(rng, ground, xs, ys, ts)
    if ground.get("joins"):
        # The dirt another entry laid here already: add only what is missing, so the two meet without a
        # darker seam (alpha over alpha: 1 - (1 - old)(1 - extra) = the more of the two)
        joined = next(g for g in GROUNDS if g["name"] == ground["joins"])
        old = _dirt_alpha(joined, ts)
        gx0, gy0, gx1, gy1 = joined["box"]
        here = np.zeros((h, w), np.float32)
        ox0, oy0 = max(x0, gx0), max(y0, gy0)
        ox1, oy1 = min(x1, gx1), min(y1, gy1)
        if ox0 < ox1 and oy0 < oy1:
            here[(oy0 - y0) * ts:(oy1 - y0) * ts, (ox0 - x0) * ts:(ox1 - x0) * ts] =                 old[(oy0 - gy0) * ts:(oy1 - gy0) * ts, (ox0 - gx0) * ts:(ox1 - gx0) * ts]
        mine = path_alpha * 0.82
        extra = np.clip((np.maximum(mine, here) - here) / np.maximum(1 - here, 1e-3), 0, 1)
        path_alpha = np.where(mine > 0, path_alpha * extra / np.maximum(mine, 1e-6), 0)

    # The grass round about: lush and dry patches, greener over the graves, moss along the walls
    patches = _noise(rng, (w, h), [ts * 4, ts * 1.6, ts * 0.6])
    lush = _smoothstep(0.55, 0.85, patches) * 0.42
    dry = _smoothstep(0.42, 0.16, patches) * 0.30
    graves = np.zeros((h, w), np.float32)
    stones = [house for house in game_map.houses if house.epitaph]
    for stone in stones:
        r = stone.collision_rect
        cx, cy = r.centerx, r.bottom + 10
        rx, ry = r.w / 2 + 16, 22
        graves = np.maximum(graves, _smoothstep(1.0, 0.3, np.hypot((xs - cx) / rx, (ys - cy) / ry)))
    lush = np.maximum(lush, graves * 0.4 * (0.6 + 0.6 * patches))
    wall = np.zeros((h, w), np.float32)
    for a, b in ground["walls"]:
        wall = np.maximum(wall, _smoothstep(14, 2, _segment_distance(xs, ys, [a, b]) + (rough - 0.5) * 10))
    # Where animals are kept: earth scratched bare in patches, the grass between trampled paler
    bare = np.zeros((h, w), np.float32)
    if ground.get("bare") or ground.get("scratched"):
        for cx, cy, rx, ry, strength in ground.get("bare", []):
            d = np.hypot((xs - cx) / rx, (ys - cy) / ry) + (rough - 0.5) * 0.8
            bare = np.maximum(bare, _smoothstep(1.0, 0.25, d) * strength)
        spots = _noise(rng, (w, h), [ts * 1.4, ts * 0.5, 4.0])
        bare = np.maximum(bare, _smoothstep(0.68, 0.84, spots) * ground.get("scratched", 0))
        bare *= inside * (1 - wall * 0.8)
        dry = dry + ground.get("trampled", 0) * (1 - bare)
    grass_alpha = (1 - worn) * inside

    canvas = np.zeros((h, w, 4), np.float32)
    for colour, alpha in ((DRY, dry * grass_alpha),
                          (LUSH, lush * grass_alpha),
                          (WALL_MOSS, wall * 0.45 * inside),
                          (SCRATCHED, bare * np.where(blades, 0.55, 0.85) * (1 - worn)),
                          (DIRT, path_alpha * 0.82),
                          (DUST, path_alpha * dust * 0.45)):
        canvas = _over(canvas, _layer(colour, alpha))
    if ground.get("scratches") or ground.get("droppings") or ground.get("feathers"):
        canvas = _over(canvas, _marks(prng, ground, bare, worn, inside))

    # Tufts, clover, moss and flowers, off the paths and the stones
    deco = pygame.Surface((w, h), pygame.SRCALPHA)
    blocked = [house.collision_rect.inflate(4, 2) for house in game_map.houses]
    for kind, subcategories, number in ground["deco"]:
        images = [image for image in painter.motifs(kind, subcategories) if max(image.get_size()) <= MAX_MOTIF]
        if not images:
            print(f"No {kind} motifs {subcategories} in the catalog")
            continue
        placed = 0
        for _ in range(number * 60):
            if placed >= number:
                break
            image = prng.choice(images)
            if prng.random() < 0.5:
                image = pygame.transform.flip(image, True, False)
            iw, ih = image.get_size()
            px, py = prng.randrange(w - iw), prng.randrange(h - ih)
            foot = (px + iw // 2, py + ih - 2)
            world = pygame.Rect(px + x0 * ts, py + y0 * ts, iw, ih)
            if (inside[py:py + ih, px:px + iw].min() < 0.99 or worn[py:py + ih, px:px + iw].max() > 0.12
                    or any(world.colliderect(r) for r in blocked)):
                continue
            # Moss keeps to the walls and the graves' feet, flowers to the open grass
            if kind == "moss" and wall[foot[1], foot[0]] < 0.08 and graves[foot[1], foot[0]] < 0.12:
                continue
            deco.blit(image, (px, py))
            placed += 1
        if placed < number:
            print(f"  only {placed} of {number} {kind} {subcategories} found room")
    tufts = np.dstack([pygame.surfarray.array3d(deco).transpose(1, 0, 2).astype(np.float32) / 255,
                       pygame.surfarray.pixels_alpha(deco).T.astype(np.float32) / 255])
    return painter._cut(canvas, FLOOR_LAYER, x0, y0), painter._cut(tufts, DECO_LAYER, x0, y0)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--preview", action="store_true",
                        help=f"only render the result to {OUTPUT_DIR}/, leave the map alone")
    parser.add_argument("--only", nargs="+", metavar="NAME", help="paint only these entries of GROUNDS")
    args = parser.parse_args()

    tmx = forest_tool.Map(TMX)
    game_map = TMXMap(TMX)
    doors_before = len(game_map.doors)
    painter = FloorPainter(tmx, FLOOR_LAYER, DECO_LAYER, TILESET, FloorBaker(tmx, FLOOR_LAYER))
    # A preview leaves the tileset as it was, or takes it away again if it made it
    saved = {path: open(path, "rb").read() if os.path.exists(path) else None for path in painter.files()}
    grounds = [g for g in GROUNDS if not args.only or g["name"] in args.only]
    for ground in grounds:
        floor, deco = paint(painter, game_map, ground)
        print(f"{ground['name']}: ground on {floor} tiles, tufts on {deco}")
    painter.save()
    print(f"{painter.added} tiles added to {TILESET}.png")

    target = PREVIEW_TMX if args.preview else TMX
    tmx.save(target, [])
    after = TMXMap(target)
    if len(after.doors) != doors_before:
        print(f"WARNING: {doors_before - len(after.doors)} door(s) lost their step")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    for ground in grounds:
        x0, y0, x1, y1 = ground["box"]
        forest_tool.render(target, OUTPUT_DIR, (x0 - 3, y0 - 2, x1 + 1, y1 + 1), scale=1.0)
        os.replace(os.path.join(OUTPUT_DIR, "forest_game.png"), os.path.join(OUTPUT_DIR, f"{ground['name']}.png"))
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
