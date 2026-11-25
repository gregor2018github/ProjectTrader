"""House click menu module for hover effects and click detection.

This module handles detecting when the mouse hovers over houses that are
within interaction range of the player, and provides hover effect rendering.
"""

import math
import pygame
import os
from typing import Optional, List, Tuple, Dict, Any, TYPE_CHECKING

from ...config import settings_store
from ...config.colors import BEIGE, DARK_BROWN, SANDY_BROWN, BLACK, WHITE, DARK_RED, GRAY
from ...config.constants import FONTS_PATH
from ..ui_utils import draw_9slice
from ...models.introductions import WOODHACKING

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
# Something waiting to be done there (the chopping stump while today's wood is not chopped):
# a soft golden halo, breathing slowly; the hover's beige takes over under the mouse
AVAILABLE_TINT = (255, 214, 110, 150)         # see-through, like the hover's beige
AVAILABLE_GLOW_EXTENSION = HOVER_GLOW_EXTENSION  # no bigger than the hover's glow
AVAILABLE_PULSE_S = 1.6              # one breath, in real seconds
AVAILABLE_ALPHA = (0.1, 1.0)         # the halo's strength between breaths: nearly gone, then clear
_available_glow_cache: Dict[Tuple[int, float], Tuple[pygame.Surface, pygame.Surface]] = {}

# House menu sizing: the menu grows to fit its title, and only titles too long
# for MAX_MENU_WIDTH get a smaller font
MIN_MENU_WIDTH = 240
MAX_MENU_WIDTH = 340
TITLE_FONT_SIZE = 26
MIN_TITLE_FONT_SIZE = 16


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
        if not is_player_near(player, house):
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
        # A gate's picture is mostly empty canvas: only what is drawn of it is hit
        hit_box = house.hit_box() if hasattr(house, "hit_box") else None
        if hit_box is not None:
            zoom = sprite.get_width() / max(1, house.image.get_width())
            sprite_rect = pygame.Rect(round(draw_x + hit_box.x * zoom), round(draw_y + hit_box.y * zoom),
                                      max(1, round(hit_box.w * zoom)), max(1, round(hit_box.h * zoom)))
        
        # Check if mouse is over this house's sprite
        if sprite_rect.collidepoint(mouse_pos):
            # Store with y_sort for later sorting (higher y_sort = rendered on top)
            candidates.append((house.y_sort, house))
    
    if not candidates:
        return None
    
    # Return the house with the highest y_sort (topmost in render order)
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def is_player_near(player, target, max_distance: float = HOUSE_INTERACTION_DISTANCE) -> bool:
    """Check if the player is close enough to a house or figurine to interact.

    Uses the target's collision rect for distance calculation, checking if
    the player's center is within max_distance of the collision box.

    Args:
        player: The MapPlayer instance.
        target: The House or Figurine to check proximity to.
        max_distance: How far apart the two may be, in world pixels.
            Defaults to HOUSE_INTERACTION_DISTANCE, the reach needed to start
            an interaction.

    Returns:
        True if the player is within interaction distance.
    """
    # Player center position in world coordinates
    player_center_x = player.x + player.width / 2
    player_center_y = player.y + player.height / 2

    # Get the target collision rect
    col_rect = target.collision_rect
    
    # Find the closest point on the collision rect to the player center
    closest_x = max(col_rect.left, min(player_center_x, col_rect.right))
    closest_y = max(col_rect.top, min(player_center_y, col_rect.bottom))
    
    # Calculate distance from player center to closest point
    dx = player_center_x - closest_x
    dy = player_center_y - closest_y
    distance_sq = dx * dx + dy * dy
    
    return distance_sq <= max_distance * max_distance


# Cache for hover glow sprites to avoid recreating them every frame.
# Values keep a reference to the source sprite so its id cannot be reused
# by another surface while the entry lives (figurine frames get rebuilt on zoom).
_hover_glow_cache: Dict[Tuple[int, float], Tuple[pygame.Surface, pygame.Surface]] = {}


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

    cached = _hover_glow_cache.get(cache_key)
    if cached is not None and cached[0] is sprite:
        return cached[1]
    
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
    
    _hover_glow_cache[cache_key] = (sprite, result)
    return result


def _create_available_glow_sprite(sprite: pygame.Surface, zoom: float) -> pygame.Surface:
    """A golden halo the shape of the sprite, as much larger as the hover's glow, its edge softened."""
    cache_key = (id(sprite), round(zoom, 3))
    cached = _available_glow_cache.get(cache_key)
    if cached is not None and cached[0] is sprite:
        return cached[1]
    ext = AVAILABLE_GLOW_EXTENSION
    w, h = sprite.get_size()
    silhouette = pygame.mask.from_surface(sprite).to_surface(setcolor=AVAILABLE_TINT, unsetcolor=(0, 0, 0, 0))
    halo = pygame.transform.smoothscale(silhouette, (w + ext * 2, h + ext * 2))   # as large as the hover's
    # Soften its edge a little: down to half and back up
    small = pygame.transform.smoothscale(halo, (max(1, halo.get_width() // 2), max(1, halo.get_height() // 2)))
    halo = pygame.transform.smoothscale(small, halo.get_size())
    if len(_available_glow_cache) > 20:
        _available_glow_cache.clear()
    _available_glow_cache[cache_key] = (sprite, halo)
    return halo


def inject_available_glow_into_queue(render_queue: List[Dict[str, Any]], target: Any, camera: 'Camera') -> None:
    """Breathe a soft golden halo behind something there is to do (see AVAILABLE_TINT).

    Like the hover's glow, it goes into the queue just before the object's own
    entry (found by its 'owner'), so it sorts with it."""
    for i, entry in enumerate(render_queue):
        if entry.get('owner') is target:
            break
    else:
        return
    sprite = entry['sprite']
    halo = _create_available_glow_sprite(sprite, camera.zoom)
    phase = (pygame.time.get_ticks() / 1000.0) / AVAILABLE_PULSE_S * 2 * math.pi
    low, high = AVAILABLE_ALPHA
    halo.set_alpha(round(255 * (low + (high - low) * (0.5 + 0.5 * math.sin(phase)))))
    dx = (halo.get_width() - sprite.get_width()) // 2
    dy = (halo.get_height() - sprite.get_height()) // 2
    render_queue.insert(i, {
        'sprite': halo,
        'pos': (entry['pos'][0] - dx, entry['pos'][1] - dy),
        'y_sort': entry['y_sort'] - 0.002,
    })


def woodhacking_available(game_state: 'GameState') -> bool:
    """Whether today's wood is still to be chopped (the woodhacking is once a day)."""
    game = getattr(game_state, 'game', None)
    if game is None:
        return False
    return game.depot.stats.last_woodhacking_day != game_state.date.date().isoformat()


def minigame_host(game_state: 'GameState', minigame: str) -> Optional[Any]:
    """The NPC on the map who introduces a minigame (models/introductions.py), or None."""
    game = getattr(game_state, 'game', None)
    if game is None:
        return None
    return next((npc for npc in game.game_map.tmx_map.npcs
                 if getattr(npc, 'introduces', None) == minigame), None)


def minigame_introduced(game_state: 'GameState', minigame: str) -> bool:
    """Whether the player has been shown a minigame; always, if nobody on the map shows it."""
    game = getattr(game_state, 'game', None)
    if game is None:
        return False
    return minigame in game.depot.stats.minigames_introduced or minigame_host(game_state, minigame) is None


def open_woodhacking(game_state: 'GameState') -> bool:
    """Start the day's woodhacking, or say it has been done; whether it started.

    The day counts as chopped from here on, however the session ends.
    """
    game_state.info_window = None
    game_state.active_house_menu = None
    if not woodhacking_available(game_state):
        game_state.show_warning("You already chopped wood today! Come back tomorrow.")
        return False
    from ...models.minigames.woodhacking import WoodhackingMinigame
    game_state.game.depot.stats.last_woodhacking_day = game_state.date.date().isoformat()
    game_state.previous_time_level = game_state.time_level
    game_state.time_level = 1
    game_state.minigame = WoodhackingMinigame(game_state.screen, game_state.game)
    return True


def inject_hover_effect_into_queue(
    render_queue: List[Dict[str, Any]],
    hovered: Optional[Any],
    camera: 'Camera',
    offset_x: int,
    offset_y: int,
    alpha_scale: Optional[float] = None
) -> None:
    """Inject hover effect sprites into the render queue for proper z-ordering.

    This modifies the render queue in place, adding a glow layer just before
    the hovered object's normal sprite. This ensures proper layering with
    other objects (player, trees, other houses).

    Args:
        render_queue: The list of render items to modify.
        hovered: The house or figurine being hovered (or None). It is found
            in the queue through the entries' 'owner' key.
        camera: Camera for zoom level.
        offset_x: Horizontal offset for the view area.
        offset_y: Vertical offset for the view area.
    """
    if hovered is None:
        return

    # Find the hovered object's own entry in the render queue
    target_index = None
    target_entry = None

    for i, obj in enumerate(render_queue):
        if obj.get('owner') is hovered:
            target_index = i
            target_entry = obj
            break

    if target_index is None or target_entry is None:
        return

    # Figurines are animated, so glow the frame actually being drawn
    sprite = target_entry['sprite']

    # Create the glow sprite
    glow_sprite = _create_hover_glow_sprite(sprite, camera.zoom)
    if alpha_scale is not None:
        base_alpha = HOVER_TINT[3] if len(HOVER_TINT) > 3 else 255
        glow_sprite = glow_sprite.copy()
        glow_sprite.set_alpha(max(0, min(255, int(base_alpha * alpha_scale))))
    
    # Calculate the offset for centering the larger glow behind the original
    size_diff_x = (glow_sprite.get_width() - sprite.get_width()) // 2
    size_diff_y = (glow_sprite.get_height() - sprite.get_height()) // 2
    
    glow_x = target_entry['pos'][0] - size_diff_x + HOVER_OFFSET_X
    glow_y = target_entry['pos'][1] - size_diff_y + HOVER_OFFSET_Y
    
    # Insert the glow layer just before the hovered object in the queue
    # Use a slightly lower y_sort so it renders behind it
    glow_entry = {
        'sprite': glow_sprite,
        'pos': (glow_x, glow_y),
        'y_sort': target_entry['y_sort'] - 0.001  # Tiny offset to ensure it's behind
    }
    
    render_queue.insert(target_index, glow_entry)


def use_gate(game_state: 'GameState', gate) -> bool:
    """Open a gate the player clicked, or shut it if nobody stands in the gateway, with its sound if it has one.

    Args:
        game_state: The current game state.
        gate: The clicked models.gate.Gate.

    Returns:
        True if it moved.
    """
    from ...models.gate import GATE_VOLUME
    game = game_state.game
    if not gate.toggle(game.game_map.gateway_bodies()):
        return False
    # The sheep fold's gate left open may let a sheep out (models/lost_sheep.py)
    quest_map = getattr(game, "lost_sheep_map", None)
    if quest_map is not None:
        quest_map.player_opened(gate)
    sound = gate.sound(game.sounds)
    if sound is not None:
        game.play_sound(sound, GATE_VOLUME)
    return True


def show_house_menu(game_state: 'GameState', house: 'House', click_pos: Tuple[int, int]) -> None:
    """Create a menu with interaction options for the clicked house.
    
    Args:
        game_state: The current game state.
        house: The clicked house.
    """
    from .info_window import InfoWindow
    from .lost_sheep_talks import blocks_buildings
    from .rank_window import open_rank_window
    from ...models.institutions.church import Church
    from ...models.institutions.town import Town
    from ...models.institutions.market import Market
    from ...models.institutions.bank import Bank
    from ...models.institutions.well import Well
    from ...models.institutions.warehouse import Warehouse
    
    # With the shepherdess's sheep on the leash, the buildings wait (models/lost_sheep.py)
    if blocks_buildings(game_state):
        from ...models.lost_sheep import WARN_BUILDINGS
        game_state.show_warning(WARN_BUILDINGS)
        return

    # Create an info window styled as a menu. Inspect is a debugging aid,
    # only offered with the debug overlay on
    options = ["Inspect"] if settings_store.get("show_map_debug") else []

    # Only show Knock option if building name starts with "House"
    if house.name and house.name.startswith("House"):
        options.insert(0, "Knock")
    
    # The merchants' guild keeps the ranks: the same overview as the rank in the top bar
    # and the trade guilds' licences
    if house.name == "Guildhall":
        options.insert(0, "Trading Licenses")
        options.insert(0, "Gourmet Collection")
        options.insert(0, "Records")
        options.insert(0, "Merchant Rank")

    if house.tavern_class:
        # A room may be booked at any inn, and rested in while it is held (models/inn_rooms.py)
        from ...models.inn_rooms import room_until
        from ...models.rest import can_rest_until
        options.insert(0, "Book a Room")
        player = getattr(game_state.game, 'player', None)
        until = room_until(player, house, game_state.date) if player is not None else None
        if until is not None and can_rest_until(game_state.date, until):
            options.insert(0, "Rest in Your Room")
        options.insert(0, "Daily Menu")

    if isinstance(house, Church):
        options.insert(0, "Donate Goods")

    if isinstance(house, (Church, Town)):
        options.insert(0, "Donate Money")

    if isinstance(house, Town):
        options.insert(0, "General Statistics")
        options.insert(0, "Population Stats")
        options.insert(0, "Town Council")

    if isinstance(house, Well):
        options.insert(0, "Throw Rock")
        options.insert(0, "Throw Coin")

    if house.name == "Stomp":
        options.insert(0, "Chop Wood")

    # A boat moored at a fishing spot is where that spot is fished from (models/fishing_spot.py)
    if house.fishing_spot:
        options.insert(0, "Go Fishing")

    if house.epitaph:
        options.insert(0, "Read")

    # A trough in the chicken pen: looked into and filled (models/chicken_troughs.py, trough_window.py)
    from ...models.trough import Trough
    if isinstance(house, Trough):
        state = game_state.game.troughs[house.name]
        if not state.empty and not state.full:
            options.insert(0, "Refill")
        options.insert(0, "Look In")

    # Uncle Gared's shop, once he has been found: the player's first place to rest (models/rest.py)
    from ...models.rest import can_rest_at
    if can_rest_at(house, getattr(game_state.game, 'intro', None)):
        options.insert(0, "Rest")

    if isinstance(house, Bank):
        options.insert(0, "Manage Loans")
        options.insert(0, "Take Out Loan")

    if isinstance(house, Market):
        goods = house.get_trade_options()
        for good in reversed(goods): # Insert in reverse so they appear in correct order at top
             options.insert(0, f"QuickTrade {good}")
        options.insert(0, "Check Prices")

    if isinstance(house, Warehouse) and not house.is_owned:
        options.insert(0, "Buy Building")

    if isinstance(house, Warehouse) and house.is_owned:
        options.insert(0, "Manage Inventory")

    # The uncle's shop holds the player's first storage, the depot's starting one
    from ...models.intro import is_found_shop
    shop_storage = is_found_shop(house, getattr(game_state.game, 'intro', None))
    if shop_storage:
        options.insert(0, "Manage Inventory")

    if not options:
        return

    # Since InfoWindow constructor takes callback for button clicks, we define one here
    def menu_callback(option_text: str):
        if option_text == "Chop Wood" and house.name == "Stomp":
            if not minigame_introduced(game_state, WOODHACKING):
                # The stump and the axe are the old woodcutter's: he is to be asked first
                host = minigame_host(game_state, WOODHACKING)
                game_state.info_window = None
                game_state.active_house_menu = None
                game_state.show_warning(f"The axe belongs to {host.display_name}, the old woodcutter. "
                                        f"Ask him first; he is about the wood shed by day.")
                return
            open_woodhacking(game_state)
            return

        if option_text == "Go Fishing" and house.fishing_spot:
            from .water_click_menu import open_fishing
            open_fishing(game_state)
            return

        if option_text == "Look In" and isinstance(house, Trough):
            from .trough_window import open_trough_window
            open_trough_window(game_state, house)
            return

        if option_text == "Refill" and isinstance(house, Trough):
            from .trough_window import refill
            game_state.info_window = None
            game_state.active_house_menu = None
            refill(game_state, house)
            return

        if option_text == "Read" and house.epitaph:
            from .gravestone_window import open_gravestone
            open_gravestone(game_state, house)
            return

        if option_text == "Rest":
            from .rest_window import open_rest_window
            open_rest_window(game_state)
            return

        if option_text == "Buy Building" and isinstance(house, Warehouse) and not house.is_owned:
            from .buy_building_dialog import open_buy_building_dialog
            open_buy_building_dialog(game_state, house)
            return

        if option_text == "Manage Inventory" and isinstance(house, Warehouse) and house.is_owned:
            from .warehouse_inventory import open_warehouse_inventory
            open_warehouse_inventory(game_state, house)
            return

        if option_text == "Manage Inventory" and shop_storage:
            from ...models.depot import START
            from .warehouse_inventory import open_warehouse_inventory
            open_warehouse_inventory(game_state, house, START)
            return

        if option_text == "Throw Coin" and isinstance(house, Well):
            house.throw_coin(game_state)
            return

        if option_text == "Throw Rock" and isinstance(house, Well):
            house.throw_rock(game_state)
            return

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
            if house.doors:
                # Townsfolk only: a trader's way home is not tied to a door
                inside = game_state.game.game_map.tmx_map.street_life.people_inside(house)
                names = f" ({', '.join(person.name for person in inside)})" if inside else ""
                msg += f"\nTownsfolk inside now: {len(inside)}{names}"
            game_state.info_window = InfoWindow(game_state.screen, msg, ["OK"], game_state.font, game_state.game)
            return

        if option_text == "Merchant Rank" and house.name == "Guildhall":
            open_rank_window(game_state)
            return

        if option_text == "Records" and house.name == "Guildhall":
            from .records_window import open_records_window
            open_records_window(game_state)
            return

        if option_text == "Gourmet Collection" and house.name == "Guildhall":
            from .gourmet_window import open_gourmet_window
            open_gourmet_window(game_state)
            return

        if option_text == "Book a Room" and house.tavern_class:
            from .room_booking_window import open_room_booking
            open_room_booking(game_state, house)
            return

        if option_text == "Rest in Your Room" and house.tavern_class:
            from .room_booking_window import open_rest_in_room
            open_rest_in_room(game_state, house)
            return

        if option_text == "Daily Menu" and house.tavern_class:
            from .tavern_menu_window import open_tavern_menu
            open_tavern_menu(game_state, house)
            return

        if option_text == "Donate Money" and isinstance(house, (Church, Town)):
            house.open_donation_menu(game_state, click_pos)
            # Don't close window here as open_donation_menu replaces it
            return

        if option_text == "Donate Goods" and isinstance(house, Church):
            house.open_feast_menu(game_state)
            return

        if option_text == "Trading Licenses" and house.name == "Guildhall":
            from .contract_overview import ContractOverview
            game_state.info_window = ContractOverview(game_state.screen, game_state, house=house)
            game_state.active_house_menu = house
            return

        if option_text == "Town Council" and isinstance(house, Town):
            from .council_window import open_council_window
            open_council_window(game_state, house)
            return

        if option_text == "Population Stats" and isinstance(house, Town):
            house.open_population_stats(game_state, click_pos)
            return

        if option_text == "General Statistics" and isinstance(house, Town):
            house.open_statistics_view(game_state, click_pos)
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
                from ...persistence.save_manager import _enforce_chart_limit
                _enforce_chart_limit(game_state.game.goods, game_state)

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
        
        # Menu dimensions
        self.button_height = 40
        self.padding = 10
        self.header_height = 44  # taller to give the fancy font breathing room
        self.total_height = self.header_height + (len(options) * (self.button_height + self.padding)) + self.padding

        self.close_button_size = 20
        close_pad = (self.header_height - self.close_button_size) // 2

        raw_name = house.name or "House"
        self.display_name = getattr(house, 'display_name', '') or raw_name.split('_')[0]

        # The title is centred, so the close button's space is reserved on both sides
        title_side_space = self.close_button_size + close_pad + 6
        self.title_font = self._fit_title_font(font, MAX_MENU_WIDTH - 2 * title_side_space)
        title_width = self.title_font.size(self.display_name)[0]
        self.width = max(MIN_MENU_WIDTH, min(MAX_MENU_WIDTH, title_width + 2 * title_side_space))

        # Position at click with screen clamping (close button is now inside the panel)
        screen_w, screen_h = screen.get_size()
        self.x = max(0, min(click_pos[0], screen_w - self.width))
        self.y = max(0, min(click_pos[1], screen_h - self.total_height))

        self.rect = pygame.Rect(self.x, self.y, self.width, self.total_height)

        # Close button rect — inside the header, top-right corner
        self.close_rect = pygame.Rect(
            self.x + self.width - self.close_button_size - close_pad,
            self.y + close_pad,
            self.close_button_size,
            self.close_button_size,
        )

        # Determine which QuickTrade buttons are disabled (market closed or no license)
        self.disabled_options: set = set()
        if game_state.game is not None:
            depot = game_state.game.depot
            for option in options:
                if option.startswith("QuickTrade "):
                    good_name = option[len("QuickTrade "):]
                    if not self._is_market_open() or not depot.has_license(good_name, game_state.date):
                        self.disabled_options.add(option)

        # Create button rects
        self.buttons: List[Tuple[pygame.Rect, str]] = []
        current_y = self.y + self.header_height + self.padding
        for option in options:
            btn_rect = pygame.Rect(self.x + self.padding, current_y, self.width - 2 * self.padding, self.button_height)
            self.buttons.append((btn_rect, option))
            current_y += self.button_height + self.padding

    def _fit_title_font(self, fallback: pygame.font.Font, max_width: int) -> pygame.font.Font:
        """Fancy title font (same as bank sub-menus), shrunk until the title fits max_width."""
        font_path = os.path.join(FONTS_PATH, "Medici Text.ttf")
        for size in range(TITLE_FONT_SIZE, MIN_TITLE_FONT_SIZE - 1, -2):
            try:
                title_font = pygame.font.Font(font_path, size)
            except Exception:
                return fallback
            if title_font.size(self.display_name)[0] <= max_width:
                break
        return title_font

    def _is_market_open(self) -> bool:
        """Whether this booth has a trader at it; opening hours only matter for market booths."""
        from ...models.institutions.market import Market
        return not isinstance(self.house, Market) or not self.house.is_closed_at(self.game_state.date)

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
                if option in self.disabled_options:
                    if not self._is_market_open():
                        self.game_state.show_warning(
                            f"The {self.house.name} is closed. Its traders have gone home "
                            f"for the night and will be back in the morning.")
                    return True  # absorb click, do nothing
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

        # Draw menu body
        body_rect = self.rect.move(ox, oy)
        game = self.game_state.game
        if game and hasattr(game, 'pic_info_window'):
            draw_9slice(target_surf, game.pic_info_window, body_rect)
        else:
            pygame.draw.rect(target_surf, SANDY_BROWN, body_rect)
            pygame.draw.rect(target_surf, DARK_BROWN, body_rect, 3)

        # Draw header title with fancy font (centred, leaving room for X on the right)
        title_surf = self.title_font.render(self.display_name, True, DARK_BROWN)
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
        hovered_disabled_rect = None
        for rect, text in self.buttons:
            btn_rect = rect.move(ox, oy)
            is_disabled = text in self.disabled_options
            is_hovered = alpha_scale >= 1.0 and rect.collidepoint(mouse_pos)
            bg_color = GRAY if is_disabled else SANDY_BROWN
            pygame.draw.rect(target_surf, bg_color, btn_rect)
            pygame.draw.rect(target_surf, DARK_BROWN, btn_rect, 2)
            if not is_disabled and is_hovered:
                ov = pygame.Surface(btn_rect.size, pygame.SRCALPHA)
                ov.fill((0, 0, 0, 30))
                target_surf.blit(ov, btn_rect)
            label = text[len("QuickTrade "):] if text.startswith("QuickTrade ") else text
            text_surf = self.font.render(label if is_disabled else text, True, BLACK)
            target_surf.blit(text_surf, text_surf.get_rect(center=btn_rect.center))
            if is_disabled and is_hovered:
                hovered_disabled_rect = btn_rect

        # Tooltip explaining why a hovered button is disabled
        if hovered_disabled_rect is not None:
            tip_text = "Market closed" if not self._is_market_open() else "No trading license"
            tip_surf = self.font.render(tip_text, True, DARK_RED)
            tip_w = tip_surf.get_width() + 10
            tip_h = tip_surf.get_height() + 6
            tip_x = min(mouse_pos[0] + 12, self.screen.get_width() - tip_w - 2)
            tip_y = max(mouse_pos[1] - tip_h - 6, 0)
            tip_rect = pygame.Rect(tip_x, tip_y, tip_w, tip_h)
            pygame.draw.rect(self.screen, WHITE, tip_rect)
            pygame.draw.rect(self.screen, DARK_RED, tip_rect, 1)
            self.screen.blit(tip_surf, (tip_x + 5, tip_y + 3))

        if temp_surf:
            temp_surf.set_alpha(int(255 * alpha_scale))
            self.screen.blit(temp_surf, (self.rect.x, self.rect.y))

