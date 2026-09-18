"""Figurine hover detection for the map.

The counterpart of house_click_menu for everything that walks around: the
player, human NPCs and animals. A figurine under the mouse and within
interaction range of the player gets the same hover glow as a house.
Figurines are not clickable yet; this module is where that will live.
"""

from typing import Iterator, Optional, Tuple, Union, TYPE_CHECKING

import pygame

from .house_click_menu import get_hovered_house, is_player_near

if TYPE_CHECKING:
    from ...models.figurines.figurine import Figurine
    from ...models.house import House
    from ...models.map import GameMap, Camera


def iter_figurines(game_map: 'GameMap') -> Iterator['Figurine']:
    """Yield every figurine on the map, in render-queue order (player last)."""
    yield from game_map.tmx_map.sheep
    yield from game_map.tmx_map.npcs
    yield game_map.map_player


def figurine_screen_pos(figurine: 'Figurine', camera: 'Camera') -> Tuple[int, int]:
    """Top-left of the figurine's drawn sprite, relative to the map content area.

    Args:
        figurine: The figurine to place.
        camera: Camera for the world-to-screen transform.

    Returns:
        Rounded screen position, without the map view's own offset.
    """
    screen_x, screen_y = camera.apply(figurine.x, figurine.y)
    sprite_offset_x, sprite_offset_y = figurine.sprite_draw_offset
    # The sprite box can be larger than the logical box (see Human)
    return (round(screen_x + sprite_offset_x * camera.zoom),
            round(screen_y + sprite_offset_y * camera.zoom))


def get_hovered_figurine(
    mouse_pos: Tuple[int, int],
    game_map: 'GameMap',
    view_rect: pygame.Rect
) -> Optional['Figurine']:
    """Determine which figurine (if any) the mouse is hovering over.

    Only considers figurines within interaction distance of the player (the
    player always is). The test is pixel-precise, because a figurine's sprite
    box is mostly transparent. When several overlap, the topmost wins.

    Args:
        mouse_pos: Screen coordinates of the mouse cursor (x, y).
        game_map: The GameMap instance containing figurines and camera.
        view_rect: The rectangle defining the map viewport on screen.

    Returns:
        The Figurine being hovered, or None.
    """
    map_content_rect = view_rect.inflate(-10, -10)
    if not map_content_rect.collidepoint(mouse_pos):
        return None

    camera = game_map.camera
    player = game_map.map_player
    hovered = None

    for figurine in iter_figurines(game_map):
        if not is_player_near(player, figurine):
            continue

        sprite = figurine._get_scaled_sprite(camera.zoom)
        draw_x, draw_y = figurine_screen_pos(figurine, camera)
        local = (mouse_pos[0] - map_content_rect.x - draw_x,
                 mouse_pos[1] - map_content_rect.y - draw_y)
        if not sprite.get_rect().collidepoint(local) or sprite.get_at(local).a == 0:
            continue

        # >= because later figurines are drawn on top at equal depth
        if hovered is None or figurine.y_sort >= hovered.y_sort:
            hovered = figurine

    return hovered


def get_hovered_map_object(
    mouse_pos: Tuple[int, int],
    game_map: 'GameMap',
    view_rect: pygame.Rect
) -> Optional[Union['House', 'Figurine']]:
    """Return the hoverable house or figurine under the mouse, whichever is drawn on top.

    Args:
        mouse_pos: Screen coordinates of the mouse cursor (x, y).
        game_map: The GameMap instance.
        view_rect: The rectangle defining the map viewport on screen.

    Returns:
        The hovered House or Figurine, or None.
    """
    house = get_hovered_house(mouse_pos, game_map, view_rect)
    figurine = get_hovered_figurine(mouse_pos, game_map, view_rect)
    if figurine is None:
        return house
    if house is None:
        return figurine
    return figurine if figurine.y_sort >= house.y_sort else house
