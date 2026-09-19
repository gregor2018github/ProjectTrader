"""Abstract base class for market traders.

Every trader behaves the same way — only their artwork, name and standing
differ — so the behaviour lives here and a concrete trader is little more than
a handful of class attributes.

At work a trader walks the patrol path around his stall to a new spot, stands
there for the best part of an in-game hour, then shuffles somewhere else.
Some time between 22:00 and midnight he packs up, walks home and disappears
indoors, and some time between 04:45 and 06:45 he steps out and walks back;
each night at a different time. His booth is open while he is minding it: it shuts as he steps off
the stall onto his way home, and opens again once he is back.

Where he works and lives is drawn on the Tiled "Movements" layer, named after
his ``TILED_PREFIX`` (``Butcher`` for the butcher):

* ``<prefix>_Market_Stall`` — polygon he walks while minding his stall.
* ``<prefix>_Homeway_Path`` — polygon or polyline leading to his house.
* ``<prefix>_Homeway_Start`` — point where he steps off the stall onto it.
* ``<prefix>_Homeway_End`` — point at his front door.
"""

import datetime
import random
from typing import TYPE_CHECKING, List, Optional, Tuple

from ....institutions.market import MarketHours
from ...patrol_path import PatrolPath
from .npc import NPC

if TYPE_CHECKING:
    from ....institutions.market import Market

#: Default walking speed in pixels per second at tile_size 32. Well under the
#: player's 120 — a trader is minding a stall, not going anywhere.
TRADER_SPEED = 35.0

#: How long a trader stays put once he has picked a spot, in in-game minutes.
IDLE_MIN_MINUTES = 40
IDLE_MAX_MINUTES = 90

#: A new spot has to be at least this far along the path to be worth walking to,
#: so he does not take a single step and call it a move.
MIN_STEP_DISTANCE = 48.0

#: Tries at rolling a far-enough spot before settling for whatever came up. A
#: path shorter than MIN_STEP_DISTANCE would otherwise loop forever.
SPOT_ATTEMPTS = 8

#: A gap between updates longer than this, in in-game minutes, means the map
#: was not being shown and time ran on without him. He then jumps straight to
#: wherever his day would have taken him instead of walking there late.
CATCH_UP_MINUTES = 30

# Where a trader is in his day.
WORKING = "At work"
LEAVING_STALL = "Leaving the stall"
WALKING_HOME = "Walking home"
AT_HOME = "At home"
WALKING_TO_WORK = "Walking to work"


class Trader(NPC):
    """A townsperson who keeps a stall at the market."""

    IS_TRADER = True
    #: Display name used when none is passed in.
    DEFAULT_NAME: str = "Trader"
    #: Walking speed in pixels per second at tile_size 32.
    SPEED: float = TRADER_SPEED
    #: Name stem of his objects on the Tiled "Movements" layer, e.g. "Butcher".
    TILED_PREFIX: str = ""
    #: Name of the Market object (on the "Houses" layer) his stall belongs to.
    MARKET_NAME: str = ""
    #: Goods he sells that his market's name does not mention.
    EXTRA_GOODS: Tuple[str, ...] = ()

    def __init__(self, x: float, y: float, tile_size: int, name: Optional[str] = None) -> None:
        """Place the trader on the map.

        Args:
            x: Initial world X.
            y: Initial world Y.
            tile_size: Base tile size for scaling.
            name: Display name. Defaults to ``DEFAULT_NAME``.
        """
        super().__init__(name or self.DEFAULT_NAME, x, y, tile_size)
        self.speed = self.SPEED * tile_size / 32.0

        self._init_human_animator(
            sprite_dir=self.sprite_dir,
            sprite_definitions=self._sprite_definitions(),
            fallback_static=self._fallback_static(),
            normalize=True,
        )

        # In-game time at which he next feels like moving. None means "decide on
        # the first update", since the clock is not known at construction.
        self.idle_until: Optional[datetime.datetime] = None

        # Filled in by the map loader from the Tiled data.
        #: The market booth he keeps; it is open while he is at his stall.
        self.market: Optional['Market'] = None
        #: The path around his stall that he walks while at work.
        self.stall_path: Optional[PatrolPath] = None
        #: Open path from his stall to his front door. None if he has no home
        #: drawn, in which case he never leaves the stall.
        self.homeway: Optional[PatrolPath] = None
        #: Where along the stall path he steps onto his homeway.
        self.stall_exit_distance: float = 0.0

        self.state: str = WORKING
        # In-game time of the last update, to notice when time ran on unseen.
        self.last_update_time: Optional[datetime.datetime] = None
        #: When he packs up and when he comes back, a little different each night.
        self.hours = MarketHours()

    def set_workplace(self, stall_path: PatrolPath, market: Optional['Market']) -> None:
        """Put the trader to work at his stall.

        Args:
            stall_path: The path around his stall.
            market: The market booth his stall belongs to, if found.
        """
        self.stall_path = stall_path
        self.market = market
        self.set_path(stall_path)

    def set_homeway(self, homeway: PatrolPath) -> None:
        """Tell the trader how he gets home.

        Args:
            homeway: Open path starting on his stall path and ending at his
                front door.
        """
        self.homeway = homeway
        if self.stall_path is not None:
            self.stall_exit_distance = self.stall_path.closest_distance(homeway.points[0])

    def inspect_lines(self, observer=None) -> List[str]:
        """Debug lines for the "Inspect" window, plus his day and when he moves on."""
        lines = super().inspect_lines(observer)
        lines.append(f"Day: {self.state}")
        lines.append(f"Market: {self.market.name if self.market else 'none'}")
        if self.homeway is not None:
            lines.append(f"Way home: {self.homeway.length:.0f} px")
        else:
            lines.append("Way home: none")
        if self.state == WORKING and self.path_target is None and self.idle_until is not None:
            lines.append(f"Idle until: {self.idle_until:%H:%M}")
        return lines

    # ------------------------------------------------------------------
    # At the stall
    # ------------------------------------------------------------------

    def _rest(self, current_time: datetime.datetime, stagger: bool = False) -> None:
        """Stand still until some way into the next in-game hour.

        Args:
            current_time: The current in-game time.
            stagger: Rest anywhere from no time at all up to a full rest. Used
                when all traders start resting at the same moment, so they
                do not keep moving in step with each other.
        """
        min_minutes = 0 if stagger else IDLE_MIN_MINUTES
        self.idle_until = current_time + datetime.timedelta(
            minutes=random.uniform(min_minutes, IDLE_MAX_MINUTES)
        )

    def _pick_new_spot(self) -> None:
        """Choose somewhere else on the path and start walking there."""
        if self.path is None or not self.path:
            return
        for _ in range(SPOT_ATTEMPTS):
            candidate = self.path.random_distance()
            if abs(self.path.signed_gap(self.path_distance, candidate)) >= MIN_STEP_DISTANCE:
                self.walk_to_distance(candidate)
                return
        self.walk_to_distance(self.path.random_distance())

    # ------------------------------------------------------------------
    # Daily schedule
    # ------------------------------------------------------------------

    def _off_duty(self, current_time: datetime.datetime) -> bool:
        """Whether it is time for him to be at home rather than at work.

        Args:
            current_time: The current in-game time.
        """
        return self.hours.is_closed_at(current_time)

    def _is_unseen(self, current_time: datetime.datetime) -> bool:
        """Whether time ran on without him, so his state no longer says where he is.

        Args:
            current_time: The current in-game time.
        """
        return (self.last_update_time is None
                or abs(current_time - self.last_update_time)
                > datetime.timedelta(minutes=CATCH_UP_MINUTES))

    def is_at_stall(self, current_time: datetime.datetime) -> bool:
        """Whether he is minding his stall, which keeps his booth open.

        He counts as there until he steps off the stall onto his way home, and
        again once he is back on it. While the map is not shown he does not
        move, so he is then taken to be wherever his hours would have put
        him, just as he is placed when the map is shown again.

        Args:
            current_time: The current in-game time.
        """
        if self.homeway is None or self.stall_path is None or self._is_unseen(current_time):
            return not self._off_duty(current_time)
        return self.state in (WORKING, LEAVING_STALL)

    def _catch_up(self, current_time: datetime.datetime) -> None:
        """Put him straight where he belongs after time ran on unseen.

        Args:
            current_time: The current in-game time.
        """
        self.stop()
        self.idle_until = None
        if self._off_duty(current_time):
            self.state = AT_HOME
            self.set_path(self.homeway, self.homeway.length)
            self.fade_out(0.0)
        else:
            self.state = WORKING
            self.set_path(self.stall_path)
            self.fade_in(0.0)

    def _keep_hours(self, current_time: datetime.datetime) -> None:
        """Set off home at the end of his day, and back at the start of the next.

        A change of mind on the way simply turns him round.

        Args:
            current_time: The current in-game time.
        """
        if self._off_duty(current_time):
            if self.state == WORKING:
                self.state = LEAVING_STALL
                self.walk_to_distance(self.stall_exit_distance)
            elif self.state == WALKING_TO_WORK:
                self.state = WALKING_HOME
                self.walk_to_distance(self.homeway.length)
        else:
            if self.state == LEAVING_STALL:
                self.state = WORKING
                self.stop()
                self._rest(current_time)
            elif self.state in (WALKING_HOME, AT_HOME):
                # Out of the door, fading back in if he had gone indoors
                self.state = WALKING_TO_WORK
                self.fade_in()
                self.walk_to_distance(0.0)

    def _arrive(self, current_time: datetime.datetime) -> None:
        """Move on to the next leg once he has reached the end of this one.

        Args:
            current_time: The current in-game time.
        """
        if self.state == LEAVING_STALL:
            self.state = WALKING_HOME
            self.set_path(self.homeway, 0.0)
            self.walk_to_distance(self.homeway.length)
        elif self.state == WALKING_HOME:
            self.state = AT_HOME
            self.fade_out()
        elif self.state == WALKING_TO_WORK:
            self.state = WORKING
            self.set_path(self.stall_path, self.stall_exit_distance)
            self._rest(current_time)

    # ------------------------------------------------------------------
    # Per-frame update
    # ------------------------------------------------------------------

    def update(self, dt: float, current_time: datetime.datetime) -> None:
        """Advance the trader's behaviour, movement and animation.

        Args:
            dt: Delta time in seconds.
            current_time: The current in-game time, which paces his rests and
                his working day.
        """
        if self.homeway is not None and self.stall_path is not None:
            if self._is_unseen(current_time):
                self._catch_up(current_time)
            self._keep_hours(current_time)
        self.last_update_time = current_time

        if self.state == WORKING and self.path_target is None:
            if self.idle_until is None:
                self._rest(current_time, stagger=True)
            elif current_time >= self.idle_until:
                self._pick_new_spot()

        is_moving = self._follow_path(dt)
        if self.state == WORKING:
            if not is_moving and self.was_moving:
                # Just arrived — settle in for a while.
                self._rest(current_time)
        elif self.state != AT_HOME and self.path_target is None:
            self._arrive(current_time)

        self._animate(dt, is_moving)
