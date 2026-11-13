"""Booking a room at an inn ("Book a Room" in a tavern's house menu; models/inn_rooms.py).

Two boxes, a night and a season, each with its price at the tavern's class, how
long it lasts and what that comes to a night; a click books it (`book`): the price
is paid, booked as cost of living, and the room held until the stay is over,
lengthened from its end when one is still held. Under them, how long the room is
the player's, and "Rest now", which opens the rest clock limited to that.
"""

import datetime
from typing import TYPE_CHECKING, List, Optional, Tuple

import pygame

from .loan_dialog import _BaseDialog, _close_dialog
from .tavern_menu_window import CARD_FILL, CARD_GAP, CARD_HOVER_FILL, CARD_MARGIN, CARD_PAD, DESCRIPTION_COLOR, _small_font
from ..transaction_feedback import on_money_spent
from ...config.colors import BLACK, DARK_BROWN, DARK_GREEN, DARK_RED, SANDY_BROWN
from ...models import inn_rooms
from ...models.rest import can_rest_until
from ...sim.calendar import format_date, format_long

if TYPE_CHECKING:
    from ...game_state import GameState
    from ...models.house import House

CARD_H = 74
BUTTON_W, BUTTON_H, BUTTON_GAP = 170, 36, 14


def open_room_booking(game_state: 'GameState', house: 'House') -> None:
    game_state.info_window = RoomBookingWindow(game_state.screen, game_state, house)


def book(game_state: 'GameState', house: 'House', stay: str) -> bool:
    """The player books a room here for the stay. False if they cannot pay."""
    price = inn_rooms.room_price(house.tavern_class, stay)
    depot = game_state.game.depot
    if depot.money < price:
        game_state.show_warning(f"You cannot pay the {price} coins for the room.")
        return False
    depot.book_cost_of_living(price)
    on_money_spent(game_state, price)
    until = inn_rooms.book_room(game_state.game.player, house, stay, game_state.date)
    game_state.log_event("FINANCE", f"Booked a room at {house.display_name or 'the inn'} "
                                    f"({inn_rooms.STAY_NAMES[stay].lower()}) for {price}g, "
                                    f"until {format_long(until)}, {until:%H:%M}")
    return True


def open_rest_in_room(game_state: 'GameState', house: 'House') -> bool:
    """The rest clock for the player's room here, limited to its booking; False if none is held."""
    until = inn_rooms.room_until(game_state.game.player, house, game_state.date)
    if until is None or not can_rest_until(game_state.date, until):
        game_state.show_warning("You have no room booked here. Book one first.")
        return False
    from .rest_window import open_rest_window
    game_state.active_house_menu = None
    open_rest_window(game_state, until)
    return True


class RoomBookingWindow(_BaseDialog):
    W = 560

    def __init__(self, screen: pygame.Surface, game_state: 'GameState', house: 'House') -> None:
        self.house = house  # closes the window when the player walks off (map_view)
        self.small_font = _small_font()
        self.card_top = self.HDR + self.PAD + 30
        status_top = self.card_top + len(inn_rooms.STAYS) * (CARD_H + CARD_GAP)
        height = status_top + 2 * 24 + BUTTON_H + 30
        super().__init__(screen, game_state, self.W, height)
        self.status_y = self.panel.top + status_top
        buttons_y = self.panel.bottom - BUTTON_H - 18
        left = self.panel.centerx - (2 * BUTTON_W + BUTTON_GAP) // 2
        self.rest_button = pygame.Rect(left, buttons_y, BUTTON_W, BUTTON_H)
        self.close_button = pygame.Rect(left + BUTTON_W + BUTTON_GAP, buttons_y, BUTTON_W, BUTTON_H)

    # -- layout ----------------------------------------------------------------

    def card_rect(self, index: int) -> pygame.Rect:
        return pygame.Rect(self.panel.left + CARD_MARGIN, self.panel.top + self.card_top + index * (CARD_H + CARD_GAP),
                           self.W - 2 * CARD_MARGIN, CARD_H)

    def _stay_at(self, pos: Tuple[int, int]) -> Optional[str]:
        for index, stay in enumerate(inn_rooms.STAYS):
            if self.card_rect(index).collidepoint(pos):
                return stay
        return None

    @property
    def until(self) -> Optional[datetime.datetime]:
        return inn_rooms.room_until(self.game_state.game.player, self.house, self.game_state.date)

    @property
    def can_rest(self) -> bool:
        until = self.until
        return until is not None and can_rest_until(self.game_state.date, until)

    # -- input -----------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            _close_dialog(self.game_state)

    def handle_click(self, pos: Tuple[int, int]) -> bool:
        if self.close_rect.collidepoint(pos) or self.close_button.collidepoint(pos) or not self.panel.collidepoint(pos):
            _close_dialog(self.game_state)
            return True
        if self.rest_button.collidepoint(pos):
            if self.can_rest:
                open_rest_in_room(self.game_state, self.house)
            return True
        stay = self._stay_at(pos)
        if stay is not None:
            book(self.game_state, self.house, stay)
        return True

    # -- drawing ---------------------------------------------------------------

    def _card_lines(self, stay: str) -> List[pygame.Surface]:
        tavern_class = self.house.tavern_class
        nights = inn_rooms.STAY_LENGTH[stay] / datetime.timedelta(hours=inn_rooms.NIGHT_HOURS)
        if stay == inn_rooms.NIGHT:
            detail = f"{inn_rooms.NIGHT_HOURS} hours from now"
        else:
            detail = (f"{nights:.0f} nights, {inn_rooms.price_per_night(tavern_class, stay):.2f} coins a night"
                      f" instead of {inn_rooms.room_price(tavern_class, inn_rooms.NIGHT)}")
        if self.until is not None:
            detail += ", added to your stay"
        return [self.body_font.render(inn_rooms.STAY_NAMES[stay], True, BLACK),
                self.small_font.render(detail, True, DESCRIPTION_COLOR)]

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
        self._draw_title(surf, off, f"A Room at {self.house.display_name or 'the Inn'}")
        p = self.panel.move(*off)
        intro = self.small_font.render("Rest here as long as the room is yours. Prices in coins.", True, DESCRIPTION_COLOR)
        surf.blit(intro, intro.get_rect(centerx=p.centerx, top=p.top + self.HDR + self.PAD))

        mouse_pos = pygame.mouse.get_pos() if not use_temp else (-1, -1)
        money = self.game_state.game.depot.money
        for index, stay in enumerate(inn_rooms.STAYS):
            screen_rect = self.card_rect(index)
            rect = screen_rect.move(*off)
            hovered = screen_rect.collidepoint(mouse_pos)
            pygame.draw.rect(surf, CARD_HOVER_FILL if hovered else CARD_FILL, rect, border_radius=6)
            pygame.draw.rect(surf, DARK_BROWN, rect, 2 if hovered else 1, border_radius=6)
            price = inn_rooms.room_price(self.house.tavern_class, stay)
            label = self.body_font.render(f"{price}", True, DARK_BROWN if money >= price else DARK_RED)
            surf.blit(label, label.get_rect(right=rect.right - CARD_PAD, centery=rect.centery))
            y = rect.top + CARD_PAD
            for line in self._card_lines(stay):
                surf.blit(line, (rect.left + CARD_PAD, y))
                y += line.get_height() + 2

        until = self.until
        if until is None:
            status = [self.small_font.render("You have no room here. Click a stay to book it.", True, BLACK)]
        else:
            left = until - self.game_state.date
            hours = left.total_seconds() / 3600.0
            span = f"{hours:.0f} hours" if hours < 48 else f"{hours / 24:.1f} days"
            status = [self.small_font.render(f"Your room is booked until {until:%H:%M}, {format_date(until)}",
                                             True, DARK_GREEN),
                      self.small_font.render(f"({span} left)", True, DESCRIPTION_COLOR)]
        y = self.status_y + off[1]
        for line in status:
            surf.blit(line, line.get_rect(centerx=p.centerx, top=y))
            y += 24

        self._draw_btn(surf, self.rest_button.move(*off), "Rest now", mouse_pos if self.can_rest else (-1, -1),
                       color=SANDY_BROWN if self.can_rest else (200, 190, 170))
        self._draw_btn(surf, self.close_button.move(*off), "Close", mouse_pos)

        if use_temp:
            surf.set_alpha(int(255 * alpha_scale))
            self.screen.blit(surf, self.panel.topleft)
