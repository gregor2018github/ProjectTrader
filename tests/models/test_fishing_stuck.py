"""When a hook sticks: only on a cast too deep, left to sink. Reeled in, it comes home whatever it passes."""

import datetime
import os
import random
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from src.models.minigames import fishing
from src.models.minigames.fishing import BANK_EDGE, FishingMinigame
from src.models.minigames.fishing_pond import WATER_Y, bottom_y
from src.models.statistics import Statistics

DT = 1 / 60
FAR_OUT = 200.0                 # deep water
TOO_DEEP = fishing.LEADER_RANGE[1]
SHALLOW_LINE = 14.0             # hangs free out there, and deeper than the water by the bank


def make(seed=1):
    pygame.init()
    screen = pygame.display.set_mode((1920, 1080))
    state = SimpleNamespace(date=datetime.datetime(1500, 1, 4, 10), coin_popups=[], screen=screen,
                            log_event=lambda *a: None)
    stats = Statistics()
    stats.minigame_tips_seen = [fishing.TIP_TUTORIAL_CAST, fishing.TIP_TUTORIAL_FIGHT]
    game = SimpleNamespace(state=state, sounds={}, weather=SimpleNamespace(),
                           depot=SimpleNamespace(stats=stats, book_labor_income=lambda *a: None))
    m = FishingMinigame(screen, game, random.Random(seed))
    m.pond.fish.clear()         # only the hook and the bottom here
    m.pond._respawn.clear()
    return m


def cast_to(m, x, leader):
    m.leader = leader
    m.hook_x = x
    m.cast_label, m.cast_mult, m.cast_colour = "GOOD CAST", 1.0, (255, 255, 255)
    m._land_cast()


def run(m, seconds):
    phases = set()
    for _ in range(round(seconds / DT)):
        m.update(DT)
        phases.add(m.phase)
    return phases


def hold(m):
    m.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(900, 500), button=1))


def let_go(m):
    m.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=(900, 500), button=1))


def test_a_cast_too_deep_left_to_sink_sticks_and_loses_its_worm():
    m = make()
    worms = m.worms
    cast_to(m, 110.0, TOO_DEEP)
    assert fishing.STUCK in run(m, 10)
    assert m.worms == worms - 1


def test_a_cast_that_hangs_free_does_not_stick():
    m = make()
    cast_to(m, FAR_OUT, SHALLOW_LINE)
    assert fishing.STUCK not in run(m, 10)


@pytest.mark.parametrize("seed", range(8))
@pytest.mark.parametrize("leader", (SHALLOW_LINE, 40.0, TOO_DEEP))
def test_reeling_all_the_way_in_never_sticks_and_keeps_the_worm(seed, leader):
    m = make(seed)
    worms = m.worms
    cast_to(m, FAR_OUT, leader)
    hold(m)
    phases = {fishing.WAIT}
    while m.phase == fishing.WAIT:
        m.update(DT)
        phases.add(m.phase)
    assert fishing.STUCK not in phases and m.phase == fishing.RETRIEVE
    assert m.worms == worms
    let_go(m)
    run(m, 3)
    assert m.phase == fishing.READY and m.baited and not m.hook_lost


def test_it_comes_in_over_the_bottom_not_through_it():
    m = make()
    cast_to(m, FAR_OUT, TOO_DEEP)
    hold(m)
    while m.phase == fishing.WAIT:
        m.update(DT)
        assert m.hook_y <= max(WATER_Y + 1, bottom_y(m.hook_x)) + 0.01


def test_stopping_in_the_shallows_lets_it_lie_on_the_bottom_unharmed():
    m = make()
    cast_to(m, FAR_OUT, 40.0)
    hold(m)
    while m.float_x > BANK_EDGE + 16:
        m.update(DT)
    let_go(m)
    assert WATER_Y + m.leader >= bottom_y(m.float_x)    # the line is longer than the water is deep here
    assert fishing.STUCK not in run(m, 6)
    assert m.phase == fishing.WAIT and m.baited
    assert m.hook_y == pytest.approx(bottom_y(m.hook_x) - 1, abs=1.0)


def test_a_cast_too_deep_reeled_before_it_touches_down_is_saved():
    m = make()
    cast_to(m, 110.0, TOO_DEEP)
    hold(m)
    run(m, 0.5)
    let_go(m)
    assert fishing.STUCK not in run(m, 6)


def test_the_next_cast_too_deep_sticks_again():
    m = make()
    cast_to(m, FAR_OUT, 40.0)
    hold(m)
    while m.phase == fishing.WAIT:
        m.update(DT)
    let_go(m)
    run(m, 3)
    assert m.phase == fishing.READY
    cast_to(m, 110.0, TOO_DEEP)
    assert fishing.STUCK in run(m, 10)
