"""How the length of the day follows the seasons: the "sun hour".

Everything that goes by daylight (the light over the map, the window lights,
chimney smoke, birdsong, crickets, owls, the dogs' night chorus and the fog
thinning by day) is set out for a day of Spring or Autumn, with full daylight
from 8:00 to 17:00 and night from 21:00 to 4:00. `sun_hour()` turns the clock
into the hour of such a day that looks the same: in Summer the dawn comes
earlier and the dusk later, in Winter the dawn later and the dusk earlier. The
shift grows and shrinks smoothly over the game calendar's year, at its most on
the middle day of Summer (DAYLIGHT_DAWN_SHIFT_HOURS earlier,
DAYLIGHT_DUSK_SHIFT_HOURS later) and the reverse on the middle day of Winter,
nothing in the middle of Spring and of Autumn, so there is no jump when a
season turns. In Autumn and Winter the dawns and dusks also last longer, up to
DAYLIGHT_TWILIGHT_STRETCH more where Autumn turns to Winter, growing through
Autumn and fading through Winter (twilight_stretch()), each about its middle.

Midnight to 2:00, noon and the half hour before midnight stay where they are;
between them the hours are stretched or squeezed in straight lines, so the
dawn's and the dusk's colours keep their order and only move. What goes by
the clock rather than the sun (the markets, the townsfolk going out, the
church bell) does not use this.
"""

import datetime
import math
from typing import List, Tuple

from ..config.constants import DAYLIGHT_DAWN_SHIFT_HOURS, DAYLIGHT_DUSK_SHIFT_HOURS, DAYLIGHT_TWILIGHT_STRETCH
from .game_calendar import DAYS_PER_SEASON, DAYS_PER_YEAR, SEASONS, day_number

#: The middle of Summer, in days from the 1st of Spring
MIDSUMMER = (SEASONS.index("Summer") + 0.5) * DAYS_PER_SEASON
#: Where Autumn turns to Winter, when the dawns and dusks are longest
LONGEST_TWILIGHT = SEASONS.index("Winter") * DAYS_PER_SEASON

#: The hours of a Spring or Autumn day that move with the dawn, and those that move with the dusk
_DAWN = (4.0, 8.0)      # the night ends .. full daylight
_DUSK = (17.0, 21.0)    # the sun begins to set .. night


def _day_of_year(moment: datetime.datetime) -> float:
    return day_number(moment) % DAYS_PER_YEAR + (moment.hour + moment.minute / 60.0) / 24.0


def summer_share(moment: datetime.datetime) -> float:
    """How far the year is towards midsummer: 1 on its middle day, -1 on midwinter's, 0 in mid Spring and Autumn."""
    return math.cos(2.0 * math.pi * (_day_of_year(moment) - MIDSUMMER) / DAYS_PER_YEAR)


def twilight_stretch(moment: datetime.datetime) -> float:
    """How many times as long the dawn and the dusk are: 1 in Spring and Summer, rising through Autumn to
    1 + DAYLIGHT_TWILIGHT_STRETCH where it turns to Winter, and falling back through Winter."""
    towards = math.cos(2.0 * math.pi * (_day_of_year(moment) - LONGEST_TWILIGHT) / DAYS_PER_YEAR)
    return 1.0 + DAYLIGHT_TWILIGHT_STRETCH * max(0.0, towards)


def _anchors(moment: datetime.datetime) -> List[Tuple[float, float]]:
    """(clock hour, sun hour) points of the day, the clock's in order."""
    share = summer_share(moment)
    stretch = twilight_stretch(moment)

    def span(hours: Tuple[float, float], shift: float) -> Tuple[float, float]:
        """The clock hours a Spring day's dawn or dusk runs over: moved by `shift`, stretched about its middle."""
        middle, half = (hours[0] + hours[1]) / 2.0 + shift, (hours[1] - hours[0]) / 2.0 * stretch
        return middle - half, middle + half

    dawn = span(_DAWN, -DAYLIGHT_DAWN_SHIFT_HOURS * share)
    dusk = span(_DUSK, DAYLIGHT_DUSK_SHIFT_HOURS * share)
    return [(0.0, 0.0), (2.0, 2.0),
            (dawn[0], _DAWN[0]), (dawn[1], _DAWN[1]),
            (12.5, 12.5),
            (dusk[0], _DUSK[0]), (dusk[1], _DUSK[1]),
            (23.5, 23.5), (24.0, 24.0)]


def sun_hour(moment: datetime.datetime) -> float:
    """The hour of a Spring or Autumn day (0 to 24) that looks as light or dark as `moment`."""
    hour = moment.hour + moment.minute / 60.0 + moment.second / 3600.0
    points = _anchors(moment)
    for (c0, s0), (c1, s1) in zip(points, points[1:]):
        if c0 <= hour <= c1:
            return s0 + (s1 - s0) * (hour - c0) / (c1 - c0) if c1 > c0 else s0
    return hour
