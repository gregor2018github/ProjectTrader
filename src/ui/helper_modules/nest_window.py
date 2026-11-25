"""Looking into the coop's nesting box: the eggs in it, how fast the hens lay, and what the keeper fetched.

"Look in the Nesting Box" in the coop's house menu opens it (open_nest_window):
a parchment sheet like the trough's with the eggs lying in the nest drawn in
straw, and beside it how many there are, how many the hens lay a day now (and
why fewer, an empty trough), when the keeper, Edric, fetched them last and how
many in all. The pen is not the player's, so there is nothing to take: only
"Done". Any click off the sheet, "Done" or Escape puts it away; it closes by
itself when the player walks off (map_view, like a house's menu). The rules are
models/chicken_eggs.py's.
"""

import os
from typing import TYPE_CHECKING, List, Optional, Tuple


import pygame

from ...config.constants import FONTS_PATH, SCREEN_HEIGHT, SCREEN_WIDTH, SIDEBAR_WIDTH
from ...models.chicken_eggs import NEST_CAP
from ...models.chicken_troughs import FEED, WATER
from ...models.minigames.tutorial_sheet import INK, RUBRIC, draw_divider, framed_sheet
from .charter_style import draw_button
from .loan_dialog import _close_dialog

if TYPE_CHECKING:
    from ...game_state import GameState

OPTION = "Look in the Nesting Box"
SHEET_SIZE = (720, 430)
PAD = 46
TITLE_SIZE = 34
LABEL_SIZE = 21
TEXT_SIZE = 21
BUTTON_SIZE = 19
NOTE_SIZE = 18
LINE_GAP = 10
BUTTON_H = 40
#: The nest drawn on the sheet: its size, and how many eggs it shows at the most
NEST_BOX = (230, 150)
EGGS_SHOWN = 12
STRAW = ((214, 176, 72), (240, 212, 112), (170, 132, 50))
NEST_WOOD = ((118, 76, 36), (86, 54, 26))
SHADOW = (0, 0, 0, 90)


def _font(name: str, size: int) -> pygame.font.Font:
    try:
        return pygame.font.Font(os.path.join(FONTS_PATH, name), size)
    except Exception:
        return pygame.font.SysFont("times new roman", size)


def is_nest_coop(game_state: 'GameState', house) -> bool:
    """Whether `house` is the coop whose nesting box the hens lay into."""
    game = getattr(game_state, "game", None)
    coop = getattr(getattr(getattr(game, "game_map", None), "tmx_map", None), "chicken_coop", None)
    return (coop is not None and coop.nest is not None and getattr(game, "nest", None) is not None
            and house.name == coop.name)


def open_nest_window(game_state: 'GameState', house) -> None:
    game_state.info_window = NestWindow(game_state.screen, game_state, house)


def _eggs_word(n: int) -> str:
    return "no eggs" if n == 0 else "one egg" if n == 1 else f"{n} eggs"


def _keeper_name(game) -> str:
    keeper = getattr(getattr(getattr(game, "game_map", None), "tmx_map", None), "pen_keeper", None)
    return keeper.name if keeper is not None else "The keeper"


class NestWindow:
    """The nesting box's sheet, in the middle of the screen."""

    def __init__(self, screen: pygame.Surface, game_state: 'GameState', house) -> None:
        self.screen = screen
        self.game_state = game_state
        self.house = house                  # map_view closes it when the player walks off
        self.title_font = _font("Medici Text.ttf", TITLE_SIZE)
        self.label_font = _font("Medici Text.ttf", LABEL_SIZE)
        self.text_font = _font("Augusta.ttf", TEXT_SIZE)
        self.button_font = _font("RomanAntique.ttf", BUTTON_SIZE)
        self.note_font = _font("RomanAntique.ttf", NOTE_SIZE)
        self.blank = framed_sheet(SHEET_SIZE)
        total_w = SCREEN_WIDTH + SIDEBAR_WIDTH
        self.panel = self.blank.get_rect(center=(total_w // 2, SCREEN_HEIGHT // 2))
        self._done: Optional[pygame.Rect] = None

    # -- what it shows ------------------------------------------------------------

    def lines(self) -> List[Tuple[str, str]]:
        game = self.game_state.game
        nest = game.nest
        keeper = _keeper_name(game)
        lines = [("In the nest", _eggs_word(nest.whole).capitalize()),
                 ("Laid a day", f"about {nest.rate:.1f}" if nest.rate >= 0.05 else "hardly any")]
        if nest.collected_on is None:
            lines.append(("Fetched", f"{keeper} has not been yet"))
        else:
            today = self.game_state.date.date() if self.game_state.date else None
            when = "today" if nest.collected_on == today else "on an earlier day"
            lines.append(("Fetched", f"{_eggs_word(nest.last_collected)} by {keeper}, {when}"))
        lines.append(("In all", f"{_eggs_word(nest.collected_total)}, sold at the market"))
        return lines

    def note(self) -> str:
        """Why they lay less, or how the keeper goes about it."""
        troughs = getattr(self.game_state.game, "troughs", None)
        missing = []
        if troughs is not None and not troughs.holds(FEED):
            missing.append("grain")
        if troughs is not None and not troughs.holds(WATER):
            missing.append("water")
        if missing:
            return f"No {' or '.join(missing)} in the troughs: the hens lay far fewer."
        if self.game_state.game.nest.whole >= NEST_CAP:
            return "The nest is full: what more is laid gets broken."
        return f"{_keeper_name(self.game_state.game)} fetches the eggs once a day, in the morning."

    # -- the event interface ------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            _close_dialog(self.game_state)

    def handle_click(self, pos: Tuple[int, int]) -> bool:
        if not self.panel.collidepoint(pos):
            _close_dialog(self.game_state)
            return True
        local = (pos[0] - self.panel.left, pos[1] - self.panel.top)
        if self._done is None:
            self._draw_sheet(local)
        if self._done.collidepoint(local):
            _close_dialog(self.game_state)
        return True

    def button_rect(self) -> Optional[pygame.Rect]:
        """"Done" on the screen, as last drawn (for the tests)."""
        return self._done.move(self.panel.topleft) if self._done else None

    # -- drawing ----------------------------------------------------------------

    def _draw_nest(self, page: pygame.Surface, box: pygame.Rect, eggs: int) -> None:
        """A wooden box of straw with the eggs in it, as many as lie there (up to EGGS_SHOWN)."""
        wood, dark = NEST_WOOD
        pygame.draw.rect(page, dark, box.inflate(10, 10), border_radius=6)
        pygame.draw.rect(page, wood, box, border_radius=4)
        straw = box.inflate(-18, -18)
        pygame.draw.ellipse(page, STRAW[2], straw)
        pygame.draw.ellipse(page, STRAW[0], straw.inflate(-8, -8))
        for i in range(60):                                     # stalks, the same every time
            x = straw.left + 10 + (i * 37) % (straw.width - 20)
            y = straw.top + 10 + (i * 53) % (straw.height - 20)
            pygame.draw.line(page, STRAW[1] if i % 2 else STRAW[2], (x, y), (x + 8 - (i % 5) * 4, y + 3), 2)
        shown = min(eggs, EGGS_SHOWN)
        cols = 4
        for i in range(shown):
            row, col = divmod(i, cols)
            cx = straw.left + 32 + col * (straw.width - 64) // (cols - 1) + (12 if row % 2 else 0)
            cy = straw.top + 30 + row * 30
            egg = pygame.Rect(0, 0, 26, 34)
            egg.center = (cx, cy)
            shell = (236, 222, 192) if i % 3 == 0 else (204, 148, 96) if i % 3 == 1 else (220, 176, 128)
            pygame.draw.ellipse(page, (24, 18, 14), egg.inflate(4, 4))
            pygame.draw.ellipse(page, shell, egg)
            pygame.draw.ellipse(page, (255, 250, 238), pygame.Rect(egg.left + 5, egg.top + 6, 7, 10))

    def _draw_sheet(self, mouse: Tuple[int, int]) -> pygame.Surface:
        page = self.blank.copy()
        sheet = page.get_rect()
        nest = self.game_state.game.nest
        title = self.title_font.render("The Nesting Box", True, INK)
        page.blit(title, title.get_rect(center=(sheet.centerx, PAD + 8)))
        draw_divider(page, (sheet.centerx, PAD + 38), 150)

        box = pygame.Rect(PAD + 6, PAD + 76, *NEST_BOX)
        self._draw_nest(page, box, nest.whole)

        x = box.right + 34
        rows = self.lines()
        label_w = max(self.label_font.size(label)[0] for label, _ in rows) + 16
        y = PAD + 76
        for label, words in rows:
            page.blit(self.label_font.render(label, True, RUBRIC), (x, y))
            page.blit(self.text_font.render(words, True, INK), (x + label_w, y))
            y += self.text_font.get_linesize() + LINE_GAP

        note = self.note_font.render(self.note(), True, RUBRIC)
        page.blit(note, note.get_rect(center=(sheet.centerx, sheet.bottom - PAD - BUTTON_H - 46)))
        self._done = pygame.Rect(0, 0, 140, BUTTON_H)
        self._done.midbottom = (sheet.centerx, sheet.bottom - PAD - 14)
        draw_button(page, self._done, "Done", self.button_font, self._done.collidepoint(mouse), True)
        return page

    def draw(self, alpha_scale: float = 1.0) -> None:
        if alpha_scale <= 0:
            return
        position = pygame.mouse.get_pos()
        page = self._draw_sheet((position[0] - self.panel.left, position[1] - self.panel.top))
        shadow = pygame.Surface(page.get_size(), pygame.SRCALPHA)
        shadow.fill(SHADOW)
        if alpha_scale < 1.0:
            page.set_alpha(round(255 * alpha_scale))
            shadow.fill((0, 0, 0, round(SHADOW[3] * alpha_scale)))
        self.screen.blit(shadow, self.panel.move(10, 12))
        self.screen.blit(page, self.panel)
