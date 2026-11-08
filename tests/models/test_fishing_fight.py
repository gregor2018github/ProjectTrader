"""The fishing fight: the bar with its momentum, the fish by its kind, the catch meter and the perfect catch."""

import datetime
import os
import random
from collections import deque
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from src.models.minigames import fishing, fishing_scene
from src.models.minigames.fishing import Fight, FishingMinigame
from src.models.minigames.fishing_pond import Fish, SPECIES
from src.models.statistics import Statistics

DT = 1 / 60
SMALL = ("roach", 20)
BIG = ("pike", 100)


def make_fight(kind, seed=1, hold=0.8):
    rng = random.Random(seed)
    fish = Fish(SPECIES[kind[0]], rng)
    fish.cm = kind[1]
    fish.x, fish.y = 194.0, 90.0
    return Fight(fish, hold, rng)


def under_way(kind=SMALL, **args):
    """A fight past its first moments."""
    fight = make_fight(kind, **args)
    fight.grace = 0.0
    return fight


def player_who_sees(late_frames, ahead):
    """Sees the fish and the bar so many frames late, and reckons the bar's way so many seconds ahead."""
    seen = deque()

    def player(fight):
        seen.append((fight.fish_at, fight.bar_at, fight.bar_v))
        if len(seen) > late_frames + 1:
            seen.popleft()
        fish_at, bar_at, bar_v = seen[0]
        return bar_at + bar_v * ahead < fish_at
    return player


def sharp():
    return player_who_sees(6, 0.28)


def fair():
    """About what a person manages: a quarter of a second late."""
    return player_who_sees(14, 0.3)


def play(fight, player, seconds=120.0):
    """Runs the fight; returns how it ended."""
    while fight.t < seconds:
        for event in fight.update(DT, player(fight)):
            if event in ("land", "free"):
                return event
    return "time"


def landed(kind, make_player, seeds=30):
    return sum(play(make_fight(kind, seed), make_player()) == "land" for seed in range(seeds))


class TestTheBar:
    def test_it_starts_over_the_fish(self):
        for seed in range(10):
            assert make_fight(BIG, seed).fish_in_bar

    def test_holding_makes_it_rise_and_letting_go_makes_it_fall(self):
        fight = under_way()
        fight.bar_at, fight.bar_v = 0.5, 0.0
        for _ in range(20):
            fight._move_bar(DT, True)
        high = fight.bar_at
        assert high > 0.5
        fight.bar_at, fight.bar_v = 0.5, 0.0
        for _ in range(20):
            fight._move_bar(DT, False)
        assert fight.bar_at < 0.5

    def test_it_keeps_moving_a_moment_after_letting_go(self):
        fight = under_way()
        fight.bar_at, fight.bar_v = 0.3, 0.0
        for _ in range(30):
            fight._move_bar(DT, True)
        at, speed = fight.bar_at, fight.bar_v
        assert speed > 0
        fight._move_bar(DT, False)
        assert fight.bar_at > at

    def test_it_stays_in_the_column_and_bounces_off_its_foot(self):
        fight = under_way()
        for _ in range(60 * 4):
            fight._move_bar(DT, False)
            assert fight.bar_at >= fight.bar_h / 2
        fight.bar_at, fight.bar_v = fight.bar_h / 2 + 0.001, -0.8
        fight._move_bar(DT, False)
        assert fight.bar_v > 0
        for _ in range(60 * 4):
            fight._move_bar(DT, True)
            assert fight.bar_at <= 1 - fight.bar_h / 2

    def test_quick_taps_keep_it_hovering(self):
        fight = under_way()
        fight.bar_at, fight.bar_v = 0.5, 0.0
        spots = []
        for _ in range(60 * 5):
            fight._move_bar(DT, fight.bar_at + fight.bar_v * 0.28 < 0.5)
            spots.append(fight.bar_at)
        assert max(spots) - min(spots) < 0.15


class TestTheFish:
    @pytest.mark.parametrize("key", sorted(SPECIES))
    def test_every_kind_has_a_way_of_moving(self, key):
        assert SPECIES[key].style in fishing.STYLES

    def test_it_moves_by_itself_and_stays_in_the_column(self):
        fight = under_way(BIG)
        spots = []
        for _ in range(60 * 30):
            fight._swim(DT)
            spots.append(fight.fish_at)
        assert min(spots) >= 0 and max(spots) <= 1
        assert max(spots) - min(spots) > 0.5

    @staticmethod
    def mean_place(key, cm=30):
        total, frames = 0.0, 0
        for seed in range(6):
            fight = under_way((key, cm), seed=seed)
            for _ in range(60 * 40):
                fight._swim(DT)
                total += fight.fish_at
                frames += 1
        return total / frames

    def test_a_sinker_keeps_low_and_a_floater_high(self):
        assert self.mean_place("bream") < 0.45 < 0.55 < self.mean_place("rudd")

    def test_a_darter_turns_oftener_and_sharper_than_a_smooth_one(self):
        def travel(key, cm):
            fight, way, last = under_way((key, cm)), 0.0, None
            for _ in range(60 * 40):
                fight._swim(DT)
                way += abs(fight.fish_at - last) if last is not None else 0.0
                last = fight.fish_at
            return way
        assert travel("perch", 25) > 1.3 * travel("roach", 25)

    def test_a_bigger_one_goes_faster_and_leaves_a_smaller_bar(self):
        small, big = make_fight(SMALL), make_fight(BIG)
        assert big.max_speed > small.max_speed
        assert big.bar_h < small.bar_h

    def test_it_holds_still_for_the_first_moments_and_the_meter_too(self):
        fight = make_fight(BIG)
        at, meter = fight.fish_at, fight.catch
        for _ in range(int(fishing.GRACE_S / DT) - 1):
            fight.update(DT, False)
        assert fight.fish_at == at and fight.catch == meter

    def test_it_shows_in_the_pond_at_its_depth_and_nearer_the_bank_as_the_meter_fills(self):
        fight = under_way(("bream", 40))
        fight._swim = lambda dt: None
        fight.fish_at = 0.9
        for _ in range(120):
            fight.update(DT, False)
            fight.bar_at, fight.bar_v = 0.9, 0.0
        shallow = fight.fish.y
        fight.fish_at = 0.1
        for _ in range(120):
            fight.update(DT, False)
            fight.bar_at, fight.bar_v = 0.1, 0.0
        assert fight.fish.y > shallow + 10
        assert fight.fish.x < fight.from_x


class TestTheMeter:
    def test_it_fills_with_the_fish_in_the_bar_and_drains_out_of_it(self):
        fight = under_way()
        fight._swim = lambda dt: None
        fight.fish_at, fight.bar_at, fight.bar_v, fight.catch = 0.5, 0.5, 0.0, 0.5
        fight.update(DT, True)
        assert fight.catch == pytest.approx(0.5 + fight.fill * DT)
        fight.fish_at, fight.bar_at, fight.catch = 0.95, 0.2, 0.5
        fight.update(DT, False)
        assert fight.catch == pytest.approx(0.5 - fight.drain * DT)

    def test_full_lands_it_and_empty_loses_it(self):
        fight = under_way()
        fight._swim = lambda dt: None
        fight.fish_at, fight.bar_at, fight.bar_v, fight.catch = 0.5, 0.5, 0.0, 0.9999
        assert "land" in fight.update(DT, True)
        fight.fish_at, fight.bar_at, fight.catch = 0.95, 0.2, 0.0001
        assert "free" in fight.update(DT, False)

    def test_a_better_strike_starts_it_higher(self):
        assert make_fight(SMALL, hold=1.0).catch > make_fight(SMALL, hold=0.8).catch > make_fight(SMALL, hold=0.55).catch

    def test_a_bigger_fish_takes_longer_and_drains_faster(self):
        small, big = make_fight(SMALL), make_fight(BIG)
        assert big.fill < small.fill
        assert big.drain > small.drain


class TestThePerfectCatch:
    def test_a_fish_that_left_the_bar_is_no_longer_perfect(self):
        fight = under_way()
        assert fight.perfect
        fight._swim = lambda dt: None
        fight.fish_at, fight.bar_at = 0.95, 0.2
        fight.update(DT, False)
        assert not fight.perfect

    def test_the_first_moments_do_not_count(self):
        fight = make_fight(SMALL)
        fight.fish_at, fight.bar_at = 0.95, 0.2
        fight.update(DT, False)
        assert fight.perfect


class TestWhoLandsWhat:
    """Simulated players, all on the same fish: the fight's balance."""

    @pytest.mark.parametrize("kind", (("roach", 16), ("roach", 28), ("rudd", 22), ("perch", 25), ("bream", 40)))
    def test_a_fair_player_lands_the_common_fish(self, kind):
        assert landed(kind, fair) >= 25

    @pytest.mark.parametrize("kind", (("carp", 55), ("eel", 60), ("pike", 65), ("golden_carp", 60)))
    def test_a_sharp_player_lands_the_big_ones(self, kind):
        assert landed(kind, sharp) >= 20

    def test_the_biggest_is_hard_but_can_be_done(self):
        assert 0 < landed(BIG, sharp) < 30
        assert landed(BIG, fair) < landed(("perch", 25), fair)

    @pytest.mark.parametrize("kind", (("roach", 28), ("perch", 25), ("bream", 40), ("tench", 35), ("rudd", 22), ("pike", 65)))
    def test_just_holding_mostly_loses_it(self, kind):
        assert landed(kind, lambda: (lambda fight: True)) <= 15     # a floater, up there anyway, is the most it gets

    @pytest.mark.parametrize("kind", (("roach", 28), ("perch", 25), ("bream", 40), ("tench", 35), ("rudd", 22), ("pike", 65)))
    def test_never_pressing_mostly_loses_it(self, kind):
        assert landed(kind, lambda: (lambda fight: False)) <= 10


class TestInTheRealOverlay:
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
        return FishingMinigame(screen, game, random.Random(1))

    @staticmethod
    def hook(minigame, kind=SMALL):
        fish = Fish(SPECIES[kind[0]], random.Random(1))
        fish.cm = kind[1]
        fish.x, fish.y = 194.0, 90.0
        minigame.pond.fish.append(fish)
        minigame._start_fight(fish, 0.8, "GOOD STRIKE")
        minigame.fight.grace = 0.0
        return minigame.fight

    @staticmethod
    def key(minigame, kind, code=pygame.K_SPACE):
        minigame.handle_event(pygame.event.Event(kind, key=code))

    @pytest.mark.parametrize("press", ("space", "mouse"))
    def test_space_and_the_left_button_both_raise_the_bar(self, minigame, press):
        fight = self.hook(minigame)
        fight.bar_at, fight.bar_v = 0.5, 0.0
        if press == "space":
            self.key(minigame, pygame.KEYDOWN)
        else:
            minigame.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(900, 500), button=1))
        for _ in range(20):
            minigame.update(DT)
        assert fight.bar_at > 0.5

    def test_letting_go_of_space_lets_it_fall(self, minigame):
        fight = self.hook(minigame)
        fight.bar_at, fight.bar_v = 0.5, 0.0
        self.key(minigame, pygame.KEYDOWN)
        self.key(minigame, pygame.KEYUP)
        for _ in range(20):
            minigame.update(DT)
        assert fight.bar_at < 0.5

    def land(self, minigame, perfect):
        fight = self.hook(minigame)
        fight.perfect = perfect
        fight.catch = 0.9999
        fight.bar_at, fight.fish_at, fight.bar_v = 0.5, 0.5, 0.0
        fight._swim = lambda dt: None
        minigame.update(DT)
        assert minigame.phase == fishing.LANDING
        for _ in range(int((fishing.NET_S + fishing.LIFT_S) / DT) + 5):
            minigame.update(DT)
        assert minigame.phase == fishing.CARD
        return minigame.card

    def test_a_perfect_catch_pays_more_and_says_so(self, minigame):
        card = self.land(minigame, perfect=True)
        fish = card["fish"]
        assert card["perfect"]
        assert card["coins"] == pytest.approx(fishing.fish_coins(fish, fishing.PERFECT_CATCH_MULT * minigame.cast_mult))
        minigame.draw()

    def test_a_plain_catch_pays_the_plain_price(self, minigame):
        card = self.land(minigame, perfect=False)
        assert not card["perfect"]
        assert card["coins"] == pytest.approx(fishing.fish_coins(card["fish"], minigame.cast_mult))

    def test_the_column_stands_left_of_the_player_inside_the_scene(self):
        whole = fishing._COLUMN.union(fishing._COLUMN.move(fishing._METER_W + 8, 0)).inflate(14, 14)
        assert whole.left >= 0 and whole.right <= fishing_scene._PLAYER_LEFT * fishing.PX

    def test_the_column_draws(self, minigame):
        self.hook(minigame, BIG)
        minigame.update(DT)
        minigame.draw()
