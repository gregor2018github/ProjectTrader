"""A homebody keeps to his house: out of his door in the morning, about his yard
all day, now and then a little walk and back, and in again in the evening.

Run on a made-up door, yard and walk with straight-line routes, the sun hour
pinned to the clock and the hours and rests pinned, so nothing hangs on the map,
the season or chance. Also that the townsfolk leave him out, and his profile.
"""

import datetime
import os
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from src.models.figurines.humans.npcs import homebody as homebody_module
from src.models.figurines.humans.npcs.homebody import (
    GOING_HOME, GOING_IN, IN_YARD, INDOORS, LINGERING, ON_WALK, STEPPING_OUT, TO_YARD, WALKING_BACK,
    Homebody, discover_homebodies,
)
from src.models.figurines.humans.npcs.townsperson import discover_townsfolk
from src.models.figurines.patrol_path import PatrolPath

TILE = 32
DAY = datetime.datetime(1500, 1, 4)
FRAME = 1 / 30
# Pinned so the test does not hang on the windows' spread
OUT_AT, IN_AT = 7.0, 19.0
PROFILE = {"name": "Testric", "gender": "male", "home": "Shed", "stand_in": "trader_woodcutter",
           "introduces": "woodhacking"}


@pytest.fixture(autouse=True)
def pinned(monkeypatch):
    pygame.display.init()
    pygame.display.set_mode((1, 1))
    monkeypatch.setattr(homebody_module, "sun_hour", lambda t: t.hour + t.minute / 60.0)
    monkeypatch.setattr(homebody_module, "OUT_WINDOW", (OUT_AT, OUT_AT))
    monkeypatch.setattr(homebody_module, "IN_WINDOW", (IN_AT, IN_AT))
    monkeypatch.setattr(homebody_module, "WALK_CHANCE", 0.0)


def straight(start, goal):
    return [start, goal]


def door():
    return SimpleNamespace(id=7, entry=(100.0, 100.0), step=(100.0, 110.0),
                           facing_in="back", facing_out="front")


def homebody(walks=((100.0, 300.0),), yard=True):
    person = Homebody("commons_testric", PROFILE, TILE)
    path = PatrolPath([(60.0, 140.0), (140.0, 140.0), (140.0, 180.0), (60.0, 180.0)], closed=True) if yard else None
    person.settle(door(), path, list(walks), straight)
    return person


def run(person, start, minutes, frames_per_minute=12, until=None):
    """Update him from `start` for `minutes` of game time, at a few frames a game minute."""
    now = start
    step = datetime.timedelta(minutes=1) / frames_per_minute
    for _ in range(minutes * frames_per_minute):
        person.update(FRAME, now)
        if until is not None and until(person):
            break
        now += step
    return now


def test_the_townsfolk_leave_a_homebody_out_and_his_profile_makes_him_one():
    homebodies = discover_homebodies(TILE)
    osric = next(h for h in homebodies if h.folder == "commons_osric")
    assert osric.home_name == "Wood Chopper" and osric.introduces == "woodhacking"
    assert osric.tiled_prefix == "Osric" and osric.SOCIAL_CLASS == "Commons" and osric.GENDER == "male"
    assert "commons_osric" not in {person.SPRITE_FOLDER for person in discover_townsfolk(TILE)}


def test_without_sprites_of_his_own_he_borrows_the_stand_ins():
    person = Homebody("commons_testric", PROFILE, TILE)
    assert (person.SPRITE_FOLDER, person.SPRITE_PREFIX) == ("trader_woodcutter", "woodcutter")


def test_at_night_he_is_indoors_and_out_of_sight():
    person = homebody()
    run(person, DAY.replace(hour=3), 30)
    assert person.state == INDOORS and person.is_hidden


def test_in_the_morning_he_steps_out_of_his_door_and_comes_out_to_the_yard():
    person = homebody()
    now = run(person, DAY.replace(hour=6, minute=50), 9)
    assert person.state == INDOORS
    now = run(person, now, 2, until=lambda p: p.state == STEPPING_OUT)
    assert person.state == STEPPING_OUT and person.feet == pytest.approx(door().entry)
    run(person, now, 20, until=lambda p: p.state == IN_YARD)
    assert person.state == IN_YARD and not person.is_hidden
    assert person.path is person.yard


def test_by_day_he_stays_about_his_yard():
    person = homebody(walks=())
    run(person, DAY.replace(hour=10), 3)          # unseen till now: put straight in the yard
    xs, ys = [], []
    now = DAY.replace(hour=10, minute=3)
    for _ in range(6 * 60):
        person.update(FRAME, now)
        xs.append(person.feet[0]); ys.append(person.feet[1])
        now += datetime.timedelta(seconds=30)      # catch-up gaps never reached
        assert person.state == IN_YARD
    assert 60 - 1 <= min(xs) and max(xs) <= 140 + 1 and 140 - 1 <= min(ys) and max(ys) <= 180 + 1
    assert max(xs) - min(xs) > 10 or max(ys) - min(ys) > 10   # he moved about, not stood all day


def test_in_the_evening_he_goes_home_and_in_by_his_door():
    person = homebody()
    now = run(person, DAY.replace(hour=18, minute=30), 29)
    assert person.state == IN_YARD
    now = run(person, now, 60, until=lambda p: p.state == GOING_IN)
    assert person.state == GOING_IN and person.feet == pytest.approx(door().entry)
    run(person, now, 2, frames_per_minute=60, until=lambda p: p.state == INDOORS)   # the fade is real seconds
    assert person.state == INDOORS and person.is_hidden


def test_now_and_then_he_walks_out_lingers_and_comes_back(monkeypatch):
    monkeypatch.setattr(homebody_module, "WALK_CHANCE", 1.0)
    person = homebody(walks=[(100.0, 300.0)])
    now = run(person, DAY.replace(hour=9), 2 * 60, until=lambda p: p.state == ON_WALK)
    assert person.state == ON_WALK
    now = run(person, now, 2 * 60, until=lambda p: p.state == LINGERING)
    assert person.feet == pytest.approx((100.0, 300.0))
    now = run(person, now, 2 * 60, until=lambda p: p.state == WALKING_BACK)
    run(person, now, 2 * 60, until=lambda p: p.state == IN_YARD)
    assert person.state == IN_YARD and person.last_walk_end is not None


def test_a_walk_waits_its_gap_after_the_last(monkeypatch):
    monkeypatch.setattr(homebody_module, "WALK_CHANCE", 1.0)
    person = homebody()
    now = DAY.replace(hour=12)
    person.last_walk_end = now - datetime.timedelta(minutes=homebody_module.WALK_GAP_MINUTES - 1)
    assert not person._wants_walk(now)
    assert person._wants_walk(now + datetime.timedelta(minutes=1))


def test_evening_on_a_walk_turns_him_back_home(monkeypatch):
    monkeypatch.setattr(homebody_module, "WALK_CHANCE", 1.0)
    person = homebody()
    now = run(person, DAY.replace(hour=12), 4 * 60, until=lambda p: p.state == LINGERING)
    assert person.state == LINGERING                 # out at the far end of his walk
    person.in_at = now.hour + now.minute / 60.0      # his evening comes while he is out
    now = run(person, now, 1)
    assert person.state == WALKING_BACK
    run(person, now, 3 * 60, until=lambda p: p.state == INDOORS)
    assert person.state == INDOORS


def test_time_run_on_unseen_puts_him_where_his_day_has_got_to():
    person = homebody()
    run(person, DAY.replace(hour=12), 1)
    assert person.state == IN_YARD and not person.is_hidden
    run(person, DAY.replace(hour=23), 1)
    assert person.state == INDOORS and person.is_hidden


def test_without_a_yard_he_stands_on_his_doorstep():
    person = homebody(yard=False)
    run(person, DAY.replace(hour=12), 10)
    assert person.state == IN_YARD and person.feet == pytest.approx(door().step)


def test_a_word_holds_him_where_he_is():
    person = homebody()
    now = run(person, DAY.replace(hour=18, minute=59), 1)
    person.talking_to = SimpleNamespace(x=0.0, y=0.0, width=10, height=10)
    run(person, now, 30)                           # his hour to go in comes and goes
    assert person.state == IN_YARD
    person.talking_to = None
    run(person, now + datetime.timedelta(minutes=30), 1)
    assert person.state != IN_YARD                 # and then he is off home
