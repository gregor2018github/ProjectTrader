import pygame
from ..config.colors import *
from .dropdown import Dropdown

def draw_layout(screen, goods, main_depot, main_font, date, input_fields, mouse_clicked_on, money_50, goods_images_30, game_state):
    _draw_background(screen)
    _draw_top_bar(screen, main_depot, main_font, date, money_50, goods_images_30)
    _draw_middle_section(screen)
    buttons = _draw_bottom_bar(screen, main_font, input_fields, mouse_clicked_on, game_state)
    return buttons

def _draw_background(screen):
    screen.fill(BEIGE)

def _draw_top_bar(screen, main_depot, main_font, date, money_50, goods_images_30):
    top_bar = pygame.Rect(0, 0, screen.get_width(), 60)
    pygame.draw.rect(screen, LIGHT_GRAY, top_bar)
    pygame.draw.rect(screen, DARK_GRAY, top_bar, 2)
    
    # Money display
    money_text = main_font.render(f"Money: {round(main_depot.money, 2)}", True, BLACK)
    screen.blit(money_text, (70, 10))
    screen.blit(money_50, (10, 5))
    
    # Date display
    date_text = main_font.render(date.strftime("%d.%m.%Y | %H o'clock"), True, DARK_BROWN)
    screen.blit(date_text, (70, 35))
    
    # Goods inventory display
    start_x = 310
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

def _draw_middle_section(screen):
    left_middle = pygame.Rect(0, 60, int(screen.get_width()/2), screen.get_height()-60)
    pygame.draw.rect(screen, SANDY_BROWN, left_middle)
    pygame.draw.rect(screen, DARK_BROWN, left_middle, 2)

def _draw_bottom_bar(screen, main_font, input_fields, mouse_clicked_on, game_state):
    bottom_bar = pygame.Rect(0, screen.get_height()-60, screen.get_width(), 60)
    pygame.draw.rect(screen, LIGHT_GRAY, bottom_bar)
    pygame.draw.rect(screen, DARK_GRAY, bottom_bar, 2)
    
    buttons = {}
    
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
    
    # Draw input fields and buttons for all three trading sections
    sections = [
        ('one', 20, "F1", "F2"),
        ('two', 390, "F3", "F4"),
        ('three', 760, "F5", "F6")
    ]
    
    for section, x_start, buy_key, sell_key in sections:
        good_rect = pygame.Rect(x_start, screen.get_height() - 56, 150, 25)
        qty_rect = pygame.Rect(x_start, screen.get_height() - 29, 150, 25)
        buy_rect = pygame.Rect(x_start + 170, screen.get_height() - 45, 80, 30)
        sell_rect = pygame.Rect(x_start + 270, screen.get_height() - 45, 80, 30)
        
        # Store button rectangles
        buttons[f'good_{section}'] = good_rect
        buttons[f'quantity_{section}'] = qty_rect
        buttons[f'buy_{section}'] = buy_rect
        buttons[f'sell_{section}'] = sell_rect
        
        # Create dropdown if it doesn't exist (but don't draw it)
        if f'dropdown_{section}' not in game_state.dropdowns:
            game_state.dropdowns[f'dropdown_{section}'] = Dropdown(
                x_start, screen.get_height() - 56, 150, 25,
                game_state.available_goods, main_font
            )
        
        # Draw input fields and buttons (but not dropdowns)
        pygame.draw.rect(screen, WHITE, good_rect)
        pygame.draw.rect(screen, BLACK, good_rect, 2)  # Change from default to BLACK for more emphasis
        draw_input_field(qty_rect, input_fields[f'quantity_{section}'],
                        mouse_clicked_on == f'quantity_{section}')
                        
        # Replace simple green and red with our new button colors
        # Draw Buy button with nicer styling
        pygame.draw.rect(screen, BUY_BUTTON, buy_rect)
        pygame.draw.rect(screen, BUY_BUTTON_BORDER, buy_rect, 2)
        
        # Draw Sell button with nicer styling
        pygame.draw.rect(screen, SELL_BUTTON, sell_rect)
        pygame.draw.rect(screen, SELL_BUTTON_BORDER, sell_rect, 2)
        
        # Draw small triangle to indicate dropdown
        pygame.draw.polygon(screen, DARK_GRAY, [
            (good_rect.right - 20, good_rect.centery - 5),
            (good_rect.right - 10, good_rect.centery - 5),
            (good_rect.right - 15, good_rect.centery + 5)
        ])
        
        # Draw text
        good_text = main_font.render(f"Good: {input_fields[f'good_{section}']}", True, BLACK)
        # Separate label from value for quantity
        qty_label = main_font.render("Quantity: ", True, BLACK)
        qty_value = main_font.render(input_fields[f'quantity_{section}'], True, BLACK)
        
        # Use white text color for better contrast on colored buttons
        buy_text = main_font.render(f"Buy ({buy_key})", True, BUTTON_TEXT)
        sell_text = main_font.render(f"Sell ({sell_key})", True, BUTTON_TEXT)
        
        screen.blit(good_text, (good_rect.x + 10, good_rect.y + 5))
        # Draw quantity label and value
        screen.blit(qty_label, (qty_rect.x + 10, qty_rect.y + 5))
        screen.blit(qty_value, (qty_rect.x + 10 + qty_label.get_width(), qty_rect.y + 5))
        screen.blit(buy_text, (buy_rect.centerx - buy_text.get_width()//2, buy_rect.centery - buy_text.get_height()//2))
        screen.blit(sell_text, (sell_rect.centerx - sell_text.get_width()//2, sell_rect.centery - sell_text.get_height()//2))
        
    return buttons