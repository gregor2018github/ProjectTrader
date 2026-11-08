"""What a fish bites on: most on a calm bait, the predators on a moving one, reeled in most of all."""

import datetime
import os
import random
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from src.models.minigames import fishing, fishing_pond
from src.models.minigames.fishing import FishingMinigame
from src.models.minigames.fishing_pond import (
    APPROACH, FLEE, Fish, Hook, INSPECT, NIBBLE, SPECIES, TAKE, WANDER, WATER_Y,
)
from src.models.statistics import Statistics

DT = 1 / 60
CALM_KINDS = ("roach", "rudd", "tench", "bream", "carp", "eel", "golden_carp", "minnow")
PREDATORS = ("perch", "pike")
BAIT = (200.0, 90.0)


def fish_by_the_bait(key, state=WANDER, off=6.0):
    fish = Fish(SPECIES[key], random.Random(1))
    fish.x, fish.y = BAIT[0] + off, BAIT[1]
    fish.state = state
    return fish


def bait(**kinds):
    return Hook(x=BAIT[0], y=BAIT[1], alluring=True, **kinds)


CALM = dict(twitch_age=99.0)
TWITCHED = dict(twitch_age=0.5)
REELED = dict(twitch_age=99.0, reeling=True)


def keenness(key, **kinds):
    return fish_by_the_bait(key)._notice_odds(bait(**kinds))[1]


def comes(key, seconds=60.0, **kinds):
    """How many of 200 goes it notices within a moment by the bait."""
    rng = random.Random(3)
    fish, hook = fish_by_the_bait(key), bait(**kinds)
    return sum(fish._notices(hook, seconds * DT, 1.0, rng) for _ in range(200))


@pytest.mark.parametrize("key", CALM_KINDS)
class TestTheCalmLovers:
    def test_they_are_no_predators(self, key):
        assert not fish_by_the_bait(key).predator

    def test_they_come_to_a_calm_bait(self, key):
        assert comes(key, **CALM) > 0

    def test_a_twitched_or_reeled_bait_does_not_draw_them(self, key):
        assert comes(key, **TWITCHED) == 0
        assert comes(key, **REELED) == 0


@pytest.mark.parametrize("key", PREDATORS)
class TestThePredators:
    def test_they_are_predators(self, key):
        assert fish_by_the_bait(key).predator

    def test_a_reeled_bait_draws_them_most_then_a_twitched_one_then_a_calm_one(self, key):
        assert keenness(key, **REELED) > keenness(key, **TWITCHED) > keenness(key, **CALM)
        assert keenness(key, **REELED) > 3 * keenness(key, **CALM)

    def test_they_still_may_look_at_a_calm_bait(self, key):
        assert comes(key, **CALM) > 0

    def test_they_notice_a_moving_bait_from_farther_off(self, key):
        fish = fish_by_the_bait(key)
        assert fish._notice_odds(bait(**REELED))[0] > fish._notice_odds(bait(**CALM))[0]


def test_a_pike_goes_for_a_moving_bait_more_than_a_perch():
    assert keenness("pike", **REELED) > keenness("perch", **REELED)


def test_the_predators_are_less_keen_on_a_calm_bait_than_the_others():
    assert keenness("pike", **CALM) < keenness("roach", **CALM)


class TestOnItsWay:
    def test_a_twitch_turns_a_calm_lover_away(self):
        fish, hook = fish_by_the_bait("roach", APPROACH), bait(twitch_age=DT)
        hook.engaged = fish
        fish.update(DT, hook, random.Random(1))
        assert fish.state == WANDER and hook.engaged is None

    def test_reeling_scares_a_calm_lover_off(self):
        for state in (APPROACH, INSPECT, NIBBLE):
            fish, hook = fish_by_the_bait("bream", state), bait(**REELED)
            hook.engaged = fish
            fish.timer, fish.sub = 1.0, "pause"
            fish.update(DT, hook, random.Random(1))
            assert fish.state == FLEE

    def test_a_twitch_does_not_turn_a_predator_away(self):
        fish, hook = fish_by_the_bait("pike", APPROACH, off=40.0), bait(twitch_age=DT)
        hook.engaged = fish
        fish.update(DT, hook, random.Random(1))
        assert fish.state == APPROACH

    def test_a_predator_catches_up_with_a_reeled_bait_and_takes_it_at_once(self):
        fish, hook = fish_by_the_bait("perch", APPROACH, off=30.0), bait(**REELED)
        hook.engaged = fish
        rng = random.Random(1)
        events = []
        for _ in range(60 * 10):
            hook.x -= fishing.REEL_IDLE_SPEED * DT
            events += fish.update(DT, hook, rng)
            if fish.state == TAKE:
                break
        assert fish.state == TAKE and any(ev[0] == "take" for ev in events)

    @pytest.mark.parametrize("state", (INSPECT, NIBBLE))
    def test_a_predator_at_the_bait_takes_it_when_it_starts_to_move(self, state):
        fish, hook = fish_by_the_bait("perch", state), bait(**REELED)
        hook.engaged = fish
        fish.timer, fish.sub = 1.0, "pause"
        fish.update(DT, hook, random.Random(1))
        assert fish.state == TAKE

    def test_it_holds_on_longer_to_a_reeled_bait(self):
        fish, hook = fish_by_the_bait("pike", INSPECT), bait(**REELED)
        fish.update(DT, hook, random.Random(1))
        assert fish.timer == pytest.approx(SPECIES["pike"].take_window * fishing_pond.REEL_TAKE_STRETCH)
        calm = fish_by_the_bait("pike")
        calm._take(bait(**CALM), [])
        assert calm.timer == pytest.approx(SPECIES["pike"].take_window)


class TestInTheGame:
    @pytest.fixture
    def minigame(self):
        pygame.init()
        screen = pygame.display.set_mode((1920, 1080))
        state = SimpleNamespace(date=datetime.datetime(1500, 1, 4, 10), coin_popups=[], screen=screen,
                                log_event=lambda *a: None)
        stats = Statistics()
        stats.minigame_tips_seen = [fishing.TIP_TUTORIAL_CAST, fishing.TIP_TUTORIAL_FIGHT]
        game = SimpleNamespace(state=state, sounds={}, weather=SimpleNamespace(),
                               depot=SimpleNamespace(stats=stats, book_labor_income=lambda *a: None))
        m = FishingMinigame(screen, game, random.Random(1))
        m.pond.fish.clear()
        m.pond._respawn.clear()
        m.phase = fishing.WAIT
        m.hook_x, m.float_x, m.hook_y = 220.0, 220.0, WATER_Y + 20.0
        m.leader, m.wait_t = 20.0, 1.0
        return m

    @staticmethod
    def add(m, key, off=10.0):
        fish = Fish(SPECIES[key], random.Random(1))
        fish.x, fish.y = m.hook_x - off, m.hook_y
        m.pond.fish.append(fish)
        return fish

    @staticmethod
    def hold(m):
        m.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(900, 500), button=1))

    def test_a_reeled_bait_is_still_alluring(self, minigame):
        self.hold(minigame)
        for _ in range(30):
            minigame.update(DT)
        assert minigame.hook.reeling and minigame.hook.alluring

    def test_reeling_past_a_pike_gets_it_on_and_letting_go_and_pressing_strikes_it(self, minigame):
        fish = self.add(minigame, "pike")
        self.hold(minigame)
        for _ in range(60 * 10):
            minigame.update(DT)
            if fish.state == TAKE:
                break
        assert fish.state == TAKE
        minigame.update(DT)
        assert not minigame.hook.reeling            # the reel stops as it takes
        minigame.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=(900, 500), button=1))
        assert minigame.phase == fishing.WAIT       # letting go is no strike
        minigame.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE))
        assert minigame.phase == fishing.FIGHT and minigame.fight.fish is fish

    def test_reeling_past_a_roach_gets_nothing(self, minigame):
        fish = self.add(minigame, "roach")
        self.hold(minigame)
        for _ in range(60 * 5):
            minigame.update(DT)
            assert fish.state not in (APPROACH, INSPECT, NIBBLE, TAKE)
