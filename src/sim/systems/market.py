"""The market: prices from stock against demand, the outside world's prices, and trading.

Functions on a ``GoodState`` (and its ``GoodDef``, and the simulation's random
generator where they draw). ``docs/pricing.md`` and ``docs/p1_living_market.md``
are their specification.

    price = reference × volume_factor(stock / target_stock) × noise
    reference = outside price × a running well wish's shock

The outside price walks slowly around its mean (``step_outside``, daily); the
noise is small and mean-reverting (``step_noise``, every price tick).
Households and merchants trade in hourly slices (``clear_buyers``,
``merchants``); the player trades unit by unit with slippage (``quote``).
"""
import datetime
import math
import random
from typing import Dict, Optional, Tuple

from ...config.constants import (
    MARKET_VOLUME_ELASTICITY, MARKET_VOLUME_FACTOR_MAX, MARKET_VOLUME_FACTOR_MIN,
    MARKET_VOLUME_GLUT_RATIO, MARKET_VOLUME_SCARCE_RATIO, PRICE_NOISE_CLAMP,
    PRICE_NOISE_PERSISTENCE, TARGET_STOCK_GLIDE,
    WELL_WISH_DURATION_DAYS, WELL_WISH_SHOCK_FACTOR,
)
from ..calendar import season_factor
from ..data import GoodDef
from ..state import GoodFlows, GoodState


def create_good(definition: GoodDef, moment: datetime.datetime) -> GoodState:
    """A good at its outside price's mean, holding its minimum stock until a town is founded."""
    base = definition.outside_price * season_factor(definition.outside_seasons, moment)
    good = GoodState(
        name=definition.name,
        stock=definition.min_target_stock,
        target_stock=definition.min_target_stock,
        outside_base=base,
        outside_price=base,
    )
    good.price_history_ticks = [price(good)]
    good.price_history_daily = [price(good)]
    return good


# -- the price -----------------------------------------------------------

def volume_factor(good: GoodState, quantity: Optional[float] = None) -> float:
    """How much dearer or cheaper the market's stock makes the good.

    1.0 between the scarce and glut ratios of the target stock; past them the
    factor follows (threshold / ratio) ** elasticity, clamped, so the further
    the stock strays the more the price moves.

    Args:
        good: The good.
        quantity: The stock to price at; the market's current one if omitted.
    """
    if quantity is None:
        quantity = good.stock
    ratio = quantity / good.target_stock
    if ratio <= 0:
        return MARKET_VOLUME_FACTOR_MAX
    if ratio < MARKET_VOLUME_SCARCE_RATIO:
        factor = (MARKET_VOLUME_SCARCE_RATIO / ratio) ** MARKET_VOLUME_ELASTICITY
    elif ratio > MARKET_VOLUME_GLUT_RATIO:
        factor = (MARKET_VOLUME_GLUT_RATIO / ratio) ** MARKET_VOLUME_ELASTICITY
    else:
        return 1.0
    return min(MARKET_VOLUME_FACTOR_MAX, max(MARKET_VOLUME_FACTOR_MIN, factor))


def ratio_for_factor(factor: float) -> float:
    """The lowest stock-to-target ratio at which the volume factor is *factor* (clamped to its range)."""
    factor = min(MARKET_VOLUME_FACTOR_MAX, max(MARKET_VOLUME_FACTOR_MIN, factor))
    if factor > 1.0:
        return MARKET_VOLUME_SCARCE_RATIO / factor ** (1.0 / MARKET_VOLUME_ELASTICITY)
    if factor < 1.0:
        return MARKET_VOLUME_GLUT_RATIO / factor ** (1.0 / MARKET_VOLUME_ELASTICITY)
    return MARKET_VOLUME_SCARCE_RATIO


def reference(good: GoodState) -> float:
    """The price the volume factor works on: the outside price, times a running well wish's shock."""
    return good.outside_price * good.shock_factor


def price(good: GoodState) -> float:
    """The current market price."""
    return reference(good) * volume_factor(good) * math.exp(good.noise)


def set_price(good: GoodState, value: float) -> None:
    """Make the price show *value* now, by moving the outside price (its walk carries on from there)."""
    outside = float(value) / (good.shock_factor * volume_factor(good) * math.exp(good.noise))
    good.outside_price = outside
    good.outside_dev = math.log(outside / good.outside_base) if good.outside_base > 0 else 0.0


def quote(good: GoodState, quantity: float, buying: bool) -> float:
    """What a trade of this many units comes to, with slippage.

    Each unit is priced at its own stock, so a big order moves the price
    against the trader as it goes: a bought unit at the stock before it is
    taken (the first one at the shown price), a sold unit at the stock after it
    is added. Buying and selling back the same units cancel out. A fraction of
    a unit is priced as the next whole one, pro rata.

    Args:
        good: The good.
        quantity: Units in the order.
        buying: True for a purchase from the market, False for a sale to it.
    """
    whole = int(quantity)
    rest = quantity - whole
    q = good.stock
    if buying:
        total = sum(volume_factor(good, q - k) for k in range(whole))
        if rest > 0:
            total += rest * volume_factor(good, q - whole)
    else:
        total = sum(volume_factor(good, q + k + 1) for k in range(whole))
        if rest > 0:
            total += rest * volume_factor(good, q + whole + 1)
    return reference(good) * math.exp(good.noise) * total


def show_current_price(good: GoodState) -> None:
    """Let the chart's latest point show the price a trade has just moved."""
    if good.price_history_ticks:
        good.price_history_ticks[-1] = price(good)


# -- the clock -------------------------------------------------------------

def step_noise(good: GoodState, definition: GoodDef, rng: random.Random) -> None:
    """A price tick's step of the noise (one draw): mean-reverting, clamped."""
    n = good.noise * PRICE_NOISE_PERSISTENCE + definition.noise_sigma * rng.gauss(0.0, 1.0)
    good.noise = max(-PRICE_NOISE_CLAMP, min(PRICE_NOISE_CLAMP, n))


def step_outside(good: GoodState, definition: GoodDef, moment: datetime.datetime, rng: random.Random) -> None:
    """A day's step of the outside price's slow walk (one draw), with today's season factor."""
    good.outside_dev = (good.outside_dev * (1.0 - definition.outside_reversion)
                        + definition.outside_volatility * rng.gauss(0.0, 1.0))
    good.outside_base = definition.outside_price * season_factor(definition.outside_seasons, moment)
    good.outside_price = good.outside_base * math.exp(good.outside_dev)


def close_day(good: GoodState) -> None:
    """Yesterday's flows become ``yesterday``; today's start from nothing."""
    good.yesterday = good.today
    good.today = GoodFlows()


def update_target(good: GoodState, definition: GoodDef, demand: float, glide: float = TARGET_STOCK_GLIDE) -> None:
    """Move the demand average towards *demand* and the target stock with it.

    Args:
        glide: Share of the gap closed; 1 sets it outright (founding a town, loading an old save).
    """
    good.demand_avg += glide * (demand - good.demand_avg)
    good.target_stock = max(definition.min_target_stock, definition.target_stock_days * good.demand_avg)


def record_tick(good: GoodState) -> None:
    """A point on the price chart (once a price tick)."""
    good.price_history_ticks.append(price(good))


def record_day(good: GoodState) -> None:
    """A point in the bookkeeping price history (once a day)."""
    good.price_history_daily.append(price(good))


def fill_history(good: GoodState, ticks: int, days: int) -> None:
    """Give a good added after a save was made a flat history as long as the saved goods'."""
    now = price(good)
    good.price_history_ticks = [now] * max(ticks, 1)
    good.price_history_daily = [now] * max(days, 1)


# -- trading ---------------------------------------------------------------

def clear_buyers(good: GoodState, orders: Dict[str, float]) -> Tuple[Dict[str, float], float]:
    """Settle one slice's purchases of a good: one order, one price for everyone in it.

    When the stock cannot meet the orders, every buyer gets the same share.
    The stock goes down by what is filled.

    Args:
        good: The good.
        orders: Buyer -> units wanted in this slice.

    Returns:
        Buyer -> units filled, and the price each unit was settled at.
    """
    total = sum(orders.values())
    if total <= 0 or good.stock <= 0:
        return {buyer: 0.0 for buyer in orders}, price(good)
    share = min(1.0, good.stock / total)
    filled_total = total * share
    unit_price = quote(good, filled_total, buying=True) / filled_total
    good.stock = max(0.0, good.stock - filled_total)
    return {buyer: units * share for buyer, units in orders.items()}, unit_price


def merchants(good: GoodState, definition: GoodDef, slices: int) -> Tuple[float, float, float]:
    """The outside world's merchants in one slice: import above the import line, export below the export line.

    They go by the stock, not by the noise: the price without noise
    (``reference × volume_factor``) is what they compare with the lines and
    bring back to them, at most the slice's share of the good's daily limit.
    The market place pays importers the import line's price and is paid the
    export line's price by exporters.

    Args:
        good: The good.
        definition: Its definition (limits, transport cost).
        slices: Slices in a trading day.

    Returns:
        Units imported, units exported, and the money the market place paid (+) or got (−).
    """
    ref = reference(good)
    level = ref * volume_factor(good)
    import_line = ref + definition.transport_cost
    export_line = ref - definition.transport_cost
    if level > import_line and definition.import_limit > 0:
        wanted_ratio = ratio_for_factor(import_line / ref)
        units = min(definition.import_limit / slices, max(0.0, wanted_ratio * good.target_stock - good.stock))
        if units > 0:
            good.stock += units
            return units, 0.0, units * import_line
    elif level < export_line and export_line > 0 and definition.export_limit > 0:
        wanted_ratio = ratio_for_factor(export_line / ref)
        units = min(definition.export_limit / slices, good.stock, max(0.0, good.stock - wanted_ratio * good.target_stock))
        if units > 0:
            good.stock -= units
            return 0.0, units, -units * export_line
    return 0.0, 0.0, 0.0


# -- well wishes -----------------------------------------------------------

def apply_well_shock(good: GoodState, up: bool) -> None:
    """A well wish: the good's outside price ×(1 ± WELL_WISH_SHOCK_FACTOR) for WELL_WISH_DURATION_DAYS.

    The import and export lines move with it, so merchants follow the new level
    and the local price settles there. A second wish while one runs multiplies
    in and restarts the count.
    """
    good.shock_factor *= 1.0 + WELL_WISH_SHOCK_FACTOR if up else 1.0 - WELL_WISH_SHOCK_FACTOR
    good.shock_days = WELL_WISH_DURATION_DAYS


def tick_well_shock_day(good: GoodState) -> bool:
    """Count a day off a running well wish; the outside price is itself again when it runs out.

    Returns:
        True on the day the shock ended.
    """
    if good.shock_days <= 0:
        return False
    good.shock_days -= 1
    if good.shock_days == 0:
        good.shock_factor = 1.0
        return True
    return False

