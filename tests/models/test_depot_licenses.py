"""Trading licenses: they run whole seasons of the game calendar, extend and expire."""

import datetime

import pytest

from tests.models.conftest import GOODS

from src.models.depot import Depot

DAYS_PER_SEASON = 7     # pinned in test_game_calendar.py


def date(year, month, day):
    return datetime.datetime(year, month, day, 10, 0)


def later(start, days):
    return start + datetime.timedelta(days=days)


START = date(1450, 3, 1)


@pytest.fixture
def unlicensed():
    return Depot(money=0, transaction_cost=2, storage_capacity=100, goods=GOODS + ("Flour", "Bread"))


@pytest.mark.parametrize("seasons", [1, 2, 4, 12])
def test_license_runs_whole_seasons(unlicensed, seasons):
    unlicensed.add_license("Wood", seasons, START)
    assert unlicensed.trading_licenses["Wood"] == later(START, seasons * DAYS_PER_SEASON)


def test_license_valid_until_its_expiry(unlicensed):
    unlicensed.add_license("Wood", 1, START)

    assert unlicensed.has_license("Wood", later(START, 6))
    assert not unlicensed.has_license("Wood", later(START, 7))
    assert not unlicensed.has_license("Stone", START)


def test_renewing_an_active_license_extends_it_from_its_expiry(unlicensed):
    unlicensed.add_license("Wood", 2, START)                 # to day 14
    unlicensed.add_license("Wood", 2, later(START, 10))
    assert unlicensed.trading_licenses["Wood"] == later(START, 28)


def test_renewing_an_expired_license_starts_from_now(unlicensed):
    unlicensed.add_license("Wood", 1, START)                 # to day 7
    unlicensed.add_license("Wood", 1, later(START, 20))
    assert unlicensed.trading_licenses["Wood"] == later(START, 27)


def test_get_licenses_counts_days_left_never_below_zero(unlicensed):
    unlicensed.add_license("Wood", 2, START)                 # to day 14
    unlicensed.add_license("Stone", 1, START)                # to day 7

    by_good = {lic["good"]: lic["days_left"] for lic in unlicensed.get_licenses(later(START, 10))}

    assert by_good == {"Wood": 4, "Stone": 0}


def test_starting_licenses(unlicensed):
    unlicensed.init_starting_licenses(START, [("Wood", 2), ("Stone", 1)])
    assert unlicensed.trading_licenses == {"Wood": later(START, 14), "Stone": later(START, 7)}


def test_a_guilds_licence_covers_its_whole_chain(unlicensed):
    unlicensed.license_of = {"Flour": "Wheat", "Bread": "Wheat"}
    unlicensed.add_license("Wheat", 1, START)
    assert all(unlicensed.has_license(g, later(START, 1)) for g in ("Wheat", "Flour", "Bread"))
    assert not unlicensed.has_license("Wood", later(START, 1))
    assert unlicensed.license_name("Bread") == "Wheat" and unlicensed.license_name("Wood") == "Wood"
    assert list(unlicensed.trading_licenses) == ["Wheat"]                   # one licence, kept by its name
