"""Health report for a headless run: is the economy sound, and is there trading to be done?

    python -m src.sim.health runs/<name>

reads the CSVs ``python -m src.sim.run`` wrote and checks them. So far:

- **market balance** (a check): the market place holds no money, so each day
  the town's money must change by exactly what crossed its border. The
  ``market_balance`` column is what those flows do not explain; it must be
  zero within float tolerance (``BALANCE_TOLERANCE`` of the money supply).
- **the town runs slightly short** (warnings): without the player, each
  class's mean comfort fulfilment lies in ``COMFORT_BAND`` and its mean luxury
  fulfilment in ``LUXURY_BAND``, and at least ``SHORT_GOODS_MIN`` goods are
  below their target stock on more than ``SHORT_DAYS_SHARE`` of days.
- **tradability** (a warning only, no threshold yet): per good, the median
  over the run of ``(30-day max price − 30-day min price) / price``, and how
  often that range, over ``TRADE_UNITS`` units, beats twice what a round trip
  of ``TRADE_UNITS`` units costs the player (two fees plus the slippage of
  buying and selling them at that day's stock). It says whether a patient
  trader could live off a good's swings.

Phase 4 of P1 adds the other checks of ``docs/p1_living_market.md``.
"""
import argparse
import csv
import math
import os
import statistics
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from ..config.constants import INITIAL_TRANSACTION_COST
from .run import ALL_CLASSES, GOODS_FILE, POPULATION_FILE, TOWN_FILE
from .state import GoodState
from .systems import market

BALANCE_TOLERANCE = 1e-9        # |market_balance| may be at most this share of the money supply (float rounding)
COMFORT_BAND = (0.80, 0.95)     # each class's mean comfort fulfilment, for a town running slightly short
LUXURY_BAND = (0.30, 0.70)      # ...and its mean luxury fulfilment
SHORT_GOODS_MIN = 3             # at least this many goods...
SHORT_DAYS_SHARE = 0.20         # ...below their target stock on more than this share of days
TRADE_WINDOW_DAYS = 30
TRADE_UNITS = 20                # a small trader's order


@dataclass
class Tradability:
    good: str
    median_range: float         # median of (window max − window min) / price
    share_worth_it: float       # share of days the window's range over TRADE_UNITS beats 2 × a round trip's cost
    days: int                   # days measured (those with a full window)


def _read(path: str) -> List[Dict[str, str]]:
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def market_balance(town_rows: Sequence[Dict[str, str]]) -> float:
    """The worst day's |market_balance| as a share of the money supply (0 when the books are sound)."""
    worst = 0.0
    for row in town_rows:
        supply = max(1.0, abs(float(row["money_supply"])))
        worst = max(worst, abs(float(row["market_balance"])) / supply)
    return worst


def fulfilment_by_class(population_rows: Sequence[Dict[str, str]]) -> Dict[str, Dict[str, float]]:
    """Per class, its mean fulfilment of each tier over the run."""
    sums: Dict[str, Dict[str, List[float]]] = {}
    for row in population_rows:
        if row["class"] == ALL_CLASSES:
            continue
        tiers = sums.setdefault(row["class"], {"comfort": [], "luxury": []})
        for tier in tiers:
            tiers[tier].append(float(row[f"fulfilment_{tier}"]))
    return {cls: {tier: statistics.mean(v) for tier, v in tiers.items()} for cls, tiers in sums.items()}


def short_days(goods_rows: Sequence[Dict[str, str]]) -> Dict[str, float]:
    """Per good, the share of days its stock was below its target stock."""
    counts: Dict[str, List[int]] = {}
    for row in goods_rows:
        c = counts.setdefault(row["good"], [0, 0])
        c[0] += float(row["stock"]) < float(row["target_stock"])
        c[1] += 1
    return {good: below / days for good, (below, days) in counts.items()}


def round_trip_cost(row: Dict[str, str], units: int = TRADE_UNITS, fee: float = INITIAL_TRANSACTION_COST) -> float:
    """What buying *units* and later selling them into the same stock costs the player: two fees and the slippage.

    Both legs are priced at that day's stock: by the time a patient trader
    sells, the market has restocked, so his buying and his selling each move the
    price against him.
    """
    good = GoodState(name=row["good"], stock=float(row["stock"]), target_stock=float(row["target_stock"]),
                     outside_price=float(row["reference"]))
    factor = market.volume_factor(good)
    good.noise = math.log(float(row["price"]) / (good.outside_price * factor))
    bought = market.quote(good, units, buying=True)
    sold = market.quote(good, units, buying=False)
    return 2 * fee + (bought - sold)


def tradability(goods_rows: Sequence[Dict[str, str]], window: int = TRADE_WINDOW_DAYS,
                units: int = TRADE_UNITS, fee: float = INITIAL_TRANSACTION_COST) -> List[Tradability]:
    """Per good, how wide its prices swing over *window* days, and how often that pays for a round trip."""
    by_good: Dict[str, List[Dict[str, str]]] = {}
    for row in goods_rows:
        by_good.setdefault(row["good"], []).append(row)
    result = []
    for good, rows in by_good.items():
        prices = [float(r["price"]) for r in rows]
        ranges, worth = [], 0
        for i in range(window - 1, len(rows)):
            span = prices[i - window + 1:i + 1]
            price_range = max(span) - min(span)
            ranges.append(price_range / prices[i])
            if price_range * units > 2 * round_trip_cost(rows[i], units, fee):
                worth += 1
        days = len(ranges)
        result.append(Tradability(good, statistics.median(ranges) if ranges else 0.0,
                                  worth / days if days else 0.0, days))
    return result


def report(run_dir: str) -> int:
    """Print the report for one run; returns 1 if a check failed (warnings never fail)."""
    town = _read(os.path.join(run_dir, TOWN_FILE))
    goods = _read(os.path.join(run_dir, GOODS_FILE))
    failed = False

    worst = market_balance(town)
    ok = worst <= BALANCE_TOLERANCE
    failed |= not ok
    print(f"[{'ok' if ok else 'FAIL'}] market balance: worst day {worst:.2e} of the money supply "
          f"(tolerance {BALANCE_TOLERANCE:.0e})")

    pop = _read(os.path.join(run_dir, POPULATION_FILE))
    for cls, tiers in fulfilment_by_class(pop).items():
        for tier, (low, high) in (("comfort", COMFORT_BAND), ("luxury", LUXURY_BAND)):
            ok = low <= tiers[tier] <= high
            print(f"[{'ok' if ok else 'warn'}] {cls}: mean {tier} fulfilment {tiers[tier]:.2f} "
                  f"(target {low:.2f}-{high:.2f})")
    shares = short_days(goods)
    short = sorted((g for g, s in shares.items() if s > SHORT_DAYS_SHARE), key=lambda g: -shares[g])
    ok = len(short) >= SHORT_GOODS_MIN
    print(f"[{'ok' if ok else 'warn'}] goods below their target stock on more than {SHORT_DAYS_SHARE:.0%} of days: "
          f"{len(short)} (want at least {SHORT_GOODS_MIN}): "
          + ", ".join(f"{g} {shares[g]:.0%}" for g in short))

    print(f"[info] tradability: {TRADE_WINDOW_DAYS}-day price range, and the share of days it beats "
          f"2 x a {TRADE_UNITS}-unit round trip (fees {INITIAL_TRANSACTION_COST} each, plus slippage)")
    print(f"       {'good':10} {'median range':>12} {'worth it':>9}")
    for t in sorted(tradability(goods), key=lambda t: -t.median_range):
        print(f"       {t.good:10} {t.median_range:12.1%} {t.share_worth_it:9.1%}")
    return 1 if failed else 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.sim.health", description=__doc__.split("\n\n")[0])
    parser.add_argument("runs", nargs="+", help="run folders written by python -m src.sim.run")
    args = parser.parse_args(argv)
    status = 0
    for run_dir in args.runs:
        print(f"== {run_dir}")
        status |= report(run_dir)
    return status


if __name__ == "__main__":
    sys.exit(main())
