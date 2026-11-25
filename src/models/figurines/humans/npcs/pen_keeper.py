"""The pen's keeper: a homebody whose yard is the chicken pen, and who fills its troughs when they run dry.

Edric (``commons_edric``) is the first: his ``npc.json`` names his home
(House_19, the nearest house to the pen) and ``"keeps": "chicken_pen"``,
which makes him one of these. His yard, ``Edric_Yard`` on the "Movements"
layer, runs round the inside of the pen, so his way from his door to it goes
through the pen's gate, which he opens and shuts behind him like anyone
(gate_passing.py).

He is out nearly every day, by the daylight as any homebody; on one day in
about eight (``DAY_OFF_CHANCE``, the same for a day every time it is asked,
seeded by his name and the date) he stays in. Each time he is done standing
somewhere in the pen he first looks at the troughs: one that is empty
(chicken_troughs.Troughs.empty_ones) he walks to, the nearest first, stands
in front of it facing it (trough.Trough.keeper_spot) and fills it to the brim
with his own water or grain (``Troughs.keeper_fill``: whichever no trough
holds, else the trough's ``Keeper_fills``), for nothing of the player's,
then stands there ``FILL_MINUTES`` and goes back to his round.

Once a day, from a sun hour drawn for the day within ``COLLECT_HOURS``, he
also fetches the eggs out of the coop's nesting box (``NestBox``, standing at
chicken_coop.Coop.nest_spot): the whole ones (chicken_eggs.Nest.collect, at
most once a calendar day), which Game then sells at market for his class.
An empty trough comes first.

The map is not always shown, and time jumps (a rest, a minigame): while he is
at work and unseen (``Homebody._is_unseen``), ``see_to_unseen`` fills every
empty trough and fetches the eggs if it is time, at once, which Game calls
each update. Nothing of him is saved.

"""

import datetime
import math
import random
import zlib
from typing import TYPE_CHECKING, Callable, List, Optional, Sequence, Union

from ...patrol_path import PatrolPath
from . import homebody as _homebody
from .homebody import Homebody, LEAVING_YARD, LINGERING, ON_WALK, Point, RouteFinder, Walk

if TYPE_CHECKING:
    from ....chicken_eggs import Nest
    from ....chicken_troughs import Troughs
    from ....door import Door
    from ....trough import Trough

#: The npc.json key that makes a homebody a keeper, and what he keeps.
KEEPS_KEY = "keeps"
CHICKEN_PEN = "chicken_pen"

#: The share of days he stays indoors.
DAY_OFF_CHANCE = 0.12
#: How long he stands at a trough he has filled, in in-game minutes.
FILL_MINUTES = (4.0, 8.0)
#: LEAVING_YARD towards a trough (Homebody's TO_DOOR is -1, a walk's index 0 or more).
TO_TROUGH = -2
#: From when in his day he fetches the eggs, a sun hour drawn each day within these (the same for a day)
COLLECT_HOURS = (8.0, 12.0)
#: How long he stands at the nesting box taking the eggs out, in in-game minutes.
COLLECT_MINUTES = (3.0, 6.0)


class NestBox:
    """The coop's nesting box as one of his chores: where he stands for it."""

    name = "Nesting Box"

    def __init__(self, spot: Point) -> None:
        self.spot = spot

    def keeper_spot(self) -> Point:
        return self.spot


class PenKeeper(Homebody):
    """A homebody who sees to the chicken pen's troughs (see the module)."""

    def __init__(self, folder: str, profile: dict, tile_size: int) -> None:
        super().__init__(folder, profile, tile_size)
        self.keeps: str = str(profile.get(KEEPS_KEY))
        #: The troughs on the map (tend()), what is in them (look_after()) and who to tell when he fills one.
        self.troughs: List['Trough'] = []
        self.pen: Optional['Troughs'] = None
        self.on_filled: Optional[Callable[[], None]] = None
        #: The trough he is on his way to or filling, or the nesting box, or None.
        self.chore: Optional[Union['Trough', NestBox]] = None
        self._find_route: Optional[RouteFinder] = None
        #: The coop's nesting box (fetch_eggs()), its eggs, and who to tell how many he fetched.
        self.nest_box: Optional[NestBox] = None
        self.nest: Optional['Nest'] = None
        self.on_collected: Optional[Callable[[int], None]] = None

    # -- setup ----------------------------------------------------------------

    def settle(self, door: 'Door', yard: Optional[PatrolPath], walk_targets: Sequence[Point],
               find_route: RouteFinder) -> None:
        self._find_route = find_route
        super().settle(door, yard, walk_targets, find_route)

    def tend(self, troughs: Sequence['Trough']) -> None:
        """The troughs on the map he sees to (TMXMap)."""
        self.troughs = list(troughs)

    def look_after(self, pen: 'Troughs', on_filled: Optional[Callable[[], None]] = None) -> None:
        """What is in them (Game's troughs), and what to call when he has filled one (Game.show_troughs)."""
        self.pen = pen
        self.on_filled = on_filled

    def fetch_eggs(self, spot: Optional[Point], nest: Optional['Nest'] = None,
                   on_collected: Optional[Callable[[int], None]] = None) -> None:
        """Where he stands at the coop's nesting box (TMXMap; Coop.nest_spot), the eggs in it (Game's nest)
        and what to call with how many he fetched (Game sells them at market)."""
        if spot is not None:
            self.nest_box = NestBox(spot)
        if nest is not None:
            self.nest = nest
            self.on_collected = on_collected

    # -- his days ---------------------------------------------------------------

    def day_off(self, day: datetime.date) -> bool:
        """Whether he stays in all `day`: the same answer for a day every time."""
        draw = random.Random(zlib.crc32(f"{self.name}:{day.isoformat()}".encode()))
        return draw.random() < DAY_OFF_CHANCE

    def is_out_time(self, current_time: datetime.datetime) -> bool:
        return not self.day_off(current_time.date()) and super().is_out_time(current_time)

    def at_work(self, current_time: datetime.datetime) -> bool:
        """Whether he is out seeing to the pen now (not on a day off, in his hours)."""
        return self.is_out_time(current_time)

    def collect_from(self, day: datetime.date) -> float:
        """The sun hour from which he fetches the eggs on `day`: the same for a day every time."""
        draw = random.Random(zlib.crc32(f"{self.name}:eggs:{day.isoformat()}".encode()))
        return draw.uniform(*COLLECT_HOURS)

    def eggs_due(self, current_time: datetime.datetime) -> bool:
        """Whether it is time he fetched today's eggs: not yet done today, and past his hour for it."""
        if self.nest is None or self.nest_box is None or not self.nest.can_collect(current_time.date()):
            return False
        return _homebody.sun_hour(current_time) >= self.collect_from(current_time.date())

    def _collect(self, current_time: datetime.datetime) -> int:
        """Fetch the whole eggs out of the nest (once a day) and say how many."""
        if self.nest is None or not self.nest.can_collect(current_time.date()):
            return 0
        taken = self.nest.collect(current_time.date())
        if self.on_collected is not None:
            self.on_collected(taken)
        return taken

    # -- the troughs ------------------------------------------------------------

    def _empty_troughs(self) -> List['Trough']:
        if self.pen is None:
            return []
        empty = set(self.pen.empty_ones())
        return [trough for trough in self.troughs if trough.name in empty]

    def _fill(self, trough: 'Trough') -> bool:
        """Fill it, if it is still empty, and say so."""
        if self.pen is None or not self.pen.keeper_fill(trough.name, trough.keeper_fills):
            return False
        if self.on_filled is not None:
            self.on_filled()
        return True

    def _see_to_everything(self, current_time: datetime.datetime) -> bool:
        """Fill every empty trough and fetch the eggs if it is time: what he did unseen."""
        done = False
        for trough in self._empty_troughs():
            done = self._fill(trough) or done
        if self.eggs_due(current_time):
            self._collect(current_time)
            done = True
        return done

    def see_to_unseen(self, current_time: datetime.datetime) -> bool:
        """While he is at work off the map's view, fill every empty trough and fetch the eggs if it is time,
        at once; whether he did anything."""
        if not self.is_settled or not self._is_unseen(current_time) or not self.at_work(current_time):
            return False
        return self._see_to_everything(current_time)

    def _start_chore(self, current_time: datetime.datetime) -> bool:
        """Off to the nearest empty trough, else to the nesting box if the eggs are due; whether he went."""
        if self.yard is None:
            return False
        here = (self.x, self.y)
        chores: List[Union['Trough', NestBox]] = sorted(self._empty_troughs(),
                                                        key=lambda t: math.dist(here, t.keeper_spot()))
        if self.nest_box is not None and self.eggs_due(current_time):
            chores.append(self.nest_box)
        for trough in chores:
            spot = trough.keeper_spot()
            yard_distance = self.yard.closest_distance(spot)
            start = self.yard.position_at(yard_distance)
            route = (self._find_route(start, spot) if self._find_route else None) or [start, spot]
            path = PatrolPath(list(route), closed=False)
            if not path or path.length <= 0:
                continue
            self.chore = trough
            self._walk = Walk(path, yard_distance)
            self.state = LEAVING_YARD
            self._exit_to = TO_TROUGH
            self.walk_to_distance(yard_distance)
            return True
        return False

    # -- Homebody's hooks --------------------------------------------------------

    def _catch_up(self, current_time: datetime.datetime) -> None:
        # Time ran on unseen: what he would have filled meanwhile is filled
        if self.at_work(current_time):
            self._see_to_everything(current_time)
        super()._catch_up(current_time)

    def _move_on(self, current_time: datetime.datetime) -> None:
        if not self._start_chore(current_time):
            super()._move_on(current_time)

    def _arrive(self, current_time: datetime.datetime) -> None:
        if self.chore is not None and self.state == ON_WALK:
            # At the trough: fill it, or at the nesting box: take the eggs out; and stand at it a while
            if isinstance(self.chore, NestBox):
                self._collect(current_time)
                minutes = COLLECT_MINUTES
            else:
                self._fill(self.chore)
                minutes = FILL_MINUTES
            self.state = LINGERING
            self.idle_until = current_time + datetime.timedelta(minutes=random.uniform(*minutes))
            return
        super()._arrive(current_time)

    def _put_in_yard(self, current_time: datetime.datetime, distance: Optional[float] = None,
                     stagger: bool = False) -> None:
        self.chore = None
        super()._put_in_yard(current_time, distance, stagger)

    def go_indoors(self) -> None:
        self.chore = None
        super().go_indoors()

    def _standing_facing(self) -> Optional[str]:
        if self.chore is not None and self.state == LINGERING:
            return "back"                      # facing the trough he is filling
        return super()._standing_facing()

    def inspect_lines(self, observer=None) -> List[str]:
        lines = super().inspect_lines(observer)
        lines.append(f"Keeps: {self.keeps}; troughs: {len(self.troughs)}")
        if self.nest is not None:
            lines.append(f"Eggs in the nest: {self.nest.eggs:.1f}; fetches them from {self.collect_from(self.last_update_time.date()) if self.last_update_time else 0:.2f} (sun hour)")

        if self.chore is not None:
            lines.append(f"Seeing to: {self.chore.name}")
        return lines
