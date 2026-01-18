import pygame
import os
from typing import Optional, Dict

class Tree:
    """Represents a tree object on the map."""
    
    def __init__(self, x: float, y: float, file_name: str, 
                 stem_position: float, stem_thick: float,
                 tile_size: int):
        """Initialize the tree.
        
        Args:
            x: World X coordinate of the bottom-left corner (from Tiled).
            y: World Y coordinate of the bottom-left corner (from Tiled).
            file_name: Filename of the sprite image (e.g., 'Tree_01.png').
            stem_position: Position of the stem center relative to x (in tiles).
            stem_thick: Thickness of the stem collision box (in tiles).
            tile_size: Size of one tile in pixels.
        """
        self.x = x
        self.y = y 
        self.file_name = file_name
        self.stem_position = stem_position
        self.stem_thick = stem_thick
        self.tile_size = tile_size
        
        # Calculate render sorting key (bottom of the object)
        self.y_sort = self.y
        
        self.image: Optional[pygame.Surface] = None
        self.scaled_image_cache: Dict[float, pygame.Surface] = {}
        
        self._load_image()
        
        # Calculate collision rect
        # Height is always 0.5 tiles
        collision_height = 0.5 * self.tile_size
        
        # Width is determined by stem_thick (assuming it's the full width)
        # "0.3 tiles around the stem center" - Interpreting Stem_Thick as the total width.
        # If it feels too thin in testing, we can adjust interpretation to radius (width * 2).
        collision_width = self.stem_thick * self.tile_size
        
        # Center of stem in world pixels
        center_x = self.x + (self.stem_position * self.tile_size)
        
        # Top-left of collision rect
        rect_left = center_x - (collision_width / 2)
        rect_top = self.y - collision_height
        
        self.collision_rect = pygame.Rect(
            rect_left,
            rect_top,
            collision_width,
            collision_height
        )

    def _load_image(self) -> None:
        """Load the tree image from assets."""
        if not self.file_name:
            return

        path = os.path.join('assets', 'map_sprites', 'trees', self.file_name)
        
        # Try finding the file, add extension if missing
        if not os.path.exists(path):
            if os.path.exists(path + '.png'):
                path = path + '.png'
        
        if os.path.exists(path):
            try:
                self.image = pygame.image.load(path).convert_alpha()
            except pygame.error as e:
                print(f"Failed to load tree image: {path} - {e}")
        else:
             print(f"Tree image not found: {path} (original name: {self.file_name})")

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
