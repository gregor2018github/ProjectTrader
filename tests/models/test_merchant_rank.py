"""The merchant rank: rising, the grace period before a fall, unlocks kept for good,
reputation from gifts and its seasonal fading, and the save."""

import datetime
import math

import pytest

from src.models import merchant_rank as rank_module
from src.models.depot import Depot
from src.models.merchant_rank import MerchantRank
from src.models.player import Player

# A short ladder the tests are written against, pinned so that rebalancing does not break them
RANKS = (
    # name,   wealth, property, volume, reputation
    ("First",      0,      0,       0,     0),
    ("Second",   100,      0,     100,     5),
    ("Third",   1000,    500,    1000,    20),
)
GRACE_DAYS = 14
SCALE = 100.0
FLOOR = 200.0
DECAY = 0.10
DAY = datetime.date(1450, 3, 1)


@pytest.fixture(autouse=True)
def pinned_ranks(monkeypatch):
    for name, value in (
        ("MERCHANT_RANKS", RANKS),
        ("RANK_GRACE_DAYS", GRACE_DAYS),
        ("RANK_UNLOCKS", {"buy_buildings": "Second"}),
        ("DONATION_REPUTATION_SCALE", SCALE),
        ("DONATION_REPUTATION_WEALTH_FLOOR", FLOOR),
        ("REPUTATION_SEASONAL_DECAY", DECAY),
    ):
        monkeypatch.setattr(rank_module, name, value)


@pytest.fixture
def depot():
    return Depot(money=0, transaction_cost=0, storage_capacity=100)


@pytest.fixture
def player():
    return Player(name="Tester", cost_of_living=0)


@pytest.fixture
def rank(depot, player):
    return MerchantRank(depot, player, goods=[])


def meet_second(depot, player):
    depot.money = 100
    depot.stats.money_spent_goods = 100
    player.reputation = 5


def later(days):
    return DAY + datetime.timedelta(days=days)


# RISING

def test_a_new_merchant_holds_the_first_rank(rank):
    assert rank.rank.name == "First"
    assert rank.daily_check(DAY) is None


def test_rises_once_every_condition_is_met(rank, depot, player):
    meet_second(depot, player)
    player.reputation = 4.9
    assert rank.daily_check(DAY) is None

    player.reputation = 5
    ledger, message = rank.daily_check(DAY)
    assert rank.rank.name == "Second"
    assert "Second" in ledger and "buy buildings" in message


def test_trade_volume_counts_buying_and_selling(rank, depot, player):
    meet_second(depot, player)
    depot.stats.money_spent_goods = 60
    depot.stats.money_received = 40
    rank.daily_check(DAY)
    assert rank.rank.name == "Second"


def test_rises_straight_to_the_highest_rank_met(rank, depot, player):
    depot.money = 500
    depot.properties["warehouses"].append({"buy_price": 500})
    depot.stats.money_received = 1000
    player.reputation = 20
    rank.daily_check(DAY)
    assert rank.rank.name == "Third"
    assert rank.highest == 2


def test_loans_count_against_the_net_wealth(rank, depot, player):
    meet_second(depot, player)
    depot.active_loans.append({"remaining_principal": 50})
    assert rank.daily_check(DAY) is None


# FALLING

def test_falls_back_only_after_the_grace_period(rank, depot, player):
    meet_second(depot, player)
    rank.daily_check(DAY)
    depot.money = 50

    ledger, message = rank.daily_check(later(1))
    assert "slipping" in ledger and "Net wealth" in message
    assert rank.grace_days_left(later(1)) == GRACE_DAYS
    assert rank.daily_check(later(GRACE_DAYS)) is None
    assert rank.rank.name == "Second"

    ledger, _ = rank.daily_check(later(GRACE_DAYS + 1))
    assert rank.rank.name == "First"
    assert "Fallen" in ledger
    assert rank.grace_since is None


def test_putting_it_right_in_time_ends_the_grace_period(rank, depot, player):
    meet_second(depot, player)
    rank.daily_check(DAY)
    depot.money = 50
    rank.daily_check(later(1))

    depot.money = 100
    ledger, message = rank.daily_check(later(5))
    assert "secured" in ledger and message == ""
    assert rank.grace_since is None
    assert rank.daily_check(later(GRACE_DAYS + 5)) is None
    assert rank.rank.name == "Second"


def test_falls_one_rank_at_a_time(rank, depot, player):
    depot.money = 500
    depot.properties["warehouses"].append({"buy_price": 500})
    depot.stats.money_received = 1000
    player.reputation = 20
    rank.daily_check(DAY)
    depot.money, player.reputation = 0, 0     # meets neither Third nor Second now

    rank.daily_check(later(1))
    rank.daily_check(later(1 + GRACE_DAYS))
    assert rank.rank.name == "Second"
    assert rank.grace_since == later(1 + GRACE_DAYS)   # a new grace period for this one

    rank.daily_check(later(1 + 2 * GRACE_DAYS))
    assert rank.rank.name == "First"


def test_unlocks_are_kept_after_a_fall(rank, depot, player):
    assert not rank.has_unlocked("buy_buildings")
    meet_second(depot, player)
    rank.daily_check(DAY)
    player.reputation = 0
    rank.daily_check(later(1))
    rank.daily_check(later(1 + GRACE_DAYS))
    assert rank.rank.name == "First"
    assert rank.has_unlocked("buy_buildings")


def test_rising_again_does_not_announce_an_unlock_twice(rank, depot, player):
    meet_second(depot, player)
    rank.daily_check(DAY)
    player.reputation = 0
    rank.daily_check(later(1))
    rank.daily_check(later(1 + GRACE_DAYS))

    player.reputation = 5
    _, message = rank.daily_check(later(2 + GRACE_DAYS))
    assert "buy buildings" not in message


# REPUTATION

def test_a_gift_is_measured_against_the_wealth_before_it(rank, depot, player):
    depot.money = 1000
    depot.book_donation(100)
    gain = rank.record_gift(100)
    assert gain == pytest.approx(SCALE * math.log1p(100 / 1000))
    assert player.reputation == pytest.approx(gain)


def test_a_small_purse_is_measured_against_the_floor(rank, depot):
    depot.money = 10
    assert rank.reputation_for_gift(10) == pytest.approx(SCALE * math.log1p(10 / FLOOR))


def test_each_coin_given_in_a_season_is_worth_less(rank, depot):
    depot.money = 10_000
    depot.book_donation(100)
    first = rank.record_gift(100)
    depot.book_donation(100)
    second = rank.record_gift(100)
    assert second < first
    # both measured against the 10,000 held before the season's giving
    assert first + second == pytest.approx(SCALE * math.log1p(200 / 10_000))


def test_the_rich_must_give_more_for_the_same_reputation(rank, depot):
    depot.money = 1000
    poor = rank.reputation_for_gift(100)
    depot.money = 100_000
    assert rank.reputation_for_gift(100) < poor / 50


def test_a_new_season_fades_reputation_and_resets_the_gifts(rank, depot, player):
    depot.money = 10_000
    depot.book_donation(100)
    rank.record_gift(100)
    player.reputation = 50
    rank.new_season()
    assert player.reputation == pytest.approx(50 * (1 - DECAY))
    assert rank.given_this_season == 0
    assert rank.reputation_for_gift(100) == pytest.approx(SCALE * math.log1p(100 / depot.money))


# SAVING

def test_save_round_trip(rank, depot, player):
    meet_second(depot, player)
    rank.daily_check(DAY)
    depot.money = 0
    rank.daily_check(later(3))
    rank.given_this_season = 42

    restored = MerchantRank(depot, player, goods=[])
    restored.load(rank.to_save())
    assert (restored.level, restored.highest, restored.grace_since, restored.given_this_season) == \
           (1, 1, later(3), 42)


def test_an_older_save_keeps_its_gifts_of_the_month(rank):
    rank.load({"level": 0, "given_this_month": 42})
    assert rank.given_this_season == 42


def test_a_save_without_a_rank_starts_at_the_first(rank):
    rank.level = rank.highest = 2
    rank.load(None)
    assert (rank.level, rank.highest, rank.grace_since) == (0, 0, None)
