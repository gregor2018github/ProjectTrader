"""Map model for the trading game.

This module contains the map logic including TMX loading, camera management,
player movement, collision detection, and map object management.
"""

import os
import random
import pygame
import pytmx
from typing import List, Dict, Tuple, Any, Optional, Union

from ..config.constants import TILE_SIZE, PLAYER_SPEED, MAX_RECULCULATIONS_PER_SEC, FOOT_STEP_VOLUME
from .house import House


class Camera:
    """Handles camera/viewport that follows the player."""
    
    def __init__(self, screen_width: int, screen_height: int) -> None:
        """Initialize the camera.
        
        Args:
            screen_width: Width of the screen in pixels.
            screen_height: Height of the screen in pixels.
        """
        self.x: float = 0.0
        self.y: float = 0.0
        self.screen_width: int = screen_width
        self.screen_height: int = screen_height
        self.zoom: float = 1.0
    
    def set_zoom(self, zoom: Union[float, int]) -> None:
        """Update current zoom factor.
        
        Args:
            zoom: The new zoom multiplier.
        """
        self.zoom = max(0.1, float(zoom))
    
    def update(self, target_x: float, target_y: float, world_width: float, world_height: float) -> None:
        """Center camera on target (usually player) respecting zoom and map bounds.
        
        Args:
            target_x: Target's X coordinate in world space.
            target_y: Target's Y coordinate in world space.
            world_width: Total width of the world map.
            world_height: Total height of the world map.
        """
        half_width = (self.screen_width / self.zoom) / 2
        half_height = (self.screen_height / self.zoom) / 2

        self.x = target_x - half_width
        self.y = target_y - half_height

        max_x = max(0, world_width - (self.screen_width / self.zoom))
        max_y = max(0, world_height - (self.screen_height / self.zoom))

        self.x = max(0, min(self.x, max_x))
        self.y = max(0, min(self.y, max_y))
    
    def apply(self, x: float, y: float) -> Tuple[float, float]:
        """Convert world coordinates to screen coordinates.
        
        Args:
            x: World X coordinate.
            y: World Y coordinate.
            
        Returns:
            Tuple[float, float]: Position relative to camera on screen.
        """
        return (x - self.x) * self.zoom, (y - self.y) * self.zoom


class TMXMap:
    """Map class that loads and renders TMX files."""
    
    def __init__(self, tmx_file: str) -> None:
        """Initialize the map from a TMX file.
        
        Args:
            tmx_file: Path to the .tmx file.
        """
        self.tmx_data: pytmx.TiledMap = pytmx.load_pygame(tmx_file, pixelalpha=True)
        self.width: int = self.tmx_data.width
        self.height: int = self.tmx_data.height
        self.tile_size: int = self.tmx_data.tilewidth
        self.scaled_tile_cache: Dict[float, Dict[Any, pygame.Surface]] = {}
        self.tree_images: List[pygame.Surface] = []
        self.trees: List[Dict[str, int]] = []  # List of dicts with x, y, variant
        self.houses: List[House] = []
        
        # Load tree sprites
        tree_dir = os.path.join('assets', 'map_sprites', 'trees')
        for i in range(1, 12):
            tree_path = os.path.join(tree_dir, f'tree{i}.png')
            if os.path.exists(tree_path):
                try:
                    self.tree_images.append(pygame.image.load(tree_path).convert_alpha())
                except pygame.error:
                    continue
        
        self._load_houses()

    def _load_houses(self) -> None:
        """Load house objects from the "Houses" object layer."""
        for layer in self.tmx_data.visible_layers:
            if isinstance(layer, pytmx.TiledObjectGroup) and layer.name == "Houses":
                for obj in layer:
                    # Extract properties
                    file_name = obj.properties.get('File_name', '')
                    if not file_name:
                        continue
                        
                    tiles_to_right = int(obj.properties.get('Tiles_to_right', 0))
                    tiles_up = int(obj.properties.get('Tiles_up', 0))
                    collision_to_right = int(obj.properties.get('Collision_to_right', 0))
                    collision_up = int(obj.properties.get('Collision_up', 0))
                    
                    house = House(
                        x=obj.x,
                        y=obj.y,
                        file_name=file_name,
                        tiles_to_right=tiles_to_right,
                        tiles_up=tiles_up,
                        collision_to_right=collision_to_right,
                        collision_up=collision_up,
                        tile_size=self.tile_size
                    )
                    self.houses.append(house)

    def check_object_collision(self, rect: pygame.Rect) -> bool:
        """Check if the given rect collides with any map objects (houses)."""
        for house in self.houses:
            if house.collision_rect.colliderect(rect):
                return True
        return False

    def place_random_trees(self, count: int = 50) -> None:
        """Randomly place trees on the map.
        
        Args:
            count: Number of trees to place.
        """
        self.trees = []
        for _ in range(count):
            tx = random.randint(0, self.width - 1)
            ty = random.randint(0, self.height - 1)
            # Only place on walkable tiles (assuming grass is walkable)
            if self.is_walkable(tx, ty):
                variant = random.randrange(len(self.tree_images)) if self.tree_images else 0
                self.trees.append({'x': tx, 'y': ty, 'variant': variant})

    def is_walkable(self, x: int, y: int) -> bool:
        """Check if tile is walkable.
        
        Args:
            x: Grid X coordinate.
            y: Grid Y coordinate.
            
        Returns:
            bool: True if walkable, False otherwise.
        """
        if 0 <= x < self.width and 0 <= y < self.height:
            # Check if there's a tree here
            for tree in self.trees:
                if tree['x'] == x and tree['y'] == y:
                    return False

            # Check all layers for a collidable property
            for layer_idx, layer in enumerate(self.tmx_data.visible_layers):
                if isinstance(layer, pytmx.TiledTileLayer):
                    tile_props = self.tmx_data.get_tile_properties(x, y, layer_idx)
                    if tile_props and tile_props.get('collidable'):
                        return False
            return True
        return False
    
    def world_to_grid(self, world_x: float, world_y: float) -> Tuple[int, int]:
        """Convert world pixel coordinates to grid coordinates.
        
        Args:
            world_x: Pixel X coordinate.
            world_y: Pixel Y coordinate.
            
        Returns:
            Tuple[int, int]: Grid coordinates (X, Y).
        """
        return int(world_x) // self.tile_size, int(world_y) // self.tile_size
    
    def grid_to_world(self, grid_x: int, grid_y: int) -> Tuple[int, int]:
        """Convert grid coordinates to world pixel coordinates.
        
        Args:
            grid_x: Grid X coordinate.
            grid_y: Grid Y coordinate.
            
        Returns:
            Tuple[int, int]: Pixel coordinates (X, Y).
        """
        return grid_x * self.tile_size, grid_y * self.tile_size
    
    def _get_scaled_tile(self, gid: int, zoom: float) -> Optional[pygame.Surface]:
        """Retrieve or create a scaled tile image from GID.
        
        Args:
            gid: Tile GID.
            zoom: Current zoom factor.
            
        Returns:
            Optional[pygame.Surface]: Scaled tile surface if it exists.
        """
        zoom_key = round(float(zoom), 3)
        cache = self.scaled_tile_cache.setdefault(zoom_key, {})
        
        if gid not in cache:
            image = self.tmx_data.get_tile_image_by_gid(gid)
            if image:
                target_width = max(1, int(round(image.get_width() * zoom)))
                target_height = max(1, int(round(image.get_height() * zoom)))
                if target_width >= image.get_width() or target_height >= image.get_height():
                    cache[gid] = pygame.transform.scale(image, (target_width, target_height))
                else:
                    cache[gid] = pygame.transform.smoothscale(image, (target_width, target_height))
            else:
                cache[gid] = None
        return cache[gid]

    def _get_scaled_tree(self, variant: int, zoom: float) -> Optional[pygame.Surface]:
        """Retrieve or create a scaled tree sprite.
        
        Args:
            variant: Tree image index.
            zoom: Current zoom factor.
            
        Returns:
            Optional[pygame.Surface]: Scaled tree surface if it exists.
        """
        if not self.tree_images:
            return None
        
        zoom_key = round(float(zoom), 3)
        cache = self.scaled_tile_cache.setdefault(zoom_key, {})
        cache_key = f"tree_{variant}"
        
        if cache_key not in cache:
            image = self.tree_images[variant % len(self.tree_images)]
            # Trees are 3x tile size wide
            base_tile_width = self.tile_size * 3
            target_width = max(1, int(round(base_tile_width * zoom)))
            scale_ratio = target_width / float(image.get_width())
            target_height = max(1, int(round(image.get_height() * scale_ratio)))
            
            if target_width >= image.get_width() or target_height >= image.get_height():
                cache[cache_key] = pygame.transform.scale(image, (target_width, target_height))
            else:
                cache[cache_key] = pygame.transform.smoothscale(image, (target_width, target_height))
        
        return cache[cache_key]

    def get_visible_trees(self, camera: Camera) -> List[Dict[str, int]]:
        """Get trees that are currently visible in the camera view.
        
        Args:
            camera: Active camera for viewport info.
            
        Returns:
            List[Dict[str, int]]: Trees within the current viewport.
        """
        world_view_width = camera.screen_width / camera.zoom
        world_view_height = camera.screen_height / camera.zoom
        
        # Add some padding for large tree sprites
        padding = 5 
        start_x = int(camera.x // self.tile_size) - padding
        start_y = int(camera.y // self.tile_size) - padding
        end_x = int((camera.x + world_view_width) // self.tile_size) + padding
        end_y = int((camera.y + world_view_height) // self.tile_size) + padding
        
        visible = []
        for tree in self.trees:
            if start_x <= tree['x'] <= end_x and start_y <= tree['y'] <= end_y:
                visible.append(tree)
        return visible


class DirectionalAnimator:
    """Handles directional animations with sprite fallbacks."""

    DIRECTIONS: Tuple[str, ...] = ("front", "back", "left", "right")

    def __init__(self, base_path: str, sprite_definitions: Dict[str, Dict[str, Any]], target_width: int, fallback_static: str) -> None:
        """Initialize the animator.
        
        Args:
            base_path: Root folder for sprites.
            sprite_definitions: Configuration for directions and animations.
            target_width: Desired pixel width for frames.
            fallback_static: Filename for the emergency fallback image.
        """
        self.base_path: str = base_path
        self.sprite_definitions: Dict[str, Dict[str, Any]] = sprite_definitions
        self.target_width: int = target_width

        self.fallback_surface: pygame.Surface = self._load_image(fallback_static)
        if self.fallback_surface is None:
            self.fallback_surface = pygame.Surface((self.target_width, self.target_width), pygame.SRCALPHA)
            self.fallback_surface.fill((255, 0, 255))

        scaled = self._scale_to_target(self.fallback_surface)
        self.fallback_scaled: pygame.Surface = scaled if scaled else self.fallback_surface.copy()

        self.frames: Dict[str, Dict[str, List[pygame.Surface]]] = {}
        self.source_frames: Dict[str, Dict[str, List[pygame.Surface]]] = {}
        
        for direction in self.DIRECTIONS:
            config = self.sprite_definitions.get(direction, {})
            source_static = self._load_image(config.get("static", ""))
            static_surface = self._scale_to_target(source_static)
            
            if source_static is None:
                source_static = self.fallback_surface
            if static_surface is None:
                static_surface = self.fallback_scaled

            move_frames: List[pygame.Surface] = []
            move_sources: List[pygame.Surface] = []
            for filename in config.get("move", []):
                source_frame = self._load_image(filename)
                frame = self._scale_to_target(source_frame)
                if source_frame:
                    move_sources.append(source_frame)
                if frame:
                    move_frames.append(frame)

            if not move_frames:
                move_frames = [static_surface]
            if not move_sources:
                move_sources = [source_static]

            self.frames[direction] = {
                "static": [static_surface],
                "move": move_frames,
            }
            self.source_frames[direction] = {
                "static": [source_static],
                "move": move_sources,
            }

        self.current_direction: str = "front"
        self.is_moving: bool = False
        self.current_frame_index: int = 0
        self.time_since_last_frame: float = 0.0

        # Use the recalc constant as baseline and slow animation slightly for readability.
        base_interval = 1.0 / max(1, MAX_RECULCULATIONS_PER_SEC)
        self.frame_interval: float = max(base_interval * 8, 0.05)

    @property
    def current_frame_size(self) -> Tuple[int, int]:
        """Get dimensions of the current frame."""
        frame = self.get_current_frame()
        return frame.get_width(), frame.get_height()

    def _load_image(self, filename: str) -> Optional[pygame.Surface]:
        """Load image from disk.
        
        Args:
            filename: Image filename.
            
        Returns:
            Optional[pygame.Surface]: Loaded surface or None.
        """
        if not filename:
            return None

        path = os.path.join(self.base_path, filename)
        if not os.path.exists(path):
            return None

        try:
            return pygame.image.load(path).convert_alpha()
        except pygame.error:
            return None

    def _scale_to_target(self, image: Optional[pygame.Surface]) -> Optional[pygame.Surface]:
        """Scale an image to the target width while preserving aspect ratio.
        
        Args:
            image: Source surface.
            
        Returns:
            Optional[pygame.Surface]: Scaled surface.
        """
        if image is None:
            return None

        original_width, original_height = image.get_size()
        if original_width <= 0 or original_height <= 0:
            return None

        scale_ratio = self.target_width / float(original_width)
        scaled_height = max(1, int(round(original_height * scale_ratio)))
        return pygame.transform.smoothscale(image, (self.target_width, scaled_height))

    def update(self, dt: float, direction: str, is_moving: bool) -> None:
        """Update animation state.
        
        Args:
            dt: Delta time.
            direction: Movement direction string.
            is_moving: True if moving, False otherwise.
        """
        if direction not in self.frames:
            direction = "front"

        if direction != self.current_direction or is_moving != self.is_moving:
            self.current_direction = direction
            self.is_moving = is_moving
            self.current_frame_index = 0
            self.time_since_last_frame = 0.0

        self.time_since_last_frame += dt

        active_key = "move" if self.is_moving else "static"
        frames = self.frames[self.current_direction][active_key]

        if len(frames) <= 1:
            self.current_frame_index = 0
            return

        if self.time_since_last_frame >= self.frame_interval:
            self.time_since_last_frame %= self.frame_interval
            self.current_frame_index = (self.current_frame_index + 1) % len(frames)

    def get_current_frame(self) -> pygame.Surface:
        """Get the current scaled frame.
        
        Returns:
            pygame.Surface: The active frame surface.
        """
        active_key = "move" if self.is_moving else "static"
        frames = self.frames[self.current_direction][active_key]
        if not frames:
            return self.fallback_scaled
        return frames[self.current_frame_index % len(frames)]

    def get_current_source_frame(self) -> pygame.Surface:
        """Get the current unscaled source frame.
        
        Returns:
            pygame.Surface: The active source surface.
        """
        active_key = "move" if self.is_moving else "static"
        frames = self.source_frames[self.current_direction][active_key]
        if not frames:
            return self.fallback_surface
        return frames[self.current_frame_index % len(frames)]


class MapPlayer:
    """Player character that moves around the map."""
    
    def __init__(self, x: float, y: float, tile_size: int = TILE_SIZE) -> None:
        """Initialize the player.
        
        Args:
            x: Initial world X.
            y: Initial world Y.
            tile_size: Base tile size for scaling.
        """
        self.x: float = float(x)  # world coordinates (float for smooth movement)
        self.y: float = float(y)
        self.tile_size: int = tile_size
        self.speed: float = PLAYER_SPEED * TILE_SIZE / 32.0  # pixels per second

        sprite_dir = os.path.join('assets', 'map_sprites')
        sprite_definitions: Dict[str, Dict[str, Any]] = {
            "front": {
                "static": "player_front_static.png",
                "move": ["player_front_move1.png", "player_front_move2.png", "player_front_move3.png"]
            },
            "back": {
                "static": "player_back_static.png",
                "move": ["player_back_move1.png", "player_back_move2.png", "player_back_move3.png", "player_back_move4.png"],
            },
            "left": {
                "static": "player_left_static.png",
                "move": ["player_left_move1.png", "player_left_move2.png"],
            },
            "right": {
                "static": "player_right_static.png",
                "move": ["player_right_move1.png", "player_right_move2.png"],
            },
        }

        self.animator: DirectionalAnimator = DirectionalAnimator(
            base_path=sprite_dir,
            sprite_definitions=sprite_definitions,
            target_width=tile_size,
            fallback_static="player_front_static.png",
        )

        self.sprite: pygame.Surface = self.animator.get_current_frame()
        self.source_sprite: pygame.Surface = self.animator.get_current_source_frame()
        self.width: int = tile_size
        self.height: int = self.sprite.get_height()
        self.scaled_sprite_cache: Dict[float, Dict[int, pygame.Surface]] = {}
        
        # Movement state
        self.vel_x: float = 0.0
        self.vel_y: float = 0.0
        self.was_moving: bool = False
        self.footstep_sounds: List[pygame.mixer.Sound] = []
        self.last_sound_index: int = -1
        self.current_sound: Optional[pygame.mixer.Sound] = None
    
    def set_footstep_sounds(self, sounds: List[pygame.mixer.Sound]) -> None:
        """Assign footstep sounds to the player.
        
        Args:
            sounds: List of pygame Sound objects for footsteps.
        """
        self.footstep_sounds = sounds
        for sound in self.footstep_sounds:
            sound.set_volume(FOOT_STEP_VOLUME)

    def stop_footstep_sound(self) -> None:
        """Stop any currently playing footstep sound."""
        if self.current_sound:
            self.current_sound.stop()
            self.current_sound = None
        self.was_moving = False

    def set_movement(self, dx: float, dy: float) -> None:
        """Set movement direction (-1, 0, 1 for each axis).
        
        Args:
            dx: Horizontal direction component.
            dy: Vertical direction component.
        """
        self.vel_x = float(dx)
        self.vel_y = float(dy)
    
    def update(self, dt: float, game_map: TMXMap) -> None:
        """Update player position with collision detection and animation.
        
        Args:
            dt: Delta time.
            game_map: The map for collision checks.
        """
        is_moving = self.vel_x != 0 or self.vel_y != 0

        # Sound logic
        if self.footstep_sounds:
            if is_moving and not self.was_moving:
                # Started moving - pick a sound
                available_indices = [i for i in range(len(self.footstep_sounds)) if i != self.last_sound_index]
                if not available_indices: # only 1 sound available or empty
                    available_indices = [0] if self.footstep_sounds else []
                
                if available_indices:
                    self.last_sound_index = random.choice(available_indices)
                    self.current_sound = self.footstep_sounds[self.last_sound_index]
                    self.current_sound.play(loops=-1)
            elif not is_moving and self.was_moving:
                # Stopped moving
                self.stop_footstep_sound()

        if is_moving:
            move_x = self.vel_x * self.speed * dt
            move_y = self.vel_y * self.speed * dt

            if move_x != 0:
                new_x = self.x + move_x
                if self.can_move_to(new_x, self.y, game_map):
                    self.x = new_x

            if move_y != 0:
                new_y = self.y + move_y
                if self.can_move_to(self.x, new_y, game_map):
                    self.y = new_y

        direction = self._determine_direction(is_moving)
        self.animator.update(dt, direction, is_moving)
        self.sprite = self.animator.get_current_frame()
        self.source_sprite = self.animator.get_current_source_frame()
        self.width = self.sprite.get_width()
        self.height = self.sprite.get_height()
        self.was_moving = is_moving

    def _determine_direction(self, is_moving: bool) -> str:
        """Calculate active direction string based on velocity.
        
        Args:
            is_moving: Whether the player is currently moving.
            
        Returns:
            str: Direction identifier.
        """
        if is_moving:
            if self.vel_y > 0:
                return "front"
            if self.vel_y < 0:
                return "back"
            if self.vel_x < 0:
                return "left"
            if self.vel_x > 0:
                return "right"
        return self.animator.current_direction
    
    def can_move_to(self, x: float, y: float, game_map: TMXMap) -> bool:
        """Check if player can move to the given position.
        
        Args:
            x: Target world X.
            y: Target world Y.
            game_map: Map data for tile checks.
            
        Returns:
            bool: True if navigable.
        """
        # Ensure coordinates are within map bounds
        if x < 0 or y < 0:
            return False
        if x + self.width > game_map.width * game_map.tile_size:
            return False
        if y + self.height > game_map.height * game_map.tile_size:
            return False
        
        # Calculate collision box (just the bottom tile/feet area)
        collision_height = self.tile_size
        collision_y = y + self.height - collision_height
        
        # Check collision with objects (houses)
        player_rect = pygame.Rect(int(x), int(collision_y), int(self.width), int(collision_height))
        if game_map.check_object_collision(player_rect):
            return False

        # Get the four corners of the player collision box (feet area)
        corners = [
            (x, collision_y),  # top-left of collision area
            (x + self.width - 1, collision_y),  # top-right of collision area
            (x, y + self.height - 1),  # bottom-left
            (x + self.width - 1, y + self.height - 1)  # bottom-right
        ]
        
        # Check if all corners are in walkable tiles
        for corner_x, corner_y in corners:
            if corner_x < 0 or corner_y < 0:
                return False
                
            grid_x, grid_y = game_map.world_to_grid(corner_x, corner_y)
            if not game_map.is_walkable(grid_x, grid_y):
                return False
        
        return True
    
    def _get_scaled_sprite(self, zoom: float) -> pygame.Surface:
        """Get the appropriately scaled player sprite for the current zoom.
        
        Args:
            zoom: Current camera zoom level.
            
        Returns:
            pygame.Surface: Scaled frame.
        """
        zoom_key = round(float(zoom), 3)
        cache = self.scaled_sprite_cache.setdefault(zoom_key, {})
        base_frame = self.source_sprite or self.sprite
        frame_id = id(base_frame)
        if frame_id not in cache:
            if abs(zoom - 1.0) < 1e-3:
                cache[frame_id] = self.sprite
            else:
                source_width = base_frame.get_width()
                source_height = base_frame.get_height()
                if source_width <= 0 or source_height <= 0:
                    cache[frame_id] = self.sprite
                else:
                    target_width = max(1, int(round(self.width * zoom)))
                    target_height = max(1, int(round(self.height * zoom)))
                    if target_width >= source_width or target_height >= source_height:
                        cache[frame_id] = pygame.transform.scale(base_frame, (target_width, target_height))
                    else:
                        cache[frame_id] = pygame.transform.smoothscale(base_frame, (target_width, target_height))
        return cache[frame_id]

    def on_zoom_change(self) -> None:
        """Invalidate the sprite cache on zoom change."""
        self.scaled_sprite_cache.clear()


class GameMap:
    """High-level map manager that coordinates all map-related objects."""
    
    def __init__(self, view_width: int, view_height: int) -> None:
        """Initialize the game map system.
        
        Args:
            view_width: Width of the map viewport in pixels.
            view_height: Height of the map viewport in pixels.
        """
        self.view_width = view_width
        self.view_height = view_height
        
        # Initialize camera
        self.camera: Camera = Camera(view_width, view_height)
        self.zoom_levels: List[float] = [0.75, 1.0, 1.25, 1.5, 1.75]
        self.zoom_index: int = 1
        self.camera.set_zoom(self.zoom_levels[self.zoom_index])
        
        # Load TMX map
        tmx_path = os.path.join('assets', 'tiles', 'Map1.tmx')
        self.tmx_map: TMXMap = TMXMap(tmx_path)
        self.tmx_map.place_random_trees(30)
        
        # Initialize map player
        self.map_player: MapPlayer = MapPlayer(
            10.0 * self.tmx_map.tile_size,
            10.0 * self.tmx_map.tile_size,
            self.tmx_map.tile_size
        )
    
    def handle_zoom(self, direction: int) -> None:
        """Handle zoom in/out.
        
        Args:
            direction: Positive for zoom in, negative for zoom out.
        """
        if direction > 0:
            self.zoom_index = min(len(self.zoom_levels) - 1, self.zoom_index + 1)
        elif direction < 0:
            self.zoom_index = max(0, self.zoom_index - 1)
        
        self.camera.set_zoom(self.zoom_levels[self.zoom_index])
        self.map_player.on_zoom_change()
    
    def handle_movement_keys(self, keys: pygame.key.ScancodeWrapper) -> None:
        """Process movement key states.
        
        Args:
            keys: Current keyboard state from pygame.key.get_pressed().
        """
        dx = 0.0
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            dx -= 1.0
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            dx += 1.0
            
        dy = 0.0
        if keys[pygame.K_UP] or keys[pygame.K_w]:
            dy -= 1.0
        if keys[pygame.K_DOWN] or keys[pygame.K_s]:
            dy += 1.0
        
        self.map_player.set_movement(dx, dy)
    
    def update(self, dt: float) -> None:
        """Update map state including player and camera.
        
        Args:
            dt: Delta time in seconds.
        """
        self.map_player.update(dt, self.tmx_map)
        self.camera.update(
            self.map_player.x + self.map_player.width / 2.0,
            self.map_player.y + self.map_player.height / 2.0,
            self.tmx_map.width * self.tmx_map.tile_size,
            self.tmx_map.height * self.tmx_map.tile_size
        )
    
    def resize_view(self, width: int, height: int) -> None:
        """Update the viewport size when the map view area changes.
        
        Args:
            width: New viewport width.
            height: New viewport height.
        """
        self.view_width = width
        self.view_height = height
        self.camera.screen_width = width
        self.camera.screen_height = height
