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
    booked = []
    depot = SimpleNamespace(stats=Statistics(), booked=booked,
                            book_labor_income=lambda coins, name: booked.append(coins))
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


def land_a_fish(minigame):
    fish = Fish(SPECIES["roach"], random.Random(1))
    minigame.pond.fish.append(fish)
    minigame.landed = fish
    minigame.fight = SimpleNamespace(fish=fish)
    minigame._land_fish()
    return minigame.coins


def test_a_landed_fish_is_not_paid_until_the_session_is_finished(minigame):
    assert land_a_fish(minigame) > 0
    assert minigame.game.depot.booked == []


def test_exiting_early_pays_nothing_and_is_no_session_played(minigame):
    land_a_fish(minigame)
    press(minigame, pygame.K_ESCAPE)
    press(minigame, pygame.K_RETURN)
    assert not minigame.active
    stats = minigame.game.depot.stats
    assert minigame.game.depot.booked == []
    assert stats.minigame_income_total == 0
    assert stats.minigames_played == 0
    assert stats.fishing_highscore == 0


def test_a_finished_session_pays_once_all_it_earned(minigame):
    first = land_a_fish(minigame)
    second = land_a_fish(minigame) - first
    minigame._finish()
    minigame._finish()
    minigame._leave()
    stats = minigame.game.depot.stats
    assert minigame.game.depot.booked == [pytest.approx(first + second)]
    assert stats.minigame_income_total == pytest.approx(first + second)
    assert stats.minigames_played == 1
    assert stats.fishing_highscore == pytest.approx(first + second)


def test_escape_with_the_worms_used_up_asks_nothing_and_pays(minigame):
    coins = land_a_fish(minigame)
    minigame.worms = 0
    press(minigame, pygame.K_ESCAPE)
    assert not minigame.active and not minigame.exit_asked
    assert minigame.game.depot.booked == [pytest.approx(coins)]


def test_the_box_says_how_much_is_lost(minigame):
    assert fishing._EXIT_COINS_TEXT.format(3.5) == "You get no money: the 3.50 coins you earned are lost."
    land_a_fish(minigame)
    press(minigame, pygame.K_ESCAPE)
    minigame.draw()
    assert minigame.exit_asked


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
