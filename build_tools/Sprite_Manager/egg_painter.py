"""Paints the good Eggs by code, pixel by pixel, in the style of the other goods' pictures.

The goods' paintings are pixel art on a grid of about 32 pixels, blown up
without smoothing, with black outlines and three or four flat tones lit from the
upper left (bread_full.jpeg, tallow_full.jpeg). This one is three eggs, a white
one and two brown ones, in a small wicker basket with a little straw, on a grid
of GRID pixels; each egg and the basket outlined on its own, so they read where
they overlap.

    python build_tools/Sprite_Manager/egg_painter.py --preview out.png
    python build_tools/Sprite_Manager/egg_painter.py --write

--write makes, through the Sprite Manager's own goods_sheets.pictures_of (as
accepting an answer in its goods area does): assets/pictures/eggs_full.jpeg (the
painting), eggs_icon.png (the cut-out), eggs_30.png (the 30px icon) and
contracts/eggs.png (the licence's picture, the good toned sepia). The output is
the same every run.
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PICTURES = ROOT / "assets" / "pictures"

GRID = (30, 25)          # the pixel art's own size
PIXEL = 28               # each of its pixels this many screen pixels in the figure (about the licences' size)

Colour = Tuple[int, int, int]
OUTLINE: Colour = (24, 18, 14)

#: (highlight, light, base, shade) of each egg
WHITE_EGG = ((255, 253, 244), (246, 238, 220), (230, 216, 188), (190, 170, 138))
BROWN_EGG = ((240, 200, 150), (218, 166, 112), (194, 136, 84), (148, 96, 56))
PALE_BROWN_EGG = ((246, 216, 176), (230, 190, 142), (210, 164, 114), (166, 120, 80))
#: The basket's wicker: lit, base, dark, the gaps of the weave
WICKER = ((190, 136, 74), (156, 104, 52), (118, 76, 36), (86, 54, 26))
STRAW = ((240, 212, 112), (214, 176, 72))

#: (centre x, centre y, half width, half height, palette), back to front
EGGS = ((15.0, 7.3, 5.3, 6.5, BROWN_EGG),
        (8.6, 10.6, 4.9, 6.5, WHITE_EGG),
        (21.4, 10.9, 4.9, 6.5, PALE_BROWN_EGG))
#: The basket: its rim's top row and bottom row, the rim's ends, the bottom's ends
RIM_TOP, RIM_BOTTOM, BOTTOM = 15, 17, 24
RIM_X = (2, 27)
#: How much narrower an egg's top end is than its bottom
TAPER = 0.1
BASE_X = (6, 23)


def _egg_shape(cx: float, cy: float, rx: float, ry: float, x: int, y: int) -> Optional[Tuple[float, float]]:
    """(nx, ny), where pixel (x, y) is on the egg from -1 to 1, or None if off it. An egg is narrower at the
    top: its half width shrinks by TAPER towards its top end."""
    px, py = x + 0.5, y + 0.5
    ny = (py - cy) / ry
    if abs(ny) > 1:
        return None
    width = rx * (1.0 - TAPER * max(0.0, -ny))
    nx = (px - cx) / width
    return (nx, ny) if nx * nx + ny * ny <= 1.0 else None


def _paint_egg(grid: Dict[Tuple[int, int], Colour], cx, cy, rx, ry, palette) -> None:
    highlight, light, base, shade = palette
    shape = {}
    for y in range(GRID[1]):
        for x in range(GRID[0]):
            at = _egg_shape(cx, cy, rx, ry, x, y)
            if at:
                shape[(x, y)] = at
    for (x, y), (nx, ny) in shape.items():
        edge = any((x + dx, y + dy) not in shape for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
        if edge:
            grid[(x, y)] = OUTLINE
            continue
        lit = -0.65 * nx - 0.75 * ny          # light from the upper left
        if -0.7 < nx < -0.05 and -0.8 < ny < -0.25 and nx + ny > -1.25:
            colour = highlight
        elif lit > 0.35:
            colour = light
        elif lit > -0.45:
            colour = base
        else:
            colour = shade
        grid[(x, y)] = colour


def _basket_span(y: int) -> Optional[Tuple[int, int]]:
    """The basket's columns on row y, or None."""
    if y < RIM_TOP or y > BOTTOM:
        return None
    if y <= RIM_BOTTOM:
        inset = 1 if y == RIM_TOP else 0
        return RIM_X[0] + inset, RIM_X[1] - inset
    share = (y - RIM_BOTTOM) / (BOTTOM - RIM_BOTTOM)
    left = round(RIM_X[0] + 1 + (BASE_X[0] - RIM_X[0] - 1) * share ** 1.4)
    right = round(RIM_X[1] - 1 - (RIM_X[1] - 1 - BASE_X[1]) * share ** 1.4)
    if y == BOTTOM:
        left, right = left + 1, right - 1
    return left, right


def _paint_basket(grid: Dict[Tuple[int, int], Colour]) -> None:
    lit, base, dark, gap = WICKER
    cells = set()
    for y in range(GRID[1]):
        span = _basket_span(y)
        if span:
            cells.update((x, y) for x in range(span[0], span[1] + 1))
    for x, y in cells:
        edge = any((x + dx, y + dy) not in cells for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
        if edge:
            grid[(x, y)] = OUTLINE
        elif y <= RIM_BOTTOM:
            # The rim: a twisted rope of wicker, lit on its upper row
            grid[(x, y)] = lit if (y == RIM_TOP + 1 and (x + y) % 3 != 0) else base if (x + y) % 3 else dark
        else:
            # The body: rows of weave, each strand passing over two stakes and under one
            row = (y - RIM_BOTTOM - 1) % 3
            if row == 2:
                colour = gap if x % 4 == 0 else dark
            else:
                over = ((x + (y // 3) * 2) // 2) % 2 == 0
                colour = (lit if row == 0 else base) if over else (base if row == 0 else dark)
            # Shade towards the right and the bottom: it is round
            if x >= RIM_X[1] - 4 - (y - RIM_BOTTOM) // 3 and colour in (lit, base):
                colour = base if colour == lit else dark
            grid[(x, y)] = colour
    # The rim's underside casts a line of shadow on the body
    for x, y in list(cells):
        if y == RIM_BOTTOM + 1 and grid[(x, y)] != OUTLINE:
            grid[(x, y)] = dark


def _paint_straw(grid: Dict[Tuple[int, int], Colour]) -> None:
    """A few stalks of straw poking up out of the basket between and beside the eggs."""
    light, dark = STRAW
    for x, y, colour in ((3, 14, dark), (4, 14, light), (4, 13, light), (14, 14, dark), (15, 14, light),
                         (25, 14, light), (26, 14, dark), (26, 13, light)):
        grid[(x, y)] = colour


def paint() -> pygame.Surface:
    """The pixel art at GRID, see-through around it."""
    grid: Dict[Tuple[int, int], Colour] = {}
    for cx, cy, rx, ry, palette in EGGS:
        _paint_egg(grid, cx, cy, rx, ry, palette)
    _paint_straw(grid)
    _paint_basket(grid)
    art = pygame.Surface(GRID, pygame.SRCALPHA)
    art.fill((0, 0, 0, 0))
    for (x, y), colour in grid.items():
        art.set_at((x, y), (*colour, 255))
    return art


def figure() -> pygame.Surface:
    """The pixel art blown up without smoothing, as the other goods' paintings are drawn."""
    art = paint()
    return pygame.transform.scale(art, (GRID[0] * PIXEL, GRID[1] * PIXEL))


def _pictures(fig: pygame.Surface) -> Dict[str, pygame.Surface]:
    sys.path.insert(0, str(HERE))
    from goods_sheets import pictures_of        # the Sprite Manager's, as accepting an answer makes them
    return pictures_of(fig)


def _paths() -> Dict[str, Path]:
    return {"painting": PICTURES / "eggs_full.jpeg", "icon": PICTURES / "eggs_icon.png",
            "small": PICTURES / "eggs_30.png", "licence": PICTURES / "contracts" / "eggs.png"}


def preview(out: str) -> None:
    pictures = _pictures(figure())
    big = pygame.transform.scale(paint(), (GRID[0] * 10, GRID[1] * 10))
    painting = pygame.transform.smoothscale(pictures["painting"], (300, 300))
    licence = pictures["licence"]
    licence = pygame.transform.smoothscale(licence, (300, round(300 * licence.get_height() / licence.get_width())))
    sheet = pygame.Surface((big.get_width() + 640, max(big.get_height(), 300) + 80))
    sheet.fill((230, 215, 180))
    sheet.blit(big, (0, 0))
    sheet.blit(painting, (big.get_width() + 20, 0))
    sheet.blit(licence, (big.get_width() + 330, 0))
    small, icon = pictures["small"], pictures["icon"]
    sheet.blit(small, (10, sheet.get_height() - 40))
    sheet.blit(pygame.transform.scale(small, (60, 60)), (60, sheet.get_height() - 70))
    sheet.blit(icon, (140, sheet.get_height() - icon.get_height() - 5))
    pygame.image.save(sheet, out)


def write() -> List[str]:
    written = []
    for kind, surface in _pictures(figure()).items():
        path = _paths()[kind]
        pygame.image.save(surface, str(path))
        written.append(str(path.relative_to(ROOT)))
    return written


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--preview", metavar="PNG", help="write a sheet of the pictures to look at")
    parser.add_argument("--write", action="store_true", help="write the game's pictures of Eggs")
    args = parser.parse_args(argv)
    pygame.init()
    pygame.display.set_mode((1, 1))
    if args.preview:
        preview(args.preview)
    if args.write:
        print("\n".join(write()))
    if not (args.preview or args.write):
        parser.print_help()


if __name__ == "__main__":
    main()
