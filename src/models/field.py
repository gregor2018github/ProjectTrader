import pygame
import os
import random
import math
from typing import List, Tuple, Dict, Optional

from ..config.constants import TILE_SIZE


class Field:
    """Represents a rectangular field object on the map.

    Scatters randomly-chosen crop sprites across every tile within the
    TMX object bounding rect.  Sprites are pre-placed once at load time
    and cached per zoom level to avoid per-frame allocations.
    """

    def __init__(self, x: float, y: float, width: float, height: float, name: str) -> None:
        """Initialize the field.

        Args:
            x: World X of the top-left corner (TMX rectangle object origin).
            y: World Y of the top-left corner (TMX rectangle object origin).
            width: Field width in world pixels.
            height: Field height in world pixels.
            name: Field name from Tiled (e.g. 'Wheat'). Used to discover sprites
                  named ``{name_lower}_1.png``, ``{name_lower}_2.png``, …
        """
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.name = name

        # Loaded source images (one per sprite variant)
        self.images: List[pygame.Surface] = []
        # Per-zoom scaled image lists
        self.scaled_sprite_cache: Dict[float, List[pygame.Surface]] = {}
        # Fixed random placement: (world_cx, world_by, sprite_idx)
        self.sprite_placements: List[Tuple[float, float, int]] = []

        self._load_images()
        if self.images:
            self._generate_placements()

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _load_images(self) -> None:
        """Discover and load all sprite variants for this field type.

        Looks for ``assets/map_sprites/fields/{name_lower}_1.png``,
        ``_2.png``, … until the next index is missing.
        """
        base = self.name.lower()
        i = 1
        while True:
            path = os.path.join('assets', 'map_sprites', 'fields', f'{base}_{i}.png')
            if not os.path.exists(path):
                break
            try:
                self.images.append(pygame.image.load(path).convert_alpha())
            except pygame.error as e:
                print(f"Failed to load field image: {path} - {e}")
                break
            i += 1

        if not self.images:
            print(f"No field sprites found for '{self.name}' in assets/map_sprites/fields/")

    def _generate_placements(self) -> None:
        """Pre-generate one random sprite assignment per tile in the field bounds.

        Each placement stores:
            world_cx  – horizontal center of the tile in world pixels
            world_by  – bottom edge of the tile in world pixels (used for
                        y-sort and bottom-aligned drawing)
            sprite_idx – index into self.images
        """
        col_start = math.floor(self.x / TILE_SIZE)
        col_end   = math.floor((self.x + self.width  - 1) / TILE_SIZE)
        row_start = math.floor(self.y / TILE_SIZE)
        row_end   = math.floor((self.y + self.height - 1) / TILE_SIZE)

        n = len(self.images)
        for col in range(col_start, col_end + 1):
            for row in range(row_start, row_end + 1):
                world_cx = col * TILE_SIZE + TILE_SIZE / 2.0
                world_by = float((row + 1) * TILE_SIZE)
                sprite_idx = random.randint(0, n - 1)
                self.sprite_placements.append((world_cx, world_by, sprite_idx))

    # ------------------------------------------------------------------
    # Rendering helpers
    # ------------------------------------------------------------------

    def get_scaled_sprites(self, zoom: float) -> List[pygame.Surface]:
        """Return a zoom-cached list of scaled surfaces.

        Each sprite is scaled so that its width equals 110 % of one tile
        (slight overlap between adjacent sprites).  Height scales
        proportionally to preserve the original aspect ratio.

        Uses ``smoothscale`` when shrinking and ``scale`` when enlarging,
        matching the pattern in house.py.
        """
        zoom_key = round(float(zoom), 3)
        if zoom_key not in self.scaled_sprite_cache:
            target_width = max(1, int(round(TILE_SIZE * zoom * 1.1)))
            scaled: List[pygame.Surface] = []
            for img in self.images:
                orig_w = img.get_width()
                orig_h = img.get_height()
                target_h = max(1, int(round(orig_h * (target_width / orig_w))))
                if target_width >= orig_w:
                    scaled.append(pygame.transform.scale(img, (target_width, target_h)))
                else:
                    scaled.append(pygame.transform.smoothscale(img, (target_width, target_h)))
            self.scaled_sprite_cache[zoom_key] = scaled
        return self.scaled_sprite_cache[zoom_key]
