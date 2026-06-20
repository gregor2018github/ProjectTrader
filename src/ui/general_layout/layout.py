import pygame
import datetime
from typing import List, Dict, Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ...models.good import Good
    from ...models.depot import Depot
    from ...game_state import GameState

from ...config.colors import *
from ..helper_modules.dropdown import Dropdown
from ...config.constants import SCREEN_WIDTH, SCREEN_HEIGHT, SIDEBAR_WIDTH


def _get_town_for_stats(game_state: "GameState") -> Optional[Any]:
    """Get the town instance used for statistics display."""
    if not hasattr(game_state, 'game') or game_state.game is None:
        return None

    if not hasattr(game_state.game, 'game_map') or game_state.game.game_map is None:
        return None

    houses = getattr(game_state.game.game_map.tmx_map, 'houses', [])
    for house in houses:
        if hasattr(house, 'population_groups') and hasattr(house, 'max_citizens'):
            return house
    return None


def _draw_town_statistics_panel(
    screen: pygame.Surface,
    main_font: pygame.font.Font,
    game_state: "GameState"
) -> Optional[pygame.Rect]:
    """Draw bottom-bar replacement with core town population statistics."""
    town = _get_town_for_stats(game_state)
    if town is None:
        return None

    # Use small font for tooltip to match right-panel tooltips
    small_font = getattr(game_state, "small_font", main_font)

    mouse_pos = pygame.mouse.get_pos()
    menu_is_open = hasattr(game_state, 'game') and hasattr(game_state.game, 'menu') and game_state.game.menu.is_open

    current_population = int(getattr(town, 'citizens', 0))
    maximum_population = int(getattr(town, 'max_citizens', 0))
    happiness = float(getattr(town, 'happiness', 80))
    population_groups = getattr(town, 'population_groups', {})

    panel_padding_x = 20
    panel_y = SCREEN_HEIGHT - 53
    panel_h = 44
    icon_size = panel_h - 10  # 34px

    pop_icon = None
    if hasattr(game_state, 'game') and hasattr(game_state.game, 'images'):
        pop_icon = game_state.game.images.get('pictogram_population')

    count_surf = main_font.render(str(current_population), True, BLACK)
    gap = 6
    content_w = (icon_size + gap if pop_icon else 0) + count_surf.get_width()
    panel_w = content_w + 20  # 10px padding each side
    panel_rect = pygame.Rect(panel_padding_x, panel_y, panel_w, panel_h)

    is_hovered = panel_rect.collidepoint(mouse_pos) and not menu_is_open

    if is_hovered:
        pygame.draw.rect(screen, PALE_BROWN, panel_rect, border_radius=4)

    draw_x = panel_rect.x + 10
    if pop_icon:
        icon_rect = pop_icon.get_rect(midleft=(draw_x, panel_rect.centery))
        screen.blit(pop_icon, icon_rect)
        draw_x = icon_rect.right + gap
    text_rect = count_surf.get_rect(midleft=(draw_x, panel_rect.centery))
    screen.blit(count_surf, text_rect)

    tooltip_text = None
    tooltip_pos = None
    if is_hovered:
        tooltip_text = [
            ("Current:", f"{current_population} Souls"),
            ("Housing Capacity:", f"{maximum_population} Souls"),
            ("Housing Fillgrade:", f"{current_population / maximum_population * 100:.1f} %" if maximum_population else "N/A"),
            ("Happiness:", f"{happiness:.0f} %"),
            ("Poor:", f"{int(population_groups.get('Poor', 0))} Souls"),
            ("Commons:", f"{int(population_groups.get('Commons', 0))} Souls"),
            ("Middling Sort:", f"{int(population_groups.get('Middling Sort', 0))} Souls"),
            ("Nobility:", f"{int(population_groups.get('Nobility', 0))} Souls")
        ]
        tooltip_pos = mouse_pos

    if tooltip_text and tooltip_pos:
        # Pre-render surfaces to calculate dimensions using the smaller font
        line_data = []
        max_label_w = 0
        max_value_w = 0
        line_height = 0
        line_spacing = 6 # Vertical distance between lines
        
        for label, val in tooltip_text:
            label_surf = small_font.render(label, True, BLACK)
            val_surf = small_font.render(val, True, BLACK)
            line_data.append((label, label_surf, val_surf))
            max_label_w = max(max_label_w, label_surf.get_width())
            max_value_w = max(max_value_w, val_surf.get_width())
            line_height = max(line_height, label_surf.get_height())

        padding = 12
        column_gap = 40 # space between columns
        stripe_height = 10 # Extra height for the separator stripe
        
        tooltip_width = max_label_w + max_value_w + column_gap + (padding * 2)
        tooltip_height = (len(tooltip_text) * (line_height + line_spacing)) + (padding * 2) + stripe_height

        tooltip_rect = pygame.Rect(
            tooltip_pos[0] + 14,
            tooltip_pos[1] - tooltip_height - 8,
            tooltip_width,
            tooltip_height
        )

        if tooltip_rect.right > SCREEN_WIDTH:
            tooltip_rect.right = SCREEN_WIDTH - 8
        if tooltip_rect.left < 8:
            tooltip_rect.left = 8
        if tooltip_rect.top < 64:
            tooltip_rect.top = 64

        pygame.draw.rect(screen, WHITE, tooltip_rect)
        pygame.draw.rect(screen, DARK_BROWN, tooltip_rect, 1)

        line_y = tooltip_rect.top + padding
        for label, label_surf, val_surf in line_data:
            # Draw label left-aligned
            screen.blit(label_surf, (tooltip_rect.left + padding, line_y))
            # Draw value right-aligned within its column
            val_x = tooltip_rect.right - padding - val_surf.get_width()
            screen.blit(val_surf, (val_x, line_y))
            
            line_y += line_height + line_spacing

            # Draw a brown stripe under "Happiness"
            if label == "Happiness:":
                stripe_y = line_y - (line_spacing // 2) + 2
                pygame.draw.line(screen, DARK_BROWN, 
                                (tooltip_rect.left + padding, stripe_y), 
                                (tooltip_rect.right - padding, stripe_y), 2)
                line_y += 8 # Add space after the stripe

    return panel_rect

def draw_layout(
    screen: pygame.Surface,
    goods: List["Good"],
    main_depot: "Depot",
    main_font: pygame.font.Font,
    date: datetime.datetime,
    input_fields: Dict[str, str],
    mouse_clicked_on: Optional[str],
    images: Dict[str, Any],
    game_state: "GameState"
) -> Dict[str, pygame.Rect]:
    """Builds layout parts - background, top bar, middle section, and bottom bar.
    
    Each section is drawn by a dedicated helper function. Only right bar is drawn separately.
    """

    _draw_top_bar(screen, main_depot, main_font, date, images, game_state)
    buttons = _draw_bottom_bar(screen, goods, main_font, input_fields, mouse_clicked_on, game_state)
    return buttons

def _draw_background(screen: pygame.Surface) -> None:
    """Draws the lowest level monochrome background color."""

    screen.fill(BEIGE)

def _draw_top_bar(
    screen: pygame.Surface,
    main_depot: "Depot",
    main_font: pygame.font.Font,
    date: datetime.datetime,
    images: Dict[str, Any],
    game_state: "GameState"
) -> None:
    """Draws the top bar with money, date, goods inventory, warehouses, and stock."""

    money_50 = images['money_50']
    goods_images_30 = images['goods_30']
    stock_30 = images['stock_30']
    warehouses_30 = images['warehouses_30']
    
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
    stock_text = main_font.render(f"Total Stock: {total_stock} / {main_depot.storage_capacity}", True, BLACK)
    screen.blit(stock_text, (1365, 35))

def _draw_bottom_bar(
    screen: pygame.Surface,
    goods: List["Good"],
    main_font: pygame.font.Font,
    input_fields: Dict[str, str],
    mouse_clicked_on: Optional[str],
    game_state: "GameState"
) -> Dict[str, pygame.Rect]:
    """Draws the bottom bar with trading buttons.
    
    Time controls and sound controls are drawn separately in their own modules.
    """
    bottom_bar = pygame.Rect(0, SCREEN_HEIGHT-60, SCREEN_WIDTH, 60)
    pygame.draw.rect(screen, LIGHT_GRAY, bottom_bar)
    pygame.draw.rect(screen, DARK_GRAY, bottom_bar, 2)
    
    buttons = {}

    # set the hovered property of all goods to False, the chart gets rendered later and will separately check if some of the chart internal buttons trigger a hover effect
    # for now we will check if the buy or sell buttons trigger a hover effect from this layout script
    for good in goods:
        good.hovered = False

    # Check if trading is allowed - if not in market area, stop here (hiding buttons)
    if hasattr(game_state, 'game') and hasattr(game_state.game, 'player') and not game_state.game.player.in_market_area:
        town_rect = _draw_town_statistics_panel(screen, main_font, game_state)
        if town_rect:
            buttons['town_population'] = town_rect
        return buttons
    
    # Get mouse position for hover effects
    mouse_pos = pygame.mouse.get_pos()
    
    # Check if menu is open - if so, disable all hover effects on other buttons
    menu_is_open = hasattr(game_state, 'game') and hasattr(game_state.game, 'menu') and game_state.game.menu.is_open
    
    def draw_input_field(rect: pygame.Rect, text: str, is_selected: bool) -> None:
        """Helper to draw a text input field with an optional cursor.
        
        Args:
            rect: The rectangular area for the input field.
            text: The current text content.
            is_selected: Whether this field is currently focused.
        """
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
    def is_hovering(rect: pygame.Rect) -> bool:
        """Check if the mouse is currently hovering over the given rect.
        
        Returns False if the menu is open to prevent hover effects on other buttons.
        """
        if menu_is_open:
            return False
        return rect.collidepoint(mouse_pos)
    
    # Draw input fields and buttons for all three trading sections
    sections = [
        ('one', 20, "F1", "F2"),
        ('two', 390, "F3", "F4"),
        ('three', 760, "F5", "F6")
    ]
    
    for section, x_start, buy_key, sell_key in sections:
        good_name = input_fields[f'good_{section}']

        # Skip this slot entirely if no good is assigned to it
        if not good_name:
            continue

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
        paused = game_state.time_level == 1
        if paused:
            buy_color = LIGHT_GRAY
        elif is_hovering(buy_rect):
            buy_color = BUY_BUTTON_HOVER
            good_obj = next((g for g in goods if g.name == good_name), None)
            if good_obj:
                good_obj.hovered = True
        else:
            buy_color = BUY_BUTTON

        pygame.draw.rect(screen, buy_color, buy_rect)
        pygame.draw.rect(screen, GRAY if paused else BUY_BUTTON_BORDER, buy_rect, 2)

        # Draw sell button
        if paused:
            sell_color = LIGHT_GRAY
        elif is_hovering(sell_rect):
            sell_color = SELL_BUTTON_HOVER
            good_obj = next((g for g in goods if g.name == good_name), None)
            if good_obj:
                good_obj.hovered = True
        else:
            sell_color = SELL_BUTTON

        pygame.draw.rect(screen, sell_color, sell_rect)
        pygame.draw.rect(screen, GRAY if paused else SELL_BUTTON_BORDER, sell_rect, 2)

        # Draw click animation overlay on buy and sell buttons if active
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
        good_text = main_font.render(f"Good: {good_name}", True, BLACK)
        qty_label = main_font.render("Quantity: ", True, BLACK)
        qty_value = main_font.render(input_fields[f'quantity_{section}'], True, BLACK)
        buy_text = main_font.render(f"Buy ({buy_key})", True, BUTTON_TEXT)
        sell_text = main_font.render(f"Sell ({sell_key})", True, BUTTON_TEXT)

        screen.blit(good_text, (good_rect.x + 10, good_rect.y + 5))
        screen.blit(qty_label, (qty_rect.x + 10, qty_rect.y + 5))
        screen.blit(qty_value, (qty_rect.x + 10 + qty_label.get_width(), qty_rect.y + 5))
        screen.blit(buy_text, (buy_rect.centerx - buy_text.get_width()//2, buy_rect.centery - buy_text.get_height()//2))
        screen.blit(sell_text, (sell_rect.centerx - sell_text.get_width()//2, sell_rect.centery - sell_text.get_height()//2))

    return buttons

def draw_right_bar(screen: pygame.Surface, images: Dict[str, Any], buttons: Dict[str, pygame.Rect], main_font: pygame.font.Font, game_state: "GameState") -> None:
    """Draws the right sidebar for menu options with pictogram buttons and sub-buttons.
    
    The menu button is drawn separately in the menu module.
    
    Args:
        screen: The pygame surface to draw on.
        images: Dictionary of pre-loaded pictogram images.
        buttons: Dictionary to store the clickable button rects.
        main_font: Font for tooltip rendering.
        game_state: The current game state object.
    """
    right_bar = pygame.Rect(SCREEN_WIDTH, 0, SIDEBAR_WIDTH, SCREEN_HEIGHT)
    pygame.draw.rect(screen, LIGHT_GRAY, right_bar)
    pygame.draw.rect(screen, DARK_GRAY, right_bar, 1)

    # Get mouse position for hover effects
    mouse_pos = pygame.mouse.get_pos()
    
    # Check if menu is open - if so, disable all hover effects on other buttons
    menu_is_open = hasattr(game_state, 'game') and hasattr(game_state.game, 'menu') and game_state.game.menu.is_open
    
    tooltips = []

    # Draw pictograms for side menu
    pictogram_names = ["map", "market", "depot", "politics", "trade_routes", "building"]
    label_map = {
        "map": "Map",
        "market": "Market",
        "depot": "Depot",
        "politics": "Politics",
        "trade_routes": "Trade Routes",
        "building": "Building"
    }

    start_y = 75    # the higher the number the lower the first button
    spacing = -15   # the higher the number (also pos), the further apart the buttons
    
    for i, name in enumerate(pictogram_names):
        img_key = f"pictogram_{name}"
        if img_key in images:
            img = images[img_key]
            # Sidebar button rect (100x100)
            rect = pygame.Rect(SCREEN_WIDTH + 5, start_y + i * (100 + spacing), 100, 100)
            # the actual visible rect of the pictogram is only 100 x 50, that is visible rect
            visible_rect = pygame.Rect(rect.x, rect.y, 100, 50)
            
            # Sub-buttons logic
            sub_btn_y = rect.bottom - 100 + 45 
            sub_btn_width = 47
            sub_btn_height = 20
            
            # Left button "picto_<name>_left"
            left_btn_rect = pygame.Rect(rect.left+2, sub_btn_y, sub_btn_width, sub_btn_height)
            is_left_hovered = left_btn_rect.collidepoint(mouse_pos) and not menu_is_open
            color_left = PALE_BROWN if is_left_hovered else TAN
            pygame.draw.rect(screen, color_left, left_btn_rect)
            pygame.draw.rect(screen, DARK_BROWN, left_btn_rect, 1) # 1px border
            buttons[f"picto_{name}_left"] = left_btn_rect
            if is_left_hovered:
                tooltips.append(("Open left", mouse_pos))
            
            # Right button "picto_<name>_right"
            right_btn_rect = pygame.Rect(rect.right-2 - sub_btn_width, sub_btn_y, sub_btn_width, sub_btn_height)
            is_right_hovered = right_btn_rect.collidepoint(mouse_pos) and not menu_is_open
            color_right = PALE_BROWN if is_right_hovered else TAN
            pygame.draw.rect(screen, color_right, right_btn_rect)
            pygame.draw.rect(screen, DARK_BROWN, right_btn_rect, 1) # 1px border
            buttons[f"picto_{name}_right"] = right_btn_rect
            if is_right_hovered:
                tooltips.append(("Open right", mouse_pos))
            
            # Draw main pictogram image after left and right buttons so it overlaps the buttons by 2 pixels
            screen.blit(img, rect)
            buttons[f"pictogram_{name}"] = visible_rect

            # Main pictogram hover effect
            is_pictogram_hovered = visible_rect.collidepoint(mouse_pos) and not is_left_hovered and not is_right_hovered and not menu_is_open
            if is_pictogram_hovered:
                # redraw pictogram a bit darker to indicate hover
                overlay = pygame.Surface((visible_rect.width, visible_rect.height), pygame.SRCALPHA)
                overlay.fill((0, 0, 0, 50))  # black overlay
                screen.blit(overlay, visible_rect.topleft)
                # add tooltip
                tooltips.append((label_map[name], mouse_pos))

    # Render tooltips last to ensure they are on top of everything
    for text, pos in tooltips:
        tooltip_surf = main_font.render(text, True, BLACK)
        # Position tooltip to the left of the side bar
        tooltip_rect = tooltip_surf.get_rect(topright=(pos[0] - 20, pos[1] + 10))
        
        # Ensure tooltip stays on screen
        if tooltip_rect.left < 0:
            tooltip_rect.left = 10
            
        pygame.draw.rect(screen, WHITE, tooltip_rect.inflate(10, 6))
        pygame.draw.rect(screen, DARK_BROWN, tooltip_rect.inflate(10, 6), 1)
        screen.blit(tooltip_surf, tooltip_rect)
