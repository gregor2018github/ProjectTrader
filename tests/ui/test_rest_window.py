"""The clock for resting: the hand at sunrise, moved by dragging, wheel and keys, and the rest itself."""

import datetime
import os
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from src.models.player import Player
from src.models.rest import Tiredness, default_end, first_step, latest_end
from src.ui.helper_modules.rest_window import RestWindow, describe_hours
from tests.fakes import FakeGameState

NOW = datetime.datetime(1500, 1, 8, 14, 7)


@pytest.fixture
def state():
    pygame.init()
    screen = pygame.display.set_mode((1920, 1080))
    game_state = FakeGameState(NOW)
    game_state.screen = screen
    player = Player("p", 0)
    player.tiredness = 0.6
    faded = []
    game_state.game = SimpleNamespace(player=player, tiredness=Tiredness(player, NOW),
                                      fade_in_from=faded.append, faded=faded)
    game_state.info_window = None
    game_state.active_house_menu = None
    game_state.menu_fade_duration = 0.2
    game_state.time_level = 3
    return game_state


@pytest.fixture
def window(state):
    state.info_window = RestWindow(state.screen, state)
    return state.info_window


def _press(window, key):
    window.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode=""))


def test_it_opens_at_sunrise_pauses_and_draws(window, state):
    assert window.end == default_end(NOW)
    assert state.time_level == 1
    window.draw()


def test_keys_move_the_hand_by_quarters_and_hours_within_its_limits(window):
    start = window.end
    _press(window, pygame.K_RIGHT)
    assert window.end == start + datetime.timedelta(minutes=15)
    _press(window, pygame.K_DOWN)
    assert window.end == start - datetime.timedelta(minutes=45)
    for _ in range(200):
        _press(window, pygame.K_UP)
    assert window.end == latest_end(NOW)
    for _ in range(200):
        _press(window, pygame.K_DOWN)
    assert window.end == first_step(NOW)


def test_clicking_the_ring_sets_the_hand_and_dragging_past_the_top_stops_at_the_longest(window):
    six_hours = window.point_at(6, 210)
    window.handle_click((round(six_hours[0]), round(six_hours[1])))
    assert window.dragging
    assert abs(window.hours_ahead - 6) < 0.3
    for hours in (12, 18, 23, 23.9, 0.3, 2):
        x, y = window.point_at(hours, 210)
        window.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=(round(x), round(y)), rel=(0, 0), buttons=(1, 0, 0)))
    assert window.end == latest_end(NOW)
    window.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=(0, 0), button=1))
    assert not window.dragging


def test_the_sunrise_button_puts_the_hand_back(window):
    _press(window, pygame.K_UP)
    window.handle_click(window.buttons["sunrise"].center)
    assert window.end == default_end(NOW)


def test_resting_moves_the_clock_and_brings_the_tiredness_down(window, state):
    _press(window, pygame.K_LEFT)     # not quite to sunrise
    end = window.end
    hours = (end - NOW).total_seconds() / 3600
    window.handle_click(window.buttons["rest"].center)
    assert state.date == end
    assert state.game.player.tiredness == pytest.approx(max(0.0, 0.6 - hours / 8))
    assert state.info_window is None
    assert state.time_level == 3
    assert len(state.game.faded) == 1
    assert state.events and state.events[0][0] == "SYSTEM"


def test_resting_lets_the_weather_go_on_for_the_time_rested(window, state):
    advanced = []
    state.game.weather = SimpleNamespace(advance=advanced.append)
    end = window.end
    window.handle_click(window.buttons["rest"].center)
    hours = (end - NOW).total_seconds() / 3600
    assert advanced == [pytest.approx(hours - 1)]   # the game's next update gives it the last hour


def test_cancel_leaves_the_clock_and_starts_the_game_again(window, state):
    window.handle_click(window.buttons["cancel"].center)
    assert state.date == NOW
    assert state.info_window is None and state.time_level == 3


def test_describe_hours():
    assert describe_hours(datetime.timedelta(hours=8, minutes=30)) == "8 h 30 min"
    assert describe_hours(datetime.timedelta(hours=1)) == "1 h"
    assert describe_hours(datetime.timedelta(minutes=45)) == "45 min"
