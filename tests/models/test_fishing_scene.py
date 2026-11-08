"""The pond's drawing: the shafts of light stay in the water."""

import os
import random

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from src.models.minigames.fishing_pond import LOW_W, bottom_y
from src.models.minigames.fishing_scene import PondScene, _SHAFT_H, _SHAFT_TOP


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
