"""Sheep NPC that wanders left and right within a defined zone on the map."""

import os
import random
import pygame
from typing import Dict

SHEEP_SPEED = 40.0          # pixels per second at base tile_size=32
STOP_CHANCE_PER_SEC = 0.15  # probability per second to stop mid-walk
STOP_MIN_DURATION = 10.0    # seconds
STOP_MAX_DURATION = 20.0    # seconds
SOUND_MIN_INTERVAL = 15.0   # minimum seconds between sheep sounds
SOUND_MAX_INTERVAL = 35.0   # maximum seconds between sheep sounds
EAT_CHANCE_PER_STOP = 0.35  # probability to start eating when a rest stop begins
EAT_MIN_DURATION = 3.0      # minimum eating duration in seconds
EAT_MAX_DURATION = 8.0      # maximum eating duration in seconds
EAT_FRAME_DURATIONS = (0.55, 0.22)  # seconds each eat frame is shown (eat1, eat2)
EAT_RETURN_PAUSE = 0.6      # static pause after eating before sheep can walk again


class Sheep:
    """An NPC sheep that walks left and right within a rectangular zone."""

    def __init__(
        self,
        zone_x: float,
        zone_y: float,
        zone_width: float,
        zone_height: float,
        tile_size: int,
    ) -> None:
        # Lazy import avoids circular dependency with map.py
        from ..map import DirectionalAnimator

        self.tile_size: int = tile_size
        self.sprite_width: int = int(1.5 * tile_size)  # 48 px at base zoom

        sprite_dir = os.path.join('assets', 'map_sprites', 'figurines', 'sheep')
        sprite_definitions: Dict = {
            "front": {
                "static": "sheep_right_static.png",
                "move": [],
            },
            "back": {
                "static": "sheep_right_static.png",
                "move": [],
            },
            "left": {
                "static": "sheep_left_static.png",
                "move": [
                    "sheep_left_move1.png",
                    "sheep_left_move2.png",
                    "sheep_left_move3.png",
                    "sheep_left_move4.png",
                ],
            },
            "right": {
                "static": "sheep_right_static.png",
                "move": [
                    "sheep_right_move1.png",
                    "sheep_right_move2.png",
                    "sheep_right_move3.png",
                    "sheep_right_move4.png",
                ],
            },
        }

        self.animator = DirectionalAnimator(
            base_path=sprite_dir,
            sprite_definitions=sprite_definitions,
            target_width=self.sprite_width,
            fallback_static="sheep_right_static.png",
        )
        # Sheep are slower than the player — use a wider frame interval
        self.animator.frame_interval *= 1.5

        self.sprite: pygame.Surface = self.animator.get_current_frame()
        self.source_sprite: pygame.Surface = self.animator.get_current_source_frame()
        self.sprite_height: int = self.sprite.get_height()

        # Load eating frames (eat1, eat2) for left and right directions
        self.eat_source_frames: Dict[str, list] = {}
        self.eat_frames: Dict[str, list] = {}
        for dir_name in ("left", "right"):
            sources = []
            scaled_list = []
            for i in (1, 2):
                filename = f"sheep_{dir_name}_eat{i}.png"
                path = os.path.join(sprite_dir, filename)
                try:
                    src = pygame.image.load(path).convert_alpha()
                except Exception:
                    src = None
                sources.append(src)
                if src is not None:
                    ratio = self.sprite_width / src.get_width()
                    h = max(1, int(round(src.get_height() * ratio)))
                    scaled_list.append(pygame.transform.smoothscale(src, (self.sprite_width, h)))
                else:
                    scaled_list.append(self.animator.fallback_scaled)
            self.eat_source_frames[dir_name] = sources
            self.eat_frames[dir_name] = scaled_list

        # Eating state
        self.eating: bool = False
        self.eat_timer: float = 0.0
        self.eat_frame_index: int = 0
        self.eat_frame_timer: float = 0.0

        # Collision box: 1 tile wide, 0.5 tile tall
        self.collision_width: int = tile_size
        self.collision_height: int = tile_size // 2

        # Zone bounds (in sprite x coordinates)
        self.zone_left: float = float(zone_x)
        self.zone_right: float = float(zone_x + zone_width - self.sprite_width)

        # Foot level = bottom edge of the zone strip
        foot_y: float = zone_y + zone_height

        # self.x, self.y = top-left of the sprite in world coordinates
        self.x: float = float(random.uniform(self.zone_left, max(self.zone_left, self.zone_right)))
        self.y: float = foot_y - self.sprite_height

        # Behaviour state
        self.direction: str = random.choice(["left", "right"])
        self.is_moving: bool = True
        self.stop_timer: float = 0.0
        self.is_blocked: bool = False  # True when stopped because a player is in the way

        # Zoom-scaled sprite cache (keyed by zoom -> {frame_id -> surface})
        self.scaled_sprite_cache: Dict[float, Dict[int, pygame.Surface]] = {}

        # Sound: stagger initial timers so sheep don't all bleat at once
        self.sound_timer: float = random.uniform(SOUND_MIN_INTERVAL, SOUND_MAX_INTERVAL)
        self.wants_sound: bool = False
        self._was_blocked: bool = False

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def collision_rect(self) -> pygame.Rect:
        """Collision rectangle, centered horizontally, at the sprite bottom."""
        col_x = int(self.x + (self.sprite_width - self.collision_width) / 2)
        col_y = int(self.y + self.sprite_height - self.collision_height)
        return pygame.Rect(col_x, col_y, self.collision_width, self.collision_height)

    @property
    def y_sort(self) -> float:
        """Y-sort key: bottom edge of the collision box."""
        return self.y + self.sprite_height

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def _would_collide_with_player(self, new_x: float, player_rect: pygame.Rect) -> bool:
        """Check whether moving to new_x would overlap the player collision rect."""
        col_x = int(new_x + (self.sprite_width - self.collision_width) / 2)
        col_y = int(self.y + self.sprite_height - self.collision_height)
        sheep_rect = pygame.Rect(col_x, col_y, self.collision_width, self.collision_height)
        return sheep_rect.colliderect(player_rect)

    def update(self, dt: float, player_rect: pygame.Rect = None) -> None:
        """Advance animation and movement each frame.

        Args:
            dt: Delta time in seconds.
            player_rect: The player's current collision rectangle, used for blocking.
        """
        if self.is_moving:
            # Random chance to stop for a rest
            if random.random() < STOP_CHANCE_PER_SEC * dt:
                self.is_moving = False
                self.is_blocked = False
                self.stop_timer = random.uniform(STOP_MIN_DURATION, STOP_MAX_DURATION)
            else:
                speed = SHEEP_SPEED * self.tile_size / 32.0
                if self.direction == "right":
                    new_x = self.x + speed * dt
                    if new_x >= self.zone_right:
                        new_x = self.zone_right
                        self.direction = "left"
                else:
                    new_x = self.x - speed * dt
                    if new_x <= self.zone_left:
                        new_x = self.zone_left
                        self.direction = "right"

                # Block if moving into the player
                if player_rect is not None and self._would_collide_with_player(new_x, player_rect):
                    self.is_moving = False
                    self.is_blocked = True
                    self.eating = False
                else:
                    self.x = new_x
        else:
            if self.is_blocked:
                # Resume only once the next step ahead is clear
                speed = SHEEP_SPEED * self.tile_size / 32.0
                if self.direction == "right":
                    test_x = self.x + speed * dt
                else:
                    test_x = self.x - speed * dt
                if player_rect is None or not self._would_collide_with_player(test_x, player_rect):
                    self.is_blocked = False
                    self.is_moving = True
            elif self.eating:
                # Animate eating frames
                self.eat_frame_timer += dt
                current_duration = EAT_FRAME_DURATIONS[self.eat_frame_index]
                if self.eat_frame_timer >= current_duration:
                    self.eat_frame_timer -= current_duration
                    self.eat_frame_index = (self.eat_frame_index + 1) % 2
                # Count down eating duration
                self.eat_timer -= dt
                if self.eat_timer <= 0.0:
                    # Return to static pose briefly before walking again
                    self.eating = False
                    self.stop_timer = EAT_RETURN_PAUSE
            else:
                self.stop_timer -= dt
                if self.stop_timer <= 0.0:
                    if random.random() < EAT_CHANCE_PER_STOP:
                        # Start eating
                        self.eating = True
                        self.eat_timer = random.uniform(EAT_MIN_DURATION, EAT_MAX_DURATION)
                        self.eat_frame_index = 0
                        self.eat_frame_timer = 0.0
                    else:
                        self.is_moving = True
                        # Occasionally flip direction when resuming
                        if random.random() < 0.3:
                            self.direction = "left" if self.direction == "right" else "right"

        self.animator.update(dt, self.direction, self.is_moving)
        if self.eating:
            eat_dir = self.direction if self.direction in self.eat_frames else "right"
            self.sprite = self.eat_frames[eat_dir][self.eat_frame_index]
            src = self.eat_source_frames[eat_dir][self.eat_frame_index]
            self.source_sprite = src if src is not None else self.sprite
        else:
            self.sprite = self.animator.get_current_frame()
            self.source_sprite = self.animator.get_current_source_frame()

        # Sound trigger — game.py reads wants_sound and plays the actual audio
        self.wants_sound = False
        newly_blocked = self.is_blocked and not self._was_blocked
        self._was_blocked = self.is_blocked
        self.sound_timer -= dt
        if self.sound_timer <= 0.0 or newly_blocked:
            self.wants_sound = True
            self.sound_timer = random.uniform(SOUND_MIN_INTERVAL, SOUND_MAX_INTERVAL)

    # ------------------------------------------------------------------
    # Rendering helpers
    # ------------------------------------------------------------------

    def _get_scaled_sprite(self, zoom: float) -> pygame.Surface:
        """Return a zoom-scaled sprite, using a per-zoom cache.

        Args:
            zoom: Current camera zoom level.

        Returns:
            pygame.Surface: The scaled frame.
        """
        zoom_key = round(float(zoom), 3)
        cache = self.scaled_sprite_cache.setdefault(zoom_key, {})
        base_frame = self.source_sprite or self.sprite
        frame_id = id(base_frame)
        if frame_id not in cache:
            if abs(zoom - 1.0) < 1e-3:
                cache[frame_id] = self.sprite
            else:
                src_w = base_frame.get_width()
                src_h = base_frame.get_height()
                if src_w <= 0 or src_h <= 0:
                    cache[frame_id] = self.sprite
                else:
                    target_w = max(1, int(round(self.sprite_width * zoom)))
                    target_h = max(1, int(round(self.sprite_height * zoom)))
                    if target_w >= src_w or target_h >= src_h:
                        cache[frame_id] = pygame.transform.scale(base_frame, (target_w, target_h))
                    else:
                        cache[frame_id] = pygame.transform.smoothscale(base_frame, (target_w, target_h))
        return cache[frame_id]

    def on_zoom_change(self) -> None:
        """Invalidate the sprite cache when the zoom level changes."""
        self.scaled_sprite_cache.clear()
