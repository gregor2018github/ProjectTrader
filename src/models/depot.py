import datetime
from typing import Dict, List, Optional, Any, Union
from ..config.constants import STARTING_LICENSES

class Depot:
    """Manages the player's financial state, inventory, and trade history.
    
    The Depot handles buying and selling of goods, tracks wealth over time,
    maintains a FIFO purchase history for profit calculation, and manages
    property ownership and trade statistics.
    """
    
    def __init__(self, money: float, transaction_cost: float, storage_capacity: int) -> None:
        """Initialize the depot with starting values.
        
        Args:
            money: Initial amount of money.
            transaction_cost: Flat cost per trade transaction.
            storage_capacity: Maximum number of goods units that can be stored.
        """
        # CURRENT STATE

        self.money: float = money                       # current money
        self.transaction_cost: float = transaction_cost # cost per transaction
        self.storage_capacity: int = storage_capacity   # maximum storage capacity
        self.warehouse_count: int = 1                   # number of warehouses owned (by default 1)
        self.good_stock: Dict[str, int] = {             # current stock of goods
            "Wood": 0, "Stone": 0, "Iron": 0,
            "Wool": 0, "Hide": 0, "Fish": 0,
            "Wheat": 0, "Wine": 0, "Beer": 0,
            "Meat": 0, "Linen": 0, "Pottery": 0,
        }
        self.properties: Dict[str, List[Any]] = {       # current properties
            "warehouses": [],
            "workshops": [],
            "farms": [],
            "mines": [],
            "taverns": [],
            "markets": [],
            "shipyards": [],
            "churches": [],
            "castles": [],
            "town_halls": [],
            "houses": []
        }
        self.expenditures: float = 0                    # current expenditures
        self.income: float = 0                          # current income
        self.transaction_expenditures: float = 0        # current transaction expenditures
        self.donation_expenditures: float = 0           # current donation expenditures
        self.cost_of_living_expenditures: float = 0     # current cost of living expenditures
        self.license_expenditures: float = 0            # current license expenditures
        self.loan_expenditures: float = 0.0             # current loan interest paid today
        self.overdraft_expenditures: float = 0.0        # current overdraft penalties paid today
        self.donations: Dict[str, float] = {            # donation subcategories (current day)
            "Church Donations": 0,
            "Town Donations": 0,
        }

        # BOOKKEEPING

        self.active_loans: List[Dict[str, Any]] = []   # list of active loan dicts
        self.wealth: List[float] = [money]              # wealth tracking for bookkeeping
        self.money_history: List[float] = [money]       # money tracking for bookkeeping
        self.property_value_history: List[float] = [0.0]  # property value history (placeholder for future)
        self.loan_history: List[float] = [0.0]          # outstanding loan principal history
        self.total_stock: List[int] = [0]               # total stock tracking for bookkeeping
        self.house_history: List[int] = [0]             # history of owned houses
        self.stock_history: Dict[str, List[int]] = {    # stock tracking for bookkeeping
            good_name: [0] for good_name in self.good_stock
        }
        self.trades: List[Dict[str, Any]] = []                     # trade tracking for bookkeeping
        self.expenditure_history: List[float] = [0.0]              # expenditures tracking for bookkeeping
        self.income_history: List[float] = [0.0]                   # income tracking for bookkeeping
        self.transaction_expenditure_history: List[float] = [0.0]  # transaction expenditures tracking for bookkeeping
        self.donation_expenditure_history: List[float] = [0.0]     # donation expenditures tracking for bookkeeping
        self.cost_of_living_expenditure_history: List[float] = [0.0]  # cost of living tracking for bookkeeping
        self.license_expenditure_history: List[float] = [0.0]      # license expenditures tracking for bookkeeping
        self.loan_expenditure_history: List[float] = [0.0]         # loan interest tracking for bookkeeping
        self.overdraft_expenditure_history: List[float] = [0.0]    # overdraft penalty tracking for bookkeeping
        self.donation_history: Dict[str, List[float]] = {          # donation subcategory history for bookkeeping
            "Church Donations": [0.0],
            "Town Donations": [0.0],
        }
        # FIFO queue to track purchased goods with their prices
        self.purchase_history: Dict[str, List[Dict[str, Any]]] = {good_name: [] for good_name in self.good_stock}

        # Add trade cycle tracking
        self.trade_cycles: Dict[str, Any] = {
            "total": 0,                             # Total number of completed trade cycles
            "successful": 0,                        # Number of profitable trade cycles
            "total_profit": 0,                      # Cumulative profit from all trade cycles
            "by_good": {},                          # Statistics broken down by good
        }
        
        # Initialize trade cycle tracking for each good
        for good_name in self.good_stock:
            self.trade_cycles["by_good"][good_name] = {
                "total": 0,
                "successful": 0,
                "total_profit": 0,
                "avg_profit": 0,
                "best_profit": 0,
                "worst_profit": 0,
            }
        
        # Add list to record individual trade cycles with their timestamp
        self.trade_cycle_records: List[Dict[str, Any]] = []

        # TRADING LICENSES
        # Each license maps good_name -> expiry datetime
        self.trading_licenses: Dict[str, datetime.datetime] = {}

    def init_starting_licenses(self, start_date: datetime.datetime) -> None:
        """Initialize trading licenses from constants.
        
        Args:
            start_date: The game's starting date to calculate expiry from.
        """
        for good_name, months in STARTING_LICENSES:
            self.add_license(good_name, months, start_date)

    def add_license(self, good_name: str, months: int, current_date: datetime.datetime) -> None:
        """Grant a trading license for a good.
        
        Args:
            good_name: Name of the good.
            months: Duration in months.
            current_date: Current game date.
        """
        # Calculate expiry: advance by the given number of months
        new_month = current_date.month + months
        new_year = current_date.year + (new_month - 1) // 12
        new_month = (new_month - 1) % 12 + 1
        try:
            expiry = current_date.replace(year=new_year, month=new_month)
        except ValueError:
            # Handle end-of-month edge cases (e.g., Jan 31 + 1 month)
            import calendar
            last_day = calendar.monthrange(new_year, new_month)[1]
            expiry = current_date.replace(year=new_year, month=new_month, day=last_day)

        # If already licensed, extend from the later of current expiry or now
        if good_name in self.trading_licenses and self.trading_licenses[good_name] > current_date:
            base = self.trading_licenses[good_name]
            ext_month = base.month + months
            ext_year = base.year + (ext_month - 1) // 12
            ext_month = (ext_month - 1) % 12 + 1
            try:
                expiry = base.replace(year=ext_year, month=ext_month)
            except ValueError:
                import calendar
                last_day = calendar.monthrange(ext_year, ext_month)[1]
                expiry = base.replace(year=ext_year, month=ext_month, day=last_day)

        self.trading_licenses[good_name] = expiry

    def has_license(self, good_name: str, current_date: datetime.datetime) -> bool:
        """Check if the player has a valid trading license for a good.
        
        Args:
            good_name: Name of the good.
            current_date: Current game date.
            
        Returns:
            bool: True if a valid license exists.
        """
        if good_name not in self.trading_licenses:
            return False
        return self.trading_licenses[good_name] > current_date

    def get_licenses(self, current_date: datetime.datetime) -> List[Dict[str, Any]]:
        """Get all trading licenses with remaining days.
        
        Args:
            current_date: Current game date.
            
        Returns:
            List of dicts with 'good', 'expiry', and 'days_left' keys.
        """
        result = []
        for good_name, expiry in self.trading_licenses.items():
            days_left = (expiry - current_date).days
            result.append({
                "good": good_name,
                "expiry": expiry,
                "days_left": max(0, days_left),
            })
        return result

    def buy(self, good: Any, quantity_to_buy: int, game_state: Any) -> bool:
        """Buy a quantity of a good from market to depot.
        
        Args:
            good: The good object to buy.
            quantity_to_buy: Number of units to purchase.
            game_state: Current game state for warnings and context.
            
        Returns:
            bool: True if purchase was successful, False otherwise.
        """
        if not self.has_license(good.name, game_state.date):
            game_state.show_warning(f"No trading license for {good.name}.")
            return False

        total_cost = good.get_price() * quantity_to_buy
        
        if self.money < total_cost + self.transaction_cost:
            game_state.show_warning("Not enough money.")
            return False

        current_total_stock = sum(self.good_stock.values())
        if current_total_stock + quantity_to_buy > self.storage_capacity:
            game_state.show_warning("Not enough storage capacity.")
            return False

        if good.get_quantity() < quantity_to_buy:
            game_state.show_warning("Market cannot fulfill the order.")
            return False

        self.money -= (total_cost + self.transaction_cost)
        self.good_stock[good.name] = self.good_stock.get(good.name, 0) + quantity_to_buy
        self.expenditures += (total_cost + self.transaction_cost)
        self.transaction_expenditures += self.transaction_cost
        
        # Store purchase in FIFO queue with timestamp, price, and quantity
        self.purchase_history[good.name].append({
            "timestamp": game_state.date,
            "price": good.get_price(),
            "quantity": quantity_to_buy,
            "total_cost": total_cost
        })
        
        good.buy(quantity_to_buy)
        self.record_trade(good, quantity_to_buy, good.get_price(), True, game_state)
        return True

    def sell(self, good: Any, quantity_to_sell: int, game_state: Any) -> bool:
        """Sell a quantity of a good from depot to market using FIFO method.
        
        Calculates profit based on original purchase prices and identifies
        completed trade cycles.
        
        Args:
            good: The good object to sell.
            quantity_to_sell: Number of units to sell.
            game_state: Current game state for warnings and context.
            
        Returns:
            bool: True if sale was successful, False otherwise.
        """
        if not self.has_license(good.name, game_state.date):
            game_state.show_warning(f"No trading license for {good.name}.")
            return False
        if good.name not in self.good_stock:
            game_state.show_warning(f"No {good.name} in stock.")
            return False
        if self.good_stock[good.name] < quantity_to_sell:
            game_state.show_warning(f"Not enough {good.name} in stock.")
            return False

        current_sale_price = good.get_price()
        total_revenue = current_sale_price * quantity_to_sell
        
        if self.money + total_revenue < self.transaction_cost:
            game_state.show_warning("Not enough money to cover transaction costs.")
            return False

        self.money += (total_revenue - self.transaction_cost)
        self.good_stock[good.name] -= quantity_to_sell
        self.income += total_revenue
        self.expenditures += self.transaction_cost
        self.transaction_expenditures += self.transaction_cost
        remaining_to_sell = quantity_to_sell
        total_cost_of_goods_sold = 0
        purchase_entries = self.purchase_history[good.name]
        
        while remaining_to_sell > 0 and purchase_entries:
            oldest_purchase = purchase_entries[0]
            if oldest_purchase["quantity"] <= remaining_to_sell:
                quantity_used = oldest_purchase["quantity"]
                cost_of_goods_sold = oldest_purchase["price"] * quantity_used
                purchase_entries.pop(0)
            else:
                quantity_used = remaining_to_sell
                cost_of_goods_sold = oldest_purchase["price"] * quantity_used
                oldest_purchase["quantity"] -= quantity_used
                oldest_purchase["total_cost"] = oldest_purchase["price"] * oldest_purchase["quantity"]
            total_cost_of_goods_sold += cost_of_goods_sold
            remaining_to_sell -= quantity_used
            profit = (current_sale_price - oldest_purchase["price"]) * quantity_used
            self._record_trade_cycle(good.name, profit, quantity_used, oldest_purchase["price"], current_sale_price, game_state.date)
        
        good.sell(quantity_to_sell)
        self.record_trade(good, quantity_to_sell, current_sale_price, False, game_state)
        return True
        
    def record_trade(self, good: Any, quantity: int, price: float, is_purchase: bool, game_state: Any) -> None:
        """Record a trade for statistical purposes.
        
        Args:
            good: The good object traded.
            quantity: Number of units.
            price: Price per unit.
            is_purchase: True if buying, False if selling.
            game_state: Current game state for timestamp.
        """
        trade = {
            "timestamp": game_state.date,
            "good": good.name,
            "quantity": quantity,
            "price": price,
            "type": "purchase" if is_purchase else "sale",
            "total": price * quantity
        }
        self.trades.append(trade)
    
    def _record_trade_cycle(self, good_name: str, profit: float, quantity: int, buy_price: float, sell_price: float, timestamp: datetime.datetime) -> Dict[str, Any]:
        """Record statistics for a completed trade cycle and store an individual record.
        
        A trade cycle is defined by the match of a sale with its original purchase(s) in FIFO order.
        """
        # Update overall statistics
        self.trade_cycles["total"] += 1
        self.trade_cycles["total_profit"] += profit
        
        if profit > 0:
            self.trade_cycles["successful"] += 1
        
        # Update good-specific statistics
        good_stats = self.trade_cycles["by_good"][good_name]
        good_stats["total"] += 1
        good_stats["total_profit"] += profit
        
        if profit > 0:
            good_stats["successful"] += 1
        
        # Update average profit
        if good_stats["total"] > 0:
            good_stats["avg_profit"] = good_stats["total_profit"] / good_stats["total"]
        
        # Update best and worst profit only if quantity is same
        profit_per_unit = profit / quantity
        
        if good_stats["best_profit"] < profit_per_unit or good_stats["total"] == 1:
            good_stats["best_profit"] = profit_per_unit
            
        if good_stats["worst_profit"] > profit_per_unit or good_stats["total"] == 1:
            good_stats["worst_profit"] = profit_per_unit
            
        # Track this specific trade cycle
        trade_cycle = {
            "good": good_name,
            "quantity": quantity,
            "buy_price": buy_price,
            "sell_price": sell_price,
            "profit": profit,
            "profit_per_unit": profit_per_unit,
            "timestamp": timestamp
        }
        
        self.trade_cycle_records.append(trade_cycle)
        return trade_cycle
    
    def update_wealth(self, goods: List[Any]) -> float:
        """Update the wealth, consisting of money and the value of all goods in stock.
        
        Args:
            goods: List of all good objects in the game to get current prices.
            
        Returns:
            float: The newly calculated total wealth value.
        """
        total_value = self.money

        for good_name, quantity in self.good_stock.items():
            for good in goods:
                if good.name == good_name:
                    total_value += quantity * good.get_price()
                    break

        outstanding = sum(
            loan.get("remaining_principal", loan.get("amount", 0.0))
            for loan in self.active_loans
        )
        total_value -= outstanding

        self.wealth.append(total_value)
        self.money_history.append(self.money)
        self.property_value_history.append(0.0)  # updated when property system is implemented
        self.loan_history.append(outstanding)
        return total_value
    
    def update_income_and_expenditures(self) -> None:
        """Update the income and expenditures history for the current day and reset daily counters."""
        self.income_history.append(self.income)
        self.expenditure_history.append(self.expenditures)
        self.transaction_expenditure_history.append(self.transaction_expenditures)
        self.donation_expenditure_history.append(self.donation_expenditures)
        self.cost_of_living_expenditure_history.append(self.cost_of_living_expenditures)
        self.license_expenditure_history.append(self.license_expenditures)
        self.loan_expenditure_history.append(self.loan_expenditures)
        self.overdraft_expenditure_history.append(self.overdraft_expenditures)
        for category, amount in self.donations.items():
            self.donation_history[category].append(amount)
        self.income = 0
        self.expenditures = 0
        self.transaction_expenditures = 0
        self.donation_expenditures = 0
        self.cost_of_living_expenditures = 0
        self.license_expenditures = 0
        self.loan_expenditures = 0.0
        self.overdraft_expenditures = 0.0
        for category in self.donations:
            self.donations[category] = 0
    
    def update_total_stock(self) -> int:
        """Update the total stock count history.
        
        Returns:
            int: The current total number of units in stock.
        """
        total_stock = sum(self.good_stock.values())
        self.total_stock.append(total_stock)
        
        # Also update house count history (assuming houses property exists)
        house_count = len(self.properties.get("houses", []))
        self.house_history.append(house_count)
        
        return total_stock
    
    def update_stock_history(self) -> None:
        """Update the stock history for all goods for bookkeeping."""
        for good_name, quantity in self.good_stock.items():
            self.stock_history[good_name].append(quantity)
    
    def get_trade_cycle_stats(self, current_date: datetime.datetime, time_delta: Optional[datetime.timedelta]) -> Dict[str, Any]:
        """Return summarized trade cycle statistics filtered by an optional time_delta.
           
        Args:
            current_date: The reference date for filtering.
            time_delta: The duration to look back. If None, all history is included.
            
        Returns:
            Dict[str, Any]: Summarized statistics including total cycles, success rate, and best/worst goods.
        """
        if time_delta is not None:
            start_date = current_date - time_delta
            records = [r for r in self.trade_cycle_records if r["timestamp"] >= start_date]
        else:
            records = self.trade_cycle_records[:]
        
        total_cycles = len(records)
        successful_cycles = sum(1 for r in records if r["profit"] > 0)
        total_profit = sum(r["profit"] for r in records)
        
        # Group profit per unit by good for aggregation
        by_good = {}
        for r in records:
            name = r["good"]
            by_good.setdefault(name, []).append(r["profit_per_unit"])
        best_goods = sorted(
            [(name, sum(profits)/len(profits)) for name, profits in by_good.items()],
            key=lambda x: x[1],
            reverse=True
        )
        worst_goods = sorted(
            [(name, sum(profits)/len(profits)) for name, profits in by_good.items()],
            key=lambda x: x[1]
        )
        stats = {
            "total_cycles": total_cycles,
            "successful_cycles": successful_cycles,
            "success_rate": (successful_cycles/total_cycles*100) if total_cycles > 0 else 0,
            "total_profit": total_profit,
            "best_goods": best_goods[:3], 
            "worst_goods": worst_goods[:3]
        }
        return stats
    
    def book_cost_of_living(self, cost_of_living: float) -> None:
        """Book the cost of living for the current day.
        
        Args:
            cost_of_living: The amount to deduct from money and add to expenditures.
        """
        self.money -= cost_of_living
        self.expenditures += cost_of_living
        self.cost_of_living_expenditures += cost_of_living

    def book_donation(self, amount: float, category: str = "Church Donations") -> bool:
        """Book a donation as an expenditure.
        
        Args:
            amount: The donation amount.
            category: The donation subcategory (e.g. "Church Donations").
            
        Returns:
            bool: True if the donation was booked successfully, False if insufficient funds.
        """
        if self.money < amount:
            return False
        
        self.money -= amount
        self.expenditures += amount
        self.donation_expenditures += amount
        
        # Track by subcategory, initialize if new
        if category not in self.donations:
            self.donations[category] = 0
            self.donation_history[category] = [0.0] * len(self.donation_expenditure_history)
        self.donations[category] += amount
        
        return True

    def book_loan_interest(self, amount: float) -> None:
        """Charge loan interest.

        Args:
            amount: The amount to deduct from money and record as loan expenditure.
        """
        self.money -= amount
        self.expenditures += amount
        self.loan_expenditures += amount

    def book_overdraft_penalty(self, amount: float) -> None:
        """Charge an overdraft penalty (negative balance fee).

        Args:
            amount: The amount to deduct from money and record as overdraft expenditure.
        """
        self.money -= amount
        self.expenditures += amount
        self.overdraft_expenditures += amount

    def take_loan(self, original_amount: float, daily_principal: float,
                  daily_interest: float, settlement_principal: float,
                  duration_days: int, start_date: str) -> None:
        """Record a new loan and credit the principal to the player's cash.

        Each day the player pays daily_principal (principal repayment) plus
        daily_interest (interest cost). At maturity, settlement_principal covers
        whatever principal was not yet repaid through daily installments.

        Args:
            original_amount: Total principal borrowed.
            daily_principal: Principal amount repaid each day.
            daily_interest: Fixed interest charged each day.
            settlement_principal: Remaining principal paid at maturity.
            duration_days: Term length in days.
            start_date: Display date string.
        """
        self.money += original_amount
        self.active_loans.append({
            "original_amount": original_amount,
            "remaining_principal": original_amount,
            "daily_principal": daily_principal,
            "daily_interest": daily_interest,
            "settlement_principal": settlement_principal,
            "duration_days": duration_days,
            "days_elapsed": 0,
            "start_date": start_date,
        })

    def repay_loan(self, loan_index: int, game_state: Any) -> bool:
        """Repay the remaining principal of a loan early.

        Args:
            loan_index: Index into self.active_loans.
            game_state: Used to show a warning if funds are insufficient.

        Returns:
            bool: True if repayment succeeded, False if insufficient funds.
        """
        if loan_index < 0 or loan_index >= len(self.active_loans):
            return False
        loan = self.active_loans[loan_index]
        remaining = loan.get("remaining_principal", loan.get("amount", 0.0))
        if self.money < remaining:
            game_state.show_warning("Not enough money to repay loan.")
            return False
        self.money -= remaining
        self.active_loans.pop(loan_index)
        return True

    def get_expense_breakdown(self, period_days: Optional[int] = None) -> Dict[str, Any]:
        """Get a full expense breakdown for a given time period.
        
        Returns totals for three top-level categories:
          - Cost of Living (with subcategory Food)
          - Trading Expenses (with subcategories Transaction Cost, Good Cost)
          - Licenses (with subcategory Trading Licenses)
          - Donations (with subcategories from self.donations)
        
        Args:
            period_days: Number of days to look back. None for all time.
            
        Returns:
            Dict with total expenses and per-category breakdowns.
        """
        if period_days is not None:
            num_history_days = period_days - 1
            if num_history_days > 0:
                total_exp = sum(self.expenditure_history[-num_history_days:]) + self.expenditures
                total_transaction = sum(self.transaction_expenditure_history[-num_history_days:]) + self.transaction_expenditures
                total_col = sum(self.cost_of_living_expenditure_history[-num_history_days:]) + self.cost_of_living_expenditures
                total_donation = sum(self.donation_expenditure_history[-num_history_days:]) + self.donation_expenditures
                total_license = sum(self.license_expenditure_history[-num_history_days:]) + self.license_expenditures
                total_loan = sum(self.loan_expenditure_history[-num_history_days:]) + self.loan_expenditures
                total_overdraft = sum(self.overdraft_expenditure_history[-num_history_days:]) + self.overdraft_expenditures
                by_donation_cat = {}
                for category, history in self.donation_history.items():
                    by_donation_cat[category] = sum(history[-num_history_days:]) + self.donations.get(category, 0)
            else:
                total_exp = self.expenditures
                total_transaction = self.transaction_expenditures
                total_col = self.cost_of_living_expenditures
                total_donation = self.donation_expenditures
                total_license = self.license_expenditures
                total_loan = self.loan_expenditures
                total_overdraft = self.overdraft_expenditures
                by_donation_cat = dict(self.donations)
        else:
            total_exp = sum(self.expenditure_history) + self.expenditures
            total_transaction = sum(self.transaction_expenditure_history) + self.transaction_expenditures
            total_col = sum(self.cost_of_living_expenditure_history) + self.cost_of_living_expenditures
            total_donation = sum(self.donation_expenditure_history) + self.donation_expenditures
            total_license = sum(self.license_expenditure_history) + self.license_expenditures
            total_loan = sum(self.loan_expenditure_history) + self.loan_expenditures
            total_overdraft = sum(self.overdraft_expenditure_history) + self.overdraft_expenditures
            by_donation_cat = {}
            for category, history in self.donation_history.items():
                by_donation_cat[category] = sum(history) + self.donations.get(category, 0)

        # Good cost = trading expenditures minus transaction fees and other known categories
        total_good_cost = total_exp - total_transaction - total_col - total_donation - total_license - total_loan - total_overdraft

        return {
            "total": total_exp,
            "cost_of_living": {
                "total": total_col,
                "Food": total_col,  # Currently cost of living is only food
            },
            "trading_expenses": {
                "total": total_transaction + total_good_cost,
                "Transaction Cost": total_transaction,
                "Good Cost": total_good_cost,
            },
            "licenses": {
                "total": total_license,
                "Trading Licenses": total_license,
            },
            "donations": {
                "total": total_donation,
                **by_donation_cat,
            },
            "loans": {
                "total": total_loan,
                "Loan Interest": total_loan,
            },
            "overdraft": {
                "total": total_overdraft,
                "Overdraft Penalty": total_overdraft,
            },
        }

    def get_donation_stats(self, period_days: Optional[int] = None) -> Dict[str, Any]:
        """Get donation statistics for a given time period.
        
        Args:
            period_days: Number of days to look back. None for all time.
            
        Returns:
            Dict with total donations, breakdown by category, and history.
        """
        if period_days is not None:
            num_history_days = period_days - 1
            if num_history_days > 0:
                total = sum(self.donation_expenditure_history[-num_history_days:]) + self.donation_expenditures
                by_category = {}
                for category, history in self.donation_history.items():
                    by_category[category] = sum(history[-num_history_days:]) + self.donations.get(category, 0)
            else:
                total = self.donation_expenditures
                by_category = dict(self.donations)
        else:
            total = sum(self.donation_expenditure_history) + self.donation_expenditures
            by_category = {}
            for category, history in self.donation_history.items():
                by_category[category] = sum(history) + self.donations.get(category, 0)
        
        return {
            "total": total,
            "by_category": by_category,
        }
