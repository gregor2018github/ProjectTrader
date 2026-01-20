import pygame
import random
import datetime
import math
from typing import Optional

from ..config.constants import (
    LIGHT_PROBABILITY, LIGHT_START_HOUR_MIN, LIGHT_START_HOUR_RANGE,
    LIGHT_DURATION_MIN, LIGHT_DURATION_RANGE,
    BUILDING_LIGHT_PROBABILITY, BUILDING_LIGHT_START_HOUR_MIN, BUILDING_LIGHT_START_HOUR_RANGE,
    BUILDING_LIGHT_DURATION_MIN, BUILDING_LIGHT_DURATION_RANGE
)


class Light:
    """Represents a rectangular window light source.
    
    The light consists of:
    1. A brightly glowing window rectangle (the window itself)
    2. A subtle, soft ambient glow around the window
    """

    def __init__(self, x: float, y: float, width: float, height: float, tile_size: int):
        """Initialize the rectangular light.

        Args:
            x: World X coordinate (top-left of rectangle).
            y: World Y coordinate (top-left of rectangle).
            width: Width of the window rectangle in world units.
            height: Height of the window rectangle in world units.
            tile_size: Size of one tile in pixels.
        """
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.tile_size = tile_size

        # Y-sort position (bottom of window for proper layering)
        self.y_sort = y + height

        # Color configuration - warm candlelight
        self.window_color = (255, 180, 80)  # Warm orange for window glow
        self.glow_color = (255, 200, 120)   # Slightly brighter for ambient glow

        # Flickering properties
        self.flicker_offset = random.random() * 100
        self.flicker_speed = 0.03 + random.random() * 0.04  # Slow, gentle flicker
        self.current_intensity = 1.0  # Multiplier for intensity

        # Activation logic
        self.is_active_tonight = False
        self.start_hour = 0.0
        self.end_hour = 0.0
        self.last_date_check = None
        
        # Cache for scaled surfaces (zoom level -> surface)
        self._surface_cache: dict = {}
        self._last_cache_zoom = -1.0

    def _create_light_surface(self, zoom: float) -> pygame.Surface:
        """Create the window light surface (no ambient glow).
        
        Args:
            zoom: Current camera zoom level.
            
        Returns:
            Surface with the window light effect.
        """
        # Calculate scaled dimensions
        scaled_width = max(1, int(self.width * zoom))
        scaled_height = max(1, int(self.height * zoom))
        
        # No glow extension - surface is exactly window size
        surface = pygame.Surface((scaled_width, scaled_height), pygame.SRCALPHA)
        
        # Create light effect within the window
        window_alpha = int(180 * self.current_intensity)
        window_alpha = max(0, min(255, window_alpha))
        
        # Draw base window fill
        surface.fill((*self.window_color, window_alpha))
        
        # Add a slightly brighter center/inner part for a bit of depth
        if scaled_width > 4 and scaled_height > 4:
            inner_rect = pygame.Rect(1, 1, scaled_width - 2, scaled_height - 2)
            inner_alpha = int(min(255, window_alpha * 1.1))
            pygame.draw.rect(surface, (*self.window_color, inner_alpha), inner_rect)
        
        return surface

    def update(self, current_time: datetime.datetime) -> None:
        """Update light state and flicker."""
        # Check if we need to reschedule for a new day
        # We shift the time by 12 hours so the transition happens at 12:00 midday
        scheduling_time = current_time - datetime.timedelta(hours=12)
        current_cycle_date = scheduling_time.strftime("%Y-%m-%d")
        
        if self.last_date_check != current_cycle_date:
            self._schedule_for_night(current_time)
            self.last_date_check = current_cycle_date
            
        # Update flickering if active
        if self.is_on(current_time):
            self.flicker_offset += self.flicker_speed
            
            # Gentle sine wave based flicker
            wave = math.sin(self.flicker_offset) 
            # Small random noise for organic feel
            noise = (random.random() - 0.5) * 0.05
            
            # Subtle intensity variation (0.9 to 1.0 range for gentle flicker)
            self.current_intensity = 0.95 + (wave * 0.03 + noise)
            self.current_intensity = max(0.85, min(1.0, self.current_intensity))
            
            # Invalidate cache when intensity changes significantly
            self._surface_cache.clear()
        else:
            self.current_intensity = 1.0

    def _schedule_for_night(self, current_time: datetime.datetime) -> None:
        """Decide if and when this light turns on for the upcoming night."""
        # Decide if active tonight based on probability constant
        self.is_active_tonight = random.random() < LIGHT_PROBABILITY
        
        if self.is_active_tonight:
            # Random start time based on constants
            self.start_hour = LIGHT_START_HOUR_MIN + random.random() * LIGHT_START_HOUR_RANGE
            
            # Duration based on constants
            duration = LIGHT_DURATION_MIN + random.random() * LIGHT_DURATION_RANGE
            self.end_hour = self.start_hour + duration
            
        # Clear cache on new schedule
        self._surface_cache.clear()

    def is_on(self, current_time: datetime.datetime) -> bool:
        """Check if the light is on at this time."""
        if not self.is_active_tonight:
            return False
            
        hour = current_time.hour + current_time.minute / 60.0
        
        # Handle midnight wrap
        effective_hour = hour
        if hour < 12:
            effective_hour += 24
            
        return self.start_hour <= effective_hour <= self.end_hour

    def get_render_data(self, camera_zoom: float) -> tuple[pygame.Surface, int]:
        """Get the current surface for rendering.
        
        Args:
            camera_zoom: Current camera zoom level.
            
        Returns:
            Tuple of (surface, glow_extend) where glow_extend is 0.
        """
        # Create surface (cache is cleared on intensity change)
        surface = self._create_light_surface(camera_zoom)
        
        # No glow extension anymore
        return surface, 0


class BuildingLight:
    """Represents a polygon-shaped window light source for big buildings.
    
    Unlike regular Light objects which are individual rectangles, BuildingLight
    objects are grouped by building name (e.g., 'Townhall', 'Church') and share
    their on/off timing as a group.
    """

    def __init__(self, x: float, y: float, polygon_points: list[tuple[float, float]], 
                 building_name: str, tile_size: int):
        """Initialize the polygon light.

        Args:
            x: World X coordinate (origin point of polygon).
            y: World Y coordinate (origin point of polygon).
            polygon_points: List of (x, y) tuples representing polygon vertices
                           relative to the origin point.
            building_name: Name of the building (e.g., 'Townhall', 'Church').
            tile_size: Size of one tile in pixels.
        """
        self.x = x
        self.y = y
        self.polygon_points = polygon_points
        self.building_name = building_name
        self.tile_size = tile_size

        # Calculate bounding box for the polygon
        abs_points = [(x + px, y + py) for px, py in polygon_points]
        min_x = min(p[0] for p in abs_points)
        max_x = max(p[0] for p in abs_points)
        min_y = min(p[1] for p in abs_points)
        max_y = max(p[1] for p in abs_points)
        
        self.bbox_x = min_x
        self.bbox_y = min_y
        self.width = max_x - min_x
        self.height = max_y - min_y

        # Y-sort position (bottom of polygon for proper layering)
        self.y_sort = max_y

        # Color configuration - warm candlelight
        self.window_color = (255, 180, 80)  # Warm orange for window glow

        # Flickering properties
        self.flicker_offset = random.random() * 100
        self.flicker_speed = 0.03 + random.random() * 0.04
        self.current_intensity = 1.0

        # Reference to the group (will be set by BuildingLightGroup)
        self.group: Optional['BuildingLightGroup'] = None
        
        # Cache for scaled surfaces
        self._surface_cache: dict = {}

    def _create_light_surface(self, zoom: float) -> pygame.Surface:
        """Create the polygon light surface.
        
        Args:
            zoom: Current camera zoom level.
            
        Returns:
            Surface with the polygon light effect.
        """
        # Calculate scaled dimensions
        scaled_width = max(1, int(self.width * zoom))
        scaled_height = max(1, int(self.height * zoom))
        
        surface = pygame.Surface((scaled_width, scaled_height), pygame.SRCALPHA)
        
        # Calculate window alpha based on intensity
        window_alpha = int(180 * self.current_intensity)
        window_alpha = max(0, min(255, window_alpha))
        
        # Scale polygon points relative to bounding box top-left
        scaled_points = []
        for px, py in self.polygon_points:
            # Convert from origin-relative to bbox-relative and scale
            abs_x = self.x + px
            abs_y = self.y + py
            rel_x = (abs_x - self.bbox_x) * zoom
            rel_y = (abs_y - self.bbox_y) * zoom
            scaled_points.append((rel_x, rel_y))
        
        # Draw the polygon
        if len(scaled_points) >= 3:
            pygame.draw.polygon(surface, (*self.window_color, window_alpha), scaled_points)
        
        return surface

    def update(self, current_time: datetime.datetime) -> None:
        """Update light flicker (timing is managed by group)."""
        if self.group and self.group.is_on(current_time):
            self.flicker_offset += self.flicker_speed
            
            # Gentle sine wave based flicker
            wave = math.sin(self.flicker_offset)
            noise = (random.random() - 0.5) * 0.05
            
            self.current_intensity = 0.95 + (wave * 0.03 + noise)
            self.current_intensity = max(0.85, min(1.0, self.current_intensity))
            
            self._surface_cache.clear()
        else:
            self.current_intensity = 1.0

    def is_on(self, current_time: datetime.datetime) -> bool:
        """Check if the light is on (delegated to group)."""
        if self.group:
            return self.group.is_on(current_time)
        return False

    def get_render_data(self, camera_zoom: float) -> tuple[pygame.Surface, int]:
        """Get the current surface for rendering.
        
        Args:
            camera_zoom: Current camera zoom level.
            
        Returns:
            Tuple of (surface, glow_extend) where glow_extend is 0.
        """
        surface = self._create_light_surface(camera_zoom)
        return surface, 0


class BuildingLightGroup:
    """Manages a group of BuildingLight objects that share timing.
    
    All lights in a group (e.g., all 'Townhall' lights) turn on and off together,
    but each light still has its own flickering effect.
    """

    def __init__(self, name: str):
        """Initialize the building light group.
        
        Args:
            name: Name of the building group (e.g., 'Townhall', 'Church').
        """
        self.name = name
        self.lights: list[BuildingLight] = []
        
        # Activation logic (shared by all lights in group)
        self.is_active_tonight = False
        self.start_hour = 0.0
        self.end_hour = 0.0
        self.last_date_check: Optional[str] = None

    def add_light(self, light: BuildingLight) -> None:
        """Add a light to this group.
        
        Args:
            light: The BuildingLight to add.
        """
        light.group = self
        self.lights.append(light)

    def update(self, current_time: datetime.datetime) -> None:
        """Update group scheduling and all lights in the group."""
        # Check if we need to reschedule for a new day
        scheduling_time = current_time - datetime.timedelta(hours=12)
        current_cycle_date = scheduling_time.strftime("%Y-%m-%d")
        
        if self.last_date_check != current_cycle_date:
            self._schedule_for_night(current_time)
            self.last_date_check = current_cycle_date
        
        # Update individual lights
        for light in self.lights:
            light.update(current_time)

    def _schedule_for_night(self, current_time: datetime.datetime) -> None:
        """Decide if and when this building's lights turn on for the night.
        
        Building lights are always on every night (unlike regular house windows),
        and they stay on longer.
        """
        # Decide if active tonight based on probability constant
        self.is_active_tonight = random.random() < BUILDING_LIGHT_PROBABILITY
        
        if self.is_active_tonight:
            # Random start time based on constants
            self.start_hour = BUILDING_LIGHT_START_HOUR_MIN + random.random() * BUILDING_LIGHT_START_HOUR_RANGE
            
            # Duration based on constants
            duration = BUILDING_LIGHT_DURATION_MIN + random.random() * BUILDING_LIGHT_DURATION_RANGE
            self.end_hour = self.start_hour + duration
        
        # Clear caches on all lights
        for light in self.lights:
            light._surface_cache.clear()

    def is_on(self, current_time: datetime.datetime) -> bool:
        """Check if the building lights are on at this time."""
        if not self.is_active_tonight:
            return False
            
        hour = current_time.hour + current_time.minute / 60.0
        
        # Handle midnight wrap
        effective_hour = hour
        if hour < 12:
            effective_hour += 24
            
        return self.start_hour <= effective_hour <= self.end_hour
