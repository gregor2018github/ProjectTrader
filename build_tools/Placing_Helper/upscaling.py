"""A sprite upscaled twice by Upscayl, compared with the old one on the map, then accepted or discarded.

Upscayl (https://upscayl.org, installed at UPSCAYL_DIR) upscales on the
graphics card with its command-line `upscayl-bin`. `Upscaler.start()` runs it
on a sprite's PNG in the background, into build_tools/output/upscaled/
(git-ignored); `poll()`, every frame, takes in what has finished. While a
`Candidate` is ready, the scene draws it in the old picture's place
(`Scene.swaps`) at half the scale, so it stands exactly as large; `toggle()`
switches between old and new.

`accept()` puts it in for good, as House_38 and House_40 were by hand (the
place-building skill, step 3): the PNG twice as large and every object
drawn from it at half its `Scale`, so nothing on the map moves or grows.
What the game reads in the PNG's own pixels doubles with it: the collision
box (`Collision_to_right`, `Collision_up`, the `Col_margin_*` and `Col_gap_*`
pixels). Doors, lights, smoke and roofs are in world pixels and stay;
`Tiles_to_right` / `Tiles_up` stay too, as they say which atlas cells show it
in Tiled (the atlas keeps the old picture, the same size on the map). The old
PNG is kept in output/upscaled/replaced/, and the catalog entry gets its
`resolution` (the catalog's numbers are in its atlas pixels; map_scene.Sprite).

Only what honours `Scale` can be upscaled: plain houses, warehouses and
decorations on the Houses layer. The church, town hall, market booths, mill,
well and bank do not pass it on (TMXMap._load_houses), and a gate has an open
picture beside the shut one; trees are not done here yet.
"""

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import pygame

from map_scene import BUILDING_CATALOG, ROOT, TMX, write_tmx

UPSCAYL_DIR = Path(os.environ.get('UPSCAYL_DIR', r'C:\Program Files\Upscayl\resources'))
UPSCAYL_BIN = UPSCAYL_DIR / 'bin' / 'upscayl-bin.exe'
UPSCAYL_MODELS = UPSCAYL_DIR / 'models'
MODEL = 'ultrasharp-4x'          # as House_38 and House_40 were upscaled
FACTOR = 2
WORK_DIR = ROOT / 'build_tools' / 'output' / 'upscaled'
REPLACED_DIR = WORK_DIR / 'replaced'
#: Object properties in the sprite's own pixels (or tiles of them), doubled with it
PIXEL_PROPS = ('Collision_to_right', 'Collision_up', 'Col_margin_left_pixel', 'Col_margin_right_pixel',
               'Col_margin_up_pixel', 'Col_margin_down_pixel', 'Col_gap_left_pixel', 'Col_gap_width_pixel')
#: Names TMXMap._load_houses makes a kind that does not pass Scale on
NO_SCALE_KINDS = (('Church', 'start'), ('Townhall', 'start'), ('Market', 'in'), ('Mill', 'start'),
                  ('Well', 'start'), ('Bank', 'start'))


def ignores_scale(name, obj_type):
    """Why a Houses object of this name and type would not be drawn at its Scale, or None."""
    if obj_type == 'Gate':
        return 'a gate (its open picture would not match)'
    for word, where in NO_SCALE_KINDS:
        if (name.startswith(word) if where == 'start' else word in name):
            return f'a {word.lower()} (the game does not scale it)'
    return None


class Candidate:
    """An upscaled picture of one sprite, on its way or ready."""

    def __init__(self, file_name, old_path, new_path, process):
        self.file_name = file_name
        self.old_path = Path(old_path)
        self.new_path = Path(new_path)
        self.process = process
        self.state = 'running'          # then 'ready' or 'failed'
        self.error = ''
        self.showing_new = True
        self.old_size = self.new_size = (0, 0)
        self.started = time.monotonic()

    @property
    def stem(self):
        return os.path.splitext(self.file_name)[0]


class Upscaler:
    def __init__(self, scene):
        self.scene = scene
        self.candidates = {}            # {file name: Candidate}

    # ----- what may be upscaled

    @staticmethod
    def available():
        return UPSCAYL_BIN.exists() and (UPSCAYL_MODELS / f'{MODEL}.param').exists()

    def refusal(self, file_name, layer):
        """Why this sprite cannot be upscaled here, or None."""
        if not self.available():
            return f'Upscayl is not found at {UPSCAYL_BIN}'
        if layer != 'Houses':
            return 'trees are not upscaled here yet'
        for t in self.scene.things:
            if t.layer == 'Houses' and t.file_name == file_name:
                why = ignores_scale(t.name, t.type)
                if why:
                    return f'{t.label} (id {t.obj_id}) uses it and is {why}'
            if t.props.get('Open_file_name') == file_name:
                return f'it is the open picture of {t.label}'
        return None

    # ----- running Upscayl

    def start(self, file_name, path):
        """Start upscaling a sprite's PNG; the Candidate, running."""
        self.discard(file_name)
        WORK_DIR.mkdir(parents=True, exist_ok=True)
        out = WORK_DIR / f'{os.path.splitext(file_name)[0]}_x{FACTOR}.png'
        out.unlink(missing_ok=True)
        process = subprocess.Popen(
            [str(UPSCAYL_BIN), '-i', str(path), '-o', str(out), '-s', str(FACTOR), '-m', str(UPSCAYL_MODELS),
             '-n', MODEL, '-f', 'png'],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        candidate = self.candidates[file_name] = Candidate(file_name, path, out, process)
        return candidate

    def poll(self):
        """Take in the upscalings that have finished; the candidates that became ready or failed now."""
        done = []
        for c in self.candidates.values():
            if c.state != 'running' or c.process.poll() is None:
                continue
            output = c.process.stdout.read().decode('utf-8', 'replace') if c.process.stdout else ''
            c.process = None
            try:
                self._take_in(c, output)
            except (OSError, ValueError, pygame.error) as error:
                c.state, c.error = 'failed', str(error)
            done.append(c)
        return done

    def _take_in(self, c, output):
        if not c.new_path.exists():
            last = [line for line in output.splitlines() if line.strip()]
            raise ValueError(last[-1] if last else 'Upscayl wrote nothing')
        old = pygame.image.load(str(c.old_path))
        new = pygame.image.load(str(c.new_path)).convert_alpha()
        c.old_size = old.get_size()
        want = (c.old_size[0] * FACTOR, c.old_size[1] * FACTOR)
        if new.get_size() != want:                   # exactly twice, so it stands exactly as large
            new = pygame.transform.smoothscale(new, want)
            pygame.image.save(new, str(c.new_path))
        c.new_size = want
        c.state = 'ready'
        self.show(c, True)

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
        """Put the upscaled picture in for good; [(obj_id, {property: value})] of the map's objects changed.

        The map, the PNG and the catalog are written together, or the PNG is
        put back. Raises OSError or ValueError.
        """
        if c.state != 'ready':
            raise ValueError('the upscaled picture is not ready')
        text = open(TMX, encoding='utf-8', newline='').read()
        text, changed = rescale_objects(text, c.file_name, 1 / FACTOR)
        REPLACED_DIR.mkdir(parents=True, exist_ok=True)
        backup = REPLACED_DIR / f'{c.stem}_{time.strftime("%Y%m%d_%H%M%S")}.png'
        shutil.copy2(c.old_path, backup)
        shutil.copyfile(c.new_path, c.old_path)
        try:
            if changed:
                write_tmx(TMX, text)
        except OSError:
            shutil.copyfile(backup, c.old_path)
            raise
        set_catalog_resolution(f'houses/{c.file_name}', c.new_size, c.old_size)
        self.candidates.pop(c.file_name, None)
        self.scene.swaps.pop(c.old_path, None)
        self.scene.forget_picture(c.old_path)
        self.scene.forget_picture(c.new_path)
        c.new_path.unlink(missing_ok=True)
        return changed, backup


def _number(value):
    return int(value) if re.fullmatch(r'-?\d+', value) else float(value)


def _fmt(value):
    if isinstance(value, int):
        return str(value)
    return f'{round(value, 4):g}'


def rescale_objects(text, file_name, factor):
    """The TMX text with every Houses object drawn from `file_name` at `factor` of its Scale, the
    properties in its own pixels divided by it; and [(obj_id, {property: new value})] of those changed."""
    group = re.search(r'<objectgroup [^>]*name="Houses"[^>]*>.*?</objectgroup>', text, re.S)
    if not group:
        raise ValueError('Map1.tmx has no Houses object layer')
    body = group.group(0)
    changed = []

    def rescale(m):
        xml = m.group(0)
        if not re.search(rf'<property name="File_name" value="{re.escape(file_name)}"/>', xml):
            return xml
        obj_id = int(m.group(1))
        props = {k: v for k, v in re.findall(r'<property name="([^"]+)"[^>]*value="([^"]*)"', xml)}
        new = {'Scale': round(float(props.get('Scale', 1) or 1) * factor, 4)}
        for key in PIXEL_PROPS:
            if key in props:
                value = _number(props[key]) / factor
                new[key] = int(round(value)) if isinstance(_number(props[key]), int) else value
        for key, value in new.items():
            kind = 'int' if isinstance(value, int) else 'float'
            if key in props:
                xml = re.sub(rf'(<property name="{key}"[^>]*value=")[^"]*(")', rf'\g<1>{_fmt(value)}\g<2>', xml, count=1)
            else:
                # A new property (a Scale of 1 is often left out) goes last, indented as the others
                indent = re.search(r'\n([ \t]*)<property ', xml)
                pad = indent.group(1) if indent else '    '
                nl = '\r\n' if '\r\n' in xml else '\n'
                line = f'<property name="{key}" type="{kind}" value="{_fmt(value)}"/>'
                xml = re.sub(r'(\s*)</properties>', lambda pm: f'{nl}{pad}{line}{pm.group(1)}</properties>',
                             xml, count=1)
        changed.append((obj_id, new))
        return xml

    new_body = re.sub(r'<object id="(\d+)"[^>]*>.*?</object>', rescale, body, flags=re.S)
    return text[:group.start()] + new_body + text[group.end():], changed


def set_catalog_resolution(key, new_size, old_size):
    """Note in the building catalog how many PNG pixels now make one of its atlas pixels."""
    if not BUILDING_CATALOG.exists():
        return
    data = json.loads(BUILDING_CATALOG.read_text(encoding='utf-8'))
    entry = data.get('files', {}).get(key)
    if entry is None:
        return
    rect = entry.get('rect')
    before = float(entry.get('resolution', 1) or 1) if not rect else old_size[0] / rect[2]
    entry['resolution'] = round(before * new_size[0] / old_size[0], 2)
    BUILDING_CATALOG.write_text(json.dumps(data, indent=1) + '\n', encoding='utf-8')

