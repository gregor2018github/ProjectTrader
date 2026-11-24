"""Previews the chicken's parts and colours, enlarged, for comparing them.

The chicken is painted by code pixel by pixel from modular parts (a head, the
body, a tail, the legs), each a small grid of characters, one per pixel; the
parts, colours and their odds live in the game, in
src/models/figurines/animals/chicken_look.py, which this imports. Add or change
a head, tail or colour there.

    python build_tools/Sprite_Manager/chicken_painter.py --preview out.png

draws every head on the body (`--parts tails` the tails, `--parts colours` the
colour variants, `--parts frames` the default chicken's walk and pecking, `--parts ages`
the default chicken growing up, from a pale chick).
"""

import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.models.figurines.animals.chicken_look import (  # noqa: E402,F401
    COLOUR, COLOUR_ODDS, COLOURS, FRAME_H, FRAME_W, HEAD, HEADS, PALETTE, TAIL, TAILS, Part, compose, frames,
    mirrored, random_chicken, standing)


def preview(path, what="heads", scale=14, per_row=6):
    """Every head (on the chosen tail), every tail (under the chosen head) or
    every colour, enlarged and labelled."""
    pygame.init()
    if what == "ages":
        shown = [(f"youth {youth:.2f}", standing(youth=youth)) for youth in (1.0, 0.75, 0.5, 0.25, 0.0)]
    elif what == "frames":
        poses = frames()
        shown = [("stand", poses["stand"])] + [(f"walk {i + 1}", f) for i, f in enumerate(poses["walk"])]
        shown += [(f"peck {n}", f) for n, f in zip(("down", "up", "step"), poses["peck"])]
    else:
        shown = [(name, standing(**{what[:-1]: name}))
                 for name in {"heads": HEADS, "tails": TAILS, "colours": COLOURS}[what]]
    names = [name for name, _ in shown]
    cell_w, cell = FRAME_W * scale, FRAME_H * scale
    columns = min(per_row, len(names))
    rows = (len(names) + per_row - 1) // per_row
    sheet = pygame.Surface((columns * (cell_w + scale) + scale,
                            rows * (cell + 2 * scale) + scale))
    sheet.fill((150, 190, 110))
    font = pygame.font.SysFont(None, 40)
    for i, (name, frame) in enumerate(shown):
        x = scale + (i % per_row) * (cell_w + scale)
        y = scale + (i // per_row) * (cell + 2 * scale)
        sheet.blit(pygame.transform.scale(frame, (cell_w, cell)), (x, y + scale))
        sheet.blit(font.render(name, True, (0, 0, 0)), (x + 4, y))
    pygame.image.save(sheet, path)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--preview", help="write the parts compared, enlarged, to this PNG")
    parser.add_argument("--parts", choices=("heads", "tails", "colours", "frames", "ages"), default="heads",
                        help="which parts --preview compares")
    args = parser.parse_args()
    if args.preview:
        preview(args.preview, args.parts)
        print(f"wrote {args.preview}")


if __name__ == "__main__":
    main()
