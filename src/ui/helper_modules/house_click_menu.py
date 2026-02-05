"""House click menu module for hover effects and click detection.

This module handles detecting when the mouse hovers over houses that are
within interaction range of the player, and provides hover effect rendering.
"""

import pygame
from typing import Optional, List, Tuple, Dict, Any, TYPE_CHECKING

from ...config.colors import BEIGE

if TYPE_CHECKING:
    from ...models.house import House
    from ...models.map import GameMap, Camera


# Maximum distance (in world units) the player can be from a house to interact with it
HOUSE_INTERACTION_DISTANCE = 48  # About 1.5 tiles

# Hover effect settings
HOVER_SCALE_FACTOR = 1.06  # How much bigger the glow layer is (6% larger)
HOVER_OFFSET_X = -2  # Pixel offset to the left
HOVER_OFFSET_Y = 2   # Pixel offset downward
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
        # Check if player is close enough to interact
        if not _is_player_near_house(player, house):
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


def _is_player_near_house(player, house: 'House') -> bool:
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
    """Create a beige-tinted, slightly larger version of a sprite for hover effect.
    
    Args:
        sprite: The original scaled sprite.
        zoom: Current zoom level (used for cache key).
        
    Returns:
        The glow effect sprite.
    """
    # Use sprite id and zoom as cache key
    cache_key = (id(sprite), round(zoom, 3))
    
    if cache_key in _hover_glow_cache:
        return _hover_glow_cache[cache_key]
    
    # Calculate new size
    orig_w, orig_h = sprite.get_size()
    new_w = int(orig_w * HOVER_SCALE_FACTOR)
    new_h = int(orig_h * HOVER_SCALE_FACTOR)
    
    # Scale the sprite up slightly
    scaled = pygame.transform.smoothscale(sprite, (new_w, new_h))
    
    # Create a tinted version by blending with beige
    # First copy the scaled sprite
    result = scaled.copy()
    
    # Create a beige overlay with same alpha pattern as sprite
    tint_surface = pygame.Surface((new_w, new_h), pygame.SRCALPHA)
    tint_surface.fill(HOVER_TINT)
    
    # Use the scaled sprite's alpha to mask the tint
    tint_surface.blit(scaled, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    
    # Add the tint on top of the result
    result.blit(tint_surface, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
    
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
    offset_y: int
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
