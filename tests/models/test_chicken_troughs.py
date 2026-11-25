"""The chicken pen's troughs: water or grain, how full, the flock eating and drinking, the rain, the save
(models/chicken_troughs.py); the trough on the map, its pictures and the chickens at it (models/trough.py)."""

import datetime
import os
import random
import xml.etree.ElementTree as ET
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from src.models import chicken_troughs as ct
from src.models.chicken_troughs import FEED, WATER, Troughs, describe_fill, trough_title
from src.models.chickens import ChickenLook, Hen
from src.models.figurines.animals import chicken as chicken_module
from src.models.figurines.animals.chicken import Chicken
from src.models.trough import Trough

ROOT = Path(__file__).resolve().parents[2]
MAP = ROOT / "assets" / "tiles" / "Map1.tmx"
NOW = datetime.datetime(1500, 3, 1, 10, 0)


@pytest.fixture(autouse=True)
def _numbers(monkeypatch):
    """The numbers these tests count with."""
    monkeypatch.setattr(ct, "FEED_WHEAT_FULL", 2)
    monkeypatch.setattr(ct, "FEED_DAYS", 7.0)
    monkeypatch.setattr(ct, "WATER_DAYS", 4.0)
    monkeypatch.setattr(ct, "FLOCK_SIZE", 5)
    monkeypatch.setattr(ct, "RAIN_FILL_PER_HOUR", 0.25)
    monkeypatch.setattr(ct, "MAX_STEP_DAYS", 30.0)


def _days(n):
    return NOW + datetime.timedelta(days=n)


# -- what the player puts in ------------------------------------------------------

def test_a_trough_starts_empty_and_takes_either():
    troughs = Troughs(["a"])
    state = troughs["a"]
    assert state.empty and state.level() == 0 and state.picture() == "trough_empty"
    assert state.takes(WATER) and state.takes(FEED)
    assert trough_title(state) == "Empty Trough" and describe_fill(state) == "Empty"


def test_water_fills_it_to_the_brim_and_then_it_takes_no_grain_till_tipped_out():
    troughs = Troughs(["a"])
    assert troughs.pour_water("a")
    state = troughs["a"]
    assert state.full and state.picture() == "trough_water_4" and trough_title(state) == "Water Trough"
    assert not troughs.pour_water("a")                   # full already
    assert troughs.grain_needed("a") == 0 and not troughs.add_grain("a", 1)
    assert troughs.tip_out("a") and troughs["a"].empty
    assert not troughs.tip_out("a")
    assert troughs.add_grain("a", 1)


def test_grain_takes_whole_units_of_wheat_as_it_has_room_for():
    troughs = Troughs(["a"])
    assert troughs.grain_needed("a") == 2                # empty: two units fill it
    troughs.add_grain("a", 1)
    state = troughs["a"]
    assert state.kind == FEED and state.amount == pytest.approx(0.5) and state.picture() == "trough_feed_2"
    assert troughs.grain_needed("a") == 1
    state.amount = 0.9
    assert troughs.grain_needed("a") == 1                # at least one while it has room
    troughs.add_grain("a", 1)
    assert state.full and troughs.grain_needed("a") == 0
    assert not troughs.pour_water("a")


def test_the_pictures_level_shows_any_drop_as_a_quarter():
    troughs = Troughs(["a"])
    troughs.pour_water("a")
    state = troughs["a"]
    for amount, level in ((0.01, 1), (0.25, 1), (0.26, 2), (0.5, 2), (0.74, 3), (0.76, 4), (1.0, 4)):
        state.amount = amount
        assert state.level() == level, amount


# -- the flock and the weather -----------------------------------------------------

def test_the_flock_empties_a_full_trough_of_grain_in_a_week_and_of_water_in_four_days():
    troughs = Troughs(["grain", "water"])
    troughs.add_grain("grain", 2)
    troughs.pour_water("water")
    troughs.update(NOW, hens=5)                          # the first update only starts the count
    assert troughs["grain"].full
    troughs.update(_days(2), hens=5)
    assert troughs["water"].amount == pytest.approx(0.5)
    assert troughs["grain"].amount == pytest.approx(1 - 2 / 7)
    assert troughs.days_left("water", 5) == pytest.approx(2.0)
    troughs.update(_days(4), hens=5)
    assert troughs["water"].empty and troughs["water"].kind is None      # dry: it takes either again
    troughs.update(_days(7), hens=5)
    assert troughs["grain"].empty


def test_troughs_of_the_same_share_the_flock_and_fewer_hens_take_less():
    troughs = Troughs(["a", "b"])
    troughs.pour_water("a")
    troughs.pour_water("b")
    assert troughs.days_left("a", 5) == pytest.approx(8.0)
    troughs.update(NOW, hens=5)
    troughs.update(_days(4), hens=5)
    assert troughs["a"].amount == pytest.approx(0.5) and troughs["b"].amount == pytest.approx(0.5)
    assert troughs.days_left("a", 0) is None


def test_rain_tops_up_water_but_not_grain_or_an_empty_trough():
    troughs = Troughs(["water", "grain", "empty"])
    troughs.pour_water("water")
    troughs["water"].amount = 0.25
    troughs.add_grain("grain", 1)
    troughs.update(NOW, hens=0)
    troughs.update(NOW + datetime.timedelta(hours=2), hens=0, rain=1.0)
    assert troughs["water"].amount == pytest.approx(0.75)
    assert troughs["grain"].amount == pytest.approx(0.5)
    assert troughs["empty"].empty


def test_update_says_when_a_picture_changed_and_a_long_jump_counts_as_its_cap():
    troughs = Troughs(["a"])
    troughs.pour_water("a")
    troughs.update(NOW, hens=5)
    assert not troughs.update(NOW + datetime.timedelta(minutes=10), hens=5)
    assert troughs.update(_days(1.5), hens=5)            # 1.5 days: down to 0.625, three quarters' picture
    assert troughs["a"].picture() == "trough_water_3"
    troughs.pour_water("a")
    troughs.update(_days(400), hens=5)                   # a year away: a month at the most, dry all the same
    assert troughs["a"].empty


def test_the_save_keeps_each_trough_and_an_older_save_has_them_empty():
    troughs = Troughs(["a", "b"])
    troughs.pour_water("a")
    troughs.add_grain("b", 1)
    again = Troughs(["a", "b"])
    again.load(troughs.to_save())
    assert (again["a"].kind, again["a"].amount) == (WATER, 1.0)
    assert (again["b"].kind, again["b"].amount) == (FEED, 0.5)
    again.load(None)
    assert again["a"].empty and again["b"].empty
    again.load({"a": ["wine", 0.5], "b": "nonsense"})
    assert again["a"].empty and again["b"].empty


# -- the trough on the map ---------------------------------------------------------

@pytest.fixture
def display():
    pygame.init()
    pygame.display.set_mode((1, 1))


def _trough(x=400, y=400):
    return Trough(x=x, y=y, file_name="troughs/trough_empty.png", tiles_to_right=2, tiles_up=1,
                  collision_to_right=2, collision_up=1, tile_size=32, col_margin_right_pixel=-2,
                  col_margin_left_pixel=-3, col_margin_up_pixel=-12, col_margin_down_pixel=-3,
                  name="Trough_Test", house_class="Trough")


def test_every_fill_has_its_picture_on_one_canvas_and_showing_one_swaps_it(display):
    trough = _trough()
    assert len(trough.pictures) == 1 + 2 * ct.LEVELS
    assert {picture.get_size() for picture, _ in trough.pictures.values()} == {(64, 32)}
    empty = trough.image
    trough.show("trough_water_3", True)
    assert trough.image is trough.pictures["trough_water_3"][0] and trough.has_contents
    trough.show("trough_empty", False)
    assert trough.image is empty and not trough.has_contents
    assert trough.hit_box().width > 50


def test_the_chickens_keep_out_of_it_and_peck_in_front_of_one_with_something_in_it(display, monkeypatch):
    trough = _trough()
    hen = Hen(ChickenLook("B", "plume", "barred"), NOW - datetime.timedelta(days=60), 100.0, 1.0)
    chicken = Chicken(pygame.Rect(300, 300, 200, 200), 32, hen, NOW, rng=random.Random(3), troughs=[trough])
    for _ in range(200):
        assert not trough.blocks(*chicken._free_spot())
    left, top, right, bottom = trough.keep_out
    assert not chicken._go_to_trough()                   # nothing in it: no reason to go
    trough.show("trough_feed_2", True)
    monkeypatch.setattr(chicken_module, "TROUGH_CHANCE", 1.0)
    chicken._next()
    x, y = chicken.target
    assert chicken.state == "walk" and left < x < right and bottom < y < bottom + 12
    for _ in range(400):
        chicken.update(0.05, None)
        if chicken.at_trough:
            break
    assert chicken.at_trough and chicken.state == "peck" and chicken.direction == "back"
    feet = chicken.feet
    for _ in range(40):
        chicken.update(0.05, None)
    assert chicken.feet == feet                          # pecking at a trough it does not step on


@pytest.mark.parametrize("start, goal", [
    ((340.0, 380.0), (490.0, 386.0)),     # left of it to right of it, straight through its middle
    ((420.0, 330.0), (430.0, 480.0)),     # above it to below it
    ((350.0, 340.0), (480.0, 470.0)),     # corner to corner, across it
])
def test_a_chicken_walks_round_a_trough_in_its_way_not_through_it(display, start, goal):
    trough = _trough()
    hen = Hen(ChickenLook("B", "plume", "barred"), NOW - datetime.timedelta(days=60), 100.0, 1.0)
    chicken = Chicken(pygame.Rect(300, 300, 200, 200), 32, hen, NOW, rng=random.Random(3), troughs=[trough])
    assert not trough.blocks(*start) and not trough.blocks(*goal) and chicken._crosses(start, goal)
    chicken.place_feet(*start)
    chicken._start("walk")
    chicken.target = goal
    for _ in range(2000):
        chicken.update(0.02, None)
        assert not trough.blocks(*chicken.feet)
        if chicken.state != "walk":
            break
    assert chicken.feet == goal


def test_a_chicken_with_a_clear_way_walks_straight(display):
    trough = _trough()
    hen = Hen(ChickenLook("B", "plume", "barred"), NOW - datetime.timedelta(days=60), 100.0, 1.0)
    chicken = Chicken(pygame.Rect(300, 300, 200, 200), 32, hen, NOW, rng=random.Random(3), troughs=[trough])
    assert chicken._route((310.0, 310.0), (490.0, 320.0)) == []


def test_the_map_has_two_troughs_in_the_chicken_pen_with_their_pictures():
    root = ET.parse(MAP).getroot()
    pen = next(o for o in root.iter("object") if o.get("name") == "Chickens")
    px, py = float(pen.get("x")), float(pen.get("y"))
    pw, ph = float(pen.get("width")), float(pen.get("height"))
    troughs = [o for o in root.iter("object") if o.get("type") == "Trough"]
    assert len(troughs) == 2
    for trough in troughs:
        x, y = float(trough.get("x")), float(trough.get("y"))
        assert px <= x and x + 64 <= px + pw and py <= y - 32 and y <= py + ph
        props = {p.get("name"): p.get("value") for p in trough.iter("property")}
        assert (ROOT / "assets" / "map_sprites" / "houses" / props["File_name"]).exists()
