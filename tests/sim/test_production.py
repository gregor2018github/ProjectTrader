"""Workshops: margin → utilisation, hiring pro rata, slices, the owner settling up, growth and shrinking."""
import datetime

import pytest

from src.sim import TownSpec
from src.sim.state import OwnerState, WorkshopState
from src.sim.systems import production as prod
from src.sim.systems.market import price
from tests.sim.builders import START, building, good_def, plain_needs, recipe, scenario, simulation

PRICES = {"Wheat": 1.0, "Beer": 5.0, "Wood": 1.0}
BREWERY = building("brewery", "brew", workers="Commons", wage=1.0, working_capital=100.0, growth_cost=100.0)
BREW = recipe("brew", {"Beer": 1.0}, inputs={"Wheat": 2.0, "Wood": 0.5}, labour=1.0)   # costs 3.5, sells for 5


@pytest.fixture(autouse=True)
def pinned(monkeypatch):
    for name, value in (("MARGIN_FLOOR", 0.0), ("MARGIN_FULL", 0.3), ("UTILISATION_GLIDE", 1.0),
                        ("GROWTH_DESIRE", 0.9), ("GROWTH_AFTER_DAYS", 3), ("GROWTH_STEP", 0.1),
                        ("GROWTH_MIN_STEP", 0.5), ("SHRINK_AFTER_DAYS", 3), ("SHRINK_STEP", 0.5)):
        monkeypatch.setattr(prod, name, value)


def a_workshop(capacity: float = 10.0, cash: float = 1000.0) -> WorkshopState:
    return WorkshopState(id="brewery", owner_id="town", building="brewery", capacity=capacity, cash=cash)


def an_owner(cash: float = 0.0, reserve: float = 0.0, surplus_to: str = "keep") -> OwnerState:
    return OwnerState(id="town", kind="town", name="The town", cash=cash, reserve=reserve, surplus_to=surplus_to)


def test_the_margin_counts_inputs_labour_and_byproducts():
    assert prod.batch_margin(BREW, BREWERY, PRICES) == pytest.approx((5.0 - 3.5) / 3.5)
    butcher = recipe("cattle", {"Beer": 1.0, "Wood": 1.0}, labour=1.0)          # two outputs
    assert prod.batch_margin(butcher, BREWERY, PRICES) == pytest.approx(5.0)


@pytest.mark.parametrize("margin, utilisation", [(-0.1, 0.0), (0.0, 0.0), (0.15, 0.5), (0.3, 1.0), (2.0, 1.0)])
def test_the_margin_sets_the_utilisation(margin, utilisation):
    assert prod.wanted_utilisation(margin) == pytest.approx(utilisation)


def test_a_workshop_plans_capacity_times_utilisation_as_far_as_its_cash_goes():
    ws = a_workshop(capacity=10.0, cash=1000.0)
    assert prod.plan_wants(ws, BREWERY, BREW, PRICES) == pytest.approx(10.0)    # full: margin 43 %
    poor = a_workshop(capacity=10.0, cash=7.0)                                   # two batches' worth
    prod.plan_wants(poor, BREWERY, BREW, PRICES)
    assert poor.planned == pytest.approx(2.0)


def test_short_hands_are_shared_and_hiring_sets_the_workers():
    ws = a_workshop()
    prod.plan_wants(ws, BREWERY, BREW, PRICES)
    assert prod.labour_share_given(0.5, 100, wanted=200.0) == pytest.approx(0.25)
    assert prod.hire(ws, BREW, 0.25) == pytest.approx(2.5)
    assert ws.planned == pytest.approx(2.5)


def test_a_slice_buys_what_is_missing_and_runs_what_the_inputs_allow():
    ws = a_workshop()
    ws.planned = 6.0
    ws.input_stock = {"Wheat": 1.0}
    assert prod.slice_orders(ws, BREW, 3, PRICES) == pytest.approx({"Wheat": 3.0, "Wood": 1.0})
    ws.input_stock = {"Wheat": 4.0, "Wood": 0.5}                                # wood for one batch only
    assert prod.run_slice(ws, BREW, 3) == pytest.approx({"Beer": 1.0})
    assert ws.done == 1.0 and ws.input_stock == pytest.approx({"Wheat": 2.0, "Wood": 0.0})


def test_the_owner_tops_up_to_working_capital_and_takes_the_rest():
    owner = an_owner(cash=500.0)
    ws = a_workshop(cash=20.0)
    ws.workers = 10.0
    assert prod.settle_day(ws, BREWERY, owner) == 10.0                          # wages paid
    assert ws.cash == 100.0 and owner.cash == 410.0                            # topped up from 10 to 100
    ws.cash = 250.0
    ws.workers = 0.0
    prod.settle_day(ws, BREWERY, owner)
    assert ws.cash == 100.0 and owner.cash == 560.0 and owner.profits_today == 150.0


def test_an_owner_pays_out_above_its_reserve_only_if_its_rule_says_so():
    keeper = an_owner(cash=300.0, reserve=100.0, surplus_to="keep")
    assert prod.owner_surplus(keeper) == 0.0 and keeper.cash == 300.0
    giver = an_owner(cash=300.0, reserve=100.0, surplus_to="townsfolk")
    assert prod.owner_surplus(giver) == 200.0 and giver.cash == 100.0


def test_busy_days_grow_a_workshop_and_its_owner_helps_pay():
    owner = an_owner(cash=1000.0)
    ws = a_workshop(capacity=10.0, cash=50.0)
    for _ in range(3):
        prod.plan_wants(ws, BREWERY, BREW, PRICES)
        prod.hire(ws, BREW, 1.0)
    assert prod.change_capacity(ws, BREWERY, owner) == (pytest.approx(1.0), pytest.approx(100.0))
    assert ws.capacity == 11.0 and ws.cash == 0.0 and owner.cash == 950.0


def test_a_busy_workshop_without_hands_does_not_grow():
    ws = a_workshop()
    for _ in range(5):
        prod.plan_wants(ws, BREWERY, BREW, PRICES)
        prod.hire(ws, BREW, 0.2)                                                # nobody to work there
    assert ws.busy_days == 0


def test_losses_shrink_a_workshop():
    ws = a_workshop(capacity=10.0)
    for _ in range(3):
        prod.plan_wants(ws, BREWERY, BREW, {"Wheat": 3.0, "Beer": 5.0, "Wood": 1.0})   # costs 7.5, sells for 5
    assert prod.change_capacity(ws, BREWERY, an_owner()) == (pytest.approx(-5.0), 0.0)


# -- in a town -----------------------------------------------------------------

def farm_town(**changes):
    """A town eating bread made by its own farm, and a farm that can make more than it eats."""
    goods = [good_def("Bread", 1.0, transport_cost=0.2, import_limit=500.0, export_limit=500.0)]
    defaults = dict(goods=goods, needs=plain_needs({"Bread": 0.5}, income=1.0), town=TownSpec([50] * 10),
                    recipes=[recipe("bake", {"Bread": 10.0}, labour=2.0)],
                    buildings=[building("bakery", "bake", workers="Commons", wage=1.0, working_capital=50.0)],
                    scenario=scenario(("bakery", "bakery", 30.0)))      # 300 loaves a day for ~220 wanted
    defaults.update(changes)
    return simulation(**defaults)


def test_a_workshop_makes_what_the_town_eats_and_pays_its_workers():
    sim = farm_town()
    sim.advance_to(START.replace(hour=0) + datetime.timedelta(days=30))
    bread = sim.good("Bread")
    commons = sim.state.population.classes["Commons"]
    assert bread.yesterday.produced > 0
    assert commons.employed > 0 and commons.yesterday.wages > 0
    assert sim.state.workshops["bakery"].done_yesterday > 0
    assert price(bread) < 1.2 - 1e-9                       # below the import line: local supply
    assert abs(sim.state.money_yesterday.market_balance) < 1e-9


def test_the_owners_surplus_is_paid_out_to_the_townsfolk():
    sim = farm_town()
    sim.advance_to(START.replace(hour=0) + datetime.timedelta(days=30))
    payouts = sum(c.yesterday.payouts for c in sim.state.population.classes.values())
    assert payouts > 0
    assert sim.state.owners["town"].cash == pytest.approx(1000.0)            # back at its reserve


def test_an_unprofitable_workshop_shrinks_while_imports_feed_the_town():
    sim = farm_town(buildings=[building("bakery", "bake", workers="Commons", wage=6.0, working_capital=50.0)])
    start = sim.state.workshops["bakery"].capacity
    sim.advance_to(START.replace(hour=0) + datetime.timedelta(days=200))
    assert sim.state.workshops["bakery"].capacity < start
    assert all(c.fulfilment["basic"] == 1.0 for c in sim.state.population.classes.values())
