"""Paints the churchyard's wrought-iron gate pixel by pixel: shut, and swung open either way.

A double gate for a 2-tile opening between two of the churchyard wall's
pillars (stone_wall_painter.py): two leaves of flat bars between stiles and
rails, rings in their middle panel, their tops an arch of spear points
rising to where they meet, a latch there. Nothing spans the gateway above
them, so a walker passing through is never drawn under iron.

Each picture is a canvas of 2 x 3 tiles, the run's foot FOOT px from its top,
its left edge on the left pillar's centre, so a gate stands between pillars
two tiles apart; the game draws it as a Gate (src/models/gate.py) whose
Tiled point is the canvas's bottom-left corner.

An open leaf is the same leaf turned OPEN_ANGLE about its hinge, into the yard:
seen from above at the game's slant, its far edge moves down the picture
(towards the viewer, `open_down`) or up it (`open_up`) by as much as it
comes in, so its columns are laid one by one at their new place, the
farther ones first. It swings nearly back against the wall, so the leaves
reach only a few px into the gateway and the player walks between them.

    python iron_gate_painter.py --preview gate.png    # all three, enlarged
    python iron_gate_painter.py --write               # into assets/map_sprites/houses/gates/
"""

import argparse
import math
import os
import sys
from pathlib import Path

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
import pygame

from stone_wall_painter import shade

GATES_DIR = Path(__file__).resolve().parents[2] / 'assets' / 'map_sprites' / 'houses' / 'gates'
NAME = 'churchyard_gate'
SIZE = (64, 96)
FOOT = 64                 # the run's foot line, as on the wall's rasters (1.5 tiles down a 2-tile raster) + a tile
LEFT, RIGHT = 9, 54       # the opening between the pillars' shafts
LEAF = 23                 # px a leaf is wide, hinge to meeting stile
OPEN_ANGLE = 80           # degrees a leaf swings open: each reaches 4 px in, 38 px clear for a 32 px walker

IRON = (58, 56, 63)
DARK = (34, 33, 38)
LIGHT = (112, 110, 121)
RUST = (112, 74, 50)

BARS = (4, 7, 10, 13, 16, 19)      # along a leaf, from its hinge
TOP_RAIL = -26                      # rows above the foot
MIDDLE_RAIL = -12
RINGS = ((6, -19), (16, -19))       # (along, row): the middle panel's rings


def arch(x):
    """The leaves' top at x across the opening: lowest at the pillars, highest where they meet."""
    return FOOT - 29 - round(7 * math.sin(math.pi * (x - LEFT) / (RIGHT - LEFT)))


def leaf_pixels(plain=False):
    """One leaf flat, as the left one: {(along, y): colour}, along 0 at the hinge.

    plain leaves out the rings and the short bars, which only clutter a leaf seen at a slant."""
    px = {}

    def put(u, y, colour):
        px[(u, y)] = colour

    for u in range(LEAF):
        top = arch(LEFT + u)
        if u in (0, 1, LEAF - 2, LEAF - 1):              # the stiles, lit on their left
            for y in range(top, FOOT + 1):
                put(u, y, LIGHT if u in (0, LEAF - 2) else DARK)
            continue
        put(u, top, DARK)                                # the arched top bar
        put(u, top + 1, IRON)
        for rail in (TOP_RAIL, MIDDLE_RAIL):
            put(u, FOOT + rail, IRON)
            put(u, FOOT + rail - 1, shade(LIGHT, 0.9))
        put(u, FOOT - 1, IRON)                           # the bottom rail
        put(u, FOOT, DARK)
        if u in BARS:
            for y in range(top, FOOT - 1):
                if (u, y) not in px or y in (FOOT + TOP_RAIL, FOOT + MIDDLE_RAIL):
                    put(u, y, IRON if y not in (FOOT + TOP_RAIL, FOOT + MIDDLE_RAIL) else LIGHT)
            # a spear point over the arch
            put(u, top - 1, LIGHT)
            put(u - 1, top - 1, DARK)
            put(u + 1, top - 1, DARK)
            put(u, top - 2, DARK)
        elif not plain and u % 3 == 0:  # short dog bars low down, between the bars
            for y in range(FOOT + MIDDLE_RAIL + 1, FOOT - 1):
                put(u, y, DARK)
    for cu, cy in () if plain else RINGS:                # rings in the middle panel
        for a in range(0, 360, 15):
            u = round(cu + 2.6 * math.cos(math.radians(a)))
            y = round(FOOT + cy + 2.6 * math.sin(math.radians(a)))
            put(u, y, LIGHT if 120 < a < 300 else IRON)
    for y in (FOOT - 24, FOOT - 6):                      # hinge straps
        for u in range(4):
            put(u, y, DARK if u else LIGHT)
    put(LEAF - 3, FOOT - 14, LIGHT)                      # the latch, a ring on the meeting stile
    put(LEAF - 3, FOOT - 13, RUST)
    for u in (2, 9, 15):                                 # a little rust where the rails rest
        put(u, FOOT - 1, RUST)
    return px


def place_leaf(surface, px, hinge, direction, angle, swing):
    """Draw a leaf with its hinge at x `hinge`, running `direction` (+1 right, -1 left) when shut.

    Open, it is turned `angle` degrees about the hinge; `swing` +1 brings its far edge down the
    picture (towards the viewer), -1 up it. The farther columns are drawn first."""
    cos, sin = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    columns = sorted({u for u, _ in px})
    if swing < 0:
        columns.reverse()                                # the hinge side is the nearer one
    for u in columns:
        x = hinge + direction * round(u * cos)
        dy = swing * round(u * sin)
        for (cu, y), colour in px.items():
            if cu == u and 0 <= x < SIZE[0] and 0 <= y + dy < SIZE[1]:
                surface.set_at((x, y + dy), (*colour, 255))


def ground_shadow(surface):
    for x in range(LEFT, RIGHT + 1):
        for i, alpha in enumerate((70, 40)):
            surface.set_at((x, FOOT + 1 + i), (20, 24, 12, alpha))


def paint(state):
    """'closed', 'open_down' or 'open_up'."""
    surface = pygame.Surface(SIZE, pygame.SRCALPHA)
    px = leaf_pixels(plain=state != 'closed')
    if state == 'closed':
        ground_shadow(surface)
        place_leaf(surface, px, LEFT, +1, 0, 0)
        place_leaf(surface, px, RIGHT, -1, 0, 0)
    else:
        swing = 1 if state == 'open_down' else -1
        place_leaf(surface, px, LEFT, +1, OPEN_ANGLE, swing)
        place_leaf(surface, px, RIGHT, -1, OPEN_ANGLE, swing)
    return surface


STATES = ('closed', 'open_down', 'open_up')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--preview', help='write the three pictures side by side, enlarged, to this PNG')
    parser.add_argument('--write', action='store_true', help=f'save them into {GATES_DIR}')
    args = parser.parse_args(argv)
    pygame.init()
    pygame.display.set_mode((1, 1))
    pictures = {state: paint(state) for state in STATES}
    if args.preview:
        k = 6
        out = pygame.Surface((len(STATES) * (SIZE[0] + 8) * k, SIZE[1] * k))
        out.fill((96, 140, 70))
        for i, state in enumerate(STATES):
            out.blit(pygame.transform.scale(pictures[state], (SIZE[0] * k, SIZE[1] * k)),
                     (i * (SIZE[0] + 8) * k, 0))
        pygame.image.save(out, args.preview)
        print(f'Preview: {args.preview}')
    if args.write:
        GATES_DIR.mkdir(parents=True, exist_ok=True)
        for state, picture in pictures.items():
            path = GATES_DIR / f'{NAME}_{state}.png'
            pygame.image.save(picture, str(path))
            print(f'Saved {path.name}')
    if not (args.preview or args.write):
        sys.exit('Nothing to do: --preview PNG and/or --write')


if __name__ == '__main__':
    main()
