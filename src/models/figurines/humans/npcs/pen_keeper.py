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

The map is not always shown, and time jumps (a rest, a minigame): while he is
at work and unseen (``Homebody._is_unseen``), ``see_to_unseen`` fills every
empty trough at once, which Game calls each update. Nothing of him is saved.
"""

import datetime
import math
import random
import zlib
from typing import TYPE_CHECKING, Callable, List, Optional, Sequence

from ...patrol_path import PatrolPath
from .homebody import Homebody, LEAVING_YARD, LINGERING, ON_WALK, Point, RouteFinder, Walk

if TYPE_CHECKING:
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


class PenKeeper(Homebody):
    """A homebody who sees to the chicken pen's troughs (see the module)."""

    def __init__(self, folder: str, profile: dict, tile_size: int) -> None:
        super().__init__(folder, profile, tile_size)
        self.keeps: str = str(profile.get(KEEPS_KEY))
        #: The troughs on the map (tend()), what is in them (look_after()) and who to tell when he fills one.
        self.troughs: List['Trough'] = []
        self.pen: Optional['Troughs'] = None
        self.on_filled: Optional[Callable[[], None]] = None
        #: The trough he is on his way to or filling, or None.
        self.chore: Optional['Trough'] = None
        self._find_route: Optional[RouteFinder] = None

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

    def see_to_unseen(self, current_time: datetime.datetime) -> bool:
        """While he is at work off the map's view, fill every empty trough at once; whether he filled any."""
        if not self.is_settled or not self._is_unseen(current_time) or not self.at_work(current_time):
            return False
        filled = False
        for trough in self._empty_troughs():
            filled = self._fill(trough) or filled
        return filled

    def _start_chore(self) -> bool:
        """Off to the nearest empty trough, if there is one; whether he went."""
        if self.yard is None:
            return False
        here = (self.x, self.y)
        for trough in sorted(self._empty_troughs(), key=lambda t: math.dist(here, t.keeper_spot())):
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
            for trough in self._empty_troughs():
                self._fill(trough)
        super()._catch_up(current_time)

    def _move_on(self, current_time: datetime.datetime) -> None:
        if not self._start_chore():
            super()._move_on(current_time)

    def _arrive(self, current_time: datetime.datetime) -> None:
        if self.chore is not None and self.state == ON_WALK:
            # At the trough: fill it and stand at it a while
            self._fill(self.chore)
            self.state = LINGERING
            self.idle_until = current_time + datetime.timedelta(minutes=random.uniform(*FILL_MINUTES))
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
        if self.chore is not None:
            lines.append(f"Seeing to: {self.chore.name}")
        return lines
