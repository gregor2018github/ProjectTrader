"""The clock for resting: the hand at sunrise, moved by dragging, wheel and keys, and the rest itself."""

import datetime
import os
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from src.ui.helper_modules import rest_window
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


def _turn_through(window):
    """Let the clock turn all the way, a frame at a time."""
    for _ in range(round((rest_window.DARKEN_SECONDS + rest_window.TURN_SECONDS_MAX
                          + rest_window.ARRIVED_SECONDS) * 60) + 2):
        window.animate(1 / 60)


def test_resting_moves_the_clock_and_brings_the_tiredness_down(window, state):
    _press(window, pygame.K_LEFT)     # not quite to sunrise
    end = window.end
    hours = (end - NOW).total_seconds() / 3600
    window.handle_click(window.buttons["rest"].center)
    _turn_through(window)
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
    _turn_through(window)
    hours = (end - NOW).total_seconds() / 3600
    assert advanced == [pytest.approx(hours - 1)]   # the game's next update gives it the last hour


def test_it_goes_dark_then_the_clock_turns_round_to_the_chosen_moment_then_the_rest_is_taken(window, state):
    hours = window.hours_ahead
    seconds = rest_window.turn_seconds(hours)
    window.handle_click(window.buttons["rest"].center)
    assert window.turning and state.info_window is window
    assert state.date == NOW and window.hours_turned == 0.0 and window.darkness == 0.0
    # The dark falls first; the hand waits for it
    frames = round(rest_window.DARKEN_SECONDS * 60)
    for _ in range(frames // 2):
        window.animate(1 / 60)
    assert 0 < window.darkness < 1 and window.hours_turned == 0.0
    window.draw()
    for _ in range(frames - frames // 2):
        window.animate(1 / 60)
    assert window.darkness == pytest.approx(1.0) and window.hours_turned == pytest.approx(0.0, abs=1e-6)
    turned = []
    for _ in range(round(seconds * 60) - 3):
        window.animate(1 / 60)
        turned.append(window.hours_turned)
        window.draw()
    assert turned == sorted(turned) and 0 < turned[len(turned) // 2] < hours   # on round, never back
    assert state.date == NOW and state.info_window is window                  # not there yet
    _turn_through(window)
    assert state.date == window.end and state.info_window is None
    # The game comes back from the window on black, not from plain black
    cover = state.game.faded[-1]
    assert cover.get_at((2, 2))[:3] == (0, 0, 0)
    assert cover.get_at(window.panel.center)[:3] != (0, 0, 0)


def test_the_hand_cannot_be_moved_once_it_turns(window):
    end = window.end
    window.handle_click(window.buttons["rest"].center)
    window.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=3))
    assert window.end == end


def test_a_click_or_a_key_while_it_turns_wakes_at_once_at_the_chosen_moment(window, state):
    end = window.end
    window.handle_click(window.buttons["rest"].center)
    window.animate(0.2)
    window.handle_click(window.buttons["cancel"].center)
    assert state.date == end and state.info_window is None and state.time_level == 3


class FakeChannel:
    def __init__(self, sound):
        self.sound, self.volume, self.faded = sound, None, []

    def set_volume(self, volume):
        self.volume = volume

    def get_sound(self):
        return self.sound

    def fadeout(self, ms):
        self.faded.append(ms)


class FakeSound:
    def __init__(self):
        self.plays = []
        self.channel = FakeChannel(self)

    def play(self, loops=0, fade_ms=0):
        self.plays.append((loops, fade_ms))
        return self.channel


def test_a_clock_ticks_while_it_turns_fading_in_with_the_dark_and_out_as_the_hand_arrives(window, state):
    clock = FakeSound()
    state.game.sounds = {rest_window.CLOCK_SOUND: clock}
    window.handle_click(window.buttons["rest"].center)
    assert clock.plays == [(-1, round(rest_window.DARKEN_SECONDS * 1000))]   # looped, fading in
    assert clock.channel.volume == rest_window.CLOCK_VOLUME
    turn_ends = rest_window.DARKEN_SECONDS + window.turn_s
    while window.turn_t + 1 / 60 < turn_ends - 0.02:
        window.animate(1 / 60)
    assert clock.channel.faded == []                                     # ticking all through the turn
    _turn_through(window)
    assert clock.channel.faded == [round(rest_window.CLOCK_FADE_OUT_S * 1000)]   # once, as it arrived


def test_waking_early_lets_the_ticking_go_quickly(window, state):
    clock = FakeSound()
    state.game.sounds = {rest_window.CLOCK_SOUND: clock}
    window.handle_click(window.buttons["rest"].center)
    window.animate(0.04)
    window.handle_click(window.buttons["rest"].center)
    assert clock.channel.faded == [round(rest_window.CLOCK_WAKE_FADE_S * 1000)]


def test_no_clock_sound_no_trouble(window, state):
    state.game.sounds = {}
    window.handle_click(window.buttons["rest"].center)
    _turn_through(window)
    assert state.info_window is None


def test_the_clock_recording_is_there():
    assert os.path.exists(os.path.join("assets", "sound", rest_window.CLOCK_SOUND + ".wav"))


def test_a_stutter_does_not_skip_the_dark_or_the_turn(window, state):
    window.handle_click(window.buttons["rest"].center)
    window.animate(3.0)                      # one very slow frame
    assert window.darkness < 0.5 and state.info_window is window


def test_a_longer_rest_turns_longer_but_a_short_one_slower_for_its_share_of_the_dial():
    assert rest_window.turn_seconds(0.25) == rest_window.TURN_SECONDS_MIN
    assert rest_window.turn_seconds(4) < rest_window.turn_seconds(12)
    assert rest_window.turn_seconds(24) == rest_window.TURN_SECONDS_MAX
    # Hours of the dial turned a second: far fewer for a short rest
    speed = lambda hours: hours / rest_window.turn_seconds(hours)
    assert speed(1) < speed(4) < speed(12)
    assert speed(1) < speed(12) / 4


def test_cancel_leaves_the_clock_and_starts_the_game_again(window, state):
    window.handle_click(window.buttons["cancel"].center)
    assert state.date == NOW
    assert state.info_window is None and state.time_level == 3


def test_describe_hours():
    assert describe_hours(datetime.timedelta(hours=8, minutes=30)) == "8 h 30 min"
    assert describe_hours(datetime.timedelta(hours=1)) == "1 h"
    assert describe_hours(datetime.timedelta(minutes=45)) == "45 min"
