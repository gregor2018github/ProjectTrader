"""Buildings and decorations already on the map, moved with what belongs to them until written into Map1.tmx.

A building on the `Houses` layer brings along what the game ties to it by
place or by name: its doors (points on `Doors` inside its collision box), its
window lights (the rectangles the game hands to it, and the shaped windows
named after it), its chimney smoke (`Smoke_<name>`), its roofs and holes, and
its preview in Tiled (tile cells on a `Houses N` layer, or an image layer).
Which they are is worked out once, when it is first chosen, by the
place-building skill's own rules (`place_building.attachments`, `_roofs_of`),
so the helper shows and writes exactly what `place_building.py move` would.

While it is moved, its window lights and roofs move in the scene and in the
light and roof edits (`LightEdits.shift`, `RoofEdits.shift`: a light changed
by hand stays changed, and its change moves along); the doors and smoke are
only drawn. `save()` writes every move with `place_building.move_object`, and
must come before the light and roof edits are written, which put the lights
and roofs changed by hand where they are now, absolutely. Paths on the
`Movements` layer, painted ground and fields stay where they are.
"""

import contextlib
import os
import re
import sys

from map_scene import ROOT, TMX, write_tmx

sys.path.insert(0, str(ROOT / '.claude' / 'skills' / 'place-building'))
import place_building  # noqa: E402

DOOR_FACINGS = ('down', 'up', 'left', 'right')


@contextlib.contextmanager
def _at_root():
    """place_building works with paths from the repo root."""
    before = os.getcwd()
    os.chdir(ROOT)
    try:
        yield
    finally:
        os.chdir(before)


def _attr(tag, key, default=0.0):
    m = re.search(rf' {key}="([^"]*)"', tag)
    return float(m.group(1)) if m else default


class Move:
    """One building being moved: where it stands in the file, and what moves with it."""

    def __init__(self, thing, ids, doors, smoke, lights, rings):
        self.thing = thing
        self.x0, self.y0 = thing.x, thing.y   # its place in Map1.tmx
        self.ids = ids                        # object ids of all that moves with it, for writing
        self.doors = doors                    # [(x, y, facing)] where they are in the file
        self.smoke = smoke                    # [(x, y, width, height)] likewise
        self.lights = lights                  # the scene's Light objects
        self.rings = rings                    # the roof edits' Rings

    @property
    def offset(self):
        return self.thing.x - self.x0, self.thing.y - self.y0

    @property
    def moved(self):
        dx, dy = self.offset
        return abs(dx) > 1e-6 or abs(dy) > 1e-6

    def summary(self):
        """What moves with it, in words: "1 door, 7 window lights, 1 smoke outlet, 2 roofs"."""
        holes = sum(1 for r in self.rings if r.hole)
        parts = [(len(self.doors), 'door'), (len(self.lights), 'window light'),
                 (len(self.smoke), 'smoke outlet'), (len(self.rings) - holes, 'roof'), (holes, 'roof hole')]
        return ', '.join(f'{n} {word}{"s" if n != 1 else ""}' for n, word in parts if n) or 'nothing else'


class ObjectMoves:
    def __init__(self, scene, light_edits, roof_edits, tmx_path=TMX):
        self.scene = scene
        self.light_edits = light_edits
        self.roof_edits = roof_edits
        self.tmx_path = tmx_path
        self.moves = {}        # {obj_id: Move}, every building chosen since the last save
        self._text = None      # Map1.tmx as last read

    def _file_text(self):
        if self._text is None:
            self._text = open(self.tmx_path, encoding='utf-8', newline='').read()
        return self._text

    def forget(self):
        """The map was written: read it again, and work out what belongs to each building again."""
        self._text = None
        self.moves = {n: m for n, m in self.moves.items() if m.moved}

    # ----- what belongs to a building

    def record(self, thing):
        """The Move of a building, worked out from the file when it is first asked for."""
        move = self.moves.get(thing.obj_id)
        if move is not None:
            return move
        text = self._file_text()
        with _at_root():
            found = place_building.attachments(text, thing.obj_id)
            found += [('Roofs', xml) for xml in place_building._roofs_of(text, thing.obj_id)]
        ids, doors, smoke, light_ids, ring_ids = [], [], [], set(), set()
        for group, xml in found:
            obj_id = int(re.search(r'id="(\d+)"', xml).group(1))
            ids.append(obj_id)
            if group == 'Doors':
                facing = re.search(r'name="([^"]*)"', xml).group(1)
                doors.append((_attr(xml, 'x'), _attr(xml, 'y'), facing))
            elif group == 'Smoke':
                smoke.append((_attr(xml, 'x'), _attr(xml, 'y'), _attr(xml, 'width'), _attr(xml, 'height')))
            elif group == 'Lights':
                light_ids.add(obj_id)
            else:
                ring_ids.add(obj_id)
        lights = [light for light in self.scene.all_lights() if light.obj_id in light_ids]
        rings = [r for r in self.roof_edits.rings if r.obj_id in ring_ids]
        move = self.moves[thing.obj_id] = Move(thing, ids, doors, smoke, lights, rings)
        return move

    def doors(self, move):
        """(x, y, facing) of its doors where they are now."""
        dx, dy = move.offset
        return [(x + dx, y + dy, facing) for x, y, facing in move.doors]

    def smoke(self, move):
        dx, dy = move.offset
        return [(x + dx, y + dy, w, h) for x, y, w, h in move.smoke]

    # ----- moving

    def shift(self, thing, dx, dy):
        """Move a building and what belongs to it by dx, dy."""
        if not dx and not dy:
            return
        move = self.record(thing)
        thing.move_to(thing.x + dx, thing.y + dy)
        for light in move.lights:
            self.light_edits.shift(light, dx, dy)
        for ring in move.rings:
            if ring in self.roof_edits.rings:          # not if deleted in the roof mode meanwhile
                self.roof_edits.shift(ring, dx, dy)

    def put_back(self, thing):
        move = self.moves.get(thing.obj_id)
        if move:
            self.shift(thing, move.x0 - thing.x, move.y0 - thing.y)

    def is_moved(self, thing):
        move = self.moves.get(thing.obj_id)
        return bool(move and move.moved)

    def moved(self):
        return [m for m in self.moves.values() if m.moved]

    @property
    def count(self):
        return len(self.moved())

    # ----- writing

    def save(self):
        """Write the moves into Map1.tmx, all or none; returns the lines place_building logged. Raises ValueError."""
        moved = self.moved()
        if not moved:
            return []
        log = []
        with _at_root():
            text, layers = place_building.load_tmx()
            for move in moved:
                tags = []
                for obj_id in move.ids:
                    tag = re.search(rf'<object id="{obj_id}" [^>]*>', text)
                    if tag:
                        tags.append(tag.group(0))
                try:
                    text = place_building.move_object(text, layers, move.thing.obj_id, round(move.thing.x, 2),
                                                      round(move.thing.y, 2), attached=tags, log=log.append)
                except place_building.MoveError as error:
                    raise ValueError(str(error)) from error
            write_tmx(self.tmx_path, place_building.layers_into_text(text, layers))
        for move in moved:
            move.x0, move.y0 = move.thing.x, move.thing.y
        self._text = None
        self.moves.clear()
        return log
