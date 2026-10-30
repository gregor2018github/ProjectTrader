"""The weather's spells, how its levels glide, and saving it."""

import datetime
import random

import pytest

from src.models import weather as weather_module
from src.models.weather import Weather

SPELLS = {
    "clear": {"rain": 0.0, "clouds": 0.0, "wind": 0.0, "hours": (2.0, 2.0), "next": {"wet": 1.0}},
    "wet":   {"rain": 1.0, "clouds": 1.0, "wind": 0.5, "hours": (3.0, 3.0), "next": {"clear": 1.0}},
}


@pytest.fixture
def weather(monkeypatch):
    monkeypatch.setattr(weather_module, "WEATHER_SPELLS", SPELLS)
    monkeypatch.setattr(weather_module, "WEATHER_GLIDE_PER_HOUR", 0.5)
    monkeypatch.setattr(weather_module, "WEATHER_WIND_TURN_CHANCE", 0.0)
    w = Weather(random.Random(1), kind="clear")
    w.wind_side = 1
    return w


def test_starts_with_its_spells_levels(weather):
    assert (weather.kind, weather.rain, weather.clouds, weather.hours_left) == ("clear", 0.0, 0.0, 2.0)
    assert not weather.is_raining


def test_next_spell_follows_when_one_runs_out(weather):
    weather.advance(1.0)
    assert weather.kind == "clear"
    weather.advance(1.5)
    assert weather.kind == "wet"
    assert weather.hours_left == pytest.approx(2.5)   # the half hour over counts towards it


def test_levels_glide_towards_the_spell(weather):
    weather.force("wet")
    weather.advance(1.0)
    assert weather.rain == pytest.approx(0.5)
    assert weather.wind == pytest.approx(0.5)          # already there, held
    weather.advance(1.0)
    assert weather.rain == pytest.approx(1.0)
    weather.advance(0.5)
    assert weather.rain == pytest.approx(1.0)          # not past it


def test_update_counts_game_time_and_caps_jumps(weather):
    start = datetime.datetime(1400, 5, 1, 12, 0)
    weather.update(start)                              # the first call only notes the date
    assert weather.hours_left == 2.0
    weather.update(start + datetime.timedelta(minutes=30))
    assert weather.hours_left == pytest.approx(1.5)
    weather.force("wet")
    weather.update(start + datetime.timedelta(days=3))  # a jump counts as an hour at most
    assert weather.rain == pytest.approx(0.5)


def test_save_round_trip(weather):
    weather.force("wet")
    weather.advance(1.0)
    saved = weather.to_save()
    other = Weather(random.Random(2), kind="clear")
    other.load(saved)
    assert other.to_save() == saved


def test_load_without_weather_keeps_it(weather):
    before = weather.to_save()
    weather.load(None)
    weather.load({"kind": "hail"})
    assert weather.to_save() == before
