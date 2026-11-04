"""Households: budget, tiers bought in order, the savings cap, slices that catch up, fulfilment, needs → happiness."""
import pytest

from src.sim.state import ClassState, PlanItem
from src.sim.systems import households as hh
from src.sim.systems.households import (
    daily_income, dearness_factor, fulfilment, needs_happiness, plan, receive, slice_orders, start_day,
)
from tests.sim.builders import START, class_needs

PRICES = {"Bread": 1.0, "Cloth": 4.0, "Wine": 10.0}
NEEDS = class_needs("Commons", income=1.0, basic={"Bread": 0.5}, comfort={"Cloth": 0.1}, luxury={"Wine": 0.02},
                    weights=(0.6, 0.3, 0.1))


@pytest.fixture(autouse=True)
def pinned(monkeypatch):
    for name, value in (("SAVINGS_CAP_DAYS", 10), ("SAVINGS_RELEASE", 0.2), ("HAPPINESS_FROM_NEEDS_MIN", 10.0),
                        ("HAPPINESS_FROM_NEEDS_MAX", 85.0), ("HUNGER_THRESHOLD", 0.6), ("HUNGER_PENALTY", 20.0)):
        monkeypatch.setattr(hh, name, value)


def commons(count: int = 100, purse: float = 0.0) -> ClassState:
    return ClassState(name="Commons", count=count, base=count, happiness=70.0, purse=purse)


def test_a_class_earns_its_base_income_per_head():
    assert daily_income(commons(100), NEEDS) == 100.0


def test_a_full_budget_buys_every_tier():
    cls = commons(100)
    plan(cls, NEEDS, PRICES, START, budget=1000.0)
    assert [(i.good, i.wanted, i.planned) for i in cls.plan] == [
        ("Bread", 50.0, 50.0), ("Cloth", 10.0, 10.0), ("Wine", 2.0, 2.0)]


def test_a_short_budget_buys_the_basic_tier_first_then_a_share_of_the_next():
    cls = commons(100)
    plan(cls, NEEDS, PRICES, START, budget=70.0)          # bread 50g, cloth 40g, wine 20g
    planned = {i.good: i.planned for i in cls.plan}
    assert planned == pytest.approx({"Bread": 50.0, "Cloth": 5.0, "Wine": 0.0})


def test_the_basic_tier_is_shared_when_even_it_is_too_dear():
    cls = commons(100)
    plan(cls, NEEDS, PRICES, START, budget=25.0)
    assert cls.plan[0].planned == pytest.approx(25.0)


def test_a_dear_good_is_bought_less_by_its_elasticity_and_a_cheap_one_no_more():
    assert dearness_factor(2.0, 1.0, 1.0) == pytest.approx(0.5)
    assert dearness_factor(4.0, 1.0, 0.5) == pytest.approx(0.5)
    assert dearness_factor(0.5, 1.0, 1.0) == 1.0                    # below its outside price: the basket, no more
    assert dearness_factor(2.0, 1.0, 0.0) == 1.0


def test_what_a_dear_tier_does_not_cost_is_left_for_the_next():
    elastic = class_needs("Commons", income=1.0, basic={"Bread": 0.5}, comfort={"Cloth": 0.1},
                          luxury={"Wine": 0.02}, elasticity=(0.0, 1.0, 0.0))
    cls = commons(100)
    outside = {"Bread": 1.0, "Cloth": 2.0, "Wine": 10.0}             # cloth at twice its outside price
    plan(cls, elastic, PRICES, START, budget=80.0, outside=outside)
    planned = {i.good: i.planned for i in cls.plan}
    assert planned["Cloth"] == pytest.approx(5.0)                    # half its 10, for 20g
    assert planned["Wine"] == pytest.approx(1.0)                     # the 10g left buys half the wine
    cls.plan[1].bought = 5.0
    assert fulfilment(cls.plan)["comfort"] == pytest.approx(0.5)     # still measured against the whole basket


def test_savings_above_the_cap_leave_town():
    cls = commons(100, purse=2000.0)
    start_day(cls, NEEDS, PRICES, START)
    assert cls.purse == pytest.approx(1000.0)              # 10 days of 100g
    assert cls.today.leaked == pytest.approx(1100.0)
    assert cls.today.income == 100.0


def test_after_an_unmet_day_savings_top_up_the_budget():
    cls = commons(100, purse=500.0)
    cls.fulfilment = {"basic": 1.0, "comfort": 0.5, "luxury": 0.0}
    start_day(cls, NEEDS, PRICES, START)                   # budget 100 + 0.2 × 500 = 200: everything
    assert all(i.planned == i.wanted for i in cls.plan)


def test_each_slice_asks_for_a_share_of_what_is_still_missing():
    cls = commons(100, purse=1000.0)
    plan(cls, NEEDS, PRICES, START, budget=1000.0)
    assert slice_orders(cls, 10, PRICES)["Bread"] == pytest.approx(5.0)
    receive(cls, "Bread", 0.0, 0.0)                        # a slice that got nothing...
    assert slice_orders(cls, 5, PRICES)["Bread"] == pytest.approx(10.0)   # ...is made up later


def test_slice_orders_stop_at_the_purse():
    cls = commons(100, purse=6.0)
    plan(cls, NEEDS, PRICES, START, budget=1000.0)
    orders = slice_orders(cls, 1, PRICES)
    assert sum(u * PRICES[g] for g, u in orders.items()) == pytest.approx(6.0)


def test_what_is_bought_goes_to_the_basic_tier_first():
    cls = commons(1)
    cls.plan = [PlanItem("Wine", "basic", 1.0, 1.0, 10.0), PlanItem("Wine", "luxury", 1.0, 1.0, 10.0)]
    cls.purse = 100.0
    receive(cls, "Wine", 1.5, 15.0)
    assert [i.bought for i in cls.plan] == [1.0, 0.5]
    assert cls.purse == 85.0 and cls.today.spent == 15.0


def test_fulfilment_is_weighted_by_the_planning_prices():
    items = [PlanItem("Bread", "comfort", 10.0, 10.0, 1.0, bought=10.0),
             PlanItem("Cloth", "comfort", 10.0, 10.0, 9.0, bought=0.0)]
    assert fulfilment(items)["comfort"] == pytest.approx(0.1)
    assert fulfilment(items)["luxury"] == 1.0              # nothing wanted: met


def test_needs_met_make_a_class_happy_and_hunger_costs_extra():
    cls = commons()
    cls.fulfilment = {"basic": 1.0, "comfort": 1.0, "luxury": 1.0}
    assert needs_happiness(cls, NEEDS) == pytest.approx(85.0)
    cls.fulfilment = {"basic": 0.5, "comfort": 0.0, "luxury": 0.0}
    assert needs_happiness(cls, NEEDS) == pytest.approx(10.0 + 75.0 * 0.3 - 20.0)
