"""Keeps a handful of townsfolk out on the streets at any one time.

The town has more people than it ever shows at once. This is the director that
decides which of them is outside: it holds every :class:`Townsperson`, sends
one out of their own front door whenever the streets are emptier than they
should be, and lets them see themselves back in. Nobody is ever out twice,
because there is only ever the one object per person.

How busy the streets are depends on the hour -- see ``STROLLERS_BY_DAY`` and
``STROLLERS_BY_NIGHT`` in the constants. Anyone already out when night falls
finishes their walk; the town only stops sending new people.
"""

import datetime
import random
from typing import TYPE_CHECKING, Dict, List, Optional, Sequence, Tuple

from ..config.constants import (
    KNOCK_ANSWER_CHANCE,
    STROLLERS_BY_DAY,
    STROLLERS_BY_NIGHT,
    STROLL_NIGHT_START_HOUR,
    STROLL_NIGHT_END_HOUR,
    STROLL_RELEASE_SECONDS_MIN,
    STROLL_RELEASE_SECONDS_MAX,
)
from .door import Door
from .figurines.humans.npcs.townsperson import Townsperson
from .navigation import NavGrid

if TYPE_CHECKING:
    from .house import House

#: Tries at finding a door someone can actually walk to before giving up on
#: sending them out this tick. A town where most pairs of doors are cut off
#: from each other would otherwise search forever.
TARGET_ATTEMPTS = 6

#: A gap between updates longer than this, in in-game minutes, means the map
#: was not on show and the walkers stood frozen in the street while time ran
#: on. Everyone then goes straight indoors and the streets refill from there.
CATCH_UP_MINUTES = 30


class StreetLife:
    """The town's supply of people out walking."""

    def __init__(
        self,
        doors: Sequence[Door],
        townsfolk: Sequence[Townsperson],
        nav: NavGrid,
    ) -> None:
        """Move everyone into a house and start the clock on the first outing.

        Args:
            doors: Every usable door on the map.
            townsfolk: Everyone who might come out of one.
            nav: The walkability grid their routes are worked out on.
        """
        self.doors: List[Door] = [door for door in doors if door.is_usable]
        self.townsfolk: List[Townsperson] = list(townsfolk)
        self.nav: NavGrid = nav

        # Routes between two doors never change, and several people walk the
        # same street, so each pair is only ever searched for once.
        self._routes: Dict[Tuple[int, int], Optional[List[Tuple[float, float]]]] = {}
        self._release_left: float = 0.0
        self.last_update_time: Optional[datetime.datetime] = None

        self._assign_homes()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _assign_homes(self) -> None:
        """Put each townsperson behind a door, sharing them out evenly.

        With more people than doors some end up as neighbours, which is what a
        town looks like anyway.
        """
        if not self.doors:
            return
        homes = list(self.doors)
        random.shuffle(homes)
        for index, person in enumerate(self.townsfolk):
            person.go_indoors(homes[index % len(homes)])

    # ------------------------------------------------------------------
    # Timekeeping
    # ------------------------------------------------------------------

    def _is_night(self, current_time: datetime.datetime) -> bool:
        """Whether it is late enough that the streets should be quiet.

        Args:
            current_time: The current in-game time.
        """
        hour = current_time.hour + current_time.minute / 60.0
        # The window runs over midnight, so it is two ranges, not one
        return hour >= STROLL_NIGHT_START_HOUR or hour < STROLL_NIGHT_END_HOUR

    def target_count(self, current_time: datetime.datetime) -> int:
        """How many people should be out at the given time.

        Args:
            current_time: The current in-game time.
        """
        return STROLLERS_BY_NIGHT if self._is_night(current_time) else STROLLERS_BY_DAY

    def _is_unseen(self, current_time: datetime.datetime) -> bool:
        """Whether time ran on while the map was not being drawn.

        Args:
            current_time: The current in-game time.
        """
        return (self.last_update_time is None
                or abs(current_time - self.last_update_time)
                > datetime.timedelta(minutes=CATCH_UP_MINUTES))

    # ------------------------------------------------------------------
    # Sending people out
    # ------------------------------------------------------------------

    def _route_between(self, start: Door, end: Door) -> Optional[List[Tuple[float, float]]]:
        """The walkable route from one doorstep to another, worked out once.

        Args:
            start: The door walked out of.
            end: The door walked into.

        Returns:
            List: World points from ``start.step`` to ``end.step``, or None if
            there is no way between the two.
        """
        key = (start.id, end.id)
        if key not in self._routes:
            self._routes[key] = self.nav.find_route(start.step, end.step)
        return self._routes[key]

    def _pick_walker(self) -> Optional[Townsperson]:
        """Choose who goes out next.

        Normally one of the rested, picked at random so the same faces do not
        come round in order. If nobody has rested long enough the streets would
        stand emptier than they should, which is more noticeable than someone
        turning back out a little early, so the one closest to being rested
        goes instead.

        Returns:
            The townsperson to send out, or None if everyone is already out.
        """
        rested = [person for person in self.townsfolk if person.is_available]
        if rested:
            return random.choice(rested)
        indoors = [person for person in self.townsfolk
                   if not person.is_out and person.home_door is not None]
        return min(indoors, key=lambda person: person.rest_left) if indoors else None

    def _send_someone_out(self) -> bool:
        """Pick a townsperson who is in and start them on a walk.

        Returns:
            bool: True if somebody set off.
        """
        person = self._pick_walker()
        if person is None or len(self.doors) < 2:
            return False
        for _ in range(TARGET_ATTEMPTS):
            target = random.choice(self.doors)
            if target.id == person.home_door.id:
                continue
            route = self._route_between(person.home_door, target)
            if route and person.begin_outing(route, target):
                return True
        return False

    def answer_knock(self, house: 'House') -> bool:
        """Maybe bring one of a building's residents to its door.

        Knocking is worth doing only if it sometimes comes to something, and
        only annoying if it always does, so a knock at a house somebody is
        actually in is answered :data:`KNOCK_ANSWER_CHANCE` of the time. The
        rest of the town carries on regardless: whoever answers is out of the
        ordinary rotation for as long as they stand there, and goes back in
        through the door they came out of.

        Args:
            house: The building knocked on, which knows its own front doors.

        Returns:
            bool: True if somebody came out.
        """
        door_ids = {door.id for door in getattr(house, "doors", ())}
        if not door_ids:
            return False
        at_home = [person for person in self.townsfolk
                   if not person.is_out and person.home_door is not None
                   and person.home_door.id in door_ids]
        if not at_home or random.random() >= KNOCK_ANSWER_CHANCE:
            return False
        return random.choice(at_home).answer_door()

    # ------------------------------------------------------------------
    # Per-frame update
    # ------------------------------------------------------------------

    def update(self, dt: float, current_time: datetime.datetime) -> None:
        """Top the streets back up if they have run thin.

        Only the directing happens here. The townsfolk themselves are walked
        by :meth:`TMXMap.update_npcs` along with every other NPC, so that a
        townsperson is animated by exactly the same call as a trader.

        Args:
            dt: Delta time in real seconds.
            current_time: The current in-game time, which says how busy the
                streets should be.
        """
        if self._is_unseen(current_time):
            # They were standing in the street with the map turned off. Rather
            # than have them teleport on, walk them in through the nearest door
            # they were headed for and let the streets fill again.
            for person in self.townsfolk:
                if person.is_out:
                    person.go_indoors(person.target_door or person.home_door)
            self._release_left = 0.0
        self.last_update_time = current_time

        out_count = sum(1 for person in self.townsfolk if person.is_out)
        target = self.target_count(current_time)
        self._release_left -= dt
        if out_count < target and self._release_left <= 0.0:
            if self._send_someone_out():
                # Doors opening one after the other read better than a crowd
                # spilling out at once -- but not while the streets are still
                # well short of what they should hold.
                self._release_left = (
                    STROLL_RELEASE_SECONDS_MIN if out_count + 1 < target
                    else random.uniform(STROLL_RELEASE_SECONDS_MIN,
                                        STROLL_RELEASE_SECONDS_MAX)
                )
            else:
                # Nobody rested, or nowhere to go: look again in a moment
                # rather than every frame.
                self._release_left = STROLL_RELEASE_SECONDS_MIN
