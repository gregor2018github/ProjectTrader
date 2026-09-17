"""Directional sprite animation shared by every figurine on the map.

Extracted from ``map.py`` so that figurines (player, NPCs, animals) can use it
without importing the map module, which would be circular.
"""

import math
import os
import pygame
from typing import Dict, List, Optional, Tuple, Any

from ...config.constants import MAX_RECULCULATIONS_PER_SEC


class DirectionalAnimator:
    """Handles directional animations with sprite fallbacks."""

    DIRECTIONS: Tuple[str, ...] = (
        "front", "back", "left", "right",
        "front_left", "front_right", "back_left", "back_right",
    )

    # A direction with no artwork of its own borrows the cardinal one it is
    # closest to. Diagonals fall back to the vertical component, which is what
    # the movement code picked before diagonals existed.
    DIRECTION_FALLBACKS: Dict[str, str] = {
        "front_left": "front",
        "front_right": "front",
        "back_left": "back",
        "back_right": "back",
    }

    # Source frames are kept at this multiple of the target box so that zooming
    # in still downsamples (rather than upsamples) from a crisp original.
    NORMALIZE_SUPERSAMPLE: int = 4

    def __init__(
        self,
        base_path: str,
        sprite_definitions: Dict[str, Dict[str, Any]],
        target_width: int,
        fallback_static: str,
        normalize: bool = False,
        target_height: Optional[int] = None,
        scale_overrides: Optional[Dict[Tuple[str, str], float]] = None,
    ) -> None:
        """Initialize the animator.
        
        Args:
            base_path: Root folder for sprites.
            sprite_definitions: Configuration for directions and animations.
            target_width: Desired pixel width for frames.
            fallback_static: Filename for the emergency fallback image.
            normalize: If True, every frame is cropped to its opaque content and
                re-rendered bottom-centred into one common box at a single shared
                scale, preserving both aspect ratio and relative size. Use this when
                the source artwork has inconsistent canvas sizes or padding. The
                resulting box is ``box_width`` x ``box_height``, which may exceed
                the logical ``target_width`` x ``target_height``.
            target_height: Height of the normalized box. Defaults to the height the
                fallback static image would get when scaled to ``target_width``.
            scale_overrides: Extra size multiplier per (direction, "static"/"move")
                group, applied on top of the shared normalized scale. Frames stay
                bottom-centred and keep their aspect ratio. Normalized mode only.
        """
        self.base_path: str = base_path
        self.sprite_definitions: Dict[str, Dict[str, Any]] = sprite_definitions
        self.target_width: int = target_width
        self.normalize: bool = normalize
        self.scale_overrides: Dict[Tuple[str, str], float] = dict(scale_overrides or {})

        self.fallback_surface: pygame.Surface = self._load_image(fallback_static)
        if self.fallback_surface is None:
            self.fallback_surface = pygame.Surface((self.target_width, self.target_width), pygame.SRCALPHA)
            self.fallback_surface.fill((255, 0, 255))

        scaled = self._scale_to_target(self.fallback_surface)
        self.fallback_scaled: pygame.Surface = scaled if scaled else self.fallback_surface.copy()

        # Fixed logical box every normalized frame is rendered into.
        if target_height is None:
            target_height = self.fallback_scaled.get_height()
        self.target_height: int = max(1, int(target_height))
        # Actual size of a built frame; set by the build pass below, which derives
        # it from the artwork rather than from a hard-coded figure.
        self.box_width: int = target_width
        self.box_height: int = self.target_height

        self.frames: Dict[str, Dict[str, List[pygame.Surface]]] = {}
        self.source_frames: Dict[str, Dict[str, List[pygame.Surface]]] = {}

        # Pass 1 — load every frame. Directions with no artwork of their own are
        # recorded here and resolved after the build, so that the direction they
        # borrow from is always fully built first.
        missing: Dict[str, List[str]] = {}
        raw: Dict[str, Dict[str, List[pygame.Surface]]] = {}
        # Which direction each group's artwork actually came from. Differs from the
        # key only where a direction borrows another's frames.
        self.frame_origin: Dict[str, Dict[str, str]] = {
            direction: {"static": direction, "move": direction} for direction in self.DIRECTIONS
        }

        for direction in self.DIRECTIONS:
            config = self.sprite_definitions.get(direction, {})

            source_static = self._load_image(config.get("static", ""))
            if source_static is None:
                missing.setdefault(direction, []).append("static")

            move_sources: List[pygame.Surface] = []
            for filename in config.get("move", []):
                source_frame = self._load_image(filename)
                if source_frame is not None:
                    move_sources.append(source_frame)
            if not move_sources:
                missing.setdefault(direction, []).append("move")

            raw[direction] = {
                "static": [source_static] if source_static is not None else [],
                "move": move_sources,
            }

        # Pass 2 — turn the raw frames into draw-ready ones.
        if self.normalize:
            self._build_normalized(raw)
        else:
            self._build_scaled(raw)

        # Pass 3 — point directions with no artwork of their own at their
        # fallback, per animation group: a direction may have walk frames but no
        # static pose (or the reverse).
        for direction, keys in missing.items():
            fallback = self.DIRECTION_FALLBACKS.get(direction)
            if fallback is None or fallback not in self.frames:
                continue
            for key in keys:
                self.frames[direction][key] = self.frames[fallback][key]
                self.source_frames[direction][key] = self.source_frames[fallback][key]
                self.frame_origin[direction][key] = fallback

        self.current_direction: str = "front"
        self.is_moving: bool = False
        self.current_frame_index: int = 0
        self.time_since_last_frame: float = 0.0

        # Use the recalc constant as baseline and slow animation slightly for readability.
        base_interval = 1.0 / max(1, MAX_RECULCULATIONS_PER_SEC)
        self.frame_interval: float = max(base_interval * 8, 0.05)

    def _load_image(self, filename: str) -> Optional[pygame.Surface]:
        """Load image from disk.
        
        Args:
            filename: Image filename.
            
        Returns:
            Optional[pygame.Surface]: Loaded surface or None.
        """
        if not filename:
            return None

        path = os.path.join(self.base_path, filename)
        if not os.path.exists(path):
            return None

        try:
            return pygame.image.load(path).convert_alpha()
        except pygame.error:
            return None

    def _scale_to_target(self, image: Optional[pygame.Surface]) -> Optional[pygame.Surface]:
        """Scale an image to the target width while preserving aspect ratio.
        
        Args:
            image: Source surface.
            
        Returns:
            Optional[pygame.Surface]: Scaled surface.
        """
        if image is None:
            return None

        original_width, original_height = image.get_size()
        if original_width <= 0 or original_height <= 0:
            return None

        scale_ratio = self.target_width / float(original_width)
        scaled_height = max(1, int(round(original_height * scale_ratio)))
        return pygame.transform.smoothscale(image, (self.target_width, scaled_height))

    def _build_scaled(self, raw: Dict[str, Dict[str, List[pygame.Surface]]]) -> None:
        """Build frames by scaling each image to ``target_width`` (legacy path).

        Args:
            raw: Loaded source surfaces per direction and animation group.
        """
        self.box_width = self.target_width
        self.box_height = self.target_height
        for direction in self.DIRECTIONS:
            groups = raw.get(direction, {})
            built: Dict[str, List[pygame.Surface]] = {}
            sources: Dict[str, List[pygame.Surface]] = {}
            for key in ("static", "move"):
                srcs = groups.get(key) or [self.fallback_surface]
                sources[key] = srcs
                built[key] = [self._scale_to_target(img) or self.fallback_scaled for img in srcs]
            self.frames[direction] = built
            self.source_frames[direction] = sources

    def _build_normalized(self, raw: Dict[str, Dict[str, List[pygame.Surface]]]) -> None:
        """Build frames at a single shared scale, bottom-centred in a common box.

        Every frame is cropped to its opaque content and scaled by ONE factor
        derived from the reference (fallback static) image, so a pose the artist
        drew taller — walking towards the camera, say — really does render taller.
        The box is then sized to hold the largest frame, which means the artwork
        alone decides the proportions; nothing here needs touching when it changes.

        The result is uniform-size frames, so the per-zoom cache stays trivial and
        nothing costs anything per rendered frame.

        Args:
            raw: Loaded source surfaces per direction and animation group.
        """
        ss = self.NORMALIZE_SUPERSAMPLE

        # One scale for everything: the reference image's content height becomes
        # exactly target_height, and every other frame keeps its size relative to it.
        ref = self._content_rect(self.fallback_surface)
        scale = (self.target_height * ss) / float(max(1, ref.height))

        # Size the box from the largest frame, never smaller than the logical box.
        all_frames = [
            (self._content_rect(img), scale * self.scale_overrides.get((direction, key), 1.0))
            for direction, groups in raw.items()
            for key, frames in groups.items()
            for img in frames
        ]
        box_w = self.target_width * ss
        box_h = self.target_height * ss
        for rect, frame_scale in all_frames:
            box_w = max(box_w, int(math.ceil(rect.width * frame_scale)))
            box_h = max(box_h, int(math.ceil(rect.height * frame_scale)))
        # Keep the box a whole number of logical pixels so the zoom-1 downscale is exact.
        self.box_width = int(math.ceil(box_w / float(ss)))
        self.box_height = int(math.ceil(box_h / float(ss)))
        box_w, box_h = self.box_width * ss, self.box_height * ss

        cache: Dict[Tuple[int, float], pygame.Surface] = {}

        def normalize(img: pygame.Surface, frame_scale: float) -> pygame.Surface:
            key = (id(img), frame_scale)
            if key not in cache:
                rect = self._content_rect(img)
                dest_w = max(1, int(round(rect.width * frame_scale)))
                dest_h = max(1, int(round(rect.height * frame_scale)))
                scaled = pygame.transform.smoothscale(img.subsurface(rect), (dest_w, dest_h))
                canvas = pygame.Surface((box_w, box_h), pygame.SRCALPHA)
                # Bottom-centred, so every pose stands on the same baseline.
                canvas.blit(scaled, ((box_w - dest_w) // 2, box_h - dest_h))
                cache[key] = canvas
            return cache[key]

        for direction in self.DIRECTIONS:
            groups = raw.get(direction, {})
            built: Dict[str, List[pygame.Surface]] = {}
            sources: Dict[str, List[pygame.Surface]] = {}
            for key in ("static", "move"):
                frame_scale = scale * self.scale_overrides.get((direction, key), 1.0)
                srcs = [normalize(img, frame_scale) for img in (groups.get(key) or [self.fallback_surface])]
                sources[key] = srcs
                built[key] = [
                    pygame.transform.smoothscale(img, (self.box_width, self.box_height))
                    for img in srcs
                ]
            self.frames[direction] = built
            self.source_frames[direction] = sources

    @staticmethod
    def _content_rect(image: pygame.Surface) -> pygame.Rect:
        """Opaque bounding box of an image, falling back to its full canvas.

        Args:
            image: Surface to measure.

        Returns:
            pygame.Rect: The area holding actual artwork.
        """
        rect = image.get_bounding_rect()
        if rect.width <= 0 or rect.height <= 0:
            return pygame.Rect(0, 0, image.get_width(), image.get_height())
        return rect

    def update(self, dt: float, direction: str, is_moving: bool) -> None:
        """Update animation state.
        
        Args:
            dt: Delta time.
            direction: Movement direction string.
            is_moving: True if moving, False otherwise.
        """
        if direction not in self.frames:
            direction = "front"

        if direction != self.current_direction or is_moving != self.is_moving:
            self.current_direction = direction
            self.is_moving = is_moving
            self.current_frame_index = 0
            self.time_since_last_frame = 0.0

        self.time_since_last_frame += dt

        active_key = "move" if self.is_moving else "static"
        frames = self.frames[self.current_direction][active_key]

        if len(frames) <= 1:
            self.current_frame_index = 0
            return

        if self.time_since_last_frame >= self.frame_interval:
            self.time_since_last_frame %= self.frame_interval
            self.current_frame_index = (self.current_frame_index + 1) % len(frames)

    def current_frame_origin(self) -> Tuple[str, str]:
        """Identify the artwork behind the current frame.

        Returns:
            Tuple[str, str]: (direction the frames were authored for, "static"/"move").
                The direction differs from ``current_direction`` when this direction
                borrows another's artwork.
        """
        key = "move" if self.is_moving else "static"
        return self.frame_origin[self.current_direction][key], key

    def get_current_frame(self) -> pygame.Surface:
        """Get the current scaled frame.
        
        Returns:
            pygame.Surface: The active frame surface.
        """
        active_key = "move" if self.is_moving else "static"
        frames = self.frames[self.current_direction][active_key]
        if not frames:
            return self.fallback_scaled
        return frames[self.current_frame_index % len(frames)]

    def get_current_source_frame(self) -> pygame.Surface:
        """Get the current unscaled source frame.
        
        Returns:
            pygame.Surface: The active source surface.
        """
        active_key = "move" if self.is_moving else "static"
        frames = self.source_frames[self.current_direction][active_key]
        if not frames:
            return self.fallback_surface
        return frames[self.current_frame_index % len(frames)]

