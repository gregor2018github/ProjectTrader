"""The pen's hens lay eggs into the coop's nesting box, and the pen's keeper fetches them once a day.

Each hen lays LAY_PER_DAY[season] eggs a game day (many in Spring, few in
Winter), a young hen and an old one STAGE_SHARE of that, a chick none
(chickens.Hen.stage). With no grain in the troughs they lay HUNGRY_SHARE of it,
with no water THIRSTY_SHARE, both multiplied (chicken_troughs.py): so the
troughs matter at last. What is laid gathers in the nest, a fraction of an
egg at a time, up to NEST_CAP.

The pen is not the player's: its keeper, Edric (npcs/pen_keeper.py), comes
once a game day to fetch the whole eggs (`Nest.collect`, at most once a
calendar day) and takes them to market, where they are sold to the merchants
for his class (Simulation.sell_from_townsfolk), EGGS_PER_UNIT eggs to a unit
of the good Eggs.

Saved under "eggs" (`to_save`, `load`; a save without it has an empty nest
and nothing fetched). No pygame.
"""

import datetime
import math
from typing import Any, Dict, Iterable, Optional

from ..sim.calendar import SEASONS, game_date

#: Eggs a grown hen lays a game day, by season
LAY_PER_DAY: Dict[str, float] = {"Spring": 0.85, "Summer": 0.75, "Autumn": 0.5, "Winter": 0.25}
#: Of that, what a hen lays by her stage of life
STAGE_SHARE: Dict[str, float] = {"Chick": 0.0, "Young hen": 0.5, "Hen": 1.0, "Old hen": 0.5}
#: What they lay with no grain in any trough, and with no water
HUNGRY_SHARE = 0.3
THIRSTY_SHARE = 0.3
#: The most the nesting box holds; the rest is broken or eaten
NEST_CAP = 40
#: Eggs to a unit of the good Eggs at the market
EGGS_PER_UNIT = 12
#: A jump of the clock counts for at most this many days (a long time unseen)
MAX_STEP_DAYS = 30.0


def laying_rate(stages: Iterable[str], season: str, fed: bool = True, watered: bool = True) -> float:
    """Eggs a game day the hens of these stages lay in this season, fed and watered or not."""
    per_hen = LAY_PER_DAY.get(season, 0.0)
    rate = sum(per_hen * STAGE_SHARE.get(stage, 0.0) for stage in stages)
    return rate * (1.0 if fed else HUNGRY_SHARE) * (1.0 if watered else THIRSTY_SHARE)


class Nest:
    """The coop's nesting box: the eggs in it, and what the keeper has fetched."""

    def __init__(self) -> None:
        self.eggs: float = 0.0                       # laid and not fetched, fractions included
        self.collected_on: Optional[datetime.date] = None   # the calendar day of the last fetching
        self.last_collected: int = 0                 # how many that was
        self.collected_total: int = 0
        self.rate: float = 0.0                       # eggs a day at the last update, for the window
        self._last: Optional[datetime.datetime] = None

    @property
    def whole(self) -> int:
        """The whole eggs lying in the nest."""
        return int(math.floor(self.eggs + 1e-9))

    def update(self, now: datetime.datetime, stages: Iterable[str], fed: bool = True,
               watered: bool = True) -> None:
        """Let the hens lay from the last update to `now`."""
        self.rate = laying_rate(list(stages), SEASONS[game_date(now).season], fed, watered)
        if self._last is None or now <= self._last:
            self._last = now if self._last is None else max(self._last, now)
            return
        days = min(MAX_STEP_DAYS, (now - self._last).total_seconds() / 86400.0)
        self._last = now
        self.eggs = min(float(NEST_CAP), self.eggs + self.rate * days)

    def restart(self, now: datetime.datetime) -> None:
        """Count from `now` on (after loading a save)."""
        self._last = now

    def can_collect(self, day: datetime.date) -> bool:
        """Whether the keeper may fetch eggs on this calendar day: once a day."""
        return self.collected_on != day

    def collect(self, day: datetime.date) -> int:
        """The keeper fetches the whole eggs; how many (0 if he has been today already)."""
        if not self.can_collect(day):
            return 0
        taken = self.whole
        self.eggs -= taken
        self.collected_on = day
        self.last_collected = taken
        self.collected_total += taken
        return taken

    # -- the save -------------------------------------------------------------------

    def to_save(self) -> Dict[str, Any]:
        return {"eggs": round(self.eggs, 5),
                "collected_on": self.collected_on.isoformat() if self.collected_on else None,
                "last_collected": self.last_collected, "collected_total": self.collected_total}

    def load(self, data: Any) -> None:
        """A save's nest; one without it (or unreadable) has an empty nest and nothing fetched."""
        self.__init__()
        if not isinstance(data, dict):
            return
        try:
            self.eggs = min(float(NEST_CAP), max(0.0, float(data.get("eggs", 0.0))))
            self.last_collected = max(0, int(data.get("last_collected", 0)))
            self.collected_total = max(0, int(data.get("collected_total", 0)))
            day = data.get("collected_on")
            self.collected_on = datetime.date.fromisoformat(day) if day else None
        except (TypeError, ValueError):
            self.__init__()
