"""The map as the game draws it, and the sprites that can be put on it.

`Scene` loads assets/tiles/Map1.tmx with pytmx: the `Ground*` tile layers
(the only tile layers the game draws), the buildings of the `Houses` object
layer, the trees of `Trees` and the bridges' rectangles. Ground is drawn from
chunks of `CHUNK_TILES` square, made per zoom level as they come into view
(at most `CHUNK_BUDGET_S` of each frame) and kept least-recently-used.
Buildings and trees are y-sorted on their base, as in the game, together
with whatever the caller adds (the placements and the one held on the mouse).

`Sprite` is one picture from assets/map_sprites/houses/ or trees/, with what
the Sprite Manager's catalogs know about it (kind, subcategory, the Tiled
properties it was made with) and how many objects on the map use it.
"""

import json
import math
import os
import re
import time
from collections import OrderedDict
from pathlib import Path

import pygame
import pytmx

ROOT = Path(__file__).resolve().parents[2]
TMX = ROOT / 'assets' / 'tiles' / 'Map1.tmx'
HOUSES_DIR = ROOT / 'assets' / 'map_sprites' / 'houses'
TREES_DIR = ROOT / 'assets' / 'map_sprites' / 'trees'
BUILDING_CATALOG = ROOT / 'build_tools' / 'Sprite_Manager' / 'building_catalog.json'
PLANT_CATALOG = ROOT / 'build_tools' / 'Sprite_Manager' / 'plant_catalog.json'
FIGURE = ROOT / 'assets' / 'map_sprites' / 'figurines' / 'humans' / 'player' / 'player_front_static.png'

TILE = 32
CHUNK_TILES = 16
CHUNK_PX = CHUNK_TILES * TILE
CHUNK_BUDGET_S = 0.025           # of a frame, for making ground chunks
CHUNK_CACHE_PIXELS = 40_000_000  # about 160 MB of ground chunks kept
MISSING_GROUND = (52, 60, 44)    # where a chunk is not made yet
BRIDGE_FILL = (150, 112, 70)
BRIDGE_LINE = (90, 62, 36)
COLLISION_LINE = (240, 240, 240)  # what is on the map; red is kept for overlaps


def boxes_overlap(a, b):
    """Whether two (left, top, right, bottom) boxes overlap; touching edges do not count."""
    return bool(a and b) and a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]

TABS = ('Buildings', 'Decoration', 'Trees')
DECORATION_KINDS = {'decoration', 'wall_fence'}
#: Catalog kinds that are not put on the Houses layer as they are
NOT_PLACEABLE_KINDS = {'reference', 'bridge', 'floor_plate'}
#: Pictures the game loads beside another one, or atlases
NOT_PLACEABLE_FILES = re.compile(r'(_closed|_front)\.png$|^(Houses|Trees)\.png$|^Bridge_')


def natural_key(text):
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r'(\d+)', text)]


class Sprite:
    """A picture that can be placed: a building or decoration (Houses layer) or a tree (Trees layer)."""

    def __init__(self, folder, file_name, entry):
        self.folder = folder                      # 'houses' or 'trees'
        self.file_name = file_name
        self.key = f'{folder}/{file_name}'
        self.path = (HOUSES_DIR if folder == 'houses' else TREES_DIR) / file_name
        self.layer = 'Houses' if folder == 'houses' else 'Trees'
        self.kind = entry.get('kind', '')
        self.subcategory = entry.get('subcategory', '')
        self.tiled = entry.get('tiled')           # the Tiled properties the catalog has, or None
        if folder == 'trees':
            self.tab = 'Trees'
        elif self.kind in DECORATION_KINDS or re.match(r'(Deco|Fence|Wall)_', file_name):
            self.tab = 'Decoration'
        else:
            self.tab = 'Buildings'
        self.on_map = 0                           # objects on the map using it
        self.size = (0, 0)

    @property
    def stem(self):
        return os.path.splitext(self.file_name)[0]

    @property
    def description(self):
        return self.subcategory or self.kind.replace('_', ' ')

    def collision(self, x, y, scale):
        """The collision box (left, top, right, bottom) the game would give it at x, y; None if unknown."""
        if not self.tiled:
            return None
        if self.layer == 'Trees':
            return tree_collision(x, y, scale, self.tiled)
        if 'Collision_to_right' not in self.tiled:
            return None
        return house_collision(x, y, scale, self.tiled)


def house_collision(x, y, scale, props):
    """House.collision_rect, as (left, top, right, bottom)."""
    def g(key):
        return float(props.get(key, 0) or 0) * scale
    w, h = g('Collision_to_right') * TILE, g('Collision_up') * TILE
    left = x - g('Col_margin_left_pixel')
    bottom = y + g('Col_margin_down_pixel')
    return (left, bottom - (h + g('Col_margin_up_pixel') + g('Col_margin_down_pixel')),
            left + w + g('Col_margin_left_pixel') + g('Col_margin_right_pixel'), bottom)


def tree_collision(x, y, scale, props):
    """Tree.collision_rect: the stem, half a tile high."""
    thick = float(props.get('Stem_Thick', 0) or 0) * scale * TILE
    centre = x + float(props.get('Stem_Position', 0) or 0) * scale * TILE
    return centre - thick / 2, y - TILE / 2, centre + thick / 2, y


class Thing:
    """Something on the map drawn from a sprite: a building or a tree."""

    def __init__(self, layer, obj, path):
        self.layer = layer
        self.obj_id = obj.id
        self.name = obj.name or ''
        self.type = getattr(obj, 'type', None) or ''
        self.props = dict(obj.properties or {})
        self.file_name = self.props.get('File_name', '')
        self.path = path
        self.x, self.y = float(obj.x), float(obj.y)
        self.scale = float(self.props.get('Scale', 1.0) or 1.0)
        if layer == 'Trees':
            self.collision = tree_collision(self.x, self.y, self.scale, self.props)
        elif 'Collision_to_right' in self.props:
            self.collision = house_collision(self.x, self.y, self.scale, self.props)
        else:
            self.collision = None


class Scene:
    def __init__(self):
        self.tmx = pytmx.load_pygame(str(TMX))
        self.width = self.tmx.width * TILE
        self.height = self.tmx.height * TILE
        self.ground = [layer for layer in self.tmx.visible_layers
                       if isinstance(layer, pytmx.TiledTileLayer) and layer.name.startswith('Ground')]
        self.chunks = OrderedDict()              # {(zoom, cx, cy): Surface}
        self.chunk_pixels = 0
        self.missing = 0                         # ground chunks the last frame had no time for
        self.sources = {}                        # {path: Surface}
        self.scaled = {}                         # {(path, factor): Surface}
        self.masks = {}                          # {path: Mask} for hit tests
        self.things = []
        self.bridges = []
        self._load_objects()
        self.sprites = self._load_sprites()
        self.figure = pygame.image.load(str(FIGURE)).convert_alpha()

    # ----- loading

    def _load_objects(self):
        for layer in self.tmx.visible_layers:
            if not isinstance(layer, pytmx.TiledObjectGroup):
                continue
            if layer.name in ('Houses', 'Trees'):
                folder = HOUSES_DIR if layer.name == 'Houses' else TREES_DIR
                for obj in layer:
                    file_name = (obj.properties or {}).get('File_name')
                    if file_name and (folder / file_name).exists():
                        self.things.append(Thing(layer.name, obj, folder / file_name))
            elif layer.name == 'Bridges':
                self.bridges += [(o.x, o.y, o.width, o.height) for o in layer]

    def _load_sprites(self):
        sprites = []
        used = {}
        for t in self.things:
            used[(t.layer, t.file_name)] = used.get((t.layer, t.file_name), 0) + 1
        for folder, catalog in (('houses', BUILDING_CATALOG), ('trees', PLANT_CATALOG)):
            entries = json.load(open(catalog, encoding='utf-8'))['files'] if catalog.exists() else {}
            directory = HOUSES_DIR if folder == 'houses' else TREES_DIR
            for path in sorted(directory.glob('*.png'), key=lambda p: natural_key(p.name)):
                entry = entries.get(f'{folder}/{path.name}', {})
                if NOT_PLACEABLE_FILES.search(path.name) or entry.get('kind') in NOT_PLACEABLE_KINDS:
                    continue
                if folder == 'trees' and not path.name.startswith('Tree_'):
                    continue
                sprite = Sprite(folder, path.name, entry)
                sprite.on_map = used.get((sprite.layer, path.name), 0)
                sprite.size = self.source(sprite.path).get_size()
                sprites.append(sprite)
        return sprites

    def sprite(self, key):
        return next((s for s in self.sprites if s.key == key), None)

    # ----- pictures

    def source(self, path):
        image = self.sources.get(path)
        if image is None:
            image = pygame.image.load(str(path)).convert_alpha()
            self.sources[path] = image
        return image

    def image(self, path, factor):
        """The sprite at `factor` of its size (its Scale times the zoom)."""
        factor = round(factor, 4)
        key = (path, factor)
        image = self.scaled.get(key)
        if image is None:
            src = self.source(path)
            size = (max(1, round(src.get_width() * factor)), max(1, round(src.get_height() * factor)))
            image = (pygame.transform.smoothscale(src, size) if factor < 1
                     else pygame.transform.scale(src, size))
            if len(self.scaled) > 4000:
                self.scaled.clear()
            self.scaled[key] = image
        return image

    def opaque_at(self, path, scale, x, y, px, py):
        """Whether the sprite drawn with its bottom-left at x, y covers world point px, py."""
        src = self.source(path)
        sx = (px - x) / scale
        sy = src.get_height() + (py - y) / scale
        if not (0 <= sx < src.get_width() and 0 <= sy < src.get_height()):
            return False
        mask = self.masks.get(path)
        if mask is None:
            mask = self.masks[path] = pygame.mask.from_surface(src, 40)
        return bool(mask.get_at((int(sx), int(sy))))

    def thing_at(self, px, py):
        """The building or tree drawn frontmost at world point px, py."""
        hits = []
        for t in self.things:
            w, h = self.source(t.path).get_size()
            if t.x <= px <= t.x + w * t.scale and t.y - h * t.scale <= py <= t.y:
                if self.opaque_at(t.path, t.scale, t.x, t.y, px, py):
                    hits.append(t)
        return max(hits, key=lambda t: t.y) if hits else None

    # ----- ground

    def _make_chunk(self, zoom, cx, cy):
        surface = pygame.Surface((CHUNK_PX, CHUNK_PX))
        surface.fill(MISSING_GROUND)
        images = self.tmx.images
        x0, y0 = cx * CHUNK_TILES, cy * CHUNK_TILES
        for layer in self.ground:
            data = layer.data
            for ty in range(y0, min(y0 + CHUNK_TILES, self.tmx.height)):
                row = data[ty]
                for tx in range(x0, min(x0 + CHUNK_TILES, self.tmx.width)):
                    gid = row[tx]
                    if gid:
                        image = images[gid]
                        if image is not None:
                            surface.blit(image, ((tx - x0) * TILE, (ty - y0) * TILE))
        size = round(CHUNK_PX * zoom)
        if zoom < 1:
            surface = pygame.transform.smoothscale(surface, (size, size))
        elif zoom > 1:
            surface = pygame.transform.scale(surface, (size, size))
        self.chunks[(zoom, cx, cy)] = surface
        self.chunk_pixels += size * size
        while self.chunk_pixels > CHUNK_CACHE_PIXELS and len(self.chunks) > 1:
            _, old = self.chunks.popitem(last=False)
            self.chunk_pixels -= old.get_width() * old.get_height()
        return surface

    # ----- drawing

    def draw(self, screen, area, cam_x, cam_y, zoom, extra=(), show_collision=False):
        """Draw the map into `area` (a screen rect) seen from cam_x, cam_y at `zoom`.

        `extra` are further (base_y, draw_function) pairs y-sorted in with the
        buildings and trees; each function gets (screen, ox, oy, zoom), the
        screen position of the world's origin.
        """
        screen.set_clip(area)
        screen.fill(MISSING_GROUND, area)
        ox = area.x - round(cam_x * zoom)
        oy = area.y - round(cam_y * zoom)
        view = (cam_x, cam_y, cam_x + area.w / zoom, cam_y + area.h / zoom)

        size = round(CHUNK_PX * zoom)
        deadline = time.perf_counter() + CHUNK_BUDGET_S
        missing = 0
        for cy in range(max(0, int(view[1] // CHUNK_PX)), min(math.ceil(self.height / CHUNK_PX), int(view[3] // CHUNK_PX) + 1)):
            for cx in range(max(0, int(view[0] // CHUNK_PX)), min(math.ceil(self.width / CHUNK_PX), int(view[2] // CHUNK_PX) + 1)):
                key = (zoom, cx, cy)
                chunk = self.chunks.get(key)
                if chunk is not None:
                    self.chunks.move_to_end(key)
                elif time.perf_counter() < deadline:
                    chunk = self._make_chunk(zoom, cx, cy)
                else:
                    missing += 1
                    continue
                screen.blit(chunk, (ox + cx * size, oy + cy * size))
        self.missing = missing

        for bx, by, bw, bh in self.bridges:
            rect = pygame.Rect(ox + round(bx * zoom), oy + round(by * zoom), max(1, round(bw * zoom)), max(1, round(bh * zoom)))
            if rect.colliderect(area):
                pygame.draw.rect(screen, BRIDGE_FILL, rect)
                pygame.draw.rect(screen, BRIDGE_LINE, rect, max(1, round(2 * zoom)))

        queue = []
        for t in self.things:
            w, h = self.source(t.path).get_size()
            if t.x + w * t.scale < view[0] or t.x > view[2] or t.y < view[1] or t.y - h * t.scale > view[3]:
                continue
            queue.append((t.y, 0, t))
        queue += [(base, 1, fn) for base, fn in extra]
        queue.sort(key=lambda item: (item[0], item[1]))
        for _, is_extra, item in queue:
            if is_extra:
                item(screen, ox, oy, zoom)
            else:
                image = self.image(item.path, item.scale * zoom)
                screen.blit(image, (ox + round(item.x * zoom), oy + round(item.y * zoom) - image.get_height()))
        if show_collision:
            for t in self.things:
                if t.collision and view[0] - 64 < t.collision[0] < view[2] and view[1] - 64 < t.collision[1] < view[3]:
                    draw_box(screen, t.collision, ox, oy, zoom, COLLISION_LINE)
        screen.set_clip(None)
        return ox, oy

    def draw_figure(self, screen, ox, oy, zoom, x, y):
        """The player standing with his feet at world x, y, at the game's size (a tile wide)."""
        w = TILE * zoom
        h = w * self.figure.get_height() / self.figure.get_width()
        image = self.image(FIGURE, w / self.figure.get_width())
        screen.blit(image, (ox + round(x * zoom - w / 2), oy + round(y * zoom - h)))


def draw_box(screen, box, ox, oy, zoom, colour, width=1):
    left, top, right, bottom = box
    rect = pygame.Rect(ox + round(left * zoom), oy + round(top * zoom),
                       max(1, round((right - left) * zoom)), max(1, round((bottom - top) * zoom)))
    pygame.draw.rect(screen, colour, rect, width)
