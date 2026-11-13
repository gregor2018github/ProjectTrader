"""The Gourmet Collection's previews made ahead: every dish picture has its small copy and its
grey silhouette, the silhouette shows nothing of the dish but its shape, and the outline
is found on a painted background."""

import glob
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from src.config.constants import PICTURES_PATH
from src.ui import dish_previews
from src.ui.dish_previews import (PREVIEW_SIZE, SILHOUETTE, dish_mask, key_of_picture, load_preview,
                                  make_previews, preview_path)

PICTURES = sorted(glob.glob(os.path.join(PICTURES_PATH, "dish_*.png")))


@pytest.fixture(autouse=True)
def display():
    pygame.init()
    pygame.display.set_mode((10, 10))


def test_the_constants_the_tests_rely_on():
    assert PREVIEW_SIZE == (124, 88)
    assert dish_previews.PREVIEWS_PATH == os.path.join(PICTURES_PATH, "dish_previews")


def test_every_dish_picture_has_its_small_copy_and_its_silhouette():
    """Made by build_tools/Dish_Previews/make_dish_previews.py, or the Sprite Manager on saving a picture."""
    assert PICTURES
    missing = [os.path.basename(p) for p in PICTURES
               if not all(os.path.exists(preview_path(key_of_picture(p), tasted)) for tasted in (True, False))]
    assert missing == [], "run build_tools/Dish_Previews/make_dish_previews.py --missing"


def test_the_previews_fit_the_card_and_the_silhouette_is_one_grey():
    for picture in PICTURES[:6]:
        key = key_of_picture(picture)
        small, shape = load_preview(key, True), load_preview(key, False)
        assert small.get_width() <= PREVIEW_SIZE[0] and small.get_height() <= PREVIEW_SIZE[1]
        assert shape.get_size() == small.get_size()
        w, h = shape.get_size()
        colours = {shape.get_at((x, y))[:3] for x in range(w) for y in range(h) if shape.get_at((x, y)).a > 0}
        assert colours == {SILHOUETTE}
        assert shape.get_at((w // 2, h // 2)).a >= 250           # solid, but for the scaling's rounding
        assert shape.get_at((0, 0)).a == 0


def test_making_them_writes_both_files(tmp_path, monkeypatch):
    monkeypatch.setattr(dish_previews, "PREVIEWS_PATH", str(tmp_path))
    picture = pygame.Surface((300, 210))
    picture.fill((158, 146, 120))
    pygame.draw.ellipse(picture, (30, 24, 20), (60, 50, 180, 120))
    pygame.draw.ellipse(picture, (200, 150, 90), (66, 56, 168, 108))
    source = tmp_path / "dish_test_stew.png"
    pygame.image.save(picture, str(source))
    small, shape = make_previews(str(source))
    assert os.path.basename(small) == "test_stew.png" and os.path.basename(shape) == "test_stew_silhouette.png"
    assert pygame.image.load(small).get_size() == (124, 87)
    assert load_preview("test_stew", False).get_at((62, 43)).a >= 250


def test_a_missing_preview_is_none():
    assert load_preview("no_such_dish", True) is None


def test_the_outline_is_found_on_a_painted_background_and_comes_out_solid():
    """A dish drawn on a wall and a table, its inside the table's colour: the shape is the whole dish."""
    picture = pygame.Surface((160, 120))
    picture.fill((158, 146, 120))                                   # the wall
    pygame.draw.rect(picture, (140, 126, 96), (0, 70, 160, 50))     # the table
    for y in range(72, 120, 6):
        pygame.draw.line(picture, (130, 116, 88), (0, y), (160, y))  # its grain
    pygame.draw.ellipse(picture, (30, 24, 20), (30, 30, 100, 70))    # the dish's dark outline
    pygame.draw.ellipse(picture, (140, 126, 96), (34, 34, 92, 62))   # filled with the table's colour
    pygame.draw.circle(picture, (150, 120, 80), (8, 112), 2)        # a crumb by itself
    mask = dish_mask(picture)
    assert mask.get_at((80, 65)) == 1                               # the middle is the dish, not a hole
    assert mask.get_at((5, 5)) == 0 and mask.get_at((150, 110)) == 0
    assert mask.get_at((8, 112)) == 0                               # the crumb is trimmed off
    assert len(mask.connected_components()) == 1
