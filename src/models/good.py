import random

class Good:
    def __init__(self, name, price, market_quantity, color, index, show_in_charts):
        self.name = name
        self.price = price
        self.market_quantity = market_quantity
        self.price_history_daily = [price]      # store price history for bookkeeping, updated daily
        self.price_history_hourly = [price]     # store detailed price history for charts, updated hourly
        self.color_orig = color                 # Original color when game started
        self.color_current = color              # Currently saved color
        self.color_temp = color                 # Temporary color changes from settings
        self.color = self.color_temp            # Used for drawing; always synced to color_temp
        self.index = index
        self.base_price = price
        self.show_in_charts = show_in_charts
        self.upper_bound = price * random.uniform(1.5, 3.5)
        self.lower_bound = price * random.uniform(0.05, 0.80)
        self.hovered = False
    
    def buy(self, quantity):
        self.market_quantity -= quantity

    def sell(self, quantity):
        self.market_quantity += quantity

    def update_price(self):
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

    def update_price_history(self):
        """Update the price history for bookkeeping (daily)"""
        self.price_history_daily.append(self.price)
    
    def update_price_history_chart(self):
        """Update the price history for charts (hourly)"""
        self.price_history_hourly.append(self.price)
    
    def get_price(self):
        return self.price
    
    def set_price(self, price):
        self.price = price
    
    def get_quantity(self):
        return self.market_quantity
    
    def set_quantity(self, quantity):
        self.market_quantity = quantity
    
    def toggle_display(self):
        self.show_in_charts = not self.show_in_charts
