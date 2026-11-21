"""NPCs going through the gates on their way: stopping, opening, passing and shutting them behind them.

The townsfolk's NavGrid takes no notice of gates (navigation.py leaves their
gateways open), so a route runs through a gateway like anywhere else. Whoever
walks it lets a GatePassing look out for the gates on it: where the path
crosses a gate's box (gate_stops, GateStop) the walker comes to a stop a
little short of it, pauses, opens the gate if it is shut, walks through to a
little past it, turns round and shuts it, open as they found it or not, once
nobody stands in the gateway (Gate.can_close, the GateKeeper's `bodies`); if
someone stays in it past GIVE_UP_S they walk on and leave it open. Then their
walk goes on to where it was going.

It works along a path either way (a homebody walks his way home backwards),
only on open paths (a yard's round is closed and has no gates on it), and on
the NPC's own path-following (npc.py: path, path_distance, path_target,
walk_to_distance, _follow_path), so townsfolk, homebodies and the harvest's
workers all do it the same way. No pygame drawing; the gates' sounds go
through NPC.wants_gate_sound as before.
"""

import itertools
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import pygame

Point = tuple[float, float]

#: Real seconds a walker stands at a gate before opening it, and after shutting it
GATE_PAUSE_S = 0.6
#: World px short of the gate's box a walker stops, and past it he turns to shut it: his feet box then
#: (32 x 14 over his feet, gate.feet_box) is clear of the gateway either way
CLEAR_PX = 18
#: Real seconds he waits for someone to leave the gateway before walking on with the gate left open
GIVE_UP_S = 8.0

WAITING, THROUGH, SHUTTING, SHUT = "waiting", "through", "shutting", "shut"


@dataclass(frozen=True)
class GateStop:
    """A gate a path goes through: from `lo` to `hi` along it, its box widened by CLEAR_PX."""
    gate: Any
    lo: float
    hi: float


def _gate_box(gate: Any) -> pygame.Rect | None:
    rects = list(getattr(gate, "_blocking", ()) or getattr(gate, "collision_rects", ()))
    if not rects:
        return None
    box = pygame.Rect(rects[0])
    for rect in rects[1:]:
        box.union_ip(rect)
    return box


def gate_stops(points: Sequence[Point], gates: Sequence[Any]) -> list[GateStop]:
    """The gates an open path through `points` crosses, in the order it reaches them."""
    stops = []
    for gate in gates:
        box = _gate_box(gate)
        if box is None:
            continue
        wide = box.inflate(2 * CLEAR_PX, 2 * CLEAR_PX)
        spans = []                                  # (lo, hi, crosses the gate's own box)
        at = 0.0
        for start, end in itertools.pairwise(points):
            length = math.dist(start, end)
            clipped = wide.clipline(start, end)
            if clipped:
                a, b = clipped
                lo, hi = sorted((at + math.dist(start, a), at + math.dist(start, b)))
                crosses = bool(box.clipline(start, end))
                if spans and lo - spans[-1][1] < 1.0:
                    spans[-1] = (spans[-1][0], hi, spans[-1][2] or crosses)
                else:
                    spans.append((lo, hi, crosses))
            at += length
        stops += [GateStop(gate, lo, hi) for lo, hi, crosses in spans if crosses]
    return sorted(stops, key=lambda stop: stop.lo)


def _facing(dx: float, dy: float) -> str:
    """The way to face to look along a step."""
    if abs(dy) >= abs(dx):
        return "back" if dy < 0 else "front"
    return "left" if dx < 0 else "right"


class GateKeeper:
    """The map's gates and who may stand in them, shared by everyone who walks through them."""

    def __init__(self, gates: Sequence[Any], bodies: Callable[[], list[pygame.Rect]] = list) -> None:
        self.gates = list(gates)
        #: The feet boxes (world rects) of everyone who could stand in a gateway; set by the GameMap
        self.bodies = bodies
        self._stops: dict[int, tuple[Any, list[GateStop]]] = {}

    def stops(self, path: Any) -> list[GateStop]:
        """The gates on a path, worked out once per path."""
        if path is None or getattr(path, "closed", False) or not self.gates:
            return []
        known = self._stops.get(id(path))
        if known is None or known[0] is not path:
            if len(self._stops) > 512:
                self._stops.clear()
            known = (path, gate_stops(path.points, self.gates))
            self._stops[id(path)] = known
        return known[1]


class GatePassing:
    """One walker going through a gate: what he does there, frame by frame."""

    def __init__(self) -> None:
        self.stop: GateStop | None = None
        self.phase: str | None = None
        self.forward = True
        self._target: float | None = None
        self._path: Any = None
        self._set: float | None = None      # the walk target it last gave him
        self._wait = 0.0
        self._waited = 0.0
        self._opened: Any | None = None

    @property
    def active(self) -> bool:
        return self.stop is not None

    def step(self, walker: Any, dt: float, keeper: GateKeeper) -> bool:
        """Handle the walker's frame if a gate holds him; False to let him walk on as usual.

        Call it each frame before the walker follows his path."""
        if self.stop is not None and walker.path is not self._path:
            self.abandon(keeper)                       # put on another path meanwhile
        if self.stop is None and not self._reach_gate(walker, keeper):
            return False
        if walker.path_target is not None and walker.path_target != self._set:
            self._target = walker.path_target          # sent elsewhere meanwhile: there, once through
            walker.path_target = self._set
        stop = self.stop
        gate = stop.gate
        before, after = (stop.lo, stop.hi) if self.forward else (stop.hi, stop.lo)
        path = walker.path
        here, there = path.position_at(before), path.position_at(after)
        if self.phase == WAITING:
            walker._animate(dt, False, _facing(there[0] - here[0], there[1] - here[1]))
            self._wait -= dt
            if self._wait > 0:
                return True
            if not gate.is_open:
                gate.set_open(True)
                walker.wants_gate_sound = gate
            self._opened = gate
            self._walk(walker, after)
            self.phase = THROUGH
            return True
        if self.phase == THROUGH:
            if walker.path_target is None:            # a word with the player stopped him: walk on
                self._walk(walker, after)
            moving = walker._follow_path(dt)
            walker._animate(dt, moving)
            if not moving:
                self._halt(walker)
                self.phase, self._wait, self._waited = SHUTTING, GATE_PAUSE_S, 0.0
            return True
        # Turned back to it, shutting it once nobody stands in the gateway, then a moment's pause
        walker._animate(dt, False, _facing(here[0] - there[0], here[1] - there[1]))
        self._wait -= dt
        if self._wait > 0:
            return True
        if self.phase == SHUTTING:
            if gate.is_open:
                if not gate.can_close(keeper.bodies()):
                    self._waited += dt
                    if self._waited < GIVE_UP_S:
                        return True
                else:
                    gate.set_open(False)
                    walker.wants_gate_sound = gate
            self._opened = None
            self.phase, self._wait = SHUT, GATE_PAUSE_S
            return True
        # On his way again, to where he was going
        target, self.stop, self.phase, self._path = self._target, None, None, None
        walker.walk_to_distance(target if target is not None else path.length)
        return False

    def _walk(self, walker: Any, distance: float) -> None:
        walker.walk_to_distance(distance)
        self._set = walker.path_target

    def _halt(self, walker: Any) -> None:
        walker.stop()
        self._set = None

    def _reach_gate(self, walker: Any, keeper: GateKeeper) -> bool:
        """Whether he has come to a gate on his path, heading through it; then it holds him."""
        target = walker.path_target
        if target is None:
            return False
        distance = walker.path_distance
        for stop in keeper.stops(walker.path):
            if target > distance and stop.lo <= distance < stop.hi and target >= stop.hi:
                self.forward = True
            elif target < distance and stop.lo < distance <= stop.hi and target <= stop.lo:
                self.forward = False
            else:
                continue
            self.stop, self.phase, self._target, self._path = stop, WAITING, target, walker.path
            self._wait = GATE_PAUSE_S
            self._halt(walker)
            return True
        return False

    def abandon(self, keeper: GateKeeper) -> None:
        """He was put away (indoors, or where time had got him) in a gateway: shut what he opened if he
        can, and forget the gate."""
        gate, self._opened = self._opened, None
        if gate is not None and gate.is_open and gate.can_close(keeper.bodies()):
            gate.set_open(False)
        self.stop, self.phase, self._path = None, None, None
