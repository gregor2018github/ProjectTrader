"""Map view module for rendering the game map.

This module handles the visualization of the map on screen, similar to other
UI layout modules like chart_view or depot_view.
"""

import pygame
import pytmx
import datetime
from typing import List, Dict, Any, Tuple, TYPE_CHECKING
from ...config.colors import *
from ...config.constants import SCREEN_WIDTH, SCREEN_HEIGHT, SIDEBAR_WIDTH
from ..helper_modules.house_click_menu import get_hovered_house, inject_hover_effect_into_queue, is_player_near_house
from ...models.water import get_water_tile_frames, get_water_edge_overlay_frames, get_masked_water_surface, WATER_FRAME_COUNT, WATER_FRAME_INTERVAL

if TYPE_CHECKING:
    from ...models.map import GameMap, Camera, TMXMap
    from ...game_state import GameState


def draw_map_view(
    screen: pygame.Surface,
    game_map: 'GameMap',
    view_rect: pygame.Rect,
    game_state: 'GameState'
) -> None:
    """Draw the map view within the specified rectangle.

    Args:
        screen: The pygame surface to draw on.
        game_map: The GameMap model instance containing all map data.
        view_rect: The rectangle defining the map viewport area on screen.
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
    _render_map_layers(screen, game_map.tmx_map, game_map.camera, offset_x, offset_y, game_map.water_anim_time)
    
    # Update light states
    game_map.tmx_map.update_lights(game_state.date)

    # Detect hovered house before building the render queue
    paused = game_state.time_level == 1
    active_house_menu = getattr(game_state, "active_house_menu", None)
    if paused:
        hovered_house = None
        game_state.house_last_hovered = None
        game_state.house_hover_fade_house = None
        game_state.house_hover_fade_timer = 0
    elif active_house_menu and getattr(game_state, "info_window", None) and getattr(game_state.info_window, "house", None) == active_house_menu:
        if is_player_near_house(game_map.map_player, active_house_menu):
            hovered_house = active_house_menu
        else:
            # Trigger fade out for the menu
            game_state.menu_fade_window = game_state.info_window
            game_state.menu_fade_timer = game_state.menu_fade_duration
            game_state.info_window = None
            game_state.active_house_menu = None
            hovered_house = None
    elif getattr(game_state, 'info_window', None):
        hovered_house = None
    else:
        mouse_pos = pygame.mouse.get_pos()
        hovered_house = get_hovered_house(mouse_pos, game_map, view_rect)

    if not paused:
        if hovered_house:
            game_state.house_last_hovered = hovered_house
            game_state.house_hover_fade_house = None
            game_state.house_hover_fade_timer = 0
        elif game_state.house_last_hovered and game_state.house_hover_fade_house is None:
            game_state.house_hover_fade_house = game_state.house_last_hovered
            game_state.house_hover_fade_timer = game_state.house_hover_fade_duration
            game_state.house_last_hovered = None
    
    # Build render queue for Y-sorting (houses and player)
    render_queue = _build_render_queue(game_map, offset_x, offset_y, game_state.date)
    
    # Inject hover effect into the queue (before sorting) for proper z-ordering
    inject_hover_effect_into_queue(render_queue, hovered_house, game_map.camera, offset_x, offset_y)
    if not hovered_house and game_state.house_hover_fade_timer > 0 and game_state.house_hover_fade_house:
        fade_alpha = game_state.house_hover_fade_timer / game_state.house_hover_fade_duration
        inject_hover_effect_into_queue(
            render_queue,
            game_state.house_hover_fade_house,
            game_map.camera,
            offset_x,
            offset_y,
            alpha_scale=fade_alpha
        )
        game_state.house_hover_fade_timer -= 1
        if game_state.house_hover_fade_timer <= 0:
            game_state.house_hover_fade_house = None
    
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
    
    # Debug overlay is drawn by the caller after the sidebar so it isn't covered


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
    offset_y: int,
    water_anim_time: float = 0.0
) -> None:
    """Render the base TMX map layers.

    Args:
        screen: Target surface for rendering.
        tmx_map: The TMX map data.
        camera: Camera for viewport transformation.
        offset_x: Horizontal offset for the view area.
        offset_y: Vertical offset for the view area.
        water_anim_time: Elapsed unpaused map time, drives the water flipbook frame.
    """
    world_view_width = camera.screen_width / camera.zoom
    world_view_height = camera.screen_height / camera.zoom

    start_x = max(0, int(camera.x // tmx_map.tile_size))
    start_y = max(0, int(camera.y // tmx_map.tile_size))
    end_x = min(tmx_map.width, int((camera.x + world_view_width) // tmx_map.tile_size) + 2)
    end_y = min(tmx_map.height, int((camera.y + world_view_height) // tmx_map.tile_size) + 2)

    water_tiles = tmx_map.water_tiles
    # The static water tile art lives in the "Ground_Mid" layer, and *only*
    # that layer gets its water cells replaced by the animated surface.
    # Layers below it (Ground_Low-1, Ground_Low) must still render normally
    # at those same cells: boundary tiles are only *partly* water (the rest
    # is cut away via alpha, see water.py's masking), so whatever grass art
    # sits underneath needs to actually be there for that cut-away part to
    # reveal — skipping it (as an earlier version did, on the assumption
    # every water tile is fully opaque) left a black hole instead of grass.
    # Layers above Ground_Mid, like "Ground_High" (shoreline decoration —
    # grass overhangs at the water's edge), also always render normally.
    water_drawn = not water_tiles

    for layer in tmx_map.tmx_data.visible_layers:
        # Only render tile layers that start with "Ground"
        if isinstance(layer, pytmx.TiledTileLayer) and layer.name.startswith("Ground"):
            is_water_layer = layer.name == "Ground_Mid"
            for y in range(start_y, end_y):
                for x in range(start_x, end_x):
                    if is_water_layer and not water_drawn and (x, y) in water_tiles:
                        continue
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

            if not water_drawn and layer.name == "Ground_Mid":
                _draw_animated_water(screen, tmx_map, camera, offset_x, offset_y, water_anim_time, start_x, start_y, end_x, end_y)
                water_drawn = True

    # Fallback for maps without a "Ground_Mid" layer — still draw the water
    # somewhere rather than silently dropping it.
    if not water_drawn:
        _draw_animated_water(screen, tmx_map, camera, offset_x, offset_y, water_anim_time, start_x, start_y, end_x, end_y)


def _draw_animated_water(
    screen: pygame.Surface,
    tmx_map: 'TMXMap',
    camera: 'Camera',
    offset_x: int,
    offset_y: int,
    water_anim_time: float,
    start_x: int,
    start_y: int,
    end_x: int,
    end_y: int,
) -> None:
    """Blit the animated water flipbook frame for every visible water tile.

    Boundary/corner cells (part water, part land within the same tile) are
    clipped to that tile's own alpha-cut shape via get_masked_water_surface,
    using the "Ground_Mid" gid still sitting under the animation as the
    shape reference — see water.py's "Sub-tile clipping" section for why.
    """
    water_tiles = tmx_map.water_tiles
    frame_idx = int(water_anim_time / WATER_FRAME_INTERVAL) % WATER_FRAME_COUNT
    edge_tiles = tmx_map.water_edge_tiles
    variants = tmx_map.water_tile_variant
    ground_mid = None
    for layer in tmx_map.tmx_data.visible_layers:
        if isinstance(layer, pytmx.TiledTileLayer) and layer.name == "Ground_Mid":
            ground_mid = layer
            break
    for y in range(start_y, end_y):
        row = ground_mid.data[y] if ground_mid is not None else None
        for x in range(start_x, end_x):
            if (x, y) not in water_tiles:
                continue
            variant = variants.get((x, y), 0)
            frames = get_water_tile_frames(tmx_map.tile_size, camera.zoom, variant)
            gid = row[x] if row is not None else 0
            water_frame = frames[frame_idx]
            if gid:
                water_frame = get_masked_water_surface(tmx_map.tmx_data, gid, water_frame, "water", frame_idx)
            world_x, world_y = tmx_map.grid_to_world(x, y)
            screen_x, screen_y = camera.apply(world_x, world_y)
            pos = (round(screen_x) + offset_x, round(screen_y) + offset_y)
            screen.blit(water_frame, pos)
            if (x, y) in edge_tiles:
                overlay = get_water_edge_overlay_frames(tmx_map.tile_size, camera.zoom, variant)[frame_idx]
                if gid:
                    overlay = get_masked_water_surface(tmx_map.tmx_data, gid, overlay, "edge", frame_idx)
                screen.blit(overlay, pos)


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

    # Add mill blade overlays — same y_sort as the mill building so they
    # sort together; appended after the house entry so they render on top.
    for mill in tmx_map.mills:
        blade_sprite = mill.get_blade_sprite(camera.zoom)
        if blade_sprite and mill.blade_pivot:
            px, py = mill.blade_pivot
            screen_x, screen_y = camera.apply(px, py)
            draw_x = screen_x + offset_x - blade_sprite.get_width() / 2
            draw_y = screen_y + offset_y - blade_sprite.get_height() / 2
            if (draw_x + blade_sprite.get_width() >= offset_x and draw_x < camera.screen_width + offset_x and
                    draw_y + blade_sprite.get_height() >= offset_y and draw_y < camera.screen_height + offset_y):
                render_queue.append({
                    'sprite': blade_sprite,
                    'pos': (draw_x, draw_y),
                    'y_sort': mill.y_sort,
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

    # Add active building lights to queue (Townhall, Church, etc.)
    for group in tmx_map.building_light_groups.values():
        for building_light in group.lights:
            if building_light.is_on(current_time):
                # Get scaled surface
                sprite, glow_extend = building_light.get_render_data(camera.zoom)
                
                # Calculate screen position using bbox coordinates
                screen_x, screen_y = camera.apply(building_light.bbox_x, building_light.bbox_y)
                
                draw_x = screen_x + offset_x - glow_extend
                draw_y = screen_y + offset_y - glow_extend

                # Culling check
                if (draw_x + sprite.get_width() >= offset_x and draw_x < camera.screen_width + offset_x and
                    draw_y + sprite.get_height() >= offset_y and draw_y < camera.screen_height + offset_y):
                    
                    render_queue.append({
                        'sprite': sprite,
                        'pos': (draw_x, draw_y),
                        'y_sort': building_light.y_sort,
                        'flags': pygame.BLEND_ADD
                    })

    # Add field crop sprites to queue (with wind sway animation)
    for field in tmx_map.fields:
        if not field.images:
            continue
        for (world_cx, world_by, sprite_idx) in field.sprite_placements:
            screen_x, screen_y = camera.apply(world_cx, world_by)
            angle = field.get_sway_angle(world_cx, world_by)
            sprite, rel_x, rel_y = field.get_sway_sprite(sprite_idx, camera.zoom, angle)
            draw_x = screen_x + rel_x + offset_x
            draw_y = screen_y + rel_y + offset_y
            if (draw_x + sprite.get_width() >= offset_x and draw_x < camera.screen_width + offset_x and
                    draw_y + sprite.get_height() >= offset_y and draw_y < camera.screen_height + offset_y):
                render_queue.append({
                    'sprite': sprite,
                    'pos': (draw_x, draw_y),
                    'y_sort': world_by
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

    # Add smoke particles to queue
    for emitter in tmx_map.smoke_emitters:
        for particle in emitter.particles:
            sprite, pos = particle.get_render_data(camera, camera.zoom)
            draw_x = pos[0] + offset_x
            draw_y = pos[1] + offset_y
            if (draw_x + sprite.get_width() >= offset_x and draw_x < camera.screen_width + offset_x and
                    draw_y + sprite.get_height() >= offset_y and draw_y < camera.screen_height + offset_y):
                render_queue.append({
                    'sprite': sprite,
                    'pos': (draw_x, draw_y),
                    'y_sort': emitter.y_sort,
                })

    # Add water ripples to queue (flat on the water surface, so sort low like ground clutter)
    for ripple in game_map.ripples:
        if not ripple.is_visible:
            continue
        sprite, pos = ripple.get_render_data(camera, camera.zoom)
        draw_x = pos[0] + offset_x
        draw_y = pos[1] + offset_y
        if (draw_x + sprite.get_width() >= offset_x and draw_x < camera.screen_width + offset_x and
                draw_y + sprite.get_height() >= offset_y and draw_y < camera.screen_height + offset_y):
            render_queue.append({
                'sprite': sprite,
                'pos': (draw_x, draw_y),
                'y_sort': ripple.y,
            })

    # Add sheep NPCs to queue
    for sheep in game_map.tmx_map.sheep:
        sheep_sprite = sheep._get_scaled_sprite(camera.zoom)
        sheep_screen_x, sheep_screen_y = camera.apply(sheep.x, sheep.y)
        draw_x = round(sheep_screen_x) + offset_x
        draw_y = round(sheep_screen_y) + offset_y
        if (draw_x + sheep_sprite.get_width() >= offset_x and draw_x < camera.screen_width + offset_x and
                draw_y + sheep_sprite.get_height() >= offset_y and draw_y < camera.screen_height + offset_y):
            render_queue.append({
                'sprite': sheep_sprite,
                'pos': (draw_x, draw_y),
                'y_sort': sheep.y_sort
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


def draw_map_debug_ui(
    screen: pygame.Surface,
    game_map: 'GameMap',
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
    font = getattr(game_state, 'small_font', main_font)
    fps = game_state.game.clock.get_fps() if game_state.game else 0
    time_str = game_state.date.strftime("%H:%M")

    lines = [
        f"Zoom: {game_map.camera.zoom:.2f}",
        f"X: {int(game_map.map_player.x)}",
        f"Y: {int(game_map.map_player.y)}",
        f"FPS: {fps:.1f}",
        f"Time: {time_str}",
    ]

    line_h = 20
    pad = 6
    panel_w = SIDEBAR_WIDTH
    panel_h = pad + len(lines) * line_h + pad
    bottom_bar_h = 60
    panel_x = SCREEN_WIDTH
    panel_y = SCREEN_HEIGHT - bottom_bar_h - panel_h

    ui_bg = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
    ui_bg.fill((0, 0, 0, 150))
    screen.blit(ui_bg, (panel_x, panel_y))

    for i, line in enumerate(lines):
        text_surf = font.render(line, True, WHITE)
        screen.blit(text_surf, (panel_x + pad, panel_y + pad + i * line_h))
