"""The simulation's save block round-trips, random generator included; older blocks and saves still load."""
import datetime
import json
import os

import pytest

from src.config.constants import SAVES_PATH
from src.persistence import save_manager
from src.sim import SIM_VERSION, Simulation, SimVersionError, load_goods, load_needs
from src.sim.systems.population import class_shares
from tests.sim.builders import START, TOWN, good_def, plain_needs, simulation


def new_sim(seed: int = 7, goods=None, needs=None) -> Simulation:
    sim = simulation(goods=goods, needs=needs, seed=seed)
    sim.presimulate(2)
    return sim


def through_json(data):
    return json.loads(json.dumps(data))


def test_a_saved_simulation_goes_on_exactly_as_the_unsaved_one():
    original = new_sim()
    original.advance(datetime.timedelta(days=3, hours=5))       # mid-morning, a plan half bought
    original.trade_with_player("Wine", 12, buying=True)
    original.apply_well_shock("Wood", up=True)

    copy = new_sim(seed=999)                       # another seed: everything must come from the save
    copy.load(through_json(original.to_dict()))
    assert copy.to_dict() == original.to_dict()
    assert copy.seed == original.seed and copy.now == original.now

    for sim in (original, copy):
        sim.advance(datetime.timedelta(days=9))
    assert copy.to_dict() == original.to_dict()


def test_the_block_is_plain_json_with_its_own_version():
    block = new_sim().to_dict()
    assert block["sim_version"] == SIM_VERSION
    assert through_json(block) == block
    _, internal, _ = block["rng"]
    assert isinstance(internal, list) and len(internal) == 625


def test_a_newer_block_is_refused():
    block = new_sim().to_dict()
    block["sim_version"] = SIM_VERSION + 1
    with pytest.raises(SimVersionError):
        new_sim().load(block)


def test_a_good_missing_from_the_save_gets_a_flat_history_as_long_and_a_dropped_one_goes():
    saved = new_sim(goods=[good_def("Wood", 1.0, 0), good_def("Amber", 3.0, 1)],
                    needs=plain_needs({"Wood": 0.5, "Amber": 0.1}))
    saved.advance(datetime.timedelta(days=2))
    sim = new_sim()
    sim.load(through_json(saved.to_dict()))
    assert list(sim.state.goods) == ["Wood", "Wine"]
    wine = sim.good("Wine")
    assert len(wine.price_history_ticks) == len(sim.good("Wood").price_history_ticks)
    assert len(set(wine.price_history_daily)) == 1


def test_a_block_from_before_the_living_market_keeps_its_stock_histories_and_people():
    """sim_version 1 (P0): a random walk and no purses; everything new starts from defaults."""
    v1 = {
        "sim_version": 1, "seed": 5, "now": START.isoformat(),
        "state": {
            "goods": [{"name": "Wood", "base_price": 1.0, "walk_price": 1.3, "market_quantity": 4321,
                       "normal_quantity": 5000, "upper_bound": 3.0, "lower_bound": 0.5,
                       "price_history_ticks": [1.0, 1.1, 1.2], "price_history_daily": [1.0, 1.2]}],
            "population": {
                "classes": [{"name": c, "count": 10 + i, "base": 12, "happiness": 66.0,
                             "happiness_history": [66.0], "population_history": [10 + i]}
                            for i, c in enumerate(["Poor", "Commons", "Middling Sort", "Nobility"])],
                "max_citizens": 60, "happiness": 66.0,
                "average_happiness_history": [66.0], "total_population_history": [46]},
        },
    }
    sim = new_sim()
    sim.load(v1, now=START)
    wood = sim.good("Wood")
    assert wood.stock == pytest.approx(wood.target_stock * 4321 / 5000)    # as short of its target as it was
    assert wood.price_history_daily == [1.0, 1.2]
    assert wood.outside_price == 1.0 and wood.target_stock > 0          # the outside price at its mean
    assert len(sim.good("Wine").price_history_ticks) == 3                # missing in the save: flat, as long
    pop = sim.state.population
    assert [c.count for c in pop.classes.values()] == [10, 11, 12, 13]
    assert all(c.purse > 0 and c.plan for c in pop.classes.values())     # a starting purse and today's plan
    sim.advance(datetime.timedelta(days=2))                              # and runs on


def _old_saves():
    if not os.path.isdir(SAVES_PATH):
        return []
    return sorted(n for n in os.listdir(SAVES_PATH) if n.endswith(".sav"))


@pytest.mark.parametrize("name", _old_saves())
def test_a_save_in_saves_still_loads_and_runs(name):
    with open(os.path.join(SAVES_PATH, name), "rb") as f:
        data = save_manager._unpack(f.read())
    goods = load_goods()
    sim = Simulation(goods, load_needs([g.name for g in goods], [c for c, _ in class_shares()]),
                     now=START, seed=1, town=TOWN)
    sim.presimulate(1)
    sim.load(data.get("sim") or save_manager._legacy_sim_block(data, sim), now=START)
    saved_goods = data["sim"]["state"]["goods"] if data.get("sim") else data["goods"]
    for gd in saved_goods:
        if gd["name"] in sim.state.goods:
            good = sim.good(gd["name"])
            if "stock" in gd:
                assert good.stock == gd["stock"]
            else:
                share = gd["market_quantity"] / gd["normal_quantity"] if gd.get("normal_quantity") else 1.0
                assert good.stock == pytest.approx(good.target_stock * share)
            assert good.price_history_daily == gd["price_history_daily"]
    sim.advance(datetime.timedelta(days=1))
