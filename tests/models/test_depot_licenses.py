"""Trading licenses: expiry dates by calendar month, extending, expiring."""

import datetime

import pytest

from src.models.depot import Depot


def date(year, month, day):
    return datetime.datetime(year, month, day, 10, 0)


@pytest.fixture
def unlicensed():
    return Depot(money=0, transaction_cost=2, storage_capacity=100)


@pytest.mark.parametrize("granted, months, expiry", [
    (date(1450, 1, 15), 2, date(1450, 3, 15)),
    (date(1450, 11, 15), 3, date(1451, 2, 15)),     # over the new year
    (date(1450, 1, 31), 1, date(1450, 2, 28)),      # no 31st in February
    (date(1452, 1, 31), 1, date(1452, 2, 29)),      # a leap year
    (date(1450, 3, 31), 12, date(1451, 3, 31)),
])
def test_license_runs_whole_calendar_months(unlicensed, granted, months, expiry):
    unlicensed.add_license("Wood", months, granted)
    assert unlicensed.trading_licenses["Wood"] == expiry


def test_license_valid_until_its_expiry(unlicensed):
    unlicensed.add_license("Wood", 1, date(1450, 3, 1))

    assert unlicensed.has_license("Wood", date(1450, 3, 31))
    assert not unlicensed.has_license("Wood", date(1450, 4, 1))
    assert not unlicensed.has_license("Stone", date(1450, 3, 1))


def test_renewing_an_active_license_extends_it_from_its_expiry(unlicensed):
    unlicensed.add_license("Wood", 2, date(1450, 3, 1))     # to May 1
    unlicensed.add_license("Wood", 2, date(1450, 4, 10))
    assert unlicensed.trading_licenses["Wood"] == date(1450, 7, 1)


def test_renewing_an_expired_license_starts_from_now(unlicensed):
    unlicensed.add_license("Wood", 1, date(1450, 1, 1))     # to Feb 1
    unlicensed.add_license("Wood", 1, date(1450, 4, 10))
    assert unlicensed.trading_licenses["Wood"] == date(1450, 5, 10)


def test_get_licenses_counts_days_left_never_below_zero(unlicensed):
    unlicensed.add_license("Wood", 1, date(1450, 3, 1))     # to Apr 1
    unlicensed.add_license("Stone", 1, date(1450, 1, 1))    # to Feb 1

    by_good = {lic["good"]: lic["days_left"] for lic in unlicensed.get_licenses(date(1450, 3, 22))}

    assert by_good == {"Wood": 10, "Stone": 0}


def test_starting_licenses(unlicensed):
    # STARTING_LICENSES is pinned to Wood for 2 months and Stone for 1 in conftest.py
    unlicensed.init_starting_licenses(date(1450, 3, 1))
    assert unlicensed.trading_licenses == {"Wood": date(1450, 5, 1), "Stone": date(1450, 4, 1)}
