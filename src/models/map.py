"""Map model for the trading game.

This module contains the map logic including TMX loading, camera management,
player movement, collision detection, and map object management.
"""

import os
import datetime
import pygame
import pytmx
from typing import List, Dict, Set, Tuple, Any, Optional, Union

from ..config.constants import TILE_SIZE, MAP_START_ZOOM, START_X_POSITION, START_Y_POSITION
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
from .figurines.animals.sheep import Sheep
from .figurines.humans.player import MapPlayer
from .figurines.humans.npcs.npc import NPC
from .figurines.humans.npcs.trader_butcher import TraderButcher
from .figurines.patrol_path import PatrolPath
from .water import Water, Ripple, water_tile_variant

# How far (per RGB channel) a ground tile's average colour may sit from the
# confirmed water tiles' colour and still count as water art itself. Kept
# tight: the water tileset is a single flat blue, so anything genuinely made
# of water pixels lands well inside this, while grass/dirt tiles are nowhere
# near it. See TMXMap._match_water_tile_gids.
WATER_TILE_COLOR_TOLERANCE = 12



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
        self.npcs: List[NPC] = []
        self.waters: List[Water] = []
        # Grid cells covered by water (used for the animated water tile
        # rendering in map_view.py). Rasterized once at load time so the
        # render loop only ever needs an O(1) set lookup per visible tile.
        self.water_tiles: Set[Tuple[int, int]] = set()
        self.water_tile_variant: Dict[Tuple[int, int], int] = {}
        self.water_edge_tiles: Set[Tuple[int, int]] = set()
        self._tile_signature_cache: Dict[int, Optional[Tuple[float, float, float, int]]] = {}

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
                        # pytmx has already offset polygon points by the object's
                        # own position, so they are world coordinates as they come
                        # (same as the building lights below). Adding obj.x/obj.y
                        # again would double the offset for any Water object not
                        # sitting at the origin.
                        world_points = [(p.x, p.y) for p in obj.points]
                        self.waters.append(Water(obj.name or "Water", world_points))

    def _rasterize_water_tiles(self) -> None:
        """Compute which grid cells should render the animated water surface.

        A pure cell-*center*-in-polygon test (the original approach) can't
        agree with the hand-placed boundary tiles in the "Ground_Mid" layer:
        those edge/corner tiles are only *partly* water (the rest of the tile
        is cut away via the tile image's own alpha channel), so a cell whose
        centre happens to fall on the land side gets excluded even though the
        tile clearly shows water, while a cell whose centre falls on the
        water side gets the animated surface drawn as a *full* opaque square
        that overshoots the tile's actual (diagonal-cut) water area. Visually
        that showed up as the water effect eating into the grass on one bank
        and stopping short of the art on the other.

        So instead the polygon test is only used to discover, once, which
        Ground_Mid tile ids are actually the map's water tileset (by seeing
        which ids appear on cells the polygon is confident about), widened by
        _match_water_tile_gids to the ids that merely *look* the same (a bank
        tile whose water half never covers a cell centre is invisible to the
        polygon test). Every cell painted with one of those ids — anywhere on
        the map, boundary or interior — then gets the animated surface, and get_masked_water_frame
        (see map_view._draw_animated_water) clips it to that exact tile's own
        alpha shape, so partial edge tiles stay partial instead of being
        rounded up to a full square or dropped entirely.
        """
        ground_mid = None
        for layer in self.tmx_data.visible_layers:
            if isinstance(layer, pytmx.TiledTileLayer) and layer.name == "Ground_Mid":
                ground_mid = layer
                break

        polygon_cells: Set[Tuple[int, int]] = set()
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
                        polygon_cells.add((gx, gy))

        if ground_mid is not None and polygon_cells:
            water_gids: Set[int] = set()
            for (gx, gy) in polygon_cells:
                gid = ground_mid.data[gy][gx]
                if gid:
                    water_gids.add(gid)

            water_gids |= self._match_water_tile_gids(ground_mid, water_gids)

            for gy in range(self.height):
                row = ground_mid.data[gy]
                for gx in range(self.width):
                    if row[gx] in water_gids:
                        self.water_tiles.add((gx, gy))
        else:
            # No Ground_Mid layer (or no water polygons resolved any tile
            # ids) — fall back to the plain polygon test so water still
            # renders, just without sub-tile precision.
            self.water_tiles = polygon_cells

        for (gx, gy) in self.water_tiles:
            self.water_tile_variant[(gx, gy)] = water_tile_variant(gx, gy)
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                if (gx + dx, gy + dy) not in self.water_tiles:
                    self.water_edge_tiles.add((gx, gy))
                    break

    def _tile_color_signature(self, gid: int) -> Optional[Tuple[float, float, float, int]]:
        """Mean colour of a tile's opaque pixels plus its widest channel spread.

        Sampled on a coarse grid (every 4th pixel) — enough to tell one
        terrain family from another, cheap enough to run over every tile id
        the ground layer uses. Returns None for tiles with (almost) no
        opaque pixels, which carry no usable colour.
        """
        if gid in self._tile_signature_cache:
            return self._tile_signature_cache[gid]

        signature: Optional[Tuple[float, float, float, int]] = None
        image = self.tmx_data.get_tile_image_by_gid(gid)
        if image is not None:
            width, height = image.get_size()
            pixels = pygame.PixelArray(image)
            count = 0
            totals = [0, 0, 0]
            lows = [255, 255, 255]
            highs = [0, 0, 0]
            for y in range(0, height, 4):
                for x in range(0, width, 4):
                    color = image.unmap_rgb(pixels[x, y])
                    if color.a <= 200:
                        continue
                    count += 1
                    for i, channel in enumerate((color.r, color.g, color.b)):
                        totals[i] += channel
                        lows[i] = min(lows[i], channel)
                        highs[i] = max(highs[i], channel)
            pixels.close()
            if count >= 4:
                spread = max(highs[i] - lows[i] for i in range(3))
                signature = (totals[0] / count, totals[1] / count, totals[2] / count, spread)

        self._tile_signature_cache[gid] = signature
        return signature

    def _match_water_tile_gids(self, ground_mid: pytmx.TiledTileLayer, seed_gids: Set[int]) -> Set[int]:
        """Find further water tile ids that look like the confirmed ``seed_gids``.

        The cell-centre-in-polygon seeding in ``_rasterize_water_tiles`` only
        discovers a tile id if at least one cell painted with it has its
        *centre* inside a water polygon. A diagonal bank tile whose water half
        never happens to cover a cell centre anywhere on the map is therefore
        missed entirely, and those cells keep the flat, static tileset art
        while every neighbour animates — the artefact was plainly visible on
        the "grass in the top-right corner" bank tile.

        So the seed ids are additionally matched by appearance: any tile id
        used in the ground layer whose opaque pixels carry the same colour
        (within a small tolerance, and no more varied than the seeds) is the
        same water art, just cut to a different shape.
        """
        seed_signatures = [sig for sig in (self._tile_color_signature(gid) for gid in seed_gids) if sig]
        if not seed_signatures:
            return set()
        max_spread = max(sig[3] for sig in seed_signatures) + WATER_TILE_COLOR_TOLERANCE

        used_gids: Set[int] = set()
        for gy in range(self.height):
            row = ground_mid.data[gy]
            for gx in range(self.width):
                gid = row[gx]
                if gid and gid not in seed_gids:
                    used_gids.add(gid)

        matched: Set[int] = set()
        for gid in used_gids:
            signature = self._tile_color_signature(gid)
            if signature is None or signature[3] > max_spread:
                continue
            if any(
                all(abs(signature[i] - seed[i]) <= WATER_TILE_COLOR_TOLERANCE for i in range(3))
                for seed in seed_signatures
            ):
                matched.add(gid)
        return matched

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

    # Objects on the "Movements" layer whose name matches a key here become that
    # NPC, walking the polygon (or polyline) drawn for them in Tiled. Add a
    # trader by drawing a shape, naming it, and adding a line here.
    NPC_TYPES: Dict[str, Any] = {
        "Butcher_Market_Stall": TraderButcher,
    }

    def _load_movements(self) -> None:
        """Load NPC movement zones from the 'Movements' object layer.

        Sheep take a rectangle (they only wander left and right inside it).
        Human NPCs take a polygon or polyline, which they walk along.
        """
        for layer in self.tmx_data.visible_layers:
            if isinstance(layer, pytmx.TiledObjectGroup) and layer.name == "Movements":
                for obj in layer:
                    if obj.name == "Sheep":
                        self.sheep.append(
                            Sheep(obj.x, obj.y, obj.width, obj.height, self.tile_size)
                        )
                        continue

                    npc_class = self.NPC_TYPES.get(obj.name)
                    if npc_class is not None:
                        self._load_npc(npc_class, obj)

    def _load_npc(self, npc_class: Any, obj: Any) -> None:
        """Create one NPC from a Tiled object and put it on its path.

        Args:
            npc_class: The NPC subclass to instantiate.
            obj: The Tiled object, ideally carrying polygon or polyline points.
        """
        points = getattr(obj, "points", None)
        npc = npc_class(obj.x, obj.y, self.tile_size)
        if points:
            # Optional "margin" property on the Tiled object, in tiles: how far
            # to keep the walker off the polygon's own edges. Movement polygons
            # are traced along whole tiles, so without it he brushes the stall
            # he is standing at.
            margin = float(obj.properties.get("margin", 0.0)) * self.tile_size
            path = PatrolPath(points, closed=getattr(obj, "closed", True), margin=margin)
            if path:
                npc.set_path(path)
            else:
                npc.place_feet(obj.x, obj.y)
        else:
            # A plain point or rectangle: he simply stands there.
            npc.place_feet(obj.x, obj.y)
        self.npcs.append(npc)

    def update_sheep(self, dt: float, player_rect: pygame.Rect = None) -> None:
        """Advance all sheep NPCs (call once per frame when not paused)."""
        for sheep in self.sheep:
            sheep.update(dt, player_rect)

    def update_npcs(self, dt: float, current_time: datetime.datetime) -> None:
        """Advance all human NPCs (call once per frame when not paused)."""
        for npc in self.npcs:
            npc.update(dt, current_time)

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

    def update_markets(self, current_time: datetime.datetime) -> None:
        """Switch market booths between their open and closed sprites."""
        for house in self.houses:
            if isinstance(house, Market):
                house.update_sprite(current_time)

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
        for npc in self.tmx_map.npcs:
            npc.on_zoom_change()
    
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
        self.tmx_map.update_npcs(dt, current_time)
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
