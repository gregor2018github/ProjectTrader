"""Abstract base class for human NPCs.

An NPC is a :class:`~..human.Human` that nobody steers — it decides where to go
itself. This class holds what every NPC needs regardless of trade: a display
name, the artwork-folder convention, and movement along a patrol path, which is
how a townsperson placed on a Tiled polygon gets around. Concrete NPCs (the
butcher, and whoever follows) subclass it and decide *when* to move.
"""

import os
import random
from abc import abstractmethod
from typing import Any, Dict, List, Optional, TYPE_CHECKING

import pygame

from ...patrol_path import PatrolPath
from ..human import Human, HUMAN_SPRITE_ROOT
from .sentences import sentences_for

if TYPE_CHECKING:
    from ...figurine import Figurine

# Artwork root shared by every human NPC.
NPC_SPRITE_ROOT = os.path.join(HUMAN_SPRITE_ROOT, 'npcs')

# How close (in world pixels) an NPC must get to a target to count as arrived.
ARRIVAL_TOLERANCE = 1.0

# A movement component smaller than this fraction of the larger one is treated
# as zero when picking a facing, so a nearly-horizontal segment reads as "left"
# rather than flickering between "left" and "front_left".
DIAGONAL_THRESHOLD = 0.4

# Hysteresis around DIAGONAL_THRESHOLD: a component already shown in the facing
# is kept down to the threshold minus this, one not shown needs the threshold
# plus this. Without it a segment whose slope sits right at the threshold
# flips the walk between two directions every frame.
DIAGONAL_HYSTERESIS = 0.1

# Standing poses tried, in order, for the fallback / size-reference sprite.
FALLBACK_DIRECTIONS = ("left", "front", "right", "back")

# The town's four population groups, named as in the population statistics.
SOCIAL_CLASSES = ("Poor", "Commons", "Middling Sort", "Nobility")


class NPC(Human):
    """A self-directed human figurine that walks a patrol path."""

    #: Folder under ``NPC_SPRITE_ROOT`` holding this NPC's artwork.
    SPRITE_FOLDER: str = ""
    #: Filename prefix of this NPC's PNGs, e.g. ``"butcher"`` for
    #: ``butcher_left_static.png``.
    SPRITE_PREFIX: str = ""
    #: Which of SOCIAL_CLASSES the NPC belongs to.
    SOCIAL_CLASS: str = "Commons"
    #: "male" or "female"; picks the voice of their coughs, among others.
    GENDER: str = "male"
    #: Traders talk shop: their chat also draws on the trader sentences.
    IS_TRADER: bool = False

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

        self._last_chat_line: Optional[str] = None

        #: Whoever the player has stopped them for, or None. While someone is
        #: set, the NPC stands still and turns to face them.
        self.talking_to: Optional['Figurine'] = None

        #: Set when the NPC goes through a front door, in or out; game.py
        #: plays the door sound and clears it again.
        self.wants_door_sound: bool = False

    # ------------------------------------------------------------------
    # Setup helpers
    # ------------------------------------------------------------------

    @property
    def display_name(self) -> str:
        """Name shown to the player, e.g. as a menu title."""
        return self.name

    @property
    def sprite_dir(self) -> str:
        """Directory holding this NPC's artwork."""
        return os.path.join(NPC_SPRITE_ROOT, self.SPRITE_FOLDER)

    def _fallback_static(self) -> str:
        """Filename of the standing sprite used as fallback and size reference.

        The animator scales every frame relative to this one, so it must be
        real artwork. Traders are drawn from one side first and filled in
        later, so take the first standing pose that exists.

        Returns:
            str: e.g. ``"butcher_left_static.png"``.
        """
        for direction in FALLBACK_DIRECTIONS:
            filename = f"{self.SPRITE_PREFIX}_{direction}_static.png"
            if os.path.exists(os.path.join(self.sprite_dir, filename)):
                return filename
        return f"{self.SPRITE_PREFIX}_{FALLBACK_DIRECTIONS[0]}_static.png"

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
    # Chat
    # ------------------------------------------------------------------

    def _direction_towards(self, other: 'Figurine') -> str:
        """The animation direction that has the NPC looking at someone.

        Args:
            other: The figurine to look at.

        Returns:
            str: Direction identifier understood by the animator; the current
            one if the two stand in exactly the same spot.
        """
        dx = (other.x + other.width / 2) - (self.x + self.width / 2)
        dy = (other.y + other.height / 2) - (self.y + self.height / 2)
        largest = max(abs(dx), abs(dy))
        if largest <= 0.0:
            return self.animator.current_direction
        current = self.animator.current_direction
        now_x = 1.0 if "right" in current else (-1.0 if "left" in current else 0.0)
        now_y = 1.0 if "front" in current else (-1.0 if "back" in current else 0.0)
        fx = self._facing_component(dx, largest, now_x)
        fy = self._facing_component(dy, largest, now_y)
        horizontal = "" if fx == 0.0 else ("right" if fx > 0 else "left")
        if fy == 0.0:
            return horizontal or current
        vertical = "front" if fy > 0 else "back"
        return f"{vertical}_{horizontal}" if horizontal else vertical

    def _hold_for_talk(self, dt: float) -> bool:
        """Stand still and face whoever stopped the NPC for a word.

        Args:
            dt: Delta time in seconds.

        Returns:
            bool: True while the NPC is being talked to, which means the
            caller must not advance any behaviour of its own this frame.
        """
        if self.talking_to is None:
            return False
        # Only the velocity is cleared, not the walk target: the NPC picks his
        # way up again where he left it once the player is done.
        self.set_movement(0.0, 0.0)
        self._animate(dt, False, self._direction_towards(self.talking_to))
        return True

    def chat_line(self) -> str:
        """Pick something to say, never the same line twice in a row.

        Returns:
            A random sentence fitting the NPC's class and trade.
        """
        sentences = sentences_for(self.SOCIAL_CLASS, self.IS_TRADER)
        if len(sentences) > 1 and self._last_chat_line in sentences:
            sentences.remove(self._last_chat_line)
        self._last_chat_line = random.choice(sentences) if sentences else "Good day to you."
        return self._last_chat_line

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
        self.set_movement(
            self._facing_component(dx, largest, self.vel_x),
            self._facing_component(dy, largest, self.vel_y),
        )

    @staticmethod
    def _facing_component(delta: float, largest: float, current: float) -> float:
        """One axis of the facing, -1, 0 or 1, with hysteresis.

        Args:
            delta: Movement along this axis.
            largest: The larger of the two axes' movements (positive).
            current: This axis' facing so far (-1, 0 or 1).

        Returns:
            float: The new facing component.
        """
        sign = 1.0 if delta > 0 else -1.0
        # Kept while it points the same way and stays above the lower bound;
        # taken up only above the higher one.
        threshold = DIAGONAL_THRESHOLD + (-DIAGONAL_HYSTERESIS if current == sign else DIAGONAL_HYSTERESIS)
        return sign if abs(delta) >= largest * threshold else 0.0

    def _animate(self, dt: float, is_moving: bool, direction: Optional[str] = None) -> None:
        """Advance the animator and any fade, and refresh the current frame.

        Args:
            dt: Delta time in seconds.
            is_moving: Whether the NPC moved this frame.
            direction: Animation direction to use instead of the one the
                current velocity implies.
        """
        self.animator.update(dt, direction or self._determine_direction(is_moving), is_moving)
        self.sprite = self.animator.get_current_frame()
        self.source_sprite = self.animator.get_current_source_frame()
        self.was_moving = is_moving
        self._update_fade(dt)

    def inspect_lines(self, observer=None) -> List[str]:
        """Debug lines for the "Inspect" window, plus the patrol path."""
        lines = super().inspect_lines(observer) + [
            "**Behaviour**",
            f"Social class: {self.SOCIAL_CLASS}",
            f"Speed: {self.speed:.0f} px/s",
        ]
        if self.path is None:
            return lines + ["Path: none"]
        path = self.path
        shape = "closed" if path.closed else "open"
        # A closed path repeats its first point at the end
        corners = len(path.points) - 1 if path.closed else len(path.points)
        lines += [
            f"Path: {corners} corners, {path.length:.0f} px, {shape}, margin {path.margin:.0f} px",
            f"On path at: {self.path_distance:.0f} px",
        ]
        if self.path_target is None:
            lines.append("Heading to: standing still")
        else:
            gap = path.signed_gap(self.path_distance, self.path_target)
            lines.append(f"Heading to: {self.path_target:.0f} px ({abs(gap):.0f} px away)")
        return lines

    @abstractmethod
    def update(self, dt: float, *args: Any, **kwargs: Any) -> None:
        """Advance behaviour, movement and animation by ``dt`` seconds."""
