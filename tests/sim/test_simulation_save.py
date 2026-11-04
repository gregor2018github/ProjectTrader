"""The simulation's save block round-trips, random generator included; old saves still load."""
import datetime
import json
import os

import pytest

from src.config.constants import SAVES_PATH
from src.persistence import save_manager
from src.sim import SIM_VERSION, GoodDef, Simulation, SimVersionError, TownSpec, load_goods
from src.sim.systems import market

START = datetime.datetime(1500, 1, 1, 8, 0)
GOODS = [GoodDef("Wood", 1.0, 5000, "BLACK", 0, True), GoodDef("Wine", 10.0, 500, "RED", 1, False)]
TOWN = TownSpec([6, 8, 0, 12, 5, 20])


def new_sim(seed: int = 7, goods=GOODS) -> Simulation:
    sim = Simulation(goods, now=START, seed=seed, town=TOWN)
    sim.presimulate(2)
    return sim


def through_json(data):
    return json.loads(json.dumps(data))


def test_a_saved_simulation_goes_on_exactly_as_the_unsaved_one():
    original = new_sim()
    original.advance(datetime.timedelta(days=3, hours=5))
    market.take(original.good("Wine"), 120)
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
    version, internal, _ = block["rng"]
    assert isinstance(internal, list) and len(internal) == 625


def test_a_newer_block_is_refused():
    block = new_sim().to_dict()
    block["sim_version"] = SIM_VERSION + 1
    with pytest.raises(SimVersionError):
        new_sim().load(block)


def test_a_good_missing_from_the_save_gets_a_history_as_long_and_a_dropped_one_goes():
    saved = new_sim(goods=[GOODS[0], GoodDef("Amber", 3.0, 100, "GOLD", 2, False)])
    saved.advance(datetime.timedelta(days=2))
    sim = new_sim()
    sim.load(through_json(saved.to_dict()))
    assert list(sim.state.goods) == ["Wood", "Wine"]
    assert len(sim.good("Wine").price_history_ticks) == len(sim.good("Wood").price_history_ticks)
    assert len(sim.good("Wine").price_history_daily) == len(sim.good("Wood").price_history_daily)


def _old_saves():
    if not os.path.isdir(SAVES_PATH):
        return []
    return sorted(n for n in os.listdir(SAVES_PATH) if n.endswith(".sav"))


@pytest.mark.parametrize("name", _old_saves())
def test_a_save_from_before_the_sim_block_still_loads(name):
    with open(os.path.join(SAVES_PATH, name), "rb") as f:
        data = save_manager._unpack(f.read())
    if "sim" in data:
        pytest.skip("already a sim-block save")
    sim = Simulation(load_goods(), now=START, seed=1, town=TOWN)
    sim.presimulate(1)
    sim.load(save_manager._legacy_sim_block(data, sim), now=START)

    for gd in data["goods"]:
        if gd["name"] in sim.state.goods:
            good = sim.good(gd["name"])
            assert good.market_quantity == gd["market_quantity"]
            if "walk_price" in gd:
                assert good.walk_price == gd["walk_price"]
            assert good.price_history_daily == gd["price_history_daily"]
    if data.get("population"):
        groups = data["population"]["town"]["population_groups"]
        assert {c.name: c.count for c in sim.state.population.classes.values()} == groups
        assert sim.state.population.happiness == data["population"]["town"]["happiness"]
    sim.advance(datetime.timedelta(days=1))       # and runs on
