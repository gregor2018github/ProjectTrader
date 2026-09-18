"""Figurine hover detection and click menu for the map.

The counterpart of house_click_menu for everything that walks around: the
player, human NPCs and animals. A figurine under the mouse and within
interaction range of the player gets the same hover glow as a house, and
clicking it opens a FigurineMenu, a small speech bubble pointing at the
figurine that is deliberately lighter than the framed HouseMenu.
"""

import os
import random
from typing import Callable, Iterator, List, Optional, Tuple, Union, TYPE_CHECKING

import pygame

from ...config.colors import DARK_BROWN, BLACK
from ...config.constants import FONTS_PATH, SHEEP_VOLUME
from .house_click_menu import get_hovered_house, is_player_near

if TYPE_CHECKING:
    from ...models.figurines.figurine import Figurine
    from ...models.figurines.animals.sheep import Sheep
    from ...models.house import House
    from ...models.map import GameMap, Camera
    from ...game_state import GameState


# Speech bubble styling
BUBBLE_FILL = (236, 222, 188)          # Light parchment, paler than the house menu
BUBBLE_BORDER = DARK_BROWN
BUBBLE_BORDER_WIDTH = 2
BUBBLE_RADIUS = 10
BUBBLE_PADDING = 8
BUBBLE_MIN_WIDTH = 120
TAIL_WIDTH = 16                        # Width of the tail where it meets the bubble
TAIL_HEIGHT = 10
TITLE_FONT_SIZE = 20
OPTION_FONT_SIZE = 20
OPTION_HEIGHT = 28
OPTION_HOVER_FILL = (218, 198, 154)    # Darker parchment tone behind the hovered option


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


def show_figurine_menu(
    game_state: 'GameState',
    figurine: 'Figurine',
    view_rect: pygame.Rect
) -> bool:
    """Open the interaction bubble for a clicked figurine, if it has any options.

    Args:
        game_state: The current game state.
        figurine: The clicked figurine.
        view_rect: The map viewport the figurine was clicked in.

    Returns:
        True if a menu was opened.
    """
    from ...models.figurines.animals.sheep import Sheep

    options: List[str] = []
    if isinstance(figurine, Sheep):
        options.append("Pet Sheep")

    if not options:
        return False

    def menu_callback(option_text: str) -> None:
        if option_text == "Pet Sheep" and isinstance(figurine, Sheep):
            _pet_sheep(game_state, figurine)
        menu.close()

    # The tail points at the top centre of the sprite, or its bottom if the bubble flips below
    camera = game_state.game.game_map.camera
    map_content_rect = view_rect.inflate(-10, -10)
    draw_x, draw_y = figurine_screen_pos(figurine, camera)
    sprite = figurine._get_scaled_sprite(camera.zoom)
    sprite_rect = pygame.Rect(map_content_rect.x + draw_x, map_content_rect.y + draw_y,
                              sprite.get_width(), sprite.get_height())

    menu = FigurineMenu(game_state.screen, figurine, options, game_state, sprite_rect, menu_callback)
    game_state.info_window = menu
    # Keeps the hover glow on and closes the menu when the player walks away
    game_state.active_house_menu = figurine
    return True


def _pet_sheep(game_state: 'GameState', sheep: 'Sheep') -> None:
    """Make the sheep bleat and stand still."""
    game = game_state.game
    player = game.game_map.map_player
    sheep.pet(player.x + player.width / 2)
    if game.sheep_sounds:
        channel = random.choice(game.sheep_sounds).play()
        if channel:
            channel.set_volume(SHEEP_VOLUME)


class FigurineMenu:
    """A small speech-bubble menu for figurine interactions.

    Sparser than HouseMenu: a rounded parchment bubble, a small title, plain
    text rows instead of framed buttons, and no close button. Clicking
    anywhere outside the bubble closes it.
    """

    def __init__(
        self,
        screen: pygame.Surface,
        figurine: 'Figurine',
        options: List[str],
        game_state: 'GameState',
        sprite_rect: pygame.Rect,
        callback: Optional[Callable[[str], None]] = None,
    ):
        """Lay out the bubble above the figurine, or below it if there is no room.

        Args:
            screen: Surface to draw on.
            figurine: The figurine the menu belongs to.
            options: Option labels, top to bottom.
            game_state: The current game state.
            sprite_rect: The figurine's drawn sprite, in screen coordinates.
            callback: Called with the chosen option's label.
        """
        self.screen = screen
        self.figurine = figurine
        self.house = figurine  # map_view's distance-based auto-close looks for .house
        self.options = options
        self.game_state = game_state
        self.callback = callback

        try:
            self.title_font = pygame.font.Font(os.path.join(FONTS_PATH, "Medici Text.ttf"), TITLE_FONT_SIZE)
            self.option_font = pygame.font.Font(os.path.join(FONTS_PATH, "RomanAntique.ttf"), OPTION_FONT_SIZE)
        except Exception:
            self.title_font = self.option_font = game_state.font

        self.title = getattr(figurine, 'display_name', type(figurine).__name__)
        self.title_height = self.title_font.get_linesize()

        content_width = max(
            [self.title_font.size(self.title)[0]]
            + [self.option_font.size(option)[0] + 2 * BUBBLE_PADDING for option in options]
        )
        width = max(BUBBLE_MIN_WIDTH, content_width + 2 * BUBBLE_PADDING)
        self.rows_top = BUBBLE_PADDING + self.title_height + BUBBLE_PADDING // 2
        height = self.rows_top + len(options) * OPTION_HEIGHT + BUBBLE_PADDING

        # Prefer sitting above the figurine; flip below when that leaves the screen
        screen_w, screen_h = screen.get_size()
        self.tail_up = sprite_rect.top - TAIL_HEIGHT - height < 0
        if self.tail_up:
            self.tip = sprite_rect.midbottom
            y = sprite_rect.bottom + TAIL_HEIGHT
        else:
            self.tip = sprite_rect.midtop
            y = sprite_rect.top - TAIL_HEIGHT - height
        x = max(0, min(self.tip[0] - width // 2, screen_w - width))
        y = max(0, min(y, screen_h - height))
        self.rect = pygame.Rect(x, y, width, height)

        # The tail stays clear of the rounded corners when the bubble is clamped at an edge
        half_tail = TAIL_WIDTH // 2
        self.tail_x = max(self.rect.left + BUBBLE_RADIUS + half_tail,
                          min(self.tip[0], self.rect.right - BUBBLE_RADIUS - half_tail))

        self.buttons: List[Tuple[pygame.Rect, str]] = []
        row_y = self.rect.y + self.rows_top
        for option in options:
            row = pygame.Rect(self.rect.x + BUBBLE_PADDING // 2, row_y, width - BUBBLE_PADDING, OPTION_HEIGHT)
            self.buttons.append((row, option))
            row_y += OPTION_HEIGHT

    def close(self) -> None:
        """Close the menu with the shared fade-out."""
        self.game_state.menu_fade_window = self
        self.game_state.menu_fade_timer = self.game_state.menu_fade_duration
        self.game_state.info_window = None
        self.game_state.active_house_menu = None

    def handle_click(self, pos: Tuple[int, int]) -> bool:
        """Run the clicked option, or close when clicked outside. Returns True if handled."""
        if not self.rect.collidepoint(pos):
            self.close()
            return True
        for rect, option in self.buttons:
            if rect.collidepoint(pos):
                if self.callback:
                    self.callback(option)
                else:
                    self.close()
                return True
        return True  # Clicks on the title or padding are absorbed

    def draw(self, alpha_scale: float = 1.0) -> None:
        """Draw the bubble.

        Args:
            alpha_scale: Transparency scale from 0.0 to 1.0.
        """
        if alpha_scale <= 0:
            return

        # Draw onto a surface covering bubble and tail, so fading is one set_alpha
        bounds = self.rect.union(pygame.Rect(self.tip[0], self.tip[1], 1, 1))
        surf = pygame.Surface(bounds.size, pygame.SRCALPHA)
        ox, oy = -bounds.x, -bounds.y
        body = self.rect.move(ox, oy)

        # Tail: an outer triangle in the border colour, then the body, then an
        # inner triangle in the fill colour that erases the border where they join
        tip = (self.tip[0] + ox, self.tip[1] + oy)
        tail_x = self.tail_x + ox
        base_y = body.top + BUBBLE_BORDER_WIDTH if self.tail_up else body.bottom - BUBBLE_BORDER_WIDTH - 1
        inset = BUBBLE_BORDER_WIDTH + 1
        pygame.draw.polygon(surf, BUBBLE_BORDER,
                            [(tail_x - TAIL_WIDTH // 2, base_y), tip, (tail_x + TAIL_WIDTH // 2, base_y)])
        pygame.draw.rect(surf, BUBBLE_BORDER, body, border_radius=BUBBLE_RADIUS)
        pygame.draw.rect(surf, BUBBLE_FILL, body.inflate(-2 * BUBBLE_BORDER_WIDTH, -2 * BUBBLE_BORDER_WIDTH),
                         border_radius=BUBBLE_RADIUS - BUBBLE_BORDER_WIDTH)
        inner_tip = (tip[0], tip[1] + inset if self.tail_up else tip[1] - inset)
        pygame.draw.polygon(surf, BUBBLE_FILL,
                            [(tail_x - TAIL_WIDTH // 2 + inset, base_y), inner_tip,
                             (tail_x + TAIL_WIDTH // 2 - inset, base_y)])

        # Title with a short rule underneath
        title_surf = self.title_font.render(self.title, True, DARK_BROWN)
        surf.blit(title_surf, title_surf.get_rect(
            center=(body.centerx, body.y + BUBBLE_PADDING + self.title_height // 2)))
        rule_y = body.y + self.rows_top - BUBBLE_PADDING // 4
        rule_half = title_surf.get_width() // 2 + 10
        pygame.draw.line(surf, BUBBLE_BORDER, (body.centerx - rule_half, rule_y),
                         (body.centerx + rule_half, rule_y), 1)

        # Options: plain text with a soft rounded highlight on hover
        mouse_pos = pygame.mouse.get_pos()
        for rect, text in self.buttons:
            row = rect.move(ox, oy)
            if alpha_scale >= 1.0 and rect.collidepoint(mouse_pos):
                pygame.draw.rect(surf, OPTION_HOVER_FILL, row, border_radius=OPTION_HEIGHT // 2)
            text_surf = self.option_font.render(text, True, BLACK)
            surf.blit(text_surf, text_surf.get_rect(center=row.center))

        if alpha_scale < 1.0:
            surf.set_alpha(int(255 * alpha_scale))
        self.screen.blit(surf, bounds.topleft)
