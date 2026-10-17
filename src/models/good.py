import math
import random
from typing import List, Optional, Tuple
from ..config.constants import (
    WELL_WISH_SHOCK_FACTOR, WELL_WISH_DURATION_DAYS,
    MARKET_VOLUME_SCARCE_RATIO, MARKET_VOLUME_GLUT_RATIO, MARKET_VOLUME_ELASTICITY,
    MARKET_VOLUME_FACTOR_MIN, MARKET_VOLUME_FACTOR_MAX, MARKET_VOLUME_DAILY_RECOVERY,
)

# Share of the gap to the normal volume closed per hour, so that 24 hours close MARKET_VOLUME_DAILY_RECOVERY
_HOURLY_RECOVERY = 1.0 - (1.0 - MARKET_VOLUME_DAILY_RECOVERY) ** (1.0 / 24.0)

class Good:
    """Represents a tradeable commodity in the game world.
    
    A Good tracks its current market price, historical data, availability, 
    and visual properties for rendering in charts.

    Its price is two parts multiplied: ``walk_price``, a random walk kept inside
    a soft corridor, and ``volume_factor()``, from how much of the good the
    market holds against its ``normal_quantity``.
    """
    
    def __init__(self, name: str, price: float, market_quantity: int, color: Tuple[int, int, int], index: int, show_in_charts: bool) -> None:
        """Initialize a new good.
        
        Args:
            name: The display name of the good.
            price: Starting market price.
            market_quantity: Initial available units in the market.
            color: RGB color tuple for chart rendering.
            index: Unique positional index.
            show_in_charts: Whether the good is initially visible in price charts.
        """
        self.name: str = name
        self.market_quantity: int = int(market_quantity)
        self.normal_quantity: int = max(1, int(market_quantity))  # The volume the market thinks is normal
        self.walk_price: float = float(price)                     # The random walk part of the price
        self.price_history_daily: List[float] = [self.price]    # store price history for bookkeeping, updated daily
        self.price_history_hourly: List[float] = [self.price]   # store detailed price history for charts, updated hourly
        self.color_orig: Tuple[int, int, int] = color           # Original color when game started
        self.color_current: Tuple[int, int, int] = color        # Currently saved color
        self.color_temp: Tuple[int, int, int] = color           # Temporary color changes from settings
        self.color: Tuple[int, int, int] = self.color_temp      # Used for drawing; always synced to color_temp
        self.index: int = index
        self.base_price: float = self.walk_price
        self.show_in_charts: bool = show_in_charts
        # The corridor bounds the walk, not the volume factor on top of it
        self.upper_bound: float = self.walk_price * random.uniform(1.5, 3.5)
        self.lower_bound: float = self.walk_price * random.uniform(0.05, 0.80)
        self.hovered: bool = False
        self.well_shock_remaining_days: int = 0
        self._well_shock_saved_upper: float = 0.0
        self._well_shock_saved_lower: float = 0.0
    
    @property
    def price(self) -> float:
        """The current market price: the random walk times the volume factor."""
        return self.walk_price * self.volume_factor()

    @price.setter
    def price(self, value: float) -> None:
        """Set the price as it should show now, at the current volume."""
        self.walk_price = float(value) / self.volume_factor()

    def volume_factor(self, quantity: Optional[float] = None) -> float:
        """How much dearer or cheaper the market's volume makes the good.

        1.0 between the scarce and glut ratios of the normal volume; past them
        the factor follows (threshold / ratio) ** elasticity, clamped, so the
        further the volume strays the more the price moves.

        Args:
            quantity: The volume to price at; the market's current one if omitted.
        """
        if quantity is None:
            quantity = self.market_quantity
        ratio = quantity / self.normal_quantity
        if ratio <= 0:
            return MARKET_VOLUME_FACTOR_MAX
        if ratio < MARKET_VOLUME_SCARCE_RATIO:
            factor = (MARKET_VOLUME_SCARCE_RATIO / ratio) ** MARKET_VOLUME_ELASTICITY
        elif ratio > MARKET_VOLUME_GLUT_RATIO:
            factor = (MARKET_VOLUME_GLUT_RATIO / ratio) ** MARKET_VOLUME_ELASTICITY
        else:
            return 1.0
        return min(MARKET_VOLUME_FACTOR_MAX, max(MARKET_VOLUME_FACTOR_MIN, factor))

    def quote(self, quantity: int, buying: bool) -> float:
        """What a trade of this many units comes to, before the trading fee.

        Each unit is priced at its own volume, so a big order moves the price
        against the trader as it goes: a bought unit at the volume before it
        is taken (the first one at the shown price), a sold unit at the volume
        after it is added. Buying and selling back the same units cancel out.

        Args:
            quantity: Units in the order.
            buying: True for a purchase from the market, False for a sale to it.
        """
        q = self.market_quantity
        if buying:
            volumes = range(q, q - quantity, -1)
        else:
            volumes = range(q + 1, q + quantity + 1)
        return self.walk_price * sum(self.volume_factor(v) for v in volumes)

    def buy(self, quantity: int) -> None:
        """Decrease market quantity when units are bought.

        Args:
            quantity: Units being removed from the market.
        """
        self.market_quantity -= quantity
        self._show_current_price()

    def sell(self, quantity: int) -> None:
        """Increase market quantity when units are sold.

        Args:
            quantity: Units being returned to the market.
        """
        self.market_quantity += quantity
        self._show_current_price()

    def _show_current_price(self) -> None:
        """Let the chart's latest point show the price a trade has just moved."""
        if self.price_history_hourly:
            self.price_history_hourly[-1] = self.price

    def recover_volume(self) -> None:
        """Move the market's volume an hour's share back towards normal.

        A stand-in for traders restocking and townsfolk buying, until the town
        has a supply and demand of its own. Moves at least one unit while there
        is a gap, so it always arrives.
        """
        gap = self.normal_quantity - self.market_quantity
        if gap == 0:
            return
        step = max(1, math.floor(abs(gap) * _HOURLY_RECOVERY))
        self.market_quantity += step if gap > 0 else -step

    def update_price(self) -> None:
        """Simulate market price fluctuations using a normal distribution.
        
        Moves the random walk part of the price, which tends to revert if it
        exceeds the upper bound or drops below the lower bound.
        """
        if self.walk_price > self.upper_bound:
            mu = 0.999
            sigma = 0.01
        elif self.walk_price < self.lower_bound:
            mu = 1.02
            sigma = 0.01
        else:
            mu = 1.00
            sigma = 0.1
            
        if self.walk_price < 1:
            mu = mu + 0.03

        self.walk_price = self.walk_price * random.normalvariate(mu, sigma)

    def update_price_history(self) -> None:
        """Update the price history for bookkeeping (daily)."""
        self.price_history_daily.append(self.price)
    
    def update_price_history_chart(self) -> None:
        """Update the price history for charts (hourly)."""
        self.price_history_hourly.append(self.price)
    
    def simulate_history(self, hours: int, days: int) -> None:
        """Make up a price history of the given lengths from the starting price.

        For a good added after a save was made: its history must be as long as
        the saved goods', so the charts line its "now" up with theirs.
        """
        self.walk_price = self.base_price
        self.price_history_hourly = [self.price]
        for _ in range(max(hours, 1) - 1):
            self.update_price()
            self.update_price_history_chart()
        # One daily entry per 24 hours, the last of them today
        last = len(self.price_history_hourly) - 1
        self.price_history_daily = [
            self.price_history_hourly[max(0, last - 24 * k)] for k in reversed(range(max(days, 1)))
        ]

    def get_price(self) -> float:
        """Get the current market price.
        
        Returns:
            float: Current price.
        """
        return self.price
    
    def set_price(self, price: float) -> None:
        """Set a new market price.
        
        Args:
            price: The new price value.
        """
        self.price = float(price)
    
    def get_quantity(self) -> int:
        """Get the current market quantity.
        
        Returns:
            int: Available units.
        """
        return self.market_quantity
    
    def set_quantity(self, quantity: int) -> None:
        """Set the available market quantity.
        
        Args:
            quantity: New number of units.
        """
        self.market_quantity = int(quantity)
    
    def apply_well_shock(self, direction: str) -> None:
        """Apply a temporary price shock from a well wish.

        Shifts the current price and both bounds by WELL_WISH_SHOCK_FACTOR in the
        given direction so the price stabilises near the new level instead of
        immediately reverting.  The original bounds are restored after
        WELL_WISH_DURATION_DAYS daily ticks.

        Args:
            direction: "Price goes up" to raise the price, anything else lowers it.
        """
        factor = 1.0 + WELL_WISH_SHOCK_FACTOR if direction == "Price goes up" else 1.0 - WELL_WISH_SHOCK_FACTOR

        # Save original bounds only when no shock is already active
        if self.well_shock_remaining_days == 0:
            self._well_shock_saved_upper = self.upper_bound
            self._well_shock_saved_lower = self.lower_bound

        self.walk_price *= factor
        self.upper_bound *= factor
        self.lower_bound *= factor
        self.well_shock_remaining_days = WELL_WISH_DURATION_DAYS

    def tick_well_shock_day(self) -> None:
        """Decrement the well shock counter and restore bounds when it expires."""
        if self.well_shock_remaining_days <= 0:
            return
        self.well_shock_remaining_days -= 1
        if self.well_shock_remaining_days == 0:
            self.upper_bound = self._well_shock_saved_upper
            self.lower_bound = self._well_shock_saved_lower

    def toggle_display(self) -> None:
        """Toggle visibility of this good in charts."""
        self.show_in_charts = not self.show_in_charts
