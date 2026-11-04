"""Good, Town and PopulationManager hold no numbers of their own: they show the simulation's."""
import datetime

from src.models.good import Good
from src.models.institutions.town import Town
from src.models.population import PopulationManager
from src.sim import GoodDef, Simulation, TownSpec

START = datetime.datetime(1500, 1, 1, 8, 0)


def make():
    sim = Simulation([GoodDef("Wood", 4.0, 1000, "BLACK", 0, True)], now=START, seed=3,
                     town=TownSpec([10, 10, 10, 10]))
    good = Good(sim, "Wood", (0, 0, 0), 0, True)
    town = Town(0, 0, "", 1, 1, 1, 1, 32)
    town.attach(sim)
    return sim, good, town, PopulationManager(sim, town)


def test_a_good_shows_what_the_simulation_holds():
    sim, good, _, _ = make()
    state = sim.good("Wood")
    state.walk_price = 7.5
    state.market_quantity = 1000
    state.upper_bound = 99.0
    state.price_history_ticks.append(1.25)
    assert good.walk_price == 7.5 and good.price == 7.5
    assert good.upper_bound == 99.0
    assert good.price_history_hourly[-1] == 1.25
    state.market_quantity = 250        # scarce: the price shows it at once
    assert good.market_quantity == 250 and good.price > 7.5


def test_a_good_follows_a_loaded_state():
    sim, good, _, _ = make()
    other = Simulation([GoodDef("Wood", 4.0, 1000, "BLACK", 0, True)], now=START, seed=4)
    other.good("Wood").walk_price = 2.0
    sim.load(other.to_dict())
    assert good.walk_price == 2.0


def test_a_trade_through_the_good_changes_the_simulation():
    sim, good, _, _ = make()
    good.buy(100)
    assert sim.good("Wood").market_quantity == 900
    good.apply_well_shock("Price goes down")
    assert sim.good("Wood").well_shock_remaining_days > 0


def test_the_town_and_the_population_show_the_simulations_people():
    sim, _, town, manager = make()
    pop = sim.state.population
    pop.classes["Poor"].count = 50
    pop.classes["Nobility"].happiness = 12.5
    pop.happiness = 33.0
    pop.total_population_history.append(4242)
    assert town.population_groups["Poor"] == 50
    assert town.citizens == sum(c.count for c in pop.classes.values())
    assert town.max_citizens == 40
    assert town.happiness_groups["Nobility"] == 12.5
    assert town.happiness == 33.0
    assert manager.total_population_history[-1] == 4242
    assert manager.population_history["Poor"] is pop.classes["Poor"].population_history
