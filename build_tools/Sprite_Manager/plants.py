"""The plant sprites: what kinds there are, where they live, and adding a new one.

Plants live in two places at once, and a new one is written to both:

* single sprites, one motif per PNG, which the game draws: trees and bushes
  are assets/map_sprites/trees/<Tree|Bush>_<n>.png, loaded by the "Trees"
  object layer's File_name; small plants go to
  assets/map_sprites/non_collision_deco/plants/<Kind>_<n>.png;
* the big sprite collections Tiled paints the map with: Trees.png (the
  "Trees" tileset) and non_collision_deco.png (the "non_collision_deco"
  tileset). A new sprite is put into the first free place of its
  collection, left edge and foot on the 32 px tile grid, so it can be
  stamped in Tiled like the others. The collection is backed up first, to
  build_tools/output/plants/atlas_backups/. The GIMP files beside them
  (Trees.xcf, non_collision_deco.xcf) do not get the new sprite.

Which kind a sprite is cannot be told from the files - the small plants
only exist inside non_collision_deco.png - so plant_catalog.json next to
this file says it: per single sprite its kind, a subcategory ("oak",
"lavender"), where it sits in its collection and, for trees, its stem; per
motif of non_collision_deco.png its kind, found again by its box. The motifs
are cut out of the collection on the fly (find_motifs()), so a motif that
is not in the catalog yet shows up as unsorted, to be given a kind in the
tool (right-click on its card).
"""

import json
import math
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import pygame

from theme import OUTPUT_DIR, ROOT

MAP_SPRITES = ROOT / 'assets' / 'map_sprites'
CATALOG_PATH = Path(__file__).resolve().parent / 'plant_catalog.json'
PLANT_OUTPUT = OUTPUT_DIR / 'plants'
ATLAS_BACKUPS = PLANT_OUTPUT / 'atlas_backups'
TILE = 32


@dataclass(frozen=True)
class Atlas:
    """One of the big sprite collections a Tiled tileset is cut from."""

    key: str
    path: Path
    tileset: str          # its name in Tiled
    source: str           # the GIMP file it is exported from

    @property
    def name(self):
        return self.path.name


TREES_ATLAS = Atlas('trees', MAP_SPRITES / 'trees' / 'Trees.png', 'Trees', 'Trees.xcf')
DECO_ATLAS = Atlas('deco', MAP_SPRITES / 'non_collision_deco' / 'non_collision_deco.png',
                   'non_collision_deco', 'non_collision_deco.xcf')
ATLASES = {a.key: a for a in (TREES_ATLAS, DECO_ATLAS)}


@dataclass(frozen=True)
class Kind:
    """A kind of plant: where its sprites go and how the prompt names it."""

    key: str
    title: str            # the section title in the overview
    noun: str             # 'needle tree', for the prompt
    main_part: str        # what the chosen colour paints, for the prompt
    atlas: Atlas
    folder: Path          # where its single sprites are saved
    file_prefix: str      # Tree -> Tree_24.png
    stem: bool = False    # stands on a stem the player bumps into (a "Trees" object)


TREES_DIR = MAP_SPRITES / 'trees'
DECO_PLANTS_DIR = MAP_SPRITES / 'non_collision_deco' / 'plants'

KINDS = (
    Kind('needle_tree', 'Needle trees', 'needle tree', 'needles', TREES_ATLAS, TREES_DIR, 'Tree', stem=True),
    Kind('broadleaf_tree', 'Broadleaf trees', 'broadleaf tree', 'leaves', TREES_ATLAS, TREES_DIR, 'Tree',
         stem=True),
    Kind('bush', 'Bushes', 'bush', 'leaves', TREES_ATLAS, TREES_DIR, 'Bush', stem=True),
    Kind('flowers', 'Flowers', 'small flowering plant', 'blossoms', DECO_ATLAS, DECO_PLANTS_DIR, 'Flower'),
    Kind('berries', 'Berries', 'small berry plant', 'berries', DECO_ATLAS, DECO_PLANTS_DIR, 'Berry'),
    Kind('grass_herbs', 'Grass, ferns and herbs', 'tuft of grass or small herb', 'leaves and blades',
         DECO_ATLAS, DECO_PLANTS_DIR, 'Herb'),
    Kind('moss', 'Moss', 'patch of moss', 'moss', DECO_ATLAS, DECO_PLANTS_DIR, 'Moss'),
    Kind('mushrooms', 'Mushrooms', 'mushroom or small cluster of mushrooms', 'caps', DECO_ATLAS,
         DECO_PLANTS_DIR, 'Mushroom'),
)
KINDS_BY_KEY = {k.key: k for k in KINDS}
UNSORTED = 'unsorted'     # a motif or file the catalog does not know yet
REFERENCE = 'reference'   # not a plant: the player drawn into the collection for scale
SORTABLE = tuple(k.key for k in KINDS) + (REFERENCE,)

# Cutting the motifs out of a collection
MOTIF_ALPHA = 100         # pixels at least this opaque hold a motif together
MOTIF_REACH = 2           # pixels this close belong to one motif
MOTIF_MIN_PIXELS = 40     # smaller specks are dropped
MATCH_IOU = 0.6           # a catalog box and a motif this alike are the same motif

# The stem of a new tree, estimated from the foot of the sprite
STEM_BAND = (0.03, 0.09)  # rows this far up from the foot, as a share of the height
STEM_LIMITS = (0.3, 2.5)  # tiles
STEM_COLLISION = 1.4      # the hand-set trees bump a little wider than their trunk shows


def kind_title(key):
    if key in KINDS_BY_KEY:
        return KINDS_BY_KEY[key].title
    return {UNSORTED: 'Unsorted', REFERENCE: 'Not a plant'}.get(key, key)


# ---------------------------------------------------------------------------
# The catalog
# ---------------------------------------------------------------------------

def _rect(values):
    return pygame.Rect(*values) if values else None


def iou(a, b):
    """How alike two boxes are: overlap over union, 0..1."""
    clip = a.clip(b)
    overlap = clip.w * clip.h
    union = a.w * a.h + b.w * b.h - overlap
    return overlap / union if union else 0.0


class Catalog:
    """plant_catalog.json: the kind of every plant sprite.

    {"files": {"trees/Tree_01.png": {"kind": ..., "subcategory": ...,
               "atlas": "trees", "rect": [x, y, w, h],
               "stem_position": 3.0, "stem_thick": 1.2}},
     "motifs": {"deco": [{"rect": [x, y, w, h], "kind": ..., "subcategory": ...}]}}

    File keys are relative to assets/map_sprites, with forward slashes.
    """

    def __init__(self, path=CATALOG_PATH):
        self.path = path
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            data = {}
        self.files = data.get('files', {})
        self.motifs = data.get('motifs', {})

    def save(self):
        data = {'files': self.files, 'motifs': self.motifs}
        self.path.write_text(json.dumps(data, indent=1) + '\n', encoding='utf-8')

    @staticmethod
    def file_key(path):
        return Path(path).relative_to(MAP_SPRITES).as_posix()

    def file_entry(self, path):
        return self.files.get(self.file_key(path))

    def motif_entry(self, atlas_key, rect):
        """The catalog's entry for the motif in `rect`, or None."""
        best, best_iou = None, MATCH_IOU
        for entry in self.motifs.get(atlas_key, []):
            alike = iou(rect, _rect(entry['rect']))
            if alike >= best_iou:
                best, best_iou = entry, alike
        return best

    def placed_rects(self, atlas_key):
        """Where the single sprites sit in a collection, so their motifs are not listed twice."""
        return [_rect(e['rect']) for e in self.files.values() if e.get('atlas') == atlas_key and e.get('rect')]

    def set_kind(self, sprite, kind, subcategory):
        """Give a listed sprite a kind and subcategory, and save."""
        if sprite.path:
            entry = self.files.setdefault(self.file_key(sprite.path), {})
        else:
            entry = self.motif_entry(sprite.atlas.key, sprite.rect)
            if entry is None:
                entry = {'rect': list(sprite.rect)}
                self.motifs.setdefault(sprite.atlas.key, []).append(entry)
            entry['rect'] = list(sprite.rect)   # follow the motif if it was moved a little
        entry['kind'] = kind
        entry['subcategory'] = subcategory
        self.save()


# ---------------------------------------------------------------------------
# The sprites as listed
# ---------------------------------------------------------------------------

@dataclass(eq=False)
class PlantSprite:
    """One plant motif: a single sprite file, or a motif inside a collection."""

    kind: str
    subcategory: str
    label: str
    surface: pygame.Surface        # trimmed, transparent
    path: Optional[Path] = None    # the single sprite, if it is one
    atlas: Optional[Atlas] = None  # the collection a motif was cut from
    rect: Optional[pygame.Rect] = None

    @property
    def where(self):
        """Where it lives, for its card."""
        if self.path:
            return self.path.name
        return f'{self.atlas.name} {self.rect.x},{self.rect.y}'


def _grown(mask, reach):
    kernel = pygame.Mask((2 * reach + 1, 2 * reach + 1), fill=True)
    return mask.convolve(kernel, None, (-reach, -reach))


def find_motifs(image):
    """The motifs of a collection: [(box, mask over the whole image)].

    Pixels close together make one motif; a motif lying wholly inside the box
    of a bigger one (a stray berry in a patch) is part of that one.
    """
    solid = pygame.mask.from_surface(image, MOTIF_ALPHA)
    motifs = []
    for part in _grown(solid, MOTIF_REACH).connected_components(1):
        if solid.overlap_area(part, (0, 0)) < MOTIF_MIN_PIXELS:
            continue
        rects = part.get_bounding_rects()
        motifs.append([rects[0].unionall(rects[1:]).clip(image.get_rect()), part])
    motifs.sort(key=lambda m: -m[0].w * m[0].h)
    kept = []
    for rect, mask in motifs:
        home = next((k for k in kept if k[0].contains(rect)), None)
        if home:
            home[1].draw(mask, (0, 0))
        else:
            kept.append([rect, mask])
    kept.sort(key=lambda m: (m[0].y // 40, m[0].x))
    return [(rect, mask) for rect, mask in kept]


def cut_motif(image, rect, mask):
    """The motif in `rect` alone, without neighbours reaching into its box."""
    part = image.subsurface(rect).copy()
    alpha = pygame.Mask(rect.size)
    alpha.draw(mask, (-rect.x, -rect.y))
    part.blit(alpha.to_surface(setcolor=(255, 255, 255, 255), unsetcolor=(0, 0, 0, 0)), (0, 0),
              special_flags=pygame.BLEND_RGBA_MULT)
    return part


def _label(name, subcategory):
    return f'{name} - {subcategory}' if subcategory else name


def _single_sprite_files():
    """Every single plant sprite on disk: the numbered trees and bushes, and the small plants."""
    files = sorted(TREES_DIR.glob('Tree_*.png')) + sorted(TREES_DIR.glob('Bush_*.png'))
    if DECO_PLANTS_DIR.is_dir():
        files += sorted(DECO_PLANTS_DIR.glob('*.png'))
    return files


def find_plants(catalog=None):
    """Every plant sprite, single files first, then the motifs of non_collision_deco.png.

    Needs a pygame display (convert_alpha).
    """
    catalog = catalog or Catalog()
    plants = []
    for path in _single_sprite_files():
        try:
            image = pygame.image.load(str(path)).convert_alpha()
        except (pygame.error, OSError):
            continue
        if not image.get_bounding_rect().w:
            continue
        entry = catalog.file_entry(path) or {}
        kind = entry.get('kind', UNSORTED)
        sub = entry.get('subcategory', '')
        plants.append(PlantSprite(kind, sub, _label(path.stem, sub), image.subsurface(image.get_bounding_rect()).copy(),
                                  path=path, atlas=ATLASES.get(entry.get('atlas')), rect=_rect(entry.get('rect'))))

    atlas = DECO_ATLAS
    try:
        image = pygame.image.load(str(atlas.path)).convert_alpha()
    except (pygame.error, OSError):
        return plants
    placed = catalog.placed_rects(atlas.key)
    for rect, mask in find_motifs(image):
        if any(iou(rect, p) >= MATCH_IOU for p in placed):
            continue   # a single sprite listed above
        entry = catalog.motif_entry(atlas.key, rect) or {}
        kind = entry.get('kind', UNSORTED)
        sub = entry.get('subcategory', '')
        plants.append(PlantSprite(kind, sub, sub or 'motif', cut_motif(image, rect, mask),
                                  atlas=atlas, rect=rect))
    return plants


# ---------------------------------------------------------------------------
# Adding a new plant
# ---------------------------------------------------------------------------

def next_free_file(kind):
    """<Prefix>_<n>.png after the highest number its folder has."""
    numbers = [0]
    for path in kind.folder.glob(f'{kind.file_prefix}_*.png'):
        tail = path.stem[len(kind.file_prefix) + 1:]
        if tail.isdigit():
            numbers.append(int(tail))
    return kind.folder / f'{kind.file_prefix}_{max(numbers) + 1:02d}.png'


def free_place(atlas_image, size, pad=TILE):
    """Top-left of the first free place for a sprite of `size` in a collection.

    Searched row by row on the tile grid, so the sprite's left edge and foot
    sit on tile lines. Keeps `pad` clear around it. None if it is full.
    """
    w, h = size
    box_w = math.ceil(w / TILE) * TILE + 2 * pad
    box_h = math.ceil(h / TILE) * TILE + 2 * pad
    taken = pygame.mask.from_surface(atlas_image, 1)
    box = pygame.Mask((box_w, box_h), fill=True)
    width, height = atlas_image.get_size()
    for y in range(0, height - box_h + 1, TILE):
        for x in range(0, width - box_w + 1, TILE):
            if taken.overlap(box, (x, y)) is None:
                foot = y + box_h - pad
                return x + pad, foot - h
    return None


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


@dataclass
class AddedPlant:
    """What adding a plant wrote."""

    path: Path
    atlas: Atlas
    rect: pygame.Rect
    stem: Optional[tuple] = None   # (Stem_Position, Stem_Thick) in tiles, for stemmed kinds
    backup: Optional[Path] = None
    notes: list = field(default_factory=list)

    def summary(self):
        """One line for the status bar."""
        text = f'Saved {self.path.name}, placed in {self.atlas.name} at {self.rect.x},{self.rect.y}'
        if self.stem:
            text += f' - Tiled: File_name {self.path.name}, Stem_Position {self.stem[0]}, Stem_Thick {self.stem[1]}'
        return text


def add_plant(sprite, kind, subcategory, catalog=None):
    """Save a new plant as a single sprite and into its collection, and catalog it.

    Args:
        sprite: The finished transparent sprite.
        kind: A Kind.
        subcategory: '' or e.g. 'oak'.

    Returns:
        AddedPlant.

    Raises:
        pygame.error, OSError: If a file cannot be read or written.
        ValueError: If the collection has no room left.
    """
    catalog = catalog or Catalog()
    sprite = sprite.subsurface(sprite.get_bounding_rect()).copy()
    atlas = kind.atlas
    atlas_image = pygame.image.load(str(atlas.path)).convert_alpha()
    spot = free_place(atlas_image, sprite.get_size())
    if spot is None:
        raise ValueError(f'No room left in {atlas.name}')

    path = next_free_file(kind)
    path.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(sprite, str(path))

    ATLAS_BACKUPS.mkdir(parents=True, exist_ok=True)
    backup = ATLAS_BACKUPS / f'{atlas.path.stem}_{datetime.now():%Y%m%d_%H%M%S}.png'
    shutil.copy2(atlas.path, backup)
    atlas_image.blit(sprite, spot)
    pygame.image.save(atlas_image, str(atlas.path))

    rect = pygame.Rect(spot, sprite.get_size())
    stem = estimate_stem(sprite) if kind.stem else None
    entry = {'kind': kind.key, 'subcategory': subcategory, 'atlas': atlas.key, 'rect': list(rect)}
    if stem:
        entry['stem_position'], entry['stem_thick'] = stem
    catalog.files[catalog.file_key(path)] = entry
    catalog.save()
    return AddedPlant(path, atlas, rect, stem, backup)
