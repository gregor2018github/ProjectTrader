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
    "scale is its Scale property.sprite_rect and collision_rect are (left, top, right, bottom) "
    "in world pixels, collision_rect from the catalog's Tiled block (trim it to the walls as the "
    "skill says). hint is a first command, not the whole job: doors, lights, smoke, roof and the "
    "note's wishes come on top. Take an entry out of this file once it is on the map (the helper "
    "also drops entries it finds on the map when it starts)."
)
HINT_SCRIPT = 'python .claude/skills/place-building/place_building.py'


class Placement:
    def __init__(self, pid, sprite, x, y, scale=1.0, note=''):
        self.id = pid
        self.sprite = sprite          # the Sprite (map_scene) it shows
        self.x = x
        self.y = y
        self.scale = scale
        self.note = note

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
        return self.sprite.collision(self.x, self.y, self.scale)

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
        placements.append(Placement(int(e['id']), sprite, x, y, scale, e.get('note', '')))
    if done:
        notes.append(f'{done} placement{"s are" if done > 1 else " is"} on the map now and left the list')
    figures = [tuple(f) for f in data.get('figures', [])]
    return placements, figures, data.get('view'), notes
