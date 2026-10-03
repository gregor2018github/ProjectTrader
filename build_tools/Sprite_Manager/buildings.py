"""The buildings and their decorations, as a sprite_library.Domain.

All of them are single sprites in assets/map_sprites/houses/ - House_<n>,
Market_<n>, Fence_<n>, Deco_<n> - loaded by the "Houses" object layer's
File_name, and live in Houses.png for Tiled. Which kind each is (a
dwelling, a workshop, a stall ...) is in building_catalog.json. A market
stall's closed sprite, Market_<n>_closed.png, belongs to its open one and
is not listed of its own.

A new building's object needs its size and collision box in tiles, which
tiled_properties() works out from the sprite: the tiles it covers, and a box
along its foot as deep as the kind's footprint share of its height (a house
stands on about a third of its picture, a stall on half), narrowed by pixel
margins to where the foot is solid. They are a start, to be fine-tuned in
Tiled like the others.
"""

import math
from pathlib import Path

import pygame

from sprite_library import MAP_SPRITES, TILE, Atlas, Domain, Kind

HOUSES_ATLAS = Atlas('houses', MAP_SPRITES / 'houses' / 'Houses.png', 'Houses', 'Houses.xcf')
HOUSES_DIR = MAP_SPRITES / 'houses'
CLOSED_SUFFIX = '_closed'   # a market stall's night sprite

KINDS = (
    Kind('dwelling', 'Dwellings', 'town house', 'roof', HOUSES_ATLAS, HOUSES_DIR, 'House',
         tiled_class='House_Frontal', footprint=0.3),
    Kind('workshop', 'Workshops, shops and inns', 'workshop or shop', 'roof', HOUSES_ATLAS, HOUSES_DIR,
         'House', tiled_class='House_Frontal', footprint=0.3),
    Kind('public', 'Public buildings', 'public building', 'roof', HOUSES_ATLAS, HOUSES_DIR,
         'House', tiled_class='House_Frontal', footprint=0.3),
    Kind('farm', 'Farm buildings and sheds', 'farm building', 'roof', HOUSES_ATLAS, HOUSES_DIR,
         'House', tiled_class='House_Frontal', footprint=0.25),
    Kind('market_stall', 'Market stalls', 'market stall', 'awning (and of the goods laid out)', HOUSES_ATLAS,
         HOUSES_DIR, 'Market', tiled_class='Market_Frontal', footprint=0.5),
    Kind('wall_fence', 'Walls and fences', 'piece of wall or fence', 'stone or wood', HOUSES_ATLAS,
         HOUSES_DIR, 'Fence', tiled_class='Fence_Frontal', footprint=0.5),
    Kind('decoration', 'Decorations', 'street or yard decoration', 'main material',
         HOUSES_ATLAS, HOUSES_DIR, 'Deco', tiled_class='Deco', footprint=0.5),
)

#: Subcategories the design screen proposes per kind: what stands in and around
#: a medieval market town somewhere in England or western Europe, picked for
#: the look of it.
SUGGESTIONS = {
    'dwelling': ('timber-framed town house', 'jettied town house', 'narrow merchant\'s house', 'thatched cottage',
                 'stone cottage', 'row of town houses', 'half-timbered farmhouse', 'longhouse',
                 'priest\'s house', 'widow\'s cottage', 'corner house'),
    'workshop': ('blacksmith\'s forge', 'bakery', 'brewery', 'tavern', 'inn', 'butcher\'s shop', 'tannery',
                 'weaver\'s workshop', 'cooper\'s workshop', 'carpenter\'s workshop', 'potter\'s workshop',
                 'apothecary', 'cobbler\'s shop', 'chandler\'s shop', 'dyer\'s workshop', 'stonemason\'s yard'),
    'public': ('guildhall', 'chapel', 'monastery', 'almshouse', 'customs house', 'town gate', 'watchtower',
               'gaol', 'bathhouse', 'tithe barn', 'market hall', 'well house'),
    'farm': ('barn', 'granary', 'windmill', 'watermill', 'stable', 'hay shed', 'dovecote', 'pigsty',
             'chicken coop', 'woodshed', 'cart shed', 'smokehouse'),
    'market_stall': ('baker\'s stall', 'cheese stall', 'herb stall', 'cloth stall', 'spice stall',
                     'candle stall', 'fruit and vegetable stall', 'egg and poultry stall', 'salt stall',
                     'leather stall', 'honey stall', 'ale stall'),
    'wall_fence': ('wattle fence', 'picket fence', 'drystone wall', 'town wall', 'wooden palisade',
                   'garden wall', 'field gate', 'stile', 'wall corner'),
    'decoration': ('barrels', 'crates', 'hay bales', 'woodpile', 'hand cart', 'wheelbarrow', 'anvil',
                   'water trough', 'bench', 'signpost', 'lantern post', 'grindstone', 'sacks of grain',
                   'stocks', 'pillory', 'fishing nets', 'baskets', 'beehives', 'scarecrow', 'plough',
                   'market cross', 'well'),
}

PROMPT_TEMPLATE = """\
The attached picture is a split view for my medieval trading game "Merchant's Rise". The left cell shows an existing pixel-art map sprite: {example}. The right cell, inside the red frame, holds a rough flat {colour_name} shape that I scribbled with the mouse. It is not a drawing to keep, only a sketch of the outline, size and position of a new sprite.

Draw a new {noun}{sub} in the right cell:
- Its outline and size follow the sketch: where the sketch is wide it is wide, where it is tall it is tall, and it stands on the ground where the sketch's lowest point is. Turn the wobbly mouse lines into straight walls, roof edges and posts, as fits a {noun}.
- The flat colour of the sketch, {colour_name} ({hex}), is the main colour of its {main_part}. Shade it with darker and lighter tones of that colour, and give everything the colour does not stand for (such as timber, plaster, stone, doors and windows) fitting medieval colours.
- No trace of the flat sketch or its edge may remain.

The most important thing is that the new {noun} looks like it comes from the exact same game as the sprite on the left:
- Copy its art style exactly: the same size of pixels (not finer), the same outline, the same way of shading with few shades per colour, the same amount of detail, the same viewing angle and the same light from the same side.
- Draw it at the scale the sketch shows next to the left sprite, not at the left sprite's size, so that doors, windows and other parts keep the size they have on the left.
- Plain white background. No shadow, ground or paving beyond what the left sprite has at its foot.

Draw nothing outside the red frame and leave the left cell exactly as it is. Output the full split image.
"""

SOLID_ALPHA = 128   # a pixel of the foot this opaque counts for the collision margins


def building_files():
    """Every building and decoration sprite; a stall's closed sprite goes with its open one."""
    return sorted(p for p in HOUSES_DIR.glob('*.png')
                  if p.name != HOUSES_ATLAS.name and not p.stem.endswith(CLOSED_SUFFIX))


def tiled_properties(kind, sprite, path):
    """The "Houses" object of a new building: class, size and collision box in tiles, and margins in pixels.

    The box runs along the sprite's foot, footprint share of its height
    deep; the margins pull its sides in to where the foot is solid.
    """
    w, h = sprite.get_size()
    tiles_right, tiles_up = math.ceil(w / TILE), math.ceil(h / TILE)
    collision_up = max(1, round(tiles_up * kind.footprint))
    foot = pygame.Rect(0, max(0, h - collision_up * TILE), w, min(h, collision_up * TILE))
    solid = pygame.mask.from_surface(sprite.subsurface(foot), SOLID_ALPHA).get_bounding_rects()
    left, right = 0, w
    if solid:
        box = solid[0].unionall(solid[1:])
        left, right = box.left, box.right
    return {
        'class': kind.tiled_class, 'File_name': path.name,
        'Tiles_to_right': tiles_right, 'Tiles_up': tiles_up,
        'Collision_to_right': tiles_right, 'Collision_up': collision_up,
        'Col_margin_left_pixel': -left, 'Col_margin_right_pixel': right - tiles_right * TILE,
    }


BUILDINGS = Domain(
    key='buildings', title='Buildings', noun='building', kinds=KINDS,
    catalog_path=Path(__file__).resolve().parent / 'building_catalog.json',
    sprite_files=building_files, motif_atlases=(), suggestions=SUGGESTIONS,
    prompt_template=PROMPT_TEMPLATE, tiled_properties=tiled_properties, reference_title='Parts and others',
    default_colour=(150, 60, 45),
)
