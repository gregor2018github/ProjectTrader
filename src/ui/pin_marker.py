"""The mark of a good pinned to the top bar: a folded corner on its box."""
from typing import Tuple

import pygame

PIN_CORNER_SIZE = 8         # the fold's legs, in pixels
PIN_CORNER_SHADE = 0.6      # its colour: the box frame's, darkened by this factor


def draw_pin_corner(screen: pygame.Surface, box: pygame.Rect, frame_color: Tuple[int, int, int]) -> None:
    """Fold *box*'s top-right corner over: a small triangle in a darker tone of its frame's colour."""
    shade = tuple(int(c * PIN_CORNER_SHADE) for c in frame_color[:3])
    right, top = box.right - 1, box.top
    pygame.draw.polygon(screen, shade, [(right - PIN_CORNER_SIZE, top), (right, top), (right, top + PIN_CORNER_SIZE)])
