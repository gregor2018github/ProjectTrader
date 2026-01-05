import pygame
from ..config.colors import *
from .dropdown import Dropdown
from ..config.constants import SCREEN_WIDTH, SCREEN_HEIGHT, SIDEBAR_WIDTH

def draw_layout(screen, goods, main_depot, main_font, date, input_fields, mouse_clicked_on, money_50, goods_images_30, stock_30, warehouses_30, game_state):
    _draw_background(screen)
    _draw_top_bar(screen, main_depot, main_font, date, money_50, goods_images_30, stock_30, warehouses_30, game_state)
    _draw_middle_section(screen)
    buttons = _draw_bottom_bar(screen, goods, main_font, input_fields, mouse_clicked_on, game_state)
    _draw_right_bar(screen)
    return buttons

def _draw_background(screen):
    screen.fill(BEIGE)

def _draw_top_bar(screen, main_depot, main_font, date, money_50, goods_images_30, stock_30, warehouses_30, game_state):
    top_bar = pygame.Rect(0, 0, SCREEN_WIDTH, 60)
    pygame.draw.rect(screen, LIGHT_GRAY, top_bar)
    pygame.draw.rect(screen, DARK_GRAY, top_bar, 2)
    
    # Money display with glow effect if active
    money_color = game_state.money_effect_color if hasattr(game_state, "money_effect_color") and game_state.money_effect_color else BLACK
    money_text = main_font.render(f"Money: {round(main_depot.money, 2)}", True, money_color)
    screen.blit(money_text, (70, 10))
    screen.blit(money_50, (10, 5))
    
    # Date display
    date_text = main_font.render(date.strftime("%d.%m.%Y | %H o'clock"), True, DARK_BROWN)
    screen.blit(date_text, (70, 35))

    # Separator bar
    pygame.draw.line(screen, DARK_GRAY, (306, 5), (306, 55), 2)
    
    # Goods inventory display
    start_x = 360
    spacing = 160
    
    # Upper row goods
    upper_goods = ["Wood", "Wool", "Wheat", "Hide", "Beer", "Meat"]
    for i, good_name in enumerate(upper_goods):
        text = main_font.render(f"{good_name}: {round(main_depot.good_stock[good_name], 2)}", True, BLACK)
        screen.blit(text, (start_x + (i * spacing), 10))
        screen.blit(goods_images_30[good_name], (start_x + (i * spacing) - 35, 0))
    
    # Lower row goods
    lower_goods = ["Stone", "Iron", "Fish", "Wine", "Linen", "Pottery"]
    for i, good_name in enumerate(lower_goods):
        text = main_font.render(f"{good_name}: {round(main_depot.good_stock[good_name], 2)}", True, BLACK)
        screen.blit(text, (start_x + (i * spacing), 35))
        screen.blit(goods_images_30[good_name], (start_x + (i * spacing) - 35, 29))

    # Separator bar
    pygame.draw.line(screen, DARK_GRAY, (1310, 5), (1310, 55), 2)
    
    # Warehouses counter
    screen.blit(warehouses_30, (1330, 5))
    warehouses_text = main_font.render(f"Warehouses: {main_depot.warehouse_count}", True, BLACK)
    screen.blit(warehouses_text, (1365, 10))
    
    # Total Stock counter
    screen.blit(stock_30, (1330, 30))
    total_stock = sum(main_depot.good_stock.values())
    stock_text = main_font.render(f"Total Stock: {total_stock}", True, BLACK)
    screen.blit(stock_text, (1365, 35))

def _draw_middle_section(screen):
    left_middle = pygame.Rect(0, 60, int(SCREEN_WIDTH/2), SCREEN_HEIGHT-60)
    pygame.draw.rect(screen, SANDY_BROWN, left_middle)
    pygame.draw.rect(screen, DARK_BROWN, left_middle, 2)

def _draw_bottom_bar(screen, goods, main_font, input_fields, mouse_clicked_on, game_state):
    bottom_bar = pygame.Rect(0, SCREEN_HEIGHT-60, SCREEN_WIDTH, 60)
    pygame.draw.rect(screen, LIGHT_GRAY, bottom_bar)
    pygame.draw.rect(screen, DARK_GRAY, bottom_bar, 2)
    
    buttons = {}

    # set the hovered property of all goods to False, the chart gets rendered later and will separately check if some of the chart internal buttons trigger a hover effect
    # for now we will check if the buy or sell buttons trigger a hover effect from this layout script
    for good in goods:
        good.hovered = False
    
    # Get mouse position for hover effects
    mouse_pos = pygame.mouse.get_pos()
    
    def draw_input_field(rect, text, is_selected):
        pygame.draw.rect(screen, WHITE, rect)
        pygame.draw.rect(screen, DARK_BROWN, rect, 2)
        
        # Only draw the cursor if field is selected
        if is_selected and game_state.cursor_visible:
            # Calculate cursor position based on text width up to cursor
            prefix = "Quantity: " + text[:game_state.cursor_position]
            text_width = main_font.size(prefix)[0]
            cursor_x = rect.x + text_width + 7
            pygame.draw.line(screen, BLACK,
                           (cursor_x+4, rect.y + 5),
                           (cursor_x+4, rect.y + rect.height - 5),
                           2)
    
    # Helper function to check if mouse is hovering over a rect
    def is_hovering(rect):
        return rect.collidepoint(mouse_pos)
    
    # Draw input fields and buttons for all three trading sections
    sections = [
        ('one', 20, "F1", "F2"),
        ('two', 390, "F3", "F4"),
        ('three', 760, "F5", "F6")
    ]
    
    for section, x_start, buy_key, sell_key in sections:
        good_rect = pygame.Rect(x_start, SCREEN_HEIGHT - 56, 150, 25)
        qty_rect = pygame.Rect(x_start, SCREEN_HEIGHT - 29, 150, 25)
        buy_rect = pygame.Rect(x_start + 170, SCREEN_HEIGHT - 45, 80, 30)
        sell_rect = pygame.Rect(x_start + 270, SCREEN_HEIGHT - 45, 80, 30)
        
        # Store button rectangles
        buttons[f'good_{section}'] = good_rect
        buttons[f'quantity_{section}'] = qty_rect
        buttons[f'buy_{section}'] = buy_rect
        buttons[f'sell_{section}'] = sell_rect
        
        # Create dropdown if it doesn't exist (but don't draw it)
        if f'dropdown_{section}' not in game_state.dropdowns:
            game_state.dropdowns[f'dropdown_{section}'] = Dropdown(
                x_start, SCREEN_HEIGHT - 56, 150, 25,
                game_state.available_goods, main_font
            )
        
        # Draw input fields and buttons (but not dropdowns)
        # Apply hover effect to good selection dropdown buttons
        good_bg_color = DROPDOWN_HOVER if is_hovering(good_rect) else WHITE
        pygame.draw.rect(screen, good_bg_color, good_rect)
        pygame.draw.rect(screen, DARK_BROWN, good_rect, 2)
        
        draw_input_field(qty_rect, input_fields[f'quantity_{section}'],
                        mouse_clicked_on == f'quantity_{section}')
                        
        # Draw buy button 
        if is_hovering(buy_rect):
            # if hovered, change color of the button 
            buy_color = BUY_BUTTON_HOVER
            # also set the "hovered" property of the good that is linked to the button to True 
            # find the right good object from the list of goods
            good_name = input_fields[f'good_{section}']
            good = next(good for good in goods if good.name == good_name)
            good.hovered = True

        else:
            buy_color = BUY_BUTTON


        pygame.draw.rect(screen, buy_color, buy_rect)
        pygame.draw.rect(screen, BUY_BUTTON_BORDER, buy_rect, 2)
        
        # Draw sell button
        if is_hovering(sell_rect):
            # if hovered, change color of the button 
            sell_color = SELL_BUTTON_HOVER
            # also set the "hovered" property of the good that is linked to the button to True 
            # find the right good object from the list of goods
            good_name = input_fields[f'good_{section}']
            good = next(good for good in goods if good.name == good_name)
            good.hovered = True
        else:
            sell_color = SELL_BUTTON

        pygame.draw.rect(screen, sell_color, sell_rect)
        pygame.draw.rect(screen, SELL_BUTTON_BORDER, sell_rect, 2)
        
        # NEW: Draw click animation overlay on buy and sell buttons if active
        effect = game_state.button_click_effects.get(f'buy_{section}', 0)
        if effect:
            effect_surf = pygame.Surface((buy_rect.width, buy_rect.height), pygame.SRCALPHA)
            effect_surf.fill((0, 0, 0, 100))
            screen.blit(effect_surf, (buy_rect.x, buy_rect.y))
        effect = game_state.button_click_effects.get(f'sell_{section}', 0)
        if effect:
            effect_surf = pygame.Surface((sell_rect.width, sell_rect.height), pygame.SRCALPHA)
            effect_surf.fill((0, 0, 0, 100))
            screen.blit(effect_surf, (sell_rect.x, sell_rect.y))
        
        # Draw small triangle to indicate dropdown - make it darker on hover
        triangle_color = DARK_GRAY if not is_hovering(good_rect) else BLACK
        pygame.draw.polygon(screen, triangle_color, [
            (good_rect.right - 20, good_rect.centery - 5),
            (good_rect.right - 10, good_rect.centery - 5),
            (good_rect.right - 15, good_rect.centery + 5)
        ])
        
        # Draw text
        good_text = main_font.render(f"Good: {input_fields[f'good_{section}']}", True, BLACK)
        # Separate label from value for quantity
        qty_label = main_font.render("Quantity: ", True, BLACK)
        qty_value = main_font.render(input_fields[f'quantity_{section}'], True, BLACK)
        buy_text = main_font.render(f"Buy ({buy_key})", True, BUTTON_TEXT)  # Changed text color for better contrast
        sell_text = main_font.render(f"Sell ({sell_key})", True, BUTTON_TEXT)  # Changed text color for better contrast
        
        screen.blit(good_text, (good_rect.x + 10, good_rect.y + 5))
        # Draw quantity label and value
        screen.blit(qty_label, (qty_rect.x + 10, qty_rect.y + 5))
        screen.blit(qty_value, (qty_rect.x + 10 + qty_label.get_width(), qty_rect.y + 5))
        screen.blit(buy_text, (buy_rect.centerx - buy_text.get_width()//2, buy_rect.centery - buy_text.get_height()//2))
        screen.blit(sell_text, (sell_rect.centerx - sell_text.get_width()//2, sell_rect.centery - sell_text.get_height()//2))
        
    return buttons

def _draw_right_bar(screen):
    right_bar = pygame.Rect(SCREEN_WIDTH, 0, SIDEBAR_WIDTH, SCREEN_HEIGHT)
    pygame.draw.rect(screen, LIGHT_GRAY, right_bar)
    pygame.draw.rect(screen, DARK_GRAY, right_bar, 1)
