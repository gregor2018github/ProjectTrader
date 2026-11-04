"""The game calendar: four seasons of one week make a year, counted from START_DATE."""

import datetime

import pytest

from src.models import game_calendar as cal
from src.models.game_calendar import EPOCH

# Pinned so that changing the calendar's constants shows up here rather than in odd places
DAYS_PER_SEASON = 7
START_YEAR = 1500


@pytest.fixture(autouse=True)
def pinned_calendar():
    assert cal.DAYS_PER_SEASON == DAYS_PER_SEASON
    assert cal.CALENDAR_START_YEAR == START_YEAR


def day(n, hour=10):
    """The clock n days after the calendar's first day."""
    return datetime.datetime.combine(EPOCH, datetime.time(hour)) + datetime.timedelta(days=n)


def test_the_first_day_is_monday_the_first_of_spring():
    assert cal.game_date(day(0)) == cal.GameDate(START_YEAR, 0, 1, 0)
    assert cal.format_long(day(0)) == "Monday, 1st of Spring 1500"


@pytest.mark.parametrize("n, expected", [
    (2, "Wednesday, 3rd of Spring 1500"),
    (6, "Sunday, 7th of Spring 1500"),
    (7, "Monday, 1st of Summer 1500"),
    (15, "Tuesday, 2nd of Autumn 1500"),
    (27, "Sunday, 7th of Winter 1500"),
    (28, "Monday, 1st of Spring 1501"),
    (28 * 40 + 9, "Wednesday, 3rd of Summer 1540"),
])
def test_days_run_through_the_seasons_and_years(n, expected):
    assert cal.format_long(day(n)) == expected


def test_before_the_first_day_is_the_year_before():
    assert cal.format_long(day(-1)) == "Sunday, 7th of Winter 1499"
    assert cal.year_of(day(-60)) == 1497


def test_short_formats():
    assert cal.format_date(day(16)) == "3 Autumn 1500"
    assert cal.format_short(day(16)) == "3 Aut 1500"
    assert cal.format_with_time(day(16, hour=8)) == "3 Autumn 1500  08:00"


def test_a_season_and_a_year_begin_at_midnight():
    last_evening = day(6, hour=23)
    first_morning = day(7, hour=0)
    assert cal.season_number(last_evening) + 1 == cal.season_number(first_morning)
    assert cal.year_of(day(27, hour=23)) + 1 == cal.year_of(day(28, hour=0))


@pytest.mark.parametrize("seasons, words", [
    (1, "1 season"), (2, "2 seasons"), (4, "1 year"), (6, "6 seasons"), (12, "3 years"),
])
def test_spans_of_seasons_in_words(seasons, words):
    assert cal.describe_seasons(seasons) == words


def test_ordinals():
    assert [cal.ordinal(n) for n in (1, 2, 3, 4, 11, 12, 13, 21, 22)] == \
           ["1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd"]


def test_lent_is_the_winter_from_ash_wednesday_to_easter_saturday():
    winter = 21
    assert [cal.is_lent(day(winter + d)) for d in range(7)] == [False, False, True, True, True, True, False]
    assert cal.is_easter(day(winter + 6))
    assert not cal.is_lent(day(winter + 7))


def test_fridays_and_lent_are_fast_days():
    assert cal.is_fast_day(day(4))           # Friday, 5th of Spring
    assert not cal.is_fast_day(day(3))
    assert cal.is_fast_day(day(21 + 3))      # Thursday in Lent
    assert not cal.is_fast_day(day(21 + 6))  # Easter Sunday


def test_the_depots_periods():
    assert cal.PERIOD_DAYS == {"Daily": 1, "Seasonal": 7, "Yearly": 28, "Total": None}
