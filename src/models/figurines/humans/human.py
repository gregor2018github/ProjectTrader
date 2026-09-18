"""Abstract base class for human figurines (the player and every human NPC).

Humans share the eight-direction walk cycle, a one-tile-wide logical box whose
height comes from the standing pose, and the draw offsets that let an oversized
frame sit correctly on that box. Animals do not — they subclass
:class:`~..animals.animal.Animal` instead.
"""

import os
from abc import abstractmethod
from typing import Any, Dict, Tuple

import pygame

from ..figurine import Figurine, FIGURINE_SPRITE_ROOT

# Artwork root shared by every human figurine.
HUMAN_SPRITE_ROOT = os.path.join(FIGURINE_SPRITE_ROOT, 'humans')


class Human(Figurine):
    """A humanoid figurine with an eight-direction walk cycle."""

    # Manual per-pose vertical draw correction, in logical pixels at zoom 1
    # (positive = drawn lower). Keyed by (authored direction, animation group),
    # so directions that borrow frames inherit the correction with them.
    # Subclasses override this for their own artwork.
    SPRITE_Y_CORRECTION: Dict[Tuple[str, str], float] = {}

    # Manual per-pose size multiplier, keyed like SPRITE_Y_CORRECTION. Purely
    # cosmetic: frames stay bottom-centred and the logical box is unaffected.
    SPRITE_SCALE: Dict[Tuple[str, str], float] = {}

    def __init__(self, x: float, y: float, tile_size: int) -> None:
        """Initialize shared human state.

        Args:
            x: World X of the logical box's top-left corner.
            y: World Y of the logical box's top-left corner.
            tile_size: Base tile size; the logical box is one tile wide.
        """
        super().__init__(x, y, tile_size)

        # The logical box, filled in by _init_human_animator().
        self.width: int = tile_size
        self.height: int = tile_size
        self.sprite_offset_x: float = 0.0
        self.sprite_offset_y: float = 0.0

        # Movement state
        self.vel_x: float = 0.0
        self.vel_y: float = 0.0
        self.was_moving: bool = False

    # ------------------------------------------------------------------
    # Setup helpers
    # ------------------------------------------------------------------

    def _init_human_animator(
        self,
        sprite_dir: str,
        sprite_definitions: Dict[str, Dict[str, Any]],
        fallback_static: str,
        **animator_kwargs: Any,
    ) -> None:
        """Build the animator and derive the logical box and draw offsets.

        The logical box is one tile wide and as tall as the reference standing
        pose. Collision, y-sorting and every "centre of the figure" calculation
        use it, so it stays fixed no matter what the artwork does. The drawn
        sprite may be larger: it is centred on the box horizontally and sits on
        its baseline vertically, hence the offsets.

        Args:
            sprite_dir: Directory holding this human's PNGs.
            sprite_definitions: Per-direction static/move filename mapping.
            fallback_static: Filename used when a requested frame is missing.
            **animator_kwargs: Passed through to :class:`DirectionalAnimator`.
        """
        animator_kwargs.setdefault('scale_overrides', self.SPRITE_SCALE)
        self._init_animator(
            sprite_dir=sprite_dir,
            sprite_definitions=sprite_definitions,
            target_width=self.tile_size,
            fallback_static=fallback_static,
            **animator_kwargs,
        )
        self.width = self.tile_size
        self.height = self.animator.target_height
        self.sprite_width = self.animator.box_width
        self.sprite_height = self.animator.box_height
        self.sprite_offset_x = -(self.sprite_width - self.width) / 2.0
        self.sprite_offset_y = -(self.sprite_height - self.height)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def sprite_draw_offset_y(self) -> float:
        """Vertical draw offset for the current frame, in logical pixels.

        Combines the sprite box's baseline alignment with the manual per-pose
        correction from ``SPRITE_Y_CORRECTION``.
        """
        return self.sprite_offset_y + self.SPRITE_Y_CORRECTION.get(
            self.animator.current_frame_origin(), 0.0
        )

    @property
    def sprite_draw_offset(self) -> Tuple[float, float]:
        """Offset from (x, y) to the drawn sprite's top-left, in logical pixels."""
        return (self.sprite_offset_x, self.sprite_draw_offset_y)

    @property
    def y_sort(self) -> float:
        """Depth-sort key: the logical box's baseline, not the sprite box's."""
        return self.y + self.height

    @property
    def feet(self) -> Tuple[float, float]:
        """Where the figure stands: the bottom centre of the logical box.

        This is the position map data is authored against — a Tiled point or
        polygon marks the ground, not the top-left of a sprite box.
        """
        return (self.x + self.width / 2.0, self.y + self.height)

    def place_feet(self, x: float, y: float) -> None:
        """Move the figure so that it stands at the given ground position.

        Args:
            x: World X to stand at.
            y: World Y to stand at.
        """
        self.x = x - self.width / 2.0
        self.y = y - self.height

    @property
    def collision_rect(self) -> pygame.Rect:
        """Feet-area collision box: full logical width, half a tile tall."""
        collision_height = self.tile_size // 2
        return pygame.Rect(
            int(round(self.x)),
            int(round(self.y + self.height - collision_height)),
            int(self.width),
            int(collision_height),
        )

    # ------------------------------------------------------------------
    # Movement
    # ------------------------------------------------------------------

    def set_movement(self, dx: float, dy: float) -> None:
        """Set the movement direction (-1, 0 or 1 per axis).

        Args:
            dx: Horizontal direction component.
            dy: Vertical direction component.
        """
        self.vel_x = float(dx)
        self.vel_y = float(dy)

    def _determine_direction(self, is_moving: bool) -> str:
        """Pick the animation direction from the current velocity.

        Args:
            is_moving: Whether the figure is currently moving.

        Returns:
            str: Direction identifier understood by the animator.
        """
        if is_moving:
            if self.vel_y > 0:
                if self.vel_x < 0:
                    return "front_left"
                if self.vel_x > 0:
                    return "front_right"
                return "front"
            if self.vel_y < 0:
                if self.vel_x < 0:
                    return "back_left"
                if self.vel_x > 0:
                    return "back_right"
                return "back"
            if self.vel_x < 0:
                return "left"
            if self.vel_x > 0:
                return "right"
        return self.animator.current_direction

    @abstractmethod
    def update(self, dt: float, *args: Any, **kwargs: Any) -> None:
        """Advance movement and animation by ``dt`` seconds."""
