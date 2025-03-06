import pygame
from ..config.colors import *

def draw_depot_view(screen, font, depot, game_state):
    # Calculate dimensions
    width = screen.get_width() // 2 - 42
    height = screen.get_height() - 120
    x = screen.get_width() - width
    y = 60
    
    # Create and draw main surface
    depot_rect = pygame.Rect(x, y, width, height)
    pygame.draw.rect(screen, BEIGE, depot_rect)
    pygame.draw.rect(screen, TAN, depot_rect, 10)
    pygame.draw.rect(screen, DARK_BROWN, depot_rect, 2)
    
    # Draw title
    current_day = game_state.date.strftime("%d.%m.%Y")
    title = font.render(f"Daily Depot Statistics - {current_day}", True, DARK_BROWN)
    title_rect = title.get_rect(center=(x + width//2, y + 30))
    screen.blit(title, title_rect)
    
    # Draw wealth information
    current_wealth = depot.wealth[-1]
    try: 
        start_wealth = depot.wealth[-2]
    except IndexError: 
        start_wealth = current_wealth
    wealth_change = current_wealth - start_wealth
    
    # Get trade statistics
    buy_actions = sum(1 for trade in depot.trades if trade["type"] == "purchase")
    sell_actions = sum(1 for trade in depot.trades if trade["type"] == "sale")
    
    # Create a smaller font for more detailed information
    small_font = pygame.font.SysFont("RomanAntique.ttf", 19)
    
    # Get trade cycle statistics
    cycle_stats = depot.get_trade_cycle_stats()
    
    # Organize stats into sections
    wealth_stats = [
        ("Wealth Today", f"{current_wealth:.2f}"),
        ("Wealth Yesterday", f"{start_wealth:.2f}"),
        ("Daily Profit", f"{wealth_change:.2f}"),
        ("Profit Margin", f"{(wealth_change/start_wealth*100):.1f}%" if start_wealth > 0 else "0.0%"),
        ("Total Stock", f"{depot.total_stock[-1]}")
    ]
    
    trade_action_stats = [
        ("Buy Actions", f"{buy_actions}"),
        ("Sell Actions", f"{sell_actions}"),
        ("Total Actions", f"{len(depot.trades)}")
    ]
    
    trade_cycle_stats = [
        ("Completed Trades", f"{cycle_stats['total_cycles']}"),
        ("Successful Trades", f"{cycle_stats['successful_cycles']}"),
        ("Success Rate", f"{cycle_stats['success_rate']:.1f}%"),
        ("Total Trade Profit", f"{cycle_stats['total_profit']:.2f}")
    ]
    
    # Draw section: Wealth Statistics
    section_y = y + 80
    section_title = font.render("Wealth Statistics", True, DARK_BROWN)
    screen.blit(section_title, (x + 20, section_y))
    section_y += 30
    
    for label, value in wealth_stats:
        draw_stat_row(screen, small_font, x, section_y, label, value)
        section_y += 24
    
    # Draw section: Trade Actions
    section_y += 15
    section_title = font.render("Trade Actions", True, DARK_BROWN)
    screen.blit(section_title, (x + 20, section_y))
    section_y += 30
    
    for label, value in trade_action_stats:
        draw_stat_row(screen, small_font, x, section_y, label, value)
        section_y += 24
    
    # Draw section: Trade Cycles
    section_y += 15
    section_title = font.render("Trade Cycles", True, DARK_BROWN)
    screen.blit(section_title, (x + 20, section_y))
    section_y += 30
    
    for label, value in trade_cycle_stats:
        draw_stat_row(screen, small_font, x, section_y, label, value)
        section_y += 24
    
    # Draw section: Best & Worst Goods
    section_y += 15
    section_title = font.render("Performance by Good", True, DARK_BROWN)
    screen.blit(section_title, (x + 20, section_y))
    section_y += 30
    
    # Draw best goods if available
    if cycle_stats["best_goods"]:
        draw_stat_row(screen, small_font, x, section_y, "Best Performing Goods:", "Profit/Unit")
        section_y += 24
        
        for i, (good_name, profit) in enumerate(cycle_stats["best_goods"][:3]):
            if profit > 0:
                draw_stat_row(screen, small_font, x, section_y, f"   {i+1}. {good_name}", f"+{profit:.2f}")
                section_y += 24
    
    # Draw worst goods if available
    if cycle_stats["worst_goods"]:
        section_y += 5
        draw_stat_row(screen, small_font, x, section_y, "Worst Performing Goods:", "Profit/Unit")
        section_y += 24
        
        for i, (good_name, profit) in enumerate(reversed(cycle_stats["worst_goods"][-3:])):
            color = RED if profit < 0 else BLACK
            draw_stat_row(screen, small_font, x, section_y, f"   {i+1}. {good_name}", f"{profit:.2f}", value_color=color)
            section_y += 24
    
    # Draw most recent trade if available
    if depot.trades:
        section_y += 15
        last_trade = depot.trades[-1]
        section_title = font.render("Last Trade", True, DARK_BROWN)
        screen.blit(section_title, (x + 20, section_y))
        section_y += 30
        
        trade_type = "Purchase" if last_trade["type"] == "purchase" else "Sale"
        trade_color = RED if last_trade["type"] == "purchase" else GREEN
        
        draw_stat_row(screen, small_font, x, section_y, "Good", last_trade["good"])
        section_y += 24
        draw_stat_row(screen, small_font, x, section_y, "Type", trade_type, value_color=trade_color)
        section_y += 24
        draw_stat_row(screen, small_font, x, section_y, "Quantity", str(last_trade["quantity"]))
        section_y += 24
        draw_stat_row(screen, small_font, x, section_y, "Price", f"{last_trade['price']:.2f}")
        section_y += 24
        draw_stat_row(screen, small_font, x, section_y, "Total", f"{last_trade['total']:.2f}")

def draw_stat_row(screen, font, x, y, label, value, label_color=DARK_BROWN, value_color=BLACK):
    """Helper function to draw a row with label and value"""
    label_surf = font.render(label, True, label_color)
    value_surf = font.render(value, True, value_color)
    screen.blit(label_surf, (x + 20, y))
    screen.blit(value_surf, (x + 250, y))
