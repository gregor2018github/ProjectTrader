"""The market: each good's price walk, volume factor, slippage, recovery and well shock.

Functions on a ``GoodState`` (and the simulation's random generator where they
draw). ``docs/pricing.md`` is their specification; the formulas are the ones
``Good`` had before the simulation core was split out, kept to the last bit.

    price = walk_price × volume_factor(market_quantity)
"""
import math
import random
from typing import Optional

from ...config.constants import (
    MARKET_VOLUME_DAILY_RECOVERY, MARKET_VOLUME_ELASTICITY, MARKET_VOLUME_FACTOR_MAX,
    MARKET_VOLUME_FACTOR_MIN, MARKET_VOLUME_GLUT_RATIO, MARKET_VOLUME_SCARCE_RATIO,
    PRICE_TICKS_PER_DAY, WELL_WISH_DURATION_DAYS, WELL_WISH_SHOCK_FACTOR,
)
from ..state import GoodState

# Share of the gap to the normal volume closed per price tick, so that a day's ticks close MARKET_VOLUME_DAILY_RECOVERY
_TICK_RECOVERY = 1.0 - (1.0 - MARKET_VOLUME_DAILY_RECOVERY) ** (1.0 / PRICE_TICKS_PER_DAY)

# The corridor rolled for a new good, as factors on its starting price
UPPER_BOUND_RANGE = (1.5, 3.5)
LOWER_BOUND_RANGE = (0.05, 0.80)


def create_good(name: str, start_price: float, start_quantity: int, rng: random.Random) -> GoodState:
    """A good as a new game has it: at its starting price and volume, with a rolled corridor.

    Draws twice from *rng* (the upper bound, then the lower).
    """
    walk = float(start_price)
    good = GoodState(
        name=name,
        base_price=walk,
        walk_price=walk,
        market_quantity=int(start_quantity),
        normal_quantity=max(1, int(start_quantity)),
        upper_bound=0.0,
        lower_bound=0.0,
    )
    good.price_history_daily = [price(good)]
    good.price_history_ticks = [price(good)]
    # The corridor bounds the walk, not the volume factor on top of it
    good.upper_bound = walk * rng.uniform(*UPPER_BOUND_RANGE)
    good.lower_bound = walk * rng.uniform(*LOWER_BOUND_RANGE)
    return good


def volume_factor(good: GoodState, quantity: Optional[float] = None) -> float:
    """How much dearer or cheaper the market's volume makes the good.

    1.0 between the scarce and glut ratios of the normal volume; past them
    the factor follows (threshold / ratio) ** elasticity, clamped, so the
    further the volume strays the more the price moves.

    Args:
        good: The good.
        quantity: The volume to price at; the market's current one if omitted.
    """
    if quantity is None:
        quantity = good.market_quantity
    ratio = quantity / good.normal_quantity
    if ratio <= 0:
        return MARKET_VOLUME_FACTOR_MAX
    if ratio < MARKET_VOLUME_SCARCE_RATIO:
        factor = (MARKET_VOLUME_SCARCE_RATIO / ratio) ** MARKET_VOLUME_ELASTICITY
    elif ratio > MARKET_VOLUME_GLUT_RATIO:
        factor = (MARKET_VOLUME_GLUT_RATIO / ratio) ** MARKET_VOLUME_ELASTICITY
    else:
        return 1.0
    return min(MARKET_VOLUME_FACTOR_MAX, max(MARKET_VOLUME_FACTOR_MIN, factor))


def price(good: GoodState) -> float:
    """The current market price: the random walk times the volume factor."""
    return good.walk_price * volume_factor(good)


def set_price(good: GoodState, value: float) -> None:
    """Set the price as it should show now, at the current volume (moves the walk)."""
    good.walk_price = float(value) / volume_factor(good)


def quote(good: GoodState, quantity: int, buying: bool) -> float:
    """What a trade of this many units comes to, before the trading fee.

    Each unit is priced at its own volume, so a big order moves the price
    against the trader as it goes: a bought unit at the volume before it is
    taken (the first one at the shown price), a sold unit at the volume after
    it is added. Buying and selling back the same units cancel out.

    Args:
        good: The good.
        quantity: Units in the order.
        buying: True for a purchase from the market, False for a sale to it.
    """
    q = good.market_quantity
    if buying:
        volumes = range(q, q - quantity, -1)
    else:
        volumes = range(q + 1, q + quantity + 1)
    return good.walk_price * sum(volume_factor(good, v) for v in volumes)


def take(good: GoodState, quantity: int) -> None:
    """Units bought from the market leave it; the chart's latest point shows the new price."""
    good.market_quantity -= quantity
    _show_current_price(good)


def put(good: GoodState, quantity: int) -> None:
    """Units sold to the market join it; the chart's latest point shows the new price."""
    good.market_quantity += quantity
    _show_current_price(good)


def _show_current_price(good: GoodState) -> None:
    """Let the chart's latest point show the price a trade has just moved."""
    if good.price_history_ticks:
        good.price_history_ticks[-1] = price(good)


def recover_volume(good: GoodState) -> None:
    """Move the market's volume a price tick's share back towards normal.

    A stand-in for traders restocking and townsfolk buying, until the town
    has a supply and demand of its own. Moves at least one unit while there
    is a gap, so it always arrives.
    """
    gap = good.normal_quantity - good.market_quantity
    if gap == 0:
        return
    step = max(1, math.floor(abs(gap) * _TICK_RECOVERY))
    good.market_quantity += step if gap > 0 else -step


def step_walk(good: GoodState, rng: random.Random) -> None:
    """One price tick's step of the random walk (one draw from *rng*).

    Free and volatile inside the corridor; calm and drifting back outside it;
    pushed up a little below 1 so cheap goods do not collapse towards 0.
    """
    if good.walk_price > good.upper_bound:
        mu = 0.999
        sigma = 0.01
    elif good.walk_price < good.lower_bound:
        mu = 1.02
        sigma = 0.01
    else:
        mu = 1.00
        sigma = 0.1

    if good.walk_price < 1:
        mu = mu + 0.03

    good.walk_price = good.walk_price * rng.normalvariate(mu, sigma)


def record_tick(good: GoodState) -> None:
    """A point on the price chart (once a price tick)."""
    good.price_history_ticks.append(price(good))


def record_day(good: GoodState) -> None:
    """A point in the bookkeeping price history (once a day)."""
    good.price_history_daily.append(price(good))


def simulate_history(good: GoodState, ticks: int, days: int, rng: random.Random) -> None:
    """Make up a price history of the given lengths from the starting price.

    For a good added after a save was made: its history must be as long as
    the saved goods', so the charts line its "now" up with theirs.
    """
    good.walk_price = good.base_price
    good.price_history_ticks = [price(good)]
    for _ in range(max(ticks, 1) - 1):
        step_walk(good, rng)
        record_tick(good)
    # One daily entry per day's ticks, the last of them today
    last = len(good.price_history_ticks) - 1
    good.price_history_daily = [
        good.price_history_ticks[max(0, last - PRICE_TICKS_PER_DAY * k)] for k in reversed(range(max(days, 1)))
    ]


def apply_well_shock(good: GoodState, up: bool) -> None:
    """A well wish's price shock: the walk and both bounds move by WELL_WISH_SHOCK_FACTOR.

    The corridor moves with the walk so the price settles at the new level
    instead of reverting at once. The original bounds come back after
    WELL_WISH_DURATION_DAYS days (``tick_well_shock_day``); a second shock while
    one runs keeps the first one's bounds to restore.

    Args:
        good: The good.
        up: True to raise the price, False to lower it.
    """
    factor = 1.0 + WELL_WISH_SHOCK_FACTOR if up else 1.0 - WELL_WISH_SHOCK_FACTOR

    # Save original bounds only when no shock is already active
    if good.well_shock_remaining_days == 0:
        good.well_shock_saved_upper = good.upper_bound
        good.well_shock_saved_lower = good.lower_bound

    good.walk_price *= factor
    good.upper_bound *= factor
    good.lower_bound *= factor
    good.well_shock_remaining_days = WELL_WISH_DURATION_DAYS


def tick_well_shock_day(good: GoodState) -> bool:
    """Count a day off a running well shock; restore the bounds when it runs out.

    Returns:
        True on the day the shock ended.
    """
    if good.well_shock_remaining_days <= 0:
        return False
    good.well_shock_remaining_days -= 1
    if good.well_shock_remaining_days == 0:
        good.upper_bound = good.well_shock_saved_upper
        good.lower_bound = good.well_shock_saved_lower
        return True
    return False
