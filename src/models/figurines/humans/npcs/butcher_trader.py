"""The butcher — the first human NPC, who will trade meat at the market.

Scaffolding only so far: he loads whatever artwork exists in
``assets/map_sprites/figurines/humans/npcs/butcher_trader`` and stands where he
is placed. Trading, the daily schedule and the walk between home and his market
booth still have to be written.
"""

from typing import TYPE_CHECKING, Optional

import pygame

from .....config.constants import TILE_SIZE
from .npc import NPC

if TYPE_CHECKING:
    from ....map import TMXMap

#: Walking speed in pixels per second at tile_size 32 — a little slower than
#: the player, so he reads as going about his business rather than rushing.
BUTCHER_SPEED = 55.0


class ButcherTrader(NPC):
    """A butcher who sells meat at the market."""

    SPRITE_FOLDER = 'butcher_trader'
    SPRITE_PREFIX = 'butcher'

    def __init__(self, x: float, y: float, tile_size: int = TILE_SIZE, name: str = "Butcher") -> None:
        """Place the butcher on the map.

        Args:
            x: Initial world X.
            y: Initial world Y.
            tile_size: Base tile size for scaling.
            name: Display name.
        """
        super().__init__(name, x, y, tile_size)
        self.speed = BUTCHER_SPEED * tile_size / 32.0

        self._init_human_animator(
            sprite_dir=self.sprite_dir,
            sprite_definitions=self._sprite_definitions(),
            fallback_static=f"{self.SPRITE_PREFIX}_left_static.png",
            normalize=True,
        )

    def update(self, dt: float, game_map: Optional["TMXMap"] = None) -> None:
        """Advance the butcher's movement and animation.

        Args:
            dt: Delta time in seconds.
            game_map: Map used for collision checks once he starts walking.
        """
        is_moving = self._steer_towards_target()

        if is_moving:
            move_x = self.vel_x * self.speed * dt
            move_y = self.vel_y * self.speed * dt
            if move_x:
                self.x += move_x
            if move_y:
                self.y += move_y

        self.animator.update(dt, self._determine_direction(is_moving), is_moving)
        self.sprite = self.animator.get_current_frame()
        self.source_sprite = self.animator.get_current_source_frame()
        self.was_moving = is_moving
