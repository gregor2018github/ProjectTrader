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
    weather.clouds = 1.0                               # already overcast: the rain need not wait
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
    weather.clouds = 1.0
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


def test_ground_wets_in_rain_and_dries_after(weather, monkeypatch):
    monkeypatch.setattr(weather_module, "PUDDLE_FILL_PER_HOUR", 0.5)
    monkeypatch.setattr(weather_module, "PUDDLE_DRY_PER_HOUR", 0.2)
    weather.force("wet")
    weather.hours_left = 99
    weather.rain, weather.clouds = 1.0, 1.0           # already pouring
    weather.advance(1.0)
    assert weather.wetness == pytest.approx(0.5)
    weather.advance(4.0)
    assert weather.wetness == 1.0                      # soaked, no wetter
    weather.rain = 0.0
    weather.force("clear")
    weather.hours_left = 99
    weather.advance(1.0)                               # the clouds go from 1.0 at 0.5 an hour: dries at 0.2 * (1 - 0.5 * 0.5)
    assert weather.wetness == pytest.approx(1.0 - 0.2 * 0.75)


@pytest.fixture
def foggy(weather, monkeypatch):
    spells = dict(SPELLS, fog={"rain": 0.0, "clouds": 0.0, "wind": 0.0, "fog": 1.0, "hours": (9.0, 9.0),
                               "next": {"clear": 1.0}})
    monkeypatch.setattr(weather_module, "WEATHER_SPELLS", spells)
    monkeypatch.setattr(weather_module, "FOG_GLIDE_PER_HOUR", 0.25)
    monkeypatch.setattr(weather_module, "FOG_FROM_WETNESS", 0.4)
    monkeypatch.setattr(weather_module, "FOG_BY_HOUR", ((0.0, 1.0), (12.0, 0.5), (24.0, 1.0)))
    return weather


def test_fog_share_follows_the_hour(foggy):
    assert weather_module.fog_share_at(0.0) == 1.0
    assert weather_module.fog_share_at(12.0) == 0.5
    assert weather_module.fog_share_at(6.0) == pytest.approx(0.75)   # halfway, eased
    assert weather_module.fog_share_at(30.0) == pytest.approx(0.75)  # past midnight wraps round


def test_fog_rolls_in_slowly(foggy):
    foggy.force("fog")
    foggy.advance(1.0)
    assert foggy.fog == pytest.approx(0.25)
    foggy.advance(4.0)
    assert foggy.fog == 1.0                            # no thicker than the spell's


def test_fog_thins_with_the_hour(foggy):
    foggy.force("fog")
    foggy.fog = 1.0
    foggy.update(datetime.datetime(1400, 5, 1, 12, 0))   # notes the hour: noon allows half
    assert foggy.fog_target() == pytest.approx(0.5)
    foggy.update(datetime.datetime(1400, 5, 1, 13, 0))
    assert foggy.fog < 1.0


def test_wet_ground_breathes_fog_once_the_rain_stops(foggy):
    foggy.wetness = 1.0
    assert foggy.fog_target() == pytest.approx(0.4)
    foggy.rain = 1.0
    assert foggy.fog_target() == 0.0                   # not while it rains


def test_old_save_without_fog_loads_clear(weather):
    saved = weather.to_save()
    del saved["fog"]
    weather.fog = 0.7
    weather.load(saved)
    assert weather.fog == 0.0


def test_rain_waits_for_its_clouds(weather, monkeypatch):
    monkeypatch.setattr(weather_module, "RAIN_FROM_CLOUDS", 0.4)
    weather.force("wet")
    weather.advance(0.5)                               # clouds 0.25: too few to rain from
    assert weather.clouds == pytest.approx(0.25)
    assert weather.rain == 0.0
    weather.advance(0.5)                               # clouds 0.5: a sixth of the way from 0.4 to 1.0
    assert weather.rain_ceiling() == pytest.approx(1.0 / 6)
    assert weather.rain == pytest.approx(1.0 / 6)
    weather.advance(1.0)                               # clouds there, rain following
    assert weather.clouds == 1.0
    assert weather.rain == pytest.approx(1.0 / 6 + 0.5)


def test_forced_spell_develops_and_lasts_until_it_has(foggy):
    foggy.force("fog")
    assert foggy.fog == 0.0                            # nothing jumps
    assert foggy.hours_left >= 1.0 / 0.25 + 9.0        # four hours to thicken, then its own nine
    foggy.force("wet")
    assert foggy.rain == 0.0 and foggy.clouds == 0.0
    assert foggy.hours_left >= (1.0 + 1.0) / 0.5 + 3.0


def test_held_weather_stays_and_ignores_the_hour(foggy):
    foggy.force("fog")
    foggy.held = True
    foggy.update(datetime.datetime(1400, 5, 1, 12, 0))
    assert foggy.fog_target() == 1.0                   # noon would allow only half
    foggy.advance(50.0)
    assert foggy.kind == "fog"                         # its 9 hours never run out


def test_spell_with_a_median_length_is_mostly_short(weather, monkeypatch):
    spells = dict(SPELLS, long={"rain": 1.0, "clouds": 1.0, "wind": 0.0, "hours": (3.0, 24.0, 5.0),
                                "next": {"clear": 1.0}})
    monkeypatch.setattr(weather_module, "WEATHER_SPELLS", spells)
    lengths = []
    for _ in range(400):
        weather.force("long")
        weather.hours_left = 0.0                       # forget force()'s minimum, draw anew
        weather._start_spell("long")
        lengths.append(weather.hours_left)
    assert 3.0 <= min(lengths) and max(lengths) <= 24.0
    assert 160 <= sum(1 for h in lengths if h < 5.0) <= 240     # about half under the median
    assert 0 < sum(1 for h in lengths if h > 15.0) < 100       # the long ones there, but seldom


def test_new_game_starts_partway_through_its_spell(monkeypatch):
    monkeypatch.setattr(weather_module, "WEATHER_SPELLS", SPELLS)
    w = Weather(random.Random(4), kind="clear", partway=True)
    assert 0.0 <= w.hours_left < 2.0


def test_storm_level_glides_in_and_out(weather, monkeypatch):
    spells = dict(SPELLS, storm={"rain": 1.0, "clouds": 1.0, "wind": 0.5, "storm": 1.0,
                                 "hours": (3.0, 3.0), "next": {"clear": 1.0}})
    monkeypatch.setattr(weather_module, "WEATHER_SPELLS", spells)
    weather.force("storm")
    weather.advance(1.0)
    assert weather.storm == pytest.approx(0.5)
    weather.force("clear")                             # a spell without a storm level calms it
    weather.advance(1.0)
    assert weather.storm == pytest.approx(0.0)
