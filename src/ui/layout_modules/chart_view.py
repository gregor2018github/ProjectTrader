import pygame
import datetime
from typing import List, Dict, Tuple, Any, TYPE_CHECKING
from ...config.colors import *
from ...config.constants import SCREEN_WIDTH, SCREEN_HEIGHT, MODULE_WIDTH, CHART_TIME_MARKER_UNIT

if TYPE_CHECKING:
    from ...models.good import Good

def draw_chart(screen: pygame.Surface, main_font: pygame.font.Font, chart_border_orig: Tuple[int, int], goods: List['Good'], goods_images_30: Dict[str, pygame.Surface], current_date: datetime.datetime, view_rect: pygame.Rect) -> List[pygame.Rect]:
    """Draw the primary price history chart and selection UI.
    
    Args:
        screen: Target surface for rendering.
        main_font: Primary font used for price levels.
        chart_border_orig: Coordinates (x, y) defining the chart's top-left corner relative to screen.
        goods: List of all tradeable goods with history data.
        goods_images_30: mapping of good names to 30x30 icons.
        current_date: Current game simulation date and time.
        view_rect: The rectangle defining the module viewport area on screen.
        
    Returns:
        List[pygame.Rect]: Hitboxes for the good selection buttons.
    """
    # Adjust chart border based on view_rect position
    # The original chart_border[0] is the left margin within the first module.
    chart_border = (view_rect.x + chart_border_orig[0], chart_border_orig[1])

    # Define the chart content width (leaving 42px buffer on right for goods icons)
    chart_content_width = view_rect.width - 42
    
    # Draw the module background
    pygame.draw.rect(screen, BEIGE, view_rect)
    pygame.draw.rect(screen, DARK_BROWN, view_rect, 2)
    
    # Draw the chart content area (with border on right before the buffer)
    chart_area = pygame.Rect(view_rect.x, view_rect.y, chart_content_width, view_rect.height)
    pygame.draw.rect(screen, SANDY_BROWN, chart_area)
    pygame.draw.rect(screen, DARK_BROWN, chart_area, 2)

    # determine max chart size based on chart content width
    # We use chart_border_orig[0] as margin for consistent padding on both sides
    max_chart_size = round((chart_content_width - (chart_border_orig[0] * 2)), 0)
    max_chart_height = screen.get_height() - (chart_border[1] * 2) - 70

    # Draw basic chart structure
    chart_left_bottom = (chart_border[0], chart_border[1])
    select_bar = pygame.Rect(view_rect.x, chart_left_bottom[1] + 15, chart_content_width, 75)
    pygame.draw.rect(screen, PALE_BROWN, select_bar)
    pygame.draw.rect(screen, DARK_BROWN, select_bar, 2)
    pygame.draw.line(screen, CHART_BROWN, (chart_border[0], chart_border[1]), (chart_border[0] + max_chart_size, chart_border[1]), 1)
    pygame.draw.line(screen, CHART_BROWN, (chart_border[0], chart_border[1]), (chart_border[0], chart_border[1] + max_chart_height), 1)

    # Calculate max price using chart history instead of bookkeeping history
    visible_goods = [good for good in goods if good.show_in_charts]
    if not visible_goods:
        return _draw_selection_boxes(screen, goods, select_bar, goods_images_30, main_font)

    max_price = max(max(good.price_history_hourly[-int(max_chart_size):]) for good in visible_goods)
    _draw_price_levels(screen, main_font, chart_border, max_chart_size, max_chart_height, max_price)

    # Draw time markers (vertical lines for day changes)
    history_len = len(visible_goods[0].price_history_hourly[-int(max_chart_size):])
    _draw_time_markers(screen, chart_border, max_chart_size, max_chart_height, current_date, history_len)

    # Store selection boxes for later use with hover effects
    image_boxes = _draw_selection_boxes(screen, goods, select_bar, goods_images_30, main_font)
    
    # Draw charts for each good with hover effects
    _draw_good_charts(screen, goods, chart_border, max_chart_size, max_chart_height, max_price, main_font, goods_images_30)

    # Draw chart hover effects (vertical line and tooltip)
    _draw_chart_hover(screen, chart_border, max_chart_size, max_chart_height, goods, max_price, main_font)

    return image_boxes

def _draw_chart_hover(screen: pygame.Surface, chart_border: Tuple[int, int], max_chart_size: float, max_chart_height: float, goods: List['Good'], max_price: float, main_font: pygame.font.Font) -> None:
    """Draw a vertical hover line and price tooltip when hovering over the chart area.
    
    Args:
        screen: Target surface.
        chart_border: Base coordinates.
        max_chart_size: Chart width.
        max_chart_height: Chart height.
        goods: List of all goods.
        max_price: Price scaling factor.
        main_font: Font for tooltip.
    """
    mouse_pos = pygame.mouse.get_pos()
    
    # Ensure height is handled correctly for collision detection (prices go 'up' from chart_border[1])
    # The chart area vertically is between chart_border[1] and chart_border[1] + max_chart_height
    # Since max_chart_height is negative, we use min/max to find the bounds.
    top_y = min(chart_border[1], chart_border[1] + int(max_chart_height))
    bottom_y = max(chart_border[1], chart_border[1] + int(max_chart_height))
    left_x = chart_border[0]
    right_x = chart_border[0] + int(max_chart_size)
    
    # Check if mouse is within the horizontal and vertical chart boundaries
    if left_x <= mouse_pos[0] <= right_x and top_y <= mouse_pos[1] <= bottom_y:
        # Draw vertical hover line spanning the full height of the chart
        pygame.draw.line(screen, DARK_GRAY, (mouse_pos[0], top_y), (mouse_pos[0], bottom_y), 1)
        
        # Calculate index in price history based on mouse x position relative to start of chart
        idx = int(mouse_pos[0] - left_x)
        
        visible_goods = [good for good in goods if good.show_in_charts]
        if not visible_goods:
            return

        # Find closest good's price at this index
        closest_good = None
        min_dist = float('inf')
        
        for good in visible_goods:
            # Use same slice as used for drawing the lines
            price_history = good.price_history_hourly[-int(max_chart_size):]
            
            if idx < len(price_history):
                # Calculate screen y-coordinate for this good at this index
                # Matches the formula in _draw_good_line
                price_y = chart_border[1] + ((price_history[idx] / max_price) * max_chart_height)
                dist = abs(mouse_pos[1] - price_y)
                
                # Update closest good if this one is nearer to the mouse y position
                if dist < min_dist:
                    min_dist = dist
                    closest_good = (good.name, price_history[idx], good.color)
        
        if closest_good:
            name, price, color = closest_good
            tooltip_text = f"{name}: {price:.2f}"
            
            # Create a stable width by calculating as if all digits were the widest digit (9)
            # This prevents the tooltip box from "jumping" as prices update.
            stable_text = "".join(['9' if c.isdigit() else c for c in tooltip_text])
            stable_width, stable_height = main_font.size(stable_text)
            
            # Render the actual text using a fixed color for readability
            tooltip_surface = main_font.render(tooltip_text, True, DARK_BROWN)
            
            # Create a stable-size rect for the background based on "all 9s" dimensions
            tooltip_base_x = mouse_pos[0] + 15
            tooltip_base_y = mouse_pos[1] - 10
            stable_rect = pygame.Rect(tooltip_base_x, tooltip_base_y, stable_width, stable_height)
            
            # Flip to left if it would go off right edge
            if stable_rect.right > screen.get_width() - 10:
                stable_rect.topright = (mouse_pos[0] - 15, tooltip_base_y)
            
            # Ensure it doesn't go off the top or bottom of the screen
            if stable_rect.top < 0:
                stable_rect.top = 0
            if stable_rect.bottom > screen.get_height():
                stable_rect.bottom = screen.get_height()
            
            # Draw background box with padding using the stable dimensions
            bg_rect = stable_rect.inflate(10, 8)
            pygame.draw.rect(screen, WHITE, bg_rect)
            pygame.draw.rect(screen, DARK_BROWN, bg_rect, 1)
            
            # Draw the text centered within the stable rect
            text_rect = tooltip_surface.get_rect(center=stable_rect.center)
            screen.blit(tooltip_surface, text_rect)

def _draw_time_markers(screen: pygame.Surface, chart_border: Tuple[int, int], max_chart_size: float, max_chart_height: float, current_date: datetime.datetime, history_len: int) -> None:
    """Draw vertical lines representing time boundaries (Day, Week, or Month).
    
    Args:
        screen: Target surface.
        chart_border: Base coordinates.
        max_chart_size: Chart width.
        max_chart_height: Chart height.
        current_date: Current game time.
        history_len: Length of the displayed history.
    """
    current_idx = history_len - 1
    
    if CHART_TIME_MARKER_UNIT == "Day":
        # First marker is at the start of the current day
        first_marker_offset = current_date.hour
        step = 24
        for i in range(current_idx - first_marker_offset, -1, -step):
            if i < max_chart_size:
                x = chart_border[0] + i
                pygame.draw.line(screen, CHART_BROWN, (x, chart_border[1]), (x, chart_border[1] + max_chart_height), 1)
                
    elif CHART_TIME_MARKER_UNIT == "Week":
        # First marker is at the start of the current week (Monday 00:00)
        first_marker_offset = (current_date.weekday() * 24) + current_date.hour
        step = 24 * 7
        for i in range(current_idx - first_marker_offset, -1, -step):
            if i < max_chart_size:
                x = chart_border[0] + i
                pygame.draw.line(screen, CHART_BROWN, (x, chart_border[1]), (x, chart_border[1] + max_chart_height), 1)
                
    elif CHART_TIME_MARKER_UNIT == "Month":
        # Month lengths vary, so we iterate backwards index by index to check for day 1 at hour 0
        # Given the chart width (~600-800 pixels), this is only hundreds of iterations.
        for i in range(current_idx, -1, -1):
            if i >= max_chart_size:
                continue
            
            hours_ago = current_idx - i
            check_date = current_date - datetime.timedelta(hours=hours_ago)
            
            if check_date.day == 1 and check_date.hour == 0:
                x = chart_border[0] + i
                pygame.draw.line(screen, CHART_BROWN, (x, chart_border[1]), (x, chart_border[1] + max_chart_height), 1)

def _draw_price_levels(screen: pygame.Surface, main_font: pygame.font.Font, chart_border: Tuple[int, int], max_chart_size: float, max_chart_height: float, max_price: float) -> None:
    """Draw grid lines and price level labels.
    
    Args:
        screen: Target surface.
        main_font: Font for labels.
        chart_border: Base screen coordinates.
        max_chart_size: Width of the chart drawing area.
        max_chart_height: Height of the chart drawing area.
        max_price: Scaling factor based on highest historical price shown.
    """
    # Start with small increments for lower values (1-5)
    price_levels = [1, 2, 3, 4, 5]
    
    # If max_price is small, don't add higher levels
    if max_price <= 6:
        price_levels = [level for level in price_levels if level <= max_price]
    else:
        # Calculate medium tier steps (increments of 5)
        current_level = 10
        while current_level <= min(max_price, 50):
            price_levels.append(current_level)
            current_level += 5
            
        # For higher values, use larger steps (increments of 10)
        if max_price > 50:
            current_level = 60
            while current_level <= max_price and len(price_levels) < 15:
                price_levels.append(current_level)
                current_level += 10

    # Draw each price level within chart boundaries
    for price_level in price_levels:
        y_ratio = price_level / max_price
        if 0 <= y_ratio <= 1:  # Only draw if within chart boundaries
            y = chart_border[1] + (y_ratio * max_chart_height)
            pygame.draw.line(screen, CHART_BROWN, (chart_border[0], y), 
                            (chart_border[0] + max_chart_size, y), 1)
            price_text = main_font.render(str(price_level), True, CHART_BROWN)
            screen.blit(price_text, (chart_border[0] - 30, y - 10))

def _draw_good_charts(screen: pygame.Surface, goods: List['Good'], chart_border: Tuple[int, int], max_chart_size: float, max_chart_height: float, max_price: float, main_font: pygame.font.Font, goods_images_30: Dict[str, pygame.Surface]) -> None:
    """Render all price lines, prioritizing hovered items on top.
    
    Args:
        screen: Target surface.
        goods: List of goods to draw lines for.
        chart_border: Base coordinates.
        max_chart_size: Area width.
        max_chart_height: Area height.
        max_price: Price scaling factor.
        main_font: Label font.
        goods_images_30: mapping of icons.
    """
    # First, separate goods into regular and hovered
    regular_goods = [good for good in goods if good.show_in_charts and not good.hovered]
    hovered_goods = [good for good in goods if good.show_in_charts and good.hovered]
    
    # Draw non-hovered goods first
    for good in regular_goods:
        _draw_good_line(screen, good, chart_border, max_chart_size, max_chart_height, max_price, main_font, goods_images_30)
    
    # Then draw hovered goods on top
    for good in hovered_goods:
        _draw_good_line(screen, good, chart_border, max_chart_size, max_chart_height, max_price, main_font, goods_images_30)

def _draw_good_line(screen: pygame.Surface, good: 'Good', chart_border: Tuple[int, int], max_chart_size: float, max_chart_height: float, max_price: float, main_font: pygame.font.Font, goods_images_30: Dict[str, pygame.Surface]) -> None:
    """Render a single good's price history line.
    
    Args:
        screen: Target surface.
        good: The good instance being drawn.
        chart_border: Base coordinates.
        max_chart_size: Max pixels to draw.
        max_chart_height: Pixel height corresponding to max_price.
        max_price: Vertical price limit.
        main_font: Price label font.
        goods_images_30: Dictionary of icons.
    """
    # Use chart price history instead of bookkeeping price history
    price_history = good.price_history_hourly[-int(max_chart_size):]
    
    # Use thicker line if good is hovered
    line_thickness = 3 if good.hovered else 1
    
    # Draw price line
    for i in range(len(price_history) - 1):
        y1 = chart_border[1] + ((price_history[i] / max_price) * max_chart_height)
        y2 = chart_border[1] + ((price_history[i + 1] / max_price) * max_chart_height)
        pygame.draw.line(screen, good.color, 
                       (chart_border[0] + i, y1),
                       (chart_border[0] + i + 1, y2), line_thickness)
    
    # Draw current price and quantities with different fonts
    price_text = main_font.render(str(round(price_history[-1], 2)), True, good.color)
    quantity = good.market_quantity
    
    # Use smaller font for quantities
    quantity_font = pygame.font.SysFont("RomanAntique.ttf", 19)
    quantity_text = quantity_font.render(f"V.{str(quantity if quantity < 999 else int(round(quantity/1000, 0)))}" + 
                                  ("" if quantity < 999 else "k"), True, good.color)
    
    text_y = chart_border[1] + ((price_history[-1] / max_price) * max_chart_height)
    screen.blit(price_text, (chart_border[0] + len(price_history) - 1, text_y))
    screen.blit(quantity_text, (chart_border[0] + len(price_history) - 1, text_y + 20))
    
    if good.name in goods_images_30:
        # Make icons larger when hovered
        if good.hovered:
            # Create a larger version of the icon (1.5x size)
            original_image = goods_images_30[good.name]
            enlarged_size = (int(original_image.get_width() * 1.4), 
                           int(original_image.get_height() * 1.4))
            enlarged_image = pygame.transform.scale(original_image, enlarged_size)
            
            # Calculate position adjustments to keep icon centered
            x_offset = (enlarged_size[0] - original_image.get_width()) // 2
            y_offset = (enlarged_size[1] - original_image.get_height()) // 2
            
            # Positioned to stay centered relative to the original position
            screen.blit(enlarged_image, (
                chart_border[0] + len(price_history) + 55 - x_offset,
                text_y + 10 - y_offset
            ))
        else:
            # Normal sized icon for non-hovered goods
            screen.blit(goods_images_30[good.name],
                      (chart_border[0] + len(price_history) + 55, text_y + 10))

def _draw_selection_boxes(screen: pygame.Surface, goods: List['Good'], select_bar: pygame.Rect, goods_images_30: Dict[str, pygame.Surface], main_font: pygame.font.Font) -> List[pygame.Rect]:
    """Draw interactive toggles for individual goods.
    
    Args:
        screen: Target surface.
        goods: List of all goods.
        select_bar: Background area dimensions.
        goods_images_30: mapping of icons.
        main_font: Font for tooltips.
        
    Returns:
        List[pygame.Rect]: Hitboxes for each good toggle.
    """
    image_box_size = 50
    image_box_spacing = 10
    total_width = (image_box_size + image_box_spacing) * len(goods)
    start_x = (select_bar.width - total_width) // 2
    mouse_pos = pygame.mouse.get_pos()
    image_boxes: List[pygame.Rect] = []
    tooltips: List[Tuple[str, Tuple[int, int]]] = []  # Collect tooltip info for later rendering

    for i, good in enumerate(goods):
        box_x = select_bar.left + start_x + (i * (image_box_size + image_box_spacing))
        box_y = select_bar.top + 10
        image_box = pygame.Rect(box_x, box_y, image_box_size, image_box_size)
        image_boxes.append(image_box)

        # Check if the mouse is hovering over this good's box
        is_hovered = image_box.collidepoint(mouse_pos)
        if is_hovered:
            good.hovered = True

        # Determine box color based on state and hover
        if good.show_in_charts:
            color = LIGHT_BROWN if is_hovered else PALE_YELLOW
        else:
            color = DARK_GRAY if is_hovered else GRAY

        pygame.draw.rect(screen, color, image_box)
        pygame.draw.rect(screen, DARK_BROWN, image_box, 2)
        
        if good.name in goods_images_30:
            screen.blit(goods_images_30[good.name], (box_x + 10, box_y + 10))
        
        if is_hovered:
            tooltips.append((good.name, mouse_pos))
    # Render tooltips after all buttons are drawn.
    for name, pos in tooltips:
        tooltip_surface = main_font.render(name, True, BLACK)
        tooltip_rect = tooltip_surface.get_rect(topleft=(pos[0] + 15, pos[1] + 10))
        pygame.draw.rect(screen, WHITE, tooltip_rect.inflate(4, 4))
        pygame.draw.rect(screen, DARK_BROWN, tooltip_rect.inflate(4, 4), 1)
        screen.blit(tooltip_surface, tooltip_rect)
    
    return image_boxes
