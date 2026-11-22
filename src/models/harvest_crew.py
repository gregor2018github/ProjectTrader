"""The harvest's workers on the map: who goes out to which field, and his day there.

harvest.py decides the rules; this is them walking about. On each harvest day
HarvestCrew picks one worker per field still standing (harvest.pick_workers)
from the Poor and Commons townsfolk and gives him a HarvestJob. The
townsperson keeps his own object: while he has a job and is indoors or out on
it, Townsperson.update hands his frames to the job, and StreetLife leaves him
alone. Someone out strolling when picked finishes the walk first.

A HarvestJob is his day: at his hour (harvest.work_day) he steps out of his
door and walks to the field, through any gate on the way, as every NPC does
(gate_passing.py): he stops at it, opens it if it is shut, walks through,
turns and shuts it behind him once nobody stands in the gateway, open as he
found it or not.
At the field he goes from plant to plant in the harvest's order, stands below
each for HARVEST_MINUTES_PER_PLANT of game time and cuts it (the plant goes,
and a shock may stand up), until his hours are over, heavy rain sends him in,
or the field is done; then he walks back to his door and goes in. If the rain
stops while his hours last he comes out again. A word with the player holds
him wherever he is, the cutting too, and he carries on where he left off.

If the clock jumped while he was out (a rest, a minigame, the map hidden),
the field has been cut by the time meanwhile (Harvest.update), and he is put
where his day has got to: at the next plant, or indoors.
"""

import datetime
import time
from typing import TYPE_CHECKING, Dict, Generator, List, Optional, Sequence

from ..sim.calendar import day_number
from .figurines.humans.npcs.townsperson import AT_HOME
from .figurines.patrol_path import PatrolPath
from .gate_passing import SHUT, SHUTTING, THROUGH, WAITING as AT_THE_GATE
from .gate_ways import GateWays, Leg, Walk
from .harvest import (
    CATCH_UP_MINUTES, HARVEST_CLASSES, HARVEST_MINUTES_PER_PLANT, Harvest, FieldHarvest, WorkDay,
    is_harvest_day, pick_workers, shocks_standing_after_harvest, work_day,
)

if TYPE_CHECKING:
    from .field import Field
    from .figurines.humans.npcs.townsperson import Townsperson
    from .shock import Shock

#: World px below a plant's base a reaper stands to cut it, so he is drawn in front of it
STAND_BELOW_PX = 6.0
#: Time a frame may spend working out the workers' ways (as StreetLife's ROUTE_BUDGET_S)
ROUTE_BUDGET_S = 0.002
#: How long the fade at his door takes, in real seconds (as a townsperson's)
DOORWAY_FADE_SECONDS = 0.9
#: Game minutes the crew may go without an update (the map hidden: another view, a menu) before
#: its workers stop counting as on the map, and their fields are cut by the clock instead
UNSEEN_MINUTES = 5.0

# Where he is in his day; the person's state shows the same words in "Inspect"
WAITING = "Waiting to go to the harvest"
PLANNING = "Setting out"
STEPPING_OUT = "Stepping out to the harvest"
WALKING = "Walking to the field"
WALKING_HOME = "Walking home from the field"
AT_GATE = "Opening a gate"
THROUGH_GATE = "Going through a gate"
SHUTTING_GATE = "Shutting a gate"
TO_PLANT = "Stepping to the next sheaf"
CUTTING = "Cutting the corn"
GOING_IN = "Going indoors"
DONE = "Done with the harvest for today"

#: The states in which he stands out of doors
OUT_STATES = (STEPPING_OUT, WALKING, WALKING_HOME, AT_GATE, THROUGH_GATE, SHUTTING_GATE, TO_PLANT, CUTTING,
              GOING_IN)
#: The states that walk a path, picked up again after a word with the player
WALKING_STATES = (WALKING, WALKING_HOME, TO_PLANT)
#: At a gate on his way (gate_passing.py), its phase in his words
GATE_STATES = (AT_GATE, THROUGH_GATE, SHUTTING_GATE)
GATE_STATES_BY_PHASE = {AT_THE_GATE: AT_GATE, THROUGH: THROUGH_GATE, SHUTTING: SHUTTING_GATE, SHUT: SHUTTING_GATE}

FIELD, HOME = "field", "home"


def stand_spot(field: 'Field', plant: int) -> tuple:
    """Where a reaper stands to cut a plant of a field: just below it."""
    cx, by, _, _ = field.plants[plant]
    return cx, by + STAND_BELOW_PX


def _facing(dx: float, dy: float) -> str:
    """The way to face to look along a step."""
    if abs(dy) >= abs(dx):
        return "back" if dy < 0 else "front"
    return "left" if dx < 0 else "right"


class HarvestJob:
    """One worker's day at one field."""

    WAITING = WAITING

    def __init__(self, crew: 'HarvestCrew', person: 'Townsperson', field: 'Field', field_harvest: FieldHarvest,
                 hours: WorkDay) -> None:
        self.crew = crew
        self.person = person
        self.field = field
        self.field_harvest = field_harvest
        self.hours = hours
        self.home = person.home_door
        self.state = WAITING
        self.heading = FIELD
        self.legs: List[Leg] = []
        self.leg = 0
        self._planning: Optional[Generator[None, None, Optional[List[Leg]]]] = None
        #: Game minutes still to cut the plant he stands at
        self.work_left = 0.0
        self.last_now: Optional[datetime.datetime] = None

    # ------------------------------------------------------------------

    @property
    def is_out(self) -> bool:
        """Whether he is out of doors on the job, or about to step out."""
        return self.state in OUT_STATES or (self.state == PLANNING and self.heading == HOME)

    @property
    def is_over(self) -> bool:
        return self.state == DONE

    def wants_work(self, now: datetime.datetime) -> bool:
        """Whether he should be at the field now."""
        return (self.hours.start <= now < self.hours.end and is_harvest_day(now)
                and not self.crew.heavy_rain and not self.field_harvest.done)

    def _set_state(self, state: str) -> None:
        """His state, and the person's: the same words while he is out, indoors while he is not."""
        self.state = state
        indoors = state in (WAITING, DONE) or (state == PLANNING and self.heading == FIELD)
        self.person.state = AT_HOME if indoors else state

    # ------------------------------------------------------------------
    # Ways
    # ------------------------------------------------------------------

    def _plan(self, start, goal, heading: str) -> None:
        self.heading = heading
        self._planning = self.crew.ways.plan_steps(start, goal)
        self._set_state(PLANNING)

    def _run_planning(self) -> None:
        """Go on working out his way, within the frame's budget."""
        try:
            while True:
                next(self._planning)
                if time.perf_counter() >= self.crew.deadline:
                    return
        except StopIteration as done:
            legs = done.value
        self._planning = None
        if legs is None:
            print(f"Harvest: no way for {self.person.name} to "
                  f"{'the field ' + str(self.field.tmx_id) if self.heading == FIELD else 'his door'}")
            if self.heading == HOME:
                self.person.go_indoors(self.home)   # nowhere to walk: in he goes, out of sight
            self._finish()
            return
        if self.heading == FIELD:
            # Out of his door: from the doorway, onto the step the way starts at
            first = next((leg for leg in legs if isinstance(leg, Walk)), None)
            if first is not None:
                first.points.insert(0, self.home.entry)
            self.legs, self.leg = legs, 0
            self.person.stop()
            self.person.place_feet(*self.home.entry)
            self.person.opacity = 0.0
            self.person.fade_in(DOORWAY_FADE_SECONDS)
            self.person.wants_door_sound = True
            self._set_state(STEPPING_OUT)
        else:
            legs.append(Walk([self.home.step, self.home.entry]))
            self.legs, self.leg = legs, 0
            self._start_leg()

    def _start_leg(self) -> None:
        """Set off on the next leg of the way, or arrive."""
        while self.leg < len(self.legs):
            leg = self.legs[self.leg]
            path = PatrolPath(leg.points, closed=False)
            if path:
                self.person.set_path(path, 0.0)
                self.person.walk_to_distance(path.length)
                self._set_state(WALKING if self.heading == FIELD else WALKING_HOME)
                return
            self.leg += 1
        self._arrive()

    def _arrive(self) -> None:
        if self.heading == FIELD:
            self._next_plant()
        else:
            self._set_state(GOING_IN)
            self.person.stop()
            self.person.fade_out(DOORWAY_FADE_SECONDS)
            self.person.wants_door_sound = True

    def _walk_straight(self, goal, state: str) -> bool:
        """Walk from where he stands to a point; False if he is there already."""
        path = PatrolPath([self.person.feet, goal], closed=False)
        if not path:
            return False
        self.person.set_path(path, 0.0)
        self.person.walk_to_distance(path.length)
        self._set_state(state)
        return True

    # ------------------------------------------------------------------
    # The work
    # ------------------------------------------------------------------

    def _next_plant(self) -> None:
        plant = self.field_harvest.next_plant()
        if plant is None:
            self._go_home()
            return
        if not self._walk_straight(stand_spot(self.field, plant), TO_PLANT):
            self._start_cutting()

    def _start_cutting(self) -> None:
        self.person.stop()
        self.work_left = HARVEST_MINUTES_PER_PLANT
        self._set_state(CUTTING)

    def _go_home(self) -> None:
        self._plan(self.person.feet, self.home.step, HOME)

    def _finish(self) -> None:
        self._planning = None
        self._set_state(DONE)

    def _catch_up(self, now: datetime.datetime) -> None:
        """Time ran on unseen: put him where his day has got to."""
        if self.state in (WAITING, DONE):
            return
        self.person._leave_gate()
        self._planning = None
        plant = self.field_harvest.next_plant()
        if self.wants_work(now) and plant is not None:
            self.person.path = None
            self.person.stop()
            self.person.place_feet(*stand_spot(self.field, plant))
            self.person.fade_in(0.0)
            self._start_cutting()
        else:
            self.person.go_indoors(self.home)
            self._set_state(WAITING)

    # ------------------------------------------------------------------
    # Per frame
    # ------------------------------------------------------------------

    def update(self, dt: float, now: datetime.datetime) -> None:
        """His day, a frame on (called by Townsperson.update while he is indoors or out on it)."""
        person = self.person
        if self.state in (STEPPING_OUT, GOING_IN):
            # A doorway fade is not held up, not even for a word
            self.last_now = now
            door = self.home
            person._animate(dt, False, door.facing_in if self.state == GOING_IN else door.facing_out)
            if person.is_fading:
                return
            if self.state == GOING_IN:
                person.go_indoors(self.home)
                self._set_state(WAITING)
            else:
                self.leg = 0
                self._start_leg()
            return
        if person._hold_for_talk(dt):
            self.last_now = now        # the time talked is not worked
            return

        elapsed = 0.0
        if self.last_now is not None:
            if abs(now - self.last_now) > datetime.timedelta(minutes=CATCH_UP_MINUTES):
                self._catch_up(now)
            else:
                elapsed = max(0.0, (now - self.last_now).total_seconds() / 60.0)
        self.last_now = now

        if self.state == WAITING:
            person._animate(dt, False)
            if self.wants_work(now):
                self._plan(self.home.step, stand_spot(self.field, self.field_harvest.next_plant()), FIELD)
            elif now >= self.hours.end or self.field_harvest.done or not is_harvest_day(now):
                self._finish()
            return
        if self.state == DONE:
            person._animate(dt, False)
            return
        if self.state == PLANNING:
            person._animate(dt, False)
            self._run_planning()
            return
        if self.state in (TO_PLANT, CUTTING) and not self.wants_work(now):
            self._go_home()
            person._animate(dt, False)
            return
        if self.state == CUTTING:
            self.work_left -= elapsed
            person._animate(dt, False, "back")
            if self.work_left <= 0:
                plant = self.field_harvest.cut_next()
                if plant is not None:
                    self.crew.on_cut(self.field, plant, now)
                self._next_plant()
            return

        # Walking: a word with the player leaves the walk without a target, so pick it up again
        if self.state in WALKING_STATES and person.path is not None and person.path_target is None:
            person.walk_to_distance(person.path.length)
        if self.state in GATE_STATES or self.state in (WALKING, WALKING_HOME):
            if person._pass_gates(dt):
                self._set_state(GATE_STATES_BY_PHASE[person.gate_passing.phase])
                return
            if self.state in GATE_STATES:
                self._set_state(WALKING if self.heading == FIELD else WALKING_HOME)
        is_moving = person._follow_path(dt)
        if is_moving:
            person._animate(dt, True)
            return
        if self.state == TO_PLANT:
            self._start_cutting()
        else:
            self.leg += 1
            self._start_leg()
        person._animate(dt, False)

    def inspect_lines(self) -> List[str]:
        lines = [f"Harvest: field {self.field.tmx_id}, {self.field_harvest.cut}/{self.field_harvest.total} cut",
                 f"Hours: {self.hours.start:%H:%M} to {self.hours.end:%H:%M}"]
        if self.state == CUTTING:
            lines.append(f"This sheaf: {self.work_left:.1f} game minutes more")
        return lines


class HarvestCrew:
    """Sends the workers out and shows what they cut."""

    def __init__(self, harvest: Harvest, fields: Sequence['Field'], shocks: Sequence['Shock'],
                 townsfolk: Sequence['Townsperson'], ways: GateWays) -> None:
        self.harvest = harvest
        self.fields: Dict[int, 'Field'] = {field.tmx_id: field for field in fields if field.harvest is not None}
        self.shocks: List['Shock'] = list(shocks)
        self.townsfolk = list(townsfolk)
        self.ways = ways
        self.jobs: Dict[int, HarvestJob] = {}
        self.day: Optional[int] = None
        self.yesterday: List[str] = []
        #: Set by the game from the weather: too wet to work
        self.heavy_rain = False
        self.deadline = 0.0
        #: The game time of the last update, i.e. the last time the map ran its workers
        self.last_seen: Optional[datetime.datetime] = None

    def _unseen(self, now: datetime.datetime) -> bool:
        """Whether the map has not run the workers for over UNSEEN_MINUTES (or ever)."""
        return self.last_seen is None or now - self.last_seen > datetime.timedelta(minutes=UNSEEN_MINUTES)

    def live_fields(self, now: Optional[datetime.datetime] = None) -> List[int]:
        """The fields a worker on the map is at or bound for today (cut by him, not by the clock).

        None while the map is not running the workers (`now` past `last_seen` by UNSEEN_MINUTES):
        the time then goes by unseen, and Harvest.update cuts every field by the clock.
        """
        if now is not None and self._unseen(now):
            return []
        return [field_id for field_id, job in self.jobs.items() if not job.is_over]

    def update(self, now: datetime.datetime) -> None:
        """While the map is shown: a new day's crew, and the workers' way-finding budget for the frame."""
        self.deadline = time.perf_counter() + ROUTE_BUDGET_S
        unseen = self.last_seen is not None and self._unseen(now)
        self.last_seen = now
        day = day_number(now)
        if day != self.day:
            self._new_day(now)
            self.day = day
        elif unseen:
            # The map was hidden while the clock ran on and the fields were cut by it: each
            # worker is put where his day has got to, his own count of the time not added on top
            for job in self.jobs.values():
                job._catch_up(now)
                job.last_now = now
        for job in self.jobs.values():
            if job.is_over and job.person.job is job:
                job.person.job = None

    def _new_day(self, now: datetime.datetime) -> None:
        names = []
        for job in self.jobs.values():
            names.append(job.person.name)
            if job.person.job is job:
                if job.is_out:
                    job.person.go_indoors(job.home)       # shutting a gate he opened, if he was at one
                job.person.job = None
        self.yesterday = names
        self.jobs = {}
        if not is_harvest_day(now):
            return
        standing = [field_id for field_id, field in self.fields.items()
                    if not self.harvest.fields[field_id].done]
        candidates = {person.name: person for person in self.townsfolk
                      if person.SOCIAL_CLASS in HARVEST_CLASSES and person.home_door is not None
                      and getattr(person, "job", None) is None}
        for field_id, name in pick_workers(standing, list(candidates), now, self.yesterday).items():
            person = candidates[name]
            job = HarvestJob(self, person, self.fields[field_id], self.harvest.fields[field_id],
                             work_day(field_id, now))
            person.job = job
            self.jobs[field_id] = job

    def on_cut(self, field: 'Field', plant: int, now: datetime.datetime) -> None:
        """A worker cut a plant: it goes, and any shock it opens up stands."""
        field.mark_cut(plant, now)
        self.refresh_shocks(now)

    def refresh_shocks(self, now: datetime.datetime) -> None:
        """Stand each shock the harvest has reached, and only those (the days after it, all of them)."""
        after = shocks_standing_after_harvest(now)
        for shock in self.shocks:
            field_harvest = self.harvest.fields.get(shock.field_id)
            if field_harvest is None:
                continue
            shock.set_shown(after or (is_harvest_day(now) and field_harvest.cut_at(now) >= shock.threshold))

    def refresh(self, now: datetime.datetime, field_ids=None) -> None:
        """Show the fields as cut as the harvest has them (all, or those named), and the shocks."""
        for field_id in (self.fields if field_ids is None else field_ids):
            field = self.fields.get(field_id)
            if field is not None:
                field.update_growth(now)
        self.refresh_shocks(now)
