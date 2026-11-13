"""The small pictures of the tavern dishes the Gourmet Collection shows, made once and kept as files.

Every dish picture, `assets/pictures/dish_<key>.png`, is large (1217 by 864), far too large
to load and shrink for a page of cards while it is open. So each has two small copies in
`PREVIEWS_PATH`, made ahead and loaded as they are:

- `<key>.png`: the picture shrunk to fit `PREVIEW_SIZE`, shown once the dish was tasted;
- `<key>_silhouette.png`: only the dish's outline as one flat grey shape (`SILHOUETTE`) on
  nothing, shown until then, so a plate is a plate and a cup a cup, but what is on it
  cannot be told.

They are made by `make_previews`: by the Sprite Manager whenever it saves a dish's
picture (`food_sheets.save_picture`), and for all dishes at once by
`python build_tools/Dish_Previews/make_dish_previews.py` (run it after changing anything
here). The game never makes them; a dish whose preview is missing shows a drawn outline
of a plate, bowl or cup instead.

The pictures have a painted wall and table behind the dish, no see-through background, so
the outline is found from the picture: the colours along its edges are the background's,
everything reached from the edges through such colours is background, and the rest is
the dish (`dish_mask`). The dish's own outline is thickened before the background is let
in and thinned after (`SILHOUETTE_CLOSE_PX`), so it does not leak in where food is
coloured like the table, and thin bits (crumbs by a bowl) are trimmed off
(`SILHOUETTE_TRIM_PX`). It is worked out at twice the size, its edge rounded off and made
soft (`SILHOUETTE_ROUND`, `SILHOUETTE_FEATHER`).
"""

import os
import re
from typing import Dict, List, Optional, Tuple

import pygame

from ..config.constants import PICTURES_PATH

#: Where the small copies are kept, and how large they are at most
PREVIEWS_PATH = os.path.join(PICTURES_PATH, "dish_previews")
PREVIEW_SIZE: Tuple[int, int] = (124, 88)

#: The outline of a dish not tasted yet: its colour
SILHOUETTE = (128, 118, 104)
#: Finding the dish in its picture: how near a background colour a pixel must be (each channel),
#: how far the dish's own outline is thickened while the background is let in, and how thin
#: a bit sticking out is trimmed off; and the share of the largest shape a lone bit must have
SILHOUETTE_TOLERANCE = 20
SILHOUETTE_CLOSE_PX = 3
SILHOUETTE_TRIM_PX = 2
SILHOUETTE_KEEP_SHARE = 0.03
#: Smoothing the outline: how much its ragged edge is rounded off, and how soft its edge is
#: (each the times a picture is made smaller to blur it; more is smoother)
SILHOUETTE_ROUND = 4
SILHOUETTE_FEATHER = 6

_loaded: Dict[Tuple[str, bool], Optional[pygame.Surface]] = {}   # (key, tasted) -> the preview
_missing_told: set = set()


def preview_path(key: str, tasted: bool) -> str:
    """Where a dish's small picture (`tasted`) or its silhouette is kept."""
    return os.path.join(PREVIEWS_PATH, f"{key}.png" if tasted else f"{key}_silhouette.png")


def key_of_picture(picture_path: str) -> str:
    """The dish's key from its picture's file name, dish_<key>.png."""
    name = os.path.splitext(os.path.basename(picture_path))[0]
    return re.sub(r"^dish_", "", name)


# ── Finding the dish's outline ───────────────────────────────────────────────

def _grow(mask: pygame.mask.Mask, radius: int) -> pygame.mask.Mask:
    """The mask with every set pixel spread to a disc of `radius` round it."""
    grown = pygame.mask.Mask(mask.get_size())
    for dx in range(-radius, radius + 1):
        for dy in range(-radius, radius + 1):
            if dx * dx + dy * dy <= radius * radius:
                grown.draw(mask, (dx, dy))
    return grown


def _shrink(mask: pygame.mask.Mask, radius: int) -> pygame.mask.Mask:
    """The mask with `radius` taken off its every edge."""
    outside = mask.copy()
    outside.invert()
    shrunk = _grow(outside, radius)
    shrunk.invert()
    return shrunk


def dish_mask(picture: pygame.Surface) -> pygame.mask.Mask:
    """Where the dish is in its picture, as a solid shape (see the module)."""
    w, h = picture.get_size()
    edge = ([picture.get_at((x, y))[:3] for x in range(0, w, 3) for y in (0, 1, h - 2, h - 1)]
            + [picture.get_at((x, y))[:3] for y in range(0, h, 3) for x in (0, 1, w - 2, w - 1)])
    palette: List[Tuple[int, int, int]] = []
    for colour in edge:
        if all(sum(abs(a - b) for a, b in zip(colour, known)) > 18 for known in palette):
            palette.append(colour)
    tolerance = (SILHOUETTE_TOLERANCE, SILHOUETTE_TOLERANCE, SILHOUETTE_TOLERANCE, 255)
    like_background = pygame.mask.Mask((w, h))
    for colour in palette:
        like_background.draw(pygame.mask.from_threshold(picture, colour, tolerance), (0, 0))
    dish = like_background.copy()
    dish.invert()
    # The background is what the edges reach past the thickened dish; all else is the dish, holes filled
    open_ground = _grow(dish, SILHOUETTE_CLOSE_PX)
    open_ground.invert()
    background = pygame.mask.Mask((w, h))
    for part in open_ground.connected_components():
        if any(r.left == 0 or r.top == 0 or r.right == w or r.bottom == h for r in part.get_bounding_rects()):
            background.draw(part, (0, 0))
    background = _grow(background, SILHOUETTE_CLOSE_PX)   # the thickening taken off again
    shape = background.copy()
    shape.invert()
    # Thin bits trimmed off, and lone bits far smaller than the dish dropped
    shape = _grow(_shrink(shape, SILHOUETTE_TRIM_PX), SILHOUETTE_TRIM_PX)
    parts = shape.connected_components()
    kept = pygame.mask.Mask((w, h))
    if parts:
        largest = max(part.count() for part in parts)
        for part in parts:
            if part.count() >= SILHOUETTE_KEEP_SHARE * largest:
                kept.draw(part, (0, 0))
    return kept


def silhouette(picture: pygame.Surface, size: Tuple[int, int]) -> pygame.Surface:
    """The dish's outline as a flat grey shape, `size` large, with smooth edges.

    The shape is found at twice the size (`dish_mask`), whose edge is ragged; it is rounded
    off by blurring it (made `SILHOUETTE_ROUND` times smaller and large again at four times
    the size) and cutting it back to a sharp shape there, and then given a soft edge
    (blurred again, `SILHOUETTE_FEATHER`, and kept soft as it comes down to `size`).
    """
    w, h = size
    double = pygame.transform.smoothscale(picture, (w * 2, h * 2))
    shape = dish_mask(double).to_surface(setcolor=(255, 255, 255, 255), unsetcolor=(0, 0, 0, 255))
    blurred = pygame.transform.smoothscale(
        pygame.transform.smoothscale(shape, (max(1, w * 2 // SILHOUETTE_ROUND), max(1, h * 2 // SILHOUETTE_ROUND))),
        (w * 4, h * 4))
    rounded = pygame.mask.from_threshold(blurred, (255, 255, 255), (128, 128, 128, 255))
    sharp = rounded.to_surface(setcolor=(255, 255, 255, 255), unsetcolor=(255, 255, 255, 0))
    soft = pygame.transform.smoothscale(
        pygame.transform.smoothscale(sharp, (max(1, w * 4 // SILHOUETTE_FEATHER), max(1, h * 4 // SILHOUETTE_FEATHER))),
        size)
    soft.fill(SILHOUETTE, special_flags=pygame.BLEND_RGB_MIN)   # white to the grey, the soft edge kept
    return soft


# ── Making and loading the files ─────────────────────────────────────────────

def fitted_size(picture_size: Tuple[int, int], box: Tuple[int, int] = PREVIEW_SIZE) -> Tuple[int, int]:
    """The size a picture is shrunk to, to fit the box keeping its proportions."""
    scale = min(box[0] / picture_size[0], box[1] / picture_size[1])
    return max(1, round(picture_size[0] * scale)), max(1, round(picture_size[1] * scale))


def make_previews(picture_path: str) -> Tuple[str, str]:
    """Write a dish picture's small copy and its silhouette into `PREVIEWS_PATH`; their paths.

    Raises:
        pygame.error, OSError: If the picture cannot be read or the files not written.
    """
    big = pygame.image.load(picture_path)
    if pygame.display.get_surface() is not None:
        big = big.convert()
    size = fitted_size(big.get_size())
    key = key_of_picture(picture_path)
    os.makedirs(PREVIEWS_PATH, exist_ok=True)
    small, shape = preview_path(key, True), preview_path(key, False)
    pygame.image.save(pygame.transform.smoothscale(big, size), small)
    pygame.image.save(silhouette(big, size), shape)
    for tasted in (True, False):
        _loaded.pop((key, tasted), None)
    return small, shape


def load_preview(key: str, tasted: bool) -> Optional[pygame.Surface]:
    """A dish's small picture or silhouette, read once; None (and a word on the console) if it is not made."""
    cached_key = (key, tasted)
    if cached_key not in _loaded:
        path = preview_path(key, tasted)
        picture = None
        if os.path.exists(path):
            try:
                picture = pygame.image.load(path)
                if pygame.display.get_surface() is not None:
                    picture = picture.convert_alpha()
            except pygame.error as error:
                print(f"Warning: could not read {path}: {error}")
        elif os.path.exists(os.path.join(PICTURES_PATH, f"dish_{key}.png")) and key not in _missing_told:
            _missing_told.add(key)
            print(f"Warning: no preview of dish_{key}.png; run build_tools/Dish_Previews/make_dish_previews.py")
        _loaded[cached_key] = picture
    return _loaded[cached_key]
