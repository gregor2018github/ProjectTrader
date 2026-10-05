"""The buildings and their decorations, as a sprite_library.Domain.

All of them are single sprites in assets/map_sprites/houses/ - House_<n>,
Market_<n>, Fence_<n>, Deco_<n> - loaded by the "Houses" object layer's
File_name, and live in Houses.png for Tiled. Which kind each is (a
dwelling, a workshop, a stall ...) is in building_catalog.json. A market
stall's closed sprite, Market_<n>_closed.png, which the game shows at night,
is listed right after its open one.

A new building's object needs its size and collision box in tiles, which
tiled_properties() works out from the sprite: the tiles it covers, and a box
along its foot as deep as the kind's footprint share of its height (a house
stands on about a third of its picture, a stall on half), narrowed by pixel
margins to where the foot is solid. They are a start, to be fine-tuned in
Tiled like the others.

A bridge, Bridge_<n>, is no "Houses" object but a rectangle on the
"Bridges" layer, as big as its sprite, with the band people walk along
in it; the game also takes an optional Bridge_<n>_front.png of the same
size, holding only the near railing, to draw over whoever is on it (made
with bridge_front.py).
"""

import math
from pathlib import Path

import pygame

from sprite_library import MAP_SPRITES, TILE, Atlas, Domain, Kind

HOUSES_ATLAS = Atlas('houses', MAP_SPRITES / 'houses' / 'Houses.png', 'Houses', 'Houses.xcf')
HOUSES_DIR = MAP_SPRITES / 'houses'

#: What a bridge needs that a building does not; the game lays it flat over the
#: water and lets people walk along its walkway (src/models/bridge.py).
BRIDGE_NOTES = (
    'It runs from left to right, as if across a river flowing from the top of the picture to the bottom, '
    'and is seen from the same high three-quarter angle as the sprite in the {first} cell: the '
    'walkway is seen from above, the railing along its far side stands behind the walkway and the '
    'railing along its near side in front of it, low and open enough that the walkway behind it stays '
    'in view.',
    'The walkway is flat and level from end to end, with no arch, no steps and no roof, and both ends '
    'are open so people can walk on and off: each railing ends in a post at either end.',
    'Do not draw any water, river bank, grass or road. The game draws the river under the bridge, so '
    'below the walkway only its beams and the tops of the piles holding it up show.',
)
BRIDGE_DECK = (0.25, 0.67)   # share of a bridge sprite's height where its walkway begins and ends

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
    Kind('bridge', 'Bridges', 'bridge', 'walkway', HOUSES_ATLAS, HOUSES_DIR, 'Bridge',
         tiled_class='Bridge', prompt_notes=BRIDGE_NOTES),
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
    'bridge': ('wooden plank bridge', 'trestle bridge', 'footbridge', 'bridge with rope railings',
               'log bridge', 'stone bridge'),
}

PROMPT_TEMPLATE = """\
The attached picture is a split view for my medieval trading game "Merchant's Rise". The {first} cell shows an existing pixel-art map sprite: {example}. The {second} cell, inside the red frame, holds a rough flat {colours} shape that I scribbled with the mouse. It is not a drawing to keep, only a sketch of the outline, size and position of a new sprite.

Draw a new {noun}{sub} in the {second} cell:
- Its outline and size follow the sketch: where the sketch is wide it is wide, where it is tall it is tall, and it stands on the ground where the sketch's lowest point is. Turn the wobbly mouse lines into straight walls, roof edges and posts, as fits a {noun}.
- {colour_rule}, and give everything the colours do not stand for (such as timber, plaster, stone, doors and windows) fitting medieval colours.
- No trace of the flat sketch or its edge may remain.{notes}

The most important thing is that the new {noun} looks like it comes from the exact same game as the sprite in the {first} cell:
- Copy its art style exactly: the same size of pixels (not finer), the same outline, the same way of shading with few shades per colour, the same amount of detail, the same viewing angle and the same light from the same side.
- Draw it at the scale the sketch shows next to the {first} sprite, not at the {first} sprite's size, so that doors, windows and other parts keep the size they have in the {first} cell.
- Plain white background. No shadow, ground or paving beyond what the {first} sprite has at its foot.

Draw nothing outside the red frame and leave the {first} cell exactly as it is. Output the full split image.
"""

SOLID_ALPHA = 128   # a pixel of the foot this opaque counts for the collision margins


def building_files():
    """Every building and decoration sprite; by name, so a stall's closed sprite follows its open one."""
    return sorted(p for p in HOUSES_DIR.glob('*.png') if p.name != HOUSES_ATLAS.name)


def tiled_properties(kind, sprite, path):
    """The "Houses" object of a new building: class, size and collision box in tiles, and margins in pixels.

    The box runs along the sprite's foot, footprint share of its height
    deep; the margins pull its sides in to where the foot is solid. A bridge
    gets its "Bridges" rectangle instead, see bridge_properties().
    """
    if kind.key == 'bridge':
        return bridge_properties(sprite, path)
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


def bridge_properties(sprite, path):
    """The "Bridges" rectangle of a new bridge: the sprite's own size, and a first guess at its walkway.

    Deck_top and Deck_bottom, in tiles from the top, bound the band feet
    may stand in; whatever is above and below it is railing. The guess
    leaves the far railing the top quarter and the near railing, with the
    beams under it, the bottom third, to be fine-tuned in Tiled.
    """
    w, h = sprite.get_size()
    return {
        'layer': 'Bridges', 'class': 'Bridge', 'File_name': path.name, 'width': w, 'height': h,
        'Deck_top': round(h * BRIDGE_DECK[0] / TILE, 2), 'Deck_bottom': round(h * BRIDGE_DECK[1] / TILE, 2),
    }


BUILDINGS = Domain(
    key='buildings', title='Buildings', noun='building', kinds=KINDS,
    catalog_path=Path(__file__).resolve().parent / 'building_catalog.json',
    sprite_files=building_files, motif_atlases=(), suggestions=SUGGESTIONS,
    prompt_template=PROMPT_TEMPLATE, tiled_properties=tiled_properties, reference_title='Parts and others',
    default_colour=(150, 60, 45), example_share=0.8,
)
