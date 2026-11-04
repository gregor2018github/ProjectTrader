"""The living market as a whole: the town gets fed through the day, the player's buying matters, wishes hold."""
import datetime

import pytest

from src.sim import TownSpec
from src.sim.systems import market
from tests.sim.builders import START, good_def, plain_needs, simulation

TOWN = TownSpec([50] * 10)        # 400 heads at 80 %


def bread_town(import_limit: float = 2000.0):
    """A town that eats only bread (1g a loaf, half a loaf a head a day) and has plenty of money."""
    return simulation(goods=[good_def("Bread", 1.0, import_limit=import_limit, transport_cost=0.1)],
                      needs=plain_needs({"Bread": 0.5}, income=2.0), town=TOWN)


def day(n: int, hour: int = 0) -> datetime.datetime:
    return START.replace(hour=0) + datetime.timedelta(days=n, hours=hour)


def test_a_founded_town_starts_with_its_market_at_target():
    sim = bread_town()
    bread = sim.good("Bread")
    assert bread.target_stock == 10 * 200.0                  # 10 days of 400 × 0.5 loaves
    assert bread.stock == bread.target_stock


def test_the_town_buys_its_bread_through_the_day_and_merchants_restock():
    sim = bread_town()
    sim.advance_to(day(20))
    bread = sim.good("Bread")
    assert bread.yesterday.bought == pytest.approx(bread.yesterday.wanted) and bread.yesterday.wanted > 0
    assert all(c.fulfilment["basic"] == 1.0 for c in sim.state.population.classes.values())
    assert bread.yesterday.imported > 0
    assert market.price(bread) <= 1.1 * 1.01                  # held at the import line (the target moved at midnight)


def test_the_player_buying_up_the_bread_leaves_the_town_short():
    sim = bread_town(import_limit=0.0)                        # nobody brings more in
    sim.advance_to(day(1, hour=10))
    bread = sim.good("Bread")
    sim.trade_with_player("Bread", int(bread.stock), buying=True)
    sim.advance_to(day(2))
    assert bread.yesterday.bought < bread.yesterday.wanted / 2
    assert all(c.fulfilment["basic"] < 0.5 for c in sim.state.population.classes.values())
    assert all(c.happiness_target < 50 for c in sim.state.population.classes.values())


def test_a_well_wish_moves_the_local_price_and_merchants_follow_it():
    sim = bread_town()
    sim.advance_to(day(3))
    sim.apply_well_shock("Bread", up=True)
    sim.advance_to(day(4))
    bread = sim.good("Bread")
    assert market.reference(bread) == 1.4
    assert market.price(bread) > 1.3                          # settled near the new level, not undone
    sim.advance_to(day(9))
    assert market.reference(bread) == 1.0                     # and over after five days
