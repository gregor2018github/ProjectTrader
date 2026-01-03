import pygame
from ..config.colors import YELLOW, BLACK, DARK_BROWN, TAN, BEIGE, PALE_BROWN, LIGHT_BROWN, WHEAT
import datetime

class DepotViewDetail:
    def __init__(self, depot_rect, game_state):
        # Place the detail panel just to the right of depot view
        self.rect = pygame.Rect(depot_rect.left + 370, depot_rect.top + 60, 300, depot_rect.height-80)
        self.visible = False
        self.current_statistic = None
        self.game_state = game_state
        
        # Add cache for wealth statistics
        self.cached_stats = {
            "Wealth Today": [],
            "Wealth Start": []
        }
        self.last_update_date = None
        self.last_time_frame = None  # Track the last time frame to detect changes
        # Add separate flags to track when each statistic was last updated
        self.last_today_update_date = None
        self.last_start_update_date = None

    def toggle(self):
        self.visible = not self.visible

    def show_for_statistic(self, statistic_label):
        self.current_statistic = statistic_label
        self.visible = True

    def update_statistics(self, force=False):
        """Update cached statistics if day has changed, time frame has changed, or force is True"""
        current_date = self.game_state.date.date()
        current_time_frame = self.game_state.depot_time_frame
        depot = self.game_state.game.depot
        goods = self.game_state.game.goods
        
        # Update "Wealth Today" only if day changed or forced
        if force or self.last_today_update_date != current_date:
            self._update_wealth_today(depot, goods)
            self.last_today_update_date = current_date
        
        # Update "Wealth Start" if time frame changed, day changed, or forced
        if force or self.last_start_update_date != current_date or self.last_time_frame != current_time_frame:
            self._update_wealth_start(depot, goods, current_time_frame)
            self.last_start_update_date = current_date
            self.last_time_frame = current_time_frame
        
        # Update last update timestamp for general statistics
        self.last_update_date = current_date
    
    def _update_wealth_today(self, depot, goods):
        """Update just the "Wealth Today" statistics"""
        # Calculate total goods value for Wealth Today, must come from the last daily records, not the very recent ones
        # base data is last qty of depot.stock_history and last price of good.price_history_daily
        total_goods_value = 0
        for good in goods:
            # Get the last recorded quantity from stock_history for this good
            qty = depot.stock_history.get(good.name, [0])[-1]
            price = good.price_history_daily[-1]
            total_goods_value += qty * price
            
        # Cache "Wealth Today" statistics
        self.cached_stats["Wealth Today"] = []
        
        # Add summary totals at the top
        total_wealth = depot.wealth[-1]
        self.cached_stats["Wealth Today"].append(f"Total: {total_wealth:,.2f}")
        self.cached_stats["Wealth Today"].append("__SEPARATOR__")
        self.cached_stats["Wealth Today"].append(f"Money: {depot.money_history[-1]:,.2f}")
        self.cached_stats["Wealth Today"].append(f"Goods: {total_goods_value:,.2f}")
        # place holders for future statistics
        self.cached_stats["Wealth Today"].append("Property: 0.00")
        self.cached_stats["Wealth Today"].append("Loans: 0.00")
        self.cached_stats["Wealth Today"].append("__SEPARATOR__")
        # empty line
        self.cached_stats["Wealth Today"].append("")
        
        # Add breakdown for each good that has quantity > 0, sorted by total value
        goods_with_value = []
        for good in goods:
            qty = depot.stock_history.get(good.name, [0])[-1]
            if qty > 0:
                price = good.price_history_daily[-1]
                value = qty * price
                goods_with_value.append((good, qty, price, value))
        
        # Sort by value descending
        goods_with_value.sort(key=lambda x: x[3], reverse=True)
        
        for good, qty, price, value in goods_with_value:
            # Add good name as a heading without value
            self.cached_stats["Wealth Today"].append(f"{good.name}")
            # Add indented details
            self.cached_stats["Wealth Today"].append(f"      Units: {qty:,}")
            self.cached_stats["Wealth Today"].append(f"      Unit Value: {price:,.2f}")
            self.cached_stats["Wealth Today"].append(f"      Total Value: {value:,.2f}")
            self.cached_stats["Wealth Today"].append("__SEPARATOR__")
    
    def _update_wealth_start(self, depot, goods, time_frame):
        """Update just the "Wealth Start" statistics based on selected time frame"""
        # Cache "Wealth Start" statistics based on selected time frame
        self.cached_stats["Wealth Start"] = []
        
        # Determine period days based on the selected time frame
        if time_frame == "Daily":
            period_days = 1
        elif time_frame == "Weekly":
            period_days = 7
        elif time_frame == "Monthly":
            period_days = 30
        elif time_frame == "Yearly":
            period_days = 365
        else:  # "Total"
            period_days = None
            
        # Get historical wealth and money values directly from records
        if period_days is not None and len(depot.wealth) > period_days:
            start_wealth = depot.wealth[-(period_days+1)]
            start_money = depot.money_history[-(period_days+1)]  # Use recorded money directly
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
            if period_days is not None and len(good.price_history_daily) > period_days:
                start_prices[good.name] = good.price_history_daily[-(period_days+1)]
            else:
                start_prices[good.name] = good.price_history_daily[0]
        
        # Calculate total goods value at start of period
        start_goods_value = 0
        for good in goods:
            good_name = good.name
            qty = start_goods.get(good_name, 0)
            price = start_prices[good_name]
            start_goods_value += qty * price
        
        # Add calculated stats to cache
        self.cached_stats["Wealth Start"].append(f"Total: {start_wealth:,.2f}")
        self.cached_stats["Wealth Start"].append("__SEPARATOR__")
        self.cached_stats["Wealth Start"].append(f"Money: {start_money:,.2f}")
        self.cached_stats["Wealth Start"].append(f"Goods: {start_goods_value:,.2f}")
        # place holders for future statistics
        self.cached_stats["Wealth Start"].append("Property: 0.00")
        self.cached_stats["Wealth Start"].append("Loans: 0.00")
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
    
    def draw(self, screen, font):
        if self.visible:
            # Update statistics if needed
            self.update_statistics()
            
            pygame.draw.rect(screen, WHEAT, self.rect)  # WHEAT or TAN look good
            pygame.draw.rect(screen, DARK_BROWN, self.rect, 3)
            
            small_font = self.game_state.small_font
            if hasattr(font, 'game_state') and hasattr(font.game_state, 'small_font'):
                small_font = font.game_state.small_font
            
            title_text = "Wealth Details"
            if self.current_statistic:
                title_text = f"{self.current_statistic} - Details"
                
            title = font.render(title_text, True, BLACK)
            screen.blit(title, (self.rect.x + 20, self.rect.y + 20))
            
            y_pos = self.rect.y + 60
            line_height = 24
            
            # Get good icons from game instance
            goods_images = None
            if hasattr(self.game_state, 'game') and hasattr(self.game_state.game, 'images'):
                goods_images = self.game_state.game.images.get('goods_30', {})
            
            # Use cached statistics if available
            lines = []
            if self.current_statistic in self.cached_stats:
                lines = self.cached_stats[self.current_statistic]
            elif self.current_statistic == "Buy Actions":
                lines.extend([
                    "Recent purchases:",
                    "  Wood: 24 units",
                    "  Iron: 12 units",
                    "  Beer: 8 units",
                    "  Total spent: 132.00"
                ])
            elif self.current_statistic == "Sell Actions":
                lines.extend([
                    "Recent sales:",
                    "  Wood: 14 units",
                    "  Iron: 8 units",
                    "  Beer: 4 units",
                    "  Total earned: 178.00"
                ])
            elif self.current_statistic == "Total Actions":
                lines.extend([
                    "All transactions:",
                    "  Purchases: 44 units",
                    "  Sales: 26 units",
                    "  Net profit: 46.00",
                    "  Average margin: 18.4%"
                ])
            else:
                lines.extend([
                    "Income: 1,240.00",
                    "Expenses: 450.00",
                    "Profit: 790.00",
                ])
            
            # Render detail lines with values aligned on the right side
            for line in lines:
                # Check if this is a separator marker
                if line == "__SEPARATOR__":
                    # Draw separator line
                    pygame.draw.line(screen, PALE_BROWN, 
                                    (self.rect.x + 20, y_pos-5), 
                                    (self.rect.x + self.rect.width - 20, y_pos-5), 1)
                    continue  # Skip rendering this line
                
                # Calculate indentation level (number of spaces at beginning)
                indent_level = len(line) - len(line.lstrip())
                indent_pixels = indent_level * 8  # 8 pixels per indentation space
                
                # Remove leading spaces for rendering
                display_line = line.lstrip()
                
                # Check if this line is just a good name (not indented and no colon)
                is_good_name = indent_level == 0 and ":" not in display_line
                
                if is_good_name and goods_images and display_line in goods_images:
                    # Render the good icon
                    good_icon = goods_images[display_line]
                    # Scale down the icon slightly if needed
                    icon_size = 24  # Slightly smaller than the original 30px
                    if good_icon.get_width() > icon_size:
                        good_icon = pygame.transform.scale(good_icon, (icon_size, icon_size))
                    
                    # Render good icon to the left of the name
                    screen.blit(good_icon, (self.rect.x + 20, y_pos - 5))
                    
                    # Render the good name with extra left padding for the icon
                    good_text = small_font.render(display_line, True, BLACK)
                    screen.blit(good_text, (self.rect.x + 50, y_pos))
                elif ":" in display_line:
                    parts = display_line.split(":", 1)
                    label_part = parts[0].strip() + ":"
                    value_part = parts[1].strip()
                    label_surf = small_font.render(label_part, True, BLACK)
                    value_surf = small_font.render(value_part, True, BLACK)
                    screen.blit(label_surf, (self.rect.x + 20 + indent_pixels, y_pos))
                    screen.blit(value_surf, (self.rect.x + 200, y_pos))
                else:
                    text = small_font.render(display_line, True, BLACK)
                    screen.blit(text, (self.rect.x + 20 + indent_pixels, y_pos))
                y_pos += line_height
            
            # add a visual closing as the last line to the content
            pygame.draw.line(screen, DARK_BROWN, (self.rect.x + 20, y_pos+10), (self.rect.x + self.rect.width - 20, y_pos+10), 2)
