import pygame
from ...config.colors import YELLOW, BLACK, DARK_BROWN, TAN, BEIGE, PALE_BROWN, LIGHT_BROWN, WHEAT, DARK_GREEN, DARK_RED
import datetime
from typing import Dict, List, Optional, Any
from ...sim.calendar import PERIOD_DAYS

class DepotViewDetail:
    """Handles the detailed statistics panel shown alongside the depot view.
    
    This panel displays granular information about wealth, stock, and trade actions
    filtered by the currently selected time frame.
    """
    
    def __init__(self, depot_rect: pygame.Rect, game_state: Any) -> None:
        """Initialize the detail panel.
        
        Args:
            depot_rect: The rectangle of the main depot view to align with.
            game_state: The current game state object.
        """
        # Place the detail panel just to the right of depot view
        self.rect = pygame.Rect(depot_rect.left + 435, depot_rect.top + 60, 325, depot_rect.height-80)
        self.visible = False
        self.current_statistic = None
        self.game_state = game_state
        self.scroll_offset = 0
        self.max_scroll = 0
        
        # Add cache for wealth statistics
        self.cached_stats: Dict[str, List[str]] = {
            "Current Wealth": [],
            "Wealth Start": [],
            "Income": [],
            "Expenses": [],
            "Profit": [],
            "Total Stock": [],
            "Buy Actions": [],
            "Sell Actions": [],
            "Total Actions": []
        }
        self.last_update_date: Optional[datetime.date] = None
        self.last_time_frame: Optional[str] = None      # Track the last time frame to detect changes
        self.last_hour: Optional[int] = None            # Track the last hour to detect price changes
        self.last_money: Optional[float] = None         # Track the last money to detect trade changes
        # Add separate flags to track when each statistic was last updated
        self.last_today_update_date: Optional[datetime.date] = None
        self.last_start_update_date: Optional[datetime.date] = None
        self.last_total_stock_update_date: Optional[datetime.date] = None
        self.last_trade_actions_update_date: Optional[datetime.date] = None
        self.last_trade_actions_count: int = 0
        self.last_expenses_update_date: Optional[datetime.date] = None
        self.last_expenses_money: Optional[float] = None
        self.last_income_update_date: Optional[datetime.date] = None
        self.last_income_money: Optional[float] = None
        self.last_profit_update_date: Optional[datetime.date] = None

    def toggle(self) -> None:
        """Toggle the visibility of the detail panel."""
        self.visible = not self.visible

    def show_for_statistic(self, statistic_label: str) -> None:
        """Show the panel for a specific statistic.
        
        Args:
            statistic_label: The label of the statistic to show details for.
        """
        if self.current_statistic != statistic_label:
            self.scroll_offset = 0
        self.current_statistic = statistic_label
        self.visible = True

    def update_statistics(self, force: bool = False) -> None:
        """Update cached statistics if state has changed or force is True.
        
        Checks if day, hour, money, or time frame has changed since the last update.
        """
        current_date = self.game_state.date.date()
        current_hour = self.game_state.date.hour
        current_time_frame = self.game_state.depot_time_frame
        depot = self.game_state.game.depot
        goods = self.game_state.game.goods
        current_money = depot.money
        
        # Update "Current Wealth" if day changed, hour changed, money changed, or forced
        if (force or self.last_today_update_date != current_date or 
            self.last_hour != current_hour or self.last_money != current_money):
            self._update_current_wealth(depot, goods)
            self.last_today_update_date = current_date
        
        # Update "Wealth Start" if time frame changed, day changed, or forced
        if force or self.last_start_update_date != current_date or self.last_time_frame != current_time_frame:
            self._update_wealth_start(depot, goods, current_time_frame)
            self.last_start_update_date = current_date
            self.last_time_frame = current_time_frame
        
        # Update "Total Stock" if day changed, hour changed, money changed, or forced
        if (force or self.last_total_stock_update_date != current_date or 
            self.last_hour != current_hour or self.last_money != current_money):
            self._update_total_stock(depot, goods)
            self.last_total_stock_update_date = current_date
        
        # Update Trade Actions if time frame changed, day changed, trade count changed, or forced
        current_trade_count = len(depot.trades)
        if (force or self.last_trade_actions_update_date != current_date or 
            self.last_time_frame != current_time_frame or 
            self.last_trade_actions_count != current_trade_count):
            self._update_trade_actions(depot, goods, current_time_frame)
            self.last_trade_actions_update_date = current_date
            self.last_trade_actions_count = current_trade_count

        # Update "Profit" if day, hour, money, or time frame changed, or forced
        if (force or self.last_profit_update_date != current_date or
            self.last_hour != current_hour or self.last_money != current_money or
            self.last_time_frame != current_time_frame):
            self._update_profit(depot, goods, current_time_frame)
            self.last_profit_update_date = current_date

        # Update "Income" if day changed, money changed, time frame changed, or forced
        if (force or self.last_income_update_date != current_date or
            self.last_income_money != current_money or
            self.last_time_frame != current_time_frame):
            self._update_income(depot, current_time_frame)
            self.last_income_update_date = current_date
            self.last_income_money = current_money

        # Update "Expenses" if day changed, money changed, time frame changed, or forced
        if (force or self.last_expenses_update_date != current_date or
            self.last_expenses_money != current_money or
            self.last_time_frame != current_time_frame):
            self._update_expenses(depot, current_time_frame)
            self.last_expenses_update_date = current_date
            self.last_expenses_money = current_money

        # Update tracking variables
        self.last_update_date = current_date
        self.last_hour = current_hour
        self.last_money = current_money
    
    def _update_current_wealth(self, depot: Any, goods: List[Any]) -> None:
        """Update just the "Current Wealth" statistics.
        
        Calculates total wealth breakdown including money and current value of all goods.
        """
        # Calculate total goods value for Current Wealth using current prices and stock
        total_goods_value = 0
        for good in goods:
            qty = depot.good_stock.get(good.name, 0)
            price = good.price
            total_goods_value += qty * price
            
        # Cache "Current Wealth" statistics
        self.cached_stats["Current Wealth"] = []

        outstanding_loans = sum(loan.get("remaining_principal", loan.get("amount", 0.0)) for loan in depot.active_loans)
        property_value = depot.get_property_value()
        total_wealth = depot.money + total_goods_value + property_value - outstanding_loans

        # Add summary totals at the top
        self.cached_stats["Current Wealth"].append(f"Total: {total_wealth:,.2f}")
        self.cached_stats["Current Wealth"].append("__SEPARATOR__")
        self.cached_stats["Current Wealth"].append(f"Money: {depot.money:,.2f}")
        self.cached_stats["Current Wealth"].append(f"Goods: {total_goods_value:,.2f}")
        self.cached_stats["Current Wealth"].append(f"Property: {property_value:,.2f}")
        self.cached_stats["Current Wealth"].append(f"Loans: -{outstanding_loans:,.2f}" if outstanding_loans > 0 else "Loans: 0.00")
        self.cached_stats["Current Wealth"].append("__SEPARATOR__")
        # empty line
        self.cached_stats["Current Wealth"].append("")
        
        # Add breakdown for each good that has quantity > 0, sorted by total value
        goods_with_value = []
        for good in goods:
            qty = depot.good_stock.get(good.name, 0)
            if qty > 0:
                price = good.price
                value = qty * price
                goods_with_value.append((good, qty, price, value))
        
        # Sort by value descending
        goods_with_value.sort(key=lambda x: x[3], reverse=True)
        
        for good, qty, price, value in goods_with_value:
            # Add good name as a heading without value
            self.cached_stats["Current Wealth"].append(f"{good.name}")
            # Add indented details
            self.cached_stats["Current Wealth"].append(f"      Units: {qty:,}")
            self.cached_stats["Current Wealth"].append(f"      Unit Value: {price:,.2f}")
            self.cached_stats["Current Wealth"].append(f"      Total Value: {value:,.2f}")
            self.cached_stats["Current Wealth"].append("__SEPARATOR__")
    
    def _calc_unrealized_pl(self, depot: Any, good_name: str, current_price: float) -> tuple:
        """Return (total_unrealized_pl, avg_cost) for a good using FIFO purchase history."""
        entries = depot.purchase_history.get(good_name, [])
        total_cost = sum(e["price"] * e["quantity"] for e in entries)
        total_qty = sum(e["quantity"] for e in entries)
        if total_qty == 0:
            return 0.0, 0.0
        avg_cost = total_cost / total_qty
        unrealized = (current_price - avg_cost) * total_qty
        return unrealized, avg_cost

    def _update_total_stock(self, depot: Any, goods: List[Any]) -> None:
        """Update just the "Total Stock" statistics.

        Lists all goods currently in stock, sorted by total units descending.
        """
        self.cached_stats["Total Stock"] = []

        # Get current total units
        total_units = sum(depot.good_stock.values())
        self.cached_stats["Total Stock"].append(f"Total Units: {total_units:,}")

        # Build per-good data including unrealized P/L
        goods_with_stock = []
        for good in goods:
            qty = depot.good_stock.get(good.name, 0)
            if qty > 0:
                price = good.price
                value = qty * price
                unrealized, avg_cost = self._calc_unrealized_pl(depot, good.name, price)
                goods_with_stock.append((good, qty, price, value, unrealized, avg_cost))

        # Total unrealized P/L across all held goods
        total_unrealized = sum(x[4] for x in goods_with_stock)
        sign = "+" if total_unrealized >= 0 else ""
        color_tag = "__GREEN__" if total_unrealized >= 0 else "__RED__"
        self.cached_stats["Total Stock"].append(f"{color_tag}Unrealized P/L: {sign}{total_unrealized:,.2f}")
        self.cached_stats["Total Stock"].append("__SEPARATOR__")
        self.cached_stats["Total Stock"].append("")

        # Sort by units descending
        goods_with_stock.sort(key=lambda x: x[1], reverse=True)

        for good, qty, price, value, unrealized, avg_cost in goods_with_stock:
            self.cached_stats["Total Stock"].append(f"{good.name}")
            self.cached_stats["Total Stock"].append(f"      Units: {qty:,}")
            self.cached_stats["Total Stock"].append(f"      Unit Value: {price:,.2f}")
            self.cached_stats["Total Stock"].append(f"      Total Value: {value:,.2f}")
            pl_sign = "+" if unrealized >= 0 else ""
            pl_tag = "__GREEN__" if unrealized >= 0 else "__RED__"
            self.cached_stats["Total Stock"].append(f"      {pl_tag}Unrealized P/L: {pl_sign}{unrealized:,.2f}")
            self.cached_stats["Total Stock"].append("__SEPARATOR__")
    
    def _update_wealth_start(self, depot: Any, goods: List[Any], time_frame: str) -> None:
        """Update just the "Wealth Start" statistics based on selected time frame.
        
        Reconstructs what the player's wealth and stocks were at the beginning of the period.
        """
        # Cache "Wealth Start" statistics based on selected time frame
        self.cached_stats["Wealth Start"] = []
        
        # Determine period days based on the selected time frame
        period_days = PERIOD_DAYS.get(time_frame)  # None: since the start
            
        # Get historical wealth and money values directly from records. The
        # daily snapshot is taken at the turn of the day, so entry -period_days
        # is the close of the period's first day - the same entry the overview
        # panel reads for its "Wealth Start" row.
        if period_days is not None and len(depot.wealth) >= period_days:
            start_wealth = depot.wealth[-period_days]
            start_money = depot.money_history[-period_days]  # Use recorded money directly
        else:
            start_wealth = depot.wealth[0]
            start_money = depot.money_history[0]  # Use recorded money directly
        
        # Calculate start date for goods reconstruction
        start_date = self.game_state.date - datetime.timedelta(days=period_days if period_days else 0)
        
        # Reconstruct goods quantities at the start 
        start_goods = {good.name: depot.good_stock.get(good.name, 0) for good in goods}
        
        # Reverse through trades and undo them if they happened within the period
        period_trades = []
        if period_days is not None:
            period_trades = [t for t in depot.trades if t["timestamp"] >= start_date]
            
        # Reconstruct trades in reverse
        for trade in reversed(period_trades):
            good_name = trade["good"]
            qty = trade["quantity"]
            
            if trade["type"] == "purchase":
                # If it was a purchase, we need to decrease the quantity
                start_goods[good_name] = max(0, start_goods[good_name] - qty)
            else:  # "sale"
                # If it was a sale, we need to increase the quantity
                start_goods[good_name] = start_goods[good_name] + qty
        
        # Get historic prices for each good at the start of the period
        start_prices = {}
        for good in goods:
            if period_days is not None and len(good.price_history_daily) >= period_days:
                start_prices[good.name] = good.price_history_daily[-period_days]
            else:
                start_prices[good.name] = good.price_history_daily[0]
        
        # Calculate total goods value at start of period
        start_goods_value = 0
        for good in goods:
            good_name = good.name
            qty = start_goods.get(good_name, 0)
            price = start_prices[good_name]
            start_goods_value += qty * price
        
        # Look up outstanding loan balance at start of period from history
        if period_days is not None and len(depot.loan_history) >= period_days:
            start_loans = depot.loan_history[-period_days]
        else:
            start_loans = depot.loan_history[0] if depot.loan_history else 0.0

        # Look up property value at the start of the period from history
        if period_days is not None and len(depot.property_value_history) >= period_days:
            start_property = depot.property_value_history[-period_days]
        else:
            start_property = depot.property_value_history[0] if depot.property_value_history else 0.0

        # Add calculated stats to cache
        self.cached_stats["Wealth Start"].append(f"Total: {start_wealth:,.2f}")
        self.cached_stats["Wealth Start"].append("__SEPARATOR__")
        self.cached_stats["Wealth Start"].append(f"Money: {start_money:,.2f}")
        self.cached_stats["Wealth Start"].append(f"Goods: {start_goods_value:,.2f}")
        self.cached_stats["Wealth Start"].append(f"Property: {start_property:,.2f}")
        self.cached_stats["Wealth Start"].append(f"Loans: -{start_loans:,.2f}" if start_loans > 0 else "Loans: 0.00")
        self.cached_stats["Wealth Start"].append("__SEPARATOR__")
        self.cached_stats["Wealth Start"].append("")
        
        # Show goods at start of period, sorted by total value
        goods_with_value = []
        for good in goods:
            good_name = good.name
            qty = start_goods.get(good_name, 0)
            # Use the identified start price instead of base_price
            price = start_prices[good_name]
            total_value = qty * price
            
            if qty > 0 or time_frame == "Total":  # Show all goods for Total view
                goods_with_value.append((good_name, qty, price, total_value))
        
        # Sort by total value descending
        goods_with_value.sort(key=lambda x: x[3], reverse=True)
        
        for good_name, qty, price, total_value in goods_with_value:
            self.cached_stats["Wealth Start"].append(f"{good_name}")
            self.cached_stats["Wealth Start"].append(f"      Units: {qty:,}")
            self.cached_stats["Wealth Start"].append(f"      Unit Value: {price:,.2f}")
            self.cached_stats["Wealth Start"].append(f"      Total Value: {total_value:,.2f}")
            self.cached_stats["Wealth Start"].append("__SEPARATOR__")
    def _update_trade_actions(self, depot: Any, goods: List[Any], time_frame: str) -> None:
        """Update Buy, Sell, and Total Actions statistics based on selected time frame.
        
        Aggregates trade volumes and units by good for the chosen period.
        """
        # Determine period days
        period_days = PERIOD_DAYS.get(time_frame)  # None: since the start

        # Filter trades by time frame
        if period_days is not None:
            delta = datetime.timedelta(days=period_days)
            start_date = self.game_state.date - delta
            filtered_trades = [t for t in depot.trades if t["timestamp"] >= start_date]
        else:
            filtered_trades = depot.trades

        # Process Buy, Sell, and Total
        for action_type in ["Buy Actions", "Sell Actions", "Total Actions"]:
            self.cached_stats[action_type] = []
            
            if action_type == "Buy Actions":
                type_filter = "purchase"
            elif action_type == "Sell Actions":
                type_filter = "sale"
            else:
                type_filter = None

            trades = [t for t in filtered_trades if type_filter is None or t["type"] == type_filter]

            # Aggregate by good
            good_stats = {}
            total_volume = 0
            total_units = 0
            volume_bought = 0
            volume_sold = 0
            units_bought = 0
            units_sold = 0

            for t in trades:
                name = t["good"]
                if name not in good_stats:
                    good_stats[name] = {"units": 0, "total_value": 0, "bought": 0, "sold": 0}
                good_stats[name]["units"] += t["quantity"]
                good_stats[name]["total_value"] += t["total"]
                total_volume += t["total"]
                total_units += t["quantity"]

                if t["type"] == "purchase":
                    good_stats[name]["bought"] += t["total"]
                    if action_type == "Total Actions":
                        volume_bought += t["total"]
                        units_bought += t["quantity"]
                else:
                    good_stats[name]["sold"] += t["total"]
                    if action_type == "Total Actions":
                        volume_sold += t["total"]
                        units_sold += t["quantity"]

            # Add summary
            self.cached_stats[action_type].append(f"Total Volume: {total_volume:,.2f}")
            self.cached_stats[action_type].append(f"Total Units: {total_units:,}")

            if action_type == "Total Actions":
                self.cached_stats[action_type].append(f"Volume Bought: {volume_bought:,.2f}")
                self.cached_stats[action_type].append(f"Volume Sold: {volume_sold:,.2f}")
                self.cached_stats[action_type].append(f"Units Bought: {units_bought:,}")
                self.cached_stats[action_type].append(f"Units Sold: {units_sold:,}")
                total_realized = volume_sold - volume_bought
                sign = "+" if total_realized >= 0 else ""
                color_tag = "__GREEN__" if total_realized >= 0 else "__RED__"
                self.cached_stats[action_type].append(f"{color_tag}Realized P/L: {sign}{total_realized:,.2f}")

            self.cached_stats[action_type].append("__SEPARATOR__")
            self.cached_stats[action_type].append("")

            # Sort goods by total value descending
            sorted_goods = sorted(good_stats.items(), key=lambda x: x[1]["total_value"], reverse=True)

            for name, stats in sorted_goods:
                avg_price = stats["total_value"] / stats["units"] if stats["units"] > 0 else 0
                self.cached_stats[action_type].append(f"{name}")
                self.cached_stats[action_type].append(f"      Units: {stats['units']:,}")
                self.cached_stats[action_type].append(f"      Avg Price: {avg_price:,.2f}")
                self.cached_stats[action_type].append(f"      Total Value: {stats['total_value']:,.2f}")
                if action_type == "Total Actions":
                    realized = stats["sold"] - stats["bought"]
                    pl_sign = "+" if realized >= 0 else ""
                    pl_tag = "__GREEN__" if realized >= 0 else "__RED__"
                    self.cached_stats[action_type].append(f"      {pl_tag}Realized P/L: {pl_sign}{realized:,.2f}")
                self.cached_stats[action_type].append("__SEPARATOR__")    

    def _update_profit(self, depot: Any, goods: List[Any], time_frame: str) -> None:
        """Update the 'Profit' detail statistics based on selected time frame.

        Profit = Cash Flow + Stock Value Change + Property Value Change
        + Loan Balance Change.
        Stock Value Change is derived from the identity rather than reconstructed
        from historical prices, so it stays consistent with the overview figure.
        """
        period_days = PERIOD_DAYS.get(time_frame)  # None: since the start

        # Current wealth
        goods_value_now = sum(depot.good_stock.get(g.name, 0) * g.price for g in goods)
        loans_now = sum(loan.get("remaining_principal", loan.get("amount", 0.0)) for loan in depot.active_loans)
        property_now = depot.get_property_value()
        current_wealth = depot.money + goods_value_now + property_now - loans_now

        # Start wealth
        if period_days is not None and len(depot.wealth) >= period_days:
            start_wealth = depot.wealth[-period_days]
        else:
            start_wealth = depot.wealth[0]
        total_profit = current_wealth - start_wealth

        # Income and expenses for the period
        if period_days is not None:
            num_history_days = period_days - 1
            if num_history_days > 0:
                current_income = sum(depot.income_history[-num_history_days:]) + depot.income
                current_expense = sum(depot.expenditure_history[-num_history_days:]) + depot.expenditures
            else:
                current_income = depot.income
                current_expense = depot.expenditures
        else:
            current_income = sum(depot.income_history) + depot.income
            current_expense = sum(depot.expenditure_history) + depot.expenditures
        cash_flow = current_income - current_expense

        # Money at the start of the period (mirrors the wealth indexing above)
        if period_days is not None and len(depot.money_history) >= period_days:
            start_money = depot.money_history[-period_days]
        else:
            start_money = depot.money_history[0]
        current_money = depot.money

        # Loan balance change (negative = took on more debt, positive = reduced debt).
        # Indexed like the wealth history above — all four series are appended in
        # the same daily snapshot, so the period has to start on the same entry.
        if period_days is not None and len(depot.loan_history) >= period_days:
            loans_start = depot.loan_history[-period_days]
        else:
            loans_start = depot.loan_history[0] if depot.loan_history else 0.0
        loan_balance_change = -(loans_now - loans_start)

        # Property value change over the period
        if period_days is not None and len(depot.property_value_history) >= period_days:
            property_start = depot.property_value_history[-period_days]
        else:
            property_start = depot.property_value_history[0] if depot.property_value_history else 0.0
        property_value_change = property_now - property_start

        # Stock value change derived from the identity:
        # total_profit = cash_flow + stock_value_change + property_value_change
        #                + loan_balance_change
        stock_value_change = total_profit - cash_flow - property_value_change - loan_balance_change

        def _fmt(val: float) -> str:
            sign = "+" if val >= 0 else ""
            return f"{sign}{val:,.2f}"

        def _tag(val: float) -> str:
            return "__GREEN__" if val >= 0 else "__RED__"

        self.cached_stats["Profit"] = []

        profit_tag = _tag(total_profit)
        self.cached_stats["Profit"].append(f"{profit_tag}Total: {_fmt(total_profit)}")
        self.cached_stats["Profit"].append("__SEPARATOR__")
        self.cached_stats["Profit"].append("")

        # Cash Flow block
        cf_tag = _tag(cash_flow)
        self.cached_stats["Profit"].append(f"Cash Flow")
        self.cached_stats["Profit"].append(f"      {cf_tag}Total: {_fmt(cash_flow)}")
        self.cached_stats["Profit"].append(f"      Money Start: {start_money:,.2f}")
        self.cached_stats["Profit"].append(f"      Income: {current_income:,.2f}")
        self.cached_stats["Profit"].append(f"      Expenses: -{current_expense:,.2f}")
        self.cached_stats["Profit"].append(f"      Money Now: {current_money:,.2f}")
        self.cached_stats["Profit"].append("__SEPARATOR__")

        # Stock Value Change block
        sv_tag = _tag(stock_value_change)
        self.cached_stats["Profit"].append(f"Stock Value Change")
        self.cached_stats["Profit"].append(f"      {sv_tag}Total: {_fmt(stock_value_change)}")
        self.cached_stats["Profit"].append("__SEPARATOR__")

        # Property Value Change block
        pv_tag = _tag(property_value_change)
        self.cached_stats["Profit"].append(f"Property Value Change")
        self.cached_stats["Profit"].append(f"      {pv_tag}Total: {_fmt(property_value_change)}")
        self.cached_stats["Profit"].append("__SEPARATOR__")

        # Loan Balance Change block
        lb_tag = _tag(loan_balance_change)
        self.cached_stats["Profit"].append(f"Loan Balance Change")
        self.cached_stats["Profit"].append(f"      {lb_tag}Total: {_fmt(loan_balance_change)}")
        self.cached_stats["Profit"].append("__SEPARATOR__")

    def _update_income(self, depot: Any, time_frame: str) -> None:
        """Update the 'Income' detail statistics based on selected time frame.

        Breaks down income by source category. Currently only Sold Goods exists;
        future categories (property rent, contracts, etc.) slot in alongside it.
        """
        period_days = PERIOD_DAYS.get(time_frame)  # None: since the start

        breakdown = depot.get_income_breakdown(period_days)

        self.cached_stats["Income"] = []

        self.cached_stats["Income"].append(f"Total: {breakdown['total']:,.2f}")
        self.cached_stats["Income"].append("__SEPARATOR__")
        self.cached_stats["Income"].append("")

        sold = breakdown["sold_goods"]
        self.cached_stats["Income"].append("Sold Goods")
        self.cached_stats["Income"].append(f"      Total: {sold['total']:,.2f}")
        for sub_name, sub_val in sold.items():
            if sub_name == "total":
                continue
            self.cached_stats["Income"].append(f"      {sub_name}: {sub_val:,.2f}")
        self.cached_stats["Income"].append("__SEPARATOR__")

        # Labor Income (minigames, e.g. woodhacking)
        labor = breakdown.get("labor_income", {"total": 0.0})
        self.cached_stats["Income"].append("Labor Income")
        self.cached_stats["Income"].append(f"      Total: {labor['total']:,.2f}")
        for sub_name, sub_val in labor.items():
            if sub_name == "total":
                continue
            self.cached_stats["Income"].append(f"      {sub_name}: {sub_val:,.2f}")
        self.cached_stats["Income"].append("__SEPARATOR__")

    def _update_expenses(self, depot: Any, time_frame: str) -> None:
        """Update the 'Expenses' detail statistics based on selected time frame.

        Breaks down expenses into Cost of Living, Trading Expenses, Licenses, and Donations.
        """
        # Determine period days
        period_days = PERIOD_DAYS.get(time_frame)  # None: since the start
        
        breakdown = depot.get_expense_breakdown(period_days)
        
        self.cached_stats["Expenses"] = []
        
        # Total expenses
        self.cached_stats["Expenses"].append(f"Total: {breakdown['total']:,.2f}")
        self.cached_stats["Expenses"].append("__SEPARATOR__")
        self.cached_stats["Expenses"].append("")
        
        # Cost of Living
        col = breakdown["cost_of_living"]
        self.cached_stats["Expenses"].append(f"Cost of Living")
        self.cached_stats["Expenses"].append(f"      Total: {col['total']:,.2f}")
        for sub_name, sub_val in col.items():
            if sub_name == "total":
                continue
            self.cached_stats["Expenses"].append(f"      {sub_name}: {sub_val:,.2f}")
        self.cached_stats["Expenses"].append("__SEPARATOR__")
        
        # Trading Expenses
        trading = breakdown["trading_expenses"]
        self.cached_stats["Expenses"].append(f"Trading Expenses")
        self.cached_stats["Expenses"].append(f"      Total: {trading['total']:,.2f}")
        for sub_name, sub_val in trading.items():
            if sub_name == "total":
                continue
            self.cached_stats["Expenses"].append(f"      {sub_name}: {sub_val:,.2f}")
        self.cached_stats["Expenses"].append("__SEPARATOR__")
        
        # Licenses
        licenses = breakdown["licenses"]
        self.cached_stats["Expenses"].append(f"Licenses")
        self.cached_stats["Expenses"].append(f"      Total: {licenses['total']:,.2f}")
        for sub_name, sub_val in licenses.items():
            if sub_name == "total":
                continue
            self.cached_stats["Expenses"].append(f"      {sub_name}: {sub_val:,.2f}")
        self.cached_stats["Expenses"].append("__SEPARATOR__")
        
        # Donations
        donations = breakdown["donations"]
        self.cached_stats["Expenses"].append(f"Donations")
        self.cached_stats["Expenses"].append(f"      Total: {donations['total']:,.2f}")
        for sub_name, sub_val in donations.items():
            if sub_name == "total":
                continue
            self.cached_stats["Expenses"].append(f"      {sub_name}: {sub_val:,.2f}")
        self.cached_stats["Expenses"].append("__SEPARATOR__")

        # Loans (includes loan interest and overdraft penalties)
        loans = breakdown.get("loans", {"total": 0.0, "Loan Interest": 0.0})
        overdraft = breakdown.get("overdraft", {"total": 0.0, "Overdraft Penalty": 0.0})
        loans_total = loans["total"] + overdraft["total"]
        self.cached_stats["Expenses"].append(f"Loans")
        self.cached_stats["Expenses"].append(f"      Total: {loans_total:,.2f}")
        for sub_name, sub_val in loans.items():
            if sub_name == "total":
                continue
            self.cached_stats["Expenses"].append(f"      {sub_name}: {sub_val:,.2f}")
        for sub_name, sub_val in overdraft.items():
            if sub_name == "total":
                continue
            self.cached_stats["Expenses"].append(f"      {sub_name}: {sub_val:,.2f}")
        self.cached_stats["Expenses"].append("__SEPARATOR__")

        # Property
        prop = breakdown.get("property", {"total": 0.0, "Buildings": 0.0})
        self.cached_stats["Expenses"].append(f"Property")
        self.cached_stats["Expenses"].append(f"      Total: {prop['total']:,.2f}")
        for sub_name, sub_val in prop.items():
            if sub_name == "total":
                continue
            self.cached_stats["Expenses"].append(f"      {sub_name}: {sub_val:,.2f}")
        self.cached_stats["Expenses"].append("__SEPARATOR__")

        # Miscellaneous
        misc = breakdown.get("miscellaneous", {"total": 0.0, "Well Coins": 0.0})
        self.cached_stats["Expenses"].append(f"Miscellaneous")
        self.cached_stats["Expenses"].append(f"      Total: {misc['total']:,.2f}")
        for sub_name, sub_val in misc.items():
            if sub_name == "total":
                continue
            self.cached_stats["Expenses"].append(f"      {sub_name}: {sub_val:,.2f}")
        self.cached_stats["Expenses"].append("__SEPARATOR__")

    def draw(self, screen: pygame.Surface, font: pygame.font.Font) -> None:
        """Draw the panel on a leaf of the counting house's sheet: the statistic's name, then its
        lines, a good's with its picture, each value set right at the end of a dotted leader.

        Args:
            screen: The surface to draw on.
            font: Unused; the panel takes the counting house's own fonts.
        """
        if not self.visible:
            return
        from . import ledger_style as style
        self.update_statistics()
        style.leaf(screen, self.rect)

        title = style.title_font(26).render(self.current_statistic or "Details", True, style.INK)
        screen.blit(title, (self.rect.x + 16, self.rect.y + 10))
        rule_y = self.rect.y + 48
        pygame.draw.line(screen, style.BRASS, (self.rect.x + 14, rule_y), (self.rect.right - 14, rule_y), 1)
        pygame.draw.line(screen, style.blend(style.BRASS, style.PAPER, 0.5), (self.rect.x + 14, rule_y + 2),
                         (self.rect.right - 14, rule_y + 2), 1)

        scroll_area = pygame.Rect(self.rect.x, rule_y + 8, self.rect.width - 10, self.rect.bottom - rule_y - 16)
        old_clip = screen.get_clip()
        screen.set_clip(scroll_area)
        y_pos = scroll_area.y + 4 - self.scroll_offset
        line_height = 24
        body = style.font(19)
        goods_images = self.game_state.game.images.get('goods_30', {}) if hasattr(self.game_state.game, 'images') else {}
        left, right = self.rect.x + 16, self.rect.right - 22

        for line in self.cached_stats.get(self.current_statistic, []):
            if line == "__SEPARATOR__":
                pygame.draw.line(screen, style.RULE, (left, y_pos - 3), (right, y_pos - 3), 1)
                continue
            text_color = style.INK
            if line.lstrip().startswith("__GREEN__"):
                text_color = style.GAIN_INK
                line = line.replace("__GREEN__", "", 1)
            elif line.lstrip().startswith("__RED__"):
                text_color = style.LOSS_INK
                line = line.replace("__RED__", "", 1)
            indent = (len(line) - len(line.lstrip())) * 3
            display = line.strip()
            if not display:
                y_pos += line_height // 2
                continue
            if indent == 0 and ":" not in display:                 # a heading, a good's with its picture
                x = left
                if display in goods_images:
                    screen.blit(pygame.transform.smoothscale(goods_images[display], (22, 22)), (x, y_pos))
                    x += 28
                heading = style.title_font(21).render(display, True, style.INK)
                screen.blit(heading, (x, y_pos))
            elif ":" in display:
                label, value = (part.strip() for part in display.split(":", 1))
                label_ink = style.FAINT_INK if indent else style.INK
                label_s = body.render(label, True, label_ink if text_color == style.INK else text_color)
                value_s = body.render(value, True, text_color)
                screen.blit(label_s, (left + indent, y_pos))
                screen.blit(value_s, (right - value_s.get_width(), y_pos))
                style.leader(screen, left + indent + label_s.get_width() + 8, right - value_s.get_width() - 6,
                             y_pos + 15)
            else:
                screen.blit(body.render(display, True, text_color), (left + indent, y_pos))
            y_pos += line_height

        content_height = (y_pos + self.scroll_offset) - (scroll_area.y + 4) + 8
        self.max_scroll = max(0, content_height - scroll_area.height)
        self.scroll_offset = min(self.scroll_offset, self.max_scroll)
        screen.set_clip(old_clip)

        if self.max_scroll > 0:                                     # a brass scrollbar in the leaf's margin
            track = pygame.Rect(self.rect.right - 9, scroll_area.y, 4, scroll_area.height)
            pygame.draw.rect(screen, style.RULE, track, border_radius=2)
            handle_h = max(24, track.height * track.height // content_height)
            handle_y = track.y + (track.height - handle_h) * self.scroll_offset // self.max_scroll
            pygame.draw.rect(screen, style.BRASS_DARK, (track.x, handle_y, 4, handle_h), border_radius=2)
