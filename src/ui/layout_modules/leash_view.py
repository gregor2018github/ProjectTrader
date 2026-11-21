"""The rope between the player and a sheep on the leash, drawn into the map's render queue.

Its shape is models/leash.py's ``rope_points`` (sagging with the slack, swaying
a little, taut once they are a rope's length apart), its ends the player's hand
and the sheep's neck (``LostSheepOnMap.rope_ends``). It is drawn as a sprite of
its own in the render queue, sorted just over whichever of the two stands
nearer the viewer, so the lighting darkens it with them at night.
"""

from typing import Any, Dict, Optional

import pygame

from ...models.leash import rope_points

ROPE = (150, 108, 62)          # hemp
ROPE_DARK = (70, 46, 26)       # its edge and shadow
ROPE_LIGHT = (196, 158, 104)   # a glint along its top
#: The rope's width at zoom 1, in screen pixels (its dark edge comes on top)
ROPE_WIDTH = 2.0


def leash_entry(game_map: Any, quest_map: Any, offset_x: int, offset_y: int,
                seconds: float) -> Optional[Dict[str, Any]]:
    """The render queue's entry for the rope, or None while nobody is led (or it is out of view).

    Args:
        game_map: The GameMap (its camera and player).
        quest_map: The LostSheepOnMap, whose rope_ends give where it is held and tied.
        offset_x, offset_y: Where the map's content area starts on screen.
        seconds: Real seconds, for its sway.
    """
    if quest_map is None:
        return None
    player = game_map.map_player
    ends = quest_map.rope_ends(player)
    if ends is None:
        return None
    camera = game_map.camera
    world = rope_points(*ends, seconds)
    points = [camera.apply(x, y) for x, y in world]
    width = max(2, round(ROPE_WIDTH * camera.zoom))
    pad = width + 2
    left = min(x for x, _ in points) - pad
    top = min(y for _, y in points) - pad
    right = max(x for x, _ in points) + pad
    bottom = max(y for _, y in points) + pad
    if right - left > 4000 or bottom - top > 4000:
        return None
    surf = pygame.Surface((max(1, int(right - left) + 1), max(1, int(bottom - top) + 1)), pygame.SRCALPHA)
    local = [(x - left, y - top) for x, y in points]
    shadow = [(x, y + max(1, width // 2)) for x, y in local]
    pygame.draw.lines(surf, (*ROPE_DARK, 90), False, shadow, width)
    pygame.draw.lines(surf, ROPE_DARK, False, local, width + 2)
    pygame.draw.lines(surf, ROPE, False, local, width)
    if width >= 3:
        pygame.draw.lines(surf, ROPE_LIGHT, False, [(x, y - width // 3) for x, y in local], 1)
    # The knot at the sheep's neck, and the hand's grip
    pygame.draw.circle(surf, ROPE_DARK, (round(local[-1][0]), round(local[-1][1])), width + 1)
    pygame.draw.circle(surf, ROPE, (round(local[-1][0]), round(local[-1][1])), max(1, width))
    pygame.draw.circle(surf, ROPE_DARK, (round(local[0][0]), round(local[0][1])), width)
    flip = quest_map.flip
    return {
        'sprite': surf,
        'pos': (left + offset_x, top + offset_y),
        'y_sort': max(player.y_sort, flip.y_sort) + 0.01,
    }
