"""Cut the goods' large paintings out of their backgrounds.

The game's 30px good icons blur when drawn larger, so bigger UI (the
warehouse inventory) uses the 1024px paintings in assets/pictures instead.
Those have a plain background (white, cream, dark blue...), which this tool
cuts away once: the background is told by the corners' colours and only what
is joined to a corner goes, loose JPEG specks are dropped, and the figure is
cropped and saved as assets/pictures/<good>_icon.png, ICON_SIZE pixels on its
longer side. Run it again after adding or repainting a good:

    python build_tools/Good_Icons/cut_good_icons.py
"""

import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PICTURES = os.path.join(ROOT, "assets", "pictures")

GOODS = ["Wood", "Stone", "Iron", "Wool", "Hide", "Fish", "Wheat", "Wine",
         "Beer", "Meat", "Linen", "Pottery", "Candle", "Herbs", "Salt"]
SOURCE_FILES = {"Candle": "candles_full.jpg", "Hide": "hides_full.jpeg"}  # the rest are <good>_full.jpeg
ICON_SIZE = 128
BACKGROUND_TOLERANCE = (40, 40, 40, 255)
MIN_PIECE_SHARE = 0.0005     # parts of the painting smaller than this share of it are specks


def cut_out(img: pygame.Surface) -> pygame.Surface:
    """The painting's figure on a transparent background, cropped to it."""
    w, h = img.get_size()
    background = pygame.mask.Mask((w, h))
    for corner in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
        similar = pygame.mask.from_threshold(img, img.get_at(corner), BACKGROUND_TOLERANCE)
        background.draw(similar.connected_component(corner), (0, 0))
    background.invert()

    figure = pygame.mask.Mask((w, h))
    for piece in background.connected_components(minimum=int(w * h * MIN_PIECE_SHARE)):
        figure.draw(piece, (0, 0))
    if figure.count() == 0:
        raise ValueError("nothing left once the background is gone")

    rects = figure.get_bounding_rects()
    return figure.to_surface(setsurface=img, unsetcolor=(0, 0, 0, 0)).subsurface(rects[0].unionall(rects[1:]))


def main() -> int:
    pygame.init()
    pygame.display.set_mode((1, 1))
    failed = 0
    for good in GOODS:
        source = os.path.join(PICTURES, SOURCE_FILES.get(good, f"{good.lower()}_full.jpeg"))
        target = os.path.join(PICTURES, f"{good.lower()}_icon.png")
        try:
            cut = cut_out(pygame.image.load(source).convert_alpha())
        except (pygame.error, FileNotFoundError, ValueError) as error:
            print(f"{good}: skipped ({error})")
            failed += 1
            continue
        scale = ICON_SIZE / max(cut.get_size())
        size = (max(1, round(cut.get_width() * scale)), max(1, round(cut.get_height() * scale)))
        pygame.image.save(pygame.transform.smoothscale(cut, size), target)
        print(f"{good}: {os.path.relpath(target, ROOT)} {size[0]}x{size[1]}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
