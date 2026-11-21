"""Tiredness, and resting it off at Uncle Gared's shop.

The player grows tired by the game hours they are up (`Player.tiredness`, 0 to
1): from rested to worn out in `HOURS_TO_EXHAUSTION` (40) hours, more slowly
while a meal keeps the player Well Fed (models/meal_effects.py). From 80 % on it
tells (models/drowsiness.py): the view narrows, the walk slows, the minigames go
worse. Resting brings it down by `REST_RECOVERY_PER_HOUR` an hour, so a night's
`FULL_REST_HOURS` (8) clears it whatever it was.

The first place to rest is Uncle Gared's shop (`intro.SHOP_HOUSE`), once he has
been found (the intro is done); the others are rooms booked at the inns, rested in
only until the booking is up (models/inn_rooms.py, the `until` of the limits here). The house
menu offers "Rest", which opens the
clock (`ui/helper_modules/rest_window.py`) to choose how long, in steps of
`REST_STEP_MINUTES`, from one step to `MAX_REST_HOURS`, at first until the next
sunrise (`next_sunrise`). Resting moves the game's clock on at a stroke, as a
minigame's work does; the game then catches up on its next update (at most one
midnight is crossed, so each day's work is done once).

`Tiredness` keeps the clock time it last counted to, so a jump of the clock is
counted as hours awake (a minigame's work) unless it was a rest (`rest`).
No pygame here.
"""

import datetime
from typing import Any, Optional

from .daylight import sun_hour
from .meal_effects import WELL_FED, bonus
from .intro import is_found_shop

#: Hours up, from rested to worn out
HOURS_TO_EXHAUSTION = 40.0
#: Hours of rest that clear any tiredness
FULL_REST_HOURS = 8.0
TIRE_PER_HOUR = 1.0 / HOURS_TO_EXHAUSTION
REST_RECOVERY_PER_HOUR = 1.0 / FULL_REST_HOURS

#: The longest rest, and the steps the clock's hand moves in
MAX_REST_HOURS = 24
REST_STEP_MINUTES = 15
#: The sun hour of sunrise (daylight.AMBIENT_KEYFRAMES' "Sunrise")
SUNRISE_SUN_HOUR = 6.5
#: How finely the next sunrise is looked for
_SUNRISE_SEARCH_MINUTES = 5


def can_rest_at(house: Any, intro: Optional[Any]) -> bool:
    """Whether the player may rest in this building: the uncle's shop, once he has been found."""
    return is_found_shop(house, intro)


def next_sunrise(now: datetime.datetime) -> datetime.datetime:
    """The next moment the sun rises (sun hour `SUNRISE_SUN_HOUR`) after `now`, within a day."""
    step = datetime.timedelta(minutes=_SUNRISE_SEARCH_MINUTES)
    previous = sun_hour(now)
    moment = now
    for _ in range(MAX_REST_HOURS * 60 // _SUNRISE_SEARCH_MINUTES):
        moment += step
        current = sun_hour(moment)
        if previous < SUNRISE_SUN_HOUR <= current:
            # Between the two samples: where the line through them crosses it
            share = (SUNRISE_SUN_HOUR - previous) / (current - previous)
            return moment - step + step * share
        previous = current
    return now + datetime.timedelta(hours=MAX_REST_HOURS)


def first_step(now: datetime.datetime) -> datetime.datetime:
    """The earliest moment a rest may end: the next whole step of the clock after `now`."""
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    steps = (now - midnight) // datetime.timedelta(minutes=REST_STEP_MINUTES) + 1
    return midnight + steps * datetime.timedelta(minutes=REST_STEP_MINUTES)


def latest_end(now: datetime.datetime, until: Optional[datetime.datetime] = None) -> datetime.datetime:
    """The latest moment a rest may end: `MAX_REST_HOURS` on, down to a whole step, and never past
    `until` (when a room at an inn is up, models/inn_rooms.py), which may itself be off the steps."""
    longest = first_step(now + datetime.timedelta(hours=MAX_REST_HOURS)) - datetime.timedelta(minutes=REST_STEP_MINUTES)
    return longest if until is None else min(longest, until)


def can_rest_until(now: datetime.datetime, until: Optional[datetime.datetime]) -> bool:
    """Whether there is at least one step of rest left before `until` (None: no end)."""
    return until is None or first_step(now) <= until


def snap_end(now: datetime.datetime, end: datetime.datetime,
             until: Optional[datetime.datetime] = None) -> datetime.datetime:
    """`end` put on the nearest whole step, kept between `first_step` and `latest_end`."""
    step = datetime.timedelta(minutes=REST_STEP_MINUTES)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    steps = round((end - midnight) / step)
    return min(latest_end(now, until), max(first_step(now), midnight + steps * step))


def default_end(now: datetime.datetime, until: Optional[datetime.datetime] = None) -> datetime.datetime:
    """Where the clock's hand starts: the next sunrise, on the nearest whole step (or as late as `until` allows)."""
    return snap_end(now, next_sunrise(now), until)


def tiredness_after_rest(tiredness: float, hours: float) -> float:
    return max(0.0, tiredness - hours * REST_RECOVERY_PER_HOUR)


class Tiredness:
    """Counts the hours the player is up into `player.tiredness` (see the module)."""

    def __init__(self, player: Any, now: Optional[datetime.datetime] = None) -> None:
        self.player = player
        self.counted_to: Optional[datetime.datetime] = now

    def update(self, now: datetime.datetime) -> None:
        """The hours since the last call were spent up."""
        if self.counted_to is not None and now > self.counted_to:
            hours = (now - self.counted_to).total_seconds() / 3600.0
            rate = TIRE_PER_HOUR * (1.0 - bonus(self.player, WELL_FED, now))
            self.player.tiredness = min(1.0, self.player.tiredness + hours * rate)
        self.counted_to = now

    def restart(self, now: datetime.datetime) -> None:
        """Count from `now` (a game loaded: the time before it was not this player's)."""
        self.counted_to = now

    def rest(self, game_state: Any, end: datetime.datetime) -> float:
        """Rest until `end`: the clock is moved on, the tiredness falls. The hours rested."""
        self.update(game_state.date)   # whatever was up to now was spent awake
        hours = max(0.0, (end - game_state.date).total_seconds() / 3600.0)
        game_state.date = end
        self.player.tiredness = tiredness_after_rest(self.player.tiredness, hours)
        self.counted_to = end
        return hours
