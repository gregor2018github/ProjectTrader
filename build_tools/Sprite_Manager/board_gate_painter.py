"""Paints the sheep yard's two wooden board gates and puts them into the gaps of its stone wall.

The yard north of the market (the old hand-made walls Fence_4 over Fence_3,
with Fence_1 and the barn-house House_9 along its south side) has two
openings, each of its own width:

- north, between two of the wall's pillars, 89 px: a double gate;
- south, between the end of the low wall and the barn-house's stone side,
  43 px: a single leaf, hung on the wall, latching on the house.

Each gate is cut to its own gap (GATES), so its wood meets the stone at
both ends: a leaf reaches a pixel under the stone on either side, and the gate
is sorted just before the walls round it, so the stone is drawn over that
pixel and the joint shows no seam and no air.

They differ from the field's farm gate (wood_fence_painter.py), which has
rails: these are board gates, upright pales with a pixel of light between
them and rounded tops, two ledges across and a brace between them, hung on
black iron straps. Open, a leaf is turned about its hinge like the iron
gate's (iron_gate_painter.place_leaf's rule), into the yard.

    python board_gate_painter.py --preview gates.png   # the pictures, enlarged
    python board_gate_painter.py --write               # into houses/gates/
    python board_gate_painter.py --place [--dry-run]   # the Gate objects into Map1.tmx

Each picture is a canvas of whole tiles (a House's Tiles_to_right x
Tiles_up, so it is not scaled), its gap from `left` px, its foot line
`canvas_foot` px down (RAISE above the wall's); its Tiled point is the canvas's bottom-left corner.
"""

import argparse
import math
import os
import random
import sys
import zlib
from dataclasses import dataclass
from pathlib import Path

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
import pygame
from fences import TILE
from iron_gate_painter import GATES_DIR
from stone_wall_painter import shade
from wood_fence_painter import PALETTE, _grain, _wood

RAISE = 6                  # px the gates stand above the walls' foot lines: level with them, they look sunk
IRON = (44, 42, 46)
IRON_LIT = (92, 90, 96)
SHADOW = (20, 26, 12)


@dataclass(frozen=True)
class GateSpec:
    """One gate: where its gap is on the map and how it is made."""
    label: str              # Gate_Sheep_Yard_<label>
    gap_x: int              # world x of the gap's first free pixel
    gap: int                # px from stone to stone
    foot: int               # world y of the wall's foot line
    tiles: tuple            # canvas (w, h) in tiles
    point: tuple            # its Tiled point, the canvas's bottom-left corner: whole tiles, so it is drawn
                            # at a whole screen pixel at every zoom, as the walls round it are
    leaves: int             # 1 (hung on the left) or 2
    height: int             # px from the foot to the pales' tops
    opens: str              # 'down' or 'up' the picture: into the yard
    angle: int              # degrees it swings open

    @property
    def name(self):
        return f'sheep_gate_{self.label.lower()}'

    @property
    def size(self):
        return self.tiles[0] * TILE, self.tiles[1] * TILE

    @property
    def left(self):
        """The gap's first pixel on the canvas."""
        return self.gap_x - self.point[0]

    @property
    def canvas_foot(self):
        """The gate's foot line on the canvas: the wall's, RAISE px up."""
        return self.foot - RAISE - (self.point[1] - self.size[1])


GATES = (
    GateSpec('North', 4534, 89, 5351, (4, 4), (141 * TILE, 169 * TILE), 2, 27, 'down', 80),
    GateSpec('South', 4576, 43, 5950, (3, 4), (142 * TILE, 187 * TILE), 1, 22, 'up', 86),
)
NAME = 'Sheep_Yard'
SORT_BEFORE_WALL = 2        # px it sorts before its foot line, so the walls round it are drawn over it


def leaf_pixels(spec, width, seed, plain=False):
    """One leaf flat, hung on its left: {(along, y): colour}, along 0 at the hinge, y on the canvas.

    Upright pales (3 or 4 px, a dark pixel between), a rounded top to each, two ledges across and a brace
    rising from the lower ledge at the hinge to the upper at the far side. `plain` leaves out the straps'
    rivets and the latch, which only clutter a leaf seen at a slant."""
    rng = random.Random(seed)
    pal = PALETTE
    px = {}
    top = spec.canvas_foot - spec.height
    ledges = (spec.canvas_foot - spec.height + 5, spec.canvas_foot - 6)     # each ledge's top row, 3 deep
    u = 0
    while u < width:
        board = min(rng.choice((3, 4, 4)), width - u)
        base = _wood(pal, rng, pal.rail)
        rise = rng.choice((0, 0, 1, -1))                    # pales a pixel taller or shorter
        for i in range(board):
            k = 1.12 if i == 0 else (0.82 if i == board - 1 else 1.0)
            t = top - rise + (1 if board > 2 and i in (0, board - 1) else 0)   # a rounded top
            for y in range(t, spec.canvas_foot):
                colour = _grain(shade(base, k * (1.0 - 0.08 * (y - t) / spec.height)), rng)
                if y == t:
                    colour = shade(pal.end_grain, 0.9 if i else 1.0)
                px[(u + i, y)] = colour
            px[(u + i, spec.canvas_foot)] = pal.outline
        u += board
        if u < width:                                       # the chink between two pales
            for y in range(top + 2, spec.canvas_foot):
                px[(u, y)] = shade(pal.outline, 0.9)
            u += 1
    ledge_base = _wood(pal, rng, pal.rail)
    for ly in ledges:
        for u in range(width):
            for r, k in enumerate((1.16, 0.98, 0.78)):
                px[(u, ly + r)] = _grain(shade(ledge_base, k), rng)
            px[(u, ly + 3)] = pal.outline
    lo, hi = ledges[1] - 1, ledges[0] + 3                   # the brace, from the hinge's foot up
    for u in range(2, width - 2):
        y = round(lo + (hi - lo) * (u - 2) / max(1, width - 5))
        px[(u, y)] = shade(ledge_base, 1.12)
        px[(u, y + 1)] = shade(ledge_base, 0.88)
        px[(u, y + 2)] = pal.outline
    strap = min(10, width // 2)                             # iron straps along the ledges from the hinge
    for ly in ledges:
        for u in range(strap):
            px[(u, ly + 1)] = IRON_LIT if u == 0 else IRON
        if not plain:
            px[(strap - 2, ly + 1)] = IRON_LIT
    if not plain:
        y = (ledges[0] + ledges[1]) // 2                    # the latch on the far stile
        px[(width - 2, y)] = IRON_LIT
        px[(width - 2, y + 1)] = IRON
        px[(width - 3, y + 1)] = IRON
    return px


def place_leaf(surface, px, hinge, direction, angle, swing):
    """A leaf with its hinge at x `hinge`, running `direction` (+1 right, -1 left) shut; open it is turned
    `angle` degrees about it, its far edge down the picture (`swing` +1) or up (-1), farther columns first."""
    w, h = surface.get_size()
    cos, sin = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    columns = sorted({u for u, _ in px})
    if swing < 0:
        columns.reverse()
    for u in columns:
        x = hinge + direction * round(u * cos)
        dy = swing * round(u * sin)
        for (cu, y), colour in px.items():
            if cu == u and 0 <= x < w and 0 <= y + dy < h:
                surface.set_at((x, y + dy), (*colour, 255))


def paint(spec, state):
    """'closed' or 'open'."""
    surface = pygame.Surface(spec.size, pygame.SRCALPHA)
    # A pixel under the stone at both ends: the walls are drawn over it
    first, last = spec.left - 1, spec.left + spec.gap
    span = last - first + 1
    widths = [span] if spec.leaves == 1 else [span // 2, span - span // 2]
    seed = zlib.crc32(spec.name.encode())
    plain = state != 'closed'
    hinged = [(leaf_pixels(spec, widths[0], seed, plain), first, +1)]
    if spec.leaves == 2:
        right = leaf_pixels(spec, widths[1], seed + 1, plain)
        hinged.append((right, last, -1))
    if state == 'closed':
        for x in range(spec.left, spec.left + spec.gap):
            for i, alpha in enumerate((60, 34)):
                surface.set_at((x, spec.canvas_foot + 1 + i), (*SHADOW, alpha))
        for px, hinge, direction in hinged:
            place_leaf(surface, px, hinge, direction, 0, 0)
    else:
        swing = 1 if spec.opens == 'down' else -1
        for px, hinge, direction in hinged:
            place_leaf(surface, px, hinge, direction, spec.angle, swing)
    return surface


def pictures():
    return {(spec, state): paint(spec, state) for spec in GATES for state in ('closed', 'open')}


def file_names(spec):
    return f'gates/{spec.name}_closed.png', f'gates/{spec.name}_open.png'


def tiled_objects():
    """[(name, 'Gate', x, y, properties)] for place_fence.lay."""
    out = []
    for spec in GATES:
        h = spec.size[1]
        x0, y0 = spec.point
        # The gateway's box on the canvas: stone to stone, 16 px deep about the foot
        cx, cy, cw, ch = spec.left, spec.canvas_foot + RAISE - 12, spec.gap, 16     # on the wall's foot line
        tiles_right, tiles_up = -(-cw // TILE), -(-ch // TILE)
        down = (cy + ch) - h
        left = -cx
        closed, opened = file_names(spec)
        props = {'Tiles_to_right': spec.tiles[0], 'Tiles_up': spec.tiles[1],
                 'Collision_to_right': tiles_right, 'Collision_up': tiles_up,
                 'Col_margin_left_pixel': left, 'Col_margin_right_pixel': cw - tiles_right * TILE - left,
                 'Col_margin_up_pixel': ch - tiles_up * TILE - down, 'Col_margin_down_pixel': down,
                 'Sort_up_pixel': h - spec.canvas_foot + SORT_BEFORE_WALL,
                 'File_name': closed, 'Open_file_name': opened, 'Opens': spec.opens}
        out.append((f'Gate_{NAME}_{spec.label}', 'Gate', x0, y0, props))
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--preview', help='write the pictures side by side, enlarged, to this PNG')
    parser.add_argument('--write', action='store_true', help=f'save them into {GATES_DIR}')
    parser.add_argument('--place', action='store_true', help='put the Gate objects into Map1.tmx')
    parser.add_argument('--dry-run', action='store_true', help='with --place: print, write nothing')
    args = parser.parse_args(argv)
    pygame.init()
    pygame.display.set_mode((1, 1))
    done = pictures()
    if args.preview:
        k = 5
        w = sum(s.size[0] + 8 for s, _ in done) * k
        out = pygame.Surface((w, max(s.size[1] for s, _ in done) * k))
        out.fill((96, 140, 70))
        x = 0
        for (spec, _), picture in done.items():
            out.blit(pygame.transform.scale(picture, (spec.size[0] * k, spec.size[1] * k)), (x, 0))
            x += (spec.size[0] + 8) * k
        pygame.image.save(out, args.preview)
        print(f'Preview: {args.preview}')
    if args.write:
        for (spec, state), picture in done.items():
            path = GATES_DIR / f'{spec.name}_{state}.png'
            pygame.image.save(picture, str(path))
            print(f'Saved {path.name}')
    if args.place:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / '.claude' / 'skills' / 'place-building'))
        import place_building as pb
        from place_fence import lay
        text, _ = pb.load_tmx()
        new = lay(text, tiled_objects(), NAME)
        if args.dry_run:
            print('Dry run: nothing written')
        else:
            with open(pb.TMX, 'w', encoding='utf-8', newline='') as f:
                f.write(new)
            print('Gates laid in Map1.tmx')
    if not (args.preview or args.write or args.place):
        sys.exit('Nothing to do: --preview PNG, --write and/or --place')


if __name__ == '__main__':
    main()
