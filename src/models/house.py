import pygame
import os
from typing import Optional, Dict

class House:
    """Represents a house object on the map."""
    
    def __init__(self, x: float, y: float, file_name: str, 
                 tiles_to_right: int, tiles_up: int,
                 collision_to_right: int, collision_up: int,
                 tile_size: int,
                 col_margin_right_pixel: int = 0,
                 col_margin_left_pixel: int = 0,
                 col_margin_up_pixel: int = 0,
                 col_margin_down_pixel: int = 0):
        """Initialize the house.
        
        Args:
            x: World X coordinate of the bottom-left corner.
            y: World Y coordinate of the bottom-left corner.
            file_name: Filename of the sprite image.
            tiles_to_right: Width of the object in tiles (informational).
            tiles_up: Height of the object in tiles (informational).
            collision_to_right: Width of collision box in tiles.
            collision_up: Height of collision box in tiles.
            tile_size: Size of one tile in pixels.
            col_margin_right_pixel: Extra pixels to add to the right of collision.
            col_margin_left_pixel: Extra pixels to add to the left of collision.
            col_margin_up_pixel: Extra pixels to add to the top of collision.
            col_margin_down_pixel: Extra pixels to add to the bottom of collision.
        """
        self.x = x
        self.y = y 
        self.file_name = file_name
        self.tiles_to_right = tiles_to_right
        self.tiles_up = tiles_up
        self.collision_to_right = collision_to_right
        self.collision_up = collision_up
        self.tile_size = tile_size
        
        self.image: Optional[pygame.Surface] = None
        self.scaled_image_cache: Dict[float, pygame.Surface] = {}
        
        self._load_image()
        
        # Calculate collision rect
        # The point (x, y) is the bottom-left corner of the image AND the anchor for base collision.
        # Base dimensions in pixels
        base_width = self.collision_to_right * self.tile_size
        base_height = self.collision_up * self.tile_size
        
        # Apply pixel margins:
        # Left margin adds/removes from the left side (x-axis)
        # Right margin adds/removes from the right side (width)
        # Up margin adds/removes from the top side (y-axis)
        # Down margin adds/removes from the bottom side (y-axis)
        
        final_x = self.x - col_margin_left_pixel
        final_width = base_width + col_margin_left_pixel + col_margin_right_pixel
        final_height = base_height + col_margin_up_pixel + col_margin_down_pixel
        
        # Rect(left, top, width, height)
        # top = (y - base_height) - up_margin
        # which is also: top = y - (base_height + up_margin)
        # but we also have down_margin which pushes the bottom down.
        # bottom = y + down_margin
        # top = bottom - final_height = (y + down_margin) - (base_height + up_margin + down_margin)
        # = y - base_height - up_margin
        
        self.collision_rect = pygame.Rect(
            final_x, 
            (self.y + col_margin_down_pixel) - final_height, 
            final_width, 
            final_height
        )

    def _load_image(self) -> None:
        """Load the house image from assets."""
        path = os.path.join('assets', 'map_sprites', 'houses', self.file_name)
        
        # Try finding the file, add extension if missing
        if not os.path.exists(path):
            if os.path.exists(path + '.png'):
                path = path + '.png'
        if os.path.exists(path):
            try:
                self.image = pygame.image.load(path).convert_alpha()
            except pygame.error as e:
                print(f"Failed to load house image: {path} - {e}")
        else:
             print(f"House image not found: {path} (original name: {self.file_name})")

    def get_scaled_sprite(self, zoom: float) -> Optional[pygame.Surface]:
        """Get the scaled sprite for the current zoom level."""
        if not self.image:
            return None
            
        zoom_key = round(float(zoom), 3)
        if zoom_key not in self.scaled_image_cache:
            original_width = self.image.get_width()
            original_height = self.image.get_height()
            
            target_width = max(1, int(round(original_width * zoom)))
            target_height = max(1, int(round(original_height * zoom)))
            
            if target_width >= original_width or target_height >= original_height:
                self.scaled_image_cache[zoom_key] = pygame.transform.scale(self.image, (target_width, target_height))
            else:
                self.scaled_image_cache[zoom_key] = pygame.transform.smoothscale(self.image, (target_width, target_height))
                
        return self.scaled_image_cache[zoom_key]

    @property
    def y_sort(self) -> float:
        """Get the Y coordinate for sorting (render order)."""
        return self.y
