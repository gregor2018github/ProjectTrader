"""Lay dirt roads into Map1.tmx, two tiles wide, joined to the roads already there.

Run from the repo root with Tiled closed:

    python build_tools/Road_Builder/lay_road.py --preview   # pictures only, map untouched
    python build_tools/Road_Builder/lay_road.py             # write the roads into the map

A road is a polyline in ROADS: the tile of its top-left cell at the start, at
each bend and at the end, so every leg runs straight across or straight down
and covers that cell and the one right of / below it. Legs of one road, and
roads of the list, may meet and cross anywhere.

The map's roads are gaps between grass: dirt underneath, with the ragged edge
of the grass laid over the road cells along their sides. This does the same,
from the squares of ground_tiles.png: on every road cell Ground_Mid gets dirt
(the dirt square), Ground_High the grass edge each side next to open ground
needs (the grass square's edges and corners, the grass frame's inner corners),
Ground_High_Plus a second corner if one cell needs two, and
Ground_Flowers_Mushrooms is cleared. Layers below Ground_Mid are left alone;
the dirt covers them.

Roads already on the map within JOIN_REACH cells of a new one are found by
colour (as the Town Plan finds them) and laid again the same way, so the grass
edge along their side opens where the new road comes in. Water is not paved:
the road stops at the bank, and the crossings are printed with a rectangle for
a bridge over each (Bridges layer, see src/models/bridge.py), which is put in
by hand.
"""
import os
import re
import sys
from typing import Dict, Iterable, List, Optional, Set, Tuple

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
sys.path.insert(0, '.')

import pygame  # noqa: E402
import pytmx  # noqa: E402

TMX = 'assets/tiles/Map1.tmx'
PREVIEW_TMX = 'assets/tiles/_road_preview.tmx'   # next to the tilesets, which it names relatively
PREVIEW_DIR = 'build_tools/output/road_preview'
TILE = 32
GROUND_FIRSTGID = 50087      # <tileset firstgid=... name="ground_tiles">
GROUND_COLS = 100

#: Each road: a name and the top-left cell of its two-wide strip at every bend.
ROADS: List[Tuple[str, List[Tuple[int, int]]]] = [
    ('West road to the warehouse', [(0, 86), (77, 86)]),
    ('South-west road', [(0, 218), (96, 218)]),
    ('South road', [(155, 212), (96, 212), (96, 299)]),
    ('South-east road', [(155, 203), (168, 203), (168, 223), (299, 223)]),
]

#: Existing road cells this close to a new one are laid again with it.
JOIN_REACH = 2
#: How much of a cell must be road coloured for it to count as road already.
ROAD_SHARE = 0.37

# Where the pieces are in ground_tiles.png, as (col, row)
DIRT = (1, 1, 20)                      # dirt square interior: first col, first row, size
GRASS_LEFT_COL = 42                    # grass square's right edge: grass on the cell's left
GRASS_RIGHT_COL = 0                    # its left edge: grass on the right
GRASS_TOP_ROW = 64                     # its bottom edge: grass along the top
GRASS_BOTTOM_ROW = 22                  # its top edge: grass along the bottom
GRASS_ROWS = (23, 41)                  # full rows of the square: first, count
GRASS_COLS = (1, 41)                   # full columns
INNER_CORNER = {                       # grass frame's hole: grass along two sides
    ('n', 'w'): (46, 24), ('n', 'e'): (64, 24),
    ('s', 'w'): (46, 42), ('s', 'e'): (64, 42),
}
OUTER_CORNER = {                       # grass square's corners: grass in one corner
    ('n', 'w'): (42, 64), ('n', 'e'): (0, 64),
    ('s', 'w'): (42, 22), ('s', 'e'): (0, 22),
}

LAYER_RE = re.compile(
    r'(<layer id="\d+" name="([^"]+)" width="(\d+)" height="(\d+)">\s*'
    r'<data encoding="csv">\s*)(.*?)(\s*</data>)', re.S)

Cell = Tuple[int, int]


def gid(col: int, row: int) -> int:
    return GROUND_FIRSTGID + row * GROUND_COLS + col


# ------------------------------------------------------------------ TMX text

def load_layers(text: str) -> Dict[str, List[List[int]]]:
    layers = {}
    for m in LAYER_RE.finditer(text):
        w = int(m.group(3))
        nums = [int(v) for v in m.group(5).replace('\r', '').replace('\n', '').split(',')]
        layers[m.group(2)] = [nums[i * w:(i + 1) * w] for i in range(len(nums) // w)]
    return layers


def write_layers(text: str, layers: Dict[str, List[List[int]]], path: str) -> None:
    nl = '\r\n' if '\r\n' in text else '\n'

    def rep(m):
        rows = layers[m.group(2)]
        return m.group(1) + (',' + nl).join(','.join(map(str, r)) for r in rows) + m.group(6)
    with open(path, 'w', encoding='utf-8', newline='') as f:
        f.write(LAYER_RE.sub(rep, text))


# ------------------------------------------------------------------ the map as it is

def road_cells(points: List[Cell]) -> Set[Cell]:
    """The cells of one road: a two-wide strip along each leg."""
    cells = set()
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x0 != x1 and y0 != y1:
            raise SystemExit(f'leg {(x0, y0)} -> {(x1, y1)} is not straight')
        for x in range(min(x0, x1), max(x0, x1) + 2):
            for y in range(min(y0, y1), max(y0, y1) + 2):
                cells.add((x, y))
    return cells


def survey(tmx_map) -> Tuple[Set[Cell], Set[Cell], Set[Cell]]:
    """The cells already road, the cells under water, and paving and sand.

    The last are no road but no grass either, so a road next to them gets no
    grass edge on that side.
    """
    from src.ui.layout_modules.town_plan import terrain
    from src.ui.layout_modules.town_plan.style import GROUND_PLAZA, GROUND_ROAD, GROUND_SAND
    px = 8
    ground = terrain._composite(tmx_map.tmx_data, px)
    need = ROAD_SHARE * px * px

    def cells_of(colour) -> Set[Cell]:
        mask = terrain._pick(ground, colour)
        return {(cx, cy) for cy in range(tmx_map.height) for cx in range(tmx_map.width)
                if sum(mask.get_at((cx * px + i, cy * px + j)) for i in range(px) for j in range(px)) >= need}
    roads = cells_of(GROUND_ROAD)
    bare = cells_of(GROUND_PLAZA) | cells_of(GROUND_SAND)
    water = set(tmx_map.water_tiles)
    for w in tmx_map.waters:
        box = w.bounding_rect
        for cy in range(box.top // TILE, box.bottom // TILE + 1):
            for cx in range(box.left // TILE, box.right // TILE + 1):
                if w.contains_point(cx * TILE + TILE / 2, cy * TILE + TILE / 2):
                    water.add((cx, cy))
    return roads, water, bare


# ------------------------------------------------------------------ laying

def pieces(cell: Cell, is_open) -> List[Tuple[int, int]]:
    """The grass edge tiles to lay over a road cell, as (col, row) in ground_tiles.

    Args:
        cell: The road cell.
        is_open: Whether a cell is open ground (not road, not water).
    """
    x, y = cell
    side = {'n': is_open((x, y - 1)), 's': is_open((x, y + 1)),
            'w': is_open((x - 1, y)), 'e': is_open((x + 1, y))}
    if (side['n'] and side['s']) or (side['w'] and side['e']):
        raise SystemExit(f'road at {cell} is only one cell wide')
    out = []
    vertical = 'n' if side['n'] else 's' if side['s'] else None
    horizontal = 'w' if side['w'] else 'e' if side['e'] else None
    if vertical and horizontal:
        out.append(INNER_CORNER[(vertical, horizontal)])
    elif vertical:
        out.append((GRASS_COLS[0] + x % GRASS_COLS[1], GRASS_TOP_ROW if vertical == 'n' else GRASS_BOTTOM_ROW))
    elif horizontal:
        out.append((GRASS_LEFT_COL if horizontal == 'w' else GRASS_RIGHT_COL, GRASS_ROWS[0] + y % GRASS_ROWS[1]))
    # Grass only diagonally off: the corner of the block reaching in
    for v, dy in (('n', -1), ('s', 1)):
        for h, dx in (('w', -1), ('e', 1)):
            if not side[v] and not side[h] and is_open((x + dx, y + dy)):
                out.append(OUTER_CORNER[(v, h)])
    if len(out) > 2:
        raise SystemExit(f'road at {cell} needs {len(out)} grass pieces, at most 2 fit')
    return out


def lay(layers: Dict[str, List[List[int]]], cells: Iterable[Cell], is_open) -> None:
    mid, high = layers['Ground_Mid'], layers['Ground_High']
    plus, flowers = layers['Ground_High_Plus'], layers['Ground_Flowers_Mushrooms']
    first, size = DIRT[0], DIRT[2]
    for x, y in cells:
        mid[y][x] = gid(first + x % size, DIRT[1] + y % size)
        found = pieces((x, y), is_open)
        high[y][x] = gid(*found[0]) if found else 0
        plus[y][x] = gid(*found[1]) if len(found) > 1 else 0
        flowers[y][x] = 0


def crossings(cells: Set[Cell], water: Set[Cell]) -> List[Tuple[str, pygame.Rect]]:
    """A bridge rectangle for every place a road crosses water, one tile of land each end.

    Returns:
        A line for Tiled and the rectangle, in world pixels, of each crossing.
    """
    wet = sorted(cells & water)
    groups: List[Set[Cell]] = []
    for c in wet:
        near = [g for g in groups if any(abs(c[0] - o[0]) <= 1 and abs(c[1] - o[1]) <= 1 for o in g)]
        merged = {c}.union(*near)
        groups = [g for g in groups if g not in near] + [merged]
    out = []
    for g in groups:
        xs, ys = [c[0] for c in g], [c[1] for c in g]
        if max(ys) - min(ys) <= 1:          # across: the road runs east-west
            x, w = (min(xs) - 1) * TILE, (max(xs) - min(xs) + 3) * TILE
            y = min(ys) * TILE - 16
            out.append((f'across  x={x} y={y} width={w} height=82  Deck_top=0.8 Deck_bottom=2.1',
                        pygame.Rect(x, y, w, 82)))
        else:                               # along: north-south
            x, h = min(xs) * TILE - 16, (max(ys) - min(ys) + 3) * TILE
            y = (min(ys) - 1) * TILE
            out.append((f'along   x={x} y={y} width=96 height={h}  Deck_left=0.5 Deck_right=2.5',
                        pygame.Rect(x, y, 96, h)))
    return out


# ------------------------------------------------------------------ preview

def render(path: str, regions: List[Tuple[int, int, int, int]], out_prefix: str) -> None:
    tmx = pytmx.load_pygame(path)
    for k, (x0, y0, x1, y1) in enumerate(regions):
        surf = pygame.Surface(((x1 - x0) * TILE, (y1 - y0) * TILE))
        for layer in tmx.visible_layers:
            if isinstance(layer, pytmx.TiledTileLayer) and layer.name.startswith('Ground'):
                for x, y, img in layer.tiles():
                    if x0 <= x < x1 and y0 <= y < y1:
                        surf.blit(img, ((x - x0) * TILE, (y - y0) * TILE))
        surf = pygame.transform.smoothscale(surf, (surf.get_width() // 2, surf.get_height() // 2))
        pygame.image.save(surf, f'{out_prefix}_{k}.png')


def main() -> None:
    preview = '--preview' in sys.argv
    pygame.init()
    pygame.display.set_mode((1, 1))
    from src.models.map import TMXMap
    tmx_map = TMXMap(TMX)
    existing, water, bare = survey(tmx_map)

    new: Set[Cell] = set()
    for _, points in ROADS:
        new |= road_cells(points)
    on_map = {(x, y) for x, y in new if 0 <= x < tmx_map.width and 0 <= y < tmx_map.height}
    paved = on_map - water
    joined = {(x, y) for x, y in existing
              if any((x + dx, y + dy) in paved
                     for dx in range(-JOIN_REACH, JOIN_REACH + 1) for dy in range(-JOIN_REACH, JOIN_REACH + 1))}
    road = existing | paved

    def is_open(cell: Cell) -> bool:
        x, y = cell
        if not (0 <= x < tmx_map.width and 0 <= y < tmx_map.height):
            return False                 # the road runs on off the map
        return cell not in road and cell not in water and cell not in bare

    with open(TMX, encoding='utf-8', newline='') as f:
        text = f.read()
    layers = load_layers(text)
    lay(layers, sorted(paved | joined), is_open)

    print(f'{len(paved)} road cells, {len(joined - paved)} cells of old road laid again')
    bridges = crossings(on_map, water)
    for line, _ in bridges:
        print('bridge', line)

    if preview:
        os.makedirs(PREVIEW_DIR, exist_ok=True)
        regions = []
        for _, points in ROADS:
            for x, y in points:
                regions.append((max(0, x - 8), max(0, y - 8), min(300, x + 10), min(300, y + 10)))
        for _, rect in bridges:
            x, y = rect.centerx // TILE, rect.centery // TILE
            regions.append((max(0, x - 9), max(0, y - 9), min(300, x + 9), min(300, y + 9)))
        write_layers(text, layers, PREVIEW_TMX)
        try:
            render(PREVIEW_TMX, regions, os.path.join(PREVIEW_DIR, 'after'))
            render(TMX, regions, os.path.join(PREVIEW_DIR, 'before'))
        finally:
            os.remove(PREVIEW_TMX)
        print(f'previews in {PREVIEW_DIR}, map untouched')
    else:
        write_layers(text, layers, TMX)
        print('written to', TMX)


if __name__ == '__main__':
    main()
