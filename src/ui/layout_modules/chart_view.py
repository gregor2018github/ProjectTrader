import pygame
import datetime
from typing import List, Dict, Tuple, Any, TYPE_CHECKING, Optional
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
    
    # Check for proximity hover on the chart itself
    closest_good, hover_idx = _get_closest_good_at_mouse(pygame.mouse.get_pos(), chart_border, max_chart_size, max_chart_height, goods, max_price)
    if closest_good:
        closest_good.hovered = True

    # Draw charts for each good with hover effects
    _draw_good_charts(screen, goods, chart_border, max_chart_size, max_chart_height, max_price, main_font, goods_images_30)

    # Draw chart hover effects (vertical line and tooltip)
    _draw_chart_hover(screen, chart_border, max_chart_size, max_chart_height, goods, max_price, main_font, current_date, closest_good, hover_idx)

    return image_boxes

def _get_closest_good_at_mouse(mouse_pos: Tuple[int, int], chart_border: Tuple[int, int], max_chart_size: float, max_chart_height: float, goods: List['Good'], max_price: float) -> Tuple[Optional['Good'], Optional[int]]:
    """Determine which good is closest to the mouse within the chart area.
    
    Args:
        mouse_pos: Current mouse coordinates.
        chart_border: Base chart coordinates.
        max_chart_size: Chart width.
        max_chart_height: Chart height.
        goods: List of all goods.
        max_price: Price scaling factor.
        
    Returns:
        Tuple containing the closest Good object and the history index, or (None, None).
    """
    # Boundary check for chart area
    top_y = min(chart_border[1], chart_border[1] + int(max_chart_height))
    bottom_y = max(chart_border[1], chart_border[1] + int(max_chart_height))
    left_x = chart_border[0]
    right_x = chart_border[0] + int(max_chart_size)
    
    if not (left_x <= mouse_pos[0] <= right_x and top_y <= mouse_pos[1] <= bottom_y):
        return None, None
        
    idx = int(mouse_pos[0] - left_x)
    visible_goods = [good for good in goods if good.show_in_charts]
    if not visible_goods:
        return None, None

    closest_good = None
    min_dist = float('inf')
    
    for good in visible_goods:
        price_history = good.price_history_hourly[-int(max_chart_size):]
        if idx < len(price_history):
            # Calculate screen y-coordinate for this good at this index
            price_y = chart_border[1] + ((price_history[idx] / max_price) * max_chart_height)
            dist = abs(mouse_pos[1] - price_y)
            
            if dist < min_dist:
                min_dist = dist
                closest_good = good
                
    return closest_good, idx

def _draw_chart_hover(screen: pygame.Surface, chart_border: Tuple[int, int], max_chart_size: float, max_chart_height: float, goods: List['Good'], max_price: float, main_font: pygame.font.Font, current_date: datetime.datetime, closest_good: Optional['Good'] = None, idx: Optional[int] = None) -> None:
    """Draw a vertical hover line and price tooltip when hovering over the chart area.
    
    Args:
        screen: Target surface.
        chart_border: Base coordinates.
        max_chart_size: Chart width.
        max_chart_height: Chart height.
        goods: List of all goods.
        max_price: Price scaling factor.
        main_font: Font for tooltip.
        current_date: Current game simulation date.
        closest_good: Pre-calculated closest good (optional).
        idx: Pre-calculated history index (optional).
    """
    mouse_pos = pygame.mouse.get_pos()
    
    # If not pre-calculated, determine it here (fallback)
    if closest_good is None or idx is None:
        closest_good, idx = _get_closest_good_at_mouse(mouse_pos, chart_border, max_chart_size, max_chart_height, goods, max_price)
    
    if idx is not None:
        # Draw vertical hover line spanning the full height of the chart
        top_y = min(chart_border[1], chart_border[1] + int(max_chart_height))
        bottom_y = max(chart_border[1], chart_border[1] + int(max_chart_height))
        pygame.draw.line(screen, DARK_GRAY, (mouse_pos[0], top_y), (mouse_pos[0], bottom_y), 1)
        
        if closest_good:
            # Get data from the closest good
            price_history = closest_good.price_history_hourly[-int(max_chart_size):]
            price = price_history[idx]
            tooltip_text = f"{closest_good.name}: {price:.2f}"
            
            # Calculate date for the hovered data point
            # Use any visible good to get history length (assuming they all have it)
            visible_goods = [g for g in goods if g.show_in_charts]
            price_history_len = len(visible_goods[0].price_history_hourly[-int(max_chart_size):])
            hours_ago = price_history_len - 1 - idx
            hover_date = current_date - datetime.timedelta(hours=hours_ago)
            date_text = hover_date.strftime("%d.%m.%Y")
            
            # Create a stable width by calculating as if all digits were the widest digit (9)
            # This prevents the tooltip box from "jumping" as prices update.
            stable_text_price = "".join(['9' if c.isdigit() else c for c in tooltip_text])
            stable_text_date = "".join(['9' if c.isdigit() else c for c in date_text])
            
            sw_price, sh_price = main_font.size(stable_text_price)
            sw_date, sh_date = main_font.size(stable_text_date)
            
            total_stable_width = max(sw_price, sw_date)
            row_spacing = 2
            total_stable_height = sh_price + sh_date + row_spacing
            
            # Render the actual text using a fixed color for readability
            price_surface = main_font.render(tooltip_text, True, DARK_BROWN)
            date_surface = main_font.render(date_text, True, DARK_BROWN)
            
            # Create a stable-size rect for the background based on "all 9s" dimensions
            tooltip_base_x = mouse_pos[0] + 15
            tooltip_base_y = mouse_pos[1] - 10
            stable_rect = pygame.Rect(tooltip_base_x, tooltip_base_y, total_stable_width, total_stable_height)
            
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
            
            # Draw the text rows centered within the stable rect
            price_rect = price_surface.get_rect(midtop=(stable_rect.centerx, stable_rect.top))
            date_rect = date_surface.get_rect(midtop=(stable_rect.centerx, stable_rect.top + sh_price + row_spacing))
            
            screen.blit(price_surface, price_rect)
            screen.blit(date_surface, date_rect)

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
