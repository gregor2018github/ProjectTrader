"""Drives the golden scenario (see golden_harness.py) through ``src.sim.Simulation``.

The goldens were written by a driver running the same scenario on the code
before the extraction (``Good``, ``PopulationManager`` and ``Town`` on the
global ``random``); this one must reproduce them to the last bit. The snapshot
is taken through small adapters with the old classes' attribute names.
"""
from types import SimpleNamespace
from typing import Any, Dict, List

from src.sim import GoodDef, Simulation, TownSpec
from src.sim import calendar
from src.sim.systems import market
from tests.sim.golden_harness import (
    ACTIONS, GOODS, HOUSE_CAPACITIES, PRESIM_DAYS, RUN_DAYS, START, TICK, snapshot,
)


def run(seed: int) -> Dict[str, Any]:
    defs = [GoodDef(name, price, qty, "BLACK", i, False) for i, (name, price, qty) in enumerate(GOODS)]
    sim = Simulation(defs, now=START, seed=seed, town=TownSpec(list(HOUSE_CAPACITIES)))
    sim.presimulate(PRESIM_DAYS)

    quotes: List[float] = []
    first_day = calendar.day_number(START)
    now = START
    end = START + RUN_DAYS * 24 * 2 * TICK
    while now < end:
        now += TICK
        sim.advance_to(now)
        day = calendar.day_number(now)
        for kind, name, arg in ACTIONS.get((day - first_day, now.hour, now.minute), []):
            good = sim.good(name)
            if kind == "buy":
                quotes.append(market.quote(good, arg, buying=True))
                market.take(good, arg)
            elif kind == "sell":
                quotes.append(market.quote(good, arg, buying=False))
                market.put(good, arg)
            else:
                sim.apply_well_shock(name, arg == "Price goes up")
    return snapshot([_legacy_good(g) for g in sim.state.goods.values()], quotes,
                    _legacy_population(sim.state.population))


def _legacy_good(g: Any) -> SimpleNamespace:
    return SimpleNamespace(
        name=g.name, walk_price=g.walk_price, price=market.price(g), market_quantity=g.market_quantity,
        normal_quantity=g.normal_quantity, upper_bound=g.upper_bound, lower_bound=g.lower_bound,
        well_shock_remaining_days=g.well_shock_remaining_days,
        _well_shock_saved_upper=g.well_shock_saved_upper, _well_shock_saved_lower=g.well_shock_saved_lower,
        price_history_daily=g.price_history_daily, price_history_hourly=g.price_history_ticks,
    )


def _legacy_population(pop: Any) -> SimpleNamespace:
    classes = pop.classes.values()
    return SimpleNamespace(
        town=SimpleNamespace(
            citizens=pop.citizens, happiness=pop.happiness,
            population_groups={c.name: c.count for c in classes},
            happiness_groups={c.name: c.happiness for c in classes},
        ),
        base_groups={c.name: c.base for c in classes},
        population_history={c.name: c.population_history for c in classes},
        total_population_history=pop.total_population_history,
        average_happiness_history=pop.average_happiness_history,
        happiness_history={c.name: c.happiness_history for c in classes},
    )
