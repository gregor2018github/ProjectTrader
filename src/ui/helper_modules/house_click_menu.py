"""House click menu module for hover effects and click detection.

This module handles detecting when the mouse hovers over houses that are
within interaction range of the player, and provides hover effect rendering.
"""

import pygame
import os
from typing import Optional, List, Tuple, Dict, Any, TYPE_CHECKING

from ...config.colors import BEIGE, DARK_BROWN, SANDY_BROWN, BLACK, WHITE
from ...config.constants import FONTS_PATH

if TYPE_CHECKING:
    from ...models.house import House
    from ...models.map import GameMap, Camera
    from ...game_state import GameState


# Maximum distance (in world units) the player can be from a house to interact with it
HOUSE_INTERACTION_DISTANCE = 48  # About 1.5 tiles

# Hover effect settings
HOVER_GLOW_EXTENSION = 4  # Fixed pixel amount to extend the sprite on each side
HOVER_OFFSET_X = 0   # Pixel offset to the right
HOVER_OFFSET_Y = 0  # Pixel offset upwards
HOVER_TINT = (245, 245, 220, 160)  # Beige with transparency


def get_hovered_house(
    mouse_pos: Tuple[int, int],
    game_map: 'GameMap',
    view_rect: pygame.Rect
) -> Optional['House']:
    """Determine which house (if any) the mouse is hovering over.
    
    Only considers houses that are within interaction distance of the player.
    When multiple houses overlap at the mouse position, returns the one with
    the highest y_sort value (topmost in render order).
    
    Args:
        mouse_pos: Screen coordinates of the mouse cursor (x, y).
        game_map: The GameMap instance containing houses and camera.
        view_rect: The rectangle defining the map viewport on screen.
        
    Returns:
        The House object being hovered, or None if no valid house is under cursor.
    """
    # Calculate the actual map content area (same as in map_view.py)
    map_content_rect = view_rect.inflate(-10, -10)
    
    # Check if mouse is within the map viewport
    if not map_content_rect.collidepoint(mouse_pos):
        return None
    
    camera = game_map.camera
    player = game_map.map_player
    houses = game_map.tmx_map.houses
    
    # Screen offset for the map content area
    offset_x = map_content_rect.x
    offset_y = map_content_rect.y
    
    # Collect candidate houses (within interaction range and under mouse)
    candidates: List[Tuple[float, 'House']] = []
    
    for house in houses:
        # Fences are not interactable buildings
        if house.name and house.name.lower().startswith("fence"):
            continue

        # Check if player is close enough to interact
        if not is_player_near_house(player, house):
            continue
        
        # Get the house sprite and calculate its screen rect
        sprite = house.get_scaled_sprite(camera.zoom)
        if not sprite:
            continue
        
        # Calculate screen position of the house sprite
        screen_x, screen_y = camera.apply(house.x, house.y)
        # house.x, house.y is the bottom-left corner in world space
        # screen_y corresponds to the bottom of the sprite
        draw_x = screen_x + offset_x
        draw_y = screen_y - sprite.get_height() + offset_y
        
        # Create a rect for hit testing
        sprite_rect = pygame.Rect(
            round(draw_x),
            round(draw_y),
            sprite.get_width(),
            sprite.get_height()
        )
        
        # Check if mouse is over this house's sprite
        if sprite_rect.collidepoint(mouse_pos):
            # Store with y_sort for later sorting (higher y_sort = rendered on top)
            candidates.append((house.y_sort, house))
    
    if not candidates:
        return None
    
    # Return the house with the highest y_sort (topmost in render order)
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def is_player_near_house(player, house: 'House') -> bool:
    """Check if the player is close enough to a house to interact.
    
    Uses the house's collision rect for distance calculation, checking if
    the player's center is within HOUSE_INTERACTION_DISTANCE of the collision box.
    
    Args:
        player: The MapPlayer instance.
        house: The House to check proximity to.
        
    Returns:
        True if the player is within interaction distance.
    """
    # Player center position in world coordinates
    player_center_x = player.x + player.width / 2
    player_center_y = player.y + player.height / 2
    
    # Get the house collision rect
    col_rect = house.collision_rect
    
    # Find the closest point on the collision rect to the player center
    closest_x = max(col_rect.left, min(player_center_x, col_rect.right))
    closest_y = max(col_rect.top, min(player_center_y, col_rect.bottom))
    
    # Calculate distance from player center to closest point
    dx = player_center_x - closest_x
    dy = player_center_y - closest_y
    distance_sq = dx * dx + dy * dy
    
    return distance_sq <= HOUSE_INTERACTION_DISTANCE * HOUSE_INTERACTION_DISTANCE


# Cache for hover glow sprites to avoid recreating them every frame
_hover_glow_cache: Dict[Tuple[int, float], pygame.Surface] = {}


def _create_hover_glow_sprite(sprite: pygame.Surface, zoom: float) -> pygame.Surface:
    """Create a monocolor beige silhouette, slightly larger, for hover effect.
    
    Args:
        sprite: The original scaled sprite.
        zoom: Current zoom level (used for cache key).
        
    Returns:
        The monocolor glow effect sprite.
    """
    # Use sprite id and zoom as cache key
    cache_key = (id(sprite), round(zoom, 3))
    
    if cache_key in _hover_glow_cache:
        return _hover_glow_cache[cache_key]
    
    # Calculate new size based on fixed pixel extension
    orig_w, orig_h = sprite.get_size()
    new_w = orig_w + HOVER_GLOW_EXTENSION * 2
    new_h = orig_h + HOVER_GLOW_EXTENSION * 2
    
    # Scale the sprite up slightly to create the "form"
    scaled = pygame.transform.smoothscale(sprite, (new_w, new_h))
    
    # Create a monocolor silhouette (only the form remains)
    # 1. Generate a mask from the scaled sprite's alpha channel
    mask = pygame.mask.from_surface(scaled)
    
    # 2. Convert mask back to a surface with the desired monocolor
    # 'setcolor' is the color for pixels in the mask, 'unsetcolor' is transparent
    result = mask.to_surface(setcolor=HOVER_TINT, unsetcolor=(0, 0, 0, 0))
    
    # Limit cache size to prevent memory issues
    if len(_hover_glow_cache) > 50:
        _hover_glow_cache.clear()
    
    _hover_glow_cache[cache_key] = result
    return result


def inject_hover_effect_into_queue(
    render_queue: List[Dict[str, Any]],
    hovered_house: Optional['House'],
    camera: 'Camera',
    offset_x: int,
    offset_y: int,
    alpha_scale: Optional[float] = None
) -> None:
    """Inject hover effect sprites into the render queue for proper z-ordering.
    
    This modifies the render queue in place, adding a glow layer just before
    the hovered house's normal sprite. This ensures proper layering with
    other objects (player, trees, other houses).
    
    Args:
        render_queue: The list of render items to modify.
        hovered_house: The house being hovered (or None).
        camera: Camera for zoom level.
        offset_x: Horizontal offset for the view area.
        offset_y: Vertical offset for the view area.
    """
    if not hovered_house:
        return
    
    sprite = hovered_house.get_scaled_sprite(camera.zoom)
    if not sprite:
        return
    
    # Find the house in the render queue
    house_index = None
    house_entry = None
    
    for i, obj in enumerate(render_queue):
        # Match by checking if this is the hovered house
        # Houses have unique y_sort based on their y position
        if obj.get('y_sort') == hovered_house.y_sort and 'flags' not in obj:
            # Verify this is actually a house by checking sprite dimensions match
            if obj['sprite'].get_size() == sprite.get_size():
                house_index = i
                house_entry = obj
                break
    
    if house_index is None or house_entry is None:
        return
    
    # Create the glow sprite
    glow_sprite = _create_hover_glow_sprite(sprite, camera.zoom)
    if alpha_scale is not None:
        base_alpha = HOVER_TINT[3] if len(HOVER_TINT) > 3 else 255
        glow_sprite = glow_sprite.copy()
        glow_sprite.set_alpha(max(0, min(255, int(base_alpha * alpha_scale))))
    
    # Calculate the offset for centering the larger glow behind the original
    size_diff_x = (glow_sprite.get_width() - sprite.get_width()) // 2
    size_diff_y = (glow_sprite.get_height() - sprite.get_height()) // 2
    
    glow_x = house_entry['pos'][0] - size_diff_x + HOVER_OFFSET_X
    glow_y = house_entry['pos'][1] - size_diff_y + HOVER_OFFSET_Y
    
    # Insert the glow layer just before the house in the queue
    # Use a slightly lower y_sort so it renders behind the house
    glow_entry = {
        'sprite': glow_sprite,
        'pos': (glow_x, glow_y),
        'y_sort': hovered_house.y_sort - 0.001  # Tiny offset to ensure it's behind
    }
    
    render_queue.insert(house_index, glow_entry)


def show_house_menu(game_state: 'GameState', house: 'House', click_pos: Tuple[int, int]) -> None:
    """Create a menu with interaction options for the clicked house.
    
    Args:
        game_state: The current game state.
        house: The clicked house.
    """
    from .info_window import InfoWindow
    from ...models.institutions.church import Church
    from ...models.institutions.town import Town
    from ...models.institutions.market import Market
    from ...models.institutions.bank import Bank
    
    # Create an info window styled as a menu
    options = ["Inspect"]
    
    # Only show Knock option if building name starts with "House"
    if house.name and house.name.startswith("House"):
        options.insert(0, "Knock")
    
    if isinstance(house, (Church, Town)):
        options.insert(0, "Donate Money")

    if isinstance(house, Town):
        options.insert(0, "Population Stats")
        options.insert(0, "Trading Licenses")

    if isinstance(house, Bank):
        options.insert(0, "Manage Loans")
        options.insert(0, "Take Out Loan")

    if isinstance(house, Market):
        goods = house.get_trade_options()
        for good in reversed(goods): # Insert in reverse so they appear in correct order at top
             options.insert(0, f"QuickTrade {good}")
        options.insert(0, "Check Prices")
    
    # Since InfoWindow constructor takes callback for button clicks, we define one here
    def menu_callback(option_text: str):
        if option_text == "Knock":
            house.interact_knock(game_state)
            
        if option_text == "Take Out Loan" and isinstance(house, Bank):
            from .loan_dialog import open_loan_dialog
            open_loan_dialog(game_state)
            return

        if option_text == "Manage Loans" and isinstance(house, Bank):
            from .loan_dialog import open_loan_management_dialog
            open_loan_management_dialog(game_state)
            return

        if option_text == "Inspect":
            msg = f"Object Name: {house.name}\nClass: {house.house_class}\nCoordinates: X={round(house.x, 1)}, Y={round(house.y, 1)}\nSprite: {house.file_name}"
            if getattr(house, "has_max_inhabitants_property", False):
                msg += f"\nInhabitants: {house.inhabitants}/{house.max_inhabitants}"
            game_state.info_window = InfoWindow(game_state.screen, msg, ["OK"], game_state.font, game_state.game)
            return

        if option_text == "Donate Money" and isinstance(house, (Church, Town)):
            house.open_donation_menu(game_state, click_pos)
            # Don't close window here as open_donation_menu replaces it
            return

        if option_text == "Trading Licenses" and isinstance(house, Town):
            house.open_license_view(game_state, click_pos)
            return

        if option_text == "Population Stats" and isinstance(house, Town):
            house.open_population_stats(game_state, click_pos)
            return

        if option_text.startswith("QuickTrade ") and isinstance(house, Market):
            good_name = option_text.replace("QuickTrade ", "")
            house.open_trade_menu(game_state, click_pos, good_name)
            return

        if option_text == "Check Prices" and isinstance(house, Market):
            game_state.left_side_mode = "market"
            game_state.right_side_mode = "depot"

            if game_state.game:
                market_goods = house.get_trade_options()
                for good in game_state.game.goods:
                    good.show_in_charts = good.name in market_goods

            game_state.info_window = None
            game_state.active_house_menu = None
            return

        # Close the window after selection
        game_state.info_window = None
        game_state.active_house_menu = None
        
    game_state.info_window = HouseMenu(
        game_state.screen,
        house,
        options,
        game_state.font,
        game_state,
        click_pos=click_pos,
        callback=menu_callback,
    )
    game_state.active_house_menu = house


class HouseMenu:
    """A pop-up menu for house interactions."""
    
    def __init__(
        self,
        screen: pygame.Surface,
        house: 'House',
        options: List[str],
        font: pygame.font.Font,
        game_state: 'GameState',
        click_pos: Tuple[int, int],
        callback=None,
    ):
        self.screen = screen
        self.house = house
        self.options = options
        self.font = font
        self.game_state = game_state
        self.callback = callback
        
        # Fancy title font (same as bank sub-menus)
        try:
            self.title_font = pygame.font.Font(os.path.join(FONTS_PATH, "Medici Text.ttf"), 26)
        except Exception:
            self.title_font = font

        # Menu dimensions
        self.width = 240
        self.button_height = 40
        self.padding = 10
        self.header_height = 44  # taller to give the fancy font breathing room
        self.total_height = self.header_height + (len(options) * (self.button_height + self.padding)) + self.padding

        self.close_button_size = 20

        # Position at click with screen clamping (close button is now inside the panel)
        screen_w, screen_h = screen.get_size()
        self.x = max(0, min(click_pos[0], screen_w - self.width))
        self.y = max(0, min(click_pos[1], screen_h - self.total_height))

        self.rect = pygame.Rect(self.x, self.y, self.width, self.total_height)

        # Close button rect — inside the header, top-right corner
        close_pad = (self.header_height - self.close_button_size) // 2
        self.close_rect = pygame.Rect(
            self.x + self.width - self.close_button_size - close_pad,
            self.y + close_pad,
            self.close_button_size,
            self.close_button_size,
        )

        # Create button rects
        self.buttons: List[Tuple[pygame.Rect, str]] = []
        current_y = self.y + self.header_height + self.padding
        for option in options:
            btn_rect = pygame.Rect(self.x + self.padding, current_y, self.width - 2 * self.padding, self.button_height)
            self.buttons.append((btn_rect, option))
            current_y += self.button_height + self.padding

    def handle_click(self, pos: Tuple[int, int]) -> bool:
        """Handle clicks on the menu. Returns True if handled/closed."""
        if self.close_rect.collidepoint(pos):
            self.game_state.menu_fade_window = self
            self.game_state.menu_fade_timer = self.game_state.menu_fade_duration
            self.game_state.info_window = None
            self.game_state.active_house_menu = None
            return True
        # Check if clicked outside
        if not self.rect.collidepoint(pos):
            # Trigger fade out
            self.game_state.menu_fade_window = self
            self.game_state.menu_fade_timer = self.game_state.menu_fade_duration

            self.game_state.info_window = None  # Close menu
            self.game_state.active_house_menu = None
            return True
            
        for rect, option in self.buttons:
            if rect.collidepoint(pos):
                if self.callback:
                    self.callback(option)
                else:
                    self.game_state.info_window = None  # Close after action
                    self.game_state.active_house_menu = None
                return True
        return False

    def draw(self, alpha_scale: float = 1.0) -> None:
        """Draw the menu.
        
        Args:
            alpha_scale: Transparency scale from 0.0 to 1.0.
        """
        if alpha_scale <= 0:
            return

        # Setup target surface — close button is inside the panel so only self.rect matters
        target_surf = self.screen
        ox, oy = 0, 0

        if alpha_scale < 1.0:
            temp_surf = pygame.Surface((self.rect.width, self.rect.height), pygame.SRCALPHA)
            target_surf = temp_surf
            ox, oy = -self.rect.x, -self.rect.y
        else:
            temp_surf = None

        mouse_pos = pygame.mouse.get_pos()

        # Draw menu body (no rounded corners)
        body_rect = self.rect.move(ox, oy)
        pygame.draw.rect(target_surf, SANDY_BROWN, body_rect)
        pygame.draw.rect(target_surf, DARK_BROWN, body_rect, 3)

        # Draw header title with fancy font (centred, leaving room for X on the right)
        raw_name = self.house.name or "House"
        display_name = raw_name.split('_')[0]
        title_surf = self.title_font.render(display_name, True, DARK_BROWN)
        title_rect = title_surf.get_rect(center=(body_rect.centerx, body_rect.y + self.header_height // 2))
        target_surf.blit(title_surf, title_rect)

        # Draw close button (inside header, top-right)
        close_draw_rect = self.close_rect.move(ox, oy)
        pygame.draw.rect(target_surf, DARK_BROWN, close_draw_rect)
        is_close_hovered = alpha_scale >= 1.0 and self.close_rect.collidepoint(mouse_pos)
        if is_close_hovered:
            ov = pygame.Surface(close_draw_rect.size, pygame.SRCALPHA)
            ov.fill((255, 255, 255, 40))
            target_surf.blit(ov, close_draw_rect)
        mg = 5
        pygame.draw.line(target_surf, WHITE,
                         (close_draw_rect.left + mg, close_draw_rect.top + mg),
                         (close_draw_rect.right - mg, close_draw_rect.bottom - mg), 2)
        pygame.draw.line(target_surf, WHITE,
                         (close_draw_rect.left + mg, close_draw_rect.bottom - mg),
                         (close_draw_rect.right - mg, close_draw_rect.top + mg), 2)

        # Draw option buttons
        for rect, text in self.buttons:
            btn_rect = rect.move(ox, oy)
            pygame.draw.rect(target_surf, SANDY_BROWN, btn_rect)
            pygame.draw.rect(target_surf, DARK_BROWN, btn_rect, 2)
            if alpha_scale >= 1.0 and rect.collidepoint(mouse_pos):
                ov = pygame.Surface(btn_rect.size, pygame.SRCALPHA)
                ov.fill((0, 0, 0, 30))
                target_surf.blit(ov, btn_rect)
            text_surf = self.font.render(text, True, BLACK)
            target_surf.blit(text_surf, text_surf.get_rect(center=btn_rect.center))

        if temp_surf:
            temp_surf.set_alpha(int(255 * alpha_scale))
            self.screen.blit(temp_surf, (self.rect.x, self.rect.y))

