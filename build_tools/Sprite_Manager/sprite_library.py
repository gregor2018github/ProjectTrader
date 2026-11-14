"""Map sprites made from an example: what kinds there are, where they live, and adding a new one.

Two families of map sprites are made this way, each a Domain: the plants
(plants.py) and the buildings with their decorations (buildings.py). Both
live in two places at once, and a new sprite is written to both:

* single sprites, one motif per PNG, which the game draws (the "Trees" and
  "Houses" object layers name them in File_name);
* the big sprite collections Tiled paints the map with, such as Trees.png
  or Houses.png. A new sprite is put into the first free place of its
  collection, left edge and foot on the 32 px tile grid, so it can be
  stamped in Tiled like the others. The collection is backed up first, to
  build_tools/output/<domain>/atlas_backups/. The GIMP file it is exported
  from (Trees.xcf, Houses.xcf, ...) does not get the new sprite.

  When a collection has no room left, the sprite goes into the next one of
  its series, Houses_2.png, Houses_3.png ... (Atlas.series()), and when
  they are all full a new one is started, as big as the first and empty,
  with a tileset of its own (Houses_2.tsx beside the map) that is added to
  Map1.tmx, so Tiled offers it at once (start_overflow()). The game loads
  every tileset of the map, so the new files must be committed with it.

Which kind a sprite is cannot always be told from the files - the small
plants only exist inside non_collision_deco.png - so each domain has a
catalog next to this file (plant_catalog.json, building_catalog.json): per
single sprite its kind, a subcategory ("oak", "bakery"), where it sits in
its collection and the Tiled properties worked out for it; per motif of a
collection without single sprites its kind, found again by its box. The
motifs are cut out of the collection on the fly (find_motifs()), so one not
in the catalog yet shows up as unsorted, to be given a kind in the tool
(right-click on its card).
"""

import json
import math
import os
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import pygame

from theme import OUTPUT_DIR, ROOT

MAP_SPRITES = ROOT / 'assets' / 'map_sprites'
TILED_DIR = ROOT / 'assets' / 'tiles'
MAP_FILE = TILED_DIR / 'Map1.tmx'
TILE = 32

UNSORTED = 'unsorted'     # a motif or file the catalog does not know yet
REFERENCE = 'reference'   # in the folder, but not something to make more of (a part, a scale figure)

# Cutting the motifs out of a collection
MOTIF_ALPHA = 100         # pixels at least this opaque hold a motif together
MOTIF_REACH = 2           # pixels this close belong to one motif
MOTIF_MIN_PIXELS = 40     # smaller specks are dropped
MATCH_IOU = 0.6           # a catalog box and a motif this alike are the same motif


@dataclass(frozen=True)
class Atlas:
    """One of the big sprite collections a Tiled tileset is cut from."""

    key: str
    path: Path
    tileset: str          # its name in Tiled
    source: str           # the GIMP file it is exported from

    def overflow(self, number):
        """The `number`th collection of this one's series (2, 3 ...): Houses_2.png, tileset Houses_2.

        It has no GIMP file: the tool writes it directly.
        """
        return Atlas(f'{self.key}_{number}', self.path.with_name(f'{self.path.stem}_{number}{self.path.suffix}'),
                     f'{self.tileset}_{number}', '')

    def series(self):
        """This collection and the overflow ones after it that exist on disk, in order."""
        found, number = [self], 2
        while (nxt := self.overflow(number)).path.is_file():
            found.append(nxt)
            number += 1
        return found

    def is_collection_file(self, path):
        """Whether `path` is this collection or one of its overflow ones (not a single sprite)."""
        path = Path(path)
        return path.parent == self.path.parent and re.fullmatch(
            rf'{re.escape(self.path.stem)}(_\d+)?{re.escape(self.path.suffix)}', path.name) is not None

    @property
    def name(self):
        return self.path.name


@dataclass(frozen=True)
class Kind:
    """A kind of sprite: where its sprites go and how the prompt names it."""

    key: str
    title: str            # the section title in the overview
    noun: str             # 'needle tree', for the prompt
    main_part: str        # what the chosen colour paints, for the prompt
    atlas: Atlas
    folder: Path          # where its single sprites are saved
    file_prefix: str      # Tree -> Tree_24.png
    stem: bool = False    # a plant on a stem the player bumps into (a "Trees" object)
    tiled_class: str = ''  # a building's class on the "Houses" object layer
    footprint: float = 0.0  # a building's share of its height that it stands on (its collision)
    prompt_notes: tuple = ()  # further rules for the prompt, for a kind the general ones do not fit
    prompt_variations: tuple = ()  # groups of alternative rules; each prompt takes one of every group at random


@dataclass(frozen=True)
class Domain:
    """A family of map sprites made from examples: the plants, or the buildings."""

    key: str                    # 'plants', also the output folder
    title: str                  # 'Plants'
    noun: str                   # 'plant'
    kinds: tuple
    catalog_path: Path
    sprite_files: Callable      # () -> [Path] of every single sprite
    motif_atlases: tuple        # collections whose motifs are listed as sprites of their own
    suggestions: dict           # {kind key: (subcategory, ...)} proposed on the design screen
    prompt_template: str
    tiled_properties: Callable  # (Kind, sprite surface, saved path) -> {Tiled property: value}
    reference_title: str        # the section of REFERENCE sprites
    default_colour: tuple = (70, 125, 50)
    example_share: float = 0.6  # of a new sprite's cell the example takes; the rest is room to sketch bigger
    in_game: Optional[Callable] = None   # (sprite path) -> whether the game shows it; None: not known

    @property
    def kinds_by_key(self):
        return {k.key: k for k in self.kinds}

    @property
    def atlases(self):
        """{key: Atlas} of every collection, each kind's overflow ones included."""
        found = {}
        for kind in self.kinds:
            found.update((a.key, a) for a in kind.atlas.series())
        found.update((a.key, a) for a in self.motif_atlases)
        return found

    @property
    def sortable(self):
        """The kinds a sprite can be given in the catalog."""
        return tuple(k.key for k in self.kinds) + (REFERENCE,)

    @property
    def output(self):
        """build_tools/output/<domain>: the jobs and the atlas backups."""
        return OUTPUT_DIR / self.key

    def kind_title(self, key):
        if key in self.kinds_by_key:
            return self.kinds_by_key[key].title
        return {UNSORTED: 'Unsorted', REFERENCE: self.reference_title}.get(key, key)


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
    """A domain's catalog: the kind of every sprite.

    {"files": {"trees/Tree_01.png": {"kind": ..., "subcategory": ...,
               "atlas": "trees", "rect": [x, y, w, h],
               "tiled": {"Stem_Position": 3.0, "Stem_Thick": 1.2}}},
     "motifs": {"deco": [{"rect": [x, y, w, h], "kind": ..., "subcategory": ...}]}}

    File keys are relative to assets/map_sprites, with forward slashes.
    """

    def __init__(self, path):
        self.path = Path(path)
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
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
class LibrarySprite:
    """One motif: a single sprite file, or a motif inside a collection."""

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
    """The motifs of a collection: [(box, mask over that box)].

    Pixels close together make one motif; a motif lying wholly inside the box
    of a bigger one (a stray berry in a patch) is part of that one.

    The collections are big (4000 x 4000), so the image is scanned only once
    for the motifs' boxes, and each motif is then picked out of its own box.
    """
    solid = pygame.mask.from_surface(image, MOTIF_ALPHA)
    grown = _grown(solid, MOTIF_REACH)
    motifs = []
    for rect in grown.get_bounding_rects():
        rect = rect.clip(image.get_rect())
        box = pygame.Mask(rect.size)
        box.draw(grown, (-rect.x, -rect.y))
        # Neighbours may reach into the box; the motif is the part spanning all of it
        parts = [m for m in box.connected_components(1) if m.get_bounding_rects()[0].size == rect.size]
        if not parts:
            continue
        part = max(parts, key=lambda m: m.count())
        if solid.overlap_area(part, rect.topleft) < MOTIF_MIN_PIXELS:
            continue
        motifs.append([rect, part])
    motifs.sort(key=lambda m: -m[0].w * m[0].h)
    kept = []
    for rect, mask in motifs:
        home = next((k for k in kept if k[0].contains(rect)), None)
        if home:
            home[1].draw(mask, (rect.x - home[0].x, rect.y - home[0].y))
        else:
            kept.append([rect, mask])
    kept.sort(key=lambda m: (m[0].y // 40, m[0].x))
    return [(rect, mask) for rect, mask in kept]


def cut_motif(image, rect, mask):
    """The motif in `rect` alone, without neighbours reaching into its box."""
    part = image.subsurface(rect).copy()
    part.blit(mask.to_surface(setcolor=(255, 255, 255, 255), unsetcolor=(0, 0, 0, 0)), (0, 0),
              special_flags=pygame.BLEND_RGBA_MULT)
    return part


def _label(name, subcategory):
    return f'{name} - {subcategory}' if subcategory else name


def find_sprites(domain, catalog=None):
    """Every sprite of a domain, single files first, then the motifs of its collections.

    Needs a pygame display (convert_alpha).
    """
    catalog = catalog or Catalog(domain.catalog_path)
    sprites = []
    for path in domain.sprite_files():
        try:
            image = pygame.image.load(str(path)).convert_alpha()
        except (pygame.error, OSError):
            continue
        box = image.get_bounding_rect()
        if not box.w:
            continue
        entry = catalog.file_entry(path) or {}
        sub = entry.get('subcategory', '')
        sprites.append(LibrarySprite(entry.get('kind', UNSORTED), sub, _label(path.stem, sub),
                                     image.subsurface(box).copy(), path=path,
                                     atlas=domain.atlases.get(entry.get('atlas')), rect=_rect(entry.get('rect'))))

    for atlas in domain.motif_atlases:
        try:
            image = pygame.image.load(str(atlas.path)).convert_alpha()
        except (pygame.error, OSError):
            continue
        placed = catalog.placed_rects(atlas.key)
        for rect, mask in find_motifs(image):
            if any(iou(rect, p) >= MATCH_IOU for p in placed):
                continue   # a single sprite listed above
            entry = catalog.motif_entry(atlas.key, rect) or {}
            sub = entry.get('subcategory', '')
            sprites.append(LibrarySprite(entry.get('kind', UNSORTED), sub, sub or 'motif',
                                         cut_motif(image, rect, mask), atlas=atlas, rect=rect))
    return sprites


# ---------------------------------------------------------------------------
# Adding a new sprite
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


@dataclass
class AddedSprite:
    """What adding a sprite wrote."""

    path: Path
    atlas: Atlas
    rect: pygame.Rect
    tiled: dict = field(default_factory=dict)   # the Tiled properties to give its object
    backup: Optional[Path] = None
    started: bool = False   # the collection was started for it, the others being full

    def summary(self):
        """One line for the status bar."""
        text = f'Saved {self.path.name}, placed in {self.atlas.name} at {self.rect.x},{self.rect.y}'
        if self.started:
            text += f' (a new collection, tileset {self.atlas.tileset} added to {MAP_FILE.name})'
        if self.tiled:
            text += ' - Tiled: ' + ', '.join(f'{name} {value}' for name, value in self.tiled.items())
        return text


def restamp(domain, path, catalog):
    """Put a single sprite edited outside the tool back into its collection, where it was.

    The sprite keeps its place's left edge and foot. If it grew into a
    neighbour the collection is left alone. The collection is backed up
    first, and a new size updates the catalog, the Tiled hints included.

    A catalog entry whose "atlas" is '' is in no collection (a market
    stall's closed sprite, which the game swaps in itself); nothing to do.

    Returns:
        (line for the status bar, True if all is up to date).

    Raises:
        pygame.error, OSError: If a file cannot be read or written.
    """
    entry = catalog.file_entry(path)
    if entry and entry.get('atlas') == '':
        return f'{path.name} saved - it is in no collection, the game loads it as it is', True
    atlas = domain.atlases.get((entry or {}).get('atlas'))
    if not (entry and entry.get('rect') and atlas):
        return f'{path.name} saved - its place in the collection is not known, so update that by hand', False
    old = _rect(entry['rect'])
    sprite = pygame.image.load(str(path)).convert_alpha()
    new = pygame.Rect(old.x, old.bottom - sprite.get_height(), *sprite.get_size())
    atlas_image = pygame.image.load(str(atlas.path)).convert_alpha()
    if not atlas_image.get_rect().contains(new):
        return f'{path.name} saved - it no longer fits at its place in {atlas.name}, which was left as it was', False
    others = pygame.mask.from_surface(atlas_image, 1)
    others.erase(pygame.Mask(old.size, fill=True), old.topleft)
    if others.overlap(pygame.Mask(new.size, fill=True), new.topleft):
        return f'{path.name} saved - it grew into a neighbour in {atlas.name}, which was left as it was', False

    backups = domain.output / 'atlas_backups'
    backups.mkdir(parents=True, exist_ok=True)
    shutil.copy2(atlas.path, backups / f'{atlas.path.stem}_{datetime.now():%Y%m%d_%H%M%S}.png')
    atlas_image.fill((0, 0, 0, 0), old)
    atlas_image.blit(sprite, new.topleft)
    pygame.image.save(atlas_image, str(atlas.path))

    if new.size != old.size:
        entry['rect'] = list(new)
        kind = domain.kinds_by_key.get(entry.get('kind'))
        if kind and entry.get('tiled'):
            entry['tiled'] = domain.tiled_properties(kind, sprite, path)
        catalog.save()
        hints = ', '.join(f'{name} {value}' for name, value in entry.get('tiled', {}).items())
        text = f'{path.name} saved and updated in {atlas.name}, now {new.w} x {new.h}'
        return text + (f' - Tiled: {hints}' if hints else ''), True
    return f'{path.name} saved and updated in {atlas.name}', True


def add_sprite(domain, sprite, kind, subcategory, catalog=None):
    """Save a new sprite as a single sprite and into its collection, and catalog it.

    Args:
        domain: The Domain it belongs to.
        sprite: The finished transparent sprite.
        kind: A Kind of the domain.
        subcategory: '' or e.g. 'oak'.

    Returns:
        AddedSprite.

    Raises:
        pygame.error, OSError: If a file cannot be read or written.
        ValueError: If the collection has no room left.
    """
    catalog = catalog or Catalog(domain.catalog_path)
    sprite = sprite.subsurface(sprite.get_bounding_rect()).copy()
    series = kind.atlas.series()
    atlas = spot = atlas_image = None
    for atlas in series:
        atlas_image = pygame.image.load(str(atlas.path)).convert_alpha()
        spot = free_place(atlas_image, sprite.get_size())
        if spot is not None:
            break
    started = spot is None
    if started:   # every collection of the series is full: start the next one, as big as the first
        size = pygame.image.load(str(kind.atlas.path)).get_size()
        atlas = kind.atlas.overflow(len(series) + 1)
        atlas_image = pygame.Surface(size, pygame.SRCALPHA)
        atlas_image.fill((0, 0, 0, 0))
        spot = free_place(atlas_image, sprite.get_size())
        if spot is None:
            raise ValueError(f'{sprite.get_width()} x {sprite.get_height()} is too big for a collection '
                             f'of {size[0]} x {size[1]}')

    path = next_free_file(kind)
    path.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(sprite, str(path))

    backup = None
    if not started:
        backups = domain.output / 'atlas_backups'
        backups.mkdir(parents=True, exist_ok=True)
        backup = backups / f'{atlas.path.stem}_{datetime.now():%Y%m%d_%H%M%S}.png'
        shutil.copy2(atlas.path, backup)
    atlas_image.blit(sprite, spot)
    pygame.image.save(atlas_image, str(atlas.path))
    if started:
        start_overflow(atlas, atlas_image.get_size())

    rect = pygame.Rect(spot, sprite.get_size())
    tiled = domain.tiled_properties(kind, sprite, path)
    if tiled.get('tileset') == kind.atlas.tileset:   # a floor plate, painted from the collection it went into
        tiled['tileset'] = atlas.tileset
    entry = {'kind': kind.key, 'subcategory': subcategory, 'atlas': atlas.key, 'rect': list(rect)}
    if tiled:
        entry['tiled'] = tiled
    catalog.files[catalog.file_key(path)] = entry
    catalog.save()
    return AddedSprite(path, atlas, rect, tiled, backup, started)


def start_overflow(atlas, size, map_file=None):
    """Make a new collection known to Tiled: its .tsx beside the map, and the map's tileset list.

    The tileset is appended after the map's last one, its first gid after
    the highest any tileset uses, so no tile already painted changes. A map
    naming it already is left alone.
    """
    map_file = Path(map_file or MAP_FILE)
    tiled_dir = map_file.parent
    tsx = tiled_dir / f'{atlas.tileset}.tsx'
    columns, rows = size[0] // TILE, size[1] // TILE
    image = Path(os.path.relpath(atlas.path, tiled_dir)).as_posix()
    tsx.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<tileset version="1.10" tiledversion="1.11.2" name="{atlas.tileset}" tilewidth="{TILE}" '
        f'tileheight="{TILE}" tilecount="{columns * rows}" columns="{columns}">\n'
        f' <image source="{image}" width="{size[0]}" height="{size[1]}"/>\n'
        '</tileset>\n', encoding='utf-8')

    with open(map_file, encoding='utf-8', newline='') as file:   # its line endings kept as they are
        text = file.read()
    if f'source="{tsx.name}"' in text:
        return
    tilesets = list(re.finditer(r'<tileset\b[^>]*?/>|<tileset\b[^>]*?[^/]>.*?</tileset>', text, re.DOTALL))
    if not tilesets:
        raise ValueError(f'{map_file.name} has no tilesets to add {tsx.name} after')
    next_gid = max(_tileset_end(m.group(0), tiled_dir) for m in tilesets)
    end = tilesets[-1].end()
    newline = '\r\n' if '\r\n' in text else '\n'
    line = f'{newline} <tileset firstgid="{next_gid}" source="{tsx.name}"/>'
    with open(map_file, 'w', encoding='utf-8', newline='') as file:
        file.write(text[:end] + line + text[end:])


def _tileset_end(tag, tiled_dir):
    """The first gid after a map's tileset: its firstgid plus its tile count (read from its .tsx if external)."""
    first = int(re.search(r'firstgid="(\d+)"', tag).group(1))
    count = re.search(r'tilecount="(\d+)"', tag)
    if count is None:
        source = re.search(r'source="([^"]+)"', tag).group(1)
        count = re.search(r'tilecount="(\d+)"', (tiled_dir / source).read_text(encoding='utf-8'))
    return first + int(count.group(1))
