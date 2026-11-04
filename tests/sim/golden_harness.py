"""Runs the economy through a fixed scenario and snapshots the result, to pin its behaviour.

The scenario: the frozen definitions in ``tests/sim/golden/data/`` (so tuning
``assets/data/`` does not break it), a fixed town, the economy run ahead as a
new game does, then one game year with a few scripted player trades (buying a
staple up, dumping a good) and well wishes on the way.

The snapshot holds every number of the final state, and digests of the long
histories. The goldens pin the living market per phase (``docs/p1_living_market.md``):
when behaviour is *meant* to change, regenerate them and say so in the commit::

    python -m tests.sim.golden_harness --write
"""
import datetime
import hashlib
import json
import os
import sys
from typing import Any, Dict, List, Tuple

from src.sim import Simulation, TownSpec, load_goods, load_needs
from src.sim.systems.population import class_shares

GOLDEN_DIR = os.path.join(os.path.dirname(__file__), "golden")
DATA_DIR = os.path.join(GOLDEN_DIR, "data")
SEEDS = (1, 20260411)
PRESIM_DAYS = 60
RUN_DAYS = 28               # one game year
START = datetime.datetime(1500, 1, 1, 8, 0)

# Residential houses' Max_inhabitants, a fixed stand-in for the map's
HOUSE_CAPACITIES: List[int] = [6, 8, 4, 12, 5, 7, 9, 3, 10, 6, 8, 15, 4, 6, 7, 5, 11, 6, 9, 4, 8, 20, 7] * 3

# Scripted actions: (day after the start, hour) -> what happens then
ACTIONS: Dict[Tuple[int, int], List[Tuple[str, str, Any]]] = {
    (1, 10): [("buy", "Wheat", 600), ("sell", "Wood", 2000)],
    (2, 14): [("shock", "Iron", True)],
    (4, 9): [("buy", "Salt", 80), ("shock", "Salt", False)],
    (5, 12): [("shock", "Iron", False)],       # a second wish while the first runs
    (12, 16): [("sell", "Fish", 3000)],
}


def _digest(values: Any) -> str:
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode("utf-8")).hexdigest()


def _compact(record: Dict[str, Any]) -> Dict[str, Any]:
    """A state record with each list replaced by its length and digest."""
    out = {}
    for key, value in record.items():
        if isinstance(value, list):
            out[key + "_len"] = len(value)
            out[key + "_sha256"] = _digest(value)
        else:
            out[key] = value
    return out


def run_scenario(seed: int) -> Dict[str, Any]:
    goods = load_goods(DATA_DIR)
    needs = load_needs([g.name for g in goods], [c for c, _ in class_shares()], DATA_DIR)
    sim = Simulation(goods, needs, now=START, seed=seed, town=TownSpec(list(HOUSE_CAPACITIES)))
    sim.presimulate(PRESIM_DAYS)
    first_day = START.date()
    trades: List[float] = []
    for hour in range(1, RUN_DAYS * 24 + 1):
        moment = START + datetime.timedelta(hours=hour)
        sim.advance_to(moment)
        for kind, name, arg in ACTIONS.get(((moment.date() - first_day).days, moment.hour), []):
            if kind == "shock":
                sim.apply_well_shock(name, arg)
            else:
                trades.append(sim.trade_with_player(name, arg, buying=(kind == "buy")))
    state = sim.to_dict()["state"]
    population = state["population"]
    return {
        "trades": trades,
        "market_cash": state["market_cash"],
        "goods": {g["name"]: _compact(g) for g in state["goods"]},
        "classes": {c["name"]: _compact(c) for c in population["classes"]},
        "town": _compact({k: v for k, v in population.items() if k != "classes"}),
        "rng_sha256": _digest(sim.to_dict()["rng"]),
    }


def golden_path(seed: int) -> str:
    return os.path.join(GOLDEN_DIR, f"living_market_seed{seed}.json")


def write_goldens() -> None:
    for seed in SEEDS:
        with open(golden_path(seed), "w", encoding="utf-8") as f:
            json.dump(run_scenario(seed), f, indent=1, sort_keys=True)
            f.write("\n")
        print("wrote", golden_path(seed))


if __name__ == "__main__":
    if "--write" in sys.argv:
        write_goldens()
    else:
        print(json.dumps(run_scenario(SEEDS[0]), indent=1, sort_keys=True)[:3000])
