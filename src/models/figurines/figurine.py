"""Abstract base class for everything that walks around on the map.

A *figurine* is any animated, y-sorted, world-positioned creature: the player,
an NPC, or an animal. This class owns only what all of them share — world
position, the current animation frame, the zoom-scaled sprite cache and the
y-sort key. Behaviour (movement, AI, collision shape) belongs in the subclass.
"""

import os
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

import pygame

from .animator import DirectionalAnimator

# Root of the figurine artwork tree. Subclasses append their own path segments,
# e.g. ``os.path.join(FIGURINE_SPRITE_ROOT, 'humans', 'player')``.
FIGURINE_SPRITE_ROOT = os.path.join('assets', 'map_sprites', 'figurines')


class Figurine(ABC):
    """A world-positioned, animated map entity."""

    def __init__(self, x: float, y: float, tile_size: int) -> None:
        """Initialize shared figurine state.

        Args:
            x: World X of the sprite's top-left corner.
            y: World Y of the sprite's top-left corner.
            tile_size: Base tile size, used for scaling sprites and speeds.
        """
        self.x: float = float(x)
        self.y: float = float(y)
        self.tile_size: int = tile_size

        # Set up by _init_animator() in the subclass.
        self.animator: Optional[DirectionalAnimator] = None
        self.sprite: Optional[pygame.Surface] = None
        self.source_sprite: Optional[pygame.Surface] = None
        self.sprite_width: int = 0
        self.sprite_height: int = 0

        # Zoom-scaled sprite cache: {zoom -> {id(source frame) -> surface}}
        self.scaled_sprite_cache: Dict[float, Dict[int, pygame.Surface]] = {}

    # ------------------------------------------------------------------
    # Setup helpers
    # ------------------------------------------------------------------

    def _init_animator(
        self,
        sprite_dir: str,
        sprite_definitions: Dict[str, Dict[str, Any]],
        target_width: int,
        fallback_static: str,
        **animator_kwargs: Any,
    ) -> DirectionalAnimator:
        """Build the figurine's animator and prime the current-frame fields.

        Args:
            sprite_dir: Directory holding this figurine's PNGs.
            sprite_definitions: Per-direction static/move filename mapping.
            target_width: Logical width the frames are scaled to, at zoom 1.
            fallback_static: Filename used when a requested frame is missing.
            **animator_kwargs: Passed through to :class:`DirectionalAnimator`.

        Returns:
            DirectionalAnimator: The animator, also stored on ``self.animator``.
        """
        self.animator = DirectionalAnimator(
            base_path=sprite_dir,
            sprite_definitions=sprite_definitions,
            target_width=target_width,
            fallback_static=fallback_static,
            **animator_kwargs,
        )
        self.sprite = self.animator.get_current_frame()
        self.source_sprite = self.animator.get_current_source_frame()
        return self.animator

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def collision_rect(self) -> pygame.Rect:
        """The rectangle other entities collide with (usually the feet area)."""

    @property
    def display_name(self) -> str:
        """Name shown to the player, e.g. as a menu title."""
        return type(self).__name__

    @property
    def y_sort(self) -> float:
        """Depth-sort key: the figurine's ground baseline."""
        return self.y + self.sprite_height

    @property
    def sprite_draw_offset(self) -> Tuple[float, float]:
        """Offset from (x, y) to the drawn sprite's top-left, in logical pixels."""
        return (0.0, 0.0)

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    def inspect_lines(self) -> List[str]:
        """Lines for the "Inspect" window, in the style of the house one."""
        sprite_dir = self.animator.base_path if self.animator else "-"
        return [
            f"Object Name: {self.display_name}",
            f"Class: {type(self).__name__}",
            f"Coordinates: X={round(self.x, 1)}, Y={round(self.y, 1)}",
            f"Sprites: {sprite_dir}",
        ]

    # ------------------------------------------------------------------
    # Per-frame update
    # ------------------------------------------------------------------

    @abstractmethod
    def update(self, dt: float, *args: Any, **kwargs: Any) -> None:
        """Advance movement and animation by ``dt`` seconds."""

    # ------------------------------------------------------------------
    # Rendering helpers
    # ------------------------------------------------------------------

    def _get_scaled_sprite(self, zoom: float) -> pygame.Surface:
        """Return the current frame scaled to the camera zoom, via a cache.

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
                source_width = base_frame.get_width()
                source_height = base_frame.get_height()
                if source_width <= 0 or source_height <= 0:
                    cache[frame_id] = self.sprite
                else:
                    target_width = max(1, int(round(self.sprite_width * zoom)))
                    target_height = max(1, int(round(self.sprite_height * zoom)))
                    if target_width >= source_width or target_height >= source_height:
                        cache[frame_id] = pygame.transform.scale(base_frame, (target_width, target_height))
                    else:
                        cache[frame_id] = pygame.transform.smoothscale(base_frame, (target_width, target_height))
        return cache[frame_id]

    def on_zoom_change(self) -> None:
        """Invalidate the sprite cache when the zoom level changes."""
        self.scaled_sprite_cache.clear()
