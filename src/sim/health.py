"""Health report for a headless run: is the economy sound, and is there trading to be done?

    python -m src.sim.health runs/<name> [runs/<other> ...]

reads the CSVs ``python -m src.sim.run`` wrote (and its ``meta.json``) and
runs the checks of ``docs/p1_living_market.md`` ("Health metrics") on them.
Each check gives one ``Finding``: ok, or its severity (``FAIL`` for the checks
that say the economy is broken, ``warn`` for those that say it is off its
calibration), a headline number (``value``, what the 20-seed table of
``python -m src.sim.sweep`` compares across seeds), and a line naming the worst
offender and when.

The checks, in report order (thresholds are the module's constants):

- **market balance** (fail): the market place holds no money, so each day the
  town's money must change by exactly what crossed its border; the
  ``market_balance`` column, what those flows do not explain, must be zero
  within ``BALANCE_TOLERANCE`` of the money supply.
- **bad numbers** (fail): any NaN or infinity anywhere, or a negative stock,
  purse or head count.
- **price at clamp** (fail): a good's volume factor (from its stock against its
  target) pinned at ``MARKET_VOLUME_FACTOR_MIN`` or ``_MAX`` for more than
  ``CLAMP_DAYS`` days running.
- **price far from outside** (warn): a good's price outside ``FAR_BAND`` times
  its outside price for more than ``FAR_DAYS`` days running.
- **hunger** (fail): a class's basic fulfilment below ``HUNGER_THRESHOLD`` for
  more than ``HUNGER_DAYS`` days running.
- **poorly supplied** (warn): a class's mean basic fulfilment below
  ``SUPPLIED_MIN``.
- **money supply** (fail): the town's money (purses, workshops, owners) over the
  last ``RECENT_YEARS`` years outside ``MONEY_BAND`` times its median over the
  whole run (so a drift and a late collapse both show).
- **population** (fail): the town's citizens outside ``POPULATION_BAND`` times
  their number on the first day.
- **population trend** (fail): the citizens' trend over the last
  ``RECENT_YEARS`` years (least squares) steeper than ``POPULATION_TREND_MAX``
  a year, either way.
- **happiness** (warn): a class's mean happiness outside ``HAPPINESS_BAND``.
- **workshop cash** (fail): a workshop's cash below zero for more than
  ``NEGATIVE_CASH_DAYS`` days running.
- **dead workshop** (warn): a workshop that ran (almost) nothing, under
  ``DEAD_SHARE`` of its capacity, for more than ``DEAD_DAYS`` days running.
  Not "utilisation 0", which a glide never reaches: a workshop the margins
  have given up on and one that plans but never gets its hands or inputs are
  both dead.
- **structural shortage** (warn): a good the merchants import at its limit
  (at least ``AT_LIMIT_SHARE`` of its ``import_limit``) on more than
  ``SHORTAGE_DAYS_SHARE`` of days.
- **recipe margins** (warn): every building's recipe, at the goods' outside
  prices and its class's base income (the cheapest labour there is), earns at
  least ``MARGIN_FULL``; one that does not can never run flat out, whatever
  the town's prices do: a bug in the data. Read from the run's ``meta.json``;
  ``tests/sim/test_data.py`` holds the game's data to it too.
- **comfort band**, **luxury band**, **goods run short** (warn): the town should
  run slightly short (the calibration target): each class's mean comfort
  fulfilment in ``COMFORT_BAND`` and luxury in ``LUXURY_BAND``, and at least
  ``SHORT_GOODS_MIN`` goods run short (some class bought less than
  ``SHORT_BELOW`` of its whole basket of it, because it was dear, the market had
  run out or its money had: the runner's ``least_share``) on more than
  ``SHORT_DAYS_SHARE`` of days.

And a measure with no threshold yet, printed after them:

- **tradability**: per good, the median over the run of ``(30-day max price −
  30-day min price) / price``, and how often that range, over a lot worth
  ``TRADE_LOT_VALUE`` at the day's price (whole units, at least 1), beats twice
  what a round trip of that lot costs the player (two fees plus the slippage
  of buying and selling it at that day's stock). It says whether a patient
  trader could live off a good's swings.

A check reads only the columns it needs, from a ``RunData``: the tests build
one from a handful of hand-written rows.
"""
import argparse
import csv
import json
import math
import os
import statistics
import sys
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from ..config.constants import (
    HUNGER_THRESHOLD, INITIAL_TRANSACTION_COST, MARGIN_FULL, MARKET_VOLUME_FACTOR_MAX, MARKET_VOLUME_FACTOR_MIN,
)
from .calendar import DAYS_PER_YEAR
from .data import RecipeDef
from .run import ALL_CLASSES, GOODS_FILE, META_FILE, POPULATION_FILE, TOWN_FILE, WORKSHOPS_FILE
from .state import GoodState
from .systems import market
from .systems.production import batch_margin

BALANCE_TOLERANCE = 1e-9        # |market_balance| may be at most this share of the money supply (float rounding)
NEGATIVE_TOLERANCE = 1e-9       # a stock, purse or count counts as negative below minus this (float dust)
CLAMP_DAYS = 14                 # a volume factor at its clamp for more days running than this fails
CLAMP_EPSILON = 1e-9            # how close to a clamp counts as at it
FAR_BAND = (0.5, 2.0)           # a price outside this band of its outside price...
FAR_DAYS = 28                   # ...for more days running than this is a warning
HUNGER_DAYS = 7                 # basic fulfilment under HUNGER_THRESHOLD for more days running than this fails
SUPPLIED_MIN = 0.9              # a class's mean basic fulfilment under this is a warning
RECENT_YEARS = 10               # the money supply's band and the population's trend look at the last years only
MONEY_BAND = (1 / 3, 3.0)       # the recent money supply must stay within this band of the run's median
POPULATION_BAND = (0.5, 1.2)    # the citizens must stay within this band of the first day's
POPULATION_TREND_MAX = 0.02     # a recent trend steeper than this a year (either way) fails
HAPPINESS_BAND = (50.0, 90.0)   # each class's mean happiness, else a warning
NEGATIVE_CASH_DAYS = 56         # a workshop's cash below zero for more days running than this fails (two seasons)
DEAD_SHARE = 0.01               # a day a workshop ran under this share of its capacity is a dead day...
DEAD_DAYS = DAYS_PER_YEAR       # ...and more of them running than this (a year) is a warning
AT_LIMIT_SHARE = 0.95           # a day a good was imported at its limit: at least this share of import_limit...
SHORTAGE_DAYS_SHARE = 0.5       # ...on more than this share of days is a structural shortage (warning)
COMFORT_BAND = (0.80, 0.95)     # each class's mean comfort fulfilment, for a town running slightly short
LUXURY_BAND = (0.30, 0.70)      # ...and its mean luxury fulfilment
SHORT_GOODS_MIN = 3             # at least this many goods...
SHORT_DAYS_SHARE = 0.05         # ...run short on more than this share of days
SHORT_BELOW = 0.90              # a day is short for a good when some class bought less than this share of its basket
TRADE_WINDOW_DAYS = 30
TRADE_LOT_VALUE = 100.0         # a small trader's order, in money at the day's price (rounded to whole units)

OK, WARN, FAIL = "ok", "warn", "FAIL"

Row = Dict[str, str]


# -- the run's data ----------------------------------------------------------

@dataclass
class RunData:
    """A run's rows, as read from its CSVs (strings, as csv gives them), and its meta data."""
    goods: List[Row] = field(default_factory=list)
    population: List[Row] = field(default_factory=list)
    workshops: List[Row] = field(default_factory=list)
    town: List[Row] = field(default_factory=list)
    meta: Dict = field(default_factory=dict)

    @classmethod
    def load(cls, run_dir: str) -> "RunData":
        meta_path = os.path.join(run_dir, META_FILE)
        meta = {}
        if os.path.exists(meta_path):
            with open(meta_path, encoding="utf-8") as f:
                meta = json.load(f)
        return cls(goods=_read(os.path.join(run_dir, GOODS_FILE)),
                   population=_read(os.path.join(run_dir, POPULATION_FILE)),
                   workshops=_read(os.path.join(run_dir, WORKSHOPS_FILE)),
                   town=_read(os.path.join(run_dir, TOWN_FILE)),
                   meta=meta)

    def classes(self) -> List[Row]:
        """The population rows of the classes themselves (not the town's ``All``)."""
        return [r for r in self.population if r["class"] != ALL_CLASSES]

    def goods_defs(self) -> Dict[str, Dict]:
        """The goods' definitions the run used (from meta.json), by name."""
        return {g["name"]: g for g in self.meta.get("definitions", {}).get("goods", [])}


def _read(path: str) -> List[Row]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _by(rows: Iterable[Row], key: str) -> Dict[str, List[Row]]:
    """The rows grouped by one column, each group in the order of the file (by day)."""
    groups: Dict[str, List[Row]] = {}
    for row in rows:
        groups.setdefault(row[key], []).append(row)
    return groups


def _when(row: Row) -> str:
    """A row's day as the game names it, for the report: 'day 812 (5 Summer 1529)'."""
    if "season" in row and "year" in row:
        return f"day {row['day']} ({row.get('day_of_season', '?')} {row['season']} {row['year']})"
    return f"day {row.get('day', '?')}"


@dataclass
class Streak:
    """The longest run of consecutive rows a condition held on."""
    length: int = 0
    first: Optional[Row] = None
    last: Optional[Row] = None

    def where(self) -> str:
        if not self.length:
            return "never"
        if self.length == 1:
            return _when(self.first)
        return f"{_when(self.first)} to {_when(self.last)}"


def longest_streak(rows: Sequence[Row], condition: Callable[[Row], bool]) -> Streak:
    """The longest run of consecutive *rows* *condition* holds on (rows of one good, class or workshop)."""
    best, start, length = Streak(), 0, 0
    for i, row in enumerate(rows):
        if condition(row):
            if not length:
                start = i
            length += 1
            if length > best.length:
                best = Streak(length, rows[start], row)
        else:
            length = 0
    return best


def _worst_streak(groups: Dict[str, List[Row]], condition: Callable[[Row], bool]) -> Tuple[str, Streak]:
    """The group with the longest streak, and the streak ('' and an empty one when none holds anywhere)."""
    worst_name, worst = "", Streak()
    for name, rows in groups.items():
        s = longest_streak(rows, condition)
        if s.length > worst.length:
            worst_name, worst = name, s
    return worst_name, worst


# -- findings and the registry of checks ------------------------------------

@dataclass
class Finding:
    """What one check found in one run."""
    check: str
    severity: str               # what it is when not ok: FAIL or WARN
    ok: bool
    value: float                # the headline number (days, a share, a ratio; see the check's ``unit``)
    text: str                   # one line: the worst offender, and when

    @property
    def status(self) -> str:
        return OK if self.ok else self.severity


@dataclass(frozen=True)
class Check:
    """A health check: its name, how bad a miss is, its threshold for the table, and its function."""
    name: str
    severity: str
    threshold: str              # as the table shows it
    unit: str                   # what ``value`` counts, as the table shows it
    higher_is_worse: bool       # which way the worst seed lies
    run: Callable[[RunData], Finding]


CHECKS: List[Check] = []


def check(name: str, severity: str, threshold: str, unit: str, higher_is_worse: bool = True):
    """Registers a check function ``f(data) -> (ok, value, text)`` under *name*, in report order."""
    def register(fn: Callable[[RunData], Tuple[bool, float, str]]):
        def run(data: RunData) -> Finding:
            ok, value, text = fn(data)
            return Finding(name, severity, ok, value, text)
        run.__name__ = run.__qualname__ = fn.__name__
        run.__doc__ = fn.__doc__
        CHECKS.append(Check(name, severity, threshold, unit, higher_is_worse, run))
        return run
    return register


def evaluate(data: RunData) -> List[Finding]:
    """Every check's finding for one run, in report order."""
    return [c.run(data) for c in CHECKS]


# -- the checks ---------------------------------------------------------------

def market_balance(town_rows: Sequence[Row]) -> float:
    """The worst day's |market_balance| as a share of the money supply (0 when the books are sound)."""
    worst = 0.0
    for row in town_rows:
        supply = max(1.0, abs(float(row["money_supply"])))
        worst = max(worst, abs(float(row["market_balance"])) / supply)
    return worst


@check("market balance", FAIL, f"<= {BALANCE_TOLERANCE:.0e} of money", "share of money")
def check_market_balance(data: RunData):
    worst = market_balance(data.town)
    return worst <= BALANCE_TOLERANCE, worst, f"worst day {worst:.2e} of the money supply"


# The columns that may never go negative, per file
NON_NEGATIVE = {"goods": ("stock",), "population": ("purse", "count")}


def bad_numbers(data: RunData) -> List[str]:
    """Every NaN or infinity, and every negative stock, purse or head count, as 'file: column, entity, day'."""
    found = []
    for file, rows in (("goods", data.goods), ("population", data.population),
                       ("workshops", data.workshops), ("town", data.town)):
        non_negative = NON_NEGATIVE.get(file, ())
        for row in rows:
            for column, text in row.items():
                if not text or not (text[0] in "-+.0123456789" or text[:3].lower() in ("nan", "inf")):
                    continue        # a name, a season, or a blank (the town's wage)
                try:
                    value = float(text)
                except ValueError:
                    continue
                who = row.get("good") or row.get("class") or row.get("workshop") or "town"
                if not math.isfinite(value):
                    found.append(f"{file}: {column} {text} for {who} on {_when(row)}")
                elif column in non_negative and value < -NEGATIVE_TOLERANCE:
                    found.append(f"{file}: {column} {value:.3g} for {who} on {_when(row)}")
    return found


@check("bad numbers", FAIL, "none", "values")
def check_bad_numbers(data: RunData):
    found = bad_numbers(data)
    if not found:
        return True, 0, "no NaN, infinity, negative stock, purse or head count"
    more = f" (and {len(found) - 3} more)" if len(found) > 3 else ""
    return False, len(found), "; ".join(found[:3]) + more


def volume_factor_of(row: Row) -> float:
    """The day's volume factor of a good, from its stock against its target (as the market prices it)."""
    good = GoodState(name=row["good"], stock=float(row["stock"]), target_stock=float(row["target_stock"]))
    return market.volume_factor(good)


def _at_clamp(row: Row) -> bool:
    factor = volume_factor_of(row)
    return factor <= MARKET_VOLUME_FACTOR_MIN + CLAMP_EPSILON or factor >= MARKET_VOLUME_FACTOR_MAX - CLAMP_EPSILON


@check("price at clamp", FAIL, f"<= {CLAMP_DAYS} days running", "days running")
def check_price_at_clamp(data: RunData):
    good, streak = _worst_streak(_by(data.goods, "good"), _at_clamp)
    if not streak.length:
        return True, 0, "no good's volume factor ever at its clamp"
    side = "glut floor" if volume_factor_of(streak.first) < 1 else "scarcity ceiling"
    return (streak.length <= CLAMP_DAYS, streak.length,
            f"{good} at its {side} for {streak.length} days running, {streak.where()}")


def _far_from_outside(row: Row) -> bool:
    ratio = float(row["price"]) / float(row["outside_price"])
    return not FAR_BAND[0] <= ratio <= FAR_BAND[1]


@check("price far from outside", WARN,
       f"<= {FAR_DAYS} days outside {FAR_BAND[0]:g}-{FAR_BAND[1]:g}x", "days running")
def check_price_far(data: RunData):
    groups = _by(data.goods, "good")
    good, streak = _worst_streak(groups, _far_from_outside)
    if not streak.length:
        return True, 0, f"every price always within {FAR_BAND[0]:g}-{FAR_BAND[1]:g}x its outside price"
    rows = groups[good]
    ratio = float(streak.first["price"]) / float(streak.first["outside_price"])
    total = sum(_far_from_outside(r) for r in rows)
    return (streak.length <= FAR_DAYS, streak.length,
            f"{good} at {ratio:.2f}x its outside price for {streak.length} days running, {streak.where()} "
            f"({total / len(rows):.1%} of all days)")


@check("hunger", FAIL, f"<= {HUNGER_DAYS} days under {HUNGER_THRESHOLD:g} basic", "days running")
def check_hunger(data: RunData):
    cls, streak = _worst_streak(_by(data.classes(), "class"),
                                lambda r: float(r["fulfilment_basic"]) < HUNGER_THRESHOLD)
    if not streak.length:
        return True, 0, f"no class's basic fulfilment ever under {HUNGER_THRESHOLD:g}"
    return (streak.length <= HUNGER_DAYS, streak.length,
            f"{cls} under {HUNGER_THRESHOLD:g} basic fulfilment for {streak.length} days running, {streak.where()}")


def mean_by_class(data: RunData, column: str) -> Dict[str, float]:
    """Per class, its mean of a population column over the run."""
    return {cls: statistics.fmean(float(r[column]) for r in rows) for cls, rows in _by(data.classes(), "class").items()}


@check("poorly supplied", WARN, f"mean basic >= {SUPPLIED_MIN:g}", "lowest mean", higher_is_worse=False)
def check_poorly_supplied(data: RunData):
    means = mean_by_class(data, "fulfilment_basic")
    if not means:
        return True, 1.0, "no classes"
    cls = min(means, key=means.get)
    low = sorted((c for c in means if means[c] < SUPPLIED_MIN), key=means.get)
    text = f"lowest mean basic fulfilment {cls} {means[cls]:.3f}"
    if low:
        text += "; under " + f"{SUPPLIED_MIN:g}: " + ", ".join(f"{c} {means[c]:.3f}" for c in low)
    return not low, means[cls], text


def recent(rows: Sequence[Row], years: Optional[float] = None) -> Sequence[Row]:
    """The rows of the last *years* years (``RECENT_YEARS`` if not given; all of them if the run is shorter)."""
    return rows[-round((RECENT_YEARS if years is None else years) * DAYS_PER_YEAR):]


@check("money supply", FAIL, f"last {RECENT_YEARS}y within {MONEY_BAND[0]:.2g}-{MONEY_BAND[1]:g}x median",
       "worst ratio")
def check_money_supply(data: RunData):
    if not data.town:
        return True, 1.0, "no days"
    median = statistics.median(float(r["money_supply"]) for r in data.town)
    if median <= 0:
        return False, math.inf, f"median money supply {median:.0f}"
    late = recent(data.town)
    low = min(late, key=lambda r: float(r["money_supply"]))
    high = max(late, key=lambda r: float(r["money_supply"]))
    lo, hi = float(low["money_supply"]) / median, float(high["money_supply"]) / median
    worst = max(hi, 1 / lo if lo > 0 else math.inf)
    ok = MONEY_BAND[0] <= lo and hi <= MONEY_BAND[1]
    return ok, worst, (f"last {RECENT_YEARS} years {lo:.2f}-{hi:.2f}x the run's median of {median:,.0f} "
                       f"(low {_when(low)}, high {_when(high)})")


@check("population", FAIL, f"within {POPULATION_BAND[0]:g}-{POPULATION_BAND[1]:g}x start", "worst ratio")
def check_population(data: RunData):
    if not data.town:
        return True, 1.0, "no days"
    start = float(data.town[0]["citizens"])
    low = min(data.town, key=lambda r: float(r["citizens"]))
    high = max(data.town, key=lambda r: float(r["citizens"]))
    lo, hi = float(low["citizens"]) / start, float(high["citizens"]) / start
    housing = sum(data.meta.get("town", {}).get("house_capacities", []) or [0])
    worst = max(hi, 1 / lo if lo > 0 else math.inf)
    text = f"{lo:.2f}-{hi:.2f}x the {start:.0f} of the first day (low {_when(low)}, high {_when(high)})"
    if housing:
        text += f"; ends at {float(data.town[-1]['citizens']):.0f} of {housing} places"
    return POPULATION_BAND[0] <= lo and hi <= POPULATION_BAND[1], worst, text


def trend_per_year(values: Sequence[float]) -> float:
    """A daily series' least-squares slope, as a share of its mean a year (0.01 = 1 %/year)."""
    n = len(values)
    if n < 2:
        return 0.0
    mean_x, mean_y = (n - 1) / 2, statistics.fmean(values)
    if mean_y == 0:
        return 0.0
    slope = (sum((i - mean_x) * (v - mean_y) for i, v in enumerate(values))
             / sum((i - mean_x) ** 2 for i in range(n)))
    return slope * DAYS_PER_YEAR / mean_y


@check("population trend", FAIL, f"last {RECENT_YEARS}y within +-{POPULATION_TREND_MAX:.0%}/year", "|trend|/year")
def check_population_trend(data: RunData):
    trend = trend_per_year([float(r["citizens"]) for r in recent(data.town)])
    return (abs(trend) <= POPULATION_TREND_MAX, abs(trend),
            f"{trend:+.2%} a year over the last {RECENT_YEARS} years")


@check("happiness", WARN, f"class means {HAPPINESS_BAND[0]:g}-{HAPPINESS_BAND[1]:g}", "classes outside")
def check_happiness(data: RunData):
    means = mean_by_class(data, "happiness")
    outside = [c for c, m in means.items() if not HAPPINESS_BAND[0] <= m <= HAPPINESS_BAND[1]]
    text = ", ".join(f"{c} {m:.1f}" + (" (!)" if c in outside else "") for c, m in means.items())
    return not outside, len(outside), "mean happiness " + text


@check("workshop cash", FAIL, f"<= {NEGATIVE_CASH_DAYS} days running below 0", "days running")
def check_workshop_cash(data: RunData):
    ws, streak = _worst_streak(_by(data.workshops, "workshop"), lambda r: float(r["cash"]) < 0)
    if not streak.length:
        return True, 0, "no workshop's cash ever below zero"
    return (streak.length <= NEGATIVE_CASH_DAYS, streak.length,
            f"{ws} below zero for {streak.length} days running, {streak.where()}")


def _dead(row: Row) -> bool:
    return float(row["done_yesterday"]) < DEAD_SHARE * float(row["capacity"])


@check("dead workshop", WARN, f"<= {DEAD_DAYS} days running idle", "days running")
def check_dead_workshop(data: RunData):
    groups = _by(data.workshops, "workshop")
    dead = []
    for ws, rows in groups.items():
        s = longest_streak(rows, _dead)
        if s.length > DEAD_DAYS:
            dead.append((s.length, ws, s))
    ws, streak = _worst_streak(groups, _dead)
    if not streak.length:
        return True, 0, f"every workshop ran at least {DEAD_SHARE:.0%} of its capacity every day"
    text = f"longest idle: {ws}, {streak.length} days running, {streak.where()}"
    if len(dead) > 1:
        text += f"; idle over a year: {len(dead)} workshops (" + ", ".join(w for _, w, _ in sorted(dead)[::-1]) + ")"
    return not dead, streak.length, text


def at_limit_shares(data: RunData) -> Dict[str, float]:
    """Per good with an import limit, the share of days it was imported at (nearly) that limit."""
    limits = {name: float(g.get("import_limit", 0)) for name, g in data.goods_defs().items()}
    shares = {}
    for good, rows in _by(data.goods, "good").items():
        limit = limits.get(good, 0.0)
        if limit > 0:
            shares[good] = sum(float(r["imported"]) >= AT_LIMIT_SHARE * limit for r in rows) / len(rows)
    return shares


@check("structural shortage", WARN, f"<= {SHORTAGE_DAYS_SHARE:.0%} of days at import limit", "share of days")
def check_structural_shortage(data: RunData):
    shares = at_limit_shares(data)
    if not data.goods_defs():
        return True, 0.0, "no import limits known (meta.json missing)"
    if not shares or not max(shares.values()):
        return True, 0.0, "no good ever imported at its limit"
    over = sorted((g for g, s in shares.items() if s > SHORTAGE_DAYS_SHARE), key=lambda g: -shares[g])
    top = sorted((g for g in shares if shares[g] > 0), key=lambda g: -shares[g])[:4]
    text = "at the limit on: " + ", ".join(f"{g} {shares[g]:.0%}" for g in (over or top))
    return not over, max(shares.values()), text


@dataclass
class RecipeMargin:
    building: str
    recipe: str
    workers_class: str
    at_base: float              # its margin at outside prices, paying its class's base income (the cheapest labour)
    at_cap: float               # ...and paying its class's wage cap (where the wage sits when hands are short)


def recipe_margins(definitions: Dict) -> List[RecipeMargin]:
    """Every building's recipe's margin at the goods' outside prices, at its class's base income and wage cap.

    *definitions* is ``dataclasses.asdict(Definitions)``, as meta.json keeps it.
    A recipe under ``MARGIN_FULL`` even at base income can never run flat out,
    whatever the town's prices do to it: a bug in the data.
    """
    outside = {g["name"]: g["outside_price"] for g in definitions.get("goods", [])}
    needs = {n["name"]: n for n in definitions.get("needs", [])}
    recipes = {r["id"]: r for r in definitions.get("recipes", [])}
    result = []
    for b in definitions.get("buildings", []):
        r = recipes[b["recipe"]]
        recipe = RecipeDef(id=r["id"], name=r.get("name", r["id"]), inputs=r["inputs"], outputs=r["outputs"],
                           labour=r["labour"])
        cls = needs[b["workers_class"]]
        result.append(RecipeMargin(b["type"], r["id"], b["workers_class"],
                                   batch_margin(recipe, cls["base_income"], outside),
                                   batch_margin(recipe, cls["wage_cap"], outside)))
    return result


@check("recipe margins", WARN, f">= {MARGIN_FULL:g} at outside prices, base income", "lowest margin",
       higher_is_worse=False)
def check_recipe_margins(data: RunData):
    margins = recipe_margins(data.meta.get("definitions", {}))
    if not margins:
        return True, MARGIN_FULL, "no recipes known (meta.json missing)"
    low = sorted((m for m in margins if m.at_base < MARGIN_FULL), key=lambda m: m.at_base)
    worst = min(margins, key=lambda m: m.at_base)
    if not low:
        return True, worst.at_base, (f"every recipe can run flat out at outside prices; the thinnest: {worst.building} "
                                     f"{worst.at_base:+.2f} at base income, {worst.at_cap:+.2f} at the wage cap")
    return False, worst.at_base, "under MARGIN_FULL even at base income: " + ", ".join(
        f"{m.building} ({m.recipe}) {m.at_base:+.2f}" for m in low)


def fulfilment_by_class(population_rows: Sequence[Row]) -> Dict[str, Dict[str, float]]:
    """Per class, its mean fulfilment of each tier over the run."""
    sums: Dict[str, Dict[str, List[float]]] = {}
    for row in population_rows:
        if row["class"] == ALL_CLASSES:
            continue
        tiers = sums.setdefault(row["class"], {"comfort": [], "luxury": []})
        for tier in tiers:
            tiers[tier].append(float(row[f"fulfilment_{tier}"]))
    return {cls: {tier: statistics.mean(v) for tier, v in tiers.items()} for cls, tiers in sums.items()}


def _band_check(data: RunData, tier: str, band: Tuple[float, float]):
    means = {cls: tiers[tier] for cls, tiers in fulfilment_by_class(data.population).items()}
    outside = [c for c, m in means.items() if not band[0] <= m <= band[1]]
    text = ", ".join(f"{c} {m:.2f}" + (" (!)" if c in outside else "") for c, m in means.items())
    return not outside, len(outside), f"mean {tier} fulfilment " + text


@check("comfort band", WARN, f"class means {COMFORT_BAND[0]:.2f}-{COMFORT_BAND[1]:.2f}", "classes outside")
def check_comfort_band(data: RunData):
    return _band_check(data, "comfort", COMFORT_BAND)


@check("luxury band", WARN, f"class means {LUXURY_BAND[0]:.2f}-{LUXURY_BAND[1]:.2f}", "classes outside")
def check_luxury_band(data: RunData):
    return _band_check(data, "luxury", LUXURY_BAND)


def short_days(goods_rows: Sequence[Row]) -> Dict[str, float]:
    """Per good, the share of days the town ran short of it: some class bought less than SHORT_BELOW of its basket.

    For whatever reason: the price (it bought less of a dear good), an empty
    market, or an empty purse. ``least_share`` is the worst class's share.
    """
    counts: Dict[str, List[int]] = {}
    for row in goods_rows:
        c = counts.setdefault(row["good"], [0, 0])
        c[0] += float(row["least_share"]) < SHORT_BELOW
        c[1] += 1
    return {good: below / days for good, (below, days) in counts.items()}


@check("goods run short", WARN, f">= {SHORT_GOODS_MIN} goods short on > {SHORT_DAYS_SHARE:.0%} of days", "goods",
       higher_is_worse=False)
def check_goods_run_short(data: RunData):
    shares = short_days(data.goods)
    short = sorted((g for g, s in shares.items() if s > SHORT_DAYS_SHARE), key=lambda g: -shares[g])
    return (len(short) >= SHORT_GOODS_MIN, len(short),
            f"{len(short)} goods some class bought under {SHORT_BELOW:.0%} of its basket of on more than "
            f"{SHORT_DAYS_SHARE:.0%} of days" + (": " + ", ".join(f"{g} {shares[g]:.0%}" for g in short) if short else ""))


# -- tradability (a measure, no threshold yet) --------------------------------

@dataclass
class Tradability:
    good: str
    median_range: float         # median of (window max − window min) / price
    share_worth_it: float       # share of days the window's range over a TRADE_LOT_VALUE lot beats 2 × its round trip's cost
    days: int                   # days measured (those with a full window)


def lot_units(price: float, value: float = TRADE_LOT_VALUE) -> int:
    """The whole units a lot worth *value* holds at *price*, at least 1."""
    return max(1, round(value / price))


def round_trip_cost(row: Row, units: int, fee: float = INITIAL_TRANSACTION_COST) -> float:
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


def tradability(goods_rows: Sequence[Row], window: int = TRADE_WINDOW_DAYS,
                lot_value: float = TRADE_LOT_VALUE, fee: float = INITIAL_TRANSACTION_COST) -> List[Tradability]:
    """Per good, how wide its prices swing over *window* days, and how often that pays for a round trip."""
    result = []
    for good, rows in _by(goods_rows, "good").items():
        prices = [float(r["price"]) for r in rows]
        ranges, worth = [], 0
        for i in range(window - 1, len(rows)):
            span = prices[i - window + 1:i + 1]
            price_range = max(span) - min(span)
            ranges.append(price_range / prices[i])
            units = lot_units(prices[i], lot_value)
            if price_range * units > 2 * round_trip_cost(rows[i], units, fee):
                worth += 1
        days = len(ranges)
        result.append(Tradability(good, statistics.median(ranges) if ranges else 0.0,
                                  worth / days if days else 0.0, days))
    return result


# -- the report -----------------------------------------------------------------

def format_finding(f: Finding) -> str:
    return f"[{f.status:>4}] {f.check}: {f.text}"


def report(run_dir: str, show_tradability: bool = True) -> int:
    """Print the report for one run; returns 1 if a check failed (warnings never fail)."""
    data = RunData.load(run_dir)
    findings = evaluate(data)
    for f in findings:
        print(format_finding(f))
    fails = sum(f.status == FAIL for f in findings)
    warns = sum(f.status == WARN for f in findings)
    print(f"       {len(findings) - fails - warns} ok, {warns} warnings, {fails} failed")
    if show_tradability:
        print(f"[info] tradability: {TRADE_WINDOW_DAYS}-day price range, and the share of days it beats "
              f"2 x the round trip of a {TRADE_LOT_VALUE:g}g lot (fees {INITIAL_TRANSACTION_COST} each, plus slippage)")
        print(f"       {'good':12} {'median range':>12} {'worth it':>9}")
        for t in sorted(tradability(data.goods), key=lambda t: -t.median_range):
            print(f"       {t.good:12} {t.median_range:12.1%} {t.share_worth_it:9.1%}")
    return 1 if fails else 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.sim.health", description=__doc__.split("\n\n")[0])
    parser.add_argument("runs", nargs="+", help="run folders written by python -m src.sim.run")
    parser.add_argument("--no-tradability", action="store_true", help="skip the tradability table (the slow part)")
    args = parser.parse_args(argv)
    status = 0
    for run_dir in args.runs:
        print(f"== {run_dir}")
        status |= report(run_dir, show_tradability=not args.no_tradability)
    return status


if __name__ == "__main__":
    sys.exit(main())
