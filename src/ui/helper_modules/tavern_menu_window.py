"""A tavern's bill of fare for the day, opened from its house menu ("Daily Menu").

The dishes are drawn by `daily_menu()` when the window opens, 2 or 3 a day. Each
is a box with its name, its price at the right, a short description under it,
what it does for the player (models/meal_effects.py) and whether the player has
eaten it before, and whether it would replace another meal's effect; clicking one
orders it (`order_dish`): its price is paid, booked as cost of living, the dish
goes into `Statistics.dishes_tried` and its effect becomes the player's meal. A dish with a picture (`dish_picture_path`) is
then brought to the table, `DishServedWindow`, and any click goes back to the
bill of fare.
"""

import os
import pygame
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from .loan_dialog import _BaseDialog, _close_dialog, _load_fonts
from ..transaction_feedback import on_money_spent
from ...config.colors import BLACK, DARK_BROWN, DARK_GREEN, DARK_RED
from ...config.constants import FONTS_PATH, FOOD_CATEGORY, SCREEN_HEIGHT
from ...sim.calendar import format_long, is_fast_day, is_lent
from ...models.tavern_menu import Dish, daily_menu, dish_key, dish_picture_path
from ...models import meal_effects

if TYPE_CHECKING:
    from ...game_state import GameState
    from ...models.house import House

DESCRIPTION_COLOR = (90, 70, 50)
EFFECT_COLOR = (40, 96, 40)   # the line saying what a dish does for the player
DESCRIPTION_FONT_SIZE = 17
CARD_FILL = (236, 216, 178)
CARD_HOVER_FILL = (246, 230, 196)
CARD_MARGIN = 26        # between the panel's edge and the boxes
CARD_PAD = 10           # inside a box
CARD_GAP = 12           # between the boxes
PICTURE_MAX = (560, 420)  # the largest a served dish's picture is drawn

_pictures: Dict[str, Optional[pygame.Surface]] = {}


def open_tavern_menu(game_state: 'GameState', house: 'House') -> None:
    game_state.info_window = TavernMenuWindow(game_state.screen, game_state, house)


def _tavern_title(house: 'House') -> str:
    return house.display_name or "The Tavern"


def _small_font() -> pygame.font.Font:
    try:
        return pygame.font.Font(os.path.join(FONTS_PATH, "Augusta.ttf"), DESCRIPTION_FONT_SIZE)
    except Exception:
        return pygame.font.SysFont("arial", DESCRIPTION_FONT_SIZE - 2)


def _wrap(text: str, font: pygame.font.Font, width: int) -> List[str]:
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if line and font.size(trial)[0] > width:
            lines.append(line)
            line = word
        else:
            line = trial
    if line:
        lines.append(line)
    return lines


def dish_picture(dish: Dish) -> Optional[pygame.Surface]:
    """The dish's picture scaled to fit `PICTURE_MAX`, or None if it has none (read once)."""
    path = dish_picture_path(dish)
    if path not in _pictures:
        picture = None
        if os.path.exists(path):
            try:
                picture = pygame.image.load(path)
                scale = min(1.0, PICTURE_MAX[0] / picture.get_width(), PICTURE_MAX[1] / picture.get_height())
                size = (max(1, round(picture.get_width() * scale)), max(1, round(picture.get_height() * scale)))
                picture = pygame.transform.smoothscale(picture.convert_alpha(), size)
            except pygame.error as error:
                print(f"Warning: could not read the picture of {dish.name!r}: {error}")
                picture = None
        _pictures[path] = picture
    return _pictures[path]


def order_dish(game_state: 'GameState', dish: Dish) -> bool:
    """The player orders a dish: paid as cost of living and booked as tried. False if they cannot pay."""
    depot = game_state.game.depot
    if depot.money < dish.price:
        game_state.show_warning(f"You cannot pay the {dish.price:.2f} coins for the {dish.name}.")
        return False
    depot.book_cost_of_living(dish.price, FOOD_CATEGORY)
    on_money_spent(game_state, dish.price)
    first = depot.stats.record_dish(dish_key(dish))
    line = f"Ate {dish.name} for {dish.price:.2f}g" + (" (first time)" if first else "")
    # What it does for the next hours, in place of the last meal's (models/meal_effects.py)
    player = getattr(game_state.game, "player", None)
    if player is not None:
        line += f": {meal_effects.eat(player, dish, game_state.date).describe()}"
    game_state.log_event("FINANCE", line)
    return True


class TavernMenuWindow(_BaseDialog):
    W = 640

    def __init__(self, screen: pygame.Surface, game_state: 'GameState', house: 'House') -> None:
        self.house = house  # closes the menu when the player walks off (map_view)
        self.day = game_state.date.date()
        # The Tiled id would be steadier, but houses keep only their position
        key = f"{house.name}@{round(house.x)},{round(house.y)}"
        self.dishes: List[Dish] = [dish for _course, dishes in daily_menu(self.day, house.tavern_class, key)
                                   for dish in dishes]
        # The lines are measured before the panel's size is known
        self.title_font, self.body_font = _load_fonts()
        self.small_font = _small_font()
        self.header = self._header_lines()
        self.card_lines = [self._card_lines(dish) for dish in self.dishes]
        y = self.HDR + self.PAD + sum(s.get_height() for s, _ in self.header) + CARD_GAP
        self.card_tops: List[int] = []
        self.card_heights: List[int] = []
        for lines in self.card_lines:
            height = 2 * CARD_PAD + sum(s.get_height() for s in lines) + self.small_font.get_linesize()
            self.card_tops.append(y)
            self.card_heights.append(height)
            y += height + CARD_GAP
        self.hint = self.small_font.render(
            "Click a dish to order it." if self.dishes else "The kitchen is cold today.",
            True, DESCRIPTION_COLOR if self.dishes else BLACK)
        height = min(SCREEN_HEIGHT - 40, y + self.hint.get_height() + self.PAD + 6)
        super().__init__(screen, game_state, self.W, height)

    # -- layout ----------------------------------------------------------------

    def _header_lines(self) -> List[Tuple[pygame.Surface, int]]:
        """The lines over the boxes, each with the gap after it."""
        lines = [(self.body_font.render(f"Bill of fare for {format_long(self.day)}", True, DARK_BROWN), 2),
                 (self.small_font.render("All prices in coins", True, DESCRIPTION_COLOR), 2)]
        if is_fast_day(self.day):
            reason = "It is Lent" if is_lent(self.day) else "It is Friday"
            lines.append((self.small_font.render(f"{reason}, a fast day: no meat is served.", True, DARK_RED), 0))
        return [(surface, surface.get_height() + gap) for surface, gap in lines]

    def _card_lines(self, dish: Dish) -> List[pygame.Surface]:
        """The name and the description's lines of a dish's box (the price and the mark are drawn apart)."""
        width = self.W - 2 * CARD_MARGIN - 2 * CARD_PAD
        price_w = self.body_font.size(f"{dish.price:.2f}")[0] + 16
        lines = [self.body_font.render(part, True, BLACK) for part in _wrap(dish.name, self.body_font, width - price_w)]
        lines += [self.small_font.render(part, True, DESCRIPTION_COLOR)
                  for part in _wrap(dish.description, self.small_font, width)]
        effect = meal_effects.describe(meal_effects.effect_kind(dish), meal_effects.effect_strength(dish.price))
        lines.append(self.small_font.render(f"{effect}, {meal_effects.describe_hours(meal_effects.meal_hours(dish))}", True, EFFECT_COLOR))
        return lines

    def card_rect(self, index: int) -> pygame.Rect:
        return pygame.Rect(self.panel.left + CARD_MARGIN, self.panel.top + self.card_tops[index],
                           self.W - 2 * CARD_MARGIN, self.card_heights[index])

    def _dish_at(self, pos: Tuple[int, int]) -> Optional[Dish]:
        for index, dish in enumerate(self.dishes):
            if self.card_rect(index).collidepoint(pos):
                return dish
        return None

    # -- input -----------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            _close_dialog(self.game_state)

    def handle_click(self, pos: Tuple[int, int]) -> bool:
        if self.close_rect.collidepoint(pos) or not self.panel.collidepoint(pos):
            _close_dialog(self.game_state)
            return True
        dish = self._dish_at(pos)
        if dish is not None and order_dish(self.game_state, dish):
            picture = dish_picture(dish)
            if picture is not None:
                self.game_state.info_window = DishServedWindow(self.screen, self.game_state, self, dish, picture)
        return True

    # -- drawing ---------------------------------------------------------------

    def _replaced_mark(self, dish: Dish) -> Optional[pygame.Surface]:
        """"Replaces your Strong Hand (3h left)", when eating it would take the place of another meal's effect."""
        player = getattr(self.game_state.game, "player", None)
        meal = meal_effects.current_meal(player, self.game_state.date) if player is not None else None
        if meal is None or meal.dish == dish.name:
            return None
        name = meal_effects.EFFECTS[meal.kind]["name"]
        return self.small_font.render(f"Replaces your {name} ({meal.hours_left(self.game_state.date):.0f}h left)",
                                      True, DARK_RED)

    def _tried_mark(self, dish: Dish) -> pygame.Surface:
        times = self.game_state.game.depot.stats.dishes_tried.get(dish_key(dish), 0)
        if times == 0:
            return self.small_font.render("Not tried yet", True, DARK_GREEN)
        return self.small_font.render("Eaten once" if times == 1 else f"Eaten {times} times", True, DESCRIPTION_COLOR)

    def draw(self, alpha_scale: float = 1.0) -> None:
        if alpha_scale <= 0:
            return

        use_temp = alpha_scale < 1.0
        if use_temp:
            surf = pygame.Surface(self.panel.size, pygame.SRCALPHA)
            off = (-self.panel.left, -self.panel.top)
        else:
            surf = self.screen
            off = (0, 0)

        self._draw_panel(surf, off)
        self._draw_close_btn(surf, off)
        self._draw_title(surf, off, _tavern_title(self.house))

        p = self.panel.move(*off)
        y = p.top + self.HDR + self.PAD
        for surface, step in self.header:
            surf.blit(surface, surface.get_rect(centerx=p.centerx, top=y))
            y += step

        mouse_pos = pygame.mouse.get_pos() if not use_temp else (-1, -1)
        for index, dish in enumerate(self.dishes):
            screen_rect = self.card_rect(index)
            rect = screen_rect.move(*off)
            hovered = screen_rect.collidepoint(mouse_pos)
            pygame.draw.rect(surf, CARD_HOVER_FILL if hovered else CARD_FILL, rect, border_radius=6)
            pygame.draw.rect(surf, DARK_BROWN, rect, 2 if hovered else 1, border_radius=6)
            price = self.body_font.render(f"{dish.price:.2f}", True, DARK_BROWN)
            surf.blit(price, price.get_rect(right=rect.right - CARD_PAD, top=rect.top + CARD_PAD))
            line_y = rect.top + CARD_PAD
            for line in self.card_lines[index]:
                surf.blit(line, (rect.left + CARD_PAD, line_y))
                line_y += line.get_height()
            mark = self._tried_mark(dish)
            surf.blit(mark, mark.get_rect(right=rect.right - CARD_PAD, bottom=rect.bottom - CARD_PAD + 4))
            replaced = self._replaced_mark(dish)
            if replaced is not None:
                surf.blit(replaced, replaced.get_rect(left=rect.left + CARD_PAD, bottom=rect.bottom - CARD_PAD + 4))

        if self.dishes:
            y = self.card_tops[-1] + self.card_heights[-1] + CARD_GAP + p.top
        surf.blit(self.hint, self.hint.get_rect(centerx=p.centerx, top=y))

        if use_temp:
            surf.set_alpha(int(255 * alpha_scale))
            self.screen.blit(surf, self.panel.topleft)


class DishServedWindow(_BaseDialog):
    """The dish just ordered, brought to the table: its picture, name and description.

    Any click, or Escape, goes back to the window it was opened from: the tavern's bill of
    fare, or the guild's Gourmet Collection (`back_hint` says which).
    """

    W = PICTURE_MAX[0] + 2 * CARD_MARGIN

    def __init__(self, screen: pygame.Surface, game_state: 'GameState', menu: _BaseDialog,
                 dish: Dish, picture: pygame.Surface,
                 back_hint: str = "Click to go back to the bill of fare.") -> None:
        self.menu = menu
        self.house = getattr(menu, "house", None)  # closes it when the player walks off (map_view)
        self.dish = dish
        self.picture = picture
        self.title_font, self.body_font = _load_fonts()
        self.small_font = _small_font()
        self.lines = [self.small_font.render(part, True, DESCRIPTION_COLOR)
                      for part in _wrap(dish.description, self.small_font, self.W - 2 * CARD_MARGIN)]
        effect = meal_effects.describe(meal_effects.effect_kind(dish), meal_effects.effect_strength(dish.price))
        self.lines.append(self.small_font.render(f"{effect} for {meal_effects.describe_hours(meal_effects.meal_hours(dish))}", True, EFFECT_COLOR))
        self.lines.append(self.small_font.render(back_hint, True, DARK_BROWN))
        height = (self.HDR + self.PAD + picture.get_height() + CARD_GAP
                  + sum(line.get_height() for line in self.lines) + self.PAD + 6)
        super().__init__(screen, game_state, self.W, min(SCREEN_HEIGHT - 40, height))

    def _back(self) -> None:
        self.game_state.info_window = self.menu

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self._back()

    def handle_click(self, pos: Tuple[int, int]) -> bool:
        if not self.panel.collidepoint(pos):
            _close_dialog(self.game_state)
        else:
            self._back()
        return True

    def draw(self, alpha_scale: float = 1.0) -> None:
        if alpha_scale <= 0:
            return

        use_temp = alpha_scale < 1.0
        if use_temp:
            surf = pygame.Surface(self.panel.size, pygame.SRCALPHA)
            off = (-self.panel.left, -self.panel.top)
        else:
            surf = self.screen
            off = (0, 0)

        self._draw_panel(surf, off)
        self._draw_close_btn(surf, off)
        self._draw_title(surf, off, self.dish.name)

        p = self.panel.move(*off)
        frame = self.picture.get_rect(centerx=p.centerx, top=p.top + self.HDR + self.PAD)
        surf.blit(self.picture, frame)
        pygame.draw.rect(surf, DARK_BROWN, frame.inflate(4, 4), 2)
        y = frame.bottom + CARD_GAP
        for line in self.lines:
            surf.blit(line, line.get_rect(centerx=p.centerx, top=y))
            y += line.get_height()

        if use_temp:
            surf.set_alpha(int(255 * alpha_scale))
            self.screen.blit(surf, self.panel.topleft)
