"""The player's hair colour (models/figurines/humans/hair.py): the hair found in
every frame by its colour, nothing else taken, painted keeping its shading."""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from src.models.figurines.humans import hair
from src.models.figurines.humans.hair import (
    DEFAULT_HAIR, HAIR_COLOURS, SWATCHES, hair_key, hair_mask, recolour_hair,
)

PLAYER_DIR = os.path.join("assets", "map_sprites", "figurines", "humans", "player")
FRAMES = sorted(f for f in os.listdir(PLAYER_DIR) if f.startswith("player_") and f.endswith(".png"))


@pytest.fixture(scope="module", autouse=True)
def _pygame():
    pygame.init()
    pygame.display.set_mode((1, 1))
    yield


def _load(name):
    return pygame.image.load(os.path.join(PLAYER_DIR, name)).convert_alpha()


def test_the_colours_are_distinct_and_the_default_is_the_artwork():
    keys = [key for key, _name, _colour in HAIR_COLOURS]
    assert len(set(keys)) == len(keys) >= 5
    assert dict((k, c) for k, _n, c in HAIR_COLOURS)[DEFAULT_HAIR] is None
    assert len(set(SWATCHES.values())) == len(SWATCHES)


def test_an_unknown_key_falls_back_to_the_default():
    assert hair_key(None) == DEFAULT_HAIR
    assert hair_key("green") == DEFAULT_HAIR
    assert hair_key("blond") == "blond"


@pytest.mark.parametrize("name", FRAMES)
def test_every_frame_has_its_hair_found_in_the_upper_half(name):
    sprite = _load(name)
    mask = hair_mask(sprite)
    drawn = sprite.get_bounding_rect()
    assert mask.count() > 5000, "the hair is a large patch on every frame"
    assert mask.get_bounding_rects()[0].bottom <= drawn.top + drawn.height * hair._HEAD_SHARE + 1
    # Neither the skin (the face's middle) nor the boots
    lower = pygame.mask.Mask(sprite.get_size())
    lower.draw(pygame.mask.Mask((drawn.width, drawn.height // 3), fill=True),
               (drawn.left, drawn.bottom - drawn.height // 3))
    assert mask.overlap_area(lower, (0, 0)) == 0


def test_the_default_changes_nothing():
    sprite = _load("player_front_static.png")
    assert recolour_hair(sprite, DEFAULT_HAIR) is sprite
    assert recolour_hair(sprite, None) is sprite


def test_a_colour_paints_only_the_hair_and_keeps_its_shading():
    sprite = _load("player_front_static.png")
    mask = hair_mask(sprite)
    painted = recolour_hair(sprite, "blond")
    assert painted is not sprite and painted.get_size() == sprite.get_size()
    w, h = sprite.get_size()
    changed_outside = 0
    lights = []
    for y in range(0, h, 3):
        for x in range(0, w, 3):
            if mask.get_at((x, y)):
                lights.append(sum(painted.get_at((x, y))[:3]))
            elif painted.get_at((x, y)) != sprite.get_at((x, y)):
                changed_outside += 1
    assert changed_outside == 0
    # Lighter than the brown it was, and still shaded rather than one flat colour
    assert sum(lights) / len(lights) > sum(hair.ARTWORK_HAIR) * 1.5
    assert max(lights) - min(lights) > 100
