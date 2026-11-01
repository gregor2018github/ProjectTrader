"""Someone in town coughing: how often, who, in which voice and how loud."""

import datetime
import random

import pygame
import pytest

from src.models import coughs as coughs_module
from src.models.coughs import Coughs


class FakeSound:
    def __init__(self, name):
        self.name = name


class FakeChannel:
    def __init__(self):
        self.played = []
        self.volume = None

    def set_volume(self, volume):
        self.volume = volume

    def play(self, sound):
        self.played.append(sound)


class FakeFigure:
    def __init__(self, x, gender="male", hidden=False):
        self.x, self.y = x, 0.0
        self.width = self.height = self.sprite_width = self.sprite_height = 0
        self.GENDER = gender
        self.is_hidden = hidden


START = datetime.datetime(1400, 5, 1, 8, 0)


@pytest.fixture
def channel(monkeypatch):
    channel = FakeChannel()
    monkeypatch.setattr(pygame.mixer, "find_channel", lambda: channel)
    return channel


@pytest.fixture
def coughs(monkeypatch, channel):
    for name, value in (("COUGH_EVERY_HOURS", (10.0, 10.0)), ("COUGH_RETRY_HOURS", 0.5),
                        ("COUGH_VOLUME", 0.5), ("COUGH_MAX_DISTANCE", 100.0), ("COUGH_FALLOFF", 1.0)):
        monkeypatch.setattr(coughs_module, name, value)
    sounds = {name: FakeSound(name) for name in ("cough_man_1", "cough_man_2", "cough_woman_1", "door_1")}
    return Coughs(sounds, random.Random(1))


def run_hours(coughs, hours, npcs, player, running=True, start=START):
    """Update every game minute for *hours*; returns the time reached."""
    now = start
    for _ in range(int(hours * 60)):
        coughs.update(now, running, npcs, player)
        now += datetime.timedelta(minutes=1)
    return now


def test_voices_are_picked_by_name(coughs):
    assert [s.name for s in coughs.voices["male"]] == ["cough_man_1", "cough_man_2"]
    assert [s.name for s in coughs.voices["female"]] == ["cough_woman_1"]


def test_one_cough_per_interval_of_map_time(coughs, channel):
    player = FakeFigure(0)
    run_hours(coughs, 25, [FakeFigure(10)], player)
    assert len(channel.played) == 2


def test_time_off_the_map_does_not_count(coughs, channel):
    player = FakeFigure(0)
    run_hours(coughs, 30, [FakeFigure(10)], player, running=False)
    assert channel.played == []


def test_a_jump_in_time_does_not_count(coughs, channel):
    player, npcs = FakeFigure(0), [FakeFigure(10)]
    coughs.update(START, True, npcs, player)
    coughs.update(START + datetime.timedelta(hours=30), True, npcs, player)
    assert channel.played == []


def test_only_someone_near_and_outdoors_coughs(coughs, channel):
    player = FakeFigure(0)
    npcs = [FakeFigure(150), FakeFigure(20, hidden=True)]
    now = run_hours(coughs, 11, npcs, player)
    assert channel.played == []
    # Retried every half hour: once someone comes near, they cough soon
    npcs.append(FakeFigure(50, gender="female"))
    run_hours(coughs, 0.6, npcs, player, start=now)
    assert [s.name for s in channel.played] == ["cough_woman_1"]
    assert channel.volume == pytest.approx(0.25)


def test_never_the_same_recording_twice_running(coughs, channel):
    player, npcs = FakeFigure(0), [FakeFigure(0)]
    for _ in range(6):
        coughs.cough(npcs, player)
    names = [s.name for s in channel.played]
    assert all(a != b for a, b in zip(names, names[1:]))
