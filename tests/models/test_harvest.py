"""The harvest's rules (models/harvest.py): its days, the order the plants are cut in, when a shock
stands, the workers' hours and who is picked, the work done unseen, and the save.

No pygame and no map: fields are a few plants' (x, base y), the numbers the tests rely on pinned."""

import datetime

import pytest

from src.models import harvest as harvest_module
from src.models.harvest import (
    FieldHarvest, Harvest, harvest_order, harvest_year, is_harvest_day, pick_workers, shock_thresholds,
    shocks_standing_after_harvest, work_day, worked_minutes,
)
from src.sim.calendar import DAYS_PER_YEAR, EPOCH

# A field of 3 plants a row, 2 rows: the bottom row at base y 64
PLANTS = [(16.0, 32.0), (48.0, 32.0), (80.0, 32.0), (16.0, 64.0), (48.0, 64.0), (80.0, 64.0)]


@pytest.fixture(autouse=True)
def pinned(monkeypatch):
    monkeypatch.setattr(harvest_module, "HARVEST_END_DAY", 21)
    monkeypatch.setattr(harvest_module, "HARVEST_DAYS", 3)
    monkeypatch.setattr(harvest_module, "HARVEST_MINUTES_PER_PLANT", 2.5)
    monkeypatch.setattr(harvest_module, "STEP_MINUTES", 2.0)
    monkeypatch.setattr(harvest_module, "WORK_START_HOURS", (6.0, 6.0))
    monkeypatch.setattr(harvest_module, "WORK_END_HOURS", (17.0, 17.0))
    monkeypatch.setattr(harvest_module, "COMMUTE_HOURS", 3.0)
    monkeypatch.setattr(harvest_module, "SHOCKS_STAND_DAYS", 3)
    monkeypatch.setattr(harvest_module, "CATCH_UP_MINUTES", 30)


def day(number, hour=0.0, year=0):
    """A moment on a day of the calendar's year (0 the 1st of Spring)."""
    return (datetime.datetime.combine(EPOCH, datetime.time())
            + datetime.timedelta(days=number + year * DAYS_PER_YEAR, hours=hour))


# ---------------------------------------------------------------------------
# Its days

def test_the_fields_are_cut_on_the_last_three_days_of_autumn():
    assert [d for d in range(DAYS_PER_YEAR) if is_harvest_day(day(d, 12))] == [18, 19, 20]


def test_the_shocks_stand_three_days_after_it_then_are_gone():
    assert [d for d in range(DAYS_PER_YEAR) if shocks_standing_after_harvest(day(d, 12))] == [21, 22, 23]


# ---------------------------------------------------------------------------
# The order and the shocks

def test_the_plants_are_cut_from_the_bottom_row_up_back_and_forth():
    assert harvest_order(PLANTS) == [3, 4, 5, 2, 1, 0]


def test_a_shock_stands_once_the_plants_under_it_are_cut_the_first_with_the_first_plant():
    order = harvest_order(PLANTS)
    # One over the bottom row's right end, one over the top row's left: the latter is the last cut
    right_bottom = (70.0, 20.0, 90.0, 64.0)   # reaches the plants at x 80 (and, round it, x 48 above)
    top_left = (0.0, 0.0, 20.0, 30.0)         # the plants at x 16 of both rows, by its reach
    thresholds = shock_thresholds(PLANTS, order, [right_bottom, top_left])
    assert thresholds[1] == 6                  # all of its plants are cut only with the last one
    assert thresholds[0] == 1                  # the first shock stands with the first plant


def test_a_shock_off_the_field_waits_for_the_plant_nearest_its_foot():
    order = harvest_order(PLANTS)
    on, off = (0.0, 50.0, 20.0, 66.0), (200.0, 0.0, 220.0, 30.0)   # off: nearest the top row's right end
    assert shock_thresholds(PLANTS, order, [on, off]) == [1, order.index(2) + 1]


# ---------------------------------------------------------------------------
# The workers

def test_a_fields_hours_are_the_same_every_time_and_within_the_day():
    hours = work_day(305, day(18, 3))
    assert hours == work_day(305, day(18, 15))
    assert hours.start == day(18, 6.0) and hours.end == day(18, 17.0)


def test_each_field_gets_its_own_worker_and_not_yesterdays_while_there_are_others():
    people = ["Avice", "Edric", "Godfrey", "Juliana"]
    picked = pick_workers([1, 2], people, day(18), avoid=["Avice", "Edric"])
    assert sorted(picked.values()) == ["Godfrey", "Juliana"]
    assert picked == pick_workers([1, 2], people, day(18), avoid=["Avice", "Edric"])


def test_yesterdays_go_again_only_for_want_of_others_and_some_fields_may_go_without():
    picked = pick_workers([1, 2], ["Avice", "Edric"], day(19), avoid=["Avice"])
    assert sorted(picked.values()) == ["Avice", "Edric"]
    assert len(pick_workers([1, 2, 3], ["Avice"], day(19))) == 1


def test_only_the_hours_after_the_walk_out_on_harvest_days_are_worked():
    # Out at 6, at the field by 9, home at 17: 8 hours a harvest day
    assert worked_minutes(1, day(18, 0), day(19, 0)) == 8 * 60
    assert worked_minutes(1, day(18, 10), day(18, 11)) == 60
    assert worked_minutes(1, day(18, 7), day(18, 8)) == 0
    assert worked_minutes(1, day(17, 0), day(18, 0)) == 0
    assert worked_minutes(1, day(17, 0), day(21, 12)) == 3 * 8 * 60


# ---------------------------------------------------------------------------
# A field's harvest

def test_a_field_is_cut_plant_by_plant_in_its_order_and_this_years_count_only_shows_this_year():
    field = FieldHarvest(5, PLANTS)
    field.start_year(day(18, 9))
    assert [field.cut_next() for _ in range(7)] == [3, 4, 5, 2, 1, 0, None]
    assert field.done and field.share(day(19)) == 1.0
    assert field.cut_at(day(18, year=1)) == 0 and field.cut_plants(day(18, year=1)) == set()
    field.start_year(day(18, year=1))
    assert field.cut == 0 and not field.done


def test_time_worked_unseen_cuts_a_plant_for_each_cut_and_step():
    field = FieldHarvest(5, PLANTS)
    field.start_year(day(18))
    assert field.work(4.0) == 0
    assert field.work(0.5) == 1           # 4.5 minutes: one plant
    assert field.work(100.0) == 5 and field.done


def test_the_harvest_cuts_an_unwatched_field_by_the_clock_and_a_watched_one_only_after_a_jump():
    harvest = Harvest([(1, PLANTS), (2, PLANTS)])
    assert harvest.update(day(18, 9.0)) == [1, 2]                 # a new year's harvest starts
    assert harvest.update(day(18, 9.0 + 4.5 / 60 * 2), live=[2]) == [1]
    assert harvest.fields[1].cut == 2 and harvest.fields[2].cut == 0
    harvest.update(day(18, 11.0), live=[2])                         # a jump: the watched one too
    assert harvest.fields[2].cut > 0


def test_heavy_rain_keeps_the_work_waiting():
    harvest = Harvest([(1, PLANTS)])
    harvest.update(day(18, 9.0))
    harvest.update(day(18, 12.0), heavy_rain=True)
    assert harvest.fields[1].cut == 0
    harvest.update(day(18, 12.25))
    assert harvest.fields[1].cut == 3                              # 15 minutes after the rain


def test_the_save_keeps_how_far_each_field_has_got():
    harvest = Harvest([(1, PLANTS), (2, PLANTS)])
    harvest.update(day(18, 9.0))
    harvest.fields[1].cut = 4
    loaded = Harvest([(1, PLANTS), (2, PLANTS)])
    loaded.load(harvest.to_save())
    assert loaded.fields[1].cut == 4 and loaded.fields[1].year == harvest_year(day(18))
    assert loaded.fields[2].cut == 0
    loaded.load({"fields": {"1": {"year": 0, "cut": 99}}})
    assert loaded.fields[1].cut == len(PLANTS)                     # never more than the field has
    loaded.load(None)                                              # a save from before the harvest
    assert all(field.cut == 0 and field.year is None for field in loaded.fields.values())
