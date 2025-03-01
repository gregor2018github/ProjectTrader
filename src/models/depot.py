class Depot:
    def __init__(self, money):
        self.money = money
        self.good_stock = {
            "Wood": 0, "Stone": 0, "Iron": 0,
            "Wool": 0, "Hide": 0, "Fish": 0,
            "Wheat": 0, "Wine": 0, "Beer": 0,
            "Meat": 0, "Linen": 0, "Pottery": 0,
        }
        self.properties = {
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
        self.trades = []
        self.wealth = [money]
        self.total_stock = [0]

    def buy(self, good, quantity_to_buy, game_state):
        """Buy a quantity of a good from market to depot"""
        if self.money >= good.get_price() * quantity_to_buy:
            if good.get_quantity() >= quantity_to_buy:
                self.money -= good.get_price() * quantity_to_buy
                self.good_stock[good.name] = self.good_stock.get(good.name, 0) + quantity_to_buy
                good.buy(quantity_to_buy)
                self.record_trade(good, quantity_to_buy, good.get_price(), True, game_state)
            else:
                raise Exception("The market does not have enough of that good to sell.")
        else:
            raise Exception("You do not have enough money to buy that good.")

    def sell(self, good, quantity_to_sell, game_state):
        """Sell a quantity of a good from depot to market"""
        if good.name in self.good_stock:
            if self.good_stock[good.name] >= quantity_to_sell:
                self.money += good.get_price() * quantity_to_sell
                self.good_stock[good.name] -= quantity_to_sell
                good.sell(quantity_to_sell)
                self.record_trade(good, quantity_to_sell, good.get_price(), False, game_state)
            else:
                raise Exception("You do not have enough of that good to sell.")
        else:
            raise Exception("You do not have any of that good to sell.")
        
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
    
    def update_wealth(self, goods):
        """Update the wealth, consisting of money and the value of all goods in stock"""
        total_value = self.money
        
        for good_name, quantity in self.good_stock.items():
            for good in goods:
                if good.name == good_name:
                    total_value += quantity * good.get_price()
                    break
                    
        self.wealth.append(total_value)
        return total_value
    
    def update_total_stock(self):
        """Update the total stock value"""
        total_stock = sum(self.good_stock.values())
        self.total_stock.append(total_stock)
        return total_stock
    
