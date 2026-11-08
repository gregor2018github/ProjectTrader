"""The fishing fight: the marker to keep the mouse under, the rages, and that a bigger fish is harder."""

import datetime
import os
import random
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from src.models.minigames import fishing
from src.models.minigames.fishing import Fight, FishingMinigame
from src.models.minigames.fishing_pond import Fish, SPECIES
from src.models.statistics import Statistics

DT = 1 / 60
TIP = (40.0, 30.0)
SMALL = ("roach", 20)
BIG = ("pike", 100)


def make_fight(kind, seed=1, hand=0.5):
    rng = random.Random(seed)
    fish = Fish(SPECIES[kind[0]], rng)
    fish.cm = kind[1]
    fish.x, fish.y = 170.0, 90.0
    return Fight(fish, 0.8, TIP, rng, hand)


def calm_at_rest(fight):
    """Hold the fish in one mode for the test: rest, with long enough to go."""
    fight.mode, fight.mode_t = "rest", 99.0
    return fight


def play(fight, player, seconds=120.0):
    """Runs the fight with player(fight) -> (reeling, hand); returns how it ended."""
    while fight.t < seconds:
        reeling, hand = player(fight)
        for event in fight.update(DT, TIP, reeling, hand):
            if event in ("land", "snap", "slip", "thrown"):
                return event
    return "time"


def careful(fight):
    """Follows the marker exactly, lets go through rages and leaps and when the line strains."""
    return fight.mode not in ("brace", "rage", "jump") and fight.strain < 0.4, fight.bar_x


class TestInTheRealOverlay:
    """Through FishingMinigame itself, whose rod bends and swings, not a Fight with a fixed tip."""

    @pytest.fixture
    def minigame(self):
        pygame.init()
        screen = pygame.display.set_mode((1920, 1080))
        state = SimpleNamespace(date=datetime.datetime(1500, 1, 4, 10), coin_popups=[], screen=screen,
                                log_event=lambda *a: None)
        game = SimpleNamespace(state=state, sounds={}, weather=SimpleNamespace(),
                               depot=SimpleNamespace(stats=Statistics(), book_labor_income=lambda *a: None))
        return FishingMinigame(screen, game, random.Random(1))

    @staticmethod
    def hold_on_marker(minigame, kind, seed=1):
        rng = random.Random(seed)
        fish = Fish(SPECIES[kind[0]], rng)
        fish.cm = kind[1]
        fish.x, fish.y = 170.0, 90.0
        minigame.pond.fish.append(fish)
        minigame._start_fight(fish, 0.8, "GOOD STRIKE")
        minigame.lmb = True
        return minigame.fight

    def test_a_bending_rod_gives_the_line_no_slack(self, minigame):
        fight = self.hold_on_marker(minigame, ("bream", 40))
        fight.mode, fight.mode_t, fight.dir = "run", 99.0, (1.0, 0.0)
        fight.endurance = 1e9
        tensions = []
        for frame in range(60 * 2):
            minigame.hand = fight.bar_x
            fight.strain = 0.0              # keep the line whole: only the tension is watched here
            minigame.update(DT)
            if frame > 30:
                tensions.append(fight.T)
        assert min(tensions) > fishing.SNAP_TENSION

    def test_holding_on_the_marker_snaps_the_line_of_a_big_fish(self, minigame):
        fight = self.hold_on_marker(minigame, BIG)
        while minigame.phase == fishing.FIGHT and fight.t < 60:
            minigame.hand = fight.bar_x
            minigame.update(DT)
        assert any("snapped" in popup[0] for popup in minigame.popups)


class TestMarker:
    def test_starts_over_the_mouse(self):
        assert make_fight(SMALL, hand=0.3).bar_x == pytest.approx(0.3)

    def test_swings_both_ways_across_the_bar_and_stays_on_it(self):
        fight = calm_at_rest(make_fight(BIG))
        seen = []
        for _ in range(60 * 30):
            fight._swing(DT)
            seen.append(fight.bar_x)
        assert min(seen) >= fishing.BAR_EDGE - 1e-9
        assert max(seen) <= 1 - fishing.BAR_EDGE + 1e-9
        assert max(seen) - min(seen) > 0.5

    def test_tracking_is_full_in_the_zone_and_gone_well_outside_it(self):
        fight = make_fight(SMALL, hand=0.5)
        assert fight.tracking(0.5 + fight.zone * 0.9) == 1.0
        assert fight.tracking(0.5 + fight.zone * (1 + fishing.BAR_FALLOFF)) == 0.0
        assert 0.0 < fight.tracking(0.5 - fight.zone * (1 + fishing.BAR_FALLOFF / 2)) < 1.0


class TestReeling:
    def test_reeling_on_the_marker_brings_the_fish_in(self):
        fight = calm_at_rest(make_fight(SMALL))
        line = fight.line
        for _ in range(60):
            fight.update(DT, TIP, True, fight.bar_x)
        assert fight.line < line - 10

    def test_reeling_off_the_marker_gains_nothing(self):
        fight = calm_at_rest(make_fight(SMALL))
        line = fight.line
        for _ in range(60):
            fight.update(DT, TIP, True, fight.bar_x + 0.5)
        assert fight.line >= line

    def test_off_the_marker_the_line_is_under_more_tension(self):
        on, off = make_fight(("bream", 40)), make_fight(("bream", 40))
        for fight in (on, off):         # running straight away from the rod, the line taut
            fight.mode, fight.mode_t, fight.dir = "run", 99.0, (1.0, 0.0)
        for _ in range(60):
            on.update(DT, TIP, True, on.bar_x)
            off.update(DT, TIP, True, off.bar_x + 0.5)
        assert off.T > on.T + 0.2

    def test_a_let_go_line_lets_the_fish_recover(self):
        fight = calm_at_rest(make_fight(BIG))
        fight.stamina = 0.5
        for _ in range(60):
            fight.update(DT, TIP, False, fight.bar_x)
        assert fight.stamina > 0.5


class TestRage:
    def rage(self, kind):
        fight = make_fight(kind)
        fight.update(DT, TIP, True, fight.bar_x)
        fight.mode, fight.mode_t = "brace", 0.0
        return fight

    def test_it_is_warned_of_then_ends_in_a_rest_to_reel_in(self):
        fight = make_fight(BIG)
        fight.mode, fight.mode_t = "brace", 0.0
        assert "rage" in fight.update(DT, TIP, False, fight.bar_x)
        assert fight.mode == "rage"
        fight.mode_t = 0.0
        assert "calm" in fight.update(DT, TIP, False, fight.bar_x)
        assert fight.mode == "rest"
        assert fight.mode_t == pytest.approx(fishing.RAGE_REST_S)

    def test_holding_on_through_it_snaps_the_line(self):
        fight = self.rage(BIG)
        fight.update(DT, TIP, True, fight.bar_x)
        fight.mode_t = 99.0
        events = []
        for _ in range(60 * 5):
            events += fight.update(DT, TIP, True, fight.bar_x)
            if "snap" in events:
                break
        assert "snap" in events

    def test_letting_go_through_it_saves_the_line_but_gives_it_line(self):
        fight = self.rage(BIG)
        fight.update(DT, TIP, False, fight.bar_x)
        fight.mode_t = 5.0
        line = fight.line
        events = []
        for _ in range(60 * 4):
            events += fight.update(DT, TIP, False, fight.bar_x)
        assert "snap" not in events
        assert fight.strain == 0.0
        assert fight.line > line


class TestOnlyTheTiniestCanBeHeld:
    """Following the marker perfectly and never letting go."""

    @staticmethod
    def landed(kind):
        return sum(play(make_fight(kind, seed), lambda f: (True, f.bar_x)) == "land" for seed in range(40))

    @pytest.mark.parametrize("kind", (("roach", 14), ("roach", 16), ("roach", 18)))
    def test_the_tiniest_can(self, kind):
        assert self.landed(kind) >= 36

    @pytest.mark.parametrize("kind", (("roach", 24), ("roach", 32), ("perch", 25), ("bream", 40), ("tench", 35)))
    def test_anything_more_mostly_snaps_the_line(self, kind):
        assert self.landed(kind) <= 12

    @pytest.mark.parametrize("kind", (("carp", 55), ("pike", 65), ("pike", 100)))
    def test_a_big_one_never_lets_you(self, kind):
        assert self.landed(kind) == 0

    def test_strain_hardly_eases_until_the_button_is_let_go(self):
        assert fishing.STRAIN_EASE_HOLDING < fishing.STRAIN_EASE_LET_GO / 4


class TestBiggerIsHarder:
    def test_narrower_zone_and_faster_marker(self):
        small, big = make_fight(SMALL), make_fight(BIG)
        assert big.heft > small.heft
        assert big.zone < small.zone
        assert fishing._lerp(fishing.BAR_SPEED, big.heft) > fishing._lerp(fishing.BAR_SPEED, small.heft)

    def test_rages_more_often_and_longer(self):
        def rage_seconds(kind):
            total = 0.0
            for seed in range(10):
                fight = make_fight(kind, seed)
                fight.endurance = 1e9       # keep it fresh: only how it behaves counts here
                fight.t = 0.0
                for _ in range(60 * 40):
                    fight.update(DT, TIP, False, fight.bar_x)
                    total += DT if fight.mode == "rage" else 0.0
                    fight.slip = 0.0
            return total
        assert rage_seconds(BIG) > 2 * rage_seconds(SMALL)

    def test_holding_on_blindly_loses_the_big_one(self):
        assert sum(play(make_fight(BIG, seed), lambda f: (True, f.bar_x)) == "land" for seed in range(20)) < 5

    def test_a_careful_player_lands_both(self):
        for kind in (SMALL, BIG):
            assert sum(play(make_fight(kind, seed), careful) == "land" for seed in range(20)) >= 15


@pytest.mark.parametrize("kind", (SMALL, BIG))
def test_holding_without_following_the_marker_rarely_lands_anything(kind):
    assert sum(play(make_fight(kind, seed), lambda f: (True, 0.1)) == "land" for seed in range(20)) <= 4


def test_never_reeling_lands_nothing():
    assert all(play(make_fight(SMALL, seed), lambda f: (False, f.bar_x), 60.0) != "land" for seed in range(10))
