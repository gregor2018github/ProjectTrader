"""The chicken pen's keeper: out nearly every day, he walks to a trough that has run dry, fills it with his
own water or grain and goes back to his round; unseen he fills them at once (npcs/pen_keeper.py, and
chicken_troughs.Troughs.keeper_kind / keeper_fill). Also Edric's profile and his yard on the map.

Run on a made-up door, yard and troughs with straight-line routes and the sun hour pinned to the clock,
as the homebody's tests are.
"""

import datetime
import json
import os
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from src.models.chicken_troughs import FEED, WATER, Troughs
from src.models.figurines.humans.npcs import homebody as homebody_module
from src.models.figurines.humans.npcs import pen_keeper as keeper_module
from src.models.figurines.humans.npcs.homebody import IN_YARD, INDOORS, LINGERING, discover_homebodies
from src.models.figurines.humans.npcs.pen_keeper import PenKeeper
from src.models.figurines.humans.npcs.townsperson import discover_townsfolk
from src.models.figurines.patrol_path import PatrolPath

ROOT = Path(__file__).resolve().parents[2]
TILE = 32
FRAME = 1 / 30
PROFILE = {"name": "Testric", "gender": "male", "home": "Shed", "keeps": "chicken_pen",
           "stand_in": "commons_edric"}


@pytest.fixture(autouse=True)
def pinned(monkeypatch):
    pygame.display.init()
    pygame.display.set_mode((1, 1))
    monkeypatch.setattr(homebody_module, "sun_hour", lambda t: t.hour + t.minute / 60.0)
    monkeypatch.setattr(homebody_module, "OUT_WINDOW", (7.0, 7.0))
    monkeypatch.setattr(homebody_module, "IN_WINDOW", (19.0, 19.0))
    monkeypatch.setattr(homebody_module, "IDLE_MIN_MINUTES", 5)
    monkeypatch.setattr(homebody_module, "IDLE_MAX_MINUTES", 5)
    monkeypatch.setattr(keeper_module, "DAY_OFF_CHANCE", 0.12)
    monkeypatch.setattr(keeper_module, "FILL_MINUTES", (5.0, 5.0))


def _trough(name, spot, fills):
    return SimpleNamespace(name=name, keeper_spot=lambda: spot, keeper_fills=fills)


def _keeper(pen):
    door = SimpleNamespace(id=7, entry=(100.0, 100.0), step=(100.0, 110.0), facing_in="back", facing_out="front")
    keeper = PenKeeper("commons_testric", PROFILE, TILE)
    yard = PatrolPath([(60.0, 140.0), (340.0, 140.0), (340.0, 300.0), (60.0, 300.0)], closed=True)
    keeper.settle(door, yard, [], lambda a, b: [a, b])
    keeper.tend([_trough("Feed", (200.0, 220.0), FEED), _trough("Water", (300.0, 220.0), WATER)])
    told = []
    keeper.look_after(pen, lambda: told.append(True))
    return keeper, told


def _work_day(keeper, start=datetime.datetime(1500, 1, 4)):
    day = start
    while keeper.day_off(day.date()):
        day += datetime.timedelta(days=1)
    return day


def _run(keeper, now, minutes, until=None, frames_per_minute=12):
    step = datetime.timedelta(minutes=1) / frames_per_minute
    for _ in range(minutes * frames_per_minute):
        keeper.update(FRAME, now)
        if until is not None and until(keeper):
            break
        now += step
    return now


# -- the rules ----------------------------------------------------------------------

def test_he_fills_an_empty_trough_with_what_no_trough_holds_else_its_own():
    pen = Troughs(["Feed", "Water"])
    assert pen.empty_ones() == ["Feed", "Water"]
    assert pen.keeper_kind("Feed", FEED) == FEED and pen.keeper_kind("Water", WATER) == WATER
    pen.pour_water("Feed")                                 # the player put water in his feed trough
    assert pen.keeper_kind("Water", WATER) == FEED         # so the other gets the grain
    assert pen.keeper_fill("Water", WATER) == FEED and pen["Water"].full
    assert pen.keeper_fill("Water", WATER) is None         # not empty: he leaves it
    assert pen.empty_ones() == []


def test_he_is_out_nearly_every_day_and_a_day_off_stays_one():
    keeper, _ = _keeper(Troughs())
    days = [datetime.date(1500, 1, 1) + datetime.timedelta(days=n) for n in range(400)]
    off = [day for day in days if keeper.day_off(day)]
    assert 0.06 < len(off) / len(days) < 0.2
    assert all(keeper.day_off(day) for day in off)
    noon = datetime.datetime.combine(off[0], datetime.time(12))
    assert not keeper.is_out_time(noon)
    _run(keeper, noon, 5)
    assert keeper.state == INDOORS


# -- on the map -----------------------------------------------------------------------

def test_he_walks_to_an_empty_trough_fills_it_facing_it_and_goes_back_to_his_round():
    pen = Troughs(["Feed", "Water"])
    pen.pour_water("Water")
    keeper, told = _keeper(pen)
    now = _work_day(keeper).replace(hour=10)
    now = _run(keeper, now, 2)                             # unseen till now: in the yard, and the feed filled
    assert keeper.state == IN_YARD and pen["Feed"].kind == FEED and told
    pen.tip_out("Water")
    told.clear()
    now = _run(keeper, now, 300, until=lambda k: k.chore is not None)
    assert keeper.chore.name == "Water"
    now = _run(keeper, now, 300, until=lambda k: k.state == LINGERING)
    assert keeper.feet == pytest.approx((300.0, 220.0), abs=1.5)
    assert pen["Water"].kind == WATER and pen["Water"].full and told
    keeper.update(FRAME, now)
    assert keeper.animator.current_direction == "back"
    _run(keeper, now, 300, until=lambda k: k.state == IN_YARD)
    assert keeper.state == IN_YARD and keeper.chore is None


def test_unseen_he_fills_every_empty_trough_at_once_but_only_while_at_work():
    pen = Troughs(["Feed", "Water"])
    keeper, told = _keeper(pen)
    day = _work_day(keeper)
    assert not keeper.see_to_unseen(day.replace(hour=3))  # in bed
    assert pen.empty_ones() == ["Feed", "Water"]
    assert keeper.see_to_unseen(day.replace(hour=12))
    assert (pen["Feed"].kind, pen["Water"].kind) == (FEED, WATER) and len(told) == 2
    keeper.update(FRAME, day.replace(hour=12, minute=1))   # on the map from now on
    pen.tip_out("Feed")
    keeper.update(FRAME, day.replace(hour=12, minute=2))   # watched: he walks there himself
    assert not keeper.see_to_unseen(day.replace(hour=12, minute=3))
    assert pen["Feed"].empty


def test_edric_keeps_the_pen_from_house_19_and_his_yard_lies_inside_it():
    profile = json.loads((ROOT / "assets/map_sprites/figurines/humans/npcs/commons_edric/npc.json").read_text())
    assert profile["home"] == "House_19" and profile["keeps"] == "chicken_pen"
    edric = next(h for h in discover_homebodies(TILE) if h.folder == "commons_edric")
    assert isinstance(edric, PenKeeper) and edric.tiled_prefix == "Edric"
    assert "commons_edric" not in {person.SPRITE_FOLDER for person in discover_townsfolk(TILE)}
    root = ET.parse(ROOT / "assets/tiles/Map1.tmx").getroot()
    objects = {o.get("name"): o for o in root.iter("object")}
    pen, yard = objects["Chickens"], objects["Edric_Yard"]
    left, top = float(pen.get("x")), float(pen.get("y"))
    right, bottom = left + float(pen.get("width")), top + float(pen.get("height"))
    ox, oy = float(yard.get("x")), float(yard.get("y"))
    for point in yard.find("polygon").get("points").split():
        x, y = (float(v) for v in point.split(","))
        assert left < ox + x < right and top < oy + y < bottom
    fills = {o.get("name"): {p.get("name"): p.get("value") for p in o.iter("property")}.get("Keeper_fills")
             for o in root.iter("object") if o.get("type") == "Trough"}
    assert sorted(fills.values()) == [FEED, WATER]
