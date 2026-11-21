"""The harvest: when the fields are cut, by whom, how far each has got, and the shocks it leaves.

On the last HARVEST_DAYS days of Autumn the ripe crop no longer goes on its own:
it stands until somebody cuts it. Each of those days every field still standing
gets one worker, one of the Poor or Commons drawn afresh each day
(pick_workers), with hours of his own (work_day). He cuts the plants one after
another in a fixed order (harvest_order: row by row from the bottom up, back
and forth), HARVEST_MINUTES_PER_PLANT of game time each and a step on, so a bigger field
takes longer, and goes home in the evening. Heavy rain (HARVEST_RAIN_FROM)
sends him home and keeps the work waiting, so a wet autumn can leave a field
unfinished: at midnight into Winter (HARVEST_END_DAY) whatever still stands is
cleared all the same, and the field lies bare as before.

Because the order is fixed, how far a field has got is one number, the plants
cut this year (FieldHarvest.cut), and that is all the save keeps. While the map
is shown, the worker himself cuts each plant (harvest_crew.py); while it is
not, or the clock jumped (a rest, a minigame), Harvest.update() cuts as many as
the time worked allows, so the field is where the day has got to.

The shocks (stooks) the reapers set up are Shock objects on the map
(shock.py), hidden until the harvest reaches them: each stands once the plants
under and around it are cut (shock_thresholds), the first with the first plant
cut, and they all stand from the harvest's end for SHOCKS_STAND_DAYS, then are
gone at once (carting them off is for later).

TODO (economy): the harvest feeds nothing yet. A field cut could bring its wheat
to the market (the sim's town producing grain), or pay the workers a wage; see
docs/TODO.md.

No pygame here: the fields and shocks are taken as plain numbers.
"""

import datetime
import math
import random
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from ..config.constants import FIELD_HARVEST_DAY
from ..sim.calendar import DAYS_PER_YEAR, day_number

Point = Tuple[float, float]
Box = Tuple[float, float, float, float]   # left, top, right, bottom in world px

#: The harvest's last day is the day before this one, the 1st of Winter (days of the year, 0 the 1st of Spring)
HARVEST_END_DAY = int(FIELD_HARVEST_DAY)
#: The harvest runs on this many days before HARVEST_END_DAY: the last three of Autumn
HARVEST_DAYS = 3
#: Game minutes a worker stands cutting one plant, and about as long again stepping to the next
#: (a tile at a walk): a field of 300 takes some 22 hours of work, about three days
HARVEST_MINUTES_PER_PLANT = 2.5
STEP_MINUTES = 2.0
#: When a worker sets out and when he stops, by the clock, drawn per field and day within these: out
#: before dawn, as reapers were, since crossing the town takes a few game hours at a walk
WORK_START_HOURS = (5.5, 6.5)
WORK_END_HOURS = (16.5, 17.5)
#: Of a worker's hours, how long the walk out takes, which the time worked unseen leaves out
COMMUTE_HOURS = 3.0
#: Rain this heavy (Weather.rain, 0 to 1) keeps the reapers home: a proper rain, not a drizzle
HARVEST_RAIN_FROM = 0.6
#: Who is sent to the fields (NPC.SOCIAL_CLASS)
HARVEST_CLASSES = ("Poor", "Commons")
#: The shocks stand this many days after the harvest's end, then are gone
SHOCKS_STAND_DAYS = 3
#: A gap between updates longer than this, in game minutes, means the worker did not cut while it passed
CATCH_UP_MINUTES = 30
#: How far round a shock's picture its plants are looked for, in world px
SHOCK_REACH_PX = 16.0


def day_of_year(moment: datetime.datetime) -> int:
    """The day of the calendar's year, 0 being the 1st of Spring."""
    return day_number(moment) % DAYS_PER_YEAR


def harvest_year(moment: datetime.datetime) -> int:
    """The calendar year (counted from its first) a moment belongs to; one harvest each."""
    return day_number(moment) // DAYS_PER_YEAR


def is_harvest_day(moment: datetime.datetime) -> bool:
    """Whether the fields are cut on this day."""
    return HARVEST_END_DAY - HARVEST_DAYS <= day_of_year(moment) < HARVEST_END_DAY


def shocks_standing_after_harvest(moment: datetime.datetime) -> bool:
    """Whether it is in the days after the harvest's end on which all the shocks still stand."""
    return HARVEST_END_DAY <= day_of_year(moment) < HARVEST_END_DAY + SHOCKS_STAND_DAYS


def harvest_order(plants: Sequence[Point]) -> List[int]:
    """The order the plants of a field are cut in, as indices into `plants` ((x, base y) each).

    Row by row from the bottom up, the bottom row left to right and each next one back the
    other way: the reaper stands on stubble in front of the row he cuts, not behind the next.
    """
    rows: Dict[float, List[int]] = {}
    for index, (_, base_y) in enumerate(plants):
        rows.setdefault(base_y, []).append(index)
    order: List[int] = []
    for number, base_y in enumerate(sorted(rows, reverse=True)):
        row = sorted(rows[base_y], key=lambda index: plants[index][0], reverse=bool(number % 2))
        order.extend(row)
    return order


def shock_thresholds(plants: Sequence[Point], order: Sequence[int], boxes: Sequence[Box]) -> List[int]:
    """For each shock's picture (`boxes`), how many plants must be cut before it stands.

    A shock stands once every plant under its picture (and SHOCK_REACH_PX round it) is cut, or,
    off the field, once the plant nearest its foot is; the first of them already with the first
    plant cut, so the field shows the work at once.
    """
    if not plants or not order:
        return [1] * len(boxes)
    rank = {plant: position for position, plant in enumerate(order)}
    thresholds = []
    for left, top, right, bottom in boxes:
        under = [rank[index] for index, (x, y) in enumerate(plants) if index in rank
                 and left - SHOCK_REACH_PX <= x <= right + SHOCK_REACH_PX
                 and top - SHOCK_REACH_PX <= y <= bottom + SHOCK_REACH_PX]
        if under:
            thresholds.append(max(under) + 1)
        else:
            foot = ((left + right) / 2, bottom)
            nearest = min(rank, key=lambda index: math.dist(plants[index], foot))
            thresholds.append(rank[nearest] + 1)
    if thresholds:
        first = min(range(len(thresholds)), key=lambda i: thresholds[i])
        thresholds[first] = 1
    return thresholds


@dataclass(frozen=True)
class WorkDay:
    """A worker's hours on one field on one day."""
    start: datetime.datetime
    end: datetime.datetime


def work_day(field_id: int, moment: datetime.datetime) -> WorkDay:
    """The hours worked on a field on the day of `moment`: the same for that field and day every time."""
    rng = random.Random(f"harvest-hours-{field_id}-{day_number(moment)}")
    midnight = datetime.datetime.combine(moment.date(), datetime.time())
    start = midnight + datetime.timedelta(hours=rng.uniform(*WORK_START_HOURS))
    end = midnight + datetime.timedelta(hours=rng.uniform(*WORK_END_HOURS))
    return WorkDay(start, end)


def pick_workers(field_ids: Sequence[int], candidates: Sequence[str], moment: datetime.datetime,
                 avoid: Iterable[str] = ()) -> Dict[int, str]:
    """One worker per field for the day: a different one for each field, and none of those in
    `avoid` (yesterday's) while there are others. Fewer if there are not enough people.

    Args:
        field_ids: The fields to be worked today.
        candidates: Who may be sent, by name.
        moment: The day.
        avoid: Who worked yesterday, sent again only for want of anyone else.
    """
    rng = random.Random(f"harvest-crew-{day_number(moment)}")
    avoid = set(avoid)
    pool = sorted(set(candidates))
    rng.shuffle(pool)
    pool.sort(key=lambda name: name in avoid)   # stable: the rested first, in their shuffled order
    return {field_id: name for field_id, name in zip(field_ids, pool)}


def worked_minutes(field_id: int, start: datetime.datetime, end: datetime.datetime) -> float:
    """Game minutes between two moments that fall in a field's working hours on harvest days, after
    the walk out (COMMUTE_HOURS): the time a worker would have cut in."""
    total = 0.0
    day = start.date()
    while day <= end.date():
        moment = datetime.datetime.combine(day, datetime.time())
        if is_harvest_day(moment):
            hours = work_day(field_id, moment)
            overlap = min(end, hours.end) - max(start, hours.start + datetime.timedelta(hours=COMMUTE_HOURS))
            total += max(0.0, overlap.total_seconds() / 60.0)
        day += datetime.timedelta(days=1)
    return total


class FieldHarvest:
    """How far one field's harvest has got this year."""

    def __init__(self, field_id: int, plants: Sequence[Point]) -> None:
        """
        Args:
            field_id: The field's Tiled id.
            plants: Its plants' (x, base y), in the field's own order.
        """
        self.field_id = field_id
        self.plants: List[Point] = list(plants)
        self.order: List[int] = harvest_order(self.plants)
        #: The year the count is of, and how many plants of it are cut
        self.year: Optional[int] = None
        self.cut: int = 0
        #: Minutes worked unseen towards the next plant (not saved)
        self.carried: float = 0.0

    @property
    def total(self) -> int:
        return len(self.order)

    @property
    def done(self) -> bool:
        return self.cut >= self.total

    def cut_at(self, moment: datetime.datetime) -> int:
        """How many plants are cut by the harvest of the year of `moment` (0 before it starts)."""
        return self.cut if self.year == harvest_year(moment) else 0

    def cut_plants(self, moment: datetime.datetime) -> Set[int]:
        """The indices of the plants cut, as of `moment`."""
        return set(self.order[:self.cut_at(moment)])

    def share(self, moment: datetime.datetime) -> float:
        """How much of the field is cut, 0..1."""
        return self.cut_at(moment) / self.total if self.total else 1.0

    def start_year(self, moment: datetime.datetime) -> None:
        """A new year's harvest starts from nothing."""
        year = harvest_year(moment)
        if self.year != year:
            self.year, self.cut, self.carried = year, 0, 0.0

    def next_plant(self) -> Optional[int]:
        """The index of the plant to be cut next, or None once all are."""
        return None if self.done else self.order[self.cut]

    def cut_next(self) -> Optional[int]:
        """Cut the next plant; its index, or None if all were cut."""
        plant = self.next_plant()
        if plant is not None:
            self.cut += 1
        return plant

    def work(self, minutes: float) -> int:
        """Minutes worked unseen: as many plants as they cut; how many."""
        if self.done or minutes <= 0:
            return 0
        per_plant = HARVEST_MINUTES_PER_PLANT + STEP_MINUTES
        self.carried += minutes
        plants = min(self.total - self.cut, int(self.carried // per_plant))
        self.carried -= plants * per_plant
        self.cut += plants
        return plants


class Harvest:
    """Every field's harvest, and the work done while nobody watched."""

    def __init__(self, fields: Iterable[Tuple[int, Sequence[Point]]]) -> None:
        """
        Args:
            fields: (Tiled id, plants' (x, base y)) of every field with a crop to cut.
        """
        self.fields: Dict[int, FieldHarvest] = {field_id: FieldHarvest(field_id, plants)
                                                for field_id, plants in fields}
        self.last_time: Optional[datetime.datetime] = None

    def update(self, now: datetime.datetime, live: Iterable[int] = (), heavy_rain: bool = False) -> List[int]:
        """Bring every field up to `now`; returns the ids of those that changed.

        A field whose worker is on the map (`live`) is cut by him plant by plant, so it is only
        caught up after a jump of the clock; any other is cut by the time worked in its hours.

        Args:
            now: The game time.
            live: The fields a worker on the map is busy at.
            heavy_rain: Whether it rains too hard to work just now.
        """
        changed = []
        if is_harvest_day(now):
            for field in self.fields.values():
                if field.year != harvest_year(now):
                    field.start_year(now)
                    changed.append(field.field_id)
        last, self.last_time = self.last_time, now
        if last is None or now <= last or heavy_rain:
            return changed
        jumped = now - last > datetime.timedelta(minutes=CATCH_UP_MINUTES)
        live = set(live)
        for field in self.fields.values():
            if field.year != harvest_year(now) or (field.field_id in live and not jumped):
                continue
            if field.work(worked_minutes(field.field_id, last, now)) and field.field_id not in changed:
                changed.append(field.field_id)
        return changed

    def to_save(self) -> Dict[str, Any]:
        return {"fields": {str(field.field_id): {"year": field.year, "cut": field.cut}
                           for field in self.fields.values() if field.year is not None}}

    def load(self, data: Optional[Dict[str, Any]]) -> None:
        """Take up a save's harvest; a save without one has nothing cut."""
        for field in self.fields.values():
            field.year, field.cut, field.carried = None, 0, 0.0
        for key, entry in ((data or {}).get("fields") or {}).items():
            field = self.fields.get(int(key))
            if field is not None and isinstance(entry, dict):
                field.year = entry.get("year")
                field.cut = max(0, min(field.total, int(entry.get("cut", 0))))
        self.last_time = None
