"""The mouse pointer, shown by the system rather than drawn into the frame.

The game draws into a 1760x1064 surface scaled to fit the screen, which on a
wider screen leaves black bars beside it. A pointer blitted into that surface
stops at its edge while the real mouse goes on into the bars, so the pointer is
a system cursor made from the game's own images instead, sized to the scaled
frame so it looks as it would drawn into it. Call ``use()`` with the pointer
wanted every frame; it only changes anything when that differs.
"""
import os
from typing import Optional

import pygame

from src.config.constants import PICTURES_PATH, SCREEN_WIDTH, SCREEN_HEIGHT, SIDEBAR_WIDTH

# Each pointer: its image, its height in the game's 1760x1064 pixels, and where
# its tip is, as a fraction of its size
_POINTERS = {
    "hand": (os.path.join(PICTURES_PATH, "cursor_1.png"), 41, (0.0, 0.0)),
    "quill": (os.path.join(PICTURES_PATH, "contracts", "cursor_quill.png"), 80, (0.0, 1.0)),
}

_images: dict[str, Optional[pygame.Surface]] = {}
_shown: object = ()  # (pointer, scale) last set; () before the first


def _frame_scale() -> float:
    """How many screen pixels one pixel of the game's frame is drawn as."""
    win_w, win_h = pygame.display.get_window_size()
    return min(win_w / (SCREEN_WIDTH + SIDEBAR_WIDTH), win_h / SCREEN_HEIGHT)


def _image(pointer: str) -> Optional[pygame.Surface]:
    if pointer not in _images:
        try:
            _images[pointer] = pygame.image.load(_POINTERS[pointer][0]).convert_alpha()
        except (pygame.error, FileNotFoundError) as e:
            print(f"Failed to load cursor '{pointer}': {e}")
            _images[pointer] = None
    return _images[pointer]


def use(pointer: Optional[str]) -> None:
    """Show *pointer* ("hand" or "quill"), or no pointer at all for None."""
    global _shown
    if pointer is None:
        if _shown is not None:
            pygame.mouse.set_visible(False)
            _shown = None
        return

    scale = _frame_scale()
    if _shown == (pointer, scale):
        return
    _shown = (pointer, scale)

    image = _image(pointer)
    if image is not None:
        _, height, (tip_x, tip_y) = _POINTERS[pointer]
        w, h = image.get_size()
        size = (max(1, round(w * height / h * scale)), max(1, round(height * scale)))
        image = pygame.transform.smoothscale(image, size)
        hotspot = (min(int(tip_x * size[0]), size[0] - 1), min(int(tip_y * size[1]), size[1] - 1))
        try:
            pygame.mouse.set_cursor(pygame.cursors.Cursor(hotspot, image))
        except pygame.error as e:
            print(f"Failed to set cursor '{pointer}': {e}")
            pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_ARROW)
    else:
        pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_ARROW)
    pygame.mouse.set_visible(True)


def reset() -> None:
    """Forget the pointer shown, after the display was set up anew."""
    global _shown
    _shown = ()
