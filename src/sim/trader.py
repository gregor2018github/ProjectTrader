"""What can a player earn by trading alone? A headless trader plays the market to find out.

    python -m src.sim.trader                # the table below, about a minute
    python -m src.sim.trader --seeds 8 --days 112

The health report's tradability is an upper bound (a price range, whether or
not the high came after the low). This is the lower one: a trader with no
foresight and a simple rule, living by the game's own limits. Run it before and
after a change to the prices, the fee or the market's depth.

**The flipper** keeps each good's hourly prices of the last ``window`` days. It
buys when the price is ``dip`` below their mean, as much as its money, its free
slots and ``max_share`` of the market's stock allow, and sells a holding as
soon as that brings ``take`` more than it cost, fee and slippage counted (or,
after ``PATIENCE_DAYS``, as soon as it brings its cost back). It trades through
``Simulation.trade_with_player`` while the booths are open, so its own orders
move the prices it gets. Holdings left at the end count at cost. The cost of
living is left out: the figure is what trading itself brings.

It is played at several sizes (``CASES``: money, storage slots, licences) with
several rules (``RULES``); the table gives each size's best rule, the median
one and the worst seed. What to read from it:

- the smallest trader earns a few per cent of his money a day: trading pays
  from the first day;
- the income stops growing with the money: beyond a few thousand coins his
  orders move the prices against him, and more money buys nothing more. From
  there the money has to come from making goods (``docs/roadmap.md``, P3).

**The hoarder** buys ``HOARD_UNITS`` of a good in the middle of Summer and
sells them in the middle of Winter, for the goods whose outside price follows
the seasons: what stocking up for the winter brings, and how often it loses.
"""
import argparse
import datetime
import statistics
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from ..config.constants import DAYS_PER_SEASON, MARKET_FEE_RATE, MARKET_PRESIMULATION_DAYS, SLOT_SIZE
from . import run
from .scenario.tmx_town import load_town
from .simulation import Simulation
from .systems import market

BOOTHS_OPEN = (7, 21)           # the hours a trader finds the booths open, roughly (MARKET_OPEN_WINDOW / _CLOSE_WINDOW)
PATIENCE_DAYS = 10              # a holding older than this is sold as soon as it brings its cost back
HOARD_UNITS = 2 * SLOT_SIZE     # what the hoarder buys of each good
HOARD_GOODS = ("Wood", "Herbs", "Candle", "Fish", "Wool", "Salted Fish", "Salt", "Garments")

EARLY_GOODS = ("Wood", "Stone", "Fish", "Wheat", "Wool", "Hide", "Iron", "Herbs")
MANY_GOODS = EARLY_GOODS + ("Meat", "Beer", "Wine", "Linen", "Candle", "Salt", "Pottery", "Spices")


@dataclass(frozen=True)
class Case:
    """A trader's means: what he starts with and may trade."""
    label: str
    money: float
    slots: int                  # storage slots of SLOT_SIZE units, one good each
    goods: Tuple[str, ...]      # the goods he holds licences for


@dataclass(frozen=True)
class Rule:
    """How the flipper decides."""
    window: int                 # days of prices it compares with
    dip: float                  # it buys this far under their mean
    take: float                 # it sells for this much more than it paid, after fee and slippage
    max_share: float            # the most of the market's stock it buys at once


CASES = (
    Case("a new game: 100g, 5 slots, Wood and Stone", 100, 5, EARLY_GOODS[:2]),
    Case("300g, 5 slots, 4 goods", 300, 5, EARLY_GOODS[:4]),
    Case("1,000g, 10 slots, 8 goods", 1_000, 10, EARLY_GOODS),
    Case("5,000g, 40 slots, 16 goods", 5_000, 40, MANY_GOODS),
    Case("30,000g, 150 slots, 16 goods", 30_000, 150, MANY_GOODS),
)
RULES = tuple(Rule(window, dip, take, 0.12) for window in (3, 6) for dip in (0.05, 0.09) for take in (0.05, 0.10))


def new_game(seed: int) -> Simulation:
    """The economy as a new game with this seed opens on it."""
    definitions, scenario = run.load_definitions()
    sim = Simulation(definitions, now=run.start_moment(), seed=seed, town=load_town(None), scenario=scenario)
    sim.presimulate(MARKET_PRESIMULATION_DAYS)
    return sim


def fee(amount: float) -> float:
    return MARKET_FEE_RATE * amount


def flip(sim: Simulation, case: Case, rule: Rule, days: int) -> Tuple[float, int]:
    """Let the flipper trade for *days*; returns what it gained and how many trades it made."""
    start = sim.now
    money = case.money
    history: Dict[str, List[float]] = {g: [] for g in case.goods}
    held: Dict[str, int] = {g: 0 for g in case.goods}
    cost: Dict[str, float] = {g: 0.0 for g in case.goods}
    since: Dict[str, int] = {g: 0 for g in case.goods}
    trades = 0
    for hour in range(1, days * 24 + 1):
        now = start + datetime.timedelta(hours=hour)
        sim.advance_to(now)
        for g in case.goods:
            history[g].append(market.price(sim.state.goods[g]))
        if not BOOTHS_OPEN[0] <= now.hour <= BOOTHS_OPEN[1] or hour < rule.window * 24:
            continue
        for g in case.goods:
            good = sim.state.goods[g]
            if held[g]:
                revenue = market.quote(good, held[g], buying=False)
                net = revenue - fee(revenue)
                patient = hour - since[g] <= PATIENCE_DAYS * 24
                if net > cost[g] * (1 + rule.take if patient else 1):
                    sim.trade_with_player(g, held[g], buying=False)
                    money += net
                    held[g], cost[g] = 0, 0.0
                    trades += 1
                continue
            mean = statistics.fmean(history[g][-rule.window * 24:])
            if history[g][-1] >= mean * (1 - rule.dip):
                continue
            free = case.slots - sum(-(-units // SLOT_SIZE) for units in held.values())
            units = min(free * SLOT_SIZE, int(good.stock * rule.max_share))
            while units > 0 and market.quote(good, units, buying=True) * (1 + MARKET_FEE_RATE) > money:
                units -= max(1, units // 20)
            if units < 1:
                continue
            paid = sim.trade_with_player(g, units, buying=True)
            money -= paid + fee(paid)
            held[g], cost[g], since[g] = units, paid + fee(paid), hour
            trades += 1
    return money + sum(cost.values()) - case.money, trades


def hoard(sim: Simulation, goods: Sequence[str], years: int, units: int = HOARD_UNITS) -> Dict[str, List[Tuple[float, float]]]:
    """Per good and year: what *units* bought in mid Summer and sold in mid Winter gained, and what they cost."""
    start = sim.now.replace(hour=12, minute=0, second=0)
    mid_summer = DAYS_PER_SEASON + DAYS_PER_SEASON // 2
    result: Dict[str, List[Tuple[float, float]]] = {g: [] for g in goods}
    for year in range(years):
        first = start + datetime.timedelta(days=4 * DAYS_PER_SEASON * year)
        sim.advance_to(first + datetime.timedelta(days=mid_summer))
        cost = {}
        for g in goods:
            lot = min(units, int(sim.state.goods[g].stock))
            paid = sim.trade_with_player(g, lot, buying=True)
            cost[g] = (lot, paid + fee(paid))
        sim.advance_to(first + datetime.timedelta(days=mid_summer + 2 * DAYS_PER_SEASON))
        for g in goods:
            lot, paid = cost[g]
            revenue = sim.trade_with_player(g, lot, buying=False)
            result[g].append((revenue - fee(revenue) - paid, paid))
    return result


def _flip_job(job: Tuple[int, int, int, int]) -> Tuple[int, int, float, int]:
    case, rule, seed, days = job
    gain, trades = flip(new_game(seed), CASES[case], RULES[rule], days)
    return case, rule, gain, trades


def _hoard_job(job: Tuple[int, int]) -> Dict[str, List[Tuple[float, float]]]:
    seed, years = job
    return hoard(new_game(seed), HOARD_GOODS, years)


def report(seeds: Sequence[int], days: int, years: int, jobs: Optional[int] = None) -> None:
    """Play every case with every rule on every seed, and print the tables."""
    flips = [(c, r, s, days) for c in range(len(CASES)) for r in range(len(RULES)) for s in seeds]
    with ProcessPoolExecutor(max_workers=jobs) as pool:
        flipped = list(pool.map(_flip_job, flips, chunksize=4))
        hoarded = list(pool.map(_hoard_job, [(s, years) for s in seeds]))

    print(f"Flipping: gain a day over {days} days, {len(seeds)} seeds, a fee of {MARKET_FEE_RATE:.1%} each way "
          f"(the cost of living not counted)")
    print(f"  {'trader':44} {'best rule':>10} {'of money':>9} {'worst seed':>11} {'median rule':>12} {'trades':>7}")
    for c, case in enumerate(CASES):
        per_rule = []
        for r in range(len(RULES)):
            runs = [(gain, trades) for cc, rr, gain, trades in flipped if cc == c and rr == r]
            per_rule.append((statistics.fmean(g for g, _ in runs) / days, min(g for g, _ in runs) / days,
                             statistics.fmean(t for _, t in runs)))
        per_rule.sort()
        best, median = per_rule[-1], per_rule[len(per_rule) // 2]
        print(f"  {case.label:44} {best[0]:8.1f} g {best[0] / case.money:9.2%} {best[1]:9.1f} g {median[0]:10.1f} g "
              f"{best[2]:7.0f}")

    print(f"\nHoarding: {HOARD_UNITS} units bought in mid Summer, sold in mid Winter, {len(seeds)} seeds x {years} years")
    print(f"  {'good':12} {'paid':>8} {'gain':>8} {'':>6} {'worst':>8} {'best':>8} {'years lost':>11}")
    for g in HOARD_GOODS:
        rows = [row for result in hoarded for row in result[g]]
        gains, paid = [gain for gain, _ in rows], statistics.fmean(p for _, p in rows)
        mean = statistics.fmean(gains)
        print(f"  {g:12} {paid:8.1f} {mean:8.1f} {mean / paid:6.0%} {min(gains):8.1f} {max(gains):8.1f} "
              f"{sum(gain < 0 for gain in gains):5} of {len(gains)}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.sim.trader", description=__doc__.split("\n\n")[0])
    parser.add_argument("--seeds", type=int, default=4, help="seeds to play, from 1 (default 4)")
    parser.add_argument("--days", type=int, default=56, help="days the flipper trades (default 56, two years)")
    parser.add_argument("--years", type=int, default=3, help="years the hoarder stocks up (default 3)")
    parser.add_argument("--jobs", type=int, help="processes (default one per CPU)")
    args = parser.parse_args(argv)
    report(range(1, args.seeds + 1), args.days, args.years, args.jobs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
