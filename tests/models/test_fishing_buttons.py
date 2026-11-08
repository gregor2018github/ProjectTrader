"""The left button and Space do the same, all through the fishing: most tests run with both."""

import datetime
import os
import random
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from src.models.minigames import fishing
from src.models.minigames.fishing import FishingMinigame
from src.models.minigames.fishing_pond import APPROACH, Fish, FLEE, INSPECT, NIBBLE, SPECIES, TAKE
from src.models.statistics import Statistics

DT = 1 / 60
POS = (900, 500)


@pytest.fixture
def minigame():
    pygame.init()
    screen = pygame.display.set_mode((1920, 1080))
    state = SimpleNamespace(date=datetime.datetime(1500, 1, 4, 10), coin_popups=[], screen=screen,
                            log_event=lambda *a: None)
    stats = Statistics()
    stats.minigame_tips_seen = [fishing.TIP_TUTORIAL_CAST, fishing.TIP_TUTORIAL_FIGHT]
    game = SimpleNamespace(state=state, sounds={}, weather=SimpleNamespace(),
                           depot=SimpleNamespace(stats=stats, book_labor_income=lambda *a: None))
    return FishingMinigame(screen, game, random.Random(1))


def press(minigame, button):
    if button == "space":
        minigame.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE))
    else:
        minigame.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=POS, button=1))


def let_go(minigame, button):
    if button == "space":
        minigame.handle_event(pygame.event.Event(pygame.KEYUP, key=pygame.K_SPACE))
    else:
        minigame.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=POS, button=1))


def waiting_with(minigame, state=None):
    """The bait in the water, and a fish at it in that state."""
    minigame.phase = fishing.WAIT
    minigame.hook_x, minigame.hook_y = 194.0, 90.0
    minigame.float_x = 194.0
    if state is None:
        return None
    fish = Fish(SPECIES["roach"], random.Random(1))
    fish.x, fish.y, fish.state = 194.0, 90.0, state
    minigame.pond.fish.append(fish)
    minigame.hook.engaged = fish
    minigame.take_t = minigame.t
    return fish


both = pytest.mark.parametrize("button", ("mouse", "space"))


@both
def test_the_right_moment_strikes(minigame, button):
    fish = waiting_with(minigame, TAKE)
    press(minigame, button)
    assert minigame.phase == fishing.FIGHT and minigame.fight.fish is fish


@both
@pytest.mark.parametrize("state", (INSPECT, NIBBLE))
def test_too_early_scares_the_fish(minigame, button, state):
    fish = waiting_with(minigame, state)
    press(minigame, button)
    assert minigame.phase == fishing.WAIT and fish.state == FLEE
    assert fish.spooked > 0                 # it keeps off baits for a while
    assert minigame.hook.engaged is None
    assert any("Too early" in popup[0] for popup in minigame.popups)


def test_too_late_the_fish_and_the_worm_are_gone(minigame):
    fish = waiting_with(minigame, TAKE)
    worms = minigame.worms
    fish.timer = 0.0                    # its take window is over
    for _ in range(5):
        minigame.update(DT)
    assert minigame.worms == worms - 1 and not minigame.baited
    assert minigame.phase == fishing.RETRIEVE and minigame.hook.engaged is None and fish.state != TAKE


@both
def test_a_fish_still_on_its_way_is_not_scared_by_a_twitch(minigame, button):
    fish = waiting_with(minigame, APPROACH)
    press(minigame, button)
    let_go(minigame, button)
    assert fish.state == APPROACH and not minigame.popups and minigame.twitches


@both
def test_letting_go_after_a_strike_is_no_twitch(minigame, button):
    waiting_with(minigame, NIBBLE)
    press(minigame, button)
    let_go(minigame, button)
    assert not minigame.twitches


@both
def test_with_no_fish_at_the_bait_a_tap_twitches(minigame, button):
    waiting_with(minigame)
    press(minigame, button)
    assert not minigame.popups and minigame.strike_cool == 0.0
    let_go(minigame, button)
    assert minigame.twitches


@both
def test_holding_reels_and_is_no_twitch(minigame, button):
    waiting_with(minigame)
    x = minigame.hook_x
    press(minigame, button)
    for _ in range(40):
        minigame.update(DT)
    assert minigame.hook_x < x
    let_go(minigame, button)
    assert not minigame.twitches


@both
def test_holding_draws_a_cast_and_letting_go_ends_it(minigame, button):
    press(minigame, button)
    assert minigame.phase == fishing.DRAW
    let_go(minigame, button)
    assert minigame.phase == fishing.READY          # no whip: no cast


@both
def test_a_press_goes_on_from_the_card(minigame, button):
    minigame.phase = fishing.CARD
    minigame.card = {}
    press(minigame, button)
    assert minigame.phase == fishing.READY and not minigame.held


@both
def test_the_press_that_strikes_starts_raising_the_bar(minigame, button):
    waiting_with(minigame, TAKE)
    press(minigame, button)
    minigame.fight.grace = 0.0
    minigame.fight.bar_at, minigame.fight.bar_v = 0.5, 0.0
    for _ in range(10):
        minigame.update(DT)
    assert minigame.fight.bar_at > 0.5


def test_the_second_of_both_held_neither_presses_again_nor_lets_go(minigame):
    waiting_with(minigame)
    press(minigame, "mouse")
    press(minigame, "space")
    let_go(minigame, "mouse")
    assert minigame.held and not minigame.twitches
    let_go(minigame, "space")
    assert not minigame.held and len(minigame.twitches) == 1


def test_a_held_key_repeating_does_not_strike_again(minigame):
    waiting_with(minigame, NIBBLE)
    press(minigame, "space")
    minigame.popups.clear()
    press(minigame, "space")
    assert not minigame.popups
