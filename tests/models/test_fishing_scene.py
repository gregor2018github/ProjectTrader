"""The pond's drawing: the shafts of light stay in the water, the back-swing stays in the frame."""

import os
import random
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from src.models.minigames import fishing
from src.models.minigames.fishing import DEG_PER_PX, READY_THETA, THETA_RANGE, FishingMinigame
from src.models.minigames.fishing_pond import LOW_W, bottom_y
from src.models.minigames.fishing_scene import PondScene, _SHAFT_H, _SHAFT_TOP, rod_points


@pytest.fixture
def layer():
    """Shafts every few pixels, at full daylight, so that one crosses every spot it can."""
    pygame.init()
    pygame.display.set_mode((1, 1))
    scene = PondScene(rng=random.Random(1))
    scene.shafts = [float(x) for x in range(-40, LOW_W + 40, 2)]
    return scene._shaft_layer(1.0)


def test_no_light_on_the_bank_or_in_the_bottom(layer):
    for x in range(LOW_W):
        for row in range(max(0, int(bottom_y(x)) - _SHAFT_TOP), _SHAFT_H):
            assert layer.get_at((x, row)).a == 0, (x, row)


def test_the_open_water_still_gets_its_light(layer):
    assert layer.get_at((150, 0)).a > 0
    assert layer.get_at((150, 40)).a > 0


@pytest.mark.parametrize("bend", (-20.0, 0.0, 20.0))
def test_the_rod_stays_in_the_picture_all_the_way_back(bend):
    for theta in range(int(THETA_RANGE[0]), int(THETA_RANGE[1]) + 1, 4):
        for x, y in rod_points(theta, bend):
            assert 0 <= x < LOW_W and y >= 0, (theta, x, y)


@pytest.fixture
def minigame():
    pygame.init()
    screen = pygame.display.set_mode((1920, 1080))
    return FishingMinigame(screen, SimpleNamespace(), random.Random(1), demo=True)


def frame_left(minigame):
    return minigame.canvas_rect.left + fishing._SCENE_RECT.left


def test_pressed_with_room_the_rod_turns_at_its_usual_rate(minigame):
    minigame.press_x = frame_left(minigame) + 800
    assert minigame._rod_target(minigame.press_x - 100) == pytest.approx(READY_THETA - 100 * DEG_PER_PX)
    assert minigame._rod_target(minigame.press_x + 50) == pytest.approx(READY_THETA + 50 * DEG_PER_PX)


def test_pressed_near_the_edge_the_whole_back_swing_fits_in_the_frame(minigame):
    minigame.press_x = frame_left(minigame) + 200
    assert minigame._rod_target(frame_left(minigame)) == pytest.approx(THETA_RANGE[0])
    assert minigame._rod_target(minigame.press_x) == pytest.approx(READY_THETA)


def test_the_forward_stroke_is_not_geared_up(minigame):
    minigame.press_x = frame_left(minigame) + 200
    assert minigame._rod_target(minigame.press_x + 50) == pytest.approx(READY_THETA + 50 * DEG_PER_PX)
