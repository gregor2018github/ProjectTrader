"""A floating building drawn as it moves on the water (models/afloat.py): lifted and turned about its waterline."""

import math
from typing import Dict, Tuple

import pygame

#: The turned pictures, by the scaled sprite they were turned from and the angle; a few per zoom level
_turned: Dict[Tuple[int, float], Tuple[pygame.Surface, pygame.Surface]] = {}
_MAX_TURNED = 64


def turned(sprite: pygame.Surface, angle: float) -> pygame.Surface:
    """The sprite turned anticlockwise by angle degrees, kept for the next time."""
    if angle == 0:
        return sprite
    key = (id(sprite), angle)
    kept = _turned.get(key)
    if kept is not None and kept[0] is sprite:
        return kept[1]
    if len(_turned) >= _MAX_TURNED:
        _turned.clear()
    result = pygame.transform.rotozoom(sprite, angle, 1.0)
    _turned[key] = (sprite, result)
    return result


def afloat_pose(sprite: pygame.Surface, draw_x: float, draw_y: float, bob_px: float,
                angle: float) -> Tuple[pygame.Surface, Tuple[int, int]]:
    """The picture to draw and where, for a sprite drawn at (draw_x, draw_y) when still, lifted by
    bob_px screen px and turned by angle degrees about the middle of its foot."""
    w, h = sprite.get_size()
    picture = turned(sprite, angle)
    # The foot's middle, from the sprite's centre, turned with it (y down: anticlockwise on the screen)
    a = math.radians(angle)
    pivot_x, pivot_y = (h / 2) * math.sin(a), (h / 2) * math.cos(a)
    centre_x = draw_x + w / 2 - pivot_x
    centre_y = draw_y + h + bob_px - pivot_y
    return picture, (round(centre_x - picture.get_width() / 2), round(centre_y - picture.get_height() / 2))
