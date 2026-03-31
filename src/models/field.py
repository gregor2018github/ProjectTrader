import pygame
import os
import random
import math
from typing import List, Tuple, Dict, Optional

from ..config.constants import TILE_SIZE

# ---------------------------------------------------------------------------
# Wind / sway constants
# ---------------------------------------------------------------------------

# Ambient background sway (always present)
_AMBIENT_AMP   = 1.5   # degrees peak
_AMBIENT_FREQ  = 0.7   # Hz  (period ≈ 1.4 s)
# Static position-based phase coefficients.  Using irrational-ish multipliers
# gives each stalk a unique, uncorrelated phase so they sway independently
# (like natural turbulence) without creating an obvious traveling wave.
_AMBIENT_PHASE_X = 0.17   # radians per world-pixel of world_cx
_AMBIENT_PHASE_Y = 0.13   # radians per world-pixel of world_by

# Wind gust
_GUST_AMP    = 8.0    # degrees peak lean (into wind direction)
_GUST_SPEED  = 180.0  # world-px / second the wave front advances
_GUST_WIDTH  = 200.0  # world-px: spatial extent of one gust wave
_GUST_MIN_INTERVAL = 8.0   # seconds between gusts (min)
_GUST_MAX_INTERVAL = 30.0  # seconds between gusts (max)

# Rotation quantisation: nearest 0.5° step keeps the cache small
_ANGLE_STEP = 0.5


class Field:
    """Represents a rectangular field object on the map.

    Scatters randomly-chosen crop sprites across every tile within the
    TMX object bounding rect.  Sprites are pre-placed once at load time
    and cached per zoom level to avoid per-frame allocations.

    Wind animation is driven by update(dt) and expressed as a per-sprite
    rotation around the sprite's bottom-centre.  Rotated surfaces are
    cached by (zoom, sprite_idx, angle_bin) so the expensive transform is
    only paid once.
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

        # Wind projection range (world_by - world_cx along the diagonal)
        if self.sprite_placements:
            projs = [world_by - world_cx for (world_cx, world_by, _) in self.sprite_placements]
            self._proj_min: float = min(projs)
            self._proj_max: float = max(projs)
        else:
            self._proj_min = 0.0
            self._proj_max = 1.0

        # Wind animation state
        self._time: float = 0.0
        self._gust_active: bool = False
        self._gust_front: float = 0.0
        self._next_gust_timer: float = random.uniform(_GUST_MIN_INTERVAL, _GUST_MAX_INTERVAL)

        # Cache: (zoom_key, sprite_idx, angle_bin) -> (surface, rel_x, rel_y)
        # rel_x/rel_y are the draw offsets relative to (screen_x, screen_y)
        self._rotated_cache: Dict[Tuple, Tuple] = {}

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

    # ------------------------------------------------------------------
    # Wind animation
    # ------------------------------------------------------------------

    def update(self, dt: float) -> None:
        """Advance wind state by dt seconds.

        Args:
            dt: Frame delta time in seconds.
        """
        self._time += dt

        if self._gust_active:
            self._gust_front += _GUST_SPEED * dt
            if self._gust_front > self._proj_max + _GUST_WIDTH:
                self._gust_active = False
                self._next_gust_timer = random.uniform(_GUST_MIN_INTERVAL, _GUST_MAX_INTERVAL)
        else:
            self._next_gust_timer -= dt
            if self._next_gust_timer <= 0.0:
                self._gust_active = True
                # Start the wave front before the earliest sprite so the gust
                # appears to arrive from outside the field.
                self._gust_front = self._proj_min - _GUST_WIDTH

    def get_sway_angle(self, world_cx: float, world_by: float) -> float:
        """Compute the current sway rotation angle (degrees) for one sprite.

        Positive = counter-clockwise (lean right), negative = clockwise (lean
        left / downwind).  The wind blows from the top-right toward the
        bottom-left, so gusts produce a negative (leftward) lean.

        Args:
            world_cx: Sprite centre X in world pixels.
            world_by: Sprite bottom Y in world pixels.

        Returns:
            Sway angle in degrees.
        """
        # Ambient background sway.  Each stalk has a fixed spatial phase offset
        # derived from its position so they move independently (no visible
        # traveling wave — that effect is reserved for the gust).
        static_phase = world_cx * _AMBIENT_PHASE_X + world_by * _AMBIENT_PHASE_Y
        ambient = _AMBIENT_AMP * math.sin(self._time * _AMBIENT_FREQ * 2.0 * math.pi + static_phase)

        # Gust contribution.  Projection along top-right → bottom-left diagonal:
        # small value = top-right (hit first), large value = bottom-left (hit last).
        gust = 0.0
        if self._gust_active:
            proj = world_by - world_cx
            dist_behind = self._gust_front - proj   # > 0 once front has passed
            if 0.0 <= dist_behind < _GUST_WIDTH:
                progress = dist_behind / _GUST_WIDTH  # 0 at leading edge, 1 at tail
                envelope = math.sin(progress * math.pi)  # smooth bell curve
                gust = -_GUST_AMP * envelope              # lean leftward/downwind

        return ambient + gust

    def get_sway_sprite(
        self, sprite_idx: int, zoom: float, angle_deg: float
    ) -> Tuple[pygame.Surface, int, int]:
        """Return a rotated sprite and its draw offsets relative to (screen_x, screen_y).

        The sprite is rotated around its bottom-centre so the roots stay fixed
        while the tips sway.  Results are cached per (zoom, sprite_idx, angle_bin).

        Args:
            sprite_idx: Index into the scaled sprite list.
            zoom: Current camera zoom.
            angle_deg: Sway angle in degrees (from get_sway_angle).

        Returns:
            Tuple of (surface, rel_x, rel_y) where the sprite should be drawn
            at (screen_x + rel_x + offset_x, screen_y + rel_y + offset_y).
        """
        zoom_key = round(float(zoom), 3)
        angle_bin = round(angle_deg / _ANGLE_STEP) * _ANGLE_STEP
        cache_key = (zoom_key, sprite_idx, angle_bin)

        if cache_key in self._rotated_cache:
            return self._rotated_cache[cache_key]

        scaled = self.get_scaled_sprites(zoom)
        base = scaled[sprite_idx]
        W, H = base.get_size()

        if abs(angle_bin) < _ANGLE_STEP / 2.0:
            # Effectively zero rotation — use base sprite directly
            result: Tuple[pygame.Surface, int, int] = (base, -(W // 2), -H)
            self._rotated_cache[cache_key] = result
            return result

        # Pad the sprite vertically so the centre of the padded surface
        # coincides with the bottom-centre of the original sprite.
        # pygame.transform.rotate() rotates around the image centre, so this
        # makes it effectively rotate around the sprite's root.
        # The sprite occupies the TOP half (y=0..H); the bottom half is empty.
        # Centre of W×2H surface = (W/2, H) = bottom edge of the sprite. ✓
        padded = pygame.Surface((W, 2 * H), pygame.SRCALPHA)
        padded.blit(base, (0, 0))
        rotated = pygame.transform.rotate(padded, angle_bin)

        RW, RH = rotated.get_size()
        # Draw so the centre of the rotated image lands at (screen_x, screen_y)
        result = (rotated, -(RW // 2), -(RH // 2))
        self._rotated_cache[cache_key] = result
        return result
