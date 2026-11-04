"""Prices move every PRICE_TICK_MINUTES: a day's worth of ticks, and older saves' hourly charts."""

import random

import pytest

from src.sim.systems import market as market_module
from src.sim.systems.market import create_good, recover_volume, simulate_history
from src.persistence.save_manager import _hourly_to_ticks

TICKS_PER_DAY = 48     # pinned: a tick every 30 game minutes


@pytest.fixture(autouse=True)
def pinned_ticks():
    assert market_module.PRICE_TICKS_PER_DAY == TICKS_PER_DAY


def test_a_days_ticks_close_the_daily_share_of_the_volume_gap():
    good = create_good("Wood", 10.0, 1000, random.Random(0))
    good.market_quantity = 0          # 1,000 short of normal
    for _ in range(TICKS_PER_DAY):
        recover_volume(good)
    # MARKET_VOLUME_DAILY_RECOVERY of the gap a day, give or take the rounding down of each tick
    expected = 1000 * market_module.MARKET_VOLUME_DAILY_RECOVERY
    assert expected - TICKS_PER_DAY <= good.market_quantity <= expected + 1


def test_a_made_up_history_has_a_daily_point_every_days_ticks():
    good = create_good("Wood", 10.0, 1000, random.Random(0))
    simulate_history(good, ticks=3 * TICKS_PER_DAY + 1, days=4, rng=random.Random(1))
    assert len(good.price_history_ticks) == 3 * TICKS_PER_DAY + 1
    assert good.price_history_daily == good.price_history_ticks[::TICKS_PER_DAY]


def test_an_hourly_chart_is_filled_in_to_the_ticks():
    assert _hourly_to_ticks([1.0, 3.0, 2.0]) == [1.0, 2.0, 3.0, 2.5, 2.0]
    assert _hourly_to_ticks([5.0]) == [5.0]
    assert _hourly_to_ticks([]) == []
