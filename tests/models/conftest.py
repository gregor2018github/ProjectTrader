"""Fixtures for the model tests: a depot with known storage, goods with flat prices, a fake game state."""

import pytest

from src.models import depot as depot_module
from src.models.depot import Depot
from src.models.good import Good
from tests.fakes import FakeGameState

# The storage layout the depot tests are written against, pinned so that
# rebalancing constants.py does not break them
SLOT_SIZE = 20
STARTING_STORAGE_SLOTS = 5
PACK_SLOTS = 10
PACK_SLOT_SIZE = 1
STARTING_LICENSES = [("Wood", 2), ("Stone", 1)]


@pytest.fixture(autouse=True)
def pinned_storage(monkeypatch):
    for name, value in (
        ("SLOT_SIZE", SLOT_SIZE),
        ("STARTING_STORAGE_SLOTS", STARTING_STORAGE_SLOTS),
        ("PACK_SLOTS", PACK_SLOTS),
        ("PACK_SLOT_SIZE", PACK_SLOT_SIZE),
        ("STARTING_LICENSES", STARTING_LICENSES),
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
    """10,000g, a 2g fee per trade, the starting storage, and year-long licenses for every good."""
    depot = Depot(money=10_000, transaction_cost=2, storage_capacity=SLOT_SIZE * STARTING_STORAGE_SLOTS)
    for good_name in depot.good_stock:
        depot.add_license(good_name, 12, game_state.date)
    return depot


@pytest.fixture
def make_good():
    """Goods priced at 10g whose market holds 1,000, so orders of a few dozen
    stay inside the volume band where the price does not move."""
    def make(name: str = "Wood", price: float = 10.0, market_quantity: int = 1000) -> Good:
        return Good(name, price, market_quantity, (0, 0, 0), 0, True)
    return make


@pytest.fixture
def wood(make_good):
    return make_good("Wood")


@pytest.fixture
def stone(make_good):
    return make_good("Stone")
