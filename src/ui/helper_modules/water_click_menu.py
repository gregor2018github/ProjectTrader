"""Water click menu module.

Handles detecting clicks on water tiles and opening a small generic
interaction menu for them (distinct from HouseMenu, since a water body is
not a building). Currently offers "Throw Stone"; fishing will be added here
later.
"""

import pygame
import os
from typing import Optional, List, Tuple, TYPE_CHECKING

from ...config.colors import SANDY_BROWN, DARK_BROWN, BLACK, WHITE
from ...config.constants import FONTS_PATH, TILE_SIZE
from ..ui_utils import draw_9slice

if TYPE_CHECKING:
    from ...models.water import Water
    from ...models.map import GameMap, Camera
    from ...game_state import GameState


# Maximum distance (in world units) the player can be from a water body to interact with it
WATER_INTERACTION_DISTANCE = 48  # About 1.5 tiles — matches HOUSE_INTERACTION_DISTANCE


def _screen_to_world(pos: Tuple[int, int], camera: 'Camera', map_content_rect: pygame.Rect) -> Optional[Tuple[float, float]]:
    """Inverse of Camera.apply() — screen position to world coordinates."""
    scaled_tile_size = round(TILE_SIZE * camera.zoom)
    scale_factor = scaled_tile_size / float(TILE_SIZE)
    if scale_factor <= 0:
        return None
    local_x = pos[0] - map_content_rect.x
    local_y = pos[1] - map_content_rect.y
    return (local_x / scale_factor + camera.x, local_y / scale_factor + camera.y)


def is_player_near_water(player, water: 'Water') -> bool:
    """Check if the player is close enough to a water body to interact with it."""
    player_center_x = player.x + player.width / 2
    player_center_y = player.y + player.height / 2
    return water.distance_to_point(player_center_x, player_center_y) <= WATER_INTERACTION_DISTANCE


def get_hovered_water(
    mouse_pos: Tuple[int, int],
    game_map: 'GameMap',
    view_rect: pygame.Rect,
) -> Optional['Water']:
    """Determine which water body (if any) the mouse is clicking, if the player is near it."""
    map_content_rect = view_rect.inflate(-10, -10)
    if not map_content_rect.collidepoint(mouse_pos):
        return None

    world_pos = _screen_to_world(mouse_pos, game_map.camera, map_content_rect)
    if world_pos is None:
        return None
    wx, wy = world_pos

    player = game_map.map_player
    for water in game_map.tmx_map.waters:
        if water.contains_point(wx, wy) and is_player_near_water(player, water):
            return water
    return None


def show_water_menu(game_state: 'GameState', water: 'Water', click_pos: Tuple[int, int]) -> None:
    """Open the generic interaction menu for a clicked water body."""
    options = ["Throw Stone"]

    def menu_callback(option_text: str) -> None:
        if option_text == "Throw Stone":
            water.throw_rock(game_state)
            return
        game_state.info_window = None

    game_state.info_window = WaterMenu(
        game_state.screen,
        "Water",
        options,
        game_state.font,
        game_state,
        click_pos=click_pos,
        callback=menu_callback,
    )


class WaterMenu:
    """A small pop-up menu for generic map-tile interactions (currently: water).

    Visually styled the same as HouseMenu, but not tied to a House — it takes
    a plain title string instead, since a water tile isn't a building.
    """

    def __init__(
        self,
        screen: pygame.Surface,
        title: str,
        options: List[str],
        font: pygame.font.Font,
        game_state: 'GameState',
        click_pos: Tuple[int, int],
        callback=None,
    ):
        self.screen = screen
        self.title = title
        self.options = options
        self.font = font
        self.game_state = game_state
        self.callback = callback

        try:
            self.title_font = pygame.font.Font(os.path.join(FONTS_PATH, "Medici Text.ttf"), 26)
        except Exception:
            self.title_font = font

        self.width = 220
        self.button_height = 40
        self.padding = 10
        self.header_height = 44
        self.total_height = self.header_height + (len(options) * (self.button_height + self.padding)) + self.padding

        self.close_button_size = 20

        screen_w, screen_h = screen.get_size()
        self.x = max(0, min(click_pos[0], screen_w - self.width))
        self.y = max(0, min(click_pos[1], screen_h - self.total_height))
        self.rect = pygame.Rect(self.x, self.y, self.width, self.total_height)

        close_pad = (self.header_height - self.close_button_size) // 2
        self.close_rect = pygame.Rect(
            self.x + self.width - self.close_button_size - close_pad,
            self.y + close_pad,
            self.close_button_size,
            self.close_button_size,
        )

        self.buttons: List[Tuple[pygame.Rect, str]] = []
        current_y = self.y + self.header_height + self.padding
        for option in options:
            btn_rect = pygame.Rect(self.x + self.padding, current_y, self.width - 2 * self.padding, self.button_height)
            self.buttons.append((btn_rect, option))
            current_y += self.button_height + self.padding

    def _close(self) -> None:
        self.game_state.menu_fade_window = self
        self.game_state.menu_fade_timer = self.game_state.menu_fade_duration
        self.game_state.info_window = None
        self.game_state.active_house_menu = None

    def handle_click(self, pos: Tuple[int, int]) -> bool:
        if self.close_rect.collidepoint(pos):
            self._close()
            return True

        if not self.rect.collidepoint(pos):
            self._close()
            return True

        for rect, option in self.buttons:
            if rect.collidepoint(pos):
                if self.callback:
                    self.callback(option)
                else:
                    self.game_state.info_window = None
                return True
        return False

    def draw(self, alpha_scale: float = 1.0) -> None:
        if alpha_scale <= 0:
            return

        target_surf = self.screen
        ox, oy = 0, 0
        temp_surf = None

        if alpha_scale < 1.0:
            temp_surf = pygame.Surface((self.rect.width, self.rect.height), pygame.SRCALPHA)
            target_surf = temp_surf
            ox, oy = -self.rect.x, -self.rect.y

        mouse_pos = pygame.mouse.get_pos()

        body_rect = self.rect.move(ox, oy)
        game = self.game_state.game
        if game and hasattr(game, 'pic_info_window'):
            draw_9slice(target_surf, game.pic_info_window, body_rect)
        else:
            pygame.draw.rect(target_surf, SANDY_BROWN, body_rect)
            pygame.draw.rect(target_surf, DARK_BROWN, body_rect, 3)

        title_surf = self.title_font.render(self.title, True, DARK_BROWN)
        title_rect = title_surf.get_rect(center=(body_rect.centerx, body_rect.y + self.header_height // 2))
        target_surf.blit(title_surf, title_rect)

        close_draw_rect = self.close_rect.move(ox, oy)
        pygame.draw.rect(target_surf, DARK_BROWN, close_draw_rect)
        if alpha_scale >= 1.0 and self.close_rect.collidepoint(mouse_pos):
            ov = pygame.Surface(close_draw_rect.size, pygame.SRCALPHA)
            ov.fill((255, 255, 255, 40))
            target_surf.blit(ov, close_draw_rect)
        mg = 5
        pygame.draw.line(target_surf, WHITE,
                          (close_draw_rect.left + mg, close_draw_rect.top + mg),
                          (close_draw_rect.right - mg, close_draw_rect.bottom - mg), 2)
        pygame.draw.line(target_surf, WHITE,
                          (close_draw_rect.left + mg, close_draw_rect.bottom - mg),
                          (close_draw_rect.right - mg, close_draw_rect.top + mg), 2)

        for rect, text in self.buttons:
            btn_rect = rect.move(ox, oy)
            is_hovered = alpha_scale >= 1.0 and rect.collidepoint(mouse_pos)
            pygame.draw.rect(target_surf, SANDY_BROWN, btn_rect)
            pygame.draw.rect(target_surf, DARK_BROWN, btn_rect, 2)
            if is_hovered:
                ov = pygame.Surface(btn_rect.size, pygame.SRCALPHA)
                ov.fill((0, 0, 0, 30))
                target_surf.blit(ov, btn_rect)
            text_surf = self.font.render(text, True, BLACK)
            target_surf.blit(text_surf, text_surf.get_rect(center=btn_rect.center))

        if temp_surf:
            temp_surf.set_alpha(int(255 * alpha_scale))
            self.screen.blit(temp_surf, (self.rect.x, self.rect.y))
