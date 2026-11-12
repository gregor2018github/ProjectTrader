"""What an order at the market would come to, before it is placed.

The market view's trade desk (``src/ui/layout_modules/trade_desk.py``) shows
each charted good with a quantity and a Buy and a Sell button. This module
works out what stands on them: what the order costs or brings with the fee and
the slippage, where it leaves the price, how much could be traded at the most,
and the reason it cannot be placed, in the words the desk shows. It draws
nothing and keeps nothing; the trade itself is still ``Depot.buy`` / ``sell``,
which check the same things again.
"""
from dataclasses import dataclass
from typing import Any, Optional

MAX_QUANTITY = 999      # the most units one order can name


@dataclass(frozen=True)
class Offer:
    """One side of a card: buying or selling *quantity* units now."""
    quantity: int
    total: float                    # coins paid (buying) or received (selling), the fee included
    fee: float
    price_after: float              # the market price once the order is through
    limit: int                      # the most units this side could trade now
    blocked: Optional[str] = None   # why the order cannot be placed, if it cannot
    profit: Optional[float] = None  # selling: against what these units cost, the fee taken off

    @property
    def each(self) -> float:
        """Coins per unit, the fee included."""
        return self.total / self.quantity if self.quantity else 0.0


def market_block(good_name: str, depot: Any, game_state: Any) -> Optional[str]:
    """Why this good cannot be traded either way right now, or None."""
    player = getattr(getattr(game_state, "game", None), "player", None)
    if player is not None and not player.in_market_area:
        return "Trade at a market square"
    if not game_state.is_good_sold_here(good_name):
        return "Not sold at this market"
    if not game_state.is_good_tradable(good_name):
        return "Booth closed"
    if getattr(game_state, "time_level", 3) == 1:
        return "Game paused"
    if not depot.has_license(good_name, game_state.date):
        return "No licence"
    return None


def price_after(good: Any, quantity: int, buying: bool) -> float:
    """The market price once *quantity* units have been bought from or sold to the market."""
    stock = good.state.stock
    now = good.volume_factor(stock)
    then = good.volume_factor(stock - quantity if buying else stock + quantity)
    return good.get_price() * then / now if now else good.get_price()


def max_buy(good: Any, depot: Any) -> int:
    """The most units the player could buy now: what the market holds, the storage takes and the purse pays."""
    most = max(0, min(depot.room_for(good.name), good.get_quantity(), MAX_QUANTITY))
    rate = 1.0 + depot.effective_fee_rate

    def affordable(units: int) -> bool:
        return good.quote(units, buying=True) * rate <= depot.money

    if most == 0 or affordable(most):
        return most
    low, high = 0, most     # affordable(low), not affordable(high)
    while high - low > 1:
        middle = (low + high) // 2
        if affordable(middle):
            low = middle
        else:
            high = middle
    return low


def fifo_cost(depot: Any, good_name: str, quantity: int) -> float:
    """What the oldest *quantity* units held cost, as a sale would count them."""
    cost, left = 0.0, quantity
    for entry in depot.purchase_history.get(good_name, []):
        if left <= 0:
            break
        used = min(left, entry["quantity"])
        cost += used * entry["price"]
        left -= used
    return cost


def buy_offer(good: Any, quantity: int, depot: Any, game_state: Any) -> Offer:
    """Buying *quantity* units of the good now."""
    goods_cost = good.quote(quantity, buying=True) if quantity > 0 else 0.0
    fee = depot.trading_fee(goods_cost)
    limit = max_buy(good, depot)
    blocked = market_block(good.name, depot, game_state)
    if blocked is None:
        if quantity <= 0:
            blocked = "Enter a quantity"
        elif good.get_quantity() < quantity:
            blocked = f"The market has only {good.get_quantity()}"
        elif depot.money < goods_cost + fee:
            blocked = "Not enough money"
        elif depot.room_for(good.name) < quantity:
            blocked = f"Room for only {depot.room_for(good.name)}"
    return Offer(quantity, goods_cost + fee, fee, price_after(good, quantity, True), limit, blocked)


def sell_offer(good: Any, quantity: int, depot: Any, game_state: Any) -> Offer:
    """Selling *quantity* units of the good now."""
    held = depot.good_stock.get(good.name, 0)
    revenue = good.quote(quantity, buying=False) if quantity > 0 else 0.0
    fee = depot.trading_fee(revenue)
    blocked = market_block(good.name, depot, game_state)
    if blocked is None:
        if held == 0:
            blocked = "None in stock"
        elif quantity <= 0:
            blocked = "Enter a quantity"
        elif held < quantity:
            blocked = f"You hold only {held}"
    profit = revenue - fee - fifo_cost(depot, good.name, quantity) if 0 < quantity <= held else None
    return Offer(quantity, revenue - fee, fee, price_after(good, quantity, False),
                 min(held, MAX_QUANTITY), blocked, profit)
