"""The butcher — the first human NPC, who will trade meat at the market.

His behaviour is deliberately minimal for now: he walks his patrol path to a
new spot, stands there for the best part of an in-game hour, then shuffles
somewhere else. Trading and a real daily schedule still have to be written.
"""

import datetime
import random
from typing import List, Optional

from .npc import NPC

#: Walking speed in pixels per second at tile_size 32. Well under the player's
#: 120 — he is minding a stall, not going anywhere.
BUTCHER_SPEED = 35.0

#: How long he stays put once he has picked a spot, in in-game minutes.
IDLE_MIN_MINUTES = 40
IDLE_MAX_MINUTES = 90

#: A new spot has to be at least this far along the path to be worth walking to,
#: so he does not take a single step and call it a move.
MIN_STEP_DISTANCE = 48.0

#: Tries at rolling a far-enough spot before settling for whatever came up. A
#: path shorter than MIN_STEP_DISTANCE would otherwise loop forever.
SPOT_ATTEMPTS = 8


class TraderButcher(NPC):
    """A butcher who sells meat at the market."""

    SPRITE_FOLDER = 'trader_butcher'
    SPRITE_PREFIX = 'butcher'
    # A master butcher is a guild member who owns his stall and tools: a
    # respectable burgher, well above the commons but no gentleman.
    SOCIAL_CLASS = "Middling Sort"
    IS_TRADER = True

    def __init__(self, x: float, y: float, tile_size: int, name: str = "Butcher") -> None:
        """Place the butcher on the map.

        Args:
            x: Initial world X.
            y: Initial world Y.
            tile_size: Base tile size for scaling.
            name: Display name.
        """
        super().__init__(name, x, y, tile_size)
        self.speed = BUTCHER_SPEED * tile_size / 32.0

        self._init_human_animator(
            sprite_dir=self.sprite_dir,
            sprite_definitions=self._sprite_definitions(),
            fallback_static=f"{self.SPRITE_PREFIX}_left_static.png",
            normalize=True,
        )

        # In-game time at which he next feels like moving. None means "decide on
        # the first update", since the clock is not known at construction.
        self.idle_until: Optional[datetime.datetime] = None

    def inspect_lines(self, observer=None) -> List[str]:
        """Debug lines for the "Inspect" window, plus when he moves on."""
        lines = super().inspect_lines(observer)
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
        """Advance the butcher's behaviour, movement and animation.

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
