"""Abstract base class for market traders.

Every trader behaves the same way — only their artwork, name and standing
differ — so the behaviour lives here and a concrete trader is little more than
a handful of class attributes.

For now a trader walks the patrol path around his stall to a new spot, stands
there for the best part of an in-game hour, then shuffles somewhere else.

Where he works and lives is drawn on the Tiled "Movements" layer, named after
his ``TILED_PREFIX`` (``Butcher`` for the butcher):

* ``<prefix>_Market_Stall`` — polygon he walks while minding his stall.
* ``<prefix>_Homeway_Path`` — polygon or polyline leading to his house.
* ``<prefix>_Homeway_Start`` — point where he steps off the stall onto it.
* ``<prefix>_Homeway_End`` — point at his front door.
"""

import datetime
import random
from typing import TYPE_CHECKING, List, Optional

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
            fallback_static=f"{self.SPRITE_PREFIX}_left_static.png",
            normalize=True,
        )

        # In-game time at which he next feels like moving. None means "decide on
        # the first update", since the clock is not known at construction.
        self.idle_until: Optional[datetime.datetime] = None

        # Filled in by the map loader from the Tiled data.
        #: The market booth he keeps; its opening hours are his working hours.
        self.market: Optional['Market'] = None
        #: The path around his stall that he walks while at work.
        self.stall_path: Optional[PatrolPath] = None
        #: Open path from his stall to his front door. None if he has no home
        #: drawn, in which case he never leaves the stall.
        self.homeway: Optional[PatrolPath] = None

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

    def inspect_lines(self, observer=None) -> List[str]:
        """Debug lines for the "Inspect" window, plus when he moves on."""
        lines = super().inspect_lines(observer)
        lines.append(f"Market: {self.market.name if self.market else 'none'}")
        if self.homeway is not None:
            lines.append(f"Way home: {self.homeway.length:.0f} px")
        else:
            lines.append("Way home: none")
        if self.path_target is None and self.idle_until is not None:
            lines.append(f"Idle until: {self.idle_until:%H:%M}")
        return lines

    def _rest(self, current_time: datetime.datetime) -> None:
        """Stand still until some way into the next in-game hour.

        Args:
            current_time: The current in-game time.
        """
        self.idle_until = current_time + datetime.timedelta(
            minutes=random.randint(IDLE_MIN_MINUTES, IDLE_MAX_MINUTES)
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

    def update(self, dt: float, current_time: datetime.datetime) -> None:
        """Advance the trader's behaviour, movement and animation.

        Args:
            dt: Delta time in seconds.
            current_time: The current in-game time, which paces his rests.
        """
        if self.path_target is None:
            if self.idle_until is None:
                self._rest(current_time)
            elif current_time >= self.idle_until:
                self._pick_new_spot()

        is_moving = self._follow_path(dt)
        if not is_moving and self.was_moving:
            # Just arrived — settle in for a while.
            self._rest(current_time)

        self._animate(dt, is_moving)
