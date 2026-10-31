"""A thunderstorm's strikes: when they come, how they flash, and the thunder after them."""

import random

import pygame
import pytest

from src.models import lightning as lightning_module
from src.models.lightning import Lightning


class FakeSound:
    pass


class FakeChannel:
    def __init__(self):
        self.played = []
        self.volume = None
        self.paused = False

    def set_volume(self, volume):
        self.volume = volume

    def play(self, sound):
        self.played.append(sound)

    def get_busy(self):
        return True

    def pause(self):
        self.paused = True

    def unpause(self):
        self.paused = False


@pytest.fixture
def channel(monkeypatch):
    channel = FakeChannel()
    monkeypatch.setattr(pygame.mixer, "find_channel", lambda: channel)
    return channel


@pytest.fixture
def lightning(monkeypatch, channel):
    for name, value in (("LIGHTNING_FROM_STORM", 0.5), ("LIGHTNING_EVERY_S", (10.0, 10.0)),
                        ("LIGHTNING_FLASH_ADD", 100), ("THUNDER_CHANCE", 1.0),
                        ("THUNDER_DELAY_S", (1.0, 1.0)), ("THUNDER_VOLUME", (0.8, 0.8))):
        monkeypatch.setattr(lightning_module, name, value)
    monkeypatch.setattr(lightning_module, "FLICKERS", (((0.0, 0.2, 1.0),),))
    sounds = {"thunder_a": FakeSound(), "thunder_b": FakeSound(), "rain": FakeSound()}
    return Lightning(sounds, random.Random(1))


def test_only_thunder_sounds_are_used(lightning):
    assert len(lightning.thunder) == 2


def test_no_lightning_without_a_storm(lightning, channel):
    for _ in range(100):
        lightning.update(1.0, 0.3, True)
    assert lightning.flash == 0.0 and not channel.played


def test_a_strike_flashes_then_thunders(lightning, channel):
    lightning.strike()
    lightning.update(0.05, 0.0, True)
    assert 0 < lightning.flash <= 1.0 and 0 < lightning.flash_add <= 100
    lightning.update(0.3, 0.0, True)
    assert lightning.flash == 0.0                      # the flicker is over
    assert not channel.played                          # the thunder is still on its way
    lightning.update(1.0, 0.0, True)
    assert len(channel.played) == 1 and channel.volume == pytest.approx(0.8)


def test_strikes_come_in_a_storm_and_thunder_does_not_repeat(lightning, channel):
    for _ in range(200):                               # 40 s at full storm: about four strikes
        lightning.update(0.2, 1.0, True)
    assert len(channel.played) >= 3
    assert all(a is not b for a, b in zip(channel.played, channel.played[1:]))


def test_held_while_not_running(lightning, channel):
    lightning.strike()
    lightning.update(1.5, 0.0, True)                   # the thunder rolls
    lightning.update(0.05, 1.0, False)
    assert channel.paused and lightning.flash == 0.0
    lightning.update(0.05, 0.0, True)
    assert not channel.paused
