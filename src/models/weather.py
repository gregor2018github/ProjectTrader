"""The weather: spells of clear sky, cloud and rain, one after another, in game time.

Each spell is a kind out of WEATHER_SPELLS (clear, overcast, drizzle, rain,
downpour) lasting a few game hours, after which the next is drawn from its
"next" weights. The kinds only say where the weather is heading: what the map
shows and plays - how hard it rains (`rain`), how overcast it is (`clouds`)
and how the wind slants the drops (`wind`) - glides there at
WEATHER_GLIDE_PER_HOUR, so a shower sets in and passes off rather than
switching on.

Owned by Game and advanced with the game's clock (update() each tick), so it
stops when the game is paused and runs on while the map is hidden. Drawn by
models/rain.py and map_view, heard through Ambience. Saved under "weather".
"""

import datetime
import random
from typing import Any, Dict, Optional

from ..config.constants import (
    WEATHER_GLIDE_PER_HOUR, WEATHER_SPELLS, WEATHER_START, WEATHER_WIND_TURN_CHANCE,
)

MAX_STEP_MINUTES = 60.0   # a longer jump of the clock (loading a save) counts as this much weather


def _glide(value: float, target: float, step: float) -> float:
    """*value* moved towards *target* by at most *step*."""
    if value < target:
        return min(target, value + step)
    return max(target, value - step)


class Weather:
    """The current spell and where rain, clouds and wind stand on the way to it.

    Args:
        rng: Where the spells' lengths and successors are drawn from (seed one in tests).
        kind: The spell to start in; its levels are taken over at once.
    """

    def __init__(self, rng: Optional[random.Random] = None, kind: str = WEATHER_START) -> None:
        self.rng = rng or random.Random()
        self.wind_side = 1 if self.rng.random() < 0.5 else -1
        self._start_spell(kind)
        spell = WEATHER_SPELLS[kind]
        self.rain: float = spell["rain"]
        self.clouds: float = spell["clouds"]
        self.wind: float = spell["wind"] * self.wind_side
        self._last_date: Optional[datetime.datetime] = None

    def _start_spell(self, kind: str) -> None:
        self.kind = kind
        shortest, longest = WEATHER_SPELLS[kind]["hours"]
        self.hours_left: float = self.rng.uniform(shortest, longest)
        if self.rng.random() < WEATHER_WIND_TURN_CHANCE:
            self.wind_side = -self.wind_side

    def _next_kind(self) -> str:
        weights = WEATHER_SPELLS[self.kind]["next"]
        return self.rng.choices(list(weights), weights=list(weights.values()))[0]

    @property
    def is_raining(self) -> bool:
        return self.rain > 0.0

    def update(self, date: datetime.datetime) -> None:
        """Advance by however much game time has passed since the last call."""
        last, self._last_date = self._last_date, date
        if last is None:
            return
        minutes = min((date - last).total_seconds() / 60.0, MAX_STEP_MINUTES)
        if minutes > 0:
            self.advance(minutes / 60.0)

    def advance(self, hours: float) -> None:
        """Let *hours* of game time pass: move on through the spells, and glide towards the current one."""
        self.hours_left -= hours
        while self.hours_left <= 0:
            overshoot = -self.hours_left
            self._start_spell(self._next_kind())
            self.hours_left -= overshoot
        spell = WEATHER_SPELLS[self.kind]
        step = WEATHER_GLIDE_PER_HOUR * hours
        self.rain = _glide(self.rain, spell["rain"], step)
        self.clouds = _glide(self.clouds, spell["clouds"], step)
        self.wind = _glide(self.wind, spell["wind"] * self.wind_side, step)

    def force(self, kind: str) -> None:
        """Start a spell of *kind* now (debug); the levels glide to it as usual."""
        self._start_spell(kind)

    def to_save(self) -> Dict[str, Any]:
        return {"kind": self.kind, "hours_left": self.hours_left, "rain": self.rain,
                "clouds": self.clouds, "wind": self.wind, "wind_side": self.wind_side}

    def load(self, saved: Optional[Dict[str, Any]]) -> None:
        """Take over a save's weather; a save without one (or with an unknown kind) keeps the current."""
        if not saved or saved.get("kind") not in WEATHER_SPELLS:
            self._last_date = None
            return
        self.kind = saved["kind"]
        self.hours_left = float(saved["hours_left"])
        self.rain = float(saved["rain"])
        self.clouds = float(saved["clouds"])
        self.wind = float(saved["wind"])
        self.wind_side = 1 if saved.get("wind_side", 1) >= 0 else -1
        self._last_date = None   # the saved date is not the one this weather last saw
