import pygame
import os
from typing import Optional, Dict

class House:
    """Represents a house object on the map."""
    
    def __init__(self, x: float, y: float, file_name: str, 
                 tiles_to_right: int, tiles_up: int,
                 collision_to_right: int, collision_up: int,
                 tile_size: int):
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
        # The point (x, y) is the bottom-left corner of the image AND the anchor for collision.
        # "Collision from this point up" means the box extends upwards (negative Y).
        collision_width = self.collision_to_right * self.tile_size
        collision_height = self.collision_up * self.tile_size
        
        # Rect(left, top, width, height)
        # Top is y - height
        self.collision_rect = pygame.Rect(
            self.x, 
            self.y - collision_height, 
            collision_width, 
            collision_height
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
