"""A sprite upscaled twice by Upscayl, compared with the old one on the map, then accepted or discarded.

Upscayl (https://upscayl.org, installed at UPSCAYL_DIR) upscales on the
graphics card with its command-line `upscayl-bin`. `Upscaler.start()` works
out what has to be upscaled with the chosen sprite (`plan()`) and runs it on
each of those PNGs in turn, in the background, into build_tools/output/upscaled/
(git-ignored); `poll()`, every frame, takes in what has finished. While a
`Candidate` is ready, the scene draws its main picture in the old one's place
(`Scene.swaps`) at half the scale, so it stands exactly as large; `toggle()`
switches between old and new.

`accept()` puts it in for good, as House_38 and House_40 were by hand (the
place-building skill, step 3): every picture twice as large and every object
drawn from it at half its `Scale`, so nothing on the map moves or grows.
What the game reads in the PNG's own pixels doubles with it: a building's
collision box (`Collision_to_right`, `Collision_up`, the `Col_margin_*` and
`Col_gap_*` pixels), a tree's stem (`Stem_Position`, `Stem_Thick`). Doors,
lights, smoke and roofs are in world pixels and stay; `Tiles_to_right` /
`Tiles_up` stay too, as they say which atlas cells show it in Tiled (the atlas
keeps the old picture, the same size on the map). The old PNGs are kept in
output/upscaled/replaced/, and the catalog entries get their `resolution`
(the catalog's numbers are in its atlas pixels; map_scene.Sprite).

Every kind draws all its pictures at its `Scale` (TMXMap._load_houses,
House._load_picture), and what goes with a picture is upscaled with it:
  - a market booth's closed picture, `<name>_closed.png`;
  - a gate's open pictures (`Open_file_name` of every gate drawn from it);
  - a mill's turning blades, `Mill_Blades.png`, whose `Mill_Blades` point on
    the Special layer gets half its `Scale` too (Mill.blade_scale);
  - a tree: only itself, on the Trees layer.
"""

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import pygame

from map_scene import BUILDING_CATALOG, HOUSES_DIR, PLANT_CATALOG, ROOT, TMX, TREES_DIR, write_tmx

UPSCAYL_DIR = Path(os.environ.get('UPSCAYL_DIR', r'C:\Program Files\Upscayl\resources'))
UPSCAYL_BIN = UPSCAYL_DIR / 'bin' / 'upscayl-bin.exe'
UPSCAYL_MODELS = UPSCAYL_DIR / 'models'
MODEL = 'ultrasharp-4x'          # as House_38 and House_40 were upscaled
FACTOR = 2
WORK_DIR = ROOT / 'build_tools' / 'output' / 'upscaled'
REPLACED_DIR = WORK_DIR / 'replaced'
#: Object properties in the sprite's own pixels (or tiles of them), doubled with it, per layer
PIXEL_PROPS = {
    'Houses': ('Collision_to_right', 'Collision_up', 'Col_margin_left_pixel', 'Col_margin_right_pixel',
               'Col_margin_up_pixel', 'Col_margin_down_pixel', 'Col_gap_left_pixel', 'Col_gap_width_pixel'),
    'Trees': ('Stem_Position', 'Stem_Thick'),
}
MILL_BLADES = 'Mill_Blades.png'  # Mill._load_blade_image; its point on Special is named "Mill_Blades"


class Plan:
    """What upscaling one sprite takes: its pictures and the objects drawn from them."""

    def __init__(self, layer, main, folder, catalog):
        self.layer = layer                # 'Houses' or 'Trees'
        self.main = main                  # the chosen sprite's file name, relative to `folder`
        self.folder = folder
        self.catalog = catalog
        self.parts = [main]               # the pictures, main first; companions after it
        self.mill_blades = False          # also halve the Scale of the Mill_Blades point
        self.problem = None               # why it cannot be done, or None

    def path(self, part):
        return self.folder / part

    @property
    def companions(self):
        return self.parts[1:]


def plan(text, file_name, layer):
    """What upscaling a sprite takes, read off the map's text (Map1.tmx)."""
    if layer == 'Trees':
        return Plan('Trees', file_name, TREES_DIR, PLANT_CATALOG)
    p = Plan('Houses', file_name, HOUSES_DIR, BUILDING_CATALOG)
    objects = _objects(text, 'Houses')
    users = [o for o in objects if o['props'].get('File_name') == file_name]
    closed = f'{os.path.splitext(file_name)[0]}_closed.png'
    if (HOUSES_DIR / closed).exists():
        p.parts.append(closed)
    for o in users:
        opened = o['props'].get('Open_file_name')
        if opened and opened not in p.parts:
            p.parts.append(opened)
        if o['name'].startswith('Mill') and MILL_BLADES not in p.parts and (HOUSES_DIR / MILL_BLADES).exists():
            p.parts.append(MILL_BLADES)
            p.mill_blades = True
    # A companion must go with this sprite only, or the other object drawn from it would grow
    for o in objects:
        if o['props'].get('File_name') == file_name:
            continue
        shared = {o['props'].get('File_name'), o['props'].get('Open_file_name')} & set(p.parts)
        if shared:
            p.problem = f'{", ".join(sorted(shared))} is drawn for {o["name"] or o["id"]} too, with another sprite'
        if p.mill_blades and o['name'].startswith('Mill'):
            p.problem = f'{MILL_BLADES} turns on {o["name"]} too, which is drawn from another sprite'
    for part in p.parts:
        if not p.path(part).exists():
            p.problem = f'{part} is missing'
    return p


def _objects(text, group_name):
    """[{'id', 'name', 'props', 'span'}] of an object layer's objects, as text."""
    group = re.search(rf'<objectgroup [^>]*name="{re.escape(group_name)}"[^>]*>.*?</objectgroup>', text, re.S)
    if not group:
        return []
    found = []
    for m in re.finditer(r'<object id="(\d+)"(?: name="([^"]*)")?[^>]*?(?:/>|>.*?</object>)', group.group(0), re.S):
        props = dict(re.findall(r'<property name="([^"]+)"[^>]*value="([^"]*)"', m.group(0)))
        found.append({'id': int(m.group(1)), 'name': m.group(2) or '', 'props': props})
    return found


class Candidate:
    """A sprite's pictures upscaled, on their way or ready."""

    def __init__(self, plan_):
        self.plan = plan_
        self.file_name = plan_.main
        self.old_path = plan_.path(plan_.main)
        self.new_paths = {part: WORK_DIR / f'{os.path.splitext(part.replace("/", "__"))[0]}_x{FACTOR}.png'
                          for part in plan_.parts}
        self.new_path = self.new_paths[plan_.main]
        self.queue = list(plan_.parts)    # still to upscale, the one running first
        self.process = None
        self.state = 'running'            # then 'ready' or 'failed'
        self.error = ''
        self.showing_new = True
        self.old_size = self.new_size = (0, 0)
        self.started = time.monotonic()

    @property
    def stem(self):
        return os.path.splitext(os.path.basename(self.file_name))[0]

    @property
    def running_part(self):
        return self.queue[0] if self.queue else None


class Upscaler:
    def __init__(self, scene):
        self.scene = scene
        self.candidates = {}              # {file name: Candidate}
        self._plans = {}                  # {(file name, layer): Plan}, until the map is written

    def forget_plans(self):
        """The map was written: work out again what each sprite takes."""
        self._plans.clear()

    # ----- what may be upscaled

    @staticmethod
    def available():
        return UPSCAYL_BIN.exists() and (UPSCAYL_MODELS / f'{MODEL}.param').exists()

    def plan(self, file_name, layer):
        """What upscaling this sprite takes (Plan), with its `problem` if it cannot be done (kept: the
        panel asks every frame)."""
        key = (file_name, layer)
        if key not in self._plans:
            p = plan(open(TMX, encoding='utf-8', newline='').read(), file_name, layer)
            if not self.available():
                p.problem = f'Upscayl is not found at {UPSCAYL_BIN}'
            self._plans[key] = p
        return self._plans[key]

    # ----- running Upscayl, a picture at a time

    def start(self, file_name, layer):
        """Start upscaling a sprite and what goes with it; the Candidate. Raises ValueError for a Plan's problem."""
        self._plans.pop((file_name, layer), None)          # read the map afresh for the real thing
        p = self.plan(file_name, layer)
        if p.problem:
            raise ValueError(p.problem)
        self.discard(file_name)
        WORK_DIR.mkdir(parents=True, exist_ok=True)
        c = self.candidates[file_name] = Candidate(p)
        for path in c.new_paths.values():
            path.unlink(missing_ok=True)
        self._run_next(c)
        return c

    def _run_next(self, c):
        part = c.running_part
        c.process = subprocess.Popen(
            [str(UPSCAYL_BIN), '-i', str(c.plan.path(part)), '-o', str(c.new_paths[part]), '-s', str(FACTOR),
             '-m', str(UPSCAYL_MODELS), '-n', MODEL, '-f', 'png'],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))

    def poll(self):
        """Take in the upscalings that have finished; the candidates that became ready or failed now."""
        done = []
        for c in self.candidates.values():
            if c.state != 'running' or c.process is None or c.process.poll() is None:
                continue
            output = c.process.stdout.read().decode('utf-8', 'replace') if c.process.stdout else ''
            c.process = None
            part = c.queue.pop(0)
            try:
                self._take_in(c, part, output)
            except (OSError, ValueError, pygame.error) as error:
                c.state, c.error = 'failed', f'{part}: {error}'
                done.append(c)
                continue
            if c.queue:
                self._run_next(c)
            else:
                c.state = 'ready'
                self.show(c, True)
                done.append(c)
        return done

    def _take_in(self, c, part, output):
        new_path = c.new_paths[part]
        if not new_path.exists():
            last = [line for line in output.splitlines() if line.strip()]
            raise ValueError(last[-1] if last else 'Upscayl wrote nothing')
        old_size = pygame.image.load(str(c.plan.path(part))).get_size()
        new = pygame.image.load(str(new_path)).convert_alpha()
        want = (old_size[0] * FACTOR, old_size[1] * FACTOR)
        if new.get_size() != want:                   # exactly twice, so it stands exactly as large
            new = pygame.transform.smoothscale(new, want)
            pygame.image.save(new, str(new_path))
        if part == c.plan.main:
            c.old_size, c.new_size = old_size, want

    # ----- comparing

    def show(self, c, new):
        c.showing_new = new
        self.scene.forget_picture(c.new_path)
        if new and c.state == 'ready':
            self.scene.swaps[c.old_path] = (c.new_path, FACTOR)
        else:
            self.scene.swaps.pop(c.old_path, None)

    def toggle(self, c):
        self.show(c, not c.showing_new)

    def discard(self, file_name):
        c = self.candidates.pop(file_name, None)
        if c is None:
            return
        if c.process is not None and c.process.poll() is None:
            c.process.kill()
        self.scene.swaps.pop(c.old_path, None)
        self.scene.forget_picture(c.new_path)

    def discard_all(self):
        for name in list(self.candidates):
            self.discard(name)

    # ----- accepting

    def accept(self, c):
        """Put the upscaled pictures in for good.

        Returns ({obj_id: {property: value}} of the map's objects changed, the
        backups). The map, the PNGs and the catalog are written together, or
        the PNGs are put back. Raises OSError or ValueError.
        """
        if c.state != 'ready':
            raise ValueError('the upscaled pictures are not ready')
        p = c.plan
        text = open(TMX, encoding='utf-8', newline='').read()
        if plan(text, p.main, p.layer).parts != p.parts:
            raise ValueError('the map changed meanwhile: upscale it again')
        text, changed = rescale_objects(text, p.layer, lambda props: props.get('File_name') == p.main,
                                        1 / FACTOR, PIXEL_PROPS[p.layer])
        if p.mill_blades:
            text, _ = rescale_objects(text, 'Special', lambda props, name='': True, 1 / FACTOR, (),
                                      name='Mill_Blades')
        REPLACED_DIR.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime('%Y%m%d_%H%M%S')
        backups = {}
        for part in p.parts:
            backup = REPLACED_DIR / f'{os.path.splitext(part.replace("/", "__"))[0]}_{stamp}.png'
            shutil.copy2(p.path(part), backup)
            backups[part] = backup
        try:
            for part in p.parts:
                shutil.copyfile(c.new_paths[part], p.path(part))
            if changed:
                write_tmx(TMX, text)
        except OSError:
            for part, backup in backups.items():
                shutil.copyfile(backup, p.path(part))
            raise
        for part in p.parts:
            set_catalog_resolution(p.catalog, f'{p.folder.name}/{part}', FACTOR)
            self.scene.forget_picture(p.path(part))
            self.scene.forget_picture(c.new_paths[part])
            c.new_paths[part].unlink(missing_ok=True)
        self.candidates.pop(c.file_name, None)
        self.scene.swaps.pop(c.old_path, None)
        self.forget_plans()
        return dict(changed), backups


def _number(value):
    return int(value) if re.fullmatch(r'-?\d+', value) else float(value)


def _fmt(value):
    if isinstance(value, int):
        return str(value)
    return f'{round(value, 4):g}'


def rescale_objects(text, group_name, matches, factor, pixel_props, name=None):
    """The TMX text with the objects of a layer that `matches` (their properties; and `name`, if
    given) at `factor` of their Scale, `pixel_props` divided by it; and [(obj_id, {property: value})]."""
    group = re.search(rf'<objectgroup [^>]*name="{re.escape(group_name)}"[^>]*>.*?</objectgroup>', text, re.S)
    if not group:
        raise ValueError(f'Map1.tmx has no {group_name} object layer')
    changed = []

    def rescale(m):
        xml = m.group(0)
        props = dict(re.findall(r'<property name="([^"]+)"[^>]*value="([^"]*)"', xml))
        if (name is not None and m.group(2) != name) or not matches(props):
            return xml
        new = {'Scale': round(float(props.get('Scale', 1) or 1) * factor, 4)}
        for key in pixel_props:
            if key in props:
                old = _number(props[key])
                new[key] = int(round(old / factor)) if isinstance(old, int) else round(old / factor, 4)
        for key, value in new.items():
            if key in props:
                xml = re.sub(rf'(<property name="{key}"[^>]*value=")[^"]*(")', rf'\g<1>{_fmt(value)}\g<2>',
                             xml, count=1)
            else:
                xml = _add_property(xml, key, value)
        changed.append((int(m.group(1)), new))
        return xml

    body = re.sub(r'<object id="(\d+)"(?: name="([^"]*)")?[^>]*>.*?</object>', rescale, group.group(0), flags=re.S)
    return text[:group.start()] + body + text[group.end():], changed


def _add_property(xml, key, value):
    """An object's XML with a property more (a Scale of 1 is often left out), indented as the others."""
    nl = '\r\n' if '\r\n' in xml else '\n'
    kind = 'int' if isinstance(value, int) else 'float'
    line = f'<property name="{key}" type="{kind}" value="{_fmt(value)}"/>'
    if '</properties>' in xml:
        pad = (re.search(r'\n([ \t]*)<property ', xml) or re.search(r'\n([ \t]*)</properties>', xml)).group(1)
        if not re.search(r'\n[ \t]*<property ', xml):
            pad += ' '
        return re.sub(r'(\s*)</properties>', lambda pm: f'{nl}{pad}{line}{pm.group(1)}</properties>', xml, count=1)
    # No properties yet: a block before its shape (or end)
    indent = re.search(r'\n([ \t]*)<', xml)
    pad = indent.group(1) if indent else '   '
    head = re.match(r'<object [^>]*>', xml).group(0)
    return head + f'{nl}{pad}<properties>{nl}{pad} {line}{nl}{pad}</properties>' + xml[len(head):]


def set_catalog_resolution(catalog, key, factor):
    """Note in a catalog that its sprite's PNG is `factor` times larger than before (its "resolution")."""
    if not catalog.exists():
        return
    data = json.loads(catalog.read_text(encoding='utf-8'))
    entry = data.get('files', {}).get(key)
    if entry is None:
        return
    rect = entry.get('rect')
    path = (HOUSES_DIR if key.startswith('houses/') else TREES_DIR) / key.split('/', 1)[1]
    if rect and rect[2]:
        entry['resolution'] = round(pygame.image.load(str(path)).get_width() / rect[2], 2)
    else:
        entry['resolution'] = round(float(entry.get('resolution', 1) or 1) * factor, 2)
    catalog.write_text(json.dumps(data, indent=1) + '\n', encoding='utf-8')
