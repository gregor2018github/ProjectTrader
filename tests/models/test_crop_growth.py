"""A field's crop following the seasons, its plants changing one by one, and its furrows."""

import datetime

import pytest

from src.models import crop_growth as crop_growth_module
from src.models.crop_growth import CropGrowth, field_season
from src.models.game_calendar import EPOCH

# Pinned: a 28-day year (game_calendar.py), five stages, sown on the 1st of Spring and
# harvested at the end of Autumn, so each of the four growing stages lasts 21 / 4 days
STAGES = ["bare", "sprouts", "young", "growing", "ripe"]
SOW, HARVEST = 0.0, 21.0
SHARE = 21.0 / 4
YEAR = 28


def day(n: float) -> datetime.datetime:
    """n days after the 1st of Spring 1500, at midnight."""
    return datetime.datetime.combine(EPOCH, datetime.time()) + datetime.timedelta(days=n)


@pytest.fixture
def growth():
    return CropGrowth(STAGES, SOW, HARVEST)


@pytest.mark.parametrize("n, stage", [
    (0.0, "sprouts"),          # sown on the 1st of Spring
    (SHARE - 0.01, "sprouts"),
    (SHARE, "young"),
    (2 * SHARE + 0.5, "growing"),
    (3 * SHARE + 0.5, "ripe"),
    (20.9, "ripe"),            # the last of Autumn
    (21.0, "bare"),            # harvested: Winter lies bare
    (27.9, "bare"),
    (28.0, "sprouts"),         # sown again the next Spring
    (YEAR * 30 + 8, "young"),  # and so every year
    (-3.0, "bare"),            # the Winter before the first day
])
def test_the_stage_follows_the_calendar(growth, n, stage):
    growth.update(day(n))
    assert growth.stage == stage


def test_a_stage_knows_when_it_began_and_ends(growth):
    growth.update(day(6))
    assert (growth.since, growth.ends) == (day(SHARE), day(2 * SHARE))
    growth.update(day(24))
    assert (growth.since, growth.ends) == (day(21), day(28))
    assert growth.days == pytest.approx(7)


def test_update_says_when_the_stage_changed(growth):
    assert growth.update(day(1))            # from the unset start to sprouts
    assert not growth.update(day(2))
    assert growth.update(day(SHARE + 0.1))


def test_a_long_jump_lands_on_the_season(growth):
    growth.update(day(2))
    growth.update(day(YEAR * 3 + 22))
    assert growth.stage == "bare"


def test_plants_ahead_and_behind_show_the_neighbouring_stages(growth):
    now = day(SHARE - 0.5)       # half a day before the young stage
    growth.update(now)
    assert STAGES[growth.plant_stage(now, 1.0)] == "young"
    assert STAGES[growth.plant_stage(now, -1.0)] == "sprouts"
    assert STAGES[growth.plant_stage(day(20.5), 1.0)] == "bare"      # already harvested
    assert STAGES[growth.plant_stage(day(21.5), -1.0)] == "ripe"     # still standing


def test_a_field_may_be_sown_late_and_harvested_early():
    growth = CropGrowth(STAGES, sow_day=7.0, harvest_day=15.0)     # Summer only, two days a stage
    for n, stage in ((6.9, "bare"), (7.0, "sprouts"), (9.0, "young"), (14.9, "ripe"), (15.0, "bare")):
        growth.update(day(n))
        assert growth.stage == stage, n


def test_a_harvest_past_the_new_year_runs_on_into_it():
    growth = CropGrowth(STAGES, sow_day=21.0, harvest_day=7.0)     # Winter and Spring
    growth.update(day(YEAR + 6))
    assert growth.stage == "ripe"
    growth.update(day(YEAR + 8))
    assert growth.stage == "bare"


def test_needs_stages():
    with pytest.raises(ValueError):
        CropGrowth([])


# A FIELD'S SEASON

def test_each_field_keeps_its_own_season_within_the_jitter(monkeypatch):
    monkeypatch.setattr(crop_growth_module, "FIELD_SOW_DAY", 0.0)
    monkeypatch.setattr(crop_growth_module, "FIELD_HARVEST_DAY", 21.0)
    monkeypatch.setattr(crop_growth_module, "FIELD_SEASON_JITTER_DAYS", 1.0)
    seasons = [field_season(field_id) for field_id in range(20)]
    assert all(-1 <= sow <= 1 and 20 <= harvest <= 22 for sow, harvest in seasons)
    assert len(set(seasons)) == 20
    assert field_season(7) == field_season(7)     # the same every game


def test_tiled_properties_set_the_season():
    assert field_season(7, {"Sow_day": 3, "Harvest_day": "18.5"}) == (3.0, 18.5)


# FURROWS

def test_furrows_show_fully_while_bare(growth):
    assert growth.furrows(day(24), fade_days=2.0) == 1.0


def test_furrows_wear_away_over_the_sprouting_stage(growth):
    assert growth.furrows(day(0), 2.0) == pytest.approx(1.0)
    assert growth.furrows(day(SHARE / 2), 2.0) == pytest.approx(0.5)
    assert growth.furrows(day(SHARE - 0.01), 2.0) == pytest.approx(0.01 / SHARE)


def test_no_furrows_under_the_grown_crop(growth):
    assert growth.furrows(day(12), 2.0) == 0.0


def test_furrows_come_back_around_the_harvest(growth):
    assert growth.furrows(day(19.5), 2.0) == 0.0
    assert growth.furrows(day(21), 2.0) == pytest.approx(0.5)   # the harvest itself, half way
    assert growth.furrows(day(21.5), 2.0) == pytest.approx(0.75)
    assert growth.furrows(day(22), 2.0) == pytest.approx(1.0)
