"""The player character on the map.

Moved out of ``map.py`` into the figurine tree; behaviour is unchanged.
"""

import os
import random
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import pygame

from ....config.constants import (
    TILE_SIZE,
    PLAYER_SPEED,
    PLAYER_DIAGONAL_SPEED_FACTOR,
    FOOT_STEP_VOLUME,
)
from .human import Human, HUMAN_SPRITE_ROOT

if TYPE_CHECKING:
    from ...map import TMXMap


class MapPlayer(Human):
    """Player character that moves around the map."""

    display_name = "You"

    # Manual per-pose vertical draw correction, in logical pixels at zoom 1
    # (positive = drawn lower). Keyed by the direction the artwork was authored
    # for and the animation group, so directions that borrow frames inherit the
    # correction with them.
    #
    # The walk-down frames are drawn taller than the rest of the set, and
    # bottom-aligning them on the ground baseline leaves the head sitting several
    # pixels higher than in every other pose, which reads as a jump when you turn.
    # This nudges that one pose back down onto the others. Purely cosmetic: the
    # logical box, collision and y-sorting are all unaffected.
    SPRITE_Y_CORRECTION: Dict[Tuple[str, str], float] = {
        ("front", "move"): 5.0,
    }

    # Manual per-pose size multiplier, keyed like SPRITE_Y_CORRECTION. The
    # diagonal walk artwork reads a little small next to the other poses. Purely
    # cosmetic: frames stay bottom-centred and the logical box is unaffected.
    SPRITE_SCALE: Dict[Tuple[str, str], float] = {
        ("front_left", "move"): 1.05,
        ("front_right", "move"): 1.05,
    }

    def __init__(self, x: float, y: float, tile_size: int = TILE_SIZE) -> None:
        """Initialize the player.
        
        Args:
            x: Initial world X.
            y: Initial world Y.
            tile_size: Base tile size for scaling.
        """
        super().__init__(x, y, tile_size)
        self.speed: float = PLAYER_SPEED * TILE_SIZE / 32.0  # pixels per second

        sprite_dir = os.path.join(HUMAN_SPRITE_ROOT, 'player')
        sprite_definitions: Dict[str, Dict[str, Any]] = {
            "front": {
                "static": "player_front_static.png",
                "move": ["player_front_move1.png", "player_front_move2.png", "player_front_move3.png", "player_front_move4.png"]
            },
            "back": {
                "static": "player_back_static.png",
                "move": ["player_back_move1.png", "player_back_move2.png", "player_back_move3.png", "player_back_move4.png"],
            },
            "left": {
                "static": "player_left_static.png",
                "move": ["player_left_move1.png", "player_left_move2.png"],
            },
            "right": {
                "static": "player_right_static.png",
                "move": ["player_right_move1.png", "player_right_move2.png"],
            },
            # Diagonals are optional — any direction whose files are absent falls
            # back to its vertical counterpart (see DIRECTION_FALLBACKS).
            "front_left": {
                "static": "player_front_left_static.png",
                "move": ["player_front_left_move1.png", "player_front_left_move2.png", "player_front_left_move3.png"],
            },
            "front_right": {
                "static": "player_front_right_static.png",
                "move": ["player_front_right_move1.png", "player_front_right_move2.png", "player_front_right_move3.png"],
            },
            "back_left": {
                "static": "player_back_left_static.png",
                "move": ["player_back_left_move1.png", "player_back_left_move2.png", "player_back_left_move3.png"],
            },
            "back_right": {
                "static": "player_back_right_static.png",
                "move": ["player_back_right_move1.png", "player_back_right_move2.png", "player_back_right_move3.png"],
            },
        }

        # Builds the animator and derives the logical box plus the draw offsets
        # (applied in _build_render_queue in map_view.py).
        self._init_human_animator(
            sprite_dir=sprite_dir,
            sprite_definitions=sprite_definitions,
            fallback_static="player_front_static.png",
            # The player artwork has inconsistent canvas sizes and padding, and
            # some poses are deliberately taller than others. Normalizing at load
            # time preserves both aspect ratio and relative size, so nothing is
            # squashed and a taller pose really does render taller.
            normalize=True,
        )

        # Movement state
        self.frame_distance_px: float = 0.0  # pixels actually moved this frame, read and reset by Game
        self.footstep_sounds: List[pygame.mixer.Sound] = []
        self.last_sound_index: int = -1
        self.current_sound: Optional[pygame.mixer.Sound] = None
        # Channel 0 is reserved exclusively for footsteps (see game.py mixer init).
        self.footstep_channel: pygame.mixer.Channel = pygame.mixer.Channel(0)
    
    def set_footstep_sounds(self, sounds: List[pygame.mixer.Sound]) -> None:
        """Assign footstep sounds to the player.
        
        Args:
            sounds: List of pygame Sound objects for footsteps.
        """
        self.footstep_sounds = sounds

    def inspect_lines(self, observer=None) -> List[str]:
        """Debug lines for the "Inspect" window, plus movement input."""
        return super().inspect_lines(observer) + [
            "**Movement**",
            f"Speed: {self.speed:.0f} px/s",
            f"Input: dx={self.vel_x:+.0f}, dy={self.vel_y:+.0f}",
        ]

    def stop_footstep_sound(self) -> None:
        """Stop any currently playing footstep sound."""
        self.footstep_channel.stop()
        self.current_sound = None
        self.was_moving = False

    def update(self, dt: float, game_map: "TMXMap") -> None:
        """Update player position with collision detection and animation.
        
        Args:
            dt: Delta time.
            game_map: The map for collision checks.
        """
        is_moving = self.vel_x != 0 or self.vel_y != 0

        # Sound logic
        if self.footstep_sounds:
            if is_moving:
                # Check if we just started moving, or if the dedicated channel stopped playing
                needs_sound = not self.was_moving or self.footstep_channel.get_sound() != self.current_sound

                if needs_sound:
                    # Started moving or sound stopped - pick a new sound
                    available_indices = [i for i in range(len(self.footstep_sounds)) if i != self.last_sound_index]
                    if not available_indices:  # only 1 sound available or empty
                        available_indices = [0] if self.footstep_sounds else []

                    if available_indices:
                        self.last_sound_index = random.choice(available_indices)
                        self.current_sound = self.footstep_sounds[self.last_sound_index]
                        self.footstep_channel.play(self.current_sound, loops=-1)
                        self.footstep_channel.set_volume(FOOT_STEP_VOLUME)
            elif not is_moving and self.was_moving:
                # Stopped moving
                self.stop_footstep_sound()

        self.frame_distance_px = 0.0
        if is_moving:
            speed = self.speed
            if self.vel_x != 0 and self.vel_y != 0:
                speed *= PLAYER_DIAGONAL_SPEED_FACTOR
            move_x = self.vel_x * speed * dt
            move_y = self.vel_y * speed * dt

            if move_x != 0:
                new_x = self.x + move_x
                if self.can_move_to(new_x, self.y, game_map):
                    self.frame_distance_px += abs(move_x)
                    self.x = new_x

            if move_y != 0:
                new_y = self.y + move_y
                if self.can_move_to(self.x, new_y, game_map):
                    self.frame_distance_px += abs(move_y)
                    self.y = new_y

        direction = self._determine_direction(is_moving)
        self.animator.update(dt, direction, is_moving)
        self.sprite = self.animator.get_current_frame()
        self.source_sprite = self.animator.get_current_source_frame()
        # self.width and self.height are kept stable for collision consistency
        self.was_moving = is_moving

    def can_move_to(self, x: float, y: float, game_map: "TMXMap") -> bool:
        """Check if player can move to the given position.
        
        Args:
            x: Target world X.
            y: Target world Y.
            game_map: Map data for tile checks.
            
        Returns:
            bool: True if navigable.
        """
        # Ensure coordinates are within map bounds
        if x < 0 or y < 0:
            return False
        if x + self.width > game_map.width * game_map.tile_size:
            return False
        if y + self.height > game_map.height * game_map.tile_size:
            return False
        
        # Calculate collision box (just the bottom tile/feet area)
        # Use a slightly smaller height for the collision box to prevent being "stuck"
        # exactly at the edge of a collision box when moving from top to bottom.
        collision_height = self.tile_size / 2 - 2
        collision_y = y + self.height - collision_height
        
        # Check collision with objects (houses)
        # Use round instead of int for slightly more accurate positioning
        player_rect = pygame.Rect(
            int(round(x)), 
            int(round(collision_y)), 
            int(self.width), 
            int(collision_height)
        )
        if game_map.check_object_collision(player_rect):
            return False

        # Get the four corners of the player collision box (feet area)
        # Inset the corners slightly to allow for easier movement through tight spaces
        margin = 2
        corners = [
            (x + margin, collision_y),  # top-left of collision area
            (x + self.width - 1 - margin, collision_y),  # top-right of collision area
            (x + margin, y + self.height - 1),  # bottom-left
            (x + self.width - 1 - margin, y + self.height - 1)  # bottom-right
        ]
        
        # Check if all corners are in walkable tiles
        for corner_x, corner_y in corners:
            if corner_x < 0 or corner_y < 0:
                return False
                
            grid_x, grid_y = game_map.world_to_grid(corner_x, corner_y)
            if not game_map.is_walkable(grid_x, grid_y):
                return False
        
        return True
