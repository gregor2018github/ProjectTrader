import pygame
from typing import List, Dict, Tuple, Any, TYPE_CHECKING
from ..config.colors import *
from ..config.constants import SCREEN_WIDTH

if TYPE_CHECKING:
    from ..models.good import Good

def draw_chart(screen: pygame.Surface, main_font: pygame.font.Font, chart_border: Tuple[int, int], goods: List['Good'], goods_images_30: Dict[str, pygame.Surface]) -> List[pygame.Rect]:
    """Draw the primary price history chart and selection UI.
    
    Args:
        screen: Target surface for rendering.
        main_font: Primary font used for price levels.
        chart_border: Coordinates (x, y) defining the chart's top-left corner.
        goods: List of all tradeable goods with history data.
        goods_images_30: mapping of good names to 30x30 icons.
        
    Returns:
        List[pygame.Rect]: Hitboxes for the good selection buttons.
    """
    # determine max chart size based on screen size
    max_chart_size = round((int(SCREEN_WIDTH / 2) - (chart_border[0] * 2)), 0)
    max_chart_height = screen.get_height() - (chart_border[1] * 2) - 70

    # Draw basic chart structure
    chart_left_bottom = (chart_border[0], chart_border[1])
    select_bar = pygame.Rect(0, chart_left_bottom[1] + 15, (max_chart_size + chart_border[0] * 2), 75)
    pygame.draw.rect(screen, PALE_BROWN, select_bar)
    pygame.draw.rect(screen, DARK_BROWN, select_bar, 2)
    pygame.draw.line(screen, CHART_BROWN, (chart_border[0], chart_border[1]), (chart_border[0] + max_chart_size, chart_border[1]), 1)
    pygame.draw.line(screen, CHART_BROWN, (chart_border[0], chart_border[1]), (chart_border[0], chart_border[1] + max_chart_height), 1)

    # Calculate max price using chart history instead of bookkeeping history
    max_price = max(max(good.price_history_hourly[-max_chart_size:]) for good in goods if good.show_in_charts)
    _draw_price_levels(screen, main_font, chart_border, max_chart_size, max_chart_height, max_price)

    # Store selection boxes for later use with hover effects
    image_boxes = _draw_selection_boxes(screen, goods, select_bar, goods_images_30, main_font)
    
    # Draw charts for each good with hover effects
    _draw_good_charts(screen, goods, chart_border, max_chart_size, max_chart_height, max_price, main_font, goods_images_30)

    return image_boxes

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
