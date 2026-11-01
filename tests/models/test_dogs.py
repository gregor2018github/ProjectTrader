"""Dogs barking in town: how often, where it is quiet, and the bouts of single barks."""

import datetime
import random

import pygame
import pytest

from src.models import dogs as dogs_module
from src.models.dogs import Dogs


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


class FakeTown:
    """As much town as *cover* everywhere."""

    def __init__(self, cover):
        self.cover = cover

    def at(self, x, y):
        return self.cover


class FakePlayer:
    x = y = width = height = 0


MORNING = datetime.datetime(1400, 5, 1, 6, 0)
NIGHT = datetime.datetime(1400, 5, 1, 22, 0)


@pytest.fixture
def channel(monkeypatch):
    channel = FakeChannel()
    monkeypatch.setattr(pygame.mixer, "find_channel", lambda: channel)
    return channel


@pytest.fixture(autouse=True)
def pinned(monkeypatch):
    for name, value in (("DOG_EVERY_HOURS", (4.0, 4.0)), ("DOG_VOLUME", 0.5), ("DOG_LOUDNESS", (1.0, 1.0)),
                        ("DOG_PAN", 0.0), ("DOG_BOUT_BARKS", (3, 3)), ("DOG_BOUT_GAP_S", (0.5, 0.5)),
                        ("DOG_CHORUS_HOURS", (21, 5)), ("DOG_CHORUS_CHANCE", 1.0), ("TOWN_FULL_COVER", 2.0)):
        monkeypatch.setattr(dogs_module, name, value)


def make_dogs(cover=2.0, names=("dog_bark_far_1", "dog_bark_far_2", "dog_bark_distant_1",
                                "dog_bark_distant_2", "dogs_far_village_night", "door_1")):
    return Dogs({name: FakeSound(name) for name in names}, FakeTown(cover), random.Random(1))


def run_hours(dogs, hours, start, running=True):
    """Update every game minute for *hours*, a tenth of a real second each."""
    now = start
    for _ in range(int(hours * 60)):
        dogs.update(0.1, now, running, FakePlayer())
        now += datetime.timedelta(minutes=1)


def test_sounds_are_sorted_by_kind():
    dogs = make_dogs()
    assert [s.name for s in dogs.far] == ["dog_bark_far_1", "dog_bark_far_2"]
    assert [s.name for s in dogs.single] == ["dog_bark_distant_1", "dog_bark_distant_2"]
    assert dogs.chorus.name == "dogs_far_village_night"


def test_in_town_one_bark_per_interval(channel):
    run_hours(make_dogs(names=("dog_bark_far_1", "dog_bark_far_2")), 9, MORNING)
    assert len(channel.played) == 2
    assert channel.volume == (pytest.approx(0.5), pytest.approx(0.5))


def test_at_the_edge_of_town_more_seldom(channel):
    run_hours(make_dogs(cover=1.0, names=("dog_bark_far_1",)), 9, MORNING)
    assert len(channel.played) == 1


@pytest.mark.parametrize("cover, running", [(0.0, True), (2.0, False)])
def test_quiet_in_the_country_and_off_the_map(channel, cover, running):
    run_hours(make_dogs(cover), 9, MORNING, running)
    assert channel.played == []


def test_a_bout_of_single_barks(channel):
    run_hours(make_dogs(names=("dog_bark_distant_1", "dog_bark_distant_2")), 4.5, MORNING)
    names = [s.name for s in channel.played]
    assert len(names) == 3
    assert all(a != b for a, b in zip(names, names[1:]))


def test_the_village_chorus_only_at_night(channel):
    run_hours(make_dogs(names=("dog_bark_far_1", "dogs_far_village_night")), 4.1, MORNING)
    run_hours(make_dogs(names=("dog_bark_far_1", "dogs_far_village_night")), 4.1, NIGHT)
    assert [s.name for s in channel.played] == ["dog_bark_far_1", "dogs_far_village_night"]
