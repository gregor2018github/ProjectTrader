"""The weather: spells of clear sky, cloud, rain and fog, one after another, in game time.

Each spell is a kind out of WEATHER_SPELLS (clear, overcast, a shower:
drizzle, rain, downpour, clearing; and mist and fog) lasting some game hours,
after which the next is drawn from its "next" weights. The kinds only say where the weather is heading: what the map
shows and plays - how hard it rains (`rain`), how overcast it is (`clouds`)
and how the wind slants the drops (`wind`) - glides there at
WEATHER_GLIDE_PER_HOUR, so a shower sets in and passes off rather than
switching on.

The fog (`fog`, 0 to 1) glides more slowly still (FOG_GLIDE_PER_HOUR), so
it rolls in and lifts over hours. Where it heads is the spell's fog, or the
ground's own mist when the ground is wet and it has stopped raining
(FOG_FROM_WETNESS), whichever is more, times the share of it the hour of the
day allows (FOG_BY_HOUR): thick before dawn, mostly burnt off by noon. It is
drawn by models/fog.py.

The ground's `wetness` (0 dry to 1 soaked) follows the rain more slowly:
it rises while it rains (PUDDLE_FILL_PER_HOUR at full rain) and dries out
once it stops (PUDDLE_DRY_PER_HOUR, slower under cloud). The puddles
(models/puddles.py) grow and dry with it.

Owned by Game and advanced with the game's clock (update() each tick), so it
stops when the game is paused and runs on while the map is hidden. Drawn by
models/rain.py, models/fog.py and map_view, heard through Ambience. Saved under "weather".
"""

import datetime
import random
from typing import Any, Dict, Optional

from ..config.constants import (
    FOG_BY_HOUR, FOG_FROM_WETNESS, FOG_GLIDE_PER_HOUR, PUDDLE_DRY_PER_HOUR, PUDDLE_FILL_PER_HOUR, WEATHER_GLIDE_PER_HOUR, WEATHER_SPELLS, WEATHER_START, WEATHER_WIND_TURN_CHANCE,
)

MAX_STEP_MINUTES = 60.0   # a longer jump of the clock (loading a save) counts as this much weather


def _glide(value: float, target: float, step: float) -> float:
    """*value* moved towards *target* by at most *step*."""
    if value < target:
        return min(target, value + step)
    return max(target, value - step)


def fog_share_at(hour: float) -> float:
    """How much of the fog the hour of the day allows (FOG_BY_HOUR, smoothly between its points)."""
    hour %= 24.0
    for (h0, v0), (h1, v1) in zip(FOG_BY_HOUR, FOG_BY_HOUR[1:]):
        if h0 <= hour <= h1:
            t = (hour - h0) / (h1 - h0) if h1 > h0 else 0.0
            t = t * t * (3 - 2 * t)   # eased, so the fog does not turn sharply at the points
            return v0 + (v1 - v0) * t
    return FOG_BY_HOUR[-1][1]


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
        self.wetness: float = 0.0
        self._last_date: Optional[datetime.datetime] = None
        self._hour: Optional[float] = None   # the hour of the day last seen, for FOG_BY_HOUR
        # Debug (the settings' weather page), not saved: the spell does not run out, and its fog
        # is not thinned by the hour
        self.held: bool = False
        self.fog: float = self.fog_target()

    def _start_spell(self, kind: str) -> None:
        self.kind = kind
        shortest, longest = WEATHER_SPELLS[kind]["hours"]
        self.hours_left: float = self.rng.uniform(shortest, longest)
        if self.rng.random() < WEATHER_WIND_TURN_CHANCE:
            self.wind_side = -self.wind_side

    def _next_kind(self) -> str:
        weights = WEATHER_SPELLS[self.kind]["next"]
        return self.rng.choices(list(weights), weights=list(weights.values()))[0]

    def fog_target(self) -> float:
        """The fog the weather is heading for now: the spell's or the wet ground's, as the hour allows."""
        ground = FOG_FROM_WETNESS * self.wetness * (1.0 - min(1.0, self.rain * 4))
        share = 1.0 if self._hour is None or self.held else fog_share_at(self._hour)
        return max(WEATHER_SPELLS[self.kind].get("fog", 0.0), ground) * share

    @property
    def is_raining(self) -> bool:
        return self.rain > 0.0

    def update(self, date: datetime.datetime) -> None:
        """Advance by however much game time has passed since the last call."""
        last, self._last_date = self._last_date, date
        self._hour = date.hour + date.minute / 60.0
        if last is None:
            return
        minutes = min((date - last).total_seconds() / 60.0, MAX_STEP_MINUTES)
        if minutes > 0:
            self.advance(minutes / 60.0)

    def advance(self, hours: float) -> None:
        """Let *hours* of game time pass: move on through the spells, and glide towards the current one."""
        if not self.held:
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
        self.fog = _glide(self.fog, self.fog_target(), FOG_GLIDE_PER_HOUR * hours)
        if self.rain > 0:
            self.wetness = min(1.0, self.wetness + PUDDLE_FILL_PER_HOUR * self.rain * hours)
        else:
            self.wetness = max(0.0, self.wetness - PUDDLE_DRY_PER_HOUR * (1 - 0.5 * self.clouds) * hours)

    def force(self, kind: str, at_once: bool = False) -> None:
        """Start a spell of *kind* now (debug); the levels glide to it as usual, or are there *at_once*."""
        self._start_spell(kind)
        if at_once:
            spell = WEATHER_SPELLS[kind]
            self.rain = spell["rain"]
            self.clouds = spell["clouds"]
            self.wind = spell["wind"] * self.wind_side
            self.fog = self.fog_target()

    def to_save(self) -> Dict[str, Any]:
        return {"kind": self.kind, "hours_left": self.hours_left, "rain": self.rain,
                "clouds": self.clouds, "wind": self.wind, "wind_side": self.wind_side,
                "wetness": self.wetness, "fog": self.fog}

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
        self.wetness = float(saved.get("wetness", 0.0))
        self.fog = float(saved.get("fog", 0.0))
        self._last_date = None   # the saved date is not the one this weather last saw
