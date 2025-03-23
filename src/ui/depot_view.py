import pygame
import datetime
from ..config.colors import *

def draw_depot_view(screen, font, depot, game_state):
    # Calculate dimensions
    width = screen.get_width() // 2 - 42
    height = screen.get_height() - 120
    x = screen.get_width() - width
    y = 60
    
    # Draw depot container
    depot_rect = pygame.Rect(x, y, width, height)
    pygame.draw.rect(screen, BEIGE, depot_rect)
    pygame.draw.rect(screen, TAN, depot_rect, 10)
    pygame.draw.rect(screen, DARK_BROWN, depot_rect, 2)
    
    # Draw heading with time frame
    current_day = game_state.date.strftime("%d.%m.%Y")
    
    # Calculate start date based on time frame
    if game_state.depot_time_frame == "Daily":
        start_date = game_state.date.strftime("%d.%m.%Y")
    elif game_state.depot_time_frame == "Weekly":
        start_date = (game_state.date - datetime.timedelta(days=6)).strftime("%d.%m.%Y")
    elif game_state.depot_time_frame == "Monthly":
        start_date = (game_state.date - datetime.timedelta(days=29)).strftime("%d.%m.%Y")
    elif game_state.depot_time_frame == "Yearly":
        start_date = (game_state.date - datetime.timedelta(days=364)).strftime("%d.%m.%Y")
    else:  # "Total"
        start_date = "01.01.1500"  # Game start date
    
    # Create heading text with date range
    if game_state.depot_time_frame == "Total":
        heading_text = f"{game_state.depot_time_frame} Depot Statistics ({start_date} - {current_day})"
    else:
        heading_text = f"{game_state.depot_time_frame} Depot Statistics ({start_date} - {current_day})"
    
    title = font.render(heading_text, True, DARK_BROWN)
    title_rect = title.get_rect(center=(x + width//2, y + 30))
    screen.blit(title, title_rect)
    
    # Define button size and positions relative to title
    btn_size = 30
    margin = 10  # margin between title and buttons
    left_btn_rect = pygame.Rect(title_rect.left - margin - btn_size, title_rect.centery - btn_size//2, btn_size, btn_size)
    right_btn_rect = pygame.Rect(title_rect.right + margin, title_rect.centery - btn_size//2, btn_size, btn_size)
    
    # Determine availability based on current time frame index
    current_index = game_state.depot_time_frames.index(game_state.depot_time_frame)
    left_active = current_index > 0
    right_active = current_index < len(game_state.depot_time_frames) - 1

    # New button design: render only available buttons with rounded rectangles and double arrows,
    # with arrows turning white on hover
    button_bg_color = SANDY_BROWN
    button_border_color = DARK_BROWN
    default_arrow_color = DARK_BROWN
    hover_arrow_color = WHITE
    arrow_font = pygame.font.SysFont("RomanAntique.ttf", 24)
    mouse_pos = pygame.mouse.get_pos()

    if left_active:
        pygame.draw.rect(screen, button_bg_color, left_btn_rect, border_radius=5)
        pygame.draw.rect(screen, button_border_color, left_btn_rect, 2, border_radius=5)
        left_arrow_color = hover_arrow_color if left_btn_rect.collidepoint(mouse_pos) else default_arrow_color
        arrow_text = arrow_font.render("<<", True, left_arrow_color)
        arrow_rect = arrow_text.get_rect(center=left_btn_rect.center)
        screen.blit(arrow_text, arrow_rect)
    # Do not render left button if not active

    if right_active:
        pygame.draw.rect(screen, button_bg_color, right_btn_rect, border_radius=5)
        pygame.draw.rect(screen, button_border_color, right_btn_rect, 2, border_radius=5)
        right_arrow_color = hover_arrow_color if right_btn_rect.collidepoint(mouse_pos) else default_arrow_color
        arrow_text = arrow_font.render(">>", True, right_arrow_color)
        arrow_rect = arrow_text.get_rect(center=right_btn_rect.center)
        screen.blit(arrow_text, arrow_rect)
    # Do not render right button if not active

    # Initialize detail panel if not already set
    if not hasattr(game_state, "detail_panel"):
        from .depot_view_detail import DepotViewDetail
        game_state.detail_panel = DepotViewDetail(depot_rect, game_state)

    # Prepare scrollable text area inside depot view (reserving 20px for scrollbar)
    scroll_area = pygame.Rect(x, y + 60, width - 35, height -80)
    # Create a temporary surface that is tall enough (estimate: current text section starts at 0)
    content_surface = pygame.Surface((scroll_area.width, 1000), pygame.SRCALPHA)
    content_surface.fill((0,0,0,0))
    content_y = 0
    
    # Determine time frame period in days based on depot_time_frame
    if game_state.depot_time_frame == "Daily":
        period_days = 1
    elif game_state.depot_time_frame == "Weekly":
        period_days = 7
    elif game_state.depot_time_frame == "Monthly":
        period_days = 30
    elif game_state.depot_time_frame == "Yearly":
        period_days = 365
    else:  # "Total"
        period_days = None

    # Calculate wealth statistics based on time frame
    current_wealth = depot.wealth[-1]
    if period_days is not None and len(depot.wealth) > period_days:
        start_wealth = depot.wealth[-(period_days+1)]
        start_income = depot.income_history[-(period_days+1)]
        start_expense = depot.expenditure_history[-(period_days+1)]
    else:
        start_wealth = depot.wealth[0]
        start_income = depot.income_history[0]
        start_expense = depot.expenditure_history[0]
    wealth_change = current_wealth - start_wealth

    # calculate the income for the given period, we need to take the last n days of the income and expenses list and sum them up
    if period_days is not None and len(depot.income_history) > period_days:
        current_income = sum(depot.income_history[-period_days:])
        current_expense = sum(depot.expenditure_history[-period_days:])
    else:
        current_income = sum(depot.income_history)
        current_expense = sum(depot.expenditure_history)

    # Filter trades by time frame for trade action stats
    if period_days is not None:
        delta = datetime.timedelta(days=period_days)
        filtered_trades = [trade for trade in depot.trades if trade["timestamp"] >= game_state.date - delta]
    else:
        filtered_trades = depot.trades
    buy_actions = sum(1 for trade in filtered_trades if trade["type"] == "purchase")
    sell_actions = sum(1 for trade in filtered_trades if trade["type"] == "sale")
    total_actions = len(filtered_trades)
    
    wealth_stats = [
        ("Wealth Today", f"{current_wealth:.2f}"),
        ("Wealth Start", f"{start_wealth:.2f}"),
        ("Income", f"{current_income:.2f}"),
        ("Expenses", f"{current_expense:.2f}"),
        ("Profit", f"{wealth_change:.2f}"),
        ("Profit Margin", f"{(wealth_change/start_wealth*100):.1f}%" if start_wealth > 0 else "0.0%"),
        ("Total Stock", f"{depot.total_stock[-1]}")
    ]
    
    trade_action_stats = [
        ("Buy Actions", f"{buy_actions}"),
        ("Sell Actions", f"{sell_actions}"),
        ("Total Actions", f"{total_actions}")
    ]
    
    # Get trade cycle statistics filtered by time frame
    if period_days is not None:
        delta = datetime.timedelta(days=period_days)
        cycle_stats = depot.get_trade_cycle_stats(game_state.date, delta)
    else:
        cycle_stats = depot.get_trade_cycle_stats(game_state.date, None)
    
    # Convert cycle_stats dictionary to a list for display
    trade_cycle_stats = [
        ("Completed Trades", f"{cycle_stats['total_cycles']}"),
        ("Successful Trades", f"{cycle_stats['successful_cycles']}"),
        ("Success Rate", f"{cycle_stats['success_rate']:.1f}%"),
        ("Total Trade Profit", f"{cycle_stats['total_profit']:.2f}")
    ]

    # Use game_state.depot_scroll_offset if it exists, otherwise default to 0
    scroll_offset = getattr(game_state, "depot_scroll_offset", 0)
    # Ensure offset is within bounds.
    if scroll_offset < 0:
        scroll_offset = 0
    
    # Helper function to draw a row on a given surface at y offset
    def draw_row(surf, y_pos, label, value, label_color=DARK_BROWN, value_color=BLACK):
        #small_font = pygame.font.SysFont("RomanAntique.ttf", 19)
        small_font = game_state.small_font
        
        # Check if this row is currently selected (its detail panel is open)
        is_selected = (hasattr(game_state, "detail_panel") and 
                     game_state.detail_panel.visible and 
                     game_state.detail_panel.current_statistic == label)
        
        # Draw a subtle gray background for the selected row
        if is_selected:
            row_rect = pygame.Rect(10, y_pos-4, surf.get_width()-80, 24)
            row_separator = pygame.Rect(345, y_pos-4, 7, 24)
            pygame.draw.rect(surf, LIGHT_GRAY, row_rect)
            pygame.draw.rect(surf, BEIGE, row_separator)
        
        labels_without_button = ["Wealth Today", "Wealth Start", "Buy Actions", "Sell Actions", "Total Actions"]
        if label in labels_without_button:
            # Create a more visible button instead of just the text
            button_size = 16
            button_rect = pygame.Rect(20, y_pos, button_size, button_size)
            
            # Get mouse position (in content surface coordinates)
            mouse_pos = pygame.mouse.get_pos()
            # Convert mouse position to content surface coordinates
            content_mouse_x = mouse_pos[0] - scroll_area.x
            content_mouse_y = mouse_pos[1] - scroll_area.y + scroll_offset
            
            # Check if mouse is hovering over this button
            button_hover = (20 <= content_mouse_x <= 20 + button_size and 
                           y_pos <= content_mouse_y <= y_pos + button_size)
            
            # Draw button with plus/minus sign
            button_bg_color = SANDY_BROWN if button_hover else TAN
            pygame.draw.rect(surf, button_bg_color, button_rect)
            pygame.draw.rect(surf, DARK_BROWN, button_rect, 1)
            
            # Check if this statistic's detail panel is currently open
            show_minus = is_selected
            
            # Add plus/minus symbol centered in button with hover effect
            button_text = "-" if show_minus else "+"
            text_color = WHITE if button_hover else DARK_BROWN
            plus_surf = small_font.render(button_text, True, text_color)
            plus_rect = plus_surf.get_rect(center=button_rect.center)
            plus_rect.y -= 3  # Shift the text up, the chosen font type is leaning to the bottom
            surf.blit(plus_surf, plus_rect)
            
            # Store all button positions in a dictionary instead of just one
            if not hasattr(game_state, "depot_plus_buttons"):
                game_state.depot_plus_buttons = {}
            
            # Store button position with label as key
            game_state.depot_plus_buttons[label] = (button_rect.x, button_rect.y, button_rect.width, button_rect.height)
        
        label_x = 40  # shift label right to accommodate button
        
        # Use bold effect for selected row
        if is_selected:
            # For bold text, render it twice with a small offset (simulating bold)
            label_surf = small_font.render(label, True, label_color)
            value_surf = small_font.render(value, True, value_color)
            
            # First render (offset by 1 pixel)
            surf.blit(label_surf, (label_x+1, y_pos))
            surf.blit(value_surf, (251, y_pos))
            
            # Second render (original position)
            surf.blit(label_surf, (label_x, y_pos))
            surf.blit(value_surf, (250, y_pos))
        else:
            # Normal rendering for non-selected rows
            label_surf = small_font.render(label, True, label_color)
            value_surf = small_font.render(value, True, value_color)
            surf.blit(label_surf, (label_x, y_pos))
            surf.blit(value_surf, (250, y_pos))
            
        # Draw separator line after specific rows
        if label in ["Total Stock", "Total Actions", "Total Trade Profit", "Total"]:
            separator_y = y_pos + 20  # Position the line 20px below the text
            pygame.draw.line(surf, PALE_BROWN, (20, separator_y), (surf.get_width()-60, separator_y), 1)
    
    # Draw section: Wealth Statistics
    section_title = font.render("Wealth Statistics", True, DARK_BROWN)
    content_surface.blit(section_title, (20, content_y))
    content_y += 30
    for label, value in wealth_stats:
        draw_row(content_surface, content_y, label, value)
        content_y += 24
    
    # Draw section: Trade Actions
    content_y += 15
    section_title = font.render("Trade Actions", True, DARK_BROWN)
    content_surface.blit(section_title, (20, content_y))
    content_y += 30
    for label, value in trade_action_stats:
        draw_row(content_surface, content_y, label, value)
        content_y += 24
    
    # Draw section: Trade Cycles
    content_y += 15
    section_title = font.render("Trade Cycles", True, DARK_BROWN)
    content_surface.blit(section_title, (20, content_y))
    content_y += 30
    for label, value in trade_cycle_stats:
        draw_row(content_surface, content_y, label, value)
        content_y += 24

    # Draw most recent trade if available
    if depot.trades:
        content_y += 15
        last_trade = depot.trades[-1]
        section_title = font.render("Last Trade", True, DARK_BROWN)
        content_surface.blit(section_title, (20, content_y))
        content_y += 30
        
        trade_type = "Purchase" if last_trade["type"] == "purchase" else "Sale"
        trade_color = RED if last_trade["type"] == "purchase" else GREEN
        
        draw_row(content_surface, content_y, "Good", last_trade["good"])
        content_y += 24
        draw_row(content_surface, content_y, "Type", trade_type, value_color=trade_color)
        content_y += 24
        draw_row(content_surface, content_y, "Quantity", str(last_trade["quantity"]))
        content_y += 24
        draw_row(content_surface, content_y, "Price", f"{last_trade['price']:.2f}")
        content_y += 24
        draw_row(content_surface, content_y, "Total", f"{last_trade['total']:.2f}")
        content_y += 24
    
    # Draw section: Best & Worst Goods
    if cycle_stats["best_goods"] or cycle_stats["worst_goods"]:
        content_y += 15
        section_title = font.render("Performance by Good", True, DARK_BROWN)
        content_surface.blit(section_title, (20, content_y))
        content_y += 30
    
    # Draw best goods if available
    if cycle_stats["best_goods"]:
        draw_row(content_surface, content_y, "Best Performing Goods:", "Profit/Unit")
        content_y += 24
        for i, (good_name, profit) in enumerate(cycle_stats["best_goods"][:3]):
            if profit > 0:
                draw_row(content_surface, content_y, f"   {i+1}. {good_name}", f"+{profit:.2f}")
                content_y += 24
    
    # Draw worst goods if available
    if cycle_stats["worst_goods"]:
        content_y += 5
        draw_row(content_surface, content_y, "Worst Performing Goods:", "Profit/Unit")
        content_y += 24
        for i, (good_name, profit) in enumerate(reversed(cycle_stats["worst_goods"][-3:])):
            color = RED if profit < 0 else BLACK
            draw_row(content_surface, content_y, f"   {i+1}. {good_name}", f"{profit:.2f}", value_color=color)
            content_y += 24

    # add a visual closing as the last line to the content
    pygame.draw.line(content_surface, DARK_BROWN, (20, content_y+10), (345, content_y+10), 2)
    content_y += 20

    # Crop the content_surface to the actual content height
    content_surface = content_surface.subsurface(pygame.Rect(0, 0, scroll_area.width, content_y)).copy()
    
    # Update max_offset after content is created
    max_offset = max(0, content_surface.get_height() - scroll_area.height)
    if scroll_offset > max_offset:
        scroll_offset = max_offset
    game_state.depot_scroll_offset = scroll_offset

    # Blit the visible content portion onto the screen
    screen.set_clip(scroll_area)
    screen.blit(content_surface, (scroll_area.x, scroll_area.y), area=pygame.Rect(0, scroll_offset, scroll_area.width, scroll_area.height))
    screen.set_clip(None)
    
    # Draw scrollbar if content is taller than scroll area
    if content_surface.get_height() > scroll_area.height:
        scrollbar_width = 10
        scrollbar_x = scroll_area.right
        scrollbar_rect = pygame.Rect(scrollbar_x, scroll_area.y, scrollbar_width, scroll_area.height)
        pygame.draw.rect(screen, LIGHT_GRAY, scrollbar_rect)  # Track
        
        # thumb height proportional to visible fraction
        thumb_height = max(20, scroll_area.height * scroll_area.height / content_surface.get_height())
        thumb_y = scroll_area.y + (scroll_offset / (content_surface.get_height() - scroll_area.height)) * (scroll_area.height - thumb_height)
        thumb_rect = pygame.Rect(scrollbar_x, thumb_y, scrollbar_width, thumb_height)
        pygame.draw.rect(screen, TAN, thumb_rect)

    # After cropping and calculating scroll offset, convert stored button positions to screen coordinates
    if hasattr(game_state, "depot_plus_buttons"):
        game_state.depot_plus_rects = {}  # Dictionary of clickable rectangles
        for label, (btn_x, btn_y, btn_w, btn_h) in game_state.depot_plus_buttons.items():
            # Only create clickable rect if button is actually visible in current scroll view
            if btn_y >= scroll_offset and btn_y <= scroll_offset + scroll_area.height:
                screen_y = scroll_area.y + (btn_y - scroll_offset)
                screen_x = scroll_area.x + btn_x
                game_state.depot_plus_rects[label] = pygame.Rect(screen_x, screen_y, btn_w, btn_h)

    # For backward compatibility, keep depot_plus_rect but set it to None
    game_state.depot_plus_rect = None

    # Store depot button rectangles for handling clicks externally
    game_state.depot_buttons = {"left": left_btn_rect, "right": right_btn_rect}

    # After all depot rendering, draw the detail panel if toggled visible
    if hasattr(game_state, "detail_panel"):
        if game_state.detail_panel.visible:
            game_state.detail_panel.draw(screen, font)

def draw_stat_row(screen, font, x, y, label, value, label_color=DARK_BROWN, value_color=BLACK):
    """Helper function to draw a row with label and value"""
    label_surf = font.render(label, True, label_color)
    value_surf = font.render(value, True, value_color)
    screen.blit(label_surf, (x + 20, y))
    screen.blit(value_surf, (x + 250, y))
