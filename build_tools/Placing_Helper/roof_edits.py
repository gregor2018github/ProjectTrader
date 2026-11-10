"""The map's roofs and their holes, edited point by point and written back into Map1.tmx.

A roof is a polygon on the `Roofs` object layer named after its building
(src/models/roofs.py); one of Tiled type `Hole` is where a roof is open, and
cuts the roofs of the same building it lies on. Here each is a `Ring` of
world points. `RoofEdits` keeps them all, remembers each one's points as on
the map, has an undo history (`checkpoint()` before a change, `undo()`,
`redo()`), and writes only what changed, as text, by object id: a changed
ring gets its x, y and points, a removed one is cut out, a new one is added
at the end of the layer with an id from `nextobjectid` (Map1.tmx is LF; its
line endings are kept).
"""

import math
import re

from map_scene import TMX

MIN_POINTS = 3
UNDO_DEPTH = 200


class Ring:
    """One roof or hole: its building's name and its points in world pixels."""

    def __init__(self, obj_id, name, hole, points):
        self.obj_id = obj_id            # None until it is written into the map
        self.name = name
        self.hole = hole
        self.points = [(float(x), float(y)) for x, y in points]

    @property
    def kind(self):
        return 'hole' if self.hole else 'roof'

    def box(self):
        xs, ys = [p[0] for p in self.points], [p[1] for p in self.points]
        return min(xs), min(ys), max(xs), max(ys)

    def area(self):
        return abs(sum(ax * by - bx * ay for (ax, ay), (bx, by) in zip(self.points, self.points[1:] + self.points[:1]))) / 2

    def centre(self):
        left, top, right, bottom = self.box()
        return (left + right) / 2, (top + bottom) / 2

    def contains(self, x, y):
        return inside(self.points, x, y)


def inside(points, x, y):
    """Whether a point lies inside a polygon (even-odd, as the game's roofs.py)."""
    result = False
    for (ax, ay), (bx, by) in zip(points, points[1:] + points[:1]):
        if (ay > y) != (by > y) and x < ax + (y - ay) * (bx - ax) / (by - ay):
            result = not result
    return result


def nearest_on_segment(a, b, p):
    """The point of segment a-b nearest to p, and its distance."""
    (ax, ay), (bx, by), (px, py) = a, b, p
    dx, dy = bx - ax, by - ay
    length = dx * dx + dy * dy
    t = 0.0 if not length else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length))
    qx, qy = ax + t * dx, ay + t * dy
    return (qx, qy), math.hypot(px - qx, py - qy)


def _fmt(value):
    return f'{round(value, 2):g}'


class RoofEdits:
    def __init__(self, rings, tmx_path=TMX):
        self.rings = list(rings)
        self.tmx_path = tmx_path
        self.original = {r.obj_id: tuple(r.points) for r in self.rings}
        self._undo, self._redo = [], []

    # ----- looking up

    def by_name(self):
        groups = {}
        for ring in self.rings:
            groups.setdefault(ring.name, []).append(ring)
        return groups

    def ring_at(self, x, y):
        """The ring under a world point, the smallest if several (so a hole wins over its roof)."""
        hits = [r for r in self.rings if r.contains(x, y)]
        return min(hits, key=Ring.area) if hits else None

    def roof_around(self, x, y):
        """The smallest roof (not hole) a world point lies in."""
        hits = [r for r in self.rings if not r.hole and r.contains(x, y)]
        return min(hits, key=Ring.area) if hits else None

    # ----- undo

    def _state(self):
        return [(ring, tuple(ring.points)) for ring in self.rings]

    def checkpoint(self):
        """Remember the rings as they are now, before a change."""
        self._undo.append(self._state())
        del self._undo[:-UNDO_DEPTH]
        self._redo.clear()

    def drop_unchanged_checkpoint(self):
        """Forget the last checkpoint if nothing changed since (a click that moved nothing)."""
        if self._undo and self._undo[-1] == self._state():
            self._undo.pop()

    def _restore(self, state):
        self.rings = [ring for ring, _ in state]
        for ring, points in state:
            ring.points = list(points)

    def undo(self):
        if not self._undo:
            return False
        self._redo.append(self._state())
        self._restore(self._undo.pop())
        return True

    def redo(self):
        if not self._redo:
            return False
        self._undo.append(self._state())
        self._restore(self._redo.pop())
        return True

    # ----- changing (each after a checkpoint())

    def add(self, name, hole, points):
        ring = Ring(None, name, hole, points)
        self.rings.append(ring)
        return ring

    def remove(self, ring):
        self.rings.remove(ring)

    def remove_point(self, ring, index):
        """Take a point out of a ring; False if that would leave fewer than MIN_POINTS."""
        if len(ring.points) <= MIN_POINTS:
            return False
        del ring.points[index]
        return True

    def reset(self, ring):
        """A ring's points back as they are on the map; False for a new one."""
        if ring.obj_id not in self.original or ring.obj_id is None:
            return False
        ring.points = list(self.original[ring.obj_id])
        return True

    # ----- what changed

    def is_changed(self, ring):
        return ring.obj_id is None or tuple(ring.points) != self.original.get(ring.obj_id)

    def removed_ids(self):
        present = {r.obj_id for r in self.rings}
        return [i for i in self.original if i is not None and i not in present]

    @property
    def count(self):
        return sum(1 for r in self.rings if self.is_changed(r)) + len(self.removed_ids())

    # ----- writing

    def save(self, path=None):
        """Write the changes into the TMX (Map1.tmx unless told); returns (rings written, ids no longer in the file)."""
        path = path or self.tmx_path
        text = open(path, encoding='utf-8', newline='').read()
        nl = '\r\n' if '\r\n' in text else '\n'
        written, missing = 0, []

        def element(obj_id):
            return re.search(rf'[ \t]*<object id="{obj_id}" [^>]*?(?:/>|>.*?</object>)', text, re.S)

        for obj_id in self.removed_ids():
            found = element(obj_id)
            if not found:
                missing.append(obj_id)
                continue
            start = found.start()
            start -= len(nl) if text[start - len(nl):start] == nl else 0
            text = text[:start] + text[found.end():]
            written += 1
        for ring in self.rings:
            if ring.obj_id is None or not self.is_changed(ring):
                continue
            found = element(ring.obj_id)
            if not found:
                missing.append(ring.obj_id)
                continue
            x0, y0 = ring.points[0]
            xml = found.group(0)
            xml = re.sub(r' x="[^"]*"', f' x="{_fmt(x0)}"', xml, count=1)
            xml = re.sub(r' y="[^"]*"', f' y="{_fmt(y0)}"', xml, count=1)
            xml = re.sub(r'points="[^"]*"', f'points="{self._relative(ring)}"', xml, count=1)
            text = text[:found.start()] + xml + text[found.end():]
            written += 1
        new = [r for r in self.rings if r.obj_id is None]
        if new:
            group = re.search(r'<objectgroup [^>]*name="Roofs"[^>]*>.*?(\s*</objectgroup>)', text, re.S)
            if not group:
                raise ValueError('Map1.tmx has no Roofs object layer')
            next_id = re.search(r'nextobjectid="(\d+)"', text)
            obj_id = int(next_id.group(1))
            added = ''
            for ring in new:
                x0, y0 = ring.points[0]
                kind = ' type="Hole"' if ring.hole else ''
                added += (f'{nl}  <object id="{obj_id}" name="{ring.name}"{kind} x="{_fmt(x0)}" y="{_fmt(y0)}">{nl}'
                          f'   <polygon points="{self._relative(ring)}"/>{nl}  </object>')
                ring.obj_id = obj_id
                obj_id += 1
                written += 1
            text = text[:group.start(1)] + added + text[group.start(1):]
            text = text.replace(next_id.group(0), f'nextobjectid="{obj_id}"', 1)
        open(path, 'w', encoding='utf-8', newline='').write(text)
        self.original = {r.obj_id: tuple(r.points) for r in self.rings}
        self._undo.clear()
        self._redo.clear()
        return written, missing

    @staticmethod
    def _relative(ring):
        x0, y0 = ring.points[0]
        return ' '.join(f'{_fmt(x - x0)},{_fmt(y - y0)}' for x, y in ring.points)
