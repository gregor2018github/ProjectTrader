"""Fences and walls drawn in the Placing Helper's fence mode, to be designed and put on the map by Claude.

No pygame. A fence is drawn on the tile grid: its posts stand at tile centres
(as the churchyard wall's do, `Raster.start` in the Sprite Manager's
fences.py), so a post is named by its tile (tx, ty), its foot at
((tx + 0.5) * TILE, (ty + 0.5) * TILE) in world pixels. It is made of straight
runs, across (h) or down the picture (v), from one post to another, and may
have gates: gaps of a few tiles on a run, post to post, where a gate is to hang.

Each fence keeps its material and the user's description of how it is to look.
fence_plans.json (beside this file, git-ignored) holds them all, and for each
fence also the pieces it splits into between its corners and gates, in the
form of a fence style's "plan" in fence.json: [orientation, tiles, x, y], x
and y the first post's tile counted from the fence's top-left post,
whose foot is `origin_px`. That is what the fence tool and the churchyard's
placing work from.
"""

import json
import time
from dataclasses import dataclass, field

TILE = 32
HORIZONTAL, VERTICAL = 'h', 'v'
MATERIALS = ('wood', 'stone', 'metal')
MATERIAL_TITLES = {'wood': 'Wood', 'stone': 'Stone', 'metal': 'Metal'}
DEFAULT_MATERIAL = 'wood'
GATE_WIDTHS = (1, 2, 3, 4)          # tiles, post to post
DEFAULT_GATE_WIDTH = 2              # as the churchyard's gates
FORMAT = 1
ABOUT = ('Fences and walls drawn in the Placing Helper (fence mode, W), for Claude to design and put on the '
         'map. Tiles are 32 px; a post is named by its tile (x, y), its foot at the tile centre '
         '((x + 0.5) * 32, (y + 0.5) * 32). A run goes from its first post `length` tiles across (h) or down '
         '(v); a gate is a gap of `width` tiles on a run, post to post. "plan" is the fence split at its '
         'corners and gates into pieces, as a fence style\'s plan in fence.json: [orientation, tiles, x, y], '
         'x and y counted in tiles from the top-left post, whose foot is origin_px. "description" is how it '
         'is to look, in the user\'s words.')


def post_foot(tx, ty):
    """The world pixel a post on tile (tx, ty) stands on."""
    return (tx + 0.5) * TILE, (ty + 0.5) * TILE


@dataclass
class Run:
    orientation: str
    x: int
    y: int
    length: int

    @property
    def step(self):
        return (1, 0) if self.orientation == HORIZONTAL else (0, 1)

    def at(self, along):
        """The tile `along` tiles from its first post."""
        dx, dy = self.step
        return self.x + dx * along, self.y + dy * along

    @property
    def end(self):
        return self.at(self.length)

    def along_of(self, tx, ty):
        """How far along it the tile (tx, ty) lies, or None if it is not on it."""
        if self.orientation == HORIZONTAL:
            along = tx - self.x
            return along if ty == self.y and 0 <= along <= self.length else None
        along = ty - self.y
        return along if tx == self.x and 0 <= along <= self.length else None

    def to_dict(self):
        return {'orientation': self.orientation, 'x': self.x, 'y': self.y, 'length': self.length,
                'from_px': list(post_foot(self.x, self.y)), 'to_px': list(post_foot(*self.end))}


@dataclass
class Gate:
    orientation: str
    x: int
    y: int
    width: int

    @property
    def end(self):
        return (self.x + self.width, self.y) if self.orientation == HORIZONTAL else (self.x, self.y + self.width)

    def to_dict(self):
        return {'orientation': self.orientation, 'x': self.x, 'y': self.y, 'width': self.width,
                'from_px': list(post_foot(self.x, self.y)), 'to_px': list(post_foot(*self.end))}


def run_between(a, b):
    """The run from post tile a to b, straight across or down (the longer way wins); None if a == b."""
    (ax, ay), (bx, by) = a, b
    if abs(bx - ax) >= abs(by - ay):
        if bx == ax:
            return None
        return Run(HORIZONTAL, min(ax, bx), ay, abs(bx - ax))
    return Run(VERTICAL, ax, min(ay, by), abs(by - ay))


def straightened(a, b):
    """Where a run from a towards b ends: b moved onto a's row or column, whichever is nearer."""
    (ax, ay), (bx, by) = a, b
    return (bx, ay) if abs(bx - ax) >= abs(by - ay) else (ax, by)


@dataclass
class Fence:
    id: int
    material: str = DEFAULT_MATERIAL
    description: str = ''
    runs: list = field(default_factory=list)
    gates: list = field(default_factory=list)

    @property
    def title(self):
        return f'{MATERIAL_TITLES.get(self.material, self.material)} fence {self.id}'

    def length(self):
        return sum(r.length for r in self.runs)

    def add_run(self, run):
        """Add a run, joined to one it continues in a straight line; returns the run it ended up in."""
        for other in self.runs:
            if other.orientation != run.orientation:
                continue
            same_line = other.y == run.y if run.orientation == HORIZONTAL else other.x == run.x
            if not same_line:
                continue
            a0 = run.x if run.orientation == HORIZONTAL else run.y
            b0 = other.x if run.orientation == HORIZONTAL else other.y
            if a0 <= b0 + other.length and b0 <= a0 + run.length:      # touching or overlapping: one run
                start = min(a0, b0)
                end = max(a0 + run.length, b0 + other.length)
                if run.orientation == HORIZONTAL:
                    other.x = start
                else:
                    other.y = start
                other.length = end - start
                self._merge_touching(other)
                return other
        self.runs.append(run)
        return run

    def _merge_touching(self, run):
        for other in list(self.runs):
            if other is not run and other.orientation == run.orientation:
                self.runs.remove(other)
                if self.add_run(other) is other:              # did not join: put it back as it was
                    continue
        if run not in self.runs:
            self.runs.append(run)

    def run_at(self, tx, ty):
        """(run, along) of a run through tile (tx, ty), or None."""
        for run in self.runs:
            along = run.along_of(tx, ty)
            if along is not None:
                return run, along
        return None

    def gates_on(self, run):
        """The gates lying on a run, ordered along it."""
        found = []
        for gate in self.gates:
            if gate.orientation != run.orientation:
                continue
            start = run.along_of(gate.x, gate.y)
            if start is not None and start + gate.width <= run.length:
                found.append((start, gate))
        return [g for _, g in sorted(found, key=lambda e: e[0])]

    def gate_at(self, tx, ty):
        """The gate whose gap takes in tile (tx, ty), or None."""
        for gate in self.gates:
            if gate.orientation == HORIZONTAL and ty == gate.y and gate.x <= tx <= gate.x + gate.width:
                return gate
            if gate.orientation == VERTICAL and tx == gate.x and gate.y <= ty <= gate.y + gate.width:
                return gate
        return None

    def place_gate(self, tx, ty, width):
        """A gate of `width` tiles on the run through (tx, ty), centred there as far as the run allows and
        clear of its other gates. Returns the Gate, or a reason it does not fit."""
        hit = self.run_at(tx, ty)
        if hit is None:
            return 'Click on a run of the fence to put a gate in it'
        run, along = hit
        if run.length < width:
            return f'That run is {run.length} tiles long, too short for a gate of {width}'
        start = min(max(0, round(along - width / 2)), run.length - width)
        for other in self.gates_on(run):
            o = run.along_of(other.x, other.y)
            if start < o + other.width and o < start + width:
                return 'A gate is already there'
        gx, gy = run.at(start)
        gate = Gate(run.orientation, gx, gy, width)
        self.gates.append(gate)
        return gate

    def remove_run(self, run):
        for gate in self.gates_on(run):
            self.gates.remove(gate)
        self.runs.remove(run)

    def posts(self):
        """Every corner, end and gatepost, as tiles."""
        points = set()
        for run in self.runs:
            points.update((run.at(0), run.end))
        for gate in self.gates:
            points.update(((gate.x, gate.y), gate.end))
        return sorted(points)

    def pieces(self):
        """[(orientation, tiles, x, y)] in absolute tiles: each run split at its gates."""
        out = []
        for run in self.runs:
            at = 0
            for gate in self.gates_on(run):
                start = run.along_of(gate.x, gate.y)
                if start > at:
                    out.append((run.orientation, start - at, *run.at(at)))
                at = start + gate.width
            if run.length > at:
                out.append((run.orientation, run.length - at, *run.at(at)))
        return out

    def origin(self):
        posts = self.posts()
        if not posts:
            return None
        return min(x for x, _ in posts), min(y for _, y in posts)

    def to_dict(self):
        data = {'id': self.id, 'material': self.material, 'description': self.description,
                'length_tiles': self.length(),
                'runs': [r.to_dict() for r in self.runs], 'gates': [g.to_dict() for g in self.gates]}
        origin = self.origin()
        if origin is not None:
            ox, oy = origin
            data['origin_tile'] = [ox, oy]
            data['origin_px'] = list(post_foot(ox, oy))
            data['plan'] = [[o, n, x - ox, y - oy] for o, n, x, y in self.pieces()]
            data['gate_plan'] = [[g.orientation, g.width, g.x - ox, g.y - oy] for g in self.gates]
        return data

    @classmethod
    def from_dict(cls, d):
        return cls(int(d['id']), d.get('material', DEFAULT_MATERIAL), d.get('description', ''),
                   [Run(r['orientation'], int(r['x']), int(r['y']), int(r['length'])) for r in d.get('runs', [])],
                   [Gate(g['orientation'], int(g['x']), int(g['y']), int(g['width'])) for g in d.get('gates', [])])


class FencePlans:
    """All the fences drawn, saved to their file after every change, with undo."""

    UNDO_DEPTH = 100

    def __init__(self, path):
        self.path = path
        self.fences = []
        self._undo, self._redo = [], []
        if path.exists():
            data = json.loads(path.read_text(encoding='utf-8'))
            self.fences = [Fence.from_dict(d) for d in data.get('fences', [])]

    @property
    def next_id(self):
        return max((f.id for f in self.fences), default=0) + 1

    def new_fence(self, material=DEFAULT_MATERIAL):
        fence = Fence(self.next_id, material)
        self.fences.append(fence)
        return fence

    def find(self, fence_id):
        return next((f for f in self.fences if f.id == fence_id), None)

    def at(self, tx, ty):
        """(fence, run, along) of a run through tile (tx, ty), the latest fence first, or None."""
        for fence in reversed(self.fences):
            hit = fence.run_at(tx, ty)
            if hit:
                return fence, *hit
        return None

    def gate_at(self, tx, ty):
        for fence in reversed(self.fences):
            gate = fence.gate_at(tx, ty)
            if gate:
                return fence, gate
        return None

    # ----- undo

    def _snapshot(self):
        return json.dumps([f.to_dict() for f in self.fences])

    def checkpoint(self):
        """Call before a change, so it can be undone."""
        self._undo.append(self._snapshot())
        del self._undo[:-self.UNDO_DEPTH]
        self._redo.clear()

    def _restore(self, snapshot):
        self.fences = [Fence.from_dict(d) for d in json.loads(snapshot)]

    def undo(self):
        if not self._undo:
            return False
        self._redo.append(self._snapshot())
        self._restore(self._undo.pop())
        self.save()
        return True

    def redo(self):
        if not self._redo:
            return False
        self._undo.append(self._snapshot())
        self._restore(self._redo.pop())
        self.save()
        return True

    # ----- the file

    def save(self):
        data = {'about': ABOUT, 'format': FORMAT, 'saved': time.strftime('%Y-%m-%d %H:%M:%S'),
                'map': 'assets/tiles/Map1.tmx', 'tile': TILE,
                'fences': [f.to_dict() for f in self.fences if f.runs or f.description]}
        tmp = self.path.with_suffix('.tmp')
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        tmp.replace(self.path)
