"""Escape in the fishing asks first: the game waits, and going back carries on where it stood."""

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
from src.models.minigames.fishing_pond import Fish, SPECIES
from src.models.statistics import Statistics

DT = 1 / 60


@pytest.fixture
def minigame():
    pygame.init()
    screen = pygame.display.set_mode((1920, 1080))
    state = SimpleNamespace(date=datetime.datetime(1500, 1, 4, 10), coin_popups=[], screen=screen,
                            log_event=lambda *a: None)
    depot = SimpleNamespace(stats=Statistics(), book_labor_income=lambda *a: None)
    game = SimpleNamespace(state=state, sounds={}, weather=SimpleNamespace(), depot=depot)
    return FishingMinigame(screen, game, random.Random(1))


def press(minigame, key):
    minigame.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key))


def click(minigame, rect):
    """A click on a rect of the canvas, press and release."""
    pos = (rect.centerx + minigame.canvas_rect.left, rect.centery + minigame.canvas_rect.top)
    minigame.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=1))
    minigame.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=pos, button=1))


def in_a_fight(minigame):
    fish = Fish(SPECIES["pike"], random.Random(1))
    fish.x, fish.y = 170.0, 90.0
    minigame.pond.fish.append(fish)
    minigame._start_fight(fish, 0.8, "GOOD STRIKE")
    return minigame.fight


def test_escape_asks_and_does_not_leave(minigame):
    press(minigame, pygame.K_ESCAPE)
    assert minigame.active and minigame.exit_asked


def test_escape_again_goes_back(minigame):
    press(minigame, pygame.K_ESCAPE)
    press(minigame, pygame.K_ESCAPE)
    assert minigame.active and not minigame.exit_asked


def test_enter_leaves_keeping_the_coins_and_counting_the_session(minigame):
    minigame.coins = 3.5
    press(minigame, pygame.K_ESCAPE)
    press(minigame, pygame.K_RETURN)
    assert not minigame.active
    assert minigame.coins == 3.5
    assert minigame.game.depot.stats.minigames_played == 1


def test_the_buttons_answer_and_a_click_beside_them_does_not(minigame):
    press(minigame, pygame.K_ESCAPE)
    minigame.draw()                         # lays the buttons out
    click(minigame, pygame.Rect(5, 5, 2, 2))
    assert minigame.exit_asked
    click(minigame, minigame.exit_back_rect)
    assert minigame.active and not minigame.exit_asked
    press(minigame, pygame.K_ESCAPE)
    minigame.draw()
    click(minigame, minigame.exit_yes_rect)
    assert not minigame.active


def test_the_fight_waits_for_the_answer(minigame):
    fight = in_a_fight(minigame)
    minigame.lmb = True
    press(minigame, pygame.K_ESCAPE)
    before = (fight.t, fight.bar_x, fight.stamina, fight.fish.x, minigame.t)
    for _ in range(120):
        minigame.update(DT)
    assert (fight.t, fight.bar_x, fight.stamina, fight.fish.x, minigame.t) == before
    assert minigame.phase == fishing.FIGHT


def test_the_box_draws_with_a_fish_on_the_line(minigame):
    in_a_fight(minigame)
    press(minigame, pygame.K_ESCAPE)
    minigame.draw()
    assert minigame.exit_asked


def test_going_back_lets_go_of_the_reel_and_puts_the_marker_over_the_mouse(minigame):
    fight = in_a_fight(minigame)
    minigame.lmb = True
    press(minigame, pygame.K_ESCAPE)
    assert not minigame.lmb
    minigame.draw()
    click(minigame, minigame.exit_back_rect)
    assert not minigame.lmb
    assert fight.bar_x == pytest.approx(min(1 - fishing.BAR_EDGE, max(fishing.BAR_EDGE, minigame.hand)))
    assert fight.tracking(minigame.hand) == 1.0


def test_a_cast_being_drawn_is_called_off(minigame):
    minigame.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(600, 400), button=1))
    assert minigame.phase == fishing.DRAW
    press(minigame, pygame.K_ESCAPE)
    assert minigame.phase == fishing.READY
    press(minigame, pygame.K_ESCAPE)
    minigame.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=(600, 400), button=1))
    assert minigame.phase == fishing.READY


def test_releasing_the_go_back_click_does_not_twitch_the_bait(minigame):
    minigame.phase = fishing.WAIT
    press(minigame, pygame.K_ESCAPE)
    minigame.draw()
    click(minigame, minigame.exit_back_rect)
    assert not minigame.twitches


def test_a_plain_click_still_twitches_the_bait(minigame):
    minigame.phase = fishing.WAIT
    minigame.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(600, 400), button=1))
    minigame.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=(600, 400), button=1))
    assert minigame.twitches


def test_escape_on_the_result_leaves_at_once(minigame):
    minigame._finish()
    press(minigame, pygame.K_ESCAPE)
    assert not minigame.active
