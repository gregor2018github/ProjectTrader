"""Tiredness and resting: tired out in 40 hours up, a night's rest clears it, the clock's limits and sunrise."""

import datetime
from types import SimpleNamespace

import pytest

from src.models import rest
from src.models.daylight import sun_hour
from src.models.intro import DONE, FIND_SHOP, SHOP_HOUSE
from src.models.player import Player
from src.models.rest import (FULL_REST_HOURS, HOURS_TO_EXHAUSTION, MAX_REST_HOURS, REST_STEP_MINUTES, Tiredness,
                             can_rest_at, default_end, first_step, latest_end, next_sunrise, snap_end)

START = datetime.datetime(1500, 1, 8, 14, 7)


def test_the_constants_the_tests_rely_on():
    assert (HOURS_TO_EXHAUSTION, FULL_REST_HOURS, MAX_REST_HOURS, REST_STEP_MINUTES) == (40.0, 8.0, 24, 15)


def test_tiredness_fills_in_forty_hours_up():
    player = Player("p", 0)
    tiredness = Tiredness(player, START)
    tiredness.update(START + datetime.timedelta(hours=20))
    assert player.tiredness == pytest.approx(0.5)
    tiredness.update(START + datetime.timedelta(hours=40))
    assert player.tiredness == pytest.approx(1.0)
    tiredness.update(START + datetime.timedelta(hours=60))
    assert player.tiredness == 1.0


def test_a_loaded_game_counts_from_its_own_date():
    player = Player("p", 0)
    tiredness = Tiredness(player, START)
    later = START + datetime.timedelta(days=30)
    tiredness.restart(later)
    tiredness.update(later + datetime.timedelta(hours=4))
    assert player.tiredness == pytest.approx(0.1)


def test_resting_moves_the_clock_on_and_brings_tiredness_down():
    player = Player("p", 0)
    player.tiredness = 0.75
    state = SimpleNamespace(date=START)
    tiredness = Tiredness(player, START)
    hours = tiredness.rest(state, START + datetime.timedelta(hours=4))
    assert hours == pytest.approx(4)
    assert state.date == START + datetime.timedelta(hours=4)
    assert player.tiredness == pytest.approx(0.25)
    tiredness.update(state.date)                 # the rested hours do not count as up
    assert player.tiredness == pytest.approx(0.25)
    tiredness.rest(state, state.date + datetime.timedelta(hours=8))
    assert player.tiredness == 0.0


def test_the_time_up_before_a_rest_is_counted_first():
    player = Player("p", 0)
    state = SimpleNamespace(date=START + datetime.timedelta(hours=20))
    tiredness = Tiredness(player, START)
    tiredness.rest(state, state.date + datetime.timedelta(hours=2))
    assert player.tiredness == pytest.approx(0.5 - 2 / 8)


def test_only_the_uncles_shop_once_he_is_found():
    shop = SimpleNamespace(name=SHOP_HOUSE)
    assert can_rest_at(shop, SimpleNamespace(stage=DONE))
    assert not can_rest_at(shop, SimpleNamespace(stage=FIND_SHOP))
    assert not can_rest_at(SimpleNamespace(name="House_9"), SimpleNamespace(stage=DONE))
    assert not can_rest_at(shop, None)


def test_the_clock_moves_in_quarter_hours_within_a_day():
    assert first_step(START) == datetime.datetime(1500, 1, 8, 14, 15)
    assert first_step(START.replace(minute=15)) == datetime.datetime(1500, 1, 8, 14, 30)
    assert latest_end(START) == datetime.datetime(1500, 1, 9, 14, 0)
    assert latest_end(START.replace(minute=0)) == datetime.datetime(1500, 1, 9, 14, 0)
    assert snap_end(START, START + datetime.timedelta(minutes=1)) == first_step(START)
    assert snap_end(START, START + datetime.timedelta(hours=30)) == latest_end(START)
    assert snap_end(START, datetime.datetime(1500, 1, 8, 20, 50)) == datetime.datetime(1500, 1, 8, 20, 45)


@pytest.mark.parametrize("now", [datetime.datetime(1500, 1, 8, 14, 7),    # an afternoon: tomorrow's
                                 datetime.datetime(1500, 1, 8, 2, 0),     # before dawn: today's
                                 datetime.datetime(1500, 2, 20, 23, 0),   # midsummer
                                 datetime.datetime(1500, 4, 2, 23, 0)])   # midwinter
def test_the_hand_starts_at_the_next_sunrise(now):
    sunrise = next_sunrise(now)
    assert now < sunrise <= now + datetime.timedelta(hours=24)
    assert sun_hour(sunrise) == pytest.approx(rest.SUNRISE_SUN_HOUR, abs=0.05)
    assert sun_hour(sunrise - datetime.timedelta(minutes=30)) < rest.SUNRISE_SUN_HOUR
    end = default_end(now)
    assert end.minute % REST_STEP_MINUTES == 0 and end.second == 0
    assert abs(end - sunrise) <= datetime.timedelta(minutes=REST_STEP_MINUTES / 2)


def test_tiredness_is_saved():
    from src.persistence import save_manager
    import inspect
    source = inspect.getsource(save_manager)
    assert '"tiredness": player.tiredness' in source
    assert 'p.get("tiredness", 0.0)' in source
