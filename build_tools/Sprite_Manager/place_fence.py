"""Lays a fence style's plan onto Map1.tmx: one Fence_Frontal object per piece, and a Gate in every gate gap.

The style's fence.json "plan" says where its pieces go ([orientation, tiles,
x, y], x and y in tiles from its top-left post); given where that post's foot
is on the map, every piece becomes a "Fence_Frontal" object on the Houses
layer at its raster's bottom-left corner, with the collision its raster gives
(fences.Raster.tiled_properties) and its picture as File_name.

A gap of GATE_TILES between two horizontal pieces of a row gets a Gate (src/models/gate.py)
when --gate names its pictures in houses/gates/ (<gate>_closed.png and
<gate>_open_down.png / _open_up.png, as iron_gate_painter.py makes them):
its leaves swing into the yard, down the picture in the top row, up it in the
others. A gap in a vertical run is reported and left open: there is no gate
seen from the side yet.

The objects are named Fence_<name> and Gate_<name>_North (the top row) or
_South / _<n>. Running it again replaces the objects of that name, keeping
their ids and their place in the file, so re-laying an unchanged plan changes
nothing. Close Tiled first. The map keeps its own line endings.

    python build_tools/Sprite_Manager/place_fence.py churchyard_wall 5808 4368 --name Churchyard \\
        --gate churchyard_gate --dry-run

The fence mode of the Placing Helper (build_tools/Placing_Helper/fence_plans.json)
gives a drawn fence's plan and its top-left post's foot as "plan" and "origin_px".
"""

import argparse
import os
import re
import sys
from pathlib import Path

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
import pygame
from fences import HORIZONTAL, TILE, find_styles

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / '.claude' / 'skills' / 'place-building'))
import itertools

import place_building as pb

GATES_DIR = ROOT / 'assets' / 'map_sprites' / 'houses' / 'gates'
GATE_TILES = 2                     # a gate's picture spans two tiles, pillar centre to pillar centre
# A Gate's object on the canvas iron_gate_painter.py paints (2 x 3 tiles, the foot 2 tiles down): its
# gateway between the pillars' shafts, 16 px deep about the foot, sorted with its wall
GATE_PROPS = {'Tiles_to_right': 2, 'Tiles_up': 3, 'Collision_to_right': 1, 'Collision_up': 1,
              'Col_margin_left_pixel': -9, 'Col_margin_right_pixel': 22,
              'Col_margin_up_pixel': 8, 'Col_margin_down_pixel': -24, 'Sort_up_pixel': 16}


def gate_gaps(plan):
    """[(row y, first post x)] of every GATE_TILES gap between horizontal pieces of a row, and the
    vertical gaps, which get no gate: ([...], [(x, y)])."""
    rows, columns = {}, {}
    for o, n, x, y in plan:
        if o == HORIZONTAL:
            rows.setdefault(y, []).append((x, n))
        else:
            columns.setdefault(x, []).append((y, n))
    gaps = []
    for y, pieces in sorted(rows.items()):
        pieces.sort()
        gaps += [(y, ax + an) for (ax, an), (bx, _) in itertools.pairwise(pieces) if bx - (ax + an) == GATE_TILES]
    side = []
    for x, pieces in sorted(columns.items()):
        pieces.sort()
        side += [(x, ay + an) for (ay, an), (by, _) in itertools.pairwise(pieces) if by - (ay + an) == GATE_TILES]
    return gaps, side


def objects(style, x0, y0, name, gate):
    """[(name, Tiled type, x, y, properties)] for the plan laid with its top-left post's foot at x0, y0."""
    out = []
    for o, n, px, py in style.plan:
        piece = style.piece(o, n)
        raster = piece.raster
        sx, sy = raster.start
        x = x0 + round((px - sx) * TILE)
        y = y0 + round((py - sy) * TILE) + raster.pixels[1]
        props = dict(raster.tiled_properties())
        props['File_name'] = piece.file_name
        out.append((f'Fence_{name}', 'Fence_Frontal', x, y, props))
    gaps, side = gate_gaps(style.plan)
    for x, y in side:
        print(f'A gap of {GATE_TILES} in the vertical run at {x}, {y} left open: no side gate yet')
    if gate:
        top = min((y for y, _ in gaps), default=0)
        rows = sorted({y for y, _ in gaps})
        for i, (y, x) in enumerate(gaps):
            north = y == top
            label = 'North' if north else ('South' if len(rows) == 2 and y == rows[-1] else str(i + 1))
            props = dict(GATE_PROPS, File_name=f'gates/{gate}_closed.png',
                         Open_file_name=f"gates/{gate}_open_{'down' if north else 'up'}.png",
                         Opens='down' if north else 'up')
            out.append((f'Gate_{name}_{label}', 'Gate', x0 + x * TILE, y0 + y * TILE + TILE, props))
    return out


def lay(text, placed, name):
    """The map's text with the objects named Fence_<name> / Gate_<name>_* replaced by `placed`."""
    nl = '\r\n' if '\r\n' in text else '\n'
    pattern = re.compile(r'(\r?\n) *<object id="(\d+)" name="(?:Fence_' + re.escape(name)
                         + r'|Gate_' + re.escape(name) + r'_\w+)" .*?</object>', re.DOTALL)
    old = list(pattern.finditer(text))
    ids = [int(m.group(2)) for m in old]
    nxt = re.search(r'nextobjectid="(\d+)"', text)
    next_id = int(nxt.group(1))
    xml = []
    for i, (obj_name, kind, x, y, props) in enumerate(placed):
        if i < len(ids):
            obj_id = ids[i]
        else:
            obj_id, next_id = next_id, next_id + 1
        xml.append(' ' + pb.object_xml(obj_id, obj_name, kind, x, y, props, nl))
        print(obj_id, obj_name, kind, x, y, props['File_name'])
    block = ''.join(nl + x for x in xml)
    if old:
        at = old[0].start()
        text = pattern.sub('', text)
    else:
        houses = re.search(r'<objectgroup id="\d+" name="Houses">.*?(\s*</objectgroup>)', text, re.DOTALL)
        at = houses.start(1)
    text = text[:at] + block + text[at:]
    return re.sub(r'nextobjectid="\d+"', f'nextobjectid="{next_id}"', text, count=1)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('style', help="the style's folder name, e.g. churchyard_wall")
    parser.add_argument('x', type=float, help="world x of the plan's top-left post's foot")
    parser.add_argument('y', type=float, help='its world y')
    parser.add_argument('--name', required=True, help='the objects are named Fence_<name> and Gate_<name>_...')
    parser.add_argument('--gate', help='the gate pictures in houses/gates/, e.g. churchyard_gate')
    parser.add_argument('--dry-run', action='store_true', help='print the objects, write nothing')
    args = parser.parse_args(argv)
    pygame.init()
    pygame.display.set_mode((1, 1))
    style = next((s for s in find_styles() if s.name == args.style), None)
    if style is None or not style.plan:
        sys.exit(f'No fence style {args.style!r} with a plan')
    missing = [p.file_name for p in {style.piece(o, n) for o, n, _, _ in style.plan} if not p.exists()]
    if missing:
        sys.exit(f'Pieces not drawn yet: {", ".join(sorted(missing))}')
    if args.gate:
        for suffix in ('closed', 'open_down', 'open_up'):
            if not (GATES_DIR / f'{args.gate}_{suffix}.png').is_file():
                sys.exit(f'No gate picture gates/{args.gate}_{suffix}.png')
    placed = objects(style, round(args.x), round(args.y), args.name, args.gate)
    text, _ = pb.load_tmx()
    new = lay(text, placed, args.name)
    if args.dry_run:
        print('Dry run: nothing written')
        return
    with open(pb.TMX, 'w', encoding='utf-8', newline='') as f:
        f.write(new)
    print(f'{len(placed)} objects laid in {Path(pb.TMX).name}')


if __name__ == '__main__':
    main()
