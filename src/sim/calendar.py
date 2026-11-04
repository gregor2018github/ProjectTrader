"""The game's calendar: a year of four seasons, each one week long.

The clock itself (``game_state.date``) is an ordinary ``datetime`` running on
from START_DATE, so hours, day spans and saves work as before. Only what a
moment is *called* goes through here: its year, season, day of the season and
weekday, counted in whole days since START_DATE, which is Monday, the 1st of
Spring of CALENDAR_START_YEAR. Nothing should read ``.month``, ``.year``,
``.weekday()`` or ``strftime`` dates off the clock for the player to see; the
clock's own calendar date runs about thirteen times slower than this one.

At normal speed a game day takes 8 real minutes, so a game year (28 days)
takes almost four real hours, which lets a playthrough span generations.

It is also the one place that says when a tick happens (``tick_numbers``): the
simulation's scheduler (``scheduler.py``) and the game's ``GameState.update()``
both count price ticks, hours, days, weeks, seasons and years from here.
"""
import datetime
import math
from typing import Dict, Mapping, NamedTuple, Optional, Union

from ..config.constants import CALENDAR_START_YEAR, DAYS_PER_SEASON, PRICE_TICK_MINUTES, START_DATE

SEASONS = ("Spring", "Summer", "Autumn", "Winter")
SEASON_ABBREVIATIONS = ("Spr", "Sum", "Aut", "Win")
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
DAYS_PER_YEAR = DAYS_PER_SEASON * len(SEASONS)
WINTER = SEASONS.index("Winter")
LENT_FIRST_DAY = 3                  # Lent runs from the winter's Ash Wednesday (its 3rd day) to its end

_day, _month, _year = (int(part) for part in START_DATE.split("."))
EPOCH = datetime.date(_year, _month, _day)

Moment = Union[datetime.datetime, datetime.date]

# The periods the depot's views add up over, and their length in days (None: since the start)
PERIOD_DAYS: Dict[str, Optional[int]] = {
    "Daily": 1,
    "Seasonal": DAYS_PER_SEASON,
    "Yearly": DAYS_PER_YEAR,
    "Total": None,
}


class GameDate(NamedTuple):
    """A day as the calendar names it."""
    year: int                       # e.g. 1500
    season: int                     # index into SEASONS
    day: int                        # day of the season, from 1
    weekday: int                    # index into WEEKDAYS, Monday 0

    @property
    def season_name(self) -> str:
        return SEASONS[self.season]

    @property
    def weekday_name(self) -> str:
        return WEEKDAYS[self.weekday]


def day_number(moment: Moment) -> int:
    """Whole days from the calendar's first day to *moment* (negative before it)."""
    if isinstance(moment, datetime.datetime):
        moment = moment.date()
    return (moment - EPOCH).days


def season_number(moment: Moment) -> int:
    """Seasons from the calendar's first one, for telling when a new season begins."""
    return day_number(moment) // DAYS_PER_SEASON


def year_of(moment: Moment) -> int:
    return CALENDAR_START_YEAR + day_number(moment) // DAYS_PER_YEAR


def game_date(moment: Moment) -> GameDate:
    """The year, season, day of the season and weekday of *moment*."""
    days = day_number(moment)
    years, day_of_year = divmod(days, DAYS_PER_YEAR)
    season, day_of_season = divmod(day_of_year, DAYS_PER_SEASON)
    return GameDate(CALENDAR_START_YEAR + years, season, day_of_season + 1, days % len(WEEKDAYS))


def ordinal(n: int) -> str:
    """1st, 2nd, 3rd, 4th, ... 11th, 12th, 13th, 21st."""
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def format_long(moment: Moment) -> str:
    """'Tuesday, 3rd of Spring 1500'."""
    d = game_date(moment)
    return f"{d.weekday_name}, {ordinal(d.day)} of {d.season_name} {d.year}"


def format_date(moment: Moment) -> str:
    """'3 Spring 1500'."""
    d = game_date(moment)
    return f"{d.day} {d.season_name} {d.year}"


def format_short(moment: Moment) -> str:
    """'3 Spr 1500', for charts and narrow columns."""
    d = game_date(moment)
    return f"{d.day} {SEASON_ABBREVIATIONS[d.season]} {d.year}"


def format_with_time(moment: datetime.datetime) -> str:
    """'3 Spring 1500  08:00'."""
    return f"{format_date(moment)}  {moment.hour:02d}:{moment.minute:02d}"


def seasons_to_days(seasons: int) -> int:
    return seasons * DAYS_PER_SEASON


def describe_seasons(seasons: int) -> str:
    """A span of seasons in words: '1 season', '2 seasons', '1 year', '3 years', '6 seasons'."""
    years, rest = divmod(seasons, len(SEASONS))
    if years and not rest:
        return f"{years} {'year' if years == 1 else 'years'}"
    return f"{seasons} {'season' if seasons == 1 else 'seasons'}"


def is_easter(moment: Moment) -> bool:
    """Easter Sunday is the winter's last day, so the year begins after it."""
    d = game_date(moment)
    return d.season == WINTER and d.day == DAYS_PER_SEASON


def is_lent(moment: Moment) -> bool:
    """The forty days before Easter, here the winter from its Ash Wednesday to Easter Saturday."""
    d = game_date(moment)
    return d.season == WINTER and LENT_FIRST_DAY <= d.day < DAYS_PER_SEASON


def is_fast_day(moment: Moment) -> bool:
    """A day without meat: every Friday, and all of Lent."""
    return game_date(moment).weekday == WEEKDAYS.index("Friday") or is_lent(moment)


# ---------------------------------------------------------------------------
# Ticks: the moments the simulation (and the game) act on
# ---------------------------------------------------------------------------

PRICE_TICK = "price_tick"           # every PRICE_TICK_MINUTES
HOUR = "hour"
DAY = "day"
WEEK = "week"                       # Monday to Sunday; with DAYS_PER_SEASON 7 it falls on the season's first day
SEASON = "season"
YEAR = "year"
# The order the ticks of one moment fire in, finest first
TICK_ORDER = (PRICE_TICK, HOUR, DAY, WEEK, SEASON, YEAR)

# The scheduler steps from price tick to price tick, so every coarser tick must fall on one
assert 60 % PRICE_TICK_MINUTES == 0, "PRICE_TICK_MINUTES must divide the hour"


def minute_number(moment: datetime.datetime) -> int:
    """Whole minutes from the calendar's first midnight to *moment*."""
    return day_number(moment) * 24 * 60 + moment.hour * 60 + moment.minute


def price_tick_number(moment: datetime.datetime) -> int:
    """How many PRICE_TICK_MINUTES have passed since the calendar's first day."""
    return minute_number(moment) // PRICE_TICK_MINUTES


def week_number(moment: Moment) -> int:
    """Weeks from the calendar's first one (it begins on a Monday)."""
    return day_number(moment) // len(WEEKDAYS)


def tick_numbers(moment: datetime.datetime) -> Dict[str, int]:
    """For each kind of tick, a number that changes exactly when that tick happens."""
    days = day_number(moment)
    return {
        PRICE_TICK: price_tick_number(moment),
        HOUR: days * 24 + moment.hour,
        DAY: days,
        WEEK: days // len(WEEKDAYS),
        SEASON: days // DAYS_PER_SEASON,
        YEAR: days // DAYS_PER_YEAR,
    }


def season_factor(factors: Mapping[str, float], moment: datetime.datetime) -> float:
    """A per-season factor (``{"Winter": 1.5}``; seasons left out are 1) at *moment*.

    Each season's factor holds at its middle and blends smoothly (a cosine)
    into the next one's, so a season's turn shows no jump.
    """
    if not factors:
        return 1.0
    days = day_number(moment) % DAYS_PER_YEAR + (moment.hour + moment.minute / 60) / 24
    position = (days - DAYS_PER_SEASON / 2) / DAYS_PER_SEASON     # 0 at Spring's middle, 1 at Summer's, ...
    index = math.floor(position)
    blend = (1 - math.cos(math.pi * (position - index))) / 2
    a = factors.get(SEASONS[index % len(SEASONS)], 1.0)
    b = factors.get(SEASONS[(index + 1) % len(SEASONS)], 1.0)
    return a + (b - a) * blend
