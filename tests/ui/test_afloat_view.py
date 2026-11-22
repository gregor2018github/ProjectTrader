"""A floating building's picture: turned about the middle of its foot and lifted by its bob."""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
import pytest

from src.ui.layout_modules.afloat_view import afloat_pose, turned


@pytest.fixture
def sprite():
    pygame.init()
    surface = pygame.Surface((140, 90), pygame.SRCALPHA)
    surface.fill((40, 80, 120, 255))
    surface.fill((255, 0, 0, 255), pygame.Rect(68, 86, 4, 4))   # a dot at the middle of its foot
    return surface


def foot_middle(picture, pos):
    """Where the red dot at the middle of the foot is drawn: the centre of the reddest pixels."""
    spots = [(x, y) for x in range(picture.get_width()) for y in range(picture.get_height())
             if picture.get_at((x, y)).r > 150]
    return (pos[0] + sum(x for x, _ in spots) / len(spots) + 0.5,
            pos[1] + sum(y for _, y in spots) / len(spots) + 0.5)


def test_still_it_is_drawn_where_it_was(sprite):
    picture, pos = afloat_pose(sprite, 100, 200, 0.0, 0.0)
    assert picture is sprite and pos == (100, 200)


def test_the_bob_lifts_it(sprite):
    _, pos = afloat_pose(sprite, 100, 200, -2.0, 0.0)
    assert pos == (100, 198)


def test_still_the_dot_is_found(sprite):
    assert foot_middle(sprite, (100, 200)) == (170, 288)


@pytest.mark.parametrize("angle", [-1.5, -0.5, 0.75, 1.5])
def test_turned_its_foot_stays_put(sprite, angle):
    picture, pos = afloat_pose(sprite, 100, 200, 0.0, angle)
    x, y = foot_middle(picture, pos)
    assert abs(x - 170) <= 1.5 and abs(y - 288) <= 1.5


def test_the_turned_pictures_are_kept(sprite):
    assert turned(sprite, 1.0) is turned(sprite, 1.0)
