"""Map model for the trading game.

This module contains the map logic including TMX loading, camera management,
player movement, collision detection, and map object management.
"""

import os
import random
import datetime
import pygame
import pytmx
from typing import List, Dict, Set, Tuple, Any, Optional, Union

from ..config.constants import TILE_SIZE, PLAYER_SPEED, MAX_RECULCULATIONS_PER_SEC, FOOT_STEP_VOLUME, MAP_START_ZOOM, START_X_POSITION, START_Y_POSITION
from .house import House
from .institutions.church import Church
from .institutions.town import Town
from .institutions.market import Market
from .institutions.mill import Mill
from .institutions.bank import Bank
from .institutions.well import Well
from .institutions.warehouse import Warehouse
from .tree import Tree
from .field import Field
from .light import Light, BuildingLight, BuildingLightGroup
from .smoke import SmokeEmitter
from .npcs.sheep import Sheep
from .water import Water, Ripple, water_tile_variant



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
        self.zoom: float = MAP_START_ZOOM
    
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
            world_width: Total width of the world map in world units.
            world_height: Total height of the world map in world units.
        """
        # Calculate scaling factor consistent with tile rendering
        scaled_tile_size = round(TILE_SIZE * self.zoom)
        scale_factor = scaled_tile_size / float(TILE_SIZE)
        
        # Center the camera on the target in pixel space
        half_screen_w = self.screen_width / 2.0
        half_screen_h = self.screen_height / 2.0
        
        # Target position in pixels
        target_px = target_x * scale_factor
        target_py = target_y * scale_factor
        
        # Camera top-left in pixels
        cam_px = target_px - half_screen_w
        cam_py = target_py - half_screen_h
        
        # Map boundaries in pixels
        world_px_w = world_width * scale_factor
        world_px_h = world_height * scale_factor
        
        # Clamp camera to map bounds
        max_px_x = max(0, world_px_w - self.screen_width)
        max_px_y = max(0, world_px_h - self.screen_height)
        
        cam_px = max(0, min(cam_px, max_px_x))
        cam_py = max(0, min(cam_py, max_px_y))
        
        # Convert pixel position back to "world units" for storage and apply()
        self.x = cam_px / scale_factor if scale_factor > 0 else 0
        self.y = cam_py / scale_factor if scale_factor > 0 else 0
    
    def apply(self, x: float, y: float) -> Tuple[float, float]:
        """Convert world coordinates to screen coordinates.
        
        Args:
            x: World X coordinate.
            y: World Y coordinate.
            
        Returns:
            Tuple[float, float]: Position relative to camera on screen.
        """
        # Ensure we use the same scaling logic as the tile renderer
        scaled_tile_size = round(TILE_SIZE * self.zoom)
        scale_factor = scaled_tile_size / float(TILE_SIZE)
        
        return (x * scale_factor - self.x * scale_factor), (y * scale_factor - self.y * scale_factor)


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
        self.houses: List[House] = []
        self.mills: List[Mill] = []
        self.trees: List[Tree] = []
        self.lights: List[Light] = []
        self.building_light_groups: Dict[str, BuildingLightGroup] = {}
        self.areas: Dict[str, pygame.Rect] = {}
        self.smoke_emitters: List[SmokeEmitter] = []
        self.fields: List[Field] = []
        self.sheep: List[Sheep] = []
        self.waters: List[Water] = []
        # Grid cells covered by water (used for the animated water tile
        # rendering in map_view.py). Rasterized once at load time so the
        # render loop only ever needs an O(1) set lookup per visible tile.
        self.water_tiles: Set[Tuple[int, int]] = set()
        self.water_tile_variant: Dict[Tuple[int, int], int] = {}
        self.water_edge_tiles: Set[Tuple[int, int]] = set()

        self._load_houses()
        self._load_special_points()
        self._load_trees()
        self._load_fields()
        self._load_lights()
        self._load_areas()
        self._load_smoke()
        self._load_movements()
        self._load_water()
        self._rasterize_water_tiles()

    def _load_areas(self) -> None:
        """Load area objects from the 'Areas' object layer."""
        for layer in self.tmx_data.visible_layers:
            if isinstance(layer, pytmx.TiledObjectGroup) and layer.name == "Areas":
                for obj in layer:
                    self.areas[obj.name] = pygame.Rect(obj.x, obj.y, obj.width, obj.height)

    def _load_water(self) -> None:
        """Load polygon water bodies from the 'Water' object layer."""
        for layer in self.tmx_data.visible_layers:
            if isinstance(layer, pytmx.TiledObjectGroup) and layer.name == "Water":
                for obj in layer:
                    if hasattr(obj, 'points') and obj.points:
                        world_points = [(obj.x + px, obj.y + py) for px, py in obj.points]
                        self.waters.append(Water(obj.name or "Water", world_points))

    def _rasterize_water_tiles(self) -> None:
        """Compute which grid cells lie inside a water polygon, once at load time.

        This turns the (potentially complex) polygon test into a plain set
        membership check that the per-frame render loop can afford to do for
        every visible tile, even when nothing on screen is water.
        """
        for water in self.waters:
            rect = water._bounding_rect
            gx0 = max(0, rect.left // self.tile_size)
            gy0 = max(0, rect.top // self.tile_size)
            gx1 = min(self.width - 1, rect.right // self.tile_size)
            gy1 = min(self.height - 1, rect.bottom // self.tile_size)
            for gy in range(int(gy0), int(gy1) + 1):
                for gx in range(int(gx0), int(gx1) + 1):
                    cx = gx * self.tile_size + self.tile_size / 2
                    cy = gy * self.tile_size + self.tile_size / 2
                    if water.contains_point(cx, cy):
                        self.water_tiles.add((gx, gy))
                        self.water_tile_variant[(gx, gy)] = water_tile_variant(gx, gy)

        for (gx, gy) in self.water_tiles:
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                if (gx + dx, gy + dy) not in self.water_tiles:
                    self.water_edge_tiles.add((gx, gy))
                    break

    def _load_houses(self) -> None:
        """Load house objects from the "Houses" object layer."""
        for layer in self.tmx_data.visible_layers:
            if isinstance(layer, pytmx.TiledObjectGroup) and layer.name == "Houses":
                for obj in layer:
                    # Extract properties
                    file_name = obj.properties.get('File_name', '')
                    # We now allow objects without a file_name (invisible collision boxes)
                        
                    tiles_to_right = int(obj.properties.get('Tiles_to_right', 0))
                    tiles_up = int(obj.properties.get('Tiles_up', 0))
                    collision_to_right = int(obj.properties.get('Collision_to_right', 0))
                    collision_up = int(obj.properties.get('Collision_up', 0))
                    
                    # Optional pixel margins for fine-tuning collision
                    col_margin_right = int(obj.properties.get('Col_margin_right_pixel', 0))
                    col_margin_left = int(obj.properties.get('Col_margin_left_pixel', 0))
                    col_margin_up = int(obj.properties.get('Col_margin_up_pixel', 0))
                    col_margin_down = int(obj.properties.get('Col_margin_down_pixel', 0))
                    has_max_inhabitants_property = 'Max_inhabitants' in obj.properties
                    max_inhabitants = int(obj.properties.get('Max_inhabitants', 0))
                    obj_class = getattr(obj, 'type', "") or ""
                    
                    if obj.name.startswith("Church"):
                        house = Church(
                            x=obj.x,
                            y=obj.y,
                            file_name=file_name,
                            tiles_to_right=tiles_to_right,
                            tiles_up=tiles_up,
                            collision_to_right=collision_to_right,
                            collision_up=collision_up,
                            tile_size=self.tile_size,
                            col_margin_right_pixel=col_margin_right,
                            col_margin_left_pixel=col_margin_left,
                            col_margin_up_pixel=col_margin_up,
                            col_margin_down_pixel=col_margin_down,
                            max_inhabitants=max_inhabitants,
                            has_max_inhabitants_property=has_max_inhabitants_property,
                            name=obj.name,
                            house_class=obj_class
                        )
                    elif obj.name.startswith("Townhall"):
                        house = Town(
                            x=obj.x,
                            y=obj.y,
                            file_name=file_name,
                            tiles_to_right=tiles_to_right,
                            tiles_up=tiles_up,
                            collision_to_right=collision_to_right,
                            collision_up=collision_up,
                            tile_size=self.tile_size,
                            col_margin_right_pixel=col_margin_right,
                            col_margin_left_pixel=col_margin_left,
                            col_margin_up_pixel=col_margin_up,
                            col_margin_down_pixel=col_margin_down,
                            max_inhabitants=max_inhabitants,
                            has_max_inhabitants_property=has_max_inhabitants_property,
                            name=obj.name,
                            house_class=obj_class
                        )
                    elif "Market" in obj.name:
                        house = Market(
                            x=obj.x,
                            y=obj.y,
                            file_name=file_name,
                            tiles_to_right=tiles_to_right,
                            tiles_up=tiles_up,
                            collision_to_right=collision_to_right,
                            collision_up=collision_up,
                            tile_size=self.tile_size,
                            col_margin_right_pixel=col_margin_right,
                            col_margin_left_pixel=col_margin_left,
                            col_margin_up_pixel=col_margin_up,
                            col_margin_down_pixel=col_margin_down,
                            max_inhabitants=max_inhabitants,
                            has_max_inhabitants_property=has_max_inhabitants_property,
                            name=obj.name,
                            house_class=obj_class
                        )
                    elif obj.name.startswith("Mill"):
                        house = Mill(
                            x=obj.x,
                            y=obj.y,
                            file_name=file_name,
                            tiles_to_right=tiles_to_right,
                            tiles_up=tiles_up,
                            collision_to_right=collision_to_right,
                            collision_up=collision_up,
                            tile_size=self.tile_size,
                            col_margin_right_pixel=col_margin_right,
                            col_margin_left_pixel=col_margin_left,
                            col_margin_up_pixel=col_margin_up,
                            col_margin_down_pixel=col_margin_down,
                            max_inhabitants=max_inhabitants,
                            has_max_inhabitants_property=has_max_inhabitants_property,
                            name=obj.name,
                            house_class=obj_class
                        )
                        self.mills.append(house)
                    elif obj.name.startswith("Well"):
                        house = Well(
                            x=obj.x,
                            y=obj.y,
                            file_name=file_name,
                            tiles_to_right=tiles_to_right,
                            tiles_up=tiles_up,
                            collision_to_right=collision_to_right,
                            collision_up=collision_up,
                            tile_size=self.tile_size,
                            col_margin_right_pixel=col_margin_right,
                            col_margin_left_pixel=col_margin_left,
                            col_margin_up_pixel=col_margin_up,
                            col_margin_down_pixel=col_margin_down,
                            max_inhabitants=max_inhabitants,
                            has_max_inhabitants_property=has_max_inhabitants_property,
                            name=obj.name,
                            house_class=obj_class
                        )
                    elif obj.name.startswith("Bank"):
                        house = Bank(
                            x=obj.x,
                            y=obj.y,
                            file_name=file_name,
                            tiles_to_right=tiles_to_right,
                            tiles_up=tiles_up,
                            collision_to_right=collision_to_right,
                            collision_up=collision_up,
                            tile_size=self.tile_size,
                            col_margin_right_pixel=col_margin_right,
                            col_margin_left_pixel=col_margin_left,
                            col_margin_up_pixel=col_margin_up,
                            col_margin_down_pixel=col_margin_down,
                            max_inhabitants=max_inhabitants,
                            has_max_inhabitants_property=has_max_inhabitants_property,
                            name=obj.name,
                            house_class=obj_class
                        )
                    elif obj.properties.get('Buy_type') is not None:
                        house = Warehouse(
                            x=obj.x,
                            y=obj.y,
                            file_name=file_name,
                            tiles_to_right=tiles_to_right,
                            tiles_up=tiles_up,
                            collision_to_right=collision_to_right,
                            collision_up=collision_up,
                            tile_size=self.tile_size,
                            col_margin_right_pixel=col_margin_right,
                            col_margin_left_pixel=col_margin_left,
                            col_margin_up_pixel=col_margin_up,
                            col_margin_down_pixel=col_margin_down,
                            max_inhabitants=max_inhabitants,
                            has_max_inhabitants_property=has_max_inhabitants_property,
                            name=obj.name,
                            house_class=obj_class,
                            buy_price=int(obj.properties.get('Buy_price', 0)),
                            buy_storage=int(obj.properties.get('Buy_storage', 0)),
                            buy_type=str(obj.properties.get('Buy_type', 'Warehouse')),
                            tmx_id=int(obj.id),
                        )
                    else:
                        house = House(
                            x=obj.x,
                            y=obj.y,
                            file_name=file_name,
                            tiles_to_right=tiles_to_right,
                            tiles_up=tiles_up,
                            collision_to_right=collision_to_right,
                            collision_up=collision_up,
                            tile_size=self.tile_size,
                            col_margin_right_pixel=col_margin_right,
                            col_margin_left_pixel=col_margin_left,
                            col_margin_up_pixel=col_margin_up,
                            col_margin_down_pixel=col_margin_down,
                            max_inhabitants=max_inhabitants,
                            has_max_inhabitants_property=has_max_inhabitants_property,
                            name=obj.name,
                            house_class=obj_class
                        )
                    house.display_name = obj.properties.get('Display_name', '')
                    self.houses.append(house)

    def _load_trees(self) -> None:
        """Load tree objects from the "Trees" object layer."""
        for layer in self.tmx_data.visible_layers:
            if isinstance(layer, pytmx.TiledObjectGroup) and layer.name == "Trees":
                for obj in layer:
                    file_name = obj.properties.get('File_name', '')
                    stem_position = float(obj.properties.get('Stem_Position', 0.0))
                    stem_thick = float(obj.properties.get('Stem_Thick', 0.0))
                    
                    if file_name:
                        tree = Tree(
                            x=obj.x,
                            y=obj.y,
                            file_name=file_name,
                            stem_position=stem_position,
                            stem_thick=stem_thick,
                            tile_size=self.tile_size
                        )
                        self.trees.append(tree)

    def _load_fields(self) -> None:
        """Load field objects from the 'Fields' object layer."""
        for layer in self.tmx_data.visible_layers:
            if isinstance(layer, pytmx.TiledObjectGroup) and layer.name == "Fields":
                for obj in layer:
                    field = Field(
                        x=obj.x,
                        y=obj.y,
                        width=obj.width,
                        height=obj.height,
                        name=obj.name
                    )
                    self.fields.append(field)

    def _load_lights(self) -> None:
        """Load light objects from the 'Lights' object layer.
        
        Loads two types of lights:
        1. 'Light_rectangle' - Individual rectangular window lights
        2. 'Townhall', 'Church' - Polygon lights for big buildings (grouped by name)
        """
        # Building names that should be treated as grouped polygon lights
        building_light_names = {'Townhall', 'Church'}
        
        for layer in self.tmx_data.visible_layers:
            if isinstance(layer, pytmx.TiledObjectGroup) and layer.name == "Lights":
                for obj in layer:
                    # Load regular rectangular lights
                    if obj.name == "Light_rectangle":
                        light = Light(
                            x=obj.x,
                            y=obj.y,
                            width=obj.width,
                            height=obj.height,
                            tile_size=self.tile_size
                        )
                        self.lights.append(light)
                        
                        # Find the house that contains this light
                        # A light is "in" a house if its center is within the house's collision_rect
                        # (We use collision_rect as a proxy for the house bounds on the map)
                        light_center_x = obj.x + obj.width / 2
                        light_center_y = obj.y + obj.height / 2
                        
                        for house in self.houses:
                            # Use collision_rect to associate lights with houses
                            # The collision_rect covers the base of the house
                            # However, windows (lights) are usually above the base (collision_rect)
                            # Let's check if the light's X is within house X range and Y is slightly above
                            # Or just check if X is within and Y is within a reasonable vertical range
                            if (house.collision_rect.left <= light_center_x <= house.collision_rect.right and
                                house.collision_rect.top - house.tile_size * 5 <= light_center_y <= house.collision_rect.bottom):
                                house.associated_lights.append(light)
                                break
                    
                    # Load polygon lights for buildings
                    elif obj.name in building_light_names and hasattr(obj, 'points'):
                        # pytmx provides absolute coordinates in Point named tuples
                        # Convert to relative coordinates (relative to obj.x, obj.y)
                        polygon_points = [(p.x - obj.x, p.y - obj.y) for p in obj.points]
                        
                        building_light = BuildingLight(
                            x=obj.x,
                            y=obj.y,
                            polygon_points=polygon_points,
                            building_name=obj.name,
                            tile_size=self.tile_size
                        )
                        
                        # Create or get the group for this building
                        if obj.name not in self.building_light_groups:
                            self.building_light_groups[obj.name] = BuildingLightGroup(obj.name)
                        
                        self.building_light_groups[obj.name].add_light(building_light)
    
    def _load_smoke(self) -> None:
        """Load Smoke objects from the 'Smoke' object layer and create SmokeEmitters."""
        import re
        house_y_sort = {h.name: h.y for h in self.houses}

        for layer in self.tmx_data.visible_layers:
            if isinstance(layer, pytmx.TiledObjectGroup) and layer.name == "Smoke":
                for obj in layer:
                    m = re.match(r'Smoke_(House_\d+)', obj.name)
                    if not m:
                        continue
                    house_name = m.group(1)
                    y_sort = house_y_sort.get(house_name, obj.y + obj.height)
                    self.smoke_emitters.append(SmokeEmitter(
                        outlet_x=obj.x,
                        outlet_y=obj.y + obj.height,  # bottom edge = chimney mouth
                        outlet_width=obj.width,
                        y_sort=y_sort,
                    ))

    def _load_special_points(self) -> None:
        """Parse the 'Special' object layer and assign named pivot points to mills."""
        for layer in self.tmx_data.visible_layers:
            if isinstance(layer, pytmx.TiledObjectGroup) and layer.name == "Special":
                for obj in layer:
                    if obj.name == "Mill_Blades":
                        for mill in self.mills:
                            mill.set_blade_pivot(obj.x, obj.y)

    def update_mills(self, dt: float) -> None:
        """Advance blade rotation for all mills (call once per frame when not paused)."""
        for mill in self.mills:
            mill.update_blades(dt)

    def _load_movements(self) -> None:
        """Load NPC movement zones from the 'Movements' object layer."""
        for layer in self.tmx_data.visible_layers:
            if isinstance(layer, pytmx.TiledObjectGroup) and layer.name == "Movements":
                for obj in layer:
                    if obj.name == "Sheep":
                        self.sheep.append(
                            Sheep(obj.x, obj.y, obj.width, obj.height, self.tile_size)
                        )

    def update_sheep(self, dt: float, player_rect: pygame.Rect = None) -> None:
        """Advance all sheep NPCs (call once per frame when not paused)."""
        for sheep in self.sheep:
            sheep.update(dt, player_rect)

    def update_fields(self, dt: float) -> None:
        """Advance wind animation for all fields (call once per frame)."""
        for field in self.fields:
            field.update(dt)

    def update_smoke(self, dt: float, current_time: datetime.datetime) -> None:
        """Advance all smoke emitters (call once per frame when not paused)."""
        for emitter in self.smoke_emitters:
            emitter.update(dt, current_time)

    def update_lights(self, current_time: datetime.datetime) -> None:
        """Update all lights (flicker, on/off state)."""
        # Update individual house lights
        for light in self.lights:
            light.update(current_time)
        
        # Update building light groups (handles timing and individual light flicker)
        for group in self.building_light_groups.values():
            group.update(current_time)

    def check_object_collision(self, rect: pygame.Rect) -> bool:
        """Check if the given rect collides with any map objects (houses, trees, sheep, or water)."""
        for house in self.houses:
            if house.collision_rect.colliderect(rect):
                return True
        for tree in self.trees:
            if tree.collision_rect.colliderect(rect):
                return True
        for sheep in self.sheep:
            if sheep.collision_rect.colliderect(rect):
                return True
        for water in self.waters:
            if water.collides_with_rect(rect):
                return True
        return False


    def is_walkable(self, x: int, y: int) -> bool:
        """Check if tile is walkable.
        
        Args:
            x: Grid X coordinate.
            y: Grid Y coordinate.
            
        Returns:
            bool: True if walkable, False otherwise.
        """
        if 0 <= x < self.width and 0 <= y < self.height:
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
        # width and height are used for logical collision and sorting.
        # They should remain stable even if animation frames have slightly different sizes.
        self.width: int = tile_size
        self.height: int = self.sprite.get_height()
        self.scaled_sprite_cache: Dict[float, Dict[int, pygame.Surface]] = {}
        
        # Movement state
        self.vel_x: float = 0.0
        self.vel_y: float = 0.0
        self.was_moving: bool = False
        self.frame_distance_px: float = 0.0  # pixels actually moved this frame, read and reset by Game
        self.footstep_sounds: List[pygame.mixer.Sound] = []
        self.last_sound_index: int = -1
        self.current_sound: Optional[pygame.mixer.Sound] = None
        # Channel 0 is reserved exclusively for footsteps (see game.py mixer init).
        self.footstep_channel: pygame.mixer.Channel = pygame.mixer.Channel(0)
    
    def set_footstep_sounds(self, sounds: List[pygame.mixer.Sound]) -> None:
        """Assign footstep sounds to the player.
        
        Args:
            sounds: List of pygame Sound objects for footsteps.
        """
        self.footstep_sounds = sounds

    def stop_footstep_sound(self) -> None:
        """Stop any currently playing footstep sound."""
        self.footstep_channel.stop()
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
            if is_moving:
                # Check if we just started moving, or if the dedicated channel stopped playing
                needs_sound = not self.was_moving or self.footstep_channel.get_sound() != self.current_sound

                if needs_sound:
                    # Started moving or sound stopped - pick a new sound
                    available_indices = [i for i in range(len(self.footstep_sounds)) if i != self.last_sound_index]
                    if not available_indices:  # only 1 sound available or empty
                        available_indices = [0] if self.footstep_sounds else []

                    if available_indices:
                        self.last_sound_index = random.choice(available_indices)
                        self.current_sound = self.footstep_sounds[self.last_sound_index]
                        self.footstep_channel.play(self.current_sound, loops=-1)
                        self.footstep_channel.set_volume(FOOT_STEP_VOLUME)
            elif not is_moving and self.was_moving:
                # Stopped moving
                self.stop_footstep_sound()

        self.frame_distance_px = 0.0
        if is_moving:
            move_x = self.vel_x * self.speed * dt
            move_y = self.vel_y * self.speed * dt

            if move_x != 0:
                new_x = self.x + move_x
                if self.can_move_to(new_x, self.y, game_map):
                    self.frame_distance_px += abs(move_x)
                    self.x = new_x

            if move_y != 0:
                new_y = self.y + move_y
                if self.can_move_to(self.x, new_y, game_map):
                    self.frame_distance_px += abs(move_y)
                    self.y = new_y

        direction = self._determine_direction(is_moving)
        self.animator.update(dt, direction, is_moving)
        self.sprite = self.animator.get_current_frame()
        self.source_sprite = self.animator.get_current_source_frame()
        # self.width and self.height are kept stable for collision consistency
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
        # Use a slightly smaller height for the collision box to prevent being "stuck"
        # exactly at the edge of a collision box when moving from top to bottom.
        collision_height = self.tile_size / 2 - 2
        collision_y = y + self.height - collision_height
        
        # Check collision with objects (houses)
        # Use round instead of int for slightly more accurate positioning
        player_rect = pygame.Rect(
            int(round(x)), 
            int(round(collision_y)), 
            int(self.width), 
            int(collision_height)
        )
        if game_map.check_object_collision(player_rect):
            return False

        # Get the four corners of the player collision box (feet area)
        # Inset the corners slightly to allow for easier movement through tight spaces
        margin = 2
        corners = [
            (x + margin, collision_y),  # top-left of collision area
            (x + self.width - 1 - margin, collision_y),  # top-right of collision area
            (x + margin, y + self.height - 1),  # bottom-left
            (x + self.width - 1 - margin, y + self.height - 1)  # bottom-right
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
        
        # Determine initial zoom index from constant if possible
        try:
            self.zoom_index: int = self.zoom_levels.index(MAP_START_ZOOM)
        except ValueError:
            self.zoom_index = 1.25  # Default fallback
            
        self.camera.set_zoom(self.zoom_levels[self.zoom_index])
        
        # Load TMX map
        tmx_path = os.path.join('assets', 'tiles', 'Map1.tmx')
        self.tmx_map: TMXMap = TMXMap(tmx_path)
        
        # Initialize map player
        self.map_player: MapPlayer = MapPlayer(
            START_X_POSITION,
            START_Y_POSITION,
            self.tmx_map.tile_size
        )

        # Transient VFX (e.g. splash ripples from thrown stones) — not part of the
        # static TMX data, so they live on GameMap rather than TMXMap.
        self.ripples: List[Ripple] = []

        # Shared clock driving the water wave flipbook animation (map_view.py).
        self.water_anim_time: float = 0.0

    def add_ripple(self, x: float, y: float, delay: float = 0.0, radius_cap: float = 18.0) -> None:
        self.ripples.append(Ripple(x, y, delay, radius_cap))

    def update_ripples(self, dt: float) -> None:
        self.ripples = [r for r in self.ripples if r.update(dt)]
    
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
        for sheep in self.tmx_map.sheep:
            sheep.on_zoom_change()
    
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
    
    def update(self, dt: float, current_time: datetime.datetime) -> None:
        """Update map state including player and camera.

        Args:
            dt: Delta time in seconds.
            current_time: Current in-game datetime for smoke scheduling.
        """
        self.map_player.update(dt, self.tmx_map)
        collision_height = self.map_player.tile_size / 2 - 2
        player_rect = pygame.Rect(
            int(round(self.map_player.x)),
            int(round(self.map_player.y + self.map_player.height - collision_height)),
            int(self.map_player.width),
            int(collision_height),
        )
        self.tmx_map.update_sheep(dt, player_rect)
        self.tmx_map.update_fields(dt)
        self.tmx_map.update_smoke(dt, current_time)
        self.tmx_map.update_mills(dt)
        self.update_ripples(dt)
        self.water_anim_time += dt
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

    def check_player_in_area(self, area_name: str) -> bool:
        """Check if player is currently inside a named area.
        
        Args:
            area_name: The name of the area to check (must exist in tmx_map.areas).
            
        Returns:
            bool: True if player intersects the area.
        """
        if area_name not in self.tmx_map.areas:
            return False
            
        area_rect = self.tmx_map.areas[area_name]
        
        # Calculate player collision box (feet area)
        # Similar logic to MapPlayer.can_move_to
        collision_height = self.map_player.tile_size / 2 - 2
        collision_y = self.map_player.y + self.map_player.height - collision_height
        
        player_rect = pygame.Rect(
            int(round(self.map_player.x)), 
            int(round(collision_y)), 
            int(self.map_player.width), 
            int(collision_height)
        )
        
        return area_rect.colliderect(player_rect)
