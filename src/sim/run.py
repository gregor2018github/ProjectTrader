"""Headless runner: simulate years of the economy and write them out for analysis.

    python -m src.sim.run --years 20 --seed 1 --out runs/baseline

writes into the ``--out`` folder, a row taken at each midnight after the day's
systems ran (the flows are the day just ended):

- ``goods_daily.csv``: one row per day and good: price, outside_price,
  reference (the outside price times a well wish's shock), stock,
  target_stock, and the day's flows: wanted and bought (households),
  input_wanted and input_bought (workshops), produced, imported, exported,
  player_bought, player_sold;
- ``population_daily.csv``: one row per day and class (and ``All`` for the
  town): count, employed, happiness, happiness_target, purse, income (of which
  wages and payouts), spent, leaked, and fulfilment_basic / _comfort / _luxury;
- ``workshops_daily.csv``: one row per day and workshop: owner, building,
  capacity, utilisation, margin, batches planned for today and run yesterday,
  workers, cash;
- ``town_daily.csv``: one row per day: citizens, the town's money (all of it,
  and in purses, workshops and owners), the money crossing the town's border
  (created as base income, leaked, invested in growth, paid to and by
  merchants), the market_balance (what those flows do not explain: always
  zero, as the market place holds no money), and the merchants' book;
- ``meta.json``: the seed, years, git commit, the constants, definitions and
  scenario the run used, and how long it took.

All files share the columns day, year, season, day_of_season. The run starts
as a new game does (the game's start moment, the map's town, the home-town
scenario's workshops, the economy run ahead), so a seed here is a seed there.
Same seed, same CSVs, byte for byte. Load them with pandas::

    goods = pd.read_csv("runs/baseline/goods_daily.csv")
    goods.pivot(index="day", columns="good", values="price").plot()
"""
import argparse
import csv
import dataclasses
import datetime
import json
import os
import platform
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..config import constants
from . import calendar
from .data import TIERS, Definitions, ScenarioDef, load_definitions as load_data, load_scenario
from .scenario.tmx_town import load_town
from .simulation import SIM_VERSION, Simulation
from .state import TownSpec
from .systems import market, population

GOODS_FILE = "goods_daily.csv"
POPULATION_FILE = "population_daily.csv"
WORKSHOPS_FILE = "workshops_daily.csv"
TOWN_FILE = "town_daily.csv"
META_FILE = "meta.json"
SCENARIO = "home_town"

STAMP_COLUMNS = ["day", "year", "season", "day_of_season"]
GOODS_COLUMNS = STAMP_COLUMNS + ["good", "price", "outside_price", "reference", "stock", "target_stock",
                                 "wanted", "bought", "input_wanted", "input_bought", "produced",
                                 "imported", "exported", "player_bought", "player_sold"]
POPULATION_COLUMNS = STAMP_COLUMNS + ["class", "count", "employed", "happiness", "happiness_target", "purse",
                                      "income", "wages", "payouts", "spent", "leaked"] + [f"fulfilment_{t}" for t in TIERS]
WORKSHOP_COLUMNS = STAMP_COLUMNS + ["workshop", "owner", "building", "capacity", "utilisation", "margin",
                                    "planned", "done_yesterday", "workers", "cash"]
TOWN_COLUMNS = STAMP_COLUMNS + ["citizens", "money_supply", "purses", "workshop_cash", "owner_cash",
                                "money_created", "money_leaked", "money_invested", "paid_to_merchants",
                                "paid_by_merchants", "market_balance", "merchant_sales", "merchant_purchases",
                                "merchant_import_cost", "merchant_export_revenue", "merchant_transport",
                                "merchant_profit"]
ALL_CLASSES = "All"

# The constants a run depends on, written to meta.json (by name prefix)
CONSTANT_PREFIXES = (
    "MARKET_", "PRICE_TICK", "PRICE_NOISE", "TARGET_STOCK", "PURSE_", "SAVINGS_", "WELL_WISH_",
    "POPULATION_", "HAPPINESS_", "HUNGER_", "UNDERPOP_", "OVERPOP_", "NEAR_CAPACITY_",
    "MAX_DAILY_POPULATION", "STARTING_OCCUPANCY", "DAYS_PER_SEASON", "CALENDAR_START_YEAR",
    "START_DATE", "START_TIME", "MARGIN_", "UTILISATION_", "GROWTH_", "SHRINK_",
)


def start_moment() -> datetime.datetime:
    """Where a new game's clock starts (START_DATE at START_TIME)."""
    day, month, year = (int(part) for part in constants.START_DATE.split("."))
    hour, minute = (int(part) for part in constants.START_TIME.split(":"))
    return datetime.datetime(year, month, day, hour, minute)


def load_definitions(scenario: str = SCENARIO) -> Tuple[Definitions, ScenarioDef]:
    """The definitions and the scenario, as the game loads them."""
    definitions = load_data([name for name, _ in population.class_shares()])
    return definitions, load_scenario(scenario, [b.type for b in definitions.buildings])


def _fmt(value: Any) -> str:
    """Floats written as repr, so they round-trip exactly and the output is byte-stable."""
    return repr(value) if isinstance(value, float) else str(value)


class DailyRecorder:
    """Takes rows at every midnight, after the day's systems ran."""

    def __init__(self, sim: Simulation) -> None:
        self.sim = sim
        self.goods_rows: List[List[str]] = []
        self.population_rows: List[List[str]] = []
        self.workshop_rows: List[List[str]] = []
        self.town_rows: List[List[str]] = []
        sim.scheduler.subscribe(calendar.DAY, self.record)

    def record(self, moment: datetime.datetime) -> None:
        state = self.sim.state
        d = calendar.game_date(moment)
        stamp = [str(calendar.day_number(moment)), str(d.year), d.season_name, str(d.day)]
        for g in state.goods.values():
            f = g.yesterday
            self.goods_rows.append(stamp + [g.name] + [_fmt(v) for v in (
                market.price(g), g.outside_price, market.reference(g), g.stock, g.target_stock,
                f.wanted, f.bought, f.input_wanted, f.input_bought, f.produced,
                f.imported, f.exported, f.player_bought, f.player_sold)])
        pop = state.population
        purses = 0.0
        if pop is not None:
            classes = list(pop.classes.values())
            for c in classes:
                purses += c.purse
                y = c.yesterday
                self.population_rows.append(stamp + [c.name] + [_fmt(v) for v in (
                    c.count, c.employed, c.happiness, c.happiness_target, c.purse,
                    y.income, y.wages, y.payouts, y.spent, y.leaked)]
                    + [_fmt(c.fulfilment.get(t, 1.0)) for t in TIERS])
            self.population_rows.append(stamp + [ALL_CLASSES] + [_fmt(v) for v in (
                pop.citizens, sum(c.employed for c in classes), pop.happiness, population.average_target(pop),
                purses, sum(c.yesterday.income for c in classes), sum(c.yesterday.wages for c in classes),
                sum(c.yesterday.payouts for c in classes), sum(c.yesterday.spent for c in classes),
                sum(c.yesterday.leaked for c in classes))] + ["", "", ""])
        for w in state.workshops.values():
            self.workshop_rows.append(stamp + [w.id, w.owner_id, w.building] + [_fmt(v) for v in (
                w.capacity, w.utilisation, w.margin, w.planned, w.done_yesterday, w.workers, w.cash)])
        money, book = state.money_yesterday, state.merchants_yesterday
        workshop_cash = sum(w.cash for w in state.workshops.values())
        owner_cash = sum(o.cash for o in state.owners.values())
        self.town_rows.append(stamp + [_fmt(v) for v in (
            pop.citizens if pop is not None else 0, self.sim.town_money(), purses, workshop_cash, owner_cash,
            money.created, money.leaked, money.invested, money.to_merchants, money.from_merchants,
            money.market_balance, book.sales, book.purchases, book.import_cost, book.export_revenue,
            book.transport, book.profit)])


def simulate(years: float, seed: int, definitions: Definitions, town: Optional[TownSpec],
             scenario: Optional[ScenarioDef] = None,
             presim_days: int = constants.MARKET_PRESIMULATION_DAYS) -> DailyRecorder:
    """Run a new game's economy for *years* and return what was recorded."""
    start = start_moment()
    sim = Simulation(definitions, now=start, seed=seed, town=town, scenario=scenario)
    sim.presimulate(presim_days)
    recorder = DailyRecorder(sim)
    days = round(years * calendar.DAYS_PER_YEAR)
    for day in range(1, days + 1):
        sim.advance_to(start + datetime.timedelta(days=day))
    return recorder


def _write_csv(path: str, columns: List[str], rows: List[List[str]]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(columns)
        writer.writerows(rows)


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=constants.MAIN_PATH, capture_output=True,
                              text=True, timeout=10, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _constants() -> Dict[str, Any]:
    return {name: getattr(constants, name) for name in sorted(dir(constants))
            if name.isupper() and name.startswith(CONSTANT_PREFIXES)}


def write_run(out: str, years: float, seed: int, definitions: Definitions, town: Optional[TownSpec],
              scenario: Optional[ScenarioDef] = None,
              presim_days: int = constants.MARKET_PRESIMULATION_DAYS) -> Dict[str, Any]:
    """Simulate and write the CSVs and meta.json into *out*; returns the meta data."""
    began = time.perf_counter()
    recorder = simulate(years, seed, definitions, town, scenario, presim_days)
    simulated = time.perf_counter() - began
    os.makedirs(out, exist_ok=True)
    files = {GOODS_FILE: (GOODS_COLUMNS, recorder.goods_rows),
             POPULATION_FILE: (POPULATION_COLUMNS, recorder.population_rows),
             WORKSHOPS_FILE: (WORKSHOP_COLUMNS, recorder.workshop_rows),
             TOWN_FILE: (TOWN_COLUMNS, recorder.town_rows)}
    for name, (columns, rows) in files.items():
        _write_csv(os.path.join(out, name), columns, rows)
    meta = {
        "seed": seed,
        "years": years,
        "days": round(years * calendar.DAYS_PER_YEAR),
        "presim_days": presim_days,
        "start": start_moment().isoformat(),
        "sim_version": SIM_VERSION,
        "git_commit": _git("rev-parse", "HEAD"),
        "git_dirty": bool(_git("status", "--porcelain", "--untracked-files=no")),
        "python": platform.python_version(),
        "definitions": dataclasses.asdict(definitions),
        "scenario": dataclasses.asdict(scenario) if scenario is not None else None,
        "town": dataclasses.asdict(town) if town is not None else None,
        "constants": _constants(),
        "files": {name: len(rows) for name, (_, rows) in files.items()},
        "runtime_seconds": {"simulate": round(simulated, 3), "total": round(time.perf_counter() - began, 3)},
    }
    with open(os.path.join(out, META_FILE), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, default=list)
        f.write("\n")
    return meta


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.sim.run", description=__doc__.split("\n\n")[0])
    parser.add_argument("--years", type=float, default=20, help="game years to simulate (default 20)")
    parser.add_argument("--seed", type=int, default=1, help="the random generator's seed (default 1)")
    parser.add_argument("--out", help="output folder (default runs/seed<seed>_<years>y)")
    parser.add_argument("--map", help="the .tmx map to take the town from (default the game's)")
    parser.add_argument("--scenario", default=SCENARIO, help="assets/data/scenarios/<name>.json (default home_town)")
    parser.add_argument("--presim-days", type=int, default=constants.MARKET_PRESIMULATION_DAYS,
                        help="days the economy runs before the start, as a new game does")
    args = parser.parse_args(argv)
    out = args.out or os.path.join("runs", f"seed{args.seed}_{args.years:g}y")
    definitions, scenario = load_definitions(args.scenario)
    meta = write_run(out, args.years, args.seed, definitions, load_town(args.map), scenario, args.presim_days)
    print(f"{meta['days']} days ({args.years:g} years), seed {args.seed}: "
          f"{meta['runtime_seconds']['total']:.2f} s -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
