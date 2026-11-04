"""Health report for a headless run: is the economy sound, and is there trading to be done?

    python -m src.sim.health runs/<name>

reads the CSVs ``python -m src.sim.run`` wrote and checks them. So far:

- **market balance** (a check): the market place holds no money, so each day
  the town's money must change by exactly what crossed its border. The
  ``market_balance`` column is what those flows do not explain; it must be
  zero within float tolerance (``BALANCE_TOLERANCE`` of the money supply).
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
from .run import GOODS_FILE, TOWN_FILE
from .state import GoodState
from .systems import market

BALANCE_TOLERANCE = 1e-9        # |market_balance| may be at most this share of the money supply (float rounding)
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
