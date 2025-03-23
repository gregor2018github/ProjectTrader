class Depot:
    def __init__(self, money):

        # CURRENT STATE

        self.money = money              # current money
        self.good_stock = {             # current stock of goods
            "Wood": 0, "Stone": 0, "Iron": 0,
            "Wool": 0, "Hide": 0, "Fish": 0,
            "Wheat": 0, "Wine": 0, "Beer": 0,
            "Meat": 0, "Linen": 0, "Pottery": 0,
        }
        self.properties = {             # current properties
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

        # BOOKKEEPING

        self.wealth = [money]           # wealth tracking for bookkeeping
        self.money_history = [money]    # money tracking for bookkeeping
        self.total_stock = [0]          # total stock tracking for bookkeeping
        self.stock_history = {          # stock tracking for bookkeeping
            good_name: [0] for good_name in self.good_stock
        }
        self.trades = []                # trade tracking for bookkeeping
        # FIFO queue to track purchased goods with their prices
        self.purchase_history = {good_name: [] for good_name in self.good_stock}

        # Add trade cycle tracking
        self.trade_cycles = {
            "total": 0,  # Total number of completed trade cycles
            "successful": 0,  # Number of profitable trade cycles
            "total_profit": 0,  # Cumulative profit from all trade cycles
            "by_good": {},  # Statistics broken down by good
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
        self.trade_cycle_records = []

    def buy(self, good, quantity_to_buy, game_state):
        """Buy a quantity of a good from market to depot"""
        total_cost = good.get_price() * quantity_to_buy
        
        if self.money < total_cost:
            game_state.show_warning("Not enough money.")
            return False
        if good.get_quantity() < quantity_to_buy:
            game_state.show_warning("Market cannot fulfill the order.")
            return False

        self.money -= total_cost
        self.good_stock[good.name] = self.good_stock.get(good.name, 0) + quantity_to_buy
        
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

    def sell(self, good, quantity_to_sell, game_state):
        """Sell a quantity of a good from depot to market using FIFO method"""
        if good.name not in self.good_stock:
            game_state.show_warning(f"No {good.name} in stock.")
            return False
        if self.good_stock[good.name] < quantity_to_sell:
            game_state.show_warning(f"Not enough {good.name} in stock.")
            return False

        current_sale_price = good.get_price()
        total_revenue = current_sale_price * quantity_to_sell
        self.money += total_revenue
        self.good_stock[good.name] -= quantity_to_sell
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
        
    def record_trade(self, good, quantity, price, is_purchase, game_state):
        """Record a trade for statistical purposes"""
        trade = {
            "timestamp": game_state.date,
            "good": good.name,
            "quantity": quantity,
            "price": price,
            "type": "purchase" if is_purchase else "sale",
            "total": price * quantity
        }
        self.trades.append(trade)
    
    def _record_trade_cycle(self, good_name, profit, quantity, buy_price, sell_price, timestamp):
        """Record statistics for a completed trade cycle and store an individual record"""
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
    
    def update_wealth(self, goods):
        """Update the wealth, consisting of money and the value of all goods in stock"""
        total_value = self.money
        
        for good_name, quantity in self.good_stock.items():
            for good in goods:
                if good.name == good_name:
                    total_value += quantity * good.get_price()
                    break
                    
        self.wealth.append(total_value)
        self.money_history.append(self.money)  # Record current money
        return total_value
    
    def update_total_stock(self):
        """Update the total stock value"""
        total_stock = sum(self.good_stock.values())
        self.total_stock.append(total_stock)
        return total_stock
    
    def update_stock_history(self):
        """Update the stock history for all goods"""
        for good_name, quantity in self.good_stock.items():
            self.stock_history[good_name].append(quantity)
    
    def get_trade_cycle_stats(self, current_date, time_delta):
        """Return summarized trade cycle statistics filtered by an optional time_delta.
           If time_delta is provided, only trade cycles with timestamp >= (current_date - time_delta) are used.
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
    
    def book_cost_of_living(self, cost_of_living):
        """Book the cost of living for the current day"""
        self.money -= cost_of_living