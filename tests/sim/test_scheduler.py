"""The scheduler fires each tick once, in order, at the calendar's boundaries."""
import datetime

import pytest

from src.sim import calendar as cal
from src.sim import scheduler as scheduler_module
from src.sim.calendar import DAY, EPOCH, HOUR, PRICE_TICK, SEASON, TICK_ORDER, WEEK, YEAR
from src.sim.scheduler import Scheduler

MIDNIGHT = datetime.datetime.combine(EPOCH, datetime.time())   # Monday, 1st of Spring
DAYS_PER_SEASON = 7     # pinned
DAYS_PER_YEAR = 28


@pytest.fixture(autouse=True)
def pinned_calendar():
    assert cal.DAYS_PER_SEASON == DAYS_PER_SEASON and cal.DAYS_PER_YEAR == DAYS_PER_YEAR
    assert scheduler_module.PRICE_TICK_MINUTES == 30


def recording(start: datetime.datetime):
    scheduler = Scheduler(start)
    fired = []
    for tick in TICK_ORDER:
        scheduler.subscribe(tick, lambda moment, tick=tick: fired.append((moment, tick)))
    return scheduler, fired


def test_nothing_fires_for_the_starting_moment_or_before_the_next_tick():
    scheduler, fired = recording(MIDNIGHT)
    scheduler.advance_to(MIDNIGHT)
    scheduler.advance_to(MIDNIGHT + datetime.timedelta(minutes=29, seconds=59))
    assert fired == []


def test_half_past_is_a_price_tick_only_and_the_hour_is_both():
    scheduler, fired = recording(MIDNIGHT + datetime.timedelta(hours=8))
    scheduler.advance_to(MIDNIGHT + datetime.timedelta(hours=9))
    assert [t for _, t in fired] == [PRICE_TICK, PRICE_TICK, HOUR]
    assert fired[0][0] == MIDNIGHT + datetime.timedelta(hours=8, minutes=30)


def test_a_new_season_fires_finest_first_and_the_year_rolls_over():
    last_evening = MIDNIGHT + datetime.timedelta(days=DAYS_PER_YEAR - 1, hours=23, minutes=45)
    scheduler, fired = recording(last_evening)            # Easter Sunday, late
    scheduler.advance_to(last_evening + datetime.timedelta(minutes=15))
    assert [t for _, t in fired] == [PRICE_TICK, HOUR, DAY, WEEK, SEASON, YEAR]
    new_year = fired[-1][0]
    assert cal.game_date(new_year) == cal.GameDate(cal.CALENDAR_START_YEAR + 1, 0, 1, 0)


def test_a_mid_year_season_turn_is_no_new_year():
    scheduler, fired = recording(MIDNIGHT + datetime.timedelta(days=DAYS_PER_SEASON - 1, hours=23))
    scheduler.advance_to(MIDNIGHT + datetime.timedelta(days=DAYS_PER_SEASON))
    assert [t for _, t in fired][-4:] == [HOUR, DAY, WEEK, SEASON]
    assert YEAR not in [t for _, t in fired]


def test_a_long_jump_fires_every_tick_on_the_way_in_order():
    scheduler, fired = recording(MIDNIGHT)
    scheduler.advance_to(MIDNIGHT + datetime.timedelta(days=2 * DAYS_PER_YEAR))
    counts = {tick: sum(1 for _, t in fired if t == tick) for tick in TICK_ORDER}
    assert counts == {PRICE_TICK: 2 * DAYS_PER_YEAR * 48, HOUR: 2 * DAYS_PER_YEAR * 24, DAY: 2 * DAYS_PER_YEAR,
                      WEEK: 2 * DAYS_PER_YEAR // 7, SEASON: 8, YEAR: 2}
    moments = [m for m, _ in fired]
    assert moments == sorted(moments)


def test_handlers_of_one_tick_run_in_the_order_they_subscribed():
    scheduler = Scheduler(MIDNIGHT)
    calls = []
    scheduler.subscribe(DAY, lambda m: calls.append("first"))
    scheduler.subscribe(DAY, lambda m: calls.append("second"))
    scheduler.advance_to(MIDNIGHT + datetime.timedelta(days=1))
    assert calls == ["first", "second"]


def test_a_reset_clock_does_not_catch_up():
    scheduler, fired = recording(MIDNIGHT)
    scheduler.reset(MIDNIGHT + datetime.timedelta(days=10, hours=3))
    scheduler.advance_to(MIDNIGHT + datetime.timedelta(days=10, hours=3, minutes=10))
    assert fired == []


def test_the_clock_cannot_go_back():
    scheduler = Scheduler(MIDNIGHT + datetime.timedelta(hours=1))
    with pytest.raises(ValueError):
        scheduler.advance_to(MIDNIGHT)


def test_an_unknown_tick_is_refused():
    with pytest.raises(ValueError):
        Scheduler(MIDNIGHT).subscribe("month", lambda m: None)
