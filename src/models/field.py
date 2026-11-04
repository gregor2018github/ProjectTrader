import datetime
import json
import pygame
import os
import random
import math
from typing import Any, List, Tuple, Dict, Optional

from ..config.constants import FIELD_PLANT_SPREAD_DAYS, FIELD_STILL_STAGES, TILE_SIZE
from .crop_growth import CropGrowth, field_season

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

# Fields with nothing sown: the ground tiles show the ploughed earth, there are
# no crop sprites to scatter
BARE_FIELDS = {"Ploughed"}

# Every crop is a folder in here, see crop_sprite_paths()
CROPS_DIR = os.path.join('assets', 'map_sprites', 'fields')

# Furrows, drawn over a field's inner tiles while the crop there lies bare
# (the edge tiles are its headland, ragged dirt in the ground tiles)
_FURROW_VARIANTS = 3          # tiles of each kind, their grain and clods drawn differently
_FURROW_SEED = 7
_FURROW_ZOOMS_KEPT = 2        # scaled furrow overlays kept per field
_FURROW_LIGHT = (255, 226, 190)
_FURROW_LIGHT_ALPHA = 0.8     # how strongly the lit wall and ridges brighten the soil, for the shade above 1
_FURROW_DROP = TILE_SIZE / 2 - 2   # world px the furrows lie lower than their tiles, onto the plants' feet
_FURROW_MIN_ALPHA = 12        # fainter shading is left out, so most of the overlay is clear and blits quickly


class Field:
    """Represents a rectangular field object on the map.

    Scatters crop sprites across the field's inner tiles, one plant per
    tile; the tiles along its edge are the headland, ragged dirt in the
    ground tiles, and stay empty.  The crop grows through the stages of its
    crop.json (crop_growth.py): every stage's sprites are loaded into
    ``images``, and each plant shows a variant of the stage it has reached
    (``sprite_placements``, renewed by ``update_growth()``; ``None`` while it
    is at a stage without sprites, the bare field).  While the field lies
    bare its furrows show (``furrow_overlay()``), fading out as it is sown
    and back in as it is harvested.  The first FIELD_STILL_STAGES stages
    with sprites, the low sprouts, do not sway in the wind
    (``still_sprites``).  The crop follows the seasons of the game
    calendar; its Tiled object may set when (``field_season``):

        Sow_day      day of the year it is sown, 0 being the 1st of Spring (default FIELD_SOW_DAY)
        Harvest_day  day of the year it is harvested (default FIELD_HARVEST_DAY)

    Without them both are moved by up to FIELD_SEASON_JITTER_DAYS, the same
    for this field every game.

    Sprites are cached per zoom level to avoid per-frame allocations.

    Wind animation is driven by update(dt) and expressed as a per-sprite
    rotation around the sprite's bottom-centre.  Rotated surfaces are
    cached by (zoom, sprite_idx, angle_bin) so the expensive transform is
    only paid once.
    """

    def __init__(self, x: float, y: float, width: float, height: float, name: str,
                 outline: Optional[List[Tuple[float, float]]] = None, tmx_id: int = 0,
                 properties: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the field.

        Args:
            x: World X of the top-left corner (TMX rectangle object origin).
            y: World Y of the top-left corner (TMX rectangle object origin).
            width: Field width in world pixels.
            height: Field height in world pixels.
            name: Field name from Tiled (e.g. 'Wheat'). Used to discover sprites
                  named ``{name_lower}_1.png``, ``{name_lower}_2.png``, …
                  A name in ``BARE_FIELDS`` has none.
            outline: World points of a field drawn as a polygon in Tiled (x, y,
                     width and height are then its bounds), or None for a rectangle.
            tmx_id: The Tiled object's id, which its season and its plants' layout follow from.
            properties: The Tiled object's custom properties (Sow_day, Harvest_day).
        """
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.name = name
        self.tmx_id = tmx_id
        properties = properties or {}
        self.outline: List[Tuple[float, float]] = outline or [
            (x, y), (x + width, y), (x + width, y + height), (x, y + height)]

        self.inner_tiles: List[Tuple[int, int]] = []
        # Loaded source images: every variant of every stage, one after another
        self.images: List[pygame.Surface] = []
        # Per stage of the crop, the indices of its variants in self.images (empty for the bare field)
        self.stage_sprites: List[range] = []
        # Per-zoom scaled image lists
        self.scaled_sprite_cache: Dict[float, List[pygame.Surface]] = {}
        # One plant per tile: (world_cx, world_by, offset in days, variant pick 0..1)
        self.plants: List[Tuple[float, float, float, float]] = []
        # What each plant shows now: (world_cx, world_by, sprite_idx or None)
        self.sprite_placements: List[Tuple[float, float, Optional[int]]] = []
        # The same field lays out the same way every time, so a save shows what it showed
        self._rng = random.Random(f'field-{tmx_id}')
        # The furrows: how strongly they show now (0..1), and the overlay at each zoom level drawn lately
        self.furrow_alpha: float = 0.0
        self._furrow_cache: Dict[float, Tuple[pygame.Surface, float, float]] = {}

        stages = self._load_images()
        # The sprites of the first stages that have any, too low to sway
        with_sprites = [sprites for sprites in self.stage_sprites if sprites]
        self.still_sprites = frozenset(i for sprites in with_sprites[:FIELD_STILL_STAGES] for i in sprites)
        self.growth: Optional[CropGrowth] = None
        if self.images:
            self.growth = CropGrowth(stages, *field_season(tmx_id, properties))
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

    def _load_images(self) -> List[str]:
        """Load the sprite variants of every stage of this field's crop; returns the stage keys.

        The crop is the folder ``assets/map_sprites/fields/{name_lower}/``;
        see ``crop_sprite_paths()``.
        """
        if self.name in BARE_FIELDS:
            return []
        stages = crop_stages(self.name)
        for stage in stages:
            first = len(self.images)
            for path in crop_sprite_paths(self.name, stage):
                try:
                    self.images.append(pygame.image.load(path).convert_alpha())
                except pygame.error as e:
                    print(f"Failed to load field image: {path} - {e}")
                    break
            self.stage_sprites.append(range(first, len(self.images)))

        if not self.images:
            print(f"No field sprites found for '{self.name}' in {os.path.join(CROPS_DIR, self.name.lower())}")
        return stages

    def _generate_placements(self) -> None:
        """Place one plant on each inner tile of the field: inside its outline, and so are its eight neighbours
        (so the inner corner of an L, ragged like the edge, stays empty too).

        Each plant stores:
            world_cx  – horizontal center of the tile in world pixels
            world_by  – bottom edge of the tile in world pixels (used for
                        y-sort and bottom-aligned drawing)
            offset    – how many days ahead of the field (behind if negative)
                        it grows, within FIELD_PLANT_SPREAD_DAYS
            pick      – which variant of a stage it shows, 0..1

        Until the growth is first updated they all show the ripe crop.
        """
        col_start = math.floor(self.x / TILE_SIZE)
        col_end   = math.floor((self.x + self.width  - 1) / TILE_SIZE)
        row_start = math.floor(self.y / TILE_SIZE)
        row_end   = math.floor((self.y + self.height - 1) / TILE_SIZE)

        tiles = {(col, row) for col in range(col_start, col_end + 1) for row in range(row_start, row_end + 1)
                 if _inside(self.outline, (col + 0.5) * TILE_SIZE, (row + 0.5) * TILE_SIZE)}
        #: The inner tiles, the ones planted and ploughed
        self.inner_tiles = sorted(cell for cell in tiles if all(
            (cell[0] + dc, cell[1] + dr) in tiles for dc in (-1, 0, 1) for dr in (-1, 0, 1)))
        half = FIELD_PLANT_SPREAD_DAYS / 2.0
        for col, row in self.inner_tiles:
            world_cx = col * TILE_SIZE + TILE_SIZE / 2.0
            world_by = float((row + 1) * TILE_SIZE)
            self.plants.append((world_cx, world_by, self._rng.uniform(-half, half), self._rng.random()))
        ripe = len(self.stage_sprites) - 1
        self.sprite_placements = [(cx, by, self._variant(ripe, pick)) for cx, by, _, pick in self.plants]

    # ------------------------------------------------------------------
    # Growth
    # ------------------------------------------------------------------

    def _variant(self, stage: int, pick: float) -> Optional[int]:
        """The index in self.images of the variant `pick` (0..1) chooses at a stage; None if it has none."""
        sprites = self.stage_sprites[stage]
        return sprites[min(len(sprites) - 1, int(pick * len(sprites)))] if sprites else None

    def _place_plants(self, now: datetime.datetime) -> None:
        growth = self.growth
        self.sprite_placements = [(cx, by, self._variant(growth.plant_stage(now, offset), pick))
                                  for cx, by, offset, pick in self.plants]
        self.furrow_alpha = growth.furrows(now, FIELD_PLANT_SPREAD_DAYS)

    def furrow_overlay(self, zoom: float) -> Optional[Tuple[pygame.Surface, float, float]]:
        """The furrows over the inner tiles at `zoom`, see-through as far as they have faded, with the
        world point of its top-left corner; None while they do not show. Made once per zoom level."""
        alpha = round(self.furrow_alpha * 255)
        if alpha <= 0 or not self.inner_tiles:
            return None
        zoom_key = round(float(zoom), 3)
        if zoom_key not in self._furrow_cache:
            self._furrow_cache[zoom_key] = self._make_furrows(zoom)
            while len(self._furrow_cache) > _FURROW_ZOOMS_KEPT:
                self._furrow_cache.pop(next(iter(self._furrow_cache)))
        overlay, world_x, world_y = self._furrow_cache[zoom_key]
        if overlay.get_alpha() != alpha:   # set only when it changes: it re-encodes the RLE
            overlay.set_alpha(alpha, pygame.RLEACCEL)
        return overlay, world_x, world_y

    def _make_furrows(self, zoom: float) -> Tuple[pygame.Surface, float, float]:
        cells = set(self.inner_tiles)
        left, top = min(c for c, _ in cells), min(r for _, r in cells)
        right, bottom = max(c for c, _ in cells) + 1, max(r for _, r in cells) + 1
        flat = pygame.Surface(((right - left) * TILE_SIZE, (bottom - top) * TILE_SIZE), pygame.SRCALPHA)
        tiles = _furrow_tiles()
        for col, row in cells:
            # Each furrow runs across the field and is rounded off at the headland
            starts, ends = (col - 1, row) not in cells, (col + 1, row) not in cells
            kind = 'single' if starts and ends else 'first' if starts else 'last' if ends else 'mid'
            flat.blit(tiles[kind][(col * 7 + row * 13) % _FURROW_VARIANTS],
                      ((col - left) * TILE_SIZE, (row - top) * TILE_SIZE))
        size = (max(1, round(flat.get_width() * zoom)), max(1, round(flat.get_height() * zoom)))
        overlay = pygame.transform.smoothscale(flat, size) if zoom < 1 else pygame.transform.scale(flat, size)
        # Mostly clear: run-length encoded, the clear runs cost nothing to blit
        overlay.set_alpha(255, pygame.RLEACCEL)
        # Half a tile down, so the grooves run where the plants stand, on their tiles' bottom edge
        return overlay, float(left * TILE_SIZE), float(top * TILE_SIZE + _FURROW_DROP)

    def update_growth(self, now: datetime.datetime) -> None:
        """Bring the field and its plants to where the calendar has them at `now`
        (when the game is built or loaded, and every game hour)."""
        if self.growth:
            self.growth.update(now)
            self._place_plants(now)

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
        # Cut down to what is painted: the padding is half of it, and every crop is blitted each frame
        painted = rotated.get_bounding_rect()
        rotated = rotated.subsurface(painted).copy()
        # Draw so the centre of the rotated image lands at (screen_x, screen_y)
        result = (rotated, -(RW // 2) + painted.x, -(RH // 2) + painted.y)
        self._rotated_cache[cache_key] = result
        return result


def _furrow_shade(d: float) -> float:
    """Brightness factor across a furrow, d = px from its centre line (as plough_field.py baked them)."""
    groove = 0.40 * math.exp(-(d / 2.7) ** 2)             # the dark bottom
    wall = 0.12 * (d / 3.5) * math.exp(-(d / 3.5) ** 2)    # lit east wall, shaded west wall
    ridge = 0.09 * math.exp(-((abs(d) - 9.5) / 3.0) ** 2)  # the turned-up soil either side
    return 1.0 - groove + wall + ridge


_FURROW_TILES: Dict[str, List[pygame.Surface]] = {}


def _furrow_tiles() -> Dict[str, List[pygame.Surface]]:
    """{'first' | 'mid' | 'last' | 'single': variant tiles}: a furrow across the tile's middle, rounded off
    at the left of the first tile, the right of the last and both ends of a single one. Each is drawn
    upright, as plough_field.py baked them, and turned on its side. Black where it darkens the soil, light where it
    brightens it, so laid over any dirt it shades it as the shade factor says. Made once."""
    if _FURROW_TILES:
        return _FURROW_TILES
    rng = random.Random(_FURROW_SEED)
    centre = TILE_SIZE / 2 - 0.5
    for kind in ('first', 'mid', 'last', 'single'):
        _FURROW_TILES[kind] = []
        for _ in range(_FURROW_VARIANTS):
            tile = pygame.Surface((TILE_SIZE, TILE_SIZE), pygame.SRCALPHA)
            for y in range(TILE_SIZE):
                # Rounded ends: past the end, the groove fades as if measured from a cap
                past = (max(0.0, 9 - y) if kind in ('first', 'single') else 0.0) +                     (max(0.0, y - 22) if kind in ('last', 'single') else 0.0)
                for x in range(TILE_SIZE):
                    d = x - centre
                    if past:
                        dist = math.hypot(d, past * 1.3)
                        f = _furrow_shade(dist)
                        f += 0.06 * math.exp(-((dist - 6.5) / 2.0) ** 2) * min(1.0, past / 3)   # the plough's heap
                    else:
                        f = _furrow_shade(d)
                    f *= 1.0 + rng.uniform(-0.03, 0.03)
                    if abs(d) < 3 and rng.random() < 0.04 and not past:
                        f *= 0.8                                   # clods in the groove
                    if f < 1.0:
                        colour, alpha = (0, 0, 0), int((1.0 - f) * 255)
                    else:
                        colour, alpha = _FURROW_LIGHT, int((f - 1.0) * _FURROW_LIGHT_ALPHA * 255)
                    if alpha >= _FURROW_MIN_ALPHA:
                        tile.set_at((x, y), (*colour, min(255, alpha)))
            # Turned a quarter anticlockwise: the rounded top becomes the left end, the lit wall the upper
            _FURROW_TILES[kind].append(pygame.transform.rotate(tile, 90))
    return _FURROW_TILES


def crop_stages(name: str) -> List[str]:
    """The stage keys of a crop's crop.json, the bare field first; empty if it cannot be read."""
    try:
        with open(os.path.join(CROPS_DIR, name.lower(), 'crop.json'), encoding='utf-8') as file:
            return [stage['key'] for stage in json.load(file)['stages']]
    except (OSError, ValueError, KeyError, TypeError) as e:
        print(f"Cannot read the stages of the crop '{name}': {e}")
        return []


def crop_sprite_paths(name: str, stage: Optional[str] = None) -> List[str]:
    """The sprite variants of a crop at one growth stage, by number.

    A crop is a folder ``assets/map_sprites/fields/<crop>/`` whose crop.json
    lists its stages, from the bare field to the ripe crop (made and kept in
    the Sprite Manager's crops area); its sprites are
    ``<crop>_<stage>_1.png``, ``_2.png``, … until the next is missing.

    Args:
        name: The field's crop, e.g. 'Wheat'.
        stage: A stage key from crop.json; None for the last, the ripe crop.

    Returns:
        The paths found, empty if the crop or the stage has none.
    """
    crop = name.lower()
    folder = os.path.join(CROPS_DIR, crop)
    if stage is None:
        stages = crop_stages(name)
        if not stages:
            return []
        stage = stages[-1]
    paths = []
    while True:
        path = os.path.join(folder, f'{crop}_{stage}_{len(paths) + 1}.png')
        if not os.path.exists(path):
            return paths
        paths.append(path)


def _inside(points: List[Tuple[float, float]], px: float, py: float) -> bool:
    """Whether a point lies inside a polygon (even-odd rule)."""
    inside = False
    for (ax, ay), (bx, by) in zip(points, points[1:] + points[:1]):
        if (ay > py) != (by > py) and px < ax + (py - ay) * (bx - ax) / (by - ay):
            inside = not inside
    return inside
