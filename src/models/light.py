import pygame
import random
import datetime
import math


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
        current_date_str = current_time.strftime("%Y-%m-%d")
        if self.last_date_check != current_date_str:
            self._schedule_for_night(current_time)
            self.last_date_check = current_date_str
            
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
        # 40% chance of being active tonight
        self.is_active_tonight = random.random() < 0.4
        
        if self.is_active_tonight:
            # Random start time (17:30 to 22:00)
            self.start_hour = 17.5 + random.random() * 4.5
            
            # Duration (2 to 6 hours)
            duration = 2.0 + random.random() * 4.0
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
