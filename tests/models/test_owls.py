"""Owls in the woods at night: when they call, and where it is quiet."""

import datetime
import random

import pygame
import pytest

from src.models import owls as owls_module
from src.models.owls import Owls


class FakeSound:
    def __init__(self, name):
        self.name = name


class FakeChannel:
    def __init__(self):
        self.played = []
        self.volume = None

    def set_volume(self, left, right=None):
        self.volume = (left, right)

    def play(self, sound):
        self.played.append(sound)


class FakeTrees:
    """As wooded as *cover* everywhere."""

    def __init__(self, cover):
        self.cover = cover

    def at(self, x, y):
        return self.cover


class FakePlayer:
    x = y = width = height = 0


MIDNIGHT = datetime.datetime(1400, 5, 1, 0, 0)
NOON = datetime.datetime(1400, 5, 1, 12, 0)


@pytest.fixture
def channel(monkeypatch):
    channel = FakeChannel()
    monkeypatch.setattr(pygame.mixer, "find_channel", lambda: channel)
    return channel


@pytest.fixture(autouse=True)
def pinned(monkeypatch):
    for name, value in (("OWL_EVERY_HOURS", (2.0, 2.0)), ("OWL_VOLUME", 0.5), ("OWL_LOUDNESS", (1.0, 1.0)),
                        ("OWL_PAN", 0.0), ("FOREST_FULL_COVER", 3.0), ("RAIN_HUSHES_OWLS", 1.0),
                        ("OWLS_BY_HOUR", ((5.0, 1.0), (6.0, 0.0), (20.0, 0.0), (21.0, 1.0)))):
        monkeypatch.setattr(owls_module, name, value)


def make_owls(cover=3.0):
    sounds = {name: FakeSound(name) for name in ("owl_hoot_1", "owl_tawny_2", "cough_man_1")}
    return Owls(sounds, FakeTrees(cover), random.Random(1))


def run_hours(owls, hours, start, running=True, rain=0.0):
    now = start
    for _ in range(int(hours * 60)):
        owls.update(now, running, FakePlayer(), rain)
        now += datetime.timedelta(minutes=1)


def test_calls_are_the_owl_sounds():
    assert [s.name for s in make_owls().calls] == ["owl_hoot_1", "owl_tawny_2"]


def test_deep_in_the_woods_at_night_every_two_hours(channel):
    run_hours(make_owls(), 4.5, MIDNIGHT)
    assert len(channel.played) == 2
    assert channel.volume == (pytest.approx(0.5), pytest.approx(0.5))
    assert channel.played[0] is not channel.played[1]


def test_at_the_edge_of_a_wood_more_seldom(channel):
    run_hours(make_owls(cover=1.5), 4.5, MIDNIGHT)
    assert len(channel.played) == 1


@pytest.mark.parametrize("cover, start, running, rain", [
    (0.0, MIDNIGHT, True, 0.0),    # out in the open
    (3.0, NOON, True, 0.0),        # by day
    (3.0, MIDNIGHT, False, 0.0),   # off the map
    (3.0, MIDNIGHT, True, 1.0),    # in pouring rain
])
def test_quiet(channel, cover, start, running, rain):
    run_hours(make_owls(cover), 4.5, start, running, rain)
    assert channel.played == []
