import pygame
import datetime
from typing import List, Dict, Tuple, Any, TYPE_CHECKING, Optional
from ...config.colors import *

if TYPE_CHECKING:
    from ...models.depot import Depot
    from ...game_state import GameState

def draw_depot_chart(screen: pygame.Surface, rect: pygame.Rect, font: pygame.font.Font, depot: 'Depot', game_state: 'GameState') -> None:
    """Draws the depot chart view with wealth, money, stock, and house statistics.
    
    Args:
        screen: The pygame surface to draw on.
        rect: The area where the chart should be drawn.
        font: Font for labels and text.
        depot: The player's depot model containing history data.
        game_state: Current game state.
    """
    # 1. Draw Background
    pygame.draw.rect(screen, BEIGE, rect)
    pygame.draw.rect(screen, DARK_BROWN, rect, 2)
    
    # 2. Define Layout Areas
    # Chart Area: Top part, buttons at bottom
    button_height = 40
    button_margin = 10
    
    chart_rect = pygame.Rect(
        rect.x + 20, 
        rect.y + 20, 
        rect.width - 40, 
        rect.height - button_height - 30
    )
    
    buttons_area_y = rect.bottom - button_height - 15
    
    # Draw chart background
    pygame.draw.rect(screen, SANDY_BROWN, chart_rect)
    pygame.draw.rect(screen, DARK_BROWN, chart_rect, 2)
    
    # 3. Get Data based on active selection
    active_chart = game_state.depot_active_chart
    data_points = []
    color = BLACK
    label = active_chart
    
    if active_chart == "Wealth":
        data_points = depot.wealth
        color = DARK_GREEN
    elif active_chart == "Money":
        data_points = depot.money_history
        color = GOLD
    elif active_chart == "Stock":
        data_points = depot.total_stock
        color = DARK_BLUE
    elif active_chart == "Houses":
        data_points = depot.house_history
        color = DARK_RED
        
    # 4. Draw Chart
    if len(data_points) > 1:
        # Determine scaling
        # We show a maximum of X points, similar to market chart, or adjust to fit
        # For now, let's limit to the last N points that fit (e.g., width of chart)
        max_points = chart_rect.width
        visible_data = data_points[-int(max_points):]
        
        if not visible_data:
            visible_data = [0]
            
        min_val = min(visible_data)
        max_val = max(visible_data)
        
        # Add some padding to Y-axis
        range_val = max_val - min_val
        if range_val == 0:
            range_val = 1 if max_val == 0 else max_val * 0.1
            
        y_min_scale = min_val - (range_val * 0.1)
        y_max_scale = max_val + (range_val * 0.1)
        
        if y_min_scale < 0 and min_val >= 0: y_min_scale = 0 # Don't go below 0 for positive data
        
        y_range = y_max_scale - y_min_scale
        
        # Calculate points
        points = []
        margin = 2  # Padding to stay clearly inside the chart border
        inner_width = chart_rect.width - (margin * 2)
        inner_height = chart_rect.height - (margin * 2)
        point_width = inner_width / max(1, len(visible_data) - 1)
        
        for i, val in enumerate(visible_data):
            x = chart_rect.left + margin + (i * point_width)
            # Y is inverted (top is 0)
            if y_range != 0:
                normalized_val = (val - y_min_scale) / y_range
                y = (chart_rect.bottom - margin) - (normalized_val * inner_height)
            else:
                y = chart_rect.bottom - margin - (0.5 * inner_height)
            points.append((x, y))
            
        # Draw lines
        if len(points) > 1:
            pygame.draw.lines(screen, color, False, points, 2)

        # Draw horizontal orientation lines
        # Determine a nice step size based on max value
        if max_val < 10:
            step = 2
        elif max_val < 50:
            step = 10
        elif max_val < 200:
            step = 50
        elif max_val < 1000:
            step = 100
        elif max_val < 5000:
            step = 500
        else:
            step = 1000

        # Draw lines at step increments
        # Start at the first multiple of step >= y_min_scale
        start_line = (int(y_min_scale // step) + 1) * step
        current_line = start_line
        
        while current_line < y_max_scale:
            # Calculate Y position
            normalized_y = (current_line - y_min_scale) / y_range
            line_y = chart_rect.bottom - margin - (normalized_y * inner_height)
            
            # Draw line - fix right side reaching 2 pixels too much
            pygame.draw.line(screen, CHART_BROWN, (chart_rect.left, line_y), (chart_rect.right - 2, line_y), 1)
            
            # Draw label
            line_label = font.render(f"{int(current_line):,}", True, CHART_BROWN)
            screen.blit(line_label, (chart_rect.left + 5, line_y - 12))
            
            current_line += step
            
        # Draw min/max labels
        max_label = font.render(f"{max_val:,.1f}", True, DARK_BROWN)
        min_label = font.render(f"{min_val:,.1f}", True, DARK_BROWN)
        
        screen.blit(max_label, (chart_rect.left + 5, chart_rect.top + 5))
        screen.blit(min_label, (chart_rect.left + 5, chart_rect.bottom - 25))
        
        # Draw Title
        title_surf = font.render(f"{label} History", True, DARK_BROWN)
        title_rect = title_surf.get_rect(midtop=(chart_rect.centerx, chart_rect.top + 10))
        # Draw background for title to make it readable
        bg_rect = title_rect.inflate(10, 4)
        pygame.draw.rect(screen, (255, 255, 255, 180), bg_rect)
        screen.blit(title_surf, title_rect)

    else:
        # Not enough data
        text = font.render("Not enough data yet", True, DARK_BROWN)
        text_rect = text.get_rect(center=chart_rect.center)
        screen.blit(text, text_rect)

    # 5. Draw Buttons
    button_labels = ["Wealth", "Money", "Stock", "Houses"]
    btn_width = (chart_rect.width - (button_margin * (len(button_labels) - 1))) / len(button_labels)
    
    current_x = chart_rect.left
    
    for label in button_labels:
        btn_rect = pygame.Rect(current_x, buttons_area_y, btn_width, button_height)
        
        # Store rect in game_state for click handling
        game_state.depot_chart_buttons[label] = btn_rect
        
        # Determine stats
        is_active = (label == active_chart)
        is_hovered = btn_rect.collidepoint(pygame.mouse.get_pos())
        
        # Colors
        if is_active:
            bg_color = PALE_BROWN
            border_color = BLACK
            text_color = BLACK
        elif is_hovered:
            bg_color = WHEAT
            border_color = DARK_BROWN
            text_color = DARK_BROWN
        else:
            bg_color = TAN
            border_color = DARK_BROWN
            text_color = DARK_BROWN
            
        # Draw button
        pygame.draw.rect(screen, bg_color, btn_rect)
        pygame.draw.rect(screen, border_color, btn_rect, 2)
        
        # Text
        text_surf = font.render(label, True, text_color)
        text_rect = text_surf.get_rect(center=btn_rect.center)
        screen.blit(text_surf, text_rect)
        
        current_x += btn_width + button_margin
