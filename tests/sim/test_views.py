"""Good, Town and PopulationManager hold no numbers of their own: they show the simulation's."""
from src.models.good import Good
from src.models.institutions.town import Town
from src.models.population import PopulationManager
from src.sim import TownSpec
from src.sim.systems import market
from tests.sim.builders import good_def, plain_needs, simulation


def make():
    sim = simulation(goods=[good_def("Wood", 4.0)], needs=plain_needs({"Wood": 0.5}), town=TownSpec([10, 10, 10, 10]))
    good = Good(sim, "Wood", (0, 0, 0), 0, True)
    town = Town(0, 0, "", 1, 1, 1, 1, 32)
    town.attach(sim)
    return sim, good, town, PopulationManager(sim, town)


def test_a_good_shows_what_the_simulation_holds():
    sim, good, _, _ = make()
    state = sim.good("Wood")
    state.outside_price = 7.5
    state.stock = state.target_stock = 1000.0
    state.price_history_ticks.append(1.25)
    assert good.outside_price == 7.5 and good.price == 7.5
    assert good.market_quantity == 1000 and good.normal_quantity == 1000.0
    assert good.price_history_hourly[-1] == 1.25
    state.stock = 250.4                # scarce: the price shows it at once, whole units are shown
    assert good.market_quantity == 250 and good.price > 7.5


def test_a_good_follows_a_loaded_state():
    sim, good, _, _ = make()
    other, _, _, _ = make()
    other.good("Wood").outside_price = 2.0
    other.good("Wood").stock = other.good("Wood").target_stock
    sim.load(other.to_dict())
    assert good.outside_price == 2.0


def test_a_players_trade_through_the_good_changes_the_simulation():
    sim, good, _, _ = make()
    before = sim.good("Wood").stock
    cost = good.quote(10, buying=True)
    good.buy(10)
    assert sim.good("Wood").stock == before - 10
    assert sim.good("Wood").today.player_bought == 10
    assert sim.state.merchants_today.sales == cost              # the player pays the merchants
    assert sim.state.money_today.to_merchants == 0              # ...with the Depot's money, not the town's
    good.apply_well_shock("Price goes down")
    assert sim.good("Wood").shock_days > 0 and market.reference(sim.good("Wood")) < 4.0


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
