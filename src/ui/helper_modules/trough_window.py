"""Looking into a trough of the chicken pen: what is in it, how full, how long it lasts, and filling it.

"Look In" in a trough's house menu opens it (open_trough_window): a parchment
sheet like the chicken's with the trough drawn large as it looks now, and
beside it what it holds, how full it is, how long that lasts the flock and how
much Wheat the player has; under them the buttons:

- "Pour in Water": fills it to the brim, free (it needs to be empty or hold water);
- "Fill with Grain": as many units of Wheat as it has room for, out of the stock
  (it needs to be empty or hold grain, and the Wheat);
- "Tip It Out": empties it, so it can take the other.

A greyed button says why underneath when hovered. The rules are
models/chicken_troughs.py's; "Refill" in the menu does the same as the button
for what it holds. Any click off the sheet, "Done" or Escape puts it away; it
closes by itself when the player walks off (map_view, like a house's menu).
"""

import os
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Tuple

import pygame

from ...config.constants import FONTS_PATH, SCREEN_HEIGHT, SCREEN_WIDTH, SIDEBAR_WIDTH
from ...models.chicken_troughs import (FEED, FEED_GOOD, WATER, contents_name, describe_fill,
                                       trough_title)
from ...models.minigames.tutorial_sheet import INK, RUBRIC, draw_divider, framed_sheet
from .charter_style import draw_button
from .loan_dialog import _close_dialog

if TYPE_CHECKING:
    from ...game_state import GameState
    from ...models.trough import Trough

SHEET_SIZE = (720, 440)
PICTURE_ZOOM = 4                # the trough's 64 x 32 picture drawn 4x, without smoothing
PAD = 46
TITLE_SIZE = 34
LABEL_SIZE = 21
TEXT_SIZE = 21
BUTTON_SIZE = 19
NOTE_SIZE = 18
LINE_GAP = 10
BUTTON_H = 40
BUTTON_GAP = 12
SHADOW = (0, 0, 0, 90)
WATER_SOUND = "splash"
GRAIN_SOUND = "sack_drop"


def _font(name: str, size: int) -> pygame.font.Font:
    try:
        return pygame.font.Font(os.path.join(FONTS_PATH, name), size)
    except Exception:
        return pygame.font.SysFont("times new roman", size)


def open_trough_window(game_state: 'GameState', trough: 'Trough') -> None:
    game_state.info_window = TroughWindow(game_state.screen, game_state, trough)


def _days(days: Optional[float]) -> str:
    if days is None:
        return "-"
    if days < 0.5:
        return "less than half a day"
    if days < 1.5:
        return "about a day"
    return f"about {round(days)} days"


# -- what the buttons and the menu's "Refill" do ----------------------------------

def pour_water(game_state: 'GameState', trough: 'Trough') -> Optional[str]:
    """Fill it with water; None if done, else why not."""
    game = game_state.game
    state = game.troughs[trough.name]
    if state.full:
        return "It is full to the brim."
    if not state.takes(WATER):
        return "There is grain in it. Tip it out first."
    game.troughs.pour_water(trough.name)
    game.show_troughs()
    _play(game, WATER_SOUND)
    return None


def fill_grain(game_state: 'GameState', trough: 'Trough') -> Optional[str]:
    """Fill it with as much Wheat as it has room for; None if done, else why not."""
    game = game_state.game
    state = game.troughs[trough.name]
    if state.full:
        return "It is full to the brim."
    if not state.takes(FEED):
        return "There is water in it. Tip it out first."
    units = game.troughs.grain_needed(trough.name)
    held = game.depot.good_stock.get(FEED_GOOD, 0)
    if held <= 0:
        return f"You have no {FEED_GOOD} to fill it with."
    units = min(units, held)
    if not game.depot.use_goods({FEED_GOOD: units}):
        return f"You have no {FEED_GOOD} to fill it with."
    game.troughs.add_grain(trough.name, units)
    game.show_troughs()
    _play(game, GRAIN_SOUND)
    return None


def tip_out(game_state: 'GameState', trough: 'Trough') -> Optional[str]:
    game = game_state.game
    if not game.troughs.tip_out(trough.name):
        return "It is empty already."
    game.show_troughs()
    _play(game, WATER_SOUND)
    return None


def refill(game_state: 'GameState', trough: 'Trough') -> None:
    """The menu's "Refill": more of what it holds, or a warning why not."""
    state = game_state.game.troughs[trough.name]
    why = pour_water(game_state, trough) if state.kind == WATER else fill_grain(game_state, trough)
    if why:
        game_state.show_warning(why)


def _play(game, family: str) -> None:
    sounds = getattr(game, "sounds", None) or {}
    takes = sorted(name for name in sounds if name.startswith(family))
    if takes and hasattr(game, "play_sound"):
        import random
        game.play_sound(random.choice(takes), 0.5)


class TroughWindow:
    """A trough's sheet, in the middle of the screen."""

    def __init__(self, screen: pygame.Surface, game_state: 'GameState', trough: 'Trough') -> None:
        self.screen = screen
        self.game_state = game_state
        self.trough = trough
        self.house = trough                 # map_view closes it when the player walks off
        self.title_font = _font("Medici Text.ttf", TITLE_SIZE)
        self.label_font = _font("Medici Text.ttf", LABEL_SIZE)
        self.text_font = _font("Augusta.ttf", TEXT_SIZE)
        self.button_font = _font("RomanAntique.ttf", BUTTON_SIZE)
        self.note_font = _font("RomanAntique.ttf", NOTE_SIZE)
        self.blank = framed_sheet(SHEET_SIZE)
        total_w = SCREEN_WIDTH + SIDEBAR_WIDTH
        self.panel = self.blank.get_rect(center=(total_w // 2, SCREEN_HEIGHT // 2))
        #: Local rects of the buttons drawn last, with what they do and why they cannot be pressed
        self._hot: Dict[str, Tuple[pygame.Rect, Callable[[], Optional[str]], Optional[str]]] = {}
        self.note: Optional[str] = None     # what the last press said, under the buttons

    # -- what it shows ------------------------------------------------------------

    def lines(self) -> List[Tuple[str, str]]:
        game = self.game_state.game
        state = game.troughs[self.trough.name]
        hens = len(game.flock.hens)
        lines = [("Holds", contents_name(state)), ("Fill", describe_fill(state))]
        if not state.empty:
            lasts = _days(game.troughs.days_left(self.trough.name, hens))
            if state.kind == WATER:
                lasts += ", longer when it rains"
            lines.append(("Lasts", f"{lasts} for the {hens} hens"))
        lines.append(("Your wheat", f"{game.depot.good_stock.get(FEED_GOOD, 0)} units"))
        return lines

    def buttons(self) -> List[Tuple[str, str, Callable[[], Optional[str]], Optional[str]]]:
        """(key, label, action, why it cannot be pressed or None) for each button."""
        game = self.game_state.game
        state = game.troughs[self.trough.name]
        name = self.trough.name
        units = game.troughs.grain_needed(name)
        held = game.depot.good_stock.get(FEED_GOOD, 0)

        def water_block() -> Optional[str]:
            if state.full:
                return "It is full to the brim."
            return None if state.takes(WATER) else "There is grain in it. Tip it out first."

        def grain_block() -> Optional[str]:
            if state.full:
                return "It is full to the brim."
            if not state.takes(FEED):
                return "There is water in it. Tip it out first."
            return None if held > 0 else f"You have no {FEED_GOOD}. It is sold at the market."

        grain_label = f"Fill with Grain ({min(units, held) or units} {FEED_GOOD})" if units else "Fill with Grain"
        return [
            ("water", "Pour in Water", lambda: pour_water(self.game_state, self.trough), water_block()),
            ("grain", grain_label, lambda: fill_grain(self.game_state, self.trough), grain_block()),
            ("tip", "Tip It Out", lambda: tip_out(self.game_state, self.trough),
             "It is empty already." if state.empty else None),
            ("done", "Done", lambda: _close_dialog(self.game_state), None),
        ]

    def button_rect(self, key: str) -> Optional[pygame.Rect]:
        """A button's rect on the screen, as last drawn (for the tests)."""
        entry = self._hot.get(key)
        return entry[0].move(self.panel.topleft) if entry else None

    # -- the event interface ------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            _close_dialog(self.game_state)

    def handle_click(self, pos: Tuple[int, int]) -> bool:
        if not self.panel.collidepoint(pos):
            _close_dialog(self.game_state)
            return True
        local = (pos[0] - self.panel.left, pos[1] - self.panel.top)
        if not self._hot:
            self._draw_sheet(local)
        for rect, action, blocked in self._hot.values():
            if rect.collidepoint(local):
                self.note = blocked or action()
                return True
        return True

    def _draw_sheet(self, mouse: Tuple[int, int]) -> pygame.Surface:
        page = self.blank.copy()
        sheet = page.get_rect()
        game = self.game_state.game
        state = game.troughs[self.trough.name]
        title = self.title_font.render(trough_title(state), True, INK)
        page.blit(title, title.get_rect(center=(sheet.centerx, PAD + 8)))
        draw_divider(page, (sheet.centerx, PAD + 38), 150)

        # The trough as it looks now, large, on a patch of trodden ground
        picture = self.trough.image
        big = pygame.transform.scale(picture, (picture.get_width() * PICTURE_ZOOM,
                                               picture.get_height() * PICTURE_ZOOM))
        box = pygame.Rect(PAD, PAD + 70, big.get_width(), big.get_height() + 20)
        ground = pygame.Rect(0, 0, box.width + 20, 34)
        ground.midbottom = (box.centerx, box.bottom)
        pygame.draw.ellipse(page, (150, 128, 90), ground)
        page.blit(big, big.get_rect(midbottom=(box.centerx, box.bottom - 6)))

        # What can be told of it
        x = box.right + 30
        rows = self.lines()
        label_w = max(self.label_font.size(label)[0] for label, _ in rows) + 16
        y = PAD + 74
        for label, words in rows:
            page.blit(self.label_font.render(label, True, RUBRIC), (x, y))
            page.blit(self.text_font.render(words, True, INK), (x + label_w, y))
            y += self.text_font.get_linesize() + LINE_GAP

        # The buttons, in a row along the bottom
        entries = self.buttons()
        widths = [max(120, self.button_font.size(label)[0] + 34) for _, label, _, _ in entries]
        total = sum(widths) + BUTTON_GAP * (len(widths) - 1)
        bx = sheet.centerx - total // 2
        by = sheet.bottom - PAD - BUTTON_H - 26
        self._hot = {}
        hovered_block = None
        for (key, label, action, blocked), width in zip(entries, widths):
            rect = pygame.Rect(bx, by, width, BUTTON_H)
            hovered = rect.collidepoint(mouse)
            draw_button(page, rect, label, self.button_font, hovered, blocked is None)
            self._hot[key] = (rect, action, blocked)
            if hovered and blocked:
                hovered_block = blocked
            bx += width + BUTTON_GAP
        note = hovered_block or self.note
        if note:
            words = self.note_font.render(note, True, RUBRIC)
            page.blit(words, words.get_rect(center=(sheet.centerx, by + BUTTON_H + 18)))
        return page

    def draw(self, alpha_scale: float = 1.0) -> None:
        if alpha_scale <= 0:
            return
        position = pygame.mouse.get_pos()
        page = self._draw_sheet((position[0] - self.panel.left, position[1] - self.panel.top))
        shadow = pygame.Surface(page.get_size(), pygame.SRCALPHA)
        shadow.fill(SHADOW)
        if alpha_scale < 1.0:
            alpha = round(255 * alpha_scale)
            page.set_alpha(alpha)
            shadow.fill((0, 0, 0, round(SHADOW[3] * alpha_scale)))
        self.screen.blit(shadow, self.panel.move(10, 12))
        self.screen.blit(page, self.panel)
