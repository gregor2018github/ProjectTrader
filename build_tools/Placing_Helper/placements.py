"""The placements and the file they are handed over in, placements.json beside this file.

The file is read back by the Placing Helper when it starts and by whoever
puts the placements into Map1.tmx (the place-building skill). Each entry
says where a sprite goes and at what size, in the coordinates of the Tiled
object it becomes, plus what follows from that (its drawn box, its collision
box by the catalog, what it overlaps) and a first command line for
.claude/skills/place-building/place_building.py. Only `id`, `sprite`, `x`,
`y`, `scale` and `note` are read back; the rest is worked out again on
every save.
"""

import json
import time

from map_scene import TILE

FORMAT = 1
ABOUT = (
    "Placements made in build_tools/Placing_Helper/Placing_Helper.py, waiting to be put into "
    "assets/tiles/Map1.tmx with the place-building skill. x, y is the Tiled object's point: the "
    "bottom-left corner of the sprite, in world pixels, already snapped where on_grid is true; "
    "scale is its Scale property. sprite_rect and collision_rect are (left, top, right, bottom) "
    "in world pixels. collision_props are the Tiled properties giving that collision box: when "
    "collision_edited is true the user drew the box, so use them as they are; otherwise they are "
    "the catalog's (trim them to the walls as the skill says). hint is a first command, not the whole job: doors, lights, smoke, roof and the "
    "note's wishes come on top. Take an entry out of this file once it is on the map (the helper "
    "also drops entries it finds on the map when it starts)."
)
HINT_SCRIPT = 'python .claude/skills/place-building/place_building.py'


COLLISION_PROPS = ('Collision_to_right', 'Collision_up', 'Col_margin_left_pixel',
                   'Col_margin_right_pixel', 'Col_margin_up_pixel', 'Col_margin_down_pixel')


def catalog_box(sprite):
    """A Houses-layer sprite's collision box by the catalog, in sprite pixels from the object point.

    (left, top, right, bottom), x to the right and y down from the sprite's
    bottom-left corner, before Scale (House.collision_rect read backwards).
    Without a catalog block: the sprite's width, one tile high.
    """
    t = sprite.tiled or {}
    if 'Collision_to_right' not in t:
        return 0, -TILE, sprite.size[0], 0

    def g(key):
        return float(t.get(key, 0) or 0)
    return (-g('Col_margin_left_pixel'), -(g('Collision_up') * TILE + g('Col_margin_up_pixel')),
            g('Collision_to_right') * TILE + g('Col_margin_right_pixel'), g('Col_margin_down_pixel'))


class Placement:
    def __init__(self, pid, sprite, x, y, scale=1.0, note='', collision_box=None):
        self.id = pid
        self.sprite = sprite          # the Sprite (map_scene) it shows
        self.x = x
        self.y = y
        self.scale = scale
        self.note = note
        #: The collision box set by hand, in sprite pixels like catalog_box(); None: the catalog's
        self.collision_box = collision_box

    @property
    def box_px(self):
        """The collision box in sprite pixels from the object point (Houses layer only)."""
        return self.collision_box or catalog_box(self.sprite)

    def collision_props(self):
        """The Tiled properties giving box_px: the catalog's tile counts, the margins making up the rest."""
        t = self.sprite.tiled or {}
        left, top, right, bottom = self.box_px
        across = int(t.get('Collision_to_right') or max(1, round(self.sprite.size[0] / TILE)))
        up = int(t.get('Collision_up') or 1)
        return {'Collision_to_right': across, 'Collision_up': up,
                'Col_margin_left_pixel': round(-left), 'Col_margin_right_pixel': round(right - across * TILE),
                'Col_margin_up_pixel': round(-top - up * TILE), 'Col_margin_down_pixel': round(bottom)}

    @property
    def size(self):
        w, h = self.sprite.size
        return w * self.scale, h * self.scale

    @property
    def rect(self):
        """(left, top, right, bottom) of the drawn sprite in world pixels."""
        w, h = self.size
        return self.x, self.y - h, self.x + w, self.y

    @property
    def on_grid(self):
        return self.x % TILE == 0 and self.y % TILE == 0

    @property
    def collision(self):
        """The collision box (left, top, right, bottom) in world pixels."""
        if self.sprite.layer == 'Trees':
            return self.sprite.collision(self.x, self.y, self.scale)
        left, top, right, bottom = self.box_px
        s = self.scale
        return self.x + left * s, self.y + top * s, self.x + right * s, self.y + bottom * s

    def hint(self):
        s = self.sprite
        x, y = f'{self.x:g}', f'{self.y:g}'
        if s.layer == 'Trees':
            line = f'{HINT_SCRIPT} tree {s.file_name} {x} {y}'
            if self.scale != 1:
                line += f' --scale {self.scale:g}'
        else:
            line = f'{HINT_SCRIPT} place {s.file_name} {x} {y}'
            if self.scale != 1:
                line += f' --prop Scale={self.scale:g}'
            if self.collision_box:
                line += ''.join(f' --prop {k}={v}' for k, v in self.collision_props().items())
        if not self.on_grid:
            line += ' --no-snap'
        return line


def _overlaps(box, others):
    if not box:
        return []
    left, top, right, bottom = box
    return [name for name, other in others
            if other and left < other[2] and other[0] < right and top < other[3] and other[1] < bottom]


def _rounded(box):
    return [round(v, 2) for v in box] if box else None


def entry(p, scene, placements):
    s = p.sprite
    checks = []
    if s.layer == 'Houses' and not s.tiled:
        checks.append('no Tiled properties in building_catalog.json: work out Tiles_to_right, Tiles_up '
                      'and the collision box from the sprite first')
    if not p.on_grid:
        checks.append('off the tile grid: --no-snap, ' + (
            'and Tiled will not show it (no preview tiles)' if s.layer == 'Trees'
            else 'and Tiled shows it from an image-layer preview'))
    if p.scale != 1 and s.layer == 'Houses':
        checks.append('scaled: check the door against a figure (the skill, step 3)')
    if p.collision_box and s.layer == 'Houses':
        checks.append('collision box set by hand: use collision_props as they are (no trimming, step 4)')
    box = p.collision
    on_map = _overlaps(box, [(f'{t.name or t.file_name} (id {t.obj_id})', t.collision) for t in scene.things])
    pending = _overlaps(box, [(f'placement {o.id} ({o.sprite.stem})', o.collision) for o in placements if o is not p])
    if on_map or pending:
        checks.append('collision overlaps ' + ', '.join(on_map + pending))
    return {
        'id': p.id,
        'sprite': s.key,
        'file_name': s.file_name,
        'object_layer': s.layer,
        'kind': s.kind,
        'subcategory': s.subcategory,
        'x': round(p.x, 2),
        'y': round(p.y, 2),
        'tile': [int(p.x // TILE), int(p.y // TILE)],
        'on_grid': p.on_grid,
        'scale': round(p.scale, 4),
        'png_size': list(s.size),
        'drawn_size': [round(v, 1) for v in p.size],
        'sprite_rect': _rounded(p.rect),
        'collision_rect': _rounded(box),
        'collision_edited': bool(p.collision_box) and s.layer == 'Houses',
        'collision_box_px': _rounded(p.box_px) if s.layer == 'Houses' else None,
        'collision_props': p.collision_props() if s.layer == 'Houses' else None,
        'catalog_tiled': s.tiled,
        'note': p.note,
        'checks': checks,
        'hint': p.hint(),
    }


def save(path, scene, placements, figures, view):
    data = {
        'about': ABOUT,
        'format': FORMAT,
        'saved': time.strftime('%Y-%m-%d %H:%M:%S'),
        'map': 'assets/tiles/Map1.tmx',
        'placements': [entry(p, scene, placements) for p in placements],
        'figures': [[round(x), round(y)] for x, y in figures],
        'view': view,
    }
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    tmp.replace(path)


def load(path, scene):
    """(placements, figures, view, notes) from the file; notes say what was dropped and why."""
    if not path.exists():
        return [], [], None, []
    data = json.loads(path.read_text(encoding='utf-8'))
    placements, notes, done = [], [], 0
    for e in data.get('placements', []):
        sprite = scene.sprite(e['sprite'])
        if sprite is None:
            notes.append(f'{e["sprite"]} is gone, its placement {e["id"]} was dropped')
            continue
        x, y, scale = float(e['x']), float(e['y']), float(e.get('scale', 1))
        if any(t.file_name == sprite.file_name and t.layer == sprite.layer and abs(t.x - x) < 1
               and abs(t.y - y) < 1 and abs(t.scale - scale) < 1e-3 for t in scene.things):
            done += 1
            continue
        box = tuple(e['collision_box_px']) if e.get('collision_edited') and e.get('collision_box_px') else None
        placements.append(Placement(int(e['id']), sprite, x, y, scale, e.get('note', ''), box))
    if done:
        notes.append(f'{done} placement{"s are" if done > 1 else " is"} on the map now and left the list')
    figures = [tuple(f) for f in data.get('figures', [])]
    return placements, figures, data.get('view'), notes
