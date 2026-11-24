"""Observing a chicken of the pen: its picture, large, and what can be told of it.

"Observe" in a chicken's menu opens it (open_chicken_window): a parchment sheet
like the guild's records' with the chicken as it looks now (its age's size and
paleness, its own look) drawn large without smoothing, and beside it its stage
of life, age, weight, build, colour with its rarity, head and tail
(models/chickens.py observation). Any click or Escape puts it away; it closes
by itself when the player walks off (map_view, like a house's menu).
"""

import os
from typing import TYPE_CHECKING, List, Tuple

import pygame

from ...config.constants import FONTS_PATH, SCREEN_HEIGHT, SCREEN_WIDTH, SIDEBAR_WIDTH
from ...models.chickens import ADULT_SIZE, observation
from ...models.minigames.tutorial_sheet import INK, RUBRIC, draw_divider, framed_sheet
from .loan_dialog import _close_dialog

if TYPE_CHECKING:
    from ...game_state import GameState
    from ...models.figurines.animals.chicken import Chicken

SHEET_SIZE = (680, 420)
PICTURE_BOX = (230, 230)        # the chicken drawn as large as fits, whole pixels each
PAD = 46
TITLE_SIZE = 34
LABEL_SIZE = 21
TEXT_SIZE = 21
HINT_SIZE = 18
LINE_GAP = 14
HINT = (236, 226, 204)
SHADOW = (0, 0, 0, 90)


def _font(name: str, size: int) -> pygame.font.Font:
    try:
        return pygame.font.Font(os.path.join(FONTS_PATH, name), size)
    except Exception:
        return pygame.font.SysFont("times new roman", size)


def open_chicken_window(game_state: 'GameState', chicken: 'Chicken') -> None:
    game_state.info_window = ChickenWindow(game_state.screen, game_state, chicken)
    game_state.active_house_menu = None


def _wrap(text: str, font: pygame.font.Font, width: int) -> List[str]:
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if line and font.size(trial)[0] > width:
            lines.append(line)
            line = word
        else:
            line = trial
    return lines + ([line] if line else [])


class ChickenWindow:
    """A chicken's sheet, in the middle of the screen."""

    def __init__(self, screen: pygame.Surface, game_state: 'GameState', chicken: 'Chicken') -> None:
        self.screen = screen
        self.game_state = game_state
        self.chicken = chicken
        now = game_state.date
        self.lines: List[Tuple[str, str]] = observation(chicken.hen, now)
        self.title = chicken.hen.stage(now)
        self.sheet = self._draw_sheet()
        total_w = SCREEN_WIDTH + SIDEBAR_WIDTH
        self.panel = self.sheet.get_rect(center=(total_w // 2, SCREEN_HEIGHT // 2))
        self.hint = self._make_hint("Click to look away.")

    def _draw_sheet(self) -> pygame.Surface:
        page = framed_sheet(SHEET_SIZE)
        sheet = page.get_rect()
        title_font = _font("Medici Text.ttf", TITLE_SIZE)
        title = title_font.render(self.title, True, INK)
        page.blit(title, title.get_rect(center=(sheet.centerx, PAD + 8)))
        draw_divider(page, (sheet.centerx, PAD + 38), 150)

        # The chicken as it looks now, standing, as large as fits in whole pixels
        # (the biggest a chicken grows filling the box, so a chick or a small hen is drawn smaller)
        frame = self.chicken.poses["left"]["stand"][0]
        fill = min(PICTURE_BOX[0] / frame.get_width(), PICTURE_BOX[1] / frame.get_height())
        zoom = max(1, int(fill * self.chicken.hen.size(self.game_state.date) / ADULT_SIZE[1]))
        self.picture_zoom = zoom
        picture = pygame.transform.scale(frame, (frame.get_width() * zoom, frame.get_height() * zoom))
        box = pygame.Rect(PAD, PAD + 60, *PICTURE_BOX)
        ground = pygame.Rect(0, 0, box.width - 30, 18)
        ground.midbottom = (box.centerx, box.bottom - 4)
        pygame.draw.ellipse(page, (150, 128, 90), ground)
        page.blit(picture, picture.get_rect(midbottom=(box.centerx, box.bottom - 10)))

        # What can be told of it
        label_font = _font("Medici Text.ttf", LABEL_SIZE)
        text_font = _font("Augusta.ttf", TEXT_SIZE)
        x = box.right + 34
        label_w = max(label_font.size(label)[0] for label, _ in self.lines) + 16
        width = sheet.right - PAD - x - label_w
        y = PAD + 66
        for label, words in self.lines:
            page.blit(label_font.render(label, True, RUBRIC), (x, y))
            for line in _wrap(words, text_font, width):
                page.blit(text_font.render(line, True, INK), (x + label_w, y))
                y += text_font.get_linesize()
            y += LINE_GAP
        return page

    @staticmethod
    def _make_hint(text: str) -> pygame.Surface:
        """Light words with a dark rim, readable over the map behind them."""
        font = _font("RomanAntique.ttf", HINT_SIZE)
        light, dark = font.render(text, True, HINT), font.render(text, True, (20, 18, 16))
        hint = pygame.Surface((light.get_width() + 4, light.get_height() + 4), pygame.SRCALPHA)
        for dx, dy in ((0, 2), (4, 2), (2, 0), (2, 4), (4, 4)):
            hint.blit(dark, (dx, dy))
        hint.blit(light, (2, 2))
        return hint

    # -- the event interface ------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            _close_dialog(self.game_state)

    def handle_click(self, pos: Tuple[int, int]) -> bool:
        _close_dialog(self.game_state)
        return True

    def draw(self, alpha_scale: float = 1.0) -> None:
        if alpha_scale <= 0:
            return
        sheet, hint = self.sheet, self.hint
        shadow = pygame.Surface(sheet.get_size(), pygame.SRCALPHA)
        shadow.fill(SHADOW)
        if alpha_scale < 1.0:
            alpha = round(255 * alpha_scale)
            sheet, hint, shadow = sheet.copy(), hint.copy(), shadow.copy()
            sheet.set_alpha(alpha)
            for surface in (hint, shadow):
                surface.fill((255, 255, 255, alpha), special_flags=pygame.BLEND_RGBA_MULT)
        self.screen.blit(shadow, self.panel.move(10, 12))
        self.screen.blit(sheet, self.panel)
        self.screen.blit(hint, hint.get_rect(centerx=self.panel.centerx, top=self.panel.bottom + 12))
