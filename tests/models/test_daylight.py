"""The sun hour: longer days in Summer, shorter in Winter, longer dawns and dusks in Autumn and Winter."""

import datetime

import pytest

from src.models import daylight
from src.models.daylight import sun_hour, summer_share, twilight_stretch
from src.sim.calendar import EPOCH

# Pinned: a dawn an hour earlier and a dusk an hour and a half later at midsummer, and the
# dawns and dusks half again as long where Autumn turns to Winter
DAWN_SHIFT, DUSK_SHIFT, STRETCH = 1.0, 1.5, 0.5


@pytest.fixture(autouse=True)
def pinned(monkeypatch):
    monkeypatch.setattr(daylight, "DAYLIGHT_DAWN_SHIFT_HOURS", DAWN_SHIFT)
    monkeypatch.setattr(daylight, "DAYLIGHT_DUSK_SHIFT_HOURS", DUSK_SHIFT)
    monkeypatch.setattr(daylight, "DAYLIGHT_TWILIGHT_STRETCH", STRETCH)


def at(day: float, hour: float) -> datetime.datetime:
    """`hour` o'clock on the day `day` days after the 1st of Spring (a fraction of a day moves the date only)."""
    return datetime.datetime.combine(EPOCH, datetime.time()) + datetime.timedelta(days=day, hours=hour)


MID_SPRING, MIDSUMMER, MID_AUTUMN, WINTER_STARTS, MIDWINTER = 3, 10, 17, 21, 24


def test_mid_spring_goes_by_the_clock():
    for hour in (1, 5, 7.5, 12, 17.25, 20, 23):
        assert sun_hour(at(MID_SPRING, hour)) == pytest.approx(hour, abs=0.15)


def test_summer_days_are_longer():
    assert sun_hour(at(MIDSUMMER, 7)) == pytest.approx(8.0, abs=0.05)       # full daylight an hour sooner
    assert sun_hour(at(MIDSUMMER, 18.5)) == pytest.approx(17.0, abs=0.05)   # the sun only begins to set
    assert sun_hour(at(MIDSUMMER, 22.5)) == pytest.approx(21.0, abs=0.05)   # night


def test_winter_gets_dark_earlier():
    assert sun_hour(at(MIDWINTER, 8)) < 7.0                  # still dawn at eight
    assert sun_hour(at(MIDWINTER, 16)) > 17.5                # the sun setting at four
    assert sun_hour(at(MIDWINTER, 20.5)) >= 21.0             # night by half past eight


def test_dawns_and_dusks_last_longer_in_autumn_and_winter():
    assert twilight_stretch(at(MID_SPRING, 12)) == 1.0
    assert twilight_stretch(at(MIDSUMMER, 12)) == 1.0
    assert 1.0 < twilight_stretch(at(MID_AUTUMN, 12)) < 1.0 + STRETCH
    assert twilight_stretch(at(WINTER_STARTS, 0)) == pytest.approx(1.0 + STRETCH)
    assert 1.0 < twilight_stretch(at(MIDWINTER, 12)) < 1.0 + STRETCH
    # Where Autumn turns to Winter, the dusk runs from full light (17) to night (21) over 6 hours, not 4
    anchors = dict((s, c) for c, s in daylight._anchors(at(WINTER_STARTS, 0)))
    assert anchors[21.0] - anchors[17.0] == pytest.approx(4 * (1 + STRETCH))
    assert anchors[8.0] - anchors[4.0] == pytest.approx(4 * (1 + STRETCH))


def test_no_jump_when_a_season_turns():
    for day in (7, 14, 21, 28):
        before, after = at(day, 0) - datetime.timedelta(minutes=1), at(day, 0)
        assert abs(summer_share(before) - summer_share(after)) < 0.01
        assert abs(twilight_stretch(before) - twilight_stretch(after)) < 0.01


@pytest.mark.parametrize("day", [0, 3, 10, 17, 21, 24, 27])
def test_the_sun_hour_never_runs_backwards(day):
    hours = [sun_hour(at(day, m / 60)) for m in range(0, 24 * 60, 5)]
    assert all(b >= a for a, b in zip(hours, hours[1:]))
    assert hours[0] == 0.0


TINTS = {"Spring": (255, 255, 255), "Summer": (255, 255, 255), "Autumn": (255, 220, 190), "Winter": (210, 220, 255)}


def test_each_season_has_its_mood_in_its_middle_and_blends_between(monkeypatch):
    monkeypatch.setattr(daylight, "SEASON_LIGHT_TINT", TINTS)
    assert daylight.season_tint(at(MIDSUMMER, 12)) == (255, 255, 255)
    assert daylight.season_tint(at(MID_AUTUMN, 12)) == (255, 220, 190)
    assert daylight.season_tint(at(MIDWINTER, 12)) == (210, 220, 255)
    # Where Autumn turns to Winter, half of each
    assert daylight.season_tint(at(WINTER_STARTS, 0)) == (232, 220, 222)
    # and no jump when a season turns
    before = daylight.season_tint(at(14, 0) - datetime.timedelta(minutes=1))
    after = daylight.season_tint(at(14, 0))
    assert max(abs(x - y) for x, y in zip(before, after)) <= 1
