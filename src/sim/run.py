"""Headless runner: simulate years of the economy and write them out for analysis.

    python -m src.sim.run --years 20 --seed 1 --out runs/baseline

writes into the ``--out`` folder:

- ``goods_daily.csv``: one row per day and good (day, year, season,
  day_of_season, good, price, walk_price, market_quantity, normal_quantity,
  upper_bound, lower_bound), taken at each midnight after the day's systems ran;
- ``population_daily.csv``: one row per day and class (day, year, season,
  day_of_season, class, count, happiness), plus a class ``All`` for the town;
- ``meta.json``: the seed, years, git commit, the constants and definitions the
  run used, and how long it took.

The run starts as a new game does (the game's start moment, the market's
pre-simulated history, the map's town), so a seed here is a seed there. Same
seed, same CSVs, byte for byte. Load them with pandas::

    goods = pd.read_csv("runs/baseline/goods_daily.csv")
    goods.pivot(index="day", columns="good", values="price").plot()
"""
import argparse
import csv
import datetime
import json
import os
import platform
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Sequence

from ..config import constants
from . import calendar
from .data import GoodDef, load_goods
from .scenario.tmx_town import load_town
from .simulation import SIM_VERSION, Simulation
from .state import TownSpec
from .systems import market, population

GOODS_FILE = "goods_daily.csv"
POPULATION_FILE = "population_daily.csv"
META_FILE = "meta.json"

GOODS_COLUMNS = ["day", "year", "season", "day_of_season", "good", "price", "walk_price",
                 "market_quantity", "normal_quantity", "upper_bound", "lower_bound"]
POPULATION_COLUMNS = ["day", "year", "season", "day_of_season", "class", "count", "happiness"]
ALL_CLASSES = "All"

# The constants a run depends on, written to meta.json (by name prefix)
CONSTANT_PREFIXES = (
    "MARKET_", "PRICE_TICK", "WELL_WISH_", "POPULATION_", "HAPPINESS_", "UNDERPOP_", "OVERPOP_",
    "NEAR_CAPACITY_", "MAX_DAILY_POPULATION", "STARTING_OCCUPANCY", "DAYS_PER_SEASON",
    "CALENDAR_START_YEAR", "START_DATE", "START_TIME",
)


def start_moment() -> datetime.datetime:
    """Where a new game's clock starts (START_DATE at START_TIME)."""
    day, month, year = (int(part) for part in constants.START_DATE.split("."))
    hour, minute = (int(part) for part in constants.START_TIME.split(":"))
    return datetime.datetime(year, month, day, hour, minute)


def _fmt(value: Any) -> str:
    """Floats written as repr, so they round-trip exactly and the output is byte-stable."""
    return repr(value) if isinstance(value, float) else str(value)


class DailyRecorder:
    """Takes a row per good and per class at every midnight, after the day's systems ran."""

    def __init__(self, sim: Simulation) -> None:
        self.sim = sim
        self.goods_rows: List[List[str]] = []
        self.population_rows: List[List[str]] = []
        sim.scheduler.subscribe(calendar.DAY, self.record)

    def record(self, moment: datetime.datetime) -> None:
        d = calendar.game_date(moment)
        stamp = [str(calendar.day_number(moment)), str(d.year), d.season_name, str(d.day)]
        for g in self.sim.state.goods.values():
            self.goods_rows.append(stamp + [g.name] + [_fmt(v) for v in (
                market.price(g), g.walk_price, g.market_quantity, g.normal_quantity, g.upper_bound, g.lower_bound)])
        pop = self.sim.state.population
        if pop is not None:
            for c in pop.classes.values():
                self.population_rows.append(stamp + [c.name, _fmt(c.count), _fmt(c.happiness)])
            self.population_rows.append(stamp + [ALL_CLASSES, _fmt(pop.citizens), _fmt(pop.happiness)])


def simulate(years: float, seed: int, goods: Sequence[GoodDef], town: Optional[TownSpec],
             presim_days: int = constants.MARKET_PRESIMULATION_DAYS) -> DailyRecorder:
    """Run a new game's economy for *years* and return what was recorded."""
    start = start_moment()
    sim = Simulation(goods, now=start, seed=seed, town=town)
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
    values = {name: getattr(constants, name) for name in sorted(dir(constants))
              if name.isupper() and name.startswith(CONSTANT_PREFIXES)}
    values["market.UPPER_BOUND_RANGE"] = market.UPPER_BOUND_RANGE
    values["market.LOWER_BOUND_RANGE"] = market.LOWER_BOUND_RANGE
    values["population.HAPPINESS_REVERSION"] = population.HAPPINESS_REVERSION
    return values


def write_run(out: str, years: float, seed: int, goods: Sequence[GoodDef], town: Optional[TownSpec],
              presim_days: int = constants.MARKET_PRESIMULATION_DAYS) -> Dict[str, Any]:
    """Simulate and write the CSVs and meta.json into *out*; returns the meta data."""
    began = time.perf_counter()
    recorder = simulate(years, seed, goods, town, presim_days)
    simulated = time.perf_counter() - began
    os.makedirs(out, exist_ok=True)
    _write_csv(os.path.join(out, GOODS_FILE), GOODS_COLUMNS, recorder.goods_rows)
    _write_csv(os.path.join(out, POPULATION_FILE), POPULATION_COLUMNS, recorder.population_rows)
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
        "goods": [g.__dict__ for g in goods],
        "town": town.__dict__ if town is not None else None,
        "constants": _constants(),
        "files": {GOODS_FILE: len(recorder.goods_rows), POPULATION_FILE: len(recorder.population_rows)},
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
    parser.add_argument("--presim-days", type=int, default=constants.MARKET_PRESIMULATION_DAYS,
                        help="days of market history made up before the start, as a new game does")
    args = parser.parse_args(argv)
    out = args.out or os.path.join("runs", f"seed{args.seed}_{args.years:g}y")
    meta = write_run(out, args.years, args.seed, load_goods(), load_town(args.map), args.presim_days)
    print(f"{meta['days']} days ({args.years:g} years), seed {args.seed}: "
          f"{meta['runtime_seconds']['total']:.2f} s -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
