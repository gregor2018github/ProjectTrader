"""Booking a room at an inn: the boxes, paying, and the rest clock held to the booking."""

import datetime
import os
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from src.models.player import Player
from src.models.rest import Tiredness, latest_end
from src.ui.helper_modules import room_booking_window
from src.ui.helper_modules.rest_window import RestWindow
from src.ui.helper_modules.room_booking_window import RoomBookingWindow
from tests.fakes import FakeGameState

NOW = datetime.datetime(1500, 1, 8, 14, 7)
INN = SimpleNamespace(name="House_28", tavern_class="high", display_name="The Golden Sheaf")


class FakeDepot:
    def __init__(self, money):
        self.money = money
        self.cost_of_living = 0.0

    def book_cost_of_living(self, amount, category="Base Cost"):
        self.category = category
        self.money -= amount
        self.cost_of_living += amount


@pytest.fixture
def state(monkeypatch):
    pygame.init()
    screen = pygame.display.set_mode((1920, 1080))
    monkeypatch.setattr(room_booking_window, "on_money_spent", lambda gs, amount: gs.money_feedback.append(("spent", amount)))
    game_state = FakeGameState(NOW)
    game_state.screen = screen
    player = Player("p", 0)
    game_state.game = SimpleNamespace(depot=FakeDepot(400.0), player=player, tiredness=Tiredness(player, NOW))
    game_state.info_window = None
    game_state.active_house_menu = None
    game_state.menu_fade_duration = 0.2
    game_state.time_level = 3
    return game_state


@pytest.fixture
def window(state):
    state.info_window = RoomBookingWindow(state.screen, state, INN)
    return state.info_window


def test_it_draws_without_a_room_and_rest_is_greyed(window, state):
    window.draw()
    assert not window.can_rest
    window.handle_click(window.rest_button.center)
    assert state.info_window is window


def test_a_click_on_a_stay_books_and_pays_for_it(window, state):
    window.handle_click(window.card_rect(0).center)
    assert state.game.depot.money == 350.0
    assert state.money_feedback == [("spent", 50)]
    assert state.game.depot.category == "Inn Rooms"
    assert window.until == NOW + datetime.timedelta(hours=24)
    window.handle_click(window.card_rect(1).center)
    assert state.game.depot.money == 50.0
    assert window.until == NOW + datetime.timedelta(hours=24, days=7)
    window.draw()


def test_without_the_money_nothing_is_booked(window, state):
    state.game.depot.money = 40.0
    window.handle_click(window.card_rect(0).center)
    assert window.until is None
    assert state.warnings


def test_rest_now_opens_the_clock_held_to_the_booking(window, state):
    window.handle_click(window.card_rect(0).center)
    state.date = NOW + datetime.timedelta(hours=10)
    window.handle_click(window.rest_button.center)
    clock = state.info_window
    assert isinstance(clock, RestWindow)
    assert clock.until == NOW + datetime.timedelta(hours=24)
    for _ in range(200):
        clock.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_UP, mod=0, unicode=""))
    assert clock.end == NOW + datetime.timedelta(hours=24)
    assert clock.end < latest_end(state.date)
    assert clock.hours_ahead == pytest.approx(14)
    clock.draw()
