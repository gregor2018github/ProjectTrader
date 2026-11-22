"""The harbour cranes' hoists: a rope off the jib's pulley, a hook on it, and now and then a load.

No pygame. A crane is a building like any other (``House``); what makes it a
crane is its sprite being in ``HOISTS``, which says where on the sprite the
rope comes off the pulley (in the sprite's own pixels, so it follows the
object's ``Scale``). ``TMXMap`` makes a ``Hoist`` for every such building.

The map is drawn frontally, so a jib cannot be seen to turn: a crane only
moves its loads up and down. What it moves them between is a lighter, a small
cargo barge moored on the water under the jib (``barge_x``, ``floor_y``),
whose loads stand in ``BARGE_SLOTS`` places along its floor, the one under
the rope (``Hoist.hook_slot``) where loads are hooked on and set down. A jib crane hoists a load out of the barge
and keeps it hanging high under the jib (as if waiting for the jib to swing
it ashore), or lowers one that hangs there into the barge. The Great Crane,
a gate crane, hoists into its hood (``stow_y``): a load going up past the
hood's floor goes out of sight inside and is stowed, and one can be fetched
out of it and lowered into the barge.

Whatever would pop in or out of sight (a barge arriving or leaving, a load
left hanging taken in) only changes while nobody sees the crane: once it has
been out of view for ``RESCENE_UNSEEN_S`` a new scene may be drawn
(``Hoist.set_scene``): nothing at all, a load just hanging there, or a barge
to work, more often by day than by night. In view, a crane with a barge works
trip after trip during working hours (``working_hours``) and otherwise lets
its hook hang and sway. The swing is a pendulum about the rope's top, pushed
by the wind with gusts, and knocked a little whenever a load starts or stops.

Nothing of it is saved.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import List, Optional, Tuple

#: The kinds of loads and their size in world pixels (width, height); the
#: pictures are assets/map_sprites/cranes/<kind>.png, painted at twice that
LOAD_SIZES = {
    "crate": (26, 22),
    "sacks": (28, 24),
    "barrel": (18, 24),
    "bale": (30, 20),
}
LOAD_KINDS = tuple(LOAD_SIZES)

#: From the rope's end (the top of the hook block) to the top of a load in its sling, world px: the
#: block and hook (HOOK_HEIGHT) and under it the sling's two ropes
HANG = 22
HOOK_HEIGHT = 13

BARGE_SLOTS = 5
#: The barge's slots' centres, world px from its middle. The one under the rope is the hook
#: slot, so a barge is only ever shifted from the rope by one of these (HoistSpec.barge_shift)
SLOT_OFFSETS = (-46, -23, 0, 23, 46)
#: How many loads a barge brings at most; one slot is always left free to put a load down in
MAX_CARGO = BARGE_SLOTS - 1

#: How fast a treadwheel winds the rope (world px a second) and how quickly it gets up to speed
HOIST_SPEED = 22.0
HOIST_ACCEL = 30.0
#: Rope lengths (world px below the pulley) of a hook at rest and of a load hung up high
REST_LENGTH = 10.0
TOP_LENGTH = 8.0
#: A gate crane's hook rests just out of its hood
HOOD_REST_LENGTH = 4.0
#: How much higher than the hood's floor a load goes to be out of sight inside it
HOOD_CLEAR = 4.0

#: A load shoved along the barge's floor from one slot to another takes this long (s)
SLIDE_S = 1.6

#: The pendulum: gravity in world px/s², the damping per second, the push of the wind
#: (px/s² at a wind of 1, signed like it) and how much it gusts
GRAVITY = 600.0
DAMPING = 0.25
WIND_PUSH = 90.0
GUST = 0.5
#: The knock a load gets when it starts or stops moving (radians, either way)
KNOCK = 0.035
#: The shortest pendulum worked with, world px (a hook drawn right up to the pulley)
MIN_SWING_LENGTH = 10.0

#: Working hours by the daylight (sun hours, see daylight.sun_hour), and the weather that stops work
WORK_FROM = 6.5
WORK_TO = 19.0
STOP_IN_STORM = 0.3
STOP_IN_RAIN = 0.8

#: How long a crane must have been out of view before a new scene may be drawn, and the chance it is
RESCENE_UNSEEN_S = 30.0
RESCENE_CHANCE = 0.6
#: The scenes' weights by day and by night: nothing, a load hanging, a barge to work
DAY_SCENES = {"idle": 0.35, "hanging": 0.15, "working": 0.5}
NIGHT_SCENES = {"idle": 0.85, "hanging": 0.15, "working": 0.0}
#: Of the working scenes, how many start with a load already hung up high (jib cranes)
WORKING_WITH_LOAD = 0.4

#: Pauses (s): between trips, a loaded jib crane holding its load up high, hooking a load on or off
REST_S = (5.0, 16.0)
HOLD_HIGH_S = (12.0, 35.0)
HOOK_ON_S = (3.0, 6.0)
INSIDE_S = (4.0, 9.0)


def working_hours(sun: float, storm: float, rain: float) -> bool:
    """Whether the cranes work: by daylight, and not in a storm or a downpour."""
    return WORK_FROM <= sun < WORK_TO and storm < STOP_IN_STORM and rain < STOP_IN_RAIN


@dataclass(frozen=True)
class HoistSpec:
    """Where a crane sprite's rope comes off its pulley, in the sprite's own pixels.

    rope_x, rope_top: the rope's top, where it leaves the pulley's rim (or the hood).
    stow_y: a gate crane's hood floor (sprite px): a load above it is inside, out of sight; None for a jib.
    waterline: where the barge floats, world px below the crane's base line (negative: above it).
    barge_shift: world px the barge lies to the right of the rope, to keep it off the quay; minus one
        of SLOT_OFFSETS, so a slot is under the rope.
    """
    rope_x: float
    rope_top: float
    stow_y: Optional[float] = None
    waterline: float = 0.0
    barge_shift: float = 0.0


#: The cranes, by sprite file
HOISTS = {
    # The treadwheel crane on the west quay: its rope drops off the far rim of the wheel at the jib's tip
    "House_53.png": HoistSpec(rope_x=433, rope_top=55, waterline=-6),
    # The covered-jib crane on the east quay: its wheel hangs under the jib's left end
    "House_54.png": HoistSpec(rope_x=27, rope_top=80),
    # The Great Crane, a gate crane: the rope comes out of the floor of its hood
    "House_55.png": HoistSpec(rope_x=1042, rope_top=262, stow_y=262, barge_shift=46),
}

#: How far the barge's floor (where loads stand) is above its waterline, world px; see crane_view.py
BARGE_FLOOR_ABOVE_WATER = 6


class Hoist:
    """One crane's rope, hook, load and barge, and what it is doing.

    Every length is the rope's, world px down from ``rope_top``; it may be
    negative on a gate crane, the hook then being up inside the hood.
    """

    def __init__(self, name: str, rope_x: float, rope_top: float, waterline_y: float,
                 stow_y: Optional[float] = None, barge_shift: float = 0.0,
                 rng: Optional[random.Random] = None) -> None:
        self.name = name
        self.rope_x = float(rope_x)
        self.rope_top = float(rope_top)
        self.waterline_y = float(waterline_y)
        self.floor_y = self.waterline_y - BARGE_FLOOR_ABOVE_WATER
        self.stow_y = None if stow_y is None else float(stow_y)
        if -barge_shift not in SLOT_OFFSETS:
            raise ValueError(f"{name}: a barge_shift of {barge_shift} puts no slot under the rope")
        self.barge_x = self.rope_x + barge_shift
        self.hook_slot = SLOT_OFFSETS.index(-barge_shift)
        self.rng = rng if rng is not None else random.Random()
        self.rest_length = HOOD_REST_LENGTH if self.is_gate_crane else REST_LENGTH
        self.length = self.rest_length
        self.speed = 0.0
        self.angle = 0.0
        self.spin = 0.0
        self.load: Optional[str] = None
        self.barge = False
        self.slots: List[Optional[str]] = [None] * BARGE_SLOTS
        #: A load being shoved along the barge: (from slot, to slot, kind, 0 to 1)
        self.slide: Optional[Tuple[int, int, str, float]] = None
        self.plan: List[tuple] = []
        self.wait = 0.0
        self.unseen = 0.0
        self.clock = 0.0
        self._gust_phase = self.rng.uniform(0.0, 100.0)
        #: Where the crane building sorts on the map (its base line): the rope is drawn just over it
        self.base_y = self.waterline_y

    @classmethod
    def on_building(cls, name: str, x: float, y: float, sprite_height: float, scale: float, spec: HoistSpec,
                    rng: Optional[random.Random] = None) -> "Hoist":
        """The hoist of a crane drawn from its bottom-left corner (x, y), its sprite sprite_height px tall."""
        top = y - sprite_height * scale
        hoist = cls(name, x + spec.rope_x * scale, top + spec.rope_top * scale, y + spec.waterline,
                    None if spec.stow_y is None else top + spec.stow_y * scale, spec.barge_shift, rng)
        hoist.base_y = y
        hoist.set_scene(hoist.draw_scene(True))
        return hoist

    # --- where things are ------------------------------------------------------------------------

    @property
    def is_gate_crane(self) -> bool:
        return self.stow_y is not None

    @property
    def inside_length(self) -> float:
        """A gate crane's rope length with any load wholly up in the hood."""
        tallest = max(h for _, h in LOAD_SIZES.values())
        return (self.stow_y - self.rope_top) - HANG - tallest - HOOD_CLEAR

    def landing_length(self, kind: str) -> float:
        """The rope's length with a load of that kind standing on the barge's floor."""
        return self.floor_y - LOAD_SIZES[kind][1] - HANG - self.rope_top

    def hook_point(self) -> Tuple[float, float]:
        """The rope's end, world px: the top of the hook block."""
        return (self.rope_x + self.length * math.sin(self.angle),
                self.rope_top + self.length * math.cos(self.angle))

    def slot_x(self, slot: int) -> float:
        return self.barge_x + SLOT_OFFSETS[slot]

    @property
    def cargo(self) -> int:
        """The loads in the barge, one being shoved along counted."""
        return sum(kind is not None for kind in self.slots) + (self.slide is not None)

    @property
    def hooking(self) -> Optional[str]:
        """The load in the barge the hook is down on and being made fast to, if it is."""
        if len(self.plan) > 1 and self.plan[0][0] == "wait" and self.plan[1][0] == "take":
            return self.slots[self.hook_slot]
        return None

    @property
    def busy(self) -> bool:
        return bool(self.plan) or self.slide is not None

    def area(self) -> Tuple[float, float, float, float]:
        """What the hoist may draw on, world (left, top, right, bottom), to tell whether it is in view."""
        left = min(self.rope_x, self.slot_x(0)) - 60
        right = max(self.rope_x, self.slot_x(BARGE_SLOTS - 1)) + 60
        return left, self.rope_top - 10, right, self.waterline_y + 20

    # --- scenes ----------------------------------------------------------------------------------

    def set_scene(self, scene: str) -> None:
        """Put the crane in a scene at once (only while nobody sees it): idle, hanging or working."""
        self.plan = []
        self.wait = self.rng.uniform(*REST_S)
        self.slide = None
        self.speed = 0.0
        self.angle = self.rng.uniform(-0.02, 0.02)
        self.spin = 0.0
        self.load = None
        self.barge = False
        self.slots = [None] * BARGE_SLOTS
        self.length = self.rest_length
        if scene == "hanging" and not self.is_gate_crane:
            self.load = self.rng.choice(LOAD_KINDS)
            low = self.landing_length(self.load) * 0.6
            self.length = self.rng.uniform(TOP_LENGTH, max(TOP_LENGTH, low))
        elif scene == "working":
            self.barge = True
            kinds = [self.rng.choice(LOAD_KINDS)] * 2 + [self.rng.choice(LOAD_KINDS)]
            places = [s for s in range(BARGE_SLOTS)]
            self.rng.shuffle(places)
            for slot in places[:self.rng.randint(0 if self.is_gate_crane else 1, MAX_CARGO - 1)]:
                self.slots[slot] = self.rng.choice(kinds)
            if not self.is_gate_crane and self.rng.random() < WORKING_WITH_LOAD:
                self.load = self.rng.choice(kinds)
                self.length = TOP_LENGTH
                self.wait = self.rng.uniform(*HOLD_HIGH_S)

    def draw_scene(self, day: bool) -> str:
        weights = DAY_SCENES if day else NIGHT_SCENES
        names = [n for n, w in weights.items() if w > 0]
        return self.rng.choices(names, [weights[n] for n in names])[0]

    # --- trips -----------------------------------------------------------------------------------

    def _free_side_slot(self) -> Optional[int]:
        sides = sorted((s for s in range(BARGE_SLOTS) if s != self.hook_slot and self.slots[s] is None),
                       key=lambda s: abs(s - self.hook_slot))
        return sides[0] if sides else None

    def _loaded_side_slot(self) -> Optional[int]:
        sides = sorted((s for s in range(BARGE_SLOTS) if s != self.hook_slot and self.slots[s] is not None),
                       key=lambda s: (abs(s - self.hook_slot), self.rng.random()))
        return sides[0] if sides else None

    def _clear_hook_slot(self) -> List[tuple]:
        """Shove the hook slot's load aside, if there is one (there is always a free side slot then)."""
        if self.slots[self.hook_slot] is None:
            return []
        return [("slide", self.hook_slot, self._free_side_slot())]

    def _feed_hook_slot(self) -> Tuple[List[tuple], str]:
        """Shove a load into the hook slot if it has none: (the steps, the kind that will be there)."""
        if self.slots[self.hook_slot] is not None:
            return [], self.slots[self.hook_slot]
        side = self._loaded_side_slot()
        return [("slide", side, self.hook_slot)], self.slots[side]

    def plan_trip(self) -> None:
        """Choose the next trip, if there is one to make; else rest a while."""
        self.plan = []
        if not self.barge:
            return
        hook_on = ("wait", self.rng.uniform(*HOOK_ON_S))
        if self.is_gate_crane:
            stow = self.cargo > 0 and (self.cargo >= MAX_CARGO or self.rng.random() < 0.5)
            if stow:
                feed, kind = self._feed_hook_slot()
                self.plan = feed + [("move", self.landing_length(kind)), hook_on, ("take",),
                                    ("move", self.inside_length), ("wait", self.rng.uniform(*INSIDE_S)),
                                    ("stow",), ("move", self.rest_length)]
            else:
                kind = self.rng.choice(LOAD_KINDS)
                self.plan = (self._clear_hook_slot() +
                             [("move", self.inside_length), ("wait", self.rng.uniform(*INSIDE_S)),
                              ("fetch", kind), ("move", self.landing_length(kind)), hook_on, ("put",),
                              ("move", self.rest_length)])
        elif self.load is not None:
            self.plan = self._clear_hook_slot() + [("move", self.landing_length(self.load)), hook_on, ("put",),
                                                   ("move", self.rest_length)]
        elif self.cargo > 0:
            feed, kind = self._feed_hook_slot()
            self.plan = feed + [("move", self.landing_length(kind)), hook_on, ("take",), ("move", TOP_LENGTH),
                                ("hold",)]

    def _step(self, dt: float) -> None:
        """Carry the plan on by dt seconds."""
        if self.slide is not None:
            a, b, kind, t = self.slide
            t += dt / SLIDE_S
            if t >= 1.0:
                self.slots[b] = kind
                self.slide = None
            else:
                self.slide = (a, b, kind, t)
            return
        if not self.plan:
            return
        step = self.plan[0]
        kind = step[0]
        if kind == "move":
            if self._wind_to(step[1], dt):
                self.plan.pop(0)
                self._knock()
            return
        if kind == "wait":
            remaining = step[1] - dt
            if remaining > 0:
                self.plan[0] = ("wait", remaining)
                return
        elif kind == "take":
            self.load, self.slots[self.hook_slot] = self.slots[self.hook_slot], None
            self._knock()
        elif kind == "put":
            self.slots[self.hook_slot], self.load = self.load, None
        elif kind == "slide":
            _, a, b = step
            self.slide = (a, b, self.slots[a], 0.0)
            self.slots[a] = None
        elif kind == "stow":
            self.load = None
        elif kind == "fetch":
            self.load = step[1]
        elif kind == "hold":
            self.wait = self.rng.uniform(*HOLD_HIGH_S)
        self.plan.pop(0)
        if not self.plan and kind != "hold":
            self.wait = self.rng.uniform(*REST_S)

    def _wind_to(self, target: float, dt: float) -> bool:
        """Wind the rope towards a length, speeding up and slowing down; True on arriving."""
        gap = target - self.length
        if abs(gap) < 0.25 and abs(self.speed) < 2.0:
            self.length, self.speed = target, 0.0
            return True
        direction = 1.0 if gap > 0 else -1.0
        # Slow down in time to stop there
        brake = math.sqrt(2.0 * HOIST_ACCEL * abs(gap))
        wanted = direction * min(HOIST_SPEED, brake)
        change = HOIST_ACCEL * dt
        self.speed += max(-change, min(change, wanted - self.speed))
        step = self.speed * dt
        if abs(step) >= abs(gap):
            self.length, self.speed = target, 0.0
            return True
        self.length += step
        return False

    def _knock(self) -> None:
        if self.load is not None:
            self.spin += self.rng.uniform(-KNOCK, KNOCK) * 3.0

    # --- the swing -------------------------------------------------------------------------------

    def gust(self) -> float:
        """The wind's gusting, about 1 (from 1 - GUST to 1 + GUST), smooth in time."""
        t = self.clock + self._gust_phase
        wave = 0.5 * math.sin(t * 0.73) + 0.3 * math.sin(t * 1.91 + 1.3) + 0.2 * math.sin(t * 3.7 + 0.4)
        return 1.0 + GUST * wave

    def _swing(self, dt: float, wind: float) -> None:
        # Every wait is with the hook down in the barge or up in the hood: it hangs straight then
        resting = bool(self.plan) and self.plan[0][0] == "wait"
        if resting or self.length < 0:
            self.angle *= max(0.0, 1.0 - 4.0 * dt)
            self.spin = 0.0
            return
        swing_length = max(MIN_SWING_LENGTH, self.length + (HANG if self.load else HANG * 0.4))
        push = WIND_PUSH * wind * self.gust()
        steps = max(1, math.ceil(dt / (1 / 120)))
        h = dt / steps
        for _ in range(steps):
            accel = (push * math.cos(self.angle) - GRAVITY * math.sin(self.angle)) / swing_length
            self.spin += (accel - DAMPING * self.spin) * h
            self.angle += self.spin * h

    # --- each frame ------------------------------------------------------------------------------

    def update(self, dt: float, seen: bool, working: bool, day: bool, wind: float) -> None:
        """Move the hoist on by dt real seconds.

        Args:
            seen: Whether any of it is in view (a new scene is only drawn while it is not).
            working: Whether it is working hours (working_hours()): trips are only begun then.
            day: Whether it is day, for which scenes may be drawn.
            wind: The weather's wind, signed.
        """
        dt = min(dt, 0.25)
        self.clock += dt
        if seen:
            self.unseen = 0.0
        else:
            self.unseen += dt
            if self.unseen >= RESCENE_UNSEEN_S:
                self.unseen = 0.0
                if self.rng.random() < RESCENE_CHANCE:
                    scene = self.draw_scene(day and working)
                    self.set_scene(scene)
        if not self.busy:
            self.wait -= dt
            if self.wait <= 0 and working:
                self.plan_trip()
                if not self.plan:
                    self.wait = self.rng.uniform(*REST_S)
        self._step(dt)
        self._swing(dt, wind)
