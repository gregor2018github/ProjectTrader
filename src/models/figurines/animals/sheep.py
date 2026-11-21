"""Sheep NPC that wanders left and right within a defined zone on the map.

Mostly a sheep grazes: it walks its zone, a strip of a Tiled rectangle, left
and right, stopping to rest and to eat. A sheep can also be taken elsewhere:
put in another zone (``set_zone``), sent walking back to its own
(``walk_home``), or led on a leash (``lead`` / ``update_led``, the way worked
out by leash.py), as Flip is in the quest for him (lost_sheep.py).
"""

import math
import os
import random
import pygame
from typing import Dict, List, Optional, Tuple

from .animal import Animal, ANIMAL_SPRITE_ROOT

SHEEP_SPEED = 40.0          # pixels per second at base tile_size=32
STOP_CHANCE_PER_SEC = 0.15  # probability per second to stop mid-walk
STOP_MIN_DURATION = 10.0    # seconds
STOP_MAX_DURATION = 20.0    # seconds
SOUND_MIN_INTERVAL = 22.5   # minimum seconds between one sheep's bleats
SOUND_MAX_INTERVAL = 52.5   # maximum (a third fewer since the flock grew to three)
EAT_CHANCE_PER_STOP = 0.35  # probability to start eating when a rest stop begins
EAT_MIN_DURATION = 3.0      # minimum eating duration in seconds
EAT_MAX_DURATION = 8.0      # maximum eating duration in seconds
EAT_FRAME_DURATIONS = (0.55, 0.22)  # seconds each eat frame is shown (eat1, eat2)
EAT_RETURN_PAUSE = 0.6      # static pause after eating before sheep can walk again
HEART_DURATION = 1.4        # seconds the heart floats up after petting
WALK_HOME_SPEED = 48.0      # pixels per second at tile_size 32, back to its zone off the leash
LED_WALK_HOLD = 0.25        # seconds a led sheep keeps walking through a stop
LED_TURN_SHARE = 0.35       # a led sheep turns only when this share of its step is sideways
SHY_DISTANCE = 3.0          # tiles a shy sheep backs away from an empty hand along its zone
SHY_MIN_DISTANCE = 0.5      # tiles; with less room than this it only turns its back

# Wool colour -> sprite folder (and file prefix) under ANIMAL_SPRITE_ROOT
WOOLS = {"brown": "sheep", "white": "white_sheep", "dark": "dark_sheep"}


class Sheep(Animal):
    """An animal that walks left and right within a rectangular zone."""

    def __init__(
        self,
        zone_x: float,
        zone_y: float,
        zone_width: float,
        zone_height: float,
        tile_size: int,
        wool: str = "brown",
        name: str = "",
    ) -> None:
        super().__init__(zone_x, zone_y, tile_size)
        #: Its own name (the Tiled "Name" property), "" for one of the flock
        self.name: str = name
        #: Whether the player knows it by its name, shown then as its title
        self.name_known: bool = False
        #: The zone it belongs in, as the Tiled rectangle (x, y, width, height)
        self.home_zone: Tuple[float, float, float, float] = (zone_x, zone_y, zone_width, zone_height)
        #: Where it is walking to, back in its zone, before it grazes again (walk_home); else None
        self.walk_target: Optional[Tuple[float, float]] = None
        #: Led on a leash: it follows whoever holds it and takes no notice of them in its way
        self.leashed: bool = False
        self._led_still: float = 0.0
        self.sprite_width = int(1.5 * tile_size)  # 48 px at base zoom

        # Each wool has its own sprite folder, the files named after it
        self.wool = wool if wool in WOOLS else "brown"
        name = WOOLS[self.wool]
        sprite_dir = os.path.join(ANIMAL_SPRITE_ROOT, name)
        sprite_definitions: Dict = {
            "front": {
                "static": f"{name}_right_static.png",
                "move": [],
            },
            "back": {
                "static": f"{name}_right_static.png",
                "move": [],
            },
            "left": {
                "static": f"{name}_left_static.png",
                "move": [
                    f"{name}_left_move1.png",
                    f"{name}_left_move2.png",
                    f"{name}_left_move3.png",
                    f"{name}_left_move4.png",
                ],
            },
            "right": {
                "static": f"{name}_right_static.png",
                "move": [
                    f"{name}_right_move1.png",
                    f"{name}_right_move2.png",
                    f"{name}_right_move3.png",
                    f"{name}_right_move4.png",
                ],
            },
        }

        self._init_animator(
            sprite_dir=sprite_dir,
            sprite_definitions=sprite_definitions,
            target_width=self.sprite_width,
            fallback_static=f"{name}_right_static.png",
        )
        # Sheep are slower than the player — use a wider frame interval
        self.animator.frame_interval *= 1.5
        self.sprite_height = self.sprite.get_height()

        # Load eating frames (eat1, eat2) for left and right directions
        self.eat_source_frames: Dict[str, list] = {}
        self.eat_frames: Dict[str, list] = {}
        for dir_name in ("left", "right"):
            sources = []
            scaled_list = []
            for i in (1, 2):
                filename = f"{name}_{dir_name}_eat{i}.png"
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

        # Collision box: 1 tile wide, 0.5 tile tall (sized by Animal)

        # Zone bounds (in sprite x coordinates), its foot level, and a random spot in it
        self.set_zone(zone_x, zone_y, zone_width, zone_height)

        # Behaviour state
        self.direction = random.choice(["left", "right"])
        self.is_moving = True
        self.stop_timer: float = 0.0
        self.is_blocked: bool = False  # True when stopped because a player is in the way

        # Sound: stagger initial timers so sheep don't all bleat at once
        self.sound_timer: float = random.uniform(SOUND_MIN_INTERVAL, SOUND_MAX_INTERVAL)
        self.wants_sound: bool = False
        self._was_blocked: bool = False

        # Seconds since the last petting while its heart is floating up, else None
        self.heart_age: Optional[float] = None

    # ------------------------------------------------------------------
    # Where it is
    # ------------------------------------------------------------------

    @property
    def display_name(self) -> str:
        """Its title: its name once the player knows it, else just a sheep."""
        return self.name if (self.name and self.name_known) else "Sheep"

    @property
    def feet(self) -> Tuple[float, float]:
        """Where it stands: the bottom centre of its sprite."""
        return (self.x + self.sprite_width / 2.0, self.y + self.sprite_height)

    def place_feet(self, x: float, y: float) -> None:
        self.x = x - self.sprite_width / 2.0
        self.y = y - self.sprite_height

    def set_zone(self, zone_x: float, zone_y: float, zone_width: float, zone_height: float,
                 place: bool = True) -> None:
        """Make a Tiled rectangle its zone: it walks the strip along the rectangle's bottom edge.

        Args:
            zone_x, zone_y, zone_width, zone_height: The rectangle, world pixels.
            place: Put it at a random spot in the zone at once (else it stays where it is).
        """
        self.zone_left = float(zone_x)
        self.zone_right = float(zone_x + zone_width - self.sprite_width)
        self.zone_foot_y = float(zone_y + zone_height)
        if place:
            self.walk_target = None
            self.x = float(random.uniform(self.zone_left, max(self.zone_left, self.zone_right)))
            self.y = self.zone_foot_y - self.sprite_height

    @property
    def in_home_zone(self) -> bool:
        """Whether its zone is the one it belongs in."""
        x, y, width, height = self.home_zone
        return self.zone_left == float(x) and self.zone_foot_y == float(y + height)

    def go_home(self) -> None:
        """Put it straight back in its own zone, at a random spot."""
        self.leashed = False
        self.set_zone(*self.home_zone)

    def walk_home(self) -> None:
        """Make its own zone its zone again, and send it walking to the nearest spot of it."""
        self.leashed = False
        self.set_zone(*self.home_zone, place=False)
        x = min(max(self.x, self.zone_left), max(self.zone_left, self.zone_right))
        self.walk_target = (x + self.sprite_width / 2.0, self.zone_foot_y)
        self.eating = False
        self.is_blocked = False

    def lead(self) -> None:
        """Put it on the leash: it stops grazing and follows (update_led)."""
        self.leashed = True
        self._led_still = LED_WALK_HOLD
        self.walk_target = None
        self.eating = False
        self.is_blocked = False
        self.is_moving = False

    # ------------------------------------------------------------------
    # Interaction
    # ------------------------------------------------------------------

    def pet(self, player_center_x: float) -> None:
        """React to being petted: turn towards the player and stand still.

        A walking sheep stops for a normal rest; one that is already resting
        or eating carries on with that.

        Args:
            player_center_x: World X of the player's centre, to face towards.
        """
        sheep_center_x = self.x + self.sprite_width / 2
        if not self.eating:
            self.direction = "right" if player_center_x > sheep_center_x else "left"
        if self.is_moving or self.is_blocked:
            self.is_moving = False
            self.is_blocked = False
            self.stop_timer = random.uniform(STOP_MIN_DURATION, STOP_MAX_DURATION)
        # Petting counts as a bleat, so the next idle one isn't right behind it
        self.sound_timer = random.uniform(SOUND_MIN_INTERVAL, SOUND_MAX_INTERVAL)
        self.heart_age = 0.0

    def shy_away(self, player_center_x: float) -> None:
        """Back away from the player along its zone (no heart): turn away and walk off
        SHY_DISTANCE tiles, as far as its zone allows; with no room that way it only turns its back.

        Args:
            player_center_x: World X of the player's centre, to get away from.
        """
        center = self.x + self.sprite_width / 2
        away = 1.0 if center >= player_center_x else -1.0
        self.direction = "right" if away > 0 else "left"
        self.eating = False
        self.is_blocked = False
        self.heart_age = None
        goal_x = min(max(self.x + away * SHY_DISTANCE * self.tile_size, self.zone_left),
                     max(self.zone_left, self.zone_right))
        if abs(goal_x - self.x) >= SHY_MIN_DISTANCE * self.tile_size:
            self.walk_target = (goal_x + self.sprite_width / 2.0, self.zone_foot_y)
        else:
            self.is_moving = False
            self.stop_timer = random.uniform(STOP_MIN_DURATION / 2, STOP_MIN_DURATION)

    def inspect_lines(self, observer=None) -> List[str]:
        """Debug lines for the "Inspect" window, plus the grazing behaviour."""
        if self.leashed:
            state = "on the leash"
        elif self.walk_target is not None:
            state = "walking to a spot of its zone"
        elif self.is_blocked:
            state = "blocked by you"
        elif self.is_moving:
            state = f"walking {self.direction}"
        elif self.eating:
            state = f"eating, {self.eat_timer:.1f} s left"
        else:
            state = f"resting, {self.stop_timer:.1f} s left"
        return super().inspect_lines(observer) + [
            "**Behaviour**",
            f"Name: {self.name or 'none'}",
            f"Wool: {self.wool}",
            f"State: {state}",
            f"Zone: X={round(self.zone_left, 1)} to {round(self.zone_right, 1)}",
            f"Next bleat in: {self.sound_timer:.1f} s",
        ]

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def move_led(self, feet: Tuple[float, float], walked: bool, dt: float = 0.0) -> None:
        """On the leash: stand at `feet` now (leash.Leash.step), facing the way it went.

        Its walk goes on through stops of up to LED_WALK_HOLD (at a steady pace it is a
        step behind and caught up by turns), so the animation is not started afresh
        every frame; it walks the same way up and down, the way it last faced. It turns
        only when it goes mostly sideways.

        Args:
            feet: Where its feet are to be, world pixels.
            walked: Whether it walked this frame.
            dt: Seconds of the frame.
        """
        old_x, old_y = self.feet
        self.place_feet(*feet)
        dx, dy = feet[0] - old_x, feet[1] - old_y
        if abs(dx) > 0.05 and abs(dx) >= LED_TURN_SHARE * math.hypot(dx, dy):
            self.direction = "right" if dx > 0 else "left"
        if walked:
            self._led_still = 0.0
        else:
            self._led_still += dt
        self.is_moving = self._led_still < LED_WALK_HOLD

    def _walk_to_target(self, dt: float) -> None:
        """Walking back to its zone (walk_home): straight there, then a rest before it grazes."""
        speed = WALK_HOME_SPEED * self.tile_size / 32.0
        fx, fy = self.feet
        tx, ty = self.walk_target
        gap = math.hypot(tx - fx, ty - fy)
        if gap <= speed * dt or gap < 0.5:
            self.place_feet(tx, ty)
            self.walk_target = None
            self.is_moving = False
            self.stop_timer = random.uniform(STOP_MIN_DURATION / 2, STOP_MIN_DURATION)
            return
        if abs(tx - fx) > 0.5:
            self.direction = "right" if tx > fx else "left"
        self.place_feet(fx + (tx - fx) * speed * dt / gap, fy + (ty - fy) * speed * dt / gap)
        self.is_moving = True

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
        if self.heart_age is not None:
            self.heart_age += dt
            if self.heart_age >= HEART_DURATION:
                self.heart_age = None

        if self.leashed:
            pass                                   # moved by move_led; only animated here
        elif self.walk_target is not None:
            self._walk_to_target(dt)
        elif self.is_moving:
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
