import pygame
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING
from ...config.colors import *
from ..ui_utils import scale_9slice

if TYPE_CHECKING:
    from ...game import Game

_BOLD_MARK = "**"
_LINE_H = 30
_BOLD_PAD = 7   # extra pixels above AND below each bold line
_TOP_PAD = 45   # from window top to first text line
_BTN_FROM_BOTTOM = 55  # button top offset from window bottom


def _is_bold(line: str) -> bool:
    return line.startswith(_BOLD_MARK) and line.endswith(_BOLD_MARK) and len(line) > 4


def _display(line: str) -> str:
    return line[2:-2] if _is_bold(line) else line


# Semi-transparent black that dims the game behind the window, per screen size
_dim_overlays: Dict[Tuple[int, int], pygame.Surface] = {}


def _dim_overlay(size: Tuple[int, int]) -> pygame.Surface:
    overlay = _dim_overlays.get(size)
    if overlay is None:
        overlay = pygame.Surface(size)
        overlay.set_alpha(128)
        overlay.fill((0, 0, 0))
        _dim_overlays[size] = overlay
    return overlay


class InfoWindow:
    """A pop-up information window with customizable message and buttons.

    Lines in *message* wrapped in ``**...**`` are rendered bold with a small
    margin above and below them.
    """

    def __init__(self, screen: pygame.Surface, message: str, options: List[str],
                 font: pygame.font.Font, game: Optional['Game'] = None) -> None:
        self.screen: pygame.Surface = screen
        self.message: str = message
        self.options: List[str] = options
        self.font: pygame.font.Font = font
        self.game: Optional['Game'] = game

        lines = message.split('\n')

        # Render every line once here. Toggling bold on the shared game font
        # flushes its glyph cache, so doing it per frame slows down all text.
        self._line_surfs: List[Tuple[pygame.Surface, bool]] = []
        for line in lines:
            bold = _is_bold(line)
            if bold:
                self.font.bold = True
            self._line_surfs.append((self.font.render(_display(line), True, BLACK), bold))
            if bold:
                self.font.bold = False
        max_line_width = max((surf.get_width() for surf, _ in self._line_surfs), default=0)

        # Content height: normal lines take _LINE_H, bold lines take _LINE_H + 2*_BOLD_PAD
        content_h = sum(
            _LINE_H + 2 * _BOLD_PAD if _is_bold(l) else _LINE_H
            for l in lines
        )

        width: int = max(max_line_width + 80, len(options) * 120 + 40)
        btn_area = _BTN_FROM_BOTTOM + 10 if options else 20
        height: int = _TOP_PAD + content_h + btn_area

        screen_center = (screen.get_width() // 2, screen.get_height() // 2)
        self.window_rect: pygame.Rect = pygame.Rect(0, 0, width, height)
        self.window_rect.center = screen_center

        self.buttons: List[Tuple[pygame.Rect, str]] = []
        button_width: int = 100
        button_height: int = 30
        total_buttons_width: int = len(options) * button_width + (len(options) - 1) * 20
        start_x: int = self.window_rect.centerx - total_buttons_width // 2

        for i, option in enumerate(options):
            button_rect = pygame.Rect(
                start_x + i * (button_width + 20),
                self.window_rect.bottom - _BTN_FROM_BOTTOM,
                button_width, button_height
            )
            self.buttons.append((button_rect, option))

        # Keyboard selection: the first option starts pre-selected (highlighted
        # as if hovered). Tab / arrow keys move it, Enter confirms.
        self.selected_index: int = 0 if options else -1

        # 9-slice frame, built on the first draw
        self._frame_surf: Optional[pygame.Surface] = None

    def handle_key(self, event: pygame.event.Event) -> Optional[str]:
        """Process a KEYDOWN event for keyboard navigation.

        Returns the chosen option when the selection is confirmed, else None.
        """
        if event.type != pygame.KEYDOWN or not self.buttons:
            return None

        if event.key == pygame.K_TAB:
            step = -1 if event.mod & pygame.KMOD_SHIFT else 1
            self.selected_index = (self.selected_index + step) % len(self.buttons)
        elif event.key in (pygame.K_RIGHT, pygame.K_DOWN):
            self.selected_index = (self.selected_index + 1) % len(self.buttons)
        elif event.key in (pygame.K_LEFT, pygame.K_UP):
            self.selected_index = (self.selected_index - 1) % len(self.buttons)
        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            if 0 <= self.selected_index < len(self.buttons):
                return self.buttons[self.selected_index][1]
        return None

    def draw(self) -> None:
        self.screen.blit(_dim_overlay(self.screen.get_size()), (0, 0))

        if self._frame_surf is None:
            if hasattr(self, 'game') and self.game:
                game = self.game
            else:
                from ...game_state import GameState
                game = GameState().game  # type: ignore
            if hasattr(game, 'pic_info_window'):
                # The 9-slice scale is costly, and the window never resizes
                self._frame_surf = scale_9slice(game.pic_info_window, self.window_rect.size)

        if self._frame_surf is not None:
            self.screen.blit(self._frame_surf, self.window_rect)
        else:
            pygame.draw.rect(self.screen, LIGHT_GRAY, self.window_rect)
            pygame.draw.rect(self.screen, DARK_GRAY, self.window_rect, 2)

        y = self.window_rect.top + _TOP_PAD

        for text, bold in self._line_surfs:
            if bold:
                y += _BOLD_PAD
            text_rect = text.get_rect(center=(self.window_rect.centerx, y + _LINE_H // 2))
            self.screen.blit(text, text_rect)
            y += _LINE_H
            if bold:
                y += _BOLD_PAD

        mouse_pos = pygame.mouse.get_pos()
        # Hovering with the mouse moves the keyboard selection along, so both
        # input methods always agree on what is currently active.
        for i, (button_rect, _) in enumerate(self.buttons):
            if button_rect.collidepoint(mouse_pos):
                self.selected_index = i
                break

        for i, (button_rect, text) in enumerate(self.buttons):
            is_hovered = i == self.selected_index
            button_color = LIGHT_GRAY if is_hovered else WHITE
            text_color = WHITE if is_hovered else BLACK
            pygame.draw.rect(self.screen, button_color, button_rect)
            pygame.draw.rect(self.screen, DARK_GRAY, button_rect, 2)
            text_surface = self.font.render(text, True, text_color)
            text_rect = text_surface.get_rect(center=button_rect.center)
            self.screen.blit(text_surface, text_rect)

    def handle_click(self, pos: Tuple[int, int]) -> Optional[str]:
        for button_rect, option in self.buttons:
            if button_rect.collidepoint(pos):
                return option
        return None
