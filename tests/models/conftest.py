"""Fixtures for the model tests: a depot with known storage, goods with flat prices, a fake game state."""

import pytest

from src.models import depot as depot_module
from src.models.depot import Depot
from src.models.good import Good
from src.sim import Definitions, GoodDef, Simulation
from tests.fakes import START_DATE, FakeGameState

# The storage layout the depot tests are written against, pinned so that
# rebalancing constants.py does not break them
SLOT_SIZE = 20
STARTING_STORAGE_SLOTS = 5
PACK_SLOTS = 10
PACK_SLOT_SIZE = 1
# The goods the depot keeps accounts for in these tests (the game takes them from goods.json)
GOODS = ("Wood", "Stone", "Iron", "Wool", "Hide", "Fish", "Wheat", "Wine", "Beer", "Meat",
         "Linen", "Pottery", "Candle", "Herbs", "Salt")


@pytest.fixture(autouse=True)
def pinned_storage(monkeypatch):
    for name, value in (
        ("SLOT_SIZE", SLOT_SIZE),
        ("STARTING_STORAGE_SLOTS", STARTING_STORAGE_SLOTS),
        ("PACK_SLOTS", PACK_SLOTS),
        ("PACK_SLOT_SIZE", PACK_SLOT_SIZE),
    ):
        monkeypatch.setattr(depot_module, name, value)


@pytest.fixture
def game_state(monkeypatch):
    """A FakeGameState, with the depot's coin feedback (a popup at the mouse) recorded
    in its money_feedback as ("spent" | "received", amount) instead of shown."""
    state = FakeGameState()
    monkeypatch.setattr(depot_module, "on_money_spent",
                        lambda gs, amount=0.0: gs.money_feedback.append(("spent", amount)))
    monkeypatch.setattr(depot_module, "on_money_received",
                        lambda gs, amount=0.0: gs.money_feedback.append(("received", amount)))
    return state


@pytest.fixture
def depot(game_state):
    """10,000g, a 2g fee per trade, the starting storage, and licenses of three years (12 seasons) for every good."""
    depot = Depot(money=10_000, transaction_cost=2, storage_capacity=SLOT_SIZE * STARTING_STORAGE_SLOTS, goods=GOODS)
    for good_name in depot.good_stock:
        depot.add_license(good_name, 12, game_state.date)
    return depot


@pytest.fixture
def make_good():
    """Goods priced at 10g whose market holds 1,000, so orders of a few dozen
    stay inside the volume band where the price does not move."""
    def make(name: str = "Wood", price: float = 10.0, market_quantity: int = 1000) -> Good:
        # Each good on a simulation of its own, without a town, noise or a moving outside
        # price, holding market_quantity as its target; the Good is only a view of it
        definition = GoodDef(name, "BLACK", 0, True, outside_price=price, outside_volatility=0.0, noise_sigma=0.0)
        sim = Simulation(Definitions([definition], []), now=START_DATE, seed=0)
        state = sim.good(name)
        state.stock = state.target_stock = float(market_quantity)
        return Good(sim, name, (0, 0, 0), 0, True)
    return make


@pytest.fixture
def wood(make_good):
    return make_good("Wood")


@pytest.fixture
def stone(make_good):
    return make_good("Stone")
