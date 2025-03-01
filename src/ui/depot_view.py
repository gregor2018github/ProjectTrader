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
    
    stats = [
        ("Wealth Today", f"{current_wealth:.2f}"),
        ("Wealth Yesterday", f"{start_wealth:.2f}"),
        ("Profit", f"{wealth_change:.2f}"),
        ("Profit Margin", f"{(wealth_change/start_wealth*100):.1f}%"),
        ("Total Trades", str(len(depot.trades))),
        # from last value of the list depot.total_stock
        ("Total Stock", str(depot.total_stock[-1]))
    ]
    
    if depot.trades:
        # Get most recent trade
        last_trade = depot.trades[-1]
        stats.extend([
            ("Last Trade", ""),
            ("   Good", last_trade["good"]),
            ("   Type", last_trade["type"].title()),
            ("   Quantity", str(last_trade["quantity"])),
            ("   Price", f"{last_trade['price']:.2f}"),
            ("   Total", f"{last_trade['total']:.2f}")
        ])
    
    # Draw statistics
    for i, (label, value) in enumerate(stats):
        y_pos = y + 80 + (i * 30)
        label_surf = font.render(label + ":", True, DARK_BROWN)
        value_surf = font.render(value, True, BLACK)
        screen.blit(label_surf, (x + 20, y_pos))
        screen.blit(value_surf, (x + 250, y_pos))
