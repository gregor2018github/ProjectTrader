"""Prices move every PRICE_TICK_MINUTES: a day's worth of ticks, and older saves' hourly charts."""

import pytest

from src.models import good as good_module
from src.models.good import Good
from src.persistence.save_manager import _hourly_to_ticks

TICKS_PER_DAY = 48     # pinned: a tick every 30 game minutes


@pytest.fixture(autouse=True)
def pinned_ticks():
    assert good_module.PRICE_TICKS_PER_DAY == TICKS_PER_DAY


def test_a_days_ticks_close_the_daily_share_of_the_volume_gap():
    good = Good("Wood", 10.0, 1000, (0, 0, 0), 0, True)
    good.market_quantity = 0          # 1,000 short of normal
    for _ in range(TICKS_PER_DAY):
        good.recover_volume()
    # MARKET_VOLUME_DAILY_RECOVERY of the gap a day, give or take the rounding down of each tick
    expected = 1000 * good_module.MARKET_VOLUME_DAILY_RECOVERY
    assert expected - TICKS_PER_DAY <= good.market_quantity <= expected + 1


def test_a_made_up_history_has_a_daily_point_every_days_ticks():
    good = Good("Wood", 10.0, 1000, (0, 0, 0), 0, True)
    good.simulate_history(ticks=3 * TICKS_PER_DAY + 1, days=4)
    assert len(good.price_history_hourly) == 3 * TICKS_PER_DAY + 1
    assert good.price_history_daily == good.price_history_hourly[::TICKS_PER_DAY]


def test_an_hourly_chart_is_filled_in_to_the_ticks():
    assert _hourly_to_ticks([1.0, 3.0, 2.0]) == [1.0, 2.0, 3.0, 2.5, 2.0]
    assert _hourly_to_ticks([5.0]) == [5.0]
    assert _hourly_to_ticks([]) == []
