"""The near railing of a bridge sprite, cut out as its own sprite for the game to draw over walkers.

The game lays a bridge (Bridge_<n>.png) under everyone walking over it and
draws Bridge_<n>_front.png, the same size and holding nothing but the
railing on the near side, over them again (src/models/bridge.py). Which
pixels are that railing is not something to tell from the picture, so the
model is asked: it gets the bridge on white and paints everything that is
not the near railing magenta. Its answer is only used as a mask; the
railing's pixels are copied from the bridge itself, so they match it exactly.

    python bridge_front.py prepare Bridge_01.png
        writes build_tools/output/buildings/bridge_front/Bridge_01_send.png
        and prints the prompt to send with it
    python bridge_front.py cut Bridge_01.png <the answer image>
        writes Bridge_01_front.png next to Bridge_01.png

Names without a folder are looked up in assets/map_sprites/houses/.
"""

import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
import pygame

from sprite_library import MAP_SPRITES
from theme import OUTPUT_DIR

SEND_DIR = OUTPUT_DIR / 'buildings' / 'bridge_front'
SEND_TARGET = 1024     # the bridge is blown up by whole pixels to about this width
SEND_MARGIN = 0.1      # of the sent picture's width left white around the bridge
MAGENTA = (255, 0, 255)
WHITE = (255, 255, 255)

PROMPT = """\
The attached picture is a pixel-art sprite of a wooden bridge from my game, seen from a high three-quarter angle, on a plain white background. It has a railing along its far side (higher up in the picture, behind the walkway) and a railing along its near side (lower down, in front of the walkway).

Paint everything except the near railing in flat pure magenta (#FF00FF): the walkway, the far railing, the beams and piles underneath, all of it. Where the walkway shows between the posts and bars of the near railing, that is magenta too.

Leave the near railing - its posts and its bars - exactly as it is, pixel for pixel: same position, same size, same colours. Leave the white background white. Do not move, redraw, crop or resize anything. Output the full picture at the same size.
"""


def _distance(a, b):
    return sum((p - q) ** 2 for p, q in zip(a, b))


def _sprite_path(name):
    path = Path(name)
    return path if path.parent != Path('.') or path.exists() else MAP_SPRITES / 'houses' / name


def _layout(bridge):
    """(factor, margin) of the sent picture: the bridge blown up by whole pixels, white around it."""
    factor = max(1, SEND_TARGET // bridge.get_width())
    margin = round(bridge.get_width() * factor * SEND_MARGIN)
    return factor, margin


def prepare(bridge_path):
    """Write the picture to send and print the prompt."""
    bridge = pygame.image.load(str(bridge_path))
    factor, margin = _layout(bridge)
    big = pygame.transform.scale(bridge, (bridge.get_width() * factor, bridge.get_height() * factor))
    picture = pygame.Surface((big.get_width() + 2 * margin, big.get_height() + 2 * margin))
    picture.fill((255, 255, 255))
    picture.blit(big, (margin, margin))
    SEND_DIR.mkdir(parents=True, exist_ok=True)
    out = SEND_DIR / f'{bridge_path.stem}_send.png'
    pygame.image.save(picture, str(out))
    (SEND_DIR / 'prompt.txt').write_text(PROMPT, encoding='utf-8')
    print(f'Send {out}\nwith this prompt (also in {SEND_DIR / "prompt.txt"}):\n\n{PROMPT}')


def cut(bridge_path, answer_path):
    """Write <bridge>_front.png: the bridge's pixels wherever the answer kept the near railing."""
    bridge = pygame.image.load(str(bridge_path))
    answer = pygame.image.load(str(answer_path))
    factor, margin = _layout(bridge)
    sent_size = (bridge.get_width() * factor + 2 * margin, bridge.get_height() * factor + 2 * margin)
    # The model may answer at another size; the layout is the same, so scale back and cut the margin
    plain = pygame.Surface(answer.get_size(), 0, 32)   # smoothscale wants 24 or 32 bits; a PNG may be paletted
    plain.blit(answer, (0, 0))
    answer = pygame.transform.smoothscale(plain, sent_size)

    front = pygame.Surface(bridge.get_size(), pygame.SRCALPHA)
    kept = 0
    half = factor // 2
    for y in range(bridge.get_height()):
        for x in range(bridge.get_width()):
            pixel = bridge.get_at((x, y))
            if pixel.a == 0:
                continue
            # The middle of the blown-up pixel, away from edges the answer may have softened
            seen = answer.get_at((margin + x * factor + half, margin + y * factor + half))[:3]
            # Kept where the answer still looks like the bridge here rather than magenta or paper
            own = _distance(seen, pixel[:3])
            if own >= _distance(seen, MAGENTA) or own >= _distance(seen, WHITE):
                continue
            front.set_at((x, y), pixel)
            kept += 1
    out = bridge_path.with_name(f'{bridge_path.stem}_front.png')
    pygame.image.save(front, str(out))
    share = kept / max(1, pygame.mask.from_surface(bridge, 0).count())
    print(f'Wrote {out}: {kept} pixels, {share:.0%} of the bridge')
    if share > 0.5:
        print('That is most of the bridge - the answer probably left more than the near railing.')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('prepare', help='write the picture to send and print the prompt')
    p.add_argument('bridge')
    c = sub.add_parser('cut', help="cut the near railing out along the model's answer")
    c.add_argument('bridge')
    c.add_argument('answer')
    args = parser.parse_args()

    pygame.init()
    bridge = _sprite_path(args.bridge)
    if not bridge.exists():
        sys.exit(f'No such sprite: {bridge}')
    if args.command == 'prepare':
        prepare(bridge)
    else:
        cut(bridge, Path(args.answer))


if __name__ == '__main__':
    main()
