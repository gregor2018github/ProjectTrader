"""Being worn out (models/drowsiness.py): from 80 % of tiredness, the penalty, the view, the eyes falling
shut, and the minigames going worse."""

import datetime
import os
import random
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from src.models import drowsiness as d
from src.models.minigames import fishing
from src.models.minigames import woodhacking as wh
from src.models.minigames.fishing_pond import SPECIES, Fish
from src.models.player import Player
from src.models.statistics import Statistics

NOON = datetime.datetime(1500, 1, 8, 12)


def test_constants_the_tests_rely_on():
    assert d.TIRED_FROM == 0.8
    assert (d.PENALTY_MIN, d.PENALTY_MAX) == (0.05, 0.25)


@pytest.mark.parametrize("tiredness", [0.0, 0.5, 0.79])
def test_nothing_below_eighty_percent(tiredness):
    assert not d.is_tired(tiredness)
    assert d.penalty(tiredness) == 0.0
    assert d.Drowsiness().view(tiredness) is None


def test_penalty_rises_from_min_to_max():
    assert d.penalty(0.8) == pytest.approx(d.PENALTY_MIN)
    assert d.penalty(0.9) == pytest.approx((d.PENALTY_MIN + d.PENALTY_MAX) / 2)
    assert d.penalty(1.0) == pytest.approx(d.PENALTY_MAX)


def test_game_penalty_reads_the_player_and_spares_a_demo():
    assert d.game_penalty(SimpleNamespace(player=SimpleNamespace(tiredness=1.0))) == pytest.approx(d.PENALTY_MAX)
    assert d.game_penalty(SimpleNamespace()) == 0.0
    assert d.game_penalty(None) == 0.0


def test_the_view_narrows_the_more_tired():
    eyes = d.Drowsiness(random.Random(1))
    wide, narrow = eyes.view(0.8), eyes.view(1.0)
    assert wide == pytest.approx((d.VIEW_WIDE, d.VIEW_WIDE))
    assert narrow == pytest.approx((d.VIEW_NARROW, d.VIEW_NARROW))


def _run(eyes, seconds, tiredness, dt=1 / 60):
    stages = []
    for _ in range(round(seconds / dt)):
        eyes.update(dt, tiredness)
        stages.append((eyes.stage, eyes.lid))
    return stages


def test_the_eyes_fall_shut_now_and_then_and_open_again():
    eyes = d.Drowsiness(random.Random(3))
    stages = _run(eyes, 120, 1.0)
    shut = [lid for stage, lid in stages if stage == d.SHUT]
    assert shut and all(lid == pytest.approx(d.LID_SHUT) for lid in shut)
    assert stages[-1][0] in (d.OPEN, d.CLOSING, d.SHUT, d.OPENING)
    # Shut, the clear part is a slit: much lower than wide
    eyes.stage, eyes.stage_t = d.SHUT, 0.0
    width, height = eyes.view(1.0)
    assert height < width * 0.2


def test_more_tired_blinks_more_often():
    def blinks(tiredness):
        eyes = d.Drowsiness(random.Random(5))
        stages = _run(eyes, 600, tiredness)
        return sum(1 for (a, _), (b, _) in zip(stages, stages[1:]) if a == d.OPEN and b == d.CLOSING)
    assert blinks(1.0) > 2 * blinks(0.82) > 0


def test_resting_below_eighty_percent_opens_the_eyes():
    eyes = d.Drowsiness(random.Random(1))
    eyes.stage = d.SHUT
    eyes.update(0.1, 0.5)
    assert eyes.stage == d.OPEN and eyes.lid == 1.0


# ── Where it acts ────────────────────────────────────────────────────────────

def _worn_out_player():
    player = Player("P", 1.0)
    player.tiredness = 1.0
    return player


def test_worn_out_swings_earn_a_quarter_less(monkeypatch):
    pygame.init()
    monkeypatch.setattr(wh, "on_money_received", lambda *a, **k: None)
    stats = Statistics()
    stats.minigame_tips_seen = [wh.TIP_TUTORIAL, wh.TIP_DOUBLE_PERFECT]
    game = SimpleNamespace(depot=SimpleNamespace(stats=stats, book_labor_income=lambda *a: None),
                           state=SimpleNamespace(log_event=lambda *a: None, date=NOON),
                           sounds={}, play_sound=lambda name: None, player=_worn_out_player())
    minigame = wh.WoodhackingMinigame(pygame.Surface((10, 10)), game)
    assert minigame.tired == pytest.approx(d.PENALTY_MAX)
    while not minigame.scene.can_charge or not minigame.scene.log_ready:
        minigame.update(1 / 60)
    minigame.aim = 0.0
    minigame.power = (minigame.opt_lo + minigame.opt_hi) / 2
    minigame._resolve_swing()
    assert minigame.last_gain == pytest.approx(5 * 0.75)


def _fishing(player):
    pygame.init()
    screen = pygame.display.set_mode((1920, 1080))
    state = SimpleNamespace(date=datetime.datetime(1500, 1, 4, 10), coin_popups=[], screen=screen,
                            log_event=lambda *a: None)
    stats = Statistics()
    stats.minigame_tips_seen = [fishing.TIP_TUTORIAL_CAST, fishing.TIP_TUTORIAL_FIGHT]
    game = SimpleNamespace(state=state, sounds={}, weather=SimpleNamespace(), player=player,
                           depot=SimpleNamespace(stats=stats, book_labor_income=lambda *a: None))
    return fishing.FishingMinigame(screen, game, random.Random(1))


def test_worn_out_a_fish_holds_the_bait_shorter_and_the_bar_is_smaller():
    rested, tired = _fishing(Player("P", 1.0)), _fishing(_worn_out_player())
    assert rested.hook.hold_extra == 0.0
    assert tired.hook.hold_extra == pytest.approx(-d.PENALTY_MAX)
    bars = []
    for minigame in (rested, tired):
        fish = Fish(SPECIES["roach"], random.Random(2))
        minigame._start_fight(fish, 0.8, "GOOD STRIKE")
        bars.append(minigame.fight.bar_h)
    assert bars[1] == pytest.approx(bars[0] * (1 - d.PENALTY_MAX))
