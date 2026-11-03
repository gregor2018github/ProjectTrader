"""A field's crop going round its stages, its plants changing one by one, and saving it."""

import datetime
import random

import pytest

from src.models import crop_growth as crop_growth_module
from src.models.crop_growth import CropGrowth

STAGES = ["bare", "sprouts", "young", "ripe"]
START = datetime.datetime(1450, 3, 1, 10, 0)


def days(n: float) -> datetime.timedelta:
    return datetime.timedelta(days=n)


@pytest.fixture
def growth(monkeypatch):
    """Stages of exactly 10 days, a new game's start day taken as it is."""
    monkeypatch.setattr(crop_growth_module, "FIELD_STAGE_VARIATION", 0.0)
    monkeypatch.setattr(crop_growth_module, "FIELD_START_JITTER_DAYS", 0.0)
    return CropGrowth(STAGES, stage_days=10.0, rng=random.Random(1))


def test_starts_where_told(growth):
    growth.start(START, "young", day=3.0)
    assert growth.stage == "young"
    assert growth.since == START - days(3)
    assert growth.ends == START + days(7)


def test_unknown_start_stage_is_the_bare_field(growth):
    growth.start(START, "turnips")
    assert (growth.stage, growth.since) == ("bare", START)


def test_moves_on_when_a_stage_runs_out(growth):
    growth.start(START, "bare", day=5.0)
    assert not growth.update(START + days(4.9))
    assert growth.update(START + days(5))
    assert growth.stage == "sprouts"
    assert growth.since == START + days(5)   # the next stage starts where the last ended, not when looked at


def test_ripe_is_harvested_back_to_bare(growth):
    growth.start(START, "ripe")
    growth.update(START + days(10))
    assert growth.stage == "bare"


def test_a_long_jump_goes_through_every_stage_on_the_way(growth):
    growth.start(START, "bare")
    growth.update(START + days(55))   # once round the four stages (40 days), then half into sprouts
    assert growth.stage == "sprouts"
    assert growth.since == START + days(50)


def test_plants_ahead_and_behind_show_the_neighbouring_stages(growth):
    growth.start(START, "young")
    near_end = START + days(9.5)
    assert growth.plant_stage(near_end, 0.0) == STAGES.index("young")
    assert growth.plant_stage(near_end, 0.8) == STAGES.index("ripe")      # already turned
    just_after_start = START + days(0.5)
    assert growth.plant_stage(just_after_start, -0.8) == STAGES.index("sprouts")   # not yet turned


def test_plants_behind_the_harvest_still_stand_ripe(growth):
    growth.start(START, "bare")
    assert growth.plant_stage(START + days(0.2), -0.5) == STAGES.index("ripe")


def test_stage_lengths_and_start_vary_within_their_bounds(monkeypatch):
    monkeypatch.setattr(crop_growth_module, "FIELD_STAGE_VARIATION", 0.2)
    monkeypatch.setattr(crop_growth_module, "FIELD_START_JITTER_DAYS", 2.0)
    for seed in range(20):
        growth = CropGrowth(STAGES, stage_days=10.0, rng=random.Random(seed))
        growth.start(START, "bare", day=5.0)
        assert 8.0 <= growth.days <= 12.0
        assert START - days(7) <= growth.since <= START - days(3)


def test_start_never_goes_before_the_stage_began(monkeypatch):
    monkeypatch.setattr(crop_growth_module, "FIELD_STAGE_VARIATION", 0.0)
    monkeypatch.setattr(crop_growth_module, "FIELD_START_JITTER_DAYS", 2.0)
    for seed in range(20):
        growth = CropGrowth(STAGES, stage_days=10.0, rng=random.Random(seed))
        growth.start(START, "ripe", day=0.0)
        assert growth.since <= START
        assert growth.stage == "ripe"


def test_saved_and_loaded(growth):
    growth.start(START, "sprouts", day=2.0)
    saved = growth.to_save()
    other = CropGrowth(STAGES, stage_days=10.0)
    assert other.load(saved, START)
    assert (other.stage, other.since, other.days) == ("sprouts", growth.since, growth.days)


def test_loading_catches_up_with_the_time_since(growth):
    growth.start(START, "sprouts")
    other = CropGrowth(STAGES, stage_days=10.0, rng=random.Random(2))
    other.load(growth.to_save(), START + days(10))
    assert other.stage == "young"


@pytest.mark.parametrize("saved", [None, {}, {"stage": "turnips", "since": START.isoformat(), "days": 10},
                                   {"stage": "young", "since": "yesterday", "days": 10}])
def test_a_missing_or_unfitting_save_is_refused(growth, saved):
    growth.start(START, "young")
    before = growth.to_save()
    assert not growth.load(saved, START)
    assert growth.to_save() == before


def test_needs_stages():
    with pytest.raises(ValueError):
        CropGrowth([])
