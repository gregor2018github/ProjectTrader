"""The market's rules one by one: the price, slippage, the merchants' lines, clearing, the outside walk, wishes."""
import math
import random

import pytest

from src.persistence.save_manager import _hourly_to_ticks
from src.sim.systems import market as market_module
from src.sim.systems.market import (
    apply_well_shock, clear_buyers, create_good, merchants, price, quote, ratio_for_factor,
    reference, set_price, step_news, step_noise, step_outside, tick_well_shock_day, update_target, volume_factor,
)
from tests.sim.builders import START, good_def

SLICES = 12


@pytest.fixture(autouse=True)
def pinned_market(monkeypatch):
    """The volume curve and the wish as these tests are written against."""
    for name, value in (("MARKET_VOLUME_SCARCE_RATIO", 0.9), ("MARKET_VOLUME_GLUT_RATIO", 1.1),
                        ("MARKET_VOLUME_ELASTICITY", 0.7), ("MARKET_VOLUME_FACTOR_MIN", 0.4),
                        ("MARKET_VOLUME_FACTOR_MAX", 3.0), ("WELL_WISH_SHOCK_FACTOR", 0.4),
                        ("WELL_WISH_DURATION_DAYS", 5), ("PRICE_TICKS_PER_DAY", 48), ("NEWS_SIZE_SPREAD", 0.5),
                        ("PRICE_NOISE_PERSISTENCE", 0.96), ("PRICE_NOISE_CLAMP", 0.25)):
        monkeypatch.setattr(market_module, name, value)


def a_good(price_: float = 10.0, stock: float = 1000.0, **changes):
    definition = good_def("Wood", price_, **changes)
    good = create_good(definition, START)
    good.stock = good.target_stock = stock
    return good, definition


def test_at_its_target_stock_a_good_costs_its_outside_price():
    good, _ = a_good(10.0)
    assert price(good) == 10.0


def test_scarcity_raises_the_price_and_a_glut_lowers_it():
    good, _ = a_good(10.0)
    good.stock = 500
    assert price(good) == pytest.approx(10.0 * (0.9 / 0.5) ** 0.7)
    good.stock = 10_000
    assert price(good) == pytest.approx(10.0 * 0.4)       # clamped


@pytest.mark.parametrize("factor", [0.5, 0.8, 1.25, 2.0])
def test_the_ratio_for_a_factor_gives_that_factor_back(factor):
    good, _ = a_good()
    assert volume_factor(good, ratio_for_factor(factor) * good.target_stock) == pytest.approx(factor)


def test_a_whole_order_costs_the_sum_of_its_units_and_fractions_pro_rata():
    good, _ = a_good(10.0, stock=100.0)
    assert quote(good, 3, buying=True) == pytest.approx(10.0 * sum(volume_factor(good, 100 - k) for k in range(3)))
    assert quote(good, 2.5, buying=True) == pytest.approx(
        10.0 * (volume_factor(good, 100) + volume_factor(good, 99) + 0.5 * volume_factor(good, 98)))


def test_buying_and_selling_back_cancel_out():
    good, _ = a_good(10.0, stock=500.0)
    cost = quote(good, 50, buying=True)
    good.stock -= 50
    assert quote(good, 50, buying=False) == pytest.approx(cost)


def test_a_short_slice_shares_the_stock_pro_rata_at_one_price():
    good, _ = a_good(10.0, stock=30.0)
    filled, unit_price = clear_buyers(good, {"Poor": 40.0, "Nobility": 20.0})
    assert filled == pytest.approx({"Poor": 20.0, "Nobility": 10.0})
    assert good.stock == pytest.approx(0.0)
    assert unit_price == pytest.approx(quote(a_good(10.0, stock=30.0)[0], 30.0, buying=True) / 30.0)


def test_merchants_import_back_to_the_import_line_within_the_slice_limit():
    good, definition = a_good(10.0, stock=1000.0, transport_cost=1.0, import_limit=12_000.0)
    good.stock = 300.0                                    # well below the import line
    imported, exported = merchants(good, definition, SLICES)
    assert exported == 0 and imported > 0
    assert reference(good) * volume_factor(good) == pytest.approx(11.0)    # back on the line


def test_merchants_bring_no_more_than_the_slices_share():
    good, definition = a_good(10.0, stock=1000.0, import_limit=120.0)
    good.stock = 100.0
    imported, _ = merchants(good, definition, SLICES)
    assert imported == pytest.approx(10.0)


def test_merchants_export_a_glut_down_to_the_export_line():
    good, definition = a_good(10.0, stock=1000.0, export_limit=120_000.0)
    good.stock = 3000.0
    imported, exported = merchants(good, definition, SLICES)
    assert imported == 0 and exported > 0
    assert reference(good) * volume_factor(good) == pytest.approx(9.0)


def test_between_the_lines_nobody_moves_and_the_noise_is_ignored():
    good, definition = a_good(10.0, stock=1000.0, import_limit=1000.0, export_limit=1000.0)
    good.noise = 0.09                                    # the price shows 10.94, the stock is fine
    assert merchants(good, definition, SLICES) == (0.0, 0.0)


def test_the_outside_price_walks_back_to_its_mean():
    good, definition = a_good(10.0, outside_reversion=0.1, outside_volatility=0.0)
    good.outside_dev = math.log(2.0)
    step_outside(good, definition, START, random.Random(1))
    assert good.outside_price == pytest.approx(10.0 * 2.0 ** 0.9)


def test_the_outside_price_follows_the_seasons():
    good, definition = a_good(10.0, outside_seasons={"Winter": 1.5}, outside_volatility=0.0)
    mid_winter = START.replace(day=25, hour=12)             # day 24.5 of the year: Winter's middle
    step_outside(good, definition, mid_winter, random.Random(1))
    assert good.outside_price == pytest.approx(15.0)


class Draws:
    """A generator stand-in handing out the given draws in turn."""

    def __init__(self, *values: float) -> None:
        self.values = list(values)

    def random(self) -> float:
        return self.values.pop(0)

    def gauss(self, mu: float, sigma: float) -> float:
        return self.values.pop(0)


def test_news_moves_the_outside_price_at_a_stroke_and_the_town_s_price_with_it():
    good, definition = a_good(10.0, news_chance=0.48, news_size=0.2, news_reversion=0.5)
    # The chance per tick is 0.48 / 48 = 0.01: a draw under it is news; size 0.2 x (1 + 0.5 x 0.5), sign up
    change = step_news(good, definition, Draws(0.005, 0.75, 0.2))
    assert change == pytest.approx(0.25)
    assert good.outside_price == pytest.approx(10.0 * math.exp(0.25))
    assert price(good) == pytest.approx(10.0 * math.exp(0.25))     # the stock is as it was: the reference moved


def test_news_may_as_well_be_bad_for_the_price():
    good, definition = a_good(10.0, news_chance=0.48, news_size=0.2, news_reversion=0.5)
    assert step_news(good, definition, Draws(0.005, 0.5, 0.9)) == pytest.approx(-0.2)
    assert good.outside_price == pytest.approx(10.0 * math.exp(-0.2))


def test_what_news_moved_fades_by_its_reversion_a_day():
    good, definition = a_good(10.0, news_chance=0.48, news_size=0.2, news_reversion=0.5)
    good.outside_news = 0.4
    for _ in range(48):                                              # a day of ticks, no news in any
        assert step_news(good, definition, Draws(0.5)) == 0.0
    assert good.outside_news == pytest.approx(0.2)
    assert good.outside_price == pytest.approx(10.0 * math.exp(0.2))


def test_a_good_without_news_draws_nothing():
    good, definition = a_good(10.0)
    assert step_news(good, definition, Draws()) == 0.0               # an empty Draws would raise on a draw
    assert good.outside_price == pytest.approx(10.0)


def test_the_slow_walk_keeps_what_the_news_moved():
    good, definition = a_good(10.0, outside_reversion=0.1, outside_volatility=0.0)
    good.outside_news = math.log(1.2)
    step_outside(good, definition, START, random.Random(1))
    assert good.outside_price == pytest.approx(12.0)


def test_setting_the_price_leaves_the_news_to_fade_from_there():
    good, _ = a_good(10.0)
    good.outside_news = 0.3
    set_price(good, 20.0)
    assert price(good) == pytest.approx(20.0)
    assert good.outside_dev + good.outside_news == pytest.approx(math.log(2.0))


def test_the_noise_keeps_part_of_itself_each_tick_and_stays_within_its_clamp():
    good, definition = a_good(10.0, noise_sigma=0.1)
    good.noise = 0.1
    step_noise(good, definition, Draws(0.5))                         # 0.1 x 0.96 + 0.1 x 0.5
    assert good.noise == pytest.approx(0.146)
    step_noise(good, definition, Draws(5.0))
    assert good.noise == 0.25


def test_a_well_wish_moves_the_outside_price_and_ends():
    good, _ = a_good(10.0)
    apply_well_shock(good, up=True)
    assert reference(good) == pytest.approx(14.0) and price(good) == pytest.approx(14.0)
    for _ in range(4):
        assert not tick_well_shock_day(good)
    assert tick_well_shock_day(good)
    assert reference(good) == pytest.approx(10.0)


def test_two_wishes_multiply():
    good, _ = a_good(10.0)
    apply_well_shock(good, up=True)
    apply_well_shock(good, up=False)
    assert reference(good) == pytest.approx(10.0 * 1.4 * 0.6)


def test_the_target_stock_is_days_of_demand_but_never_below_the_minimum():
    good, definition = a_good(target_stock_days=10.0, min_target_stock=100.0)
    update_target(good, definition, 50.0, glide=1.0)
    assert good.target_stock == 500.0
    update_target(good, definition, 0.0, glide=1.0)
    assert good.target_stock == 100.0


def test_an_hourly_chart_is_filled_in_to_the_ticks():
    assert _hourly_to_ticks([1.0, 3.0, 2.0]) == [1.0, 2.0, 3.0, 2.5, 2.0]
    assert _hourly_to_ticks([5.0]) == [5.0]
    assert _hourly_to_ticks([]) == []
