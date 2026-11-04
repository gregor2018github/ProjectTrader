"""A tradeable good as the game's UI and depot see it: a thin view over the simulation.

Every number of the good (price walk, volumes, corridor, well shock,
histories) lives once, in the simulation's ``GoodState``
(``src/sim/state.py``); a ``Good`` looks it up there on every access and keeps
none of it. What the ``Good`` itself keeps is only how the UI shows it: its
colours, its place in the lists, whether it is in the chart, whether it is
hovered.

This wrapper is a seam kept for P0 so the depot and the views did not have to
change; see ``docs/sim_core.md`` before building on it.
"""
from typing import TYPE_CHECKING, List, Optional, Tuple

from ..sim.systems import market

if TYPE_CHECKING:
    from ..sim import Simulation
    from ..sim.state import GoodState


class Good:
    """A tradeable commodity: the simulation's market numbers, plus how the UI shows them.

    Its price is two parts multiplied: ``walk_price``, a random walk kept inside
    a soft corridor, and ``volume_factor()``, from how much of the good the
    market holds against its ``normal_quantity`` (``docs/pricing.md``).
    """

    def __init__(self, sim: "Simulation", name: str, color: Tuple[int, int, int], index: int,
                 show_in_charts: bool) -> None:
        """Show the simulation's good *name*.

        Args:
            sim: The simulation holding the good.
            name: The good's name, as the simulation knows it.
            color: RGB colour for the charts.
            index: Its place in the charts and lists.
            show_in_charts: Whether it is shown in the price chart.
        """
        self._sim = sim
        self.name: str = name
        self.color_orig: Tuple[int, int, int] = color           # Original color when game started
        self.color_current: Tuple[int, int, int] = color        # Currently saved color
        self.color_temp: Tuple[int, int, int] = color           # Temporary color changes from settings
        self.color: Tuple[int, int, int] = self.color_temp      # Used for drawing; always synced to color_temp
        self.index: int = index
        self.show_in_charts: bool = show_in_charts
        self.hovered: bool = False

    @property
    def state(self) -> "GoodState":
        """The simulation's state of this good (looked up anew, so a loaded save shows at once)."""
        return self._sim.state.goods[self.name]

    # -- the simulation's numbers, passed through --------------------------

    @property
    def walk_price(self) -> float:
        return self.state.walk_price

    @walk_price.setter
    def walk_price(self, value: float) -> None:
        self.state.walk_price = value

    @property
    def market_quantity(self) -> int:
        return self.state.market_quantity

    @market_quantity.setter
    def market_quantity(self, value: int) -> None:
        self.state.market_quantity = int(value)

    @property
    def normal_quantity(self) -> int:
        return self.state.normal_quantity

    @property
    def upper_bound(self) -> float:
        return self.state.upper_bound

    @property
    def lower_bound(self) -> float:
        return self.state.lower_bound

    @property
    def base_price(self) -> float:
        return self.state.base_price

    @property
    def well_shock_remaining_days(self) -> int:
        return self.state.well_shock_remaining_days

    @property
    def price_history_daily(self) -> List[float]:
        """One price a day, for bookkeeping."""
        return self.state.price_history_daily

    @property
    def price_history_hourly(self) -> List[float]:
        """The price chart: one price per price tick (named for the old save format)."""
        return self.state.price_history_ticks

    @property
    def price(self) -> float:
        """The current market price: the random walk times the volume factor."""
        return market.price(self.state)

    @price.setter
    def price(self, value: float) -> None:
        """Set the price as it should show now, at the current volume."""
        market.set_price(self.state, value)

    def volume_factor(self, quantity: Optional[float] = None) -> float:
        """How much dearer or cheaper the market's volume makes the good (``market.volume_factor``)."""
        return market.volume_factor(self.state, quantity)

    def quote(self, quantity: int, buying: bool) -> float:
        """What a trade of this many units comes to, before the trading fee, with slippage (``market.quote``)."""
        return market.quote(self.state, quantity, buying)

    def buy(self, quantity: int) -> None:
        """Units bought by the player leave the market."""
        market.take(self.state, quantity)

    def sell(self, quantity: int) -> None:
        """Units sold by the player join the market."""
        market.put(self.state, quantity)

    def apply_well_shock(self, direction: str) -> None:
        """A well wish's price shock (``market.apply_well_shock``).

        Args:
            direction: "Price goes up" to raise the price, anything else lowers it.
        """
        self._sim.apply_well_shock(self.name, direction == "Price goes up")

    def get_price(self) -> float:
        return self.price

    def set_price(self, price: float) -> None:
        self.price = float(price)

    def get_quantity(self) -> int:
        return self.market_quantity

    def set_quantity(self, quantity: int) -> None:
        self.market_quantity = int(quantity)

    # -- how the UI shows it -------------------------------------------------

    def toggle_display(self) -> None:
        """Toggle visibility of this good in charts."""
        self.show_in_charts = not self.show_in_charts
