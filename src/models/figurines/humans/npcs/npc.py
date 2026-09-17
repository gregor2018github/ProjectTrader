"""Abstract base class for human NPCs.

An NPC is a :class:`~..human.Human` that nobody steers — it decides where to go
itself. This class holds what every NPC needs regardless of trade: a display
name, the artwork folder, and the walk-to-a-target movement that a daily
schedule will drive. Concrete NPCs (the butcher, and whoever follows) subclass
it and add their own behaviour.
"""

import os
from abc import abstractmethod
from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple

import pygame

from ..human import Human, HUMAN_SPRITE_ROOT

if TYPE_CHECKING:
    from ....map import TMXMap

# Artwork root shared by every human NPC.
NPC_SPRITE_ROOT = os.path.join(HUMAN_SPRITE_ROOT, 'npcs')

# How close (in world pixels) an NPC must get to a target to count as arrived.
ARRIVAL_TOLERANCE = 2.0


class NPC(Human):
    """A self-directed human figurine."""

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

        # Current walk target in world coordinates, or None when idle.
        self.target: Optional[Tuple[float, float]] = None

    # ------------------------------------------------------------------
    # Setup helpers
    # ------------------------------------------------------------------

    @property
    def sprite_dir(self) -> str:
        """Directory holding this NPC's artwork."""
        return os.path.join(NPC_SPRITE_ROOT, self.SPRITE_FOLDER)

    def _sprite_definitions(self) -> Dict[str, Dict[str, Any]]:
        """Build the per-direction filename mapping from ``SPRITE_PREFIX``.

        Directions with no artwork on disk are simply skipped — the animator
        falls back to its cardinal counterpart (see ``DIRECTION_FALLBACKS``),
        so a half-drawn NPC still renders.

        Returns:
            Dict: Mapping understood by :class:`DirectionalAnimator`.
        """
        from ...animator import DirectionalAnimator

        definitions: Dict[str, Dict[str, Any]] = {}
        for direction in DirectionalAnimator.DIRECTIONS:
            static = f"{self.SPRITE_PREFIX}_{direction}_static.png"
            if not os.path.exists(os.path.join(self.sprite_dir, static)):
                continue
            move = []
            index = 1
            while True:
                filename = f"{self.SPRITE_PREFIX}_{direction}_move{index}.png"
                if not os.path.exists(os.path.join(self.sprite_dir, filename)):
                    break
                move.append(filename)
                index += 1
            definitions[direction] = {"static": static, "move": move}
        return definitions

    # ------------------------------------------------------------------
    # Movement
    # ------------------------------------------------------------------

    def walk_to(self, x: float, y: float) -> None:
        """Send the NPC walking towards a world position.

        Args:
            x: Target world X.
            y: Target world Y.
        """
        self.target = (float(x), float(y))

    def stop(self) -> None:
        """Clear the current walk target and stand still."""
        self.target = None
        self.set_movement(0.0, 0.0)

    def _steer_towards_target(self) -> bool:
        """Point ``vel_x``/``vel_y`` at the current target.

        Returns:
            bool: True while the NPC still has ground to cover.
        """
        if self.target is None:
            return False
        dx = self.target[0] - self.x
        dy = self.target[1] - self.y
        if abs(dx) <= ARRIVAL_TOLERANCE and abs(dy) <= ARRIVAL_TOLERANCE:
            self.stop()
            return False
        self.set_movement(
            0.0 if abs(dx) <= ARRIVAL_TOLERANCE else (1.0 if dx > 0 else -1.0),
            0.0 if abs(dy) <= ARRIVAL_TOLERANCE else (1.0 if dy > 0 else -1.0),
        )
        return True

    @abstractmethod
    def update(self, dt: float, *args: Any, **kwargs: Any) -> None:
        """Advance behaviour, movement and animation by ``dt`` seconds."""
