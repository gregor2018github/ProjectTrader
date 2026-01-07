import random
from typing import List, Tuple

class Good:
    """Represents a tradeable commodity in the game world.
    
    A Good tracks its current market price, historical data, availability, 
    and visual properties for rendering in charts.
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
        self.price: float = float(price)
        self.market_quantity: int = int(market_quantity)
        self.price_history_daily: List[float] = [self.price]    # store price history for bookkeeping, updated daily
        self.price_history_hourly: List[float] = [self.price]   # store detailed price history for charts, updated hourly
        self.color_orig: Tuple[int, int, int] = color           # Original color when game started
        self.color_current: Tuple[int, int, int] = color        # Currently saved color
        self.color_temp: Tuple[int, int, int] = color           # Temporary color changes from settings
        self.color: Tuple[int, int, int] = self.color_temp      # Used for drawing; always synced to color_temp
        self.index: int = index
        self.base_price: float = self.price
        self.show_in_charts: bool = show_in_charts
        self.upper_bound: float = self.price * random.uniform(1.5, 3.5)
        self.lower_bound: float = self.price * random.uniform(0.05, 0.80)
        self.hovered: bool = False
    
    def buy(self, quantity: int) -> None:
        """Decrease market quantity when units are bought.
        
        Args:
            quantity: Units being removed from the market.
        """
        self.market_quantity -= quantity

    def sell(self, quantity: int) -> None:
        """Increase market quantity when units are sold.
        
        Args:
            quantity: Units being returned to the market.
        """
        self.market_quantity += quantity

    def update_price(self) -> None:
        """Simulate market price fluctuations using a normal distribution.
        
        The price tends to revert if it exceeds the upper bound or drops 
        below the lower bound.
        """
        if self.price > self.upper_bound:
            mu = 0.999
            sigma = 0.01
        elif self.price < self.lower_bound:
            mu = 1.02
            sigma = 0.01
        else:
            mu = 1.00
            sigma = 0.1
            
        if self.price < 1:
            mu = mu + 0.03

        self.price = self.price * random.normalvariate(mu, sigma)

    def update_price_history(self) -> None:
        """Update the price history for bookkeeping (daily)."""
        self.price_history_daily.append(self.price)
    
    def update_price_history_chart(self) -> None:
        """Update the price history for charts (hourly)."""
        self.price_history_hourly.append(self.price)
    
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
    
    def toggle_display(self) -> None:
        """Toggle visibility of this good in charts."""
        self.show_in_charts = not self.show_in_charts
