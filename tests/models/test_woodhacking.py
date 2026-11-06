"""The woodhacking minigame's chopping scene, and how the game waits for it."""

import math
import random
from types import SimpleNamespace

import pygame
import pytest

from src.models.minigames import woodhacking as wh
from src.models.minigames.woodhacking_scene import BITE, SHORT, SPLIT, WHIFF, ChoppingScene

DT = 1 / 60


@pytest.fixture(scope="module", autouse=True)
def fonts():
    pygame.font.init()
    yield


@pytest.fixture
def scene():
    return ChoppingScene(pygame.font.SysFont(None, 20), random.Random(0))


def run(scene, seconds):
    sounds = []
    for _ in range(round(seconds / DT)):
        sounds += scene.update(DT)
    return sounds


def swing(scene, outcome, power=0.6):
    scene.charge(power)
    run(scene, 0.3)
    return scene.swing(outcome, 3)


@pytest.mark.parametrize("points, power, expected", [
    (5, 0.6, SPLIT), (3, 0.6, SPLIT), (2, 0.6, BITE), (1, 0.3, BITE),
    (0, 0.1, SHORT), (0, 0.9, WHIFF),
])
def test_the_grade_decides_what_the_axe_does(points, power, expected):
    assert wh.swing_outcome(points, power, opt_lo=0.57) == expected


def test_a_split_chops_on_impact_and_stacks_the_log(scene):
    assert swing(scene, SPLIT) == []           # no swish for a blow that lands
    sounds = run(scene, 0.15)
    assert "chop" in sounds
    assert scene.pile == 1
    assert not scene.log_ready                 # the next log is on its way
    run(scene, 2.0)
    assert scene.log_ready and scene.settled


def test_a_miss_swishes_at_once_and_leaves_the_log(scene):
    assert swing(scene, WHIFF) == ["swoosh"]
    assert "chop" not in run(scene, 2.0)
    assert scene.pile == 0 and scene.log_damage == 0


def test_the_second_bite_splits_the_log(scene):
    swing(scene, BITE)
    run(scene, 2.0)
    assert scene.log_damage == 1 and scene.pile == 0
    swing(scene, BITE)
    run(scene, 2.0)
    assert scene.log_damage == 0 and scene.pile == 1


def test_no_new_swing_until_the_last_one_has_landed(scene):
    swing(scene, SPLIT)
    assert not scene.can_charge
    run(scene, 0.6)
    assert scene.can_charge


def test_the_blade_lands_on_the_log(scene):
    """The axe's length and strike angle are worked out so the blade meets the log's top."""
    from src.models.minigames import woodhacking_scene as ws
    swing(scene, SPLIT)
    while scene.state == "swing":
        scene.update(DT)
    head = scene._axe_head()
    assert abs(head.x - ws._BLOCK_CX) < ws._LOG_W / 2
    assert ws._LOG_TOP - 40 < head.y < ws._LOG_TOP


def test_the_scene_draws_every_moment(scene):
    for outcome in (SPLIT, BITE, WHIFF, SHORT):
        scene.charge(1.0)
        for _ in range(30):
            scene.update(DT)
            scene.draw()
        scene.swing(outcome, 2)
        for _ in range(90):
            scene.update(DT)
            scene.draw()


def _game():
    stats = SimpleNamespace(woodhacking_highscore=0, minigames_played=0, minigame_income_total=0.0)
    booked = []
    depot = SimpleNamespace(stats=stats, book_labor_income=lambda coins, name: booked.append(coins))
    game = SimpleNamespace(depot=depot, state=SimpleNamespace(log_event=lambda *a: None),
                           sounds={}, play_sound=lambda name: None)
    return game, booked


def test_the_result_waits_for_the_last_swing_to_settle(monkeypatch):
    monkeypatch.setattr(wh, "on_money_received", lambda *a, **k: None)
    game, booked = _game()
    minigame = wh.WoodhackingMinigame(pygame.Surface((10, 10)), game)
    down = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(0, 0))
    up = pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(0, 0))
    for _ in range(wh.MAX_SWINGS):
        while not minigame.scene.can_charge:
            minigame.update(DT)
        minigame.handle_event(down)
        for _ in range(50):
            minigame.update(DT)
        minigame.aim = 0.0                       # dead centre
        minigame.handle_event(up)
    assert minigame.attempt == wh.MAX_SWINGS
    assert not minigame.done                     # the last log is still flying
    minigame.handle_event(down)
    assert not minigame.charging                 # no 31st swing
    for _ in range(round(5 / DT)):
        minigame.update(DT)
        if minigame.done:
            break
    assert minigame.done
    assert game.depot.stats.minigames_played == 1
    assert len(booked) <= 1


# ── The streak ────────────────────────────────────────────────────────────────

@pytest.fixture
def minigame(monkeypatch):
    monkeypatch.setattr(wh, "on_money_received", lambda *a, **k: None)
    monkeypatch.setattr(wh, "STREAK_BONUS", 0.05)
    game, _ = _game()
    return wh.WoodhackingMinigame(pygame.Surface((10, 10)), game)


def _swing(minigame, perfect: bool):
    """One swing: dead centre and in the power's sweet spot (5 points, a split),
    or far too weak (nothing). Waits for the scene to take the next one."""
    while not minigame.scene.can_charge or not minigame.scene.log_ready:
        minigame.update(DT)
    minigame.aim = 0.0
    minigame.power = (minigame.opt_lo + minigame.opt_hi) / 2 if perfect else 0.01
    minigame._resolve_swing()
    for _ in range(round(1.5 / DT)):
        minigame.update(DT)


def test_each_split_in_a_row_adds_five_percent_to_the_next_swing(minigame):
    _swing(minigame, True)
    assert minigame.last_gain == 5 and minigame.streak == 1
    _swing(minigame, True)
    assert minigame.last_gain == pytest.approx(5.25) and minigame.streak == 2
    _swing(minigame, True)
    assert minigame.last_gain == pytest.approx(5.5) and minigame.streak == 3
    assert minigame.score == pytest.approx(15.75)


def test_a_swing_that_splits_nothing_ends_the_streak(minigame):
    for _ in range(3):
        _swing(minigame, True)
    _swing(minigame, False)
    assert minigame.streak == 0 and minigame.last_gain == 0
    _swing(minigame, True)
    assert minigame.last_gain == 5                # no bonus left
    assert minigame.best_streak == 3


def _fair_swing(minigame):
    """Fair aim (1 point) and power just under the sweet spot (1 point): the axe bites."""
    while not minigame.scene.can_charge or not minigame.scene.log_ready:
        minigame.update(DT)
    minigame.aim = math.radians(30)
    minigame.power = minigame.opt_lo - 0.05
    minigame._resolve_swing()
    for _ in range(round(1.5 / DT)):
        minigame.update(DT)


def test_a_bite_ends_the_streak_and_the_second_bite_splits_and_starts_one(minigame):
    _swing(minigame, True)
    _fair_swing(minigame)
    assert minigame.scene.log_damage == 1
    assert minigame.streak == 0
    assert minigame.last_gain == pytest.approx(2.1)   # the bite still had the split's 5%
    _fair_swing(minigame)                              # the cracked log splits
    assert minigame.scene.pile == 2
    assert minigame.streak == 1


def test_the_woodpile_has_room_for_a_split_from_every_swing():
    from src.models.minigames import woodhacking_scene as ws
    assert ws._PILE_ROWS * (ws._PILE_ROWS + 1) // 2 >= wh.MAX_SWINGS


# ── Perfect swings ────────────────────────────────────────────────────────────

def test_a_swing_perfect_on_both_gauges_rings_and_holds_still(scene):
    scene.charge(0.6)
    run(scene, 0.3)
    scene.swing(SPLIT, 5, flourish=2)
    sounds = []
    while scene.state == "swing":
        sounds += scene.update(DT)
    assert sounds == ["chop", "ring"]
    angle = scene.angle
    scene.update(DT)                           # the heartbeat: nothing moves
    assert scene.angle == angle and scene.motes
    run(scene, 3.0)
    assert scene.settled                       # the motes and the glow are gone again


def test_an_ordinary_split_does_not_ring(scene):
    swing(scene, SPLIT)
    assert "ring" not in run(scene, 2.0)
    assert not scene.motes


def test_each_perfect_gauge_glints(minigame):
    minigame.aim = 0.0                         # dead centre and the sweet spot's middle
    minigame.power = (minigame.opt_lo + minigame.opt_hi) / 2
    minigame._resolve_swing()
    assert sorted(g["kind"] for g in minigame.glints) == ["aim", "power"]
    assert minigame.scene.flourish == 2
    while not minigame.scene.can_charge or not minigame.scene.log_ready:
        minigame.update(DT)
    minigame.aim = 0.0
    minigame.power = minigame.opt_lo - 0.05    # aim perfect, power only good
    minigame._resolve_swing()
    assert [g["kind"] for g in minigame.glints] == ["aim"]
    assert minigame.scene.flourish == 0
    for _ in range(round(wh._GLINT_S / DT) + 1):
        minigame.update(DT)
    assert minigame.glints == []
