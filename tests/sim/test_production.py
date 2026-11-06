"""Workshops: margin → utilisation, hiring by workers wanted × margin, slices, the owner settling up, growth and shrinking."""
import datetime

import pytest

from src.sim import TownSpec
from src.sim.state import OwnerState, WorkshopState
from src.sim.systems import production as prod
from src.sim.systems.market import price
from tests.sim.builders import START, building, good_def, plain_needs, recipe, scenario, simulation

PRICES = {"Wheat": 1.0, "Beer": 5.0, "Wood": 1.0}
WAGE = 1.0
BREWERY = building("brewery", "brew", workers="Commons", working_capital=100.0, growth_cost=100.0)
BREW = recipe("brew", {"Beer": 1.0}, inputs={"Wheat": 2.0, "Wood": 0.5}, labour=1.0)   # costs 3.5, sells for 5


@pytest.fixture(autouse=True)
def pinned(monkeypatch):
    for name, value in (("MARGIN_FLOOR", 0.0), ("MARGIN_FULL", 0.3), ("UTILISATION_GLIDE", 1.0),
                        ("GROWTH_DESIRE", 0.9), ("GROWTH_BUSY_DAYS", 3), ("GROWTH_WINDOW_DAYS", 4),
                        ("GROWTH_STEP", 0.1), ("GROWTH_MIN_STEP", 0.5), ("SHRINK_LOSS_DAYS", 3),
                        ("SHRINK_WINDOW_DAYS", 4), ("SHRINK_STEP", 0.5), ("HIRING_MARGIN_FLOOR", 0.01),
                        ("WAGE_GLIDE", 0.1), ("TREASURY_CAP_DAYS", 10), ("TREASURY_INCOME_GLIDE", 1.0)):
        monkeypatch.setattr(prod, name, value)


def a_workshop(capacity: float = 10.0, cash: float = 1000.0) -> WorkshopState:
    return WorkshopState(id="brewery", owner_id="town", building="brewery", capacity=capacity, cash=cash)


def an_owner(cash: float = 0.0, reserve: float = 0.0, surplus_to: str = "keep") -> OwnerState:
    return OwnerState(id="town", kind="town", name="The town", cash=cash, reserve=reserve, surplus_to=surplus_to)


def test_the_margin_counts_inputs_labour_and_byproducts():
    assert prod.batch_margin(BREW, WAGE, PRICES) == pytest.approx((5.0 - 3.5) / 3.5)
    butcher = recipe("cattle", {"Beer": 1.0, "Wood": 1.0}, labour=1.0)          # two outputs
    assert prod.batch_margin(butcher, WAGE, PRICES) == pytest.approx(5.0)


@pytest.mark.parametrize("margin, utilisation", [(-0.1, 0.0), (0.0, 0.0), (0.15, 0.5), (0.3, 1.0), (2.0, 1.0)])
def test_the_margin_sets_the_utilisation(margin, utilisation):
    assert prod.wanted_utilisation(margin) == pytest.approx(utilisation)


def test_a_workshop_plans_capacity_times_utilisation_as_far_as_its_cash_goes():
    ws = a_workshop(capacity=10.0, cash=1000.0)
    assert prod.plan_wants(ws, BREW, PRICES, WAGE) == pytest.approx(10.0)       # full: margin 43 %
    poor = a_workshop(capacity=10.0, cash=7.0)                                   # two batches' worth
    prod.plan_wants(poor, BREW, PRICES, WAGE)
    assert poor.planned == pytest.approx(2.0)


def test_short_hands_are_shared_and_hiring_sets_the_workers():
    ws = a_workshop()
    prod.plan_wants(ws, BREW, PRICES, WAGE)
    assert prod.hire(ws, BREW, 0.25, 1.2) == pytest.approx(2.5)
    assert ws.planned == pytest.approx(2.5) and ws.wage == 1.2


def test_enough_hands_give_everyone_all_it_wanted():
    assert prod.share_hands(100.0, {"farm": (60.0, 0.2), "mill": (40.0, 0.9)}) == {"farm": 1.0, "mill": 1.0}


def test_short_hands_go_by_workers_wanted_times_margin():
    shares = prod.share_hands(30.0, {"farm": (40.0, 0.25), "forester": (20.0, 1.0)})
    # weights 10 and 20: the farm gets 10 of its 40 workers, the forester 20 of its 20
    assert shares["farm"] == pytest.approx(0.25) and shares["forester"] == pytest.approx(1.0)


def test_what_a_workshop_cannot_use_goes_round_again():
    shares = prod.share_hands(50.0, {"farm": (40.0, 0.25), "forester": (20.0, 1.0)})
    # first round: 50 by weight 10:20 gives 16.7 and 33.3; the forester only wants 20, so the farm gets the other 30
    assert shares["forester"] == pytest.approx(1.0) and shares["farm"] == pytest.approx(30.0 / 40.0)
    assert sum(s * w for s, (w, _) in zip(shares.values(), [(40.0, 0), (20.0, 0)])) == pytest.approx(50.0)


def test_a_workshop_at_a_loss_still_gets_a_few_hands_and_one_wanting_none_its_whole_nothing():
    shares = prod.share_hands(10.0, {"farm": (20.0, 0.5), "quarry": (10.0, -0.4), "idle": (0.0, 0.3)})
    assert 0.0 < shares["quarry"] < 0.02 and shares["idle"] == 1.0
    assert shares["farm"] * 20.0 + shares["quarry"] * 10.0 == pytest.approx(10.0)


def test_a_wage_rises_when_hands_are_short_and_falls_when_they_are_spare():
    assert prod.move_wage(1.0, wanted=200.0, hands=100.0, floor=0.5, cap=2.0) == pytest.approx(1.1)
    assert prod.move_wage(1.0, wanted=150.0, hands=100.0, floor=0.5, cap=2.0) == pytest.approx(1.05)
    assert prod.move_wage(1.0, wanted=0.0, hands=100.0, floor=0.5, cap=2.0) == pytest.approx(0.95)
    assert prod.move_wage(1.0, wanted=100.0, hands=100.0, floor=0.5, cap=2.0) == 1.0
    wage = 1.0
    for _ in range(500):
        wage = prod.move_wage(wage, wanted=1000.0, hands=100.0, floor=0.5, cap=2.0)
    assert 1.99 < wage <= 2.0                                                    # never past the cap


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
    ws.workers, ws.wage = 10.0, 1.0
    assert prod.settle_day(ws, BREWERY, owner) == 10.0                          # wages paid
    assert ws.cash == 100.0 and owner.cash == 410.0                            # topped up from 10 to 100
    ws.cash = 250.0
    ws.workers = 0.0
    prod.settle_day(ws, BREWERY, owner)
    assert ws.cash == 100.0 and owner.cash == 560.0 and owner.profits_today == 150.0


def test_an_owner_pays_out_above_its_reserve_only_if_its_rule_says_so():
    keeper = an_owner(cash=300.0, reserve=100.0, surplus_to="keep")
    assert prod.owner_day(keeper) == (0.0, 0.0) and keeper.cash == 300.0
    giver = an_owner(cash=300.0, reserve=100.0, surplus_to="townsfolk")
    assert prod.owner_day(giver) == (200.0, 0.0) and giver.cash == 100.0


def test_a_treasury_keeps_days_of_income_and_pays_the_rest_as_tribute():
    town = an_owner(cash=1000.0, reserve=100.0, surplus_to="treasury_with_tribute")
    town.profits_today, town.topped_up_today = 50.0, 20.0           # 30 a day net (the glide is 1 here)
    assert prod.owner_day(town) == (0.0, pytest.approx(700.0))       # keeps 10 days: 300
    assert town.cash == pytest.approx(300.0) and town.income_avg == pytest.approx(30.0)
    poor_town = an_owner(cash=150.0, reserve=100.0, surplus_to="treasury_with_tribute")
    assert prod.owner_day(poor_town) == (0.0, pytest.approx(50.0))   # no income yet: keeps its reserve


def test_a_window_keeps_only_its_last_days():
    log = []
    for day in (True, False, True, True, True):
        prod.remember(log, day, 4)
    assert log == [False, True, True, True]


def test_busy_days_grow_a_workshop_and_its_owner_helps_pay():
    owner = an_owner(cash=1000.0)
    ws = a_workshop(capacity=10.0, cash=50.0)
    for _ in range(3):
        prod.plan_wants(ws, BREW, PRICES, WAGE)
        prod.hire(ws, BREW, 1.0, WAGE)
    assert prod.change_capacity(ws, BREWERY, owner) == (pytest.approx(1.0), pytest.approx(100.0))
    assert ws.capacity == 11.0 and ws.cash == 0.0 and owner.cash == 950.0


def test_a_busy_workshop_without_hands_does_not_grow():
    ws = a_workshop()
    for _ in range(5):
        prod.plan_wants(ws, BREW, PRICES, WAGE)
        prod.hire(ws, BREW, 0.2, WAGE)                                          # nobody to work there
    assert not any(ws.busy_log)


def test_a_slack_day_in_the_window_does_not_stop_growth():
    ws, owner = a_workshop(capacity=10.0), an_owner(cash=1000.0)
    for share in (1.0, 0.2, 1.0, 1.0):                                         # 3 busy days of the last 4
        prod.plan_wants(ws, BREW, PRICES, WAGE)
        prod.hire(ws, BREW, share, WAGE)
    assert prod.change_capacity(ws, BREWERY, owner)[0] == pytest.approx(1.0)
    assert ws.busy_log == []                                                     # the next growth needs a window of its own
    prod.plan_wants(ws, BREW, PRICES, WAGE)
    prod.hire(ws, BREW, 1.0, WAGE)
    assert prod.change_capacity(ws, BREWERY, owner) == (0.0, 0.0)


def test_too_many_slack_days_in_the_window_stop_growth():
    ws = a_workshop(capacity=10.0)
    for share in (1.0, 0.2, 1.0, 0.2, 1.0):                                    # never 3 of the last 4
        prod.plan_wants(ws, BREW, PRICES, WAGE)
        prod.hire(ws, BREW, share, WAGE)
    assert prod.change_capacity(ws, BREWERY, an_owner(cash=1000.0)) == (0.0, 0.0)


def test_losses_shrink_a_workshop():
    ws = a_workshop(capacity=10.0)
    for _ in range(3):
        prod.plan_wants(ws, BREW, {"Wheat": 3.0, "Beer": 5.0, "Wood": 1.0}, WAGE)   # costs 7.5, sells for 5
    assert prod.change_capacity(ws, BREWERY, an_owner()) == (pytest.approx(-5.0), 0.0)


# -- in a town -----------------------------------------------------------------

def farm_town(**changes):
    """A town eating bread made by its own farm, and a farm that can make more than it eats."""
    goods = [good_def("Bread", 1.0, transport_cost=0.2, import_limit=500.0, export_limit=500.0)]
    defaults = dict(goods=goods, needs=plain_needs({"Bread": 0.5}, income=1.0), town=TownSpec([50] * 10),
                    recipes=[recipe("bake", {"Bread": 10.0}, labour=2.0)],
                    buildings=[building("bakery", "bake", workers="Commons", working_capital=50.0)],
                    scenario=scenario(("bakery", "bakery", 30.0), surplus_to="townsfolk"))   # 300 loaves for ~220 wanted
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
    sim = farm_town(needs=plain_needs({"Bread": 0.5}, income=6.0))      # a wage of 6 a worker: 12 a batch of 10 loaves
    start = sim.state.workshops["bakery"].capacity
    sim.advance_to(START.replace(hour=0) + datetime.timedelta(days=200))
    assert sim.state.workshops["bakery"].capacity < start
    assert all(c.fulfilment["basic"] == 1.0 for c in sim.state.population.classes.values())


def test_losses_with_a_good_day_among_them_still_shrink_a_workshop():
    ws = a_workshop(capacity=10.0)
    losing, earning = {"Wheat": 3.0, "Beer": 5.0, "Wood": 1.0}, PRICES
    for prices in (losing, earning, losing, losing):                         # 3 losses in the last 4 days
        prod.plan_wants(ws, BREW, prices, WAGE)
    assert prod.change_capacity(ws, BREWERY, an_owner()) == (pytest.approx(-5.0), 0.0)
    assert ws.loss_log == []


def test_a_saved_workshop_from_before_the_windows_loads_with_empty_logs():
    old = {"id": "mill", "owner_id": "town", "building": "mill", "capacity": 4.0, "cash": 50.0,
           "busy_days": 9, "unprofitable_days": 2}
    ws = WorkshopState.from_dict(old)
    assert ws.busy_log == [] and ws.loss_log == [] and ws.capacity == 4.0
    assert WorkshopState.from_dict(ws.to_dict()) == ws
