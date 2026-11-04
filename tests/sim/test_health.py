"""The health report: the market balance check and the tradability measure."""
import pytest

from src.sim import health


def good_row(day: int, price: float, stock: float = 1000.0, target: float = 1000.0, good: str = "Wood"):
    return {"day": str(day), "good": good, "price": repr(price), "reference": repr(price),
            "stock": repr(stock), "target_stock": repr(target)}


def test_a_round_trip_in_a_calm_market_costs_two_fees():
    assert health.round_trip_cost(good_row(0, 10.0), units=20, fee=2.0) == pytest.approx(4.0)


def test_a_round_trip_in_a_thin_market_costs_its_slippage_too():
    assert health.round_trip_cost(good_row(0, 10.0, stock=100.0, target=100.0), units=20, fee=2.0) > 4.0


def test_tradability_measures_the_window_range_against_the_price():
    flat = [good_row(d, 10.0) for d in range(40)]
    swing = [good_row(d, 10.0 if d % 2 else 12.0, good="Wine") for d in range(40)]
    result = {t.good: t for t in health.tradability(flat + swing, window=30, units=20, fee=2.0)}
    assert result["Wood"].median_range == 0.0 and result["Wood"].share_worth_it == 0.0
    assert result["Wood"].days == 11
    assert 2.0 / 12.0 <= result["Wine"].median_range <= 2.0 / 10.0            # a 2g range on 10g or 12g
    assert result["Wine"].share_worth_it == 1.0                                 # 2g × 20 = 40g > 2 × 4g


def test_a_stock_out_day_is_one_with_unmet_household_orders():
    rows = [{"good": "Wood", "unmet": u} for u in ("0.0", "3.5", "1e-9", "0.0")]
    assert health.short_days(rows) == {"Wood": 0.25}


def test_the_market_balance_is_measured_against_the_money_supply():
    rows = [{"money_supply": "1000.0", "market_balance": "1e-12"}, {"money_supply": "0.5", "market_balance": "0.0"}]
    assert health.market_balance(rows) == pytest.approx(1e-15)
