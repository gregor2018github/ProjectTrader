"""Map view module for rendering the game map.

This module handles the visualization of the map on screen, similar to other
UI layout modules like chart_view or depot_view.
"""

import pygame
import pytmx
import datetime
from typing import List, Dict, Any, Tuple, TYPE_CHECKING
from ...config.colors import *
from ...config.constants import SHOW_MAP_DEBUG

if TYPE_CHECKING:
    from ...models.map import GameMap, Camera, TMXMap, MapPlayer
    from ...game_state import GameState


def draw_map_view(
    screen: pygame.Surface,
    game_map: 'GameMap',
    view_rect: pygame.Rect,
    main_font: pygame.font.Font,
    game_state: 'GameState'
) -> None:
    """Draw the map view within the specified rectangle.
    
    Args:
        screen: The pygame surface to draw on.
        game_map: The GameMap model instance containing all map data.
        view_rect: The rectangle defining the map viewport area on screen.
        main_font: Font for UI text rendering.
        game_state: The current game state.
    """
    # Draw the background frame for the map area
    pygame.draw.rect(screen, SANDY_BROWN, view_rect)
    pygame.draw.rect(screen, DARK_BROWN, view_rect, 2)
    
    # Draw the actual map content area (slightly inset)
    map_content_rect = view_rect.inflate(-10, -10)
    pygame.draw.rect(screen, BLACK, map_content_rect)
    
    # Set up clipping rectangle to prevent drawing outside the view
    old_clip = screen.get_clip()
    screen.set_clip(map_content_rect)
    
    # Offset all drawing by view_rect position
    offset_x = map_content_rect.x
    offset_y = map_content_rect.y
    
    # Update camera dimensions to match the view
    game_map.camera.screen_width = map_content_rect.width
    game_map.camera.screen_height = map_content_rect.height
    
    # Render the map layers
    _render_map_layers(screen, game_map.tmx_map, game_map.camera, offset_x, offset_y)
    
    # Update light states
    game_map.tmx_map.update_lights(game_state.date)

    # Build render queue for Y-sorting (houses and player)
    render_queue = _build_render_queue(game_map, offset_x, offset_y, game_state.date)
    
    # Sort by Y coordinate and render
    render_queue.sort(key=lambda obj: obj['y_sort'])
    for obj in render_queue:
        # Use round() for consistent pixel alignment during movement
        flags = obj.get('flags', 0)
        screen.blit(obj['sprite'], (round(obj['pos'][0]), round(obj['pos'][1])), special_flags=flags)
    
    # Apply day/night cycle lighting (passing rendered Map info to punch holes if needed)
    _apply_lighting(screen, map_content_rect, game_state.date, render_queue)
    
    # Restore clipping
    screen.set_clip(old_clip)
    
    # Draw UI overlay (zoom level, position info, FPS, time) if enabled
    if SHOW_MAP_DEBUG:
        _draw_map_ui(screen, game_map, view_rect, main_font, game_state)


def _apply_lighting(
    screen: pygame.Surface,
    rect: pygame.Rect,
    current_time: datetime.datetime,
    render_queue: List[Dict[str, Any]]
) -> None:
    """Apply a colored overlay to the map based on the time of day.
    
    Args:
        screen: The surface to draw onto.
        rect: The area to apply the lighting to.
        current_time: The current game time.
        render_queue: The list of rendered objects (to find/apply active lights to the mask).
    """
    # Calculate ambient color
    color = _get_ambient_color(current_time)
    
    # If it's effectively full daylight (white), don't draw anything to save resources
    if color == (255, 255, 255):
        return
        
    # Create a lighting overlay
    # optimizing: we could cache this surface if rect size hasn't changed
    # but for now we create it fresh to keep logic simple
    lighting_surf = pygame.Surface((rect.width, rect.height))
    lighting_surf.fill(color)
    
    # We want lights to "break through" the darkness.
    # The darkness is applied via BLEND_MULT. 
    # To make a spot bright, the lighting_surf must be brighter (closer to White) at that spot.
    # We iterate the render queue to find lights that were drawn.
    # Note: This ignores Z-depth for the "glow" effect (tree in front will glow),
    # but it ensures the light itself is not darkened.
    
    for obj in render_queue:
        if obj.get('flags') == pygame.BLEND_ADD: # Identify lights by their blend flag
             # Draw the light onto the darkness mask using ADD
             # Adding color to the dark mask brightens it.
             # e.g. Dark Blue (30,30,70) + Orange Light (200, 100, 0) -> (230, 130, 70)
             # Then Screen (House Wall) * Mask (230, 130, 70) ~ Wall * 0.9 (keep brightness)
             
             # We might want to use the sprite's alpha or color.
             # The sprite in render_queue is already scaled.
             
             # Position logic is same as used in blit
             pos = (round(obj['pos'][0]), round(obj['pos'][1]))
             
             # Determine offset from rect (screen is relative to window, but rect is view_rect)
             # Note: screen passed here IS the main screen. 
             # lighting_surf is same size as rect.
             # obj['pos'] is in screen coordinates (absolute values around 110, 10 etc).
             # rect.x, rect.y is top-left of view.
             # so we need to offset by -rect.x, -rect.y to draw on lighting_surf surface at (0,0)
             
             local_pos = (pos[0] - rect.x, pos[1] - rect.y)
             
             lighting_surf.blit(obj['sprite'], local_pos, special_flags=pygame.BLEND_ADD)

    # Apply using multiply blend mode for a lighting effect
    screen.blit(lighting_surf, rect, special_flags=pygame.BLEND_MULT)


def _get_ambient_color(date: datetime.datetime) -> Tuple[int, int, int]:
    """Calculate the ambient light color based on current time.
    
    Returns:
        RGB tuple representing the ambient light.
    """
    hour = date.hour + date.minute / 60.0
    
    # Keyframes define the color at specific times of day
    # Format: (hour, (r, g, b))
    # We use BLEND_MULT, so (255, 255, 255) is normal brightness (Day)
    # Lower values darken the screen (Night)
    keyframes = [
        (0.0, (30, 30, 70)),     # Deep night (Dark Blue)
        (4.0, (30, 30, 70)),     # Still deep night
        (5.5, (60, 60, 90)),     # Night triggers pre-dawn
        (6.5, (180, 100, 100)),  # Sunrise (Red/Orange tint)
        (8.0, (255, 255, 255)),  # Full daylight
        (17.0, (255, 255, 255)), # Start of sunset
        (18.5, (220, 150, 100)), # Golden hour (Orange/Gold)
        (20.0, (80, 60, 100)),   # Twilight (Purple/Dark)
        (21.0, (30, 30, 70)),    # Night begins
        (24.0, (30, 30, 70))     # Midnight wrap
    ]
    
    # Find which segment we are in
    for i in range(len(keyframes) - 1):
        start_hour, start_color = keyframes[i]
        end_hour, end_color = keyframes[i + 1]
        
        if start_hour <= hour <= end_hour:
            # Interpolate
            t = (hour - start_hour) / (end_hour - start_hour)
            r = int(start_color[0] + (end_color[0] - start_color[0]) * t)
            g = int(start_color[1] + (end_color[1] - start_color[1]) * t)
            b = int(start_color[2] + (end_color[2] - start_color[2]) * t)
            return (r, g, b)
            
    # Fallback (shouldn't be reached if keyframes cover 0-24)
    return (255, 255, 255)


def _render_map_layers(
    screen: pygame.Surface,
    tmx_map: 'TMXMap',
    camera: 'Camera',
    offset_x: int,
    offset_y: int
) -> None:
    """Render the base TMX map layers.
    
    Args:
        screen: Target surface for rendering.
        tmx_map: The TMX map data.
        camera: Camera for viewport transformation.
        offset_x: Horizontal offset for the view area.
        offset_y: Vertical offset for the view area.
    """
    world_view_width = camera.screen_width / camera.zoom
    world_view_height = camera.screen_height / camera.zoom

    start_x = max(0, int(camera.x // tmx_map.tile_size))
    start_y = max(0, int(camera.y // tmx_map.tile_size))
    end_x = min(tmx_map.width, int((camera.x + world_view_width) // tmx_map.tile_size) + 2)
    end_y = min(tmx_map.height, int((camera.y + world_view_height) // tmx_map.tile_size) + 2)

    for layer in tmx_map.tmx_data.visible_layers:
        if isinstance(layer, pytmx.TiledTileLayer):
            for y in range(start_y, end_y):
                for x in range(start_x, end_x):
                    gid = layer.data[y][x]
                    if gid:
                        tile_image = tmx_map._get_scaled_tile(gid, camera.zoom)
                        if tile_image:
                            world_x, world_y = tmx_map.grid_to_world(x, y)
                            screen_x, screen_y = camera.apply(world_x, world_y)
                            # Tiled aligns tiles to the bottom-left of the grid cell
                            # Use rounded tile size for consistency with scaling logic
                            scaled_grid_size = round(tmx_map.tile_size * camera.zoom)
                            screen_y -= (tile_image.get_height() - scaled_grid_size)
                            screen.blit(tile_image, (round(screen_x) + offset_x, round(screen_y) + offset_y))


def _build_render_queue(
    game_map: 'GameMap',
    offset_x: int,
    offset_y: int,
    current_time: datetime.datetime
) -> List[Dict[str, Any]]:
    """Build a list of objects to render, sorted by Y coordinate.
    
    Args:
        game_map: The GameMap model instance.
        offset_x: Horizontal offset for the view area.
        offset_y: Vertical offset for the view area.
        current_time: The current game time.
        
    Returns:
        List of render items with sprite, position, and y_sort value.
    """
    render_queue: List[Dict[str, Any]] = []
    tmx_map = game_map.tmx_map
    camera = game_map.camera
    map_player = game_map.map_player
    
    # Add houses to queue
    for house in tmx_map.houses:
        sprite = house.get_scaled_sprite(camera.zoom)
        if sprite:
            screen_x, screen_y = camera.apply(house.x, house.y)
            # screen_y is the bottom of the sprite because house.x, house.y is bottom-left
            draw_x = screen_x + offset_x
            draw_y = screen_y - sprite.get_height() + offset_y
            
            # Culling - check if sprite frame intersects with screen area
            if (draw_x + sprite.get_width() >= offset_x and draw_x < camera.screen_width + offset_x and
                draw_y + sprite.get_height() >= offset_y and draw_y < camera.screen_height + offset_y):
                
                render_queue.append({
                    'sprite': sprite,
                    'pos': (draw_x, draw_y),
                    'y_sort': house.y_sort
                })

    # Add active lights to queue
    for light in tmx_map.lights:
        if light.is_on(current_time):
            # Get scaled surface and glow offset
            sprite, glow_extend = light.get_render_data(camera.zoom)
            
            # Calculate screen position
            # light.x, light.y is top-left of window rectangle in world coordinates
            screen_x, screen_y = camera.apply(light.x, light.y)
            
            # Draw position accounts for glow extending beyond the window
            draw_x = screen_x + offset_x - glow_extend
            draw_y = screen_y + offset_y - glow_extend

            # Culling check
            if (draw_x + sprite.get_width() >= offset_x and draw_x < camera.screen_width + offset_x and
                draw_y + sprite.get_height() >= offset_y and draw_y < camera.screen_height + offset_y):
                
                render_queue.append({
                    'sprite': sprite,
                    'pos': (draw_x, draw_y),
                    # Y-sort at bottom of window for proper layering
                    'y_sort': light.y_sort, 
                    'flags': pygame.BLEND_ADD
                })

    # Add trees to queue
    for tree in tmx_map.trees:
        sprite = tree.get_scaled_sprite(camera.zoom)
        if sprite:
            screen_x, screen_y = camera.apply(tree.x, tree.y)
            # screen_y is the bottom of the sprite because x, y is bottom-left
            draw_x = screen_x + offset_x
            draw_y = screen_y - sprite.get_height() + offset_y
            
            # Culling - check if sprite frame intersects with screen area
            if (draw_x + sprite.get_width() >= offset_x and draw_x < camera.screen_width + offset_x and
                draw_y + sprite.get_height() >= offset_y and draw_y < camera.screen_height + offset_y):
                
                render_queue.append({
                    'sprite': sprite,
                    'pos': (draw_x, draw_y),
                    'y_sort': tree.y_sort
                })

    # Add player to queue
    player_sprite = map_player._get_scaled_sprite(camera.zoom)
    player_screen_x, player_screen_y = camera.apply(map_player.x, map_player.y)
    render_queue.append({
        'sprite': player_sprite,
        # Use rounding for draw position to prevent shimmering during slow movement
        'pos': (round(player_screen_x) + offset_x, round(player_screen_y) + offset_y),
        'y_sort': map_player.y + map_player.height  # Use world Y of player bottom
    })
    
    return render_queue


def _draw_map_ui(
    screen: pygame.Surface,
    game_map: 'GameMap',
    view_rect: pygame.Rect,
    main_font: pygame.font.Font,
    game_state: 'GameState'
) -> None:
    """Draw UI overlay elements on top of the map.
    
    Args:
        screen: Target surface for rendering.
        game_map: The GameMap model instance.
        view_rect: The rectangle defining the map viewport area.
        main_font: Font for text rendering.
        game_state: The current game state.
    """
    # Create semi-transparent background for UI text (consolidated at top)
    ui_bg = pygame.Surface((200, 95), pygame.SRCALPHA)
    ui_bg.fill((0, 0, 0, 128))
    screen.blit(ui_bg, (view_rect.x + 10, view_rect.y + 10))
    
    # Draw zoom level
    zoom_text = main_font.render(f"Zoom: {game_map.camera.zoom:.2f}", True, WHITE)
    screen.blit(zoom_text, (view_rect.x + 15, view_rect.y + 15))
    
    # Draw player position
    pos_text = main_font.render(
        f"Pos: ({int(game_map.map_player.x)}, {int(game_map.map_player.y)})",
        True, WHITE
    )
    screen.blit(pos_text, (view_rect.x + 15, view_rect.y + 35))
    
    # Draw FPS and Time
    fps = game_state.game.clock.get_fps() if game_state.game else 0
    time_str = game_state.date.strftime("%H:%M")
    
    fps_text = main_font.render(f"FPS: {fps:.1f}", True, WHITE)
    screen.blit(fps_text, (view_rect.x + 15, view_rect.y + 55))
    
    time_text = main_font.render(f"Time: {time_str}", True, WHITE)
    screen.blit(time_text, (view_rect.x + 15, view_rect.y + 75))
