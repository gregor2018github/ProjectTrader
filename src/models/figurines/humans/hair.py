"""The player's hair colour: found in his sprites by its colour and painted over.

The player's artwork has brown hair. ``hair_mask`` finds it in any of his frames
by colour alone, all in pygame's C code (a few boxes along the browns' line of
colour, kept to the upper half of the figure and to large patches, which leaves
out the boots, belt and vest), and ``recolour_hair`` paints it in another colour
keeping each pixel's lightness, so the shading and highlights stay. The colours
offered are ``HAIR_COLOURS``; ``DEFAULT_HAIR`` is the artwork's own and changes
nothing.
"""

import math
from typing import Dict, List, Optional, Tuple

import pygame

#: The colours offered on the new game page: key, name, and the colour the
#: artwork's mid brown becomes (None: the artwork as it is)
HAIR_COLOURS: List[Tuple[str, str, Optional[Tuple[int, int, int]]]] = [
    ("black", "Black", (38, 33, 34)),
    ("dark_brown", "Dark Brown", (62, 42, 30)),
    ("brown", "Brown", None),
    ("chestnut", "Chestnut", (120, 62, 34)),
    ("auburn", "Auburn", (140, 55, 32)),
    ("red", "Red", (186, 82, 36)),
    ("dark_blond", "Dark Blond", (150, 116, 66)),
    ("blond", "Blond", (212, 176, 104)),
    ("flaxen", "Flaxen", (226, 208, 156)),
    ("grey", "Grey", (150, 146, 140)),
]
DEFAULT_HAIR = "brown"

#: What each colour shows as on its swatch: the artwork's mid brown for the default
ARTWORK_HAIR = (99, 72, 46)
SWATCHES: Dict[str, Tuple[int, int, int]] = {key: colour or ARTWORK_HAIR for key, _name, colour in HAIR_COLOURS}
HAIR_NAMES: Dict[str, str] = {key: name for key, name, _colour in HAIR_COLOURS}

#: The browns of the hair lie along G = 0.72 R, B = 0.46 R; a box round each step
_LINE_G, _LINE_B = 0.72, 0.46
_LINE_REDS = range(48, 170, 10)
_BOX = (7, 6, 6, 255)
#: Hair is only looked for in this upper share of the figure's height
_HEAD_SHARE = 0.5
#: Smaller patches of brown are a belt, a bag or a boot's edge
_MIN_PATCH = 200
#: Looser boxes for the specks inside the hair and the pixels along its edge
_LOOSE_REDS = range(30, 186, 8)
_LOOSE_BOX = (12, 11, 11, 255)
#: Holes up to about twice this wide are filled
_CLOSE_PX = 2
#: How far the hair may grow into loose browns along its edge, a pixel a step
_GROW_STEPS = 2


def _lightness(colour: Tuple[int, int, int]) -> float:
    r, g, b = colour
    return 0.299 * r + 0.587 * g + 0.114 * b


_ARTWORK_LIGHTNESS = _lightness(ARTWORK_HAIR)


def hair_key(key: Optional[str]) -> str:
    """*key* if it is one of HAIR_COLOURS, else the default (an older save, a typo)."""
    return key if key in SWATCHES else DEFAULT_HAIR


def hair_mask(sprite: pygame.Surface) -> pygame.mask.Mask:
    """The hair's pixels in one of the player's frames."""
    w, h = sprite.get_size()
    found = pygame.mask.Mask((w, h))
    if w == 0 or h == 0:
        return found
    for red in _LINE_REDS:
        colour = (red, round(red * _LINE_G), round(red * _LINE_B))
        found.draw(pygame.mask.from_threshold(sprite, colour, _BOX), (0, 0))

    drawn = sprite.get_bounding_rect()
    head = pygame.mask.Mask((w, h))
    head_bottom = drawn.top + int(drawn.height * _HEAD_SHARE)
    if head_bottom > 0:
        head.draw(pygame.mask.Mask((w, head_bottom), fill=True), (0, 0))
    found = found.overlap_mask(head, (0, 0))
    found = found.overlap_mask(pygame.mask.from_surface(sprite, 127), (0, 0))

    kept = pygame.mask.Mask((w, h))
    for patch in found.connected_components(minimum=_MIN_PATCH):
        kept.draw(patch, (0, 0))

    # Specks and seams the boxes missed: browns a little further off the line,
    # taken where they lie inside the hair or along its edge
    loose = pygame.mask.Mask((w, h))
    for red in _LOOSE_REDS:
        colour = (red, round(red * _LINE_G), round(red * _LINE_B))
        loose.draw(pygame.mask.from_threshold(sprite, colour, _LOOSE_BOX), (0, 0))
    loose = loose.overlap_mask(head, (0, 0))
    closed = _erode(_dilate(kept, _CLOSE_PX), _CLOSE_PX)
    kept.draw(closed.overlap_mask(loose, (0, 0)), (0, 0))
    for _ in range(_GROW_STEPS):
        kept.draw(_dilate(kept, 1).overlap_mask(loose, (0, 0)), (0, 0))
    return kept


def _dilate(mask: pygame.mask.Mask, px: int) -> pygame.mask.Mask:
    """*mask* grown by *px* pixels each way (a square), at its own size."""
    grown = mask.convolve(pygame.mask.Mask((2 * px + 1, 2 * px + 1), fill=True))
    out = pygame.mask.Mask(mask.get_size())
    out.draw(grown, (-px, -px))
    return out


def _erode(mask: pygame.mask.Mask, px: int) -> pygame.mask.Mask:
    """*mask* shrunk by *px* pixels each way: the grown outside, taken off."""
    outside = mask.copy()
    outside.invert()
    w, h = mask.get_size()
    # Beyond the edges counts as outside, so the hair does not stick to them
    framed = pygame.mask.Mask((w + 2, h + 2), fill=True)
    framed.erase(mask, (1, 1))
    grown = _dilate(framed, px)
    out = pygame.mask.Mask((w, h))
    out.draw(grown, (-1, -1))
    out.invert()
    return out


def recolour_hair(sprite: pygame.Surface, key: Optional[str]) -> pygame.Surface:
    """A copy of *sprite* with its hair in the colour *key*; *sprite* itself for the default."""
    colour = SWATCHES.get(hair_key(key))
    if colour is None or colour == ARTWORK_HAIR:
        return sprite
    mask = hair_mask(sprite)
    if mask.count() == 0:
        return sprite

    # Each hair pixel becomes colour x (its lightness / the mid brown's): in steps
    # a multiply can take (it cannot go past 1), added up again
    hair = mask.to_surface(setsurface=sprite.convert_alpha(), unsetcolor=(0, 0, 0, 0))
    grey = pygame.transform.grayscale(hair)
    factors = [c / _ARTWORK_LIGHTNESS for c in colour]
    steps = max(1, math.ceil(max(factors)))
    tint = tuple(min(255, round(f / steps * 255)) for f in factors)
    grey.fill(tint, special_flags=pygame.BLEND_RGB_MULT)
    painted = grey.copy()
    for _ in range(steps - 1):
        painted.blit(grey, (0, 0), special_flags=pygame.BLEND_RGB_ADD)

    result = sprite.copy()
    result.blit(painted, (0, 0))
    return result
