"""Abstract base class for human NPCs.

An NPC is a :class:`~..human.Human` that nobody steers — it decides where to go
itself. This class holds what every NPC needs regardless of trade: a display
name, the artwork-folder convention, and movement along a patrol path, which is
how a townsperson placed on a Tiled polygon gets around. Concrete NPCs (the
butcher, and whoever follows) subclass it and decide *when* to move.
"""

import os
from abc import abstractmethod
from typing import Any, Dict, Optional

import pygame

from ...patrol_path import PatrolPath
from ..human import Human, HUMAN_SPRITE_ROOT

# Artwork root shared by every human NPC.
NPC_SPRITE_ROOT = os.path.join(HUMAN_SPRITE_ROOT, 'npcs')

# How close (in world pixels) an NPC must get to a target to count as arrived.
ARRIVAL_TOLERANCE = 1.0

# A movement component smaller than this fraction of the larger one is treated
# as zero when picking a facing, so a nearly-horizontal segment reads as "left"
# rather than flickering between "left" and "front_left".
DIAGONAL_THRESHOLD = 0.4


class NPC(Human):
    """A self-directed human figurine that walks a patrol path."""

    #: Folder under ``NPC_SPRITE_ROOT`` holding this NPC's artwork.
    SPRITE_FOLDER: str = ""
    #: Filename prefix of this NPC's PNGs, e.g. ``"butcher"`` for
    #: ``butcher_left_static.png``.
    SPRITE_PREFIX: str = ""

    def __init__(self, name: str, x: float, y: float, tile_size: int) -> None:
        """Initialize shared NPC state.

        Args:
            name: Display name, shown when the player interacts with the NPC.
            x: Initial world X.
            y: Initial world Y.
            tile_size: Base tile size for scaling.
        """
        super().__init__(x, y, tile_size)
        self.name: str = name
        self.speed: float = 0.0  # pixels per second; set by the subclass

        self.path: Optional[PatrolPath] = None
        # Where the NPC currently is along the path, and where it is headed.
        # A target of None means standing still.
        self.path_distance: float = 0.0
        self.path_target: Optional[float] = None

    # ------------------------------------------------------------------
    # Setup helpers
    # ------------------------------------------------------------------

    @property
    def sprite_dir(self) -> str:
        """Directory holding this NPC's artwork."""
        return os.path.join(NPC_SPRITE_ROOT, self.SPRITE_FOLDER)

    def _sprite_definitions(self) -> Dict[str, Dict[str, Any]]:
        """Build the per-direction filename mapping from ``SPRITE_PREFIX``.

        Directions with no artwork on disk are simply left out — the animator
        borrows frames from a direction that does have some (mirroring them
        where that keeps the figure facing the right way), so an NPC drawn only
        from one side still renders and animates in all eight directions.

        Returns:
            Dict: Mapping understood by :class:`DirectionalAnimator`.
        """
        from ...animator import DirectionalAnimator

        definitions: Dict[str, Dict[str, Any]] = {}
        for direction in DirectionalAnimator.DIRECTIONS:
            static = f"{self.SPRITE_PREFIX}_{direction}_static.png"
            move = []
            index = 1
            while True:
                filename = f"{self.SPRITE_PREFIX}_{direction}_move{index}.png"
                if not os.path.exists(os.path.join(self.sprite_dir, filename)):
                    break
                move.append(filename)
                index += 1
            has_static = os.path.exists(os.path.join(self.sprite_dir, static))
            if has_static or move:
                definitions[direction] = {
                    "static": static if has_static else "",
                    "move": move,
                }
        return definitions

    # ------------------------------------------------------------------
    # Movement
    # ------------------------------------------------------------------

    def set_path(self, path: PatrolPath, distance: Optional[float] = None) -> None:
        """Put the NPC on a patrol path.

        Args:
            path: The path to walk.
            distance: Where along it to start. Defaults to a random point.
        """
        self.path = path
        self.path_distance = path.random_distance() if distance is None else path.normalize(distance)
        self.path_target = None
        self.place_feet(*path.position_at(self.path_distance))

    def walk_to_distance(self, distance: float) -> None:
        """Send the NPC walking to a point on its path.

        Args:
            distance: Target distance along the path.
        """
        if self.path is not None:
            self.path_target = self.path.normalize(distance)

    def stop(self) -> None:
        """Abandon the current walk target and stand still."""
        self.path_target = None
        self.set_movement(0.0, 0.0)

    def _follow_path(self, dt: float) -> bool:
        """Advance along the path towards the current target.

        Args:
            dt: Delta time in seconds.

        Returns:
            bool: True while the NPC is still walking.
        """
        if self.path is None or not self.path or self.path_target is None:
            self.set_movement(0.0, 0.0)
            return False

        gap = self.path.signed_gap(self.path_distance, self.path_target)
        if abs(gap) <= ARRIVAL_TOLERANCE:
            self.path_distance = self.path_target
            self.place_feet(*self.path.position_at(self.path_distance))
            self.stop()
            return False

        step = min(self.speed * dt, abs(gap))
        before = self.path.position_at(self.path_distance)
        self.path_distance = self.path.normalize(
            self.path_distance + (step if gap > 0 else -step)
        )
        after = self.path.position_at(self.path_distance)
        self.place_feet(*after)
        self._face_along(after[0] - before[0], after[1] - before[1])
        return True

    def _face_along(self, dx: float, dy: float) -> None:
        """Point the NPC in the direction it just moved.

        Args:
            dx: Horizontal movement since the last frame.
            dy: Vertical movement since the last frame.
        """
        largest = max(abs(dx), abs(dy))
        if largest <= 0.0:
            return
        deadzone = largest * DIAGONAL_THRESHOLD
        self.set_movement(
            0.0 if abs(dx) < deadzone else (1.0 if dx > 0 else -1.0),
            0.0 if abs(dy) < deadzone else (1.0 if dy > 0 else -1.0),
        )

    def _animate(self, dt: float, is_moving: bool) -> None:
        """Advance the animator and refresh the current frame.

        Args:
            dt: Delta time in seconds.
            is_moving: Whether the NPC moved this frame.
        """
        self.animator.update(dt, self._determine_direction(is_moving), is_moving)
        self.sprite = self.animator.get_current_frame()
        self.source_sprite = self.animator.get_current_source_frame()
        self.was_moving = is_moving

    @abstractmethod
    def update(self, dt: float, *args: Any, **kwargs: Any) -> None:
        """Advance behaviour, movement and animation by ``dt`` seconds."""
