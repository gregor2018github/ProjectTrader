"""The crop on a field growing through its stages, and each of its plants a little ahead or behind.

A crop's stages are the keys of its crop.json (made in the Sprite Manager's
crops area), from the bare field to the ripe crop. A field goes round them
for ever: once ripe it is harvested and lies bare again. Each stage lasts
about FIELD_STAGE_DAYS of game time, longer or shorter at random by up to
FIELD_STAGE_VARIATION, so no two fields keep step.

The field as a whole is at one stage, from `since` for `days`. Its plants
are not all there at once: each has an offset of up to half of
FIELD_PLANT_SPREAD_DAYS either way and shows the stage the field is at that
much earlier or later, so near a change some already show the next stage and
some still the last, and the field turns over plant by plant within a day or
two.

Where a field starts comes from its Tiled object (see Field), and what it
has reached is saved with the game (to_save(), load()).
"""

import datetime
import random
from typing import Any, Dict, List, Optional, Sequence

from ..config.constants import FIELD_STAGE_DAYS, FIELD_STAGE_VARIATION, FIELD_START_JITTER_DAYS

MIN_STAGE_DAYS = 0.1   # a stage is never shorter, whatever a Tiled property says


class CropGrowth:
    """Which stage a field is at, since when and for how long."""

    def __init__(self, stages: Sequence[str], stage_days: float = FIELD_STAGE_DAYS,
                 rng: Optional[random.Random] = None) -> None:
        """
        Args:
            stages: The crop's stage keys, the bare field first and the ripe crop last.
            stage_days: How long a stage lasts on average, in game days.
            rng: Where the chance comes from; tests pass a seeded one.
        """
        if not stages:
            raise ValueError("A crop needs stages to grow through.")
        self.stages: List[str] = list(stages)
        self.stage_days: float = max(MIN_STAGE_DAYS, stage_days)
        self.rng: random.Random = rng or random.Random()
        self.index: int = 0
        self.since: datetime.datetime = datetime.datetime.min
        self.days: float = self.stage_days

    @property
    def stage(self) -> str:
        """The key of the stage the field is at."""
        return self.stages[self.index]

    @property
    def ends(self) -> datetime.datetime:
        """When the field moves on to the next stage."""
        return self.since + datetime.timedelta(days=self.days)

    def _draw_days(self) -> float:
        return max(MIN_STAGE_DAYS,
                   self.stage_days * (1.0 + self.rng.uniform(-FIELD_STAGE_VARIATION, FIELD_STAGE_VARIATION)))

    def start(self, now: datetime.datetime, stage: Optional[str] = None, day: float = 0.0) -> None:
        """Begin as a new game does: `day` days into `stage` (the first stage if unknown or None),
        give or take up to FIELD_START_JITTER_DAYS, never before the stage began."""
        self.index = self.stages.index(stage) if stage in self.stages else 0
        self.days = self._draw_days()
        day = max(0.0, day + self.rng.uniform(-FIELD_START_JITTER_DAYS, FIELD_START_JITTER_DAYS))
        self.since = now - datetime.timedelta(days=day)
        self.update(now)

    def update(self, now: datetime.datetime) -> bool:
        """Move on through every stage that has run out by `now`; True if the stage changed."""
        changed = False
        while now >= self.ends:
            self.since = self.ends
            self.index = (self.index + 1) % len(self.stages)
            self.days = self._draw_days()
            changed = True
        return changed

    def plant_stage(self, now: datetime.datetime, offset_days: float) -> int:
        """The index of the stage a plant `offset_days` ahead of the field (behind if negative) shows.

        The offset must stay under a stage's length, which FIELD_PLANT_SPREAD_DAYS does.
        """
        moment = now + datetime.timedelta(days=offset_days)
        if moment >= self.ends:
            return (self.index + 1) % len(self.stages)
        if moment < self.since:
            return (self.index - 1) % len(self.stages)
        return self.index

    def to_save(self) -> Dict[str, Any]:
        return {"stage": self.stage, "since": self.since.isoformat(), "days": self.days}

    def load(self, saved: Optional[Dict[str, Any]], now: datetime.datetime) -> bool:
        """Take over a saved state and catch up to `now`; False (and nothing changed) if there is none
        or it does not fit the crop, e.g. a stage taken out of crop.json since."""
        try:
            index = self.stages.index(saved["stage"])
            since = datetime.datetime.fromisoformat(saved["since"])
            days = max(MIN_STAGE_DAYS, float(saved["days"]))
        except (TypeError, KeyError, ValueError):
            return False
        self.index, self.since, self.days = index, since, days
        self.update(now)
        return True
