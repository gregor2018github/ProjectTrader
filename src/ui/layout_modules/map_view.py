"""Map view module for rendering the game map.

This module handles the visualization of the map on screen, similar to other
UI layout modules like chart_view or depot_view.
"""

import pygame
import pytmx
from typing import List, Dict, Any, TYPE_CHECKING
from ...config.colors import *

if TYPE_CHECKING:
    from ...models.map import GameMap, Camera, TMXMap, MapPlayer
    from ...game_state import GameState


def draw_map_view(
    screen: pygame.Surface,
    game_map: 'GameMap',
    view_rect: pygame.Rect,
    main_font: pygame.font.Font
) -> None:
    """Draw the map view within the specified rectangle.
    
    Args:
        screen: The pygame surface to draw on.
        game_map: The GameMap model instance containing all map data.
        view_rect: The rectangle defining the map viewport area on screen.
        main_font: Font for UI text rendering.
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
    
    # Build render queue for Y-sorting (trees and player)
    render_queue = _build_render_queue(game_map, offset_x, offset_y)
    
    # Sort by Y coordinate and render
    render_queue.sort(key=lambda obj: obj['y_sort'])
    for obj in render_queue:
        screen.blit(obj['sprite'], obj['pos'])
    
    # Restore clipping
    screen.set_clip(old_clip)
    
    # Draw UI overlay (zoom level, position info)
    _draw_map_ui(screen, game_map, view_rect, main_font)


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
                            screen_y -= (tile_image.get_height() - tmx_map.tile_size * camera.zoom)
                            screen.blit(tile_image, (int(screen_x) + offset_x, int(screen_y) + offset_y))


def _build_render_queue(
    game_map: 'GameMap',
    offset_x: int,
    offset_y: int
) -> List[Dict[str, Any]]:
    """Build a list of objects to render, sorted by Y coordinate.
    
    Args:
        game_map: The GameMap model instance.
        offset_x: Horizontal offset for the view area.
        offset_y: Vertical offset for the view area.
        
    Returns:
        List of render items with sprite, position, and y_sort value.
    """
    render_queue: List[Dict[str, Any]] = []
    tmx_map = game_map.tmx_map
    camera = game_map.camera
    map_player = game_map.map_player
    
    # Add visible trees to queue
    visible_trees = tmx_map.get_visible_trees(camera)
    for tree in visible_trees:
        sprite = tmx_map._get_scaled_tree(tree['variant'], camera.zoom)
        if sprite:
            world_px, world_py = tmx_map.grid_to_world(tree['x'], tree['y'])
            screen_x, screen_y = camera.apply(world_px, world_py)
            
            # Align tree bottom to tile bottom
            tile_screen_height = tmx_map.tile_size * camera.zoom
            tile_screen_width = tmx_map.tile_size * camera.zoom
            draw_x = int(screen_x - (sprite.get_width() - tile_screen_width) / 2.0) + offset_x
            draw_y = int(screen_y + tile_screen_height - sprite.get_height()) + offset_y
            
            # Y-sort by the bottom of the tile (where the trunk is)
            render_queue.append({
                'sprite': sprite,
                'pos': (draw_x, draw_y),
                'y_sort': float(world_py) + tmx_map.tile_size
            })
    
    # Add houses to queue
    for house in tmx_map.houses:
        sprite = house.get_scaled_sprite(camera.zoom)
        if sprite:
            screen_x, screen_y = camera.apply(house.x, house.y)
            # screen_y is the bottom of the sprite because house.x, house.y is bottom-left
            draw_x = screen_x
            draw_y = screen_y - sprite.get_height()
            
            # Culling - check if sprite frame intersects with screen area
            if (draw_x + sprite.get_width() >= 0 and draw_x < camera.screen_width and
                draw_y + sprite.get_height() >= 0 and draw_y < camera.screen_height):
                
                render_queue.append({
                    'sprite': sprite,
                    'pos': (int(draw_x) + offset_x, int(draw_y) + offset_y),
                    'y_sort': house.y_sort
                })

    # Add player to queue
    player_sprite = map_player._get_scaled_sprite(camera.zoom)
    player_screen_x, player_screen_y = camera.apply(map_player.x, map_player.y)
    render_queue.append({
        'sprite': player_sprite,
        'pos': (int(player_screen_x) + offset_x, int(player_screen_y) + offset_y),
        'y_sort': map_player.y + map_player.height  # Use world Y of player bottom
    })
    
    return render_queue


def _draw_map_ui(
    screen: pygame.Surface,
    game_map: 'GameMap',
    view_rect: pygame.Rect,
    main_font: pygame.font.Font
) -> None:
    """Draw UI overlay elements on top of the map.
    
    Args:
        screen: Target surface for rendering.
        game_map: The GameMap model instance.
        view_rect: The rectangle defining the map viewport area.
        main_font: Font for text rendering.
    """
    # Create semi-transparent background for UI text
    ui_bg = pygame.Surface((200, 50), pygame.SRCALPHA)
    ui_bg.fill((0, 0, 0, 128))
    screen.blit(ui_bg, (view_rect.x + 10, view_rect.y + 10))
    
    # Draw zoom level
    zoom_text = main_font.render(f"Zoom: {game_map.camera.zoom:.2f} (+/-)", True, WHITE)
    screen.blit(zoom_text, (view_rect.x + 15, view_rect.y + 15))
    
    # Draw player position
    pos_text = main_font.render(
        f"Pos: ({int(game_map.map_player.x)}, {int(game_map.map_player.y)})",
        True, WHITE
    )
    screen.blit(pos_text, (view_rect.x + 15, view_rect.y + 35))
    
    # Draw controls hint at bottom of map view
    controls_bg = pygame.Surface((250, 25), pygame.SRCALPHA)
    controls_bg.fill((0, 0, 0, 128))
    screen.blit(controls_bg, (view_rect.x + 10, view_rect.bottom - 35))
    
    controls_text = main_font.render("WASD/Arrows: Move | +/-: Zoom", True, WHITE)
    screen.blit(controls_text, (view_rect.x + 15, view_rect.bottom - 32))
