"""Make the small pictures and grey silhouettes of the tavern dishes for the Gourmet Collection.

For every assets/pictures/dish_<key>.png it writes assets/pictures/dish_previews/<key>.png
(the picture shrunk to the collection's card) and <key>_silhouette.png (only the dish's
outline, in grey), with the game's own code (src/ui/dish_previews.py). The game only loads
them; the Sprite Manager makes a dish's pair whenever it saves its picture. Run this after
changing how they are made, or for pictures added by hand:

    python build_tools/Dish_Previews/make_dish_previews.py            # all of them
    python build_tools/Dish_Previews/make_dish_previews.py --missing  # only those not made yet
    python build_tools/Dish_Previews/make_dish_previews.py roast_pigeons ale
"""

import argparse
import glob
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame  # noqa: E402

from src.config.constants import PICTURES_PATH  # noqa: E402
from src.ui.dish_previews import key_of_picture, make_previews, preview_path  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("keys", nargs="*", help="only these dishes (their keys, as in dish_<key>.png)")
    parser.add_argument("--missing", action="store_true", help="only dishes whose previews are not made yet")
    args = parser.parse_args()

    pygame.init()
    pygame.display.set_mode((1, 1))
    pictures = sorted(glob.glob(os.path.join(PICTURES_PATH, "dish_*.png")))
    if args.keys:
        pictures = [p for p in pictures if key_of_picture(p) in args.keys]
    if args.missing:
        pictures = [p for p in pictures
                    if not all(os.path.exists(preview_path(key_of_picture(p), tasted)) for tasted in (True, False))]
    started = time.perf_counter()
    failed = 0
    for picture in pictures:
        try:
            make_previews(picture)
        except (pygame.error, OSError) as error:
            failed += 1
            print(f"Could not make the previews of {os.path.basename(picture)}: {error}")
    print(f"Made the previews of {len(pictures) - failed} dishes in {time.perf_counter() - started:.1f} s"
          + (f", {failed} failed" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
