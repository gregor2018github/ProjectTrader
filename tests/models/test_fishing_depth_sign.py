"""The sign at the top of the fishing scene: what the line's depth is, and what the wheel just did."""

import datetime
import os
import random
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from src.models.minigames import fishing
from src.models.minigames.fishing import FishingMinigame, SCENE_H, SCENE_W
from src.models.statistics import Statistics

DT = 1 / 60


@pytest.fixture(scope="module", autouse=True)
def screen():
    pygame.init()
    yield pygame.display.set_mode((1920, 1080))


@pytest.fixture
def minigame(screen):
    stats = Statistics()
    stats.minigame_tips_seen = [fishing.TIP_TUTORIAL_CAST, fishing.TIP_TUTORIAL_FIGHT]
    state = SimpleNamespace(date=datetime.datetime(1500, 1, 4, 10), coin_popups=[], screen=screen,
                            log_event=lambda *a: None)
    game = SimpleNamespace(state=state, sounds={}, weather=SimpleNamespace(),
                           depot=SimpleNamespace(stats=stats, book_labor_income=lambda *a: None))
    return FishingMinigame(screen, game, random.Random(1))


def wheel(minigame, y):
    minigame.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, y=y))


def sign(minigame):
    return minigame._draw_depth(pygame.Surface((SCENE_W, SCENE_H)))


class TestWhereItIs:
    def test_it_is_at_the_top_in_the_middle(self, minigame):
        rect = sign(minigame)
        assert rect.centerx == SCENE_W // 2
        assert rect.top < 20

    def test_it_stays_clear_of_the_worms_and_the_ponds_name(self, minigame):
        rect = sign(minigame)
        scene = pygame.Surface((SCENE_W, SCENE_H))
        worms = minigame._plaque(scene, f"Worms: {minigame.worms}", (SCENE_W - 14, 12))
        worm_row = worms.left - 16 - minigame.worms * 13
        assert rect.right < worm_row
        assert rect.left > 12 + minigame.font_small.size(minigame.pond.lore)[0]

    def test_it_keeps_its_size_from_notch_to_notch(self, minigame):
        sizes = set()
        for leader in range(int(fishing.LEADER_RANGE[0]), int(fishing.LEADER_RANGE[1]) + 1, int(fishing.LEADER_STEP)):
            minigame.leader = float(leader)
            sizes.add(sign(minigame).size)
        assert len(sizes) == 1


class TestWhenItShows:
    @pytest.mark.parametrize("phase", [fishing.READY, fishing.DRAW, fishing.FLIGHT, fishing.WAIT, fishing.STUCK])
    def test_while_the_line_matters(self, minigame, phase):
        minigame.phase = phase
        assert sign(minigame) is not None

    @pytest.mark.parametrize("phase", [fishing.FIGHT, fishing.LANDING, fishing.CARD, fishing.RETRIEVE])
    def test_not_otherwise(self, minigame, phase):
        minigame.phase = phase
        assert sign(minigame) is None

    def test_the_wheels_room_only_while_the_wheel_can_set_it(self, minigame):
        with_wheel = sign(minigame).width
        minigame.phase = fishing.WAIT
        assert sign(minigame).width < with_wheel


class TestTheWheel:
    def test_a_turn_towards_you_goes_deeper_and_the_sign_says_so(self, minigame):
        before = minigame.leader
        wheel(minigame, -1)
        assert minigame.leader == before + fishing.LEADER_STEP
        assert minigame.depth_turn == 1 and minigame.depth_nudge > 0

    def test_a_turn_away_goes_shallower_and_the_sign_says_so(self, minigame):
        before = minigame.leader
        wheel(minigame, 1)
        assert minigame.leader == before - fishing.LEADER_STEP
        assert minigame.depth_turn == -1 and minigame.depth_nudge > 0

    def test_at_the_end_of_its_range_nothing_lights_up(self, minigame):
        minigame.leader = fishing.LEADER_RANGE[1]
        wheel(minigame, -1)
        assert minigame.leader == fishing.LEADER_RANGE[1] and minigame.depth_nudge == 0

    def test_the_light_goes_out_after_a_moment(self, minigame):
        wheel(minigame, -1)
        for _ in range(round(fishing._DEPTH_NUDGE_S / DT) + 2):
            minigame.update(DT)
        assert minigame.depth_nudge == 0

    def test_the_sign_looks_different_while_lit(self, minigame):
        def picture():
            surf = pygame.Surface((SCENE_W, SCENE_H))
            rect = minigame._draw_depth(surf)
            return pygame.image.tobytes(surf.subsurface(rect), "RGB")
        still = picture()
        minigame.depth_nudge, minigame.depth_turn = 1.0, 1
        deeper = picture()
        minigame.depth_turn = -1
        shallower = picture()
        assert len({still, deeper, shallower}) == 3
