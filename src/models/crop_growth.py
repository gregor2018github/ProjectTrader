"""The crop on a field growing with the seasons, and each of its plants a little ahead or behind.

A crop's stages are the keys of its crop.json (made in the Sprite Manager's
crops area), from the bare field to the ripe crop. The field follows the game
calendar (game_calendar.py, a year of 28 days): it lies bare, ploughed, from
the harvest through the winter; it is sown at its sow day and grows through
the other stages, each an equal part of the time until its harvest day, when
the ripe crop is cut and the field is bare again. With the defaults that is
sown on the 1st of Spring and harvested at the end of Autumn.

Which stage a field is at is worked out from the date alone, so nothing needs
saving: a loaded game shows what the calendar says. Each field's sow and
harvest days are moved by up to FIELD_SEASON_JITTER_DAYS (the same for that
field every game, from its Tiled id), so no two fields keep step.

The field as a whole is at one stage, from `since` until `ends`. Its plants
are not all there at once: each has an offset of up to half of
FIELD_PLANT_SPREAD_DAYS either way and shows the stage the field is at that
much earlier or later, so near a change some already show the next stage and
some still the last, and the field turns over plant by plant within a day or
two.

The furrows of the bare field (furrows()) fade out over the first stage
after it, as the sprouts come up, and back in as the crop is harvested.
"""

import datetime
import math
import random
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..config.constants import FIELD_HARVEST_DAY, FIELD_SEASON_JITTER_DAYS, FIELD_SOW_DAY
from .game_calendar import DAYS_PER_YEAR, EPOCH

MIN_GROWING_DAYS = 1.0   # the growing season is never shorter, whatever a Tiled property says
_EPOCH = datetime.datetime.combine(EPOCH, datetime.time())
_DAY = datetime.timedelta(days=1)


def field_season(field_id: int, properties: Optional[Dict[str, Any]] = None) -> Tuple[float, float]:
    """A field's sow and harvest days of the year (0 = the 1st of Spring).

    Its Tiled object's Sow_day and Harvest_day if it has them; otherwise FIELD_SOW_DAY and
    FIELD_HARVEST_DAY, each moved by up to FIELD_SEASON_JITTER_DAYS, the same every game for that field.
    """
    properties = properties or {}
    rng = random.Random(f"field-season-{field_id}")
    sow = FIELD_SOW_DAY + rng.uniform(-FIELD_SEASON_JITTER_DAYS, FIELD_SEASON_JITTER_DAYS)
    harvest = FIELD_HARVEST_DAY + rng.uniform(-FIELD_SEASON_JITTER_DAYS, FIELD_SEASON_JITTER_DAYS)
    if 'Sow_day' in properties:
        sow = float(properties['Sow_day'])
    if 'Harvest_day' in properties:
        harvest = float(properties['Harvest_day'])
    return sow, harvest


def _days_since_epoch(moment: datetime.datetime) -> float:
    return (moment - _EPOCH) / _DAY


def _moment(days: float) -> datetime.datetime:
    return _EPOCH + datetime.timedelta(days=days)


class CropGrowth:
    """Which stage a field is at by the calendar, since when and until when."""

    def __init__(self, stages: Sequence[str], sow_day: float = FIELD_SOW_DAY,
                 harvest_day: float = FIELD_HARVEST_DAY) -> None:
        """
        Args:
            stages: The crop's stage keys, the bare field first and the ripe crop last.
            sow_day: Day of the year (0 = the 1st of Spring) the field is sown and the first sprouts come up.
            harvest_day: Day of the year the ripe crop is cut; until the next sow day the field lies bare.
        """
        if not stages:
            raise ValueError("A crop needs stages to grow through.")
        self.stages: List[str] = list(stages)
        self.sow_day: float = sow_day
        # From sowing to harvest, within one year; a harvest day before the sow day is the next year's
        growing = (harvest_day - sow_day) % DAYS_PER_YEAR
        self.growing_days: float = min(DAYS_PER_YEAR - MIN_GROWING_DAYS, max(MIN_GROWING_DAYS, growing))
        self.index: int = 0
        self.since: datetime.datetime = _EPOCH
        self.ends: datetime.datetime = _EPOCH

    @property
    def stage(self) -> str:
        """The key of the stage the field is at."""
        return self.stages[self.index]

    @property
    def days(self) -> float:
        """How long the stage it is at lasts, in game days."""
        return (self.ends - self.since) / _DAY

    def stage_at(self, moment: datetime.datetime) -> Tuple[int, datetime.datetime, datetime.datetime]:
        """The index of the stage the field is at at `moment`, and when that stage began and ends."""
        days = _days_since_epoch(moment) - self.sow_day
        year_start = math.floor(days / DAYS_PER_YEAR) * DAYS_PER_YEAR   # the last sowing, in days after the sow day
        into = days - year_start
        sowing = self.sow_day + year_start
        growing_stages = len(self.stages) - 1
        if into < self.growing_days and growing_stages:
            share = self.growing_days / growing_stages
            k = min(growing_stages - 1, int(into // share))
            return k + 1, _moment(sowing + k * share), _moment(sowing + (k + 1) * share)
        # Bare: from this year's harvest to the next sowing
        return 0, _moment(sowing + self.growing_days), _moment(sowing + DAYS_PER_YEAR)

    def update(self, now: datetime.datetime) -> bool:
        """Take up the stage the calendar puts the field at by `now`; True if the stage changed."""
        index, self.since, self.ends = self.stage_at(now)
        changed = index != self.index
        self.index = index
        return changed

    def plant_stage(self, now: datetime.datetime, offset_days: float) -> int:
        """The index of the stage a plant `offset_days` ahead of the field (behind if negative) shows."""
        return self.stage_at(now + datetime.timedelta(days=offset_days))[0]

    def furrows(self, now: datetime.datetime, fade_days: float) -> float:
        """How strongly the bare field's furrows show, 0..1: fully while it lies bare, fading out evenly
        over the stage after it, and back in over `fade_days` centred on the harvest (the ripe crop's end)."""
        index, since, ends = self.stage_at(now)
        half = datetime.timedelta(days=fade_days / 2.0)

        def risen(moment: datetime.datetime) -> float:
            """0 until half the fade before `moment`, 1 from half of it after."""
            if not half:
                return 1.0 if now >= moment else 0.0
            return min(1.0, max(0.0, (now - (moment - half)) / (2 * half)))

        last = len(self.stages) - 1
        shown = 0.0
        if index == 0:
            shown = risen(since)
        if index == 1:   # sprouting: the furrows wear away as it grows
            elapsed = (now - since) / (ends - since)
            shown = max(shown, min(1.0, max(0.0, 1.0 - elapsed)))
        if index == last:
            shown = max(shown, risen(ends))           # being harvested
        return shown
