"""Runs the market and the population through a fixed scenario and snapshots the result.

The golden files in ``tests/sim/golden/`` were written by this harness from the
code as it was *before* the simulation core was extracted (``Good``,
``PopulationManager`` and ``Town`` drawing from the global ``random``), so they
pin the old behaviour to the last bit. The scenario now runs through
``src.sim`` (``scenario_driver.py``) and must still match them exactly: the sim
draws from its own ``random.Random(seed)`` in the old order, and
``random.Random(seed)`` draws what ``random.seed(seed)`` did.

The scenario follows ``Game``: the goods are created in the game's order (two
corridor draws each), the market's history is pre-simulated, then the clock
runs from the game's start time in price ticks, firing in the order of
``Game.run()``: price tick, then the hour, then the day. A few scripted trades
and well wishes on the way exercise slippage, volume recovery and the shock.

Regenerate (only when behaviour is *meant* to change)::

    python -m tests.sim.golden_harness --write
"""
import datetime
import hashlib
import json
import os
import sys
from typing import Any, Dict, List, Tuple

GOLDEN_DIR = os.path.join(os.path.dirname(__file__), "golden")
SEEDS = (1, 20260411)
PRESIM_DAYS = 60            # MARKET_PRESIMULATION_DAYS when the goldens were written
RUN_DAYS = 28               # one game year after the pre-simulation
TICK = datetime.timedelta(minutes=30)
START = datetime.datetime(1500, 1, 1, 8, 0)

# (name, start price, start quantity), the game's goods in the game's order
GOODS: List[Tuple[str, float, int]] = [
    ("Wood", 1, 5000), ("Stone", 2, 2000), ("Iron", 5, 900), ("Wool", 3, 2500),
    ("Hide", 4, 1000), ("Fish", 2, 5000), ("Wheat", 1, 5000), ("Wine", 10, 500),
    ("Beer", 5, 500), ("Meat", 5, 800), ("Pottery", 3, 3500), ("Linen", 3, 2000),
    ("Candle", 4, 1500), ("Herbs", 3, 1200), ("Salt", 6, 1500),
]

# Residential houses' Max_inhabitants, a fixed stand-in for the map's
HOUSE_CAPACITIES: List[int] = [6, 8, 4, 12, 5, 7, 9, 3, 10, 6, 8, 15, 4, 6, 7, 5, 11, 6, 9, 4, 8, 20, 7]

# Scripted actions: (day after the start, hour, minute) -> what happens then
ACTIONS: Dict[Tuple[int, int, int], List[Tuple[str, str, Any]]] = {
    (1, 10, 0): [("buy", "Wine", 300), ("sell", "Wood", 4000)],
    (2, 14, 30): [("shock", "Iron", "Price goes up")],
    (4, 9, 0): [("buy", "Salt", 1400), ("shock", "Salt", "Price goes down")],
    (5, 12, 0): [("shock", "Iron", "Price goes down")],   # a second shock while the first runs
    (12, 16, 30): [("sell", "Fish", 20000)],
}


def _digest(values: List[float]) -> str:
    return hashlib.sha256(json.dumps(values).encode("utf-8")).hexdigest()


def run_scenario(seed: int) -> Dict[str, Any]:
    """Run the scenario on the current code and return its snapshot."""
    from tests.sim import scenario_driver
    return scenario_driver.run(seed)


def snapshot(goods: List[Any], quotes: List[float], population: Any) -> Dict[str, Any]:
    """The comparable result: final state, daily histories, digests of the long ones.

    Args:
        goods: Objects with the old ``Good``'s attributes.
        quotes: The quote of every scripted trade, in order.
        population: An object with the old ``PopulationManager``'s attributes
            and a ``town`` with ``citizens``, ``happiness`` and the groups.
    """
    pm = population
    return {
        "goods": {
            g.name: {
                "walk_price": g.walk_price,
                "price": g.price,
                "market_quantity": g.market_quantity,
                "normal_quantity": g.normal_quantity,
                "upper_bound": g.upper_bound,
                "lower_bound": g.lower_bound,
                "well_shock_remaining_days": g.well_shock_remaining_days,
                "well_shock_saved_upper": g._well_shock_saved_upper,
                "well_shock_saved_lower": g._well_shock_saved_lower,
                "price_history_daily": list(g.price_history_daily),
                "price_history_hourly_len": len(g.price_history_hourly),
                "price_history_hourly_sha256": _digest(list(g.price_history_hourly)),
            }
            for g in goods
        },
        "quotes": list(quotes),
        "population": {
            "citizens": pm.town.citizens,
            "happiness": pm.town.happiness,
            "population_groups": dict(pm.town.population_groups),
            "happiness_groups": dict(pm.town.happiness_groups),
            "base_groups": dict(pm.base_groups),
            "population_history": {k: list(v) for k, v in pm.population_history.items()},
            "total_population_history": list(pm.total_population_history),
            "average_happiness_history_len": len(pm.average_happiness_history),
            "average_happiness_history_sha256": _digest(list(pm.average_happiness_history)),
            "happiness_history_sha256": {k: _digest(list(v)) for k, v in pm.happiness_history.items()},
        },
    }


def golden_path(seed: int) -> str:
    return os.path.join(GOLDEN_DIR, f"market_population_seed{seed}.json")


def write_goldens() -> None:
    os.makedirs(GOLDEN_DIR, exist_ok=True)
    for seed in SEEDS:
        with open(golden_path(seed), "w", encoding="utf-8") as f:
            json.dump(run_scenario(seed), f, indent=1, sort_keys=True)
            f.write("\n")
        print("wrote", golden_path(seed))


if __name__ == "__main__":
    if "--write" in sys.argv:
        write_goldens()
    else:
        print(json.dumps(run_scenario(SEEDS[0]), indent=1, sort_keys=True)[:2000])
