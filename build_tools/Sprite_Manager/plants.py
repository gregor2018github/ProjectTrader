"""The plants, as a sprite_library.Domain: their kinds, where they live, the prompt.

Trees and bushes are single sprites assets/map_sprites/trees/<Tree|Bush>_<n>.png,
loaded by the "Trees" object layer's File_name, and live in Trees.png for
Tiled. Small plants go to assets/map_sprites/non_collision_deco/plants/ and
non_collision_deco.png - which holds the older small plants only as motifs,
so those are cut out of it and sorted in plant_catalog.json.
"""

from pathlib import Path

import pygame

from sprite_library import MAP_SPRITES, TILE, Atlas, Domain, Kind

TREES_ATLAS = Atlas('trees', MAP_SPRITES / 'trees' / 'Trees.png', 'Trees', 'Trees.xcf')
DECO_ATLAS = Atlas('deco', MAP_SPRITES / 'non_collision_deco' / 'non_collision_deco.png',
                   'non_collision_deco', 'non_collision_deco.xcf')
TREES_DIR = MAP_SPRITES / 'trees'
DECO_PLANTS_DIR = MAP_SPRITES / 'non_collision_deco' / 'plants'

KINDS = (
    Kind('needle_tree', 'Needle trees', 'needle tree', 'needles', TREES_ATLAS, TREES_DIR, 'Tree', stem=True),
    Kind('broadleaf_tree', 'Broadleaf trees', 'broadleaf tree', 'crown (its leaves, or its blossoms if it is in bloom)',
         TREES_ATLAS, TREES_DIR, 'Tree', stem=True),
    Kind('bush', 'Bushes', 'bush', 'foliage (its leaves, or its blossoms if it is in bloom)',
         TREES_ATLAS, TREES_DIR, 'Bush', stem=True),
    Kind('flowers', 'Flowers', 'small flowering plant', 'blossoms', DECO_ATLAS, DECO_PLANTS_DIR, 'Flower'),
    Kind('berries', 'Berries', 'small berry plant', 'berries', DECO_ATLAS, DECO_PLANTS_DIR, 'Berry'),
    Kind('grass_herbs', 'Grass, ferns and herbs', 'tuft of grass or small herb', 'leaves and blades',
         DECO_ATLAS, DECO_PLANTS_DIR, 'Herb'),
    Kind('moss', 'Moss', 'patch of moss', 'moss', DECO_ATLAS, DECO_PLANTS_DIR, 'Moss'),
    Kind('mushrooms', 'Mushrooms', 'mushroom or small cluster of mushrooms', 'caps', DECO_ATLAS,
         DECO_PLANTS_DIR, 'Mushroom'),
)

#: Subcategories the design screen proposes per kind: what grows in and around
#: a medieval town somewhere in England or western Europe - the woods, hedges,
#: meadows, cottage and monastery gardens - picked for the look, not botany.
SUGGESTIONS = {
    'needle_tree': ('Scots pine', 'Norway spruce', 'silver fir', 'English yew', 'churchyard yew',
                    'European larch', 'common juniper', 'stone pine', 'young fir sapling', 'dead pine snag'),
    'broadleaf_tree': ('English oak', 'gnarled old oak', 'beech', 'ash', 'elm', 'lime tree', 'silver birch',
                       'hornbeam', 'sweet chestnut', 'walnut', 'weeping willow', 'pollarded willow', 'alder',
                       'rowan', 'field maple', 'apple tree', 'pear tree', 'cherry tree', 'holly tree'),
    'bush': ('hawthorn', 'blackthorn', 'elder', 'hazel', 'holly bush', 'dog rose', 'rosebush', 'bramble',
             'gorse', 'broom', 'box hedge', 'privet hedge', 'rosemary bush', 'gooseberry bush',
             'redcurrant bush', 'juniper shrub'),
    'flowers': ('poppies', 'cornflowers', 'daisies', 'dandelions', 'buttercups', 'foxgloves', 'bluebells',
                'primroses', 'cowslips', 'forget-me-nots', 'violets', 'marigolds', 'madonna lilies', 'lavender',
                'heather', 'thistles', 'yarrow', 'chamomile', "St John's wort", 'meadowsweet', 'irises'),
    'berries': ('wild strawberries', 'bilberries', 'lingonberries', 'cranberries', 'raspberry canes',
                'dewberries', 'cloudberries', 'redcurrants'),
    'grass_herbs': ('tall meadow grass', 'reeds', 'rushes', 'cattails', 'bracken fern', 'nettles', 'ivy', 'clover',
                    'thyme', 'sage', 'rosemary', 'mint', 'parsley', 'dill', 'fennel', 'rue', 'mugwort',
                    'wormwood', 'sorrel', 'plantain'),
    'moss': ('cushion moss', 'mossy stone', 'moss on a fallen log', 'lichen patch', 'peat moss',
             'haircap moss'),
    'mushrooms': ('fly agaric', 'porcini', 'chanterelles', 'field mushrooms', 'puffballs', 'fairy ring',
                  'shaggy ink caps', 'morels', 'honey fungus on a stump', 'bracket fungus on a log'),
}

PROMPT_TEMPLATE = """\
The attached picture is a split view for my medieval trading game "Merchant's Rise". The {first} cell shows an existing pixel-art map sprite: {example}. The {second} cell, inside the red frame, holds a rough flat {colours} shape that I scribbled with the mouse. It is not a drawing to keep, only a sketch of the outline, size and position of a new sprite.

Draw a new {noun}{sub} in the {second} cell:
- Its outline and size follow the sketch: where the sketch is wide it is wide, where it is tall it is tall, and it stands on the ground where the sketch's lowest point is. Turn the wobbly mouse lines into a natural shape for a {noun}.
- {colour_rule}, and give the parts the colours do not stand for (such as stems, trunk or soil) natural colours.
- No trace of the flat sketch or its edge may remain.{notes}

The most important thing is that the new {noun} looks like it comes from the exact same game as the sprite in the {first} cell:
- Copy its art style exactly: the same size of pixels (not finer), the same outline, the same way of shading with few shades per colour, the same amount of detail, the same viewing angle and the same light from the same side.
- Draw it at the scale the sketch shows next to the {first} sprite, not at the {first} sprite's size.
- Plain white background. No shadow, ground or grass beyond what the {first} sprite has at its foot.

Draw nothing outside the red frame and leave the {first} cell exactly as it is. Output the full split image.
"""

# The stem of a new tree, estimated from the foot of the sprite
STEM_BAND = (0.03, 0.09)  # rows this far up from the foot, as a share of the height
STEM_LIMITS = (0.3, 2.5)  # tiles
STEM_COLLISION = 1.4      # the hand-set trees bump a little wider than their trunk shows


def plant_files():
    """Every single plant sprite on disk: the numbered trees and bushes, and the small plants."""
    files = sorted(TREES_DIR.glob('Tree_*.png')) + sorted(TREES_DIR.glob('Bush_*.png'))
    if DECO_PLANTS_DIR.is_dir():
        files += sorted(DECO_PLANTS_DIR.glob('*.png'))
    return files


def estimate_stem(sprite):
    """(stem centre from the left, stem width), in tiles, from the sprite's foot.

    Looks at a band of rows just above the foot - above the grass a tree
    stands in - and takes the opaque run nearest the middle in each.
    """
    mask = pygame.mask.from_surface(sprite, 128)
    w, h = sprite.get_size()
    centres, widths = [], []
    for share in [STEM_BAND[0] + i * (STEM_BAND[1] - STEM_BAND[0]) / 6 for i in range(7)]:
        y = h - 1 - int(h * share)
        runs, start = [], None
        for x in range(w + 1):
            on = x < w and mask.get_at((x, y))
            if on and start is None:
                start = x
            elif not on and start is not None:
                runs.append((start, x))
                start = None
        if runs:
            a, b = min(runs, key=lambda r: abs((r[0] + r[1]) / 2 - w / 2))
            centres.append((a + b) / 2)
            widths.append(b - a)
    if not centres:
        return round(w / 2 / TILE, 2), STEM_LIMITS[0]
    centres.sort()
    widths.sort()
    centre = centres[len(centres) // 2]
    thick = min(max(widths[len(widths) // 2] * STEM_COLLISION / TILE, STEM_LIMITS[0]), STEM_LIMITS[1])
    return round(centre / TILE, 2), round(thick, 1)


def tiled_properties(kind, sprite, path):
    """A tree's or bush's "Trees" object: its stem. Small plants are painted as tiles and need none."""
    if not kind.stem:
        return {}
    position, thick = estimate_stem(sprite)
    return {'File_name': path.name, 'Stem_Position': position, 'Stem_Thick': thick}


PLANTS = Domain(
    key='plants', title='Plants', noun='plant', kinds=KINDS,
    catalog_path=Path(__file__).resolve().parent / 'plant_catalog.json',
    sprite_files=plant_files, motif_atlases=(DECO_ATLAS,), suggestions=SUGGESTIONS,
    prompt_template=PROMPT_TEMPLATE, tiled_properties=tiled_properties, reference_title='Not a plant',
    default_colour=(70, 125, 50),
)
