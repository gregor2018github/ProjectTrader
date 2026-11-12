"""The headless trader (src/sim/trader.py): it buys the dips, sells for a gain, and lives within its means."""
import datetime

import pytest

from src.sim import TownSpec, trader
from src.sim.systems import market
from tests.sim.builders import good_def, plain_needs, simulation

TOWN = TownSpec([50] * 10)


@pytest.fixture(autouse=True)
def pinned(monkeypatch):
    monkeypatch.setattr(trader, "MARKET_FEE_RATE", 0.01)
    monkeypatch.setattr(trader, "SLOT_SIZE", 20)
    monkeypatch.setattr(trader, "DAYS_PER_SEASON", 7)
    monkeypatch.setattr(market, "PRICE_NOISE_PERSISTENCE", 0.96)
    monkeypatch.setattr(market, "PRICE_NOISE_CLAMP", 0.25)


def lively_town(noise_sigma: float = 0.03):
    """A town eating bread whose price wobbles by a tenth or so."""
    return simulation(goods=[good_def("Bread", 1.0, import_limit=2000.0, transport_cost=0.1, noise_sigma=noise_sigma)],
                      needs=plain_needs({"Bread": 0.5}, income=2.0), town=TOWN, seed=3)


def test_the_flipper_lives_off_a_lively_price():
    case = trader.Case("small", money=50.0, slots=5, goods=("Bread",))
    gain, trades = trader.flip(lively_town(), case, trader.Rule(window=3, dip=0.05, take=0.05, max_share=0.12), days=40)
    assert trades >= 4 and gain > 0


def test_the_flipper_finds_nothing_in_a_dead_price():
    case = trader.Case("small", money=50.0, slots=5, goods=("Bread",))
    gain, trades = trader.flip(lively_town(noise_sigma=0.0), case,
                               trader.Rule(window=3, dip=0.05, take=0.05, max_share=0.12), days=20)
    assert (gain, trades) == (0.0, 0)


def test_the_flipper_never_holds_more_than_its_slots_or_its_money(monkeypatch):
    sim = lively_town()
    bought = []
    trade = sim.trade_with_player
    monkeypatch.setattr(sim, "trade_with_player", lambda name, units, buying: (
        bought.append((units, market.quote(sim.good(name), units, buying))) if buying else None,
        trade(name, units, buying))[1])
    case = trader.Case("tiny", money=10.0, slots=1, goods=("Bread",))
    trader.flip(sim, case, trader.Rule(window=3, dip=0.05, take=0.05, max_share=0.5), days=40)
    assert bought and all(units <= 20 for units, _ in bought)
    assert bought[0][1] * 1.01 <= 10.0


def test_the_hoarder_reports_each_year_s_gain_and_cost():
    sim = simulation(goods=[good_def("Wood", 1.0, import_limit=2000.0, transport_cost=0.1,
                                     outside_seasons={"Summer": 0.8, "Winter": 1.3})],
                     needs=plain_needs({"Wood": 0.5}, income=2.0), town=TOWN)
    result = trader.hoard(sim, ["Wood"], years=2, units=20)
    assert len(result["Wood"]) == 2
    for gain, paid in result["Wood"]:
        assert paid == pytest.approx(20 * 0.9 * 1.01, rel=0.05)      # bought near the Summer's import line
        assert gain > 0.3 * paid                                       # sold near the Winter's
