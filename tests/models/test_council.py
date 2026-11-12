"""The town council: who may stand, favour and what wins it, the purse and the delay,
the session's vote, the price of winning (grudges, feuds, the seat voted on again),
what an office gives, the data file and the save."""

import datetime
import json
import os
from types import SimpleNamespace

import pytest

from tests.models.conftest import GOODS

from src.config.constants import COUNCIL_DATA_PATH, DATA_PATH
from src.models import council as council_module
from src.models.council import (
    Council, DELAYED, GIFT_CATEGORY, Office, PLAYER, favour_word, load_definitions, session_moment,
)
from src.models.depot import Depot
from src.models.merchant_rank import rank_index
from src.models.player import Player
from src.ui.heraldry import CHARGES

# The numbers the tests are written against, pinned so that rebalancing does not break them
PINNED = {
    "COUNCIL_SESSION_DAY": 4, "COUNCIL_SESSION_HOUR": 10, "COUNCIL_TERM_SEASONS": 4,
    "COUNCIL_TIER_RANKS": {1: "Chapman", 2: "Merchant", 3: "Burgher"},
    "COUNCIL_FILING_FEE": {1: 40, 2: 300, 3: 1500},
    "NOTABLE_MEANS": {1: 100, 2: 200, 3: 400}, "NOTABLE_MEANS_WEALTH_SHARE": 0.0,
    "FAVOUR_GIFT_SCALE": 20.0, "FAVOUR_GIFT_CEILING": 40.0, "LIKED_GOOD_WORTH": 1.5,
    "FAVOUR_PER_REPUTATION": 0.25, "FAVOUR_BASELINE_CAP": 15.0, "FAVOUR_PER_OFFICE_TIER": 5.0,
    "FAVOUR_DRIFT": 0.5,
    "BANQUET_MEANS": 0.25, "BANQUET_FAVOUR": 6.0,
    "PURSE_MEANS": 3.0, "PURSE_PLEDGE": 30.0, "PURSES_PER_ELECTION": 2,
    "PURSE_REFUSED_FAVOUR": 10.0, "PURSE_REFUSED_REPUTATION": 1.0,
    "PURSE_TALK_CHANCE": 0.0, "PURSE_SCANDAL_REPUTATION": 3.0, "PURSE_SCANDAL_FAVOUR": 6.0,
    "DELAY_MEANS": 2.5, "DELAY_SUCCESS": 1.0, "DELAY_FOUND": 0.0, "DELAY_GRUDGE": 40.0,
    "DELAY_REPUTATION": 3.0, "DELAY_FAVOUR": 5.0,
    "ABSENCE_CHANCE": 0.0, "VOTE_NOISE": 0.0, "NOTABLE_AFFINITY": (20.0, 20.0), "INCUMBENT_BONUS": 10.0,
    "LEANING_MARGIN": 10.0,
    "FEUD_OUSTED": 45.0, "FEUD_RIVAL": 25.0, "FEUD_ACTS_FROM": 30.0, "GRUDGE_FADE": 8.0,
    "FEUD_FINE_SHARE": 0.04, "FEUD_FINE_CAP": {1: 60, 2: 250, 3: 800},
    "FEUD_SLANDER_REPUTATION": 2.0, "FEUD_WHISPER_FAVOUR": 4.0, "AMENDS_MEANS": 4.0,
    "CHALLENGE_CHANCE": 0.0, "NPC_CHALLENGE_CHANCE": 0.0, "THIRD_CANDIDATE_CHANCE": 0.0,
}
CHAPMAN, MERCHANT, BURGHER = (rank_index(name) for name in ("Chapman", "Merchant", "Burgher"))
START = datetime.datetime(1500, 1, 1, 8)            # the calendar's first day: session 0 sits on its 4th day
ARMS = {"field": [10, 20, 30], "charge": "pale", "metal": "gold"}


def office(key, tier, **privileges):
    return Office(key=key, name=key.title(), tier=tier, stipend=privileges.pop("stipend", 5), duty="", **privileges)


def notable(key, seat=None, integrity=0.5, likes="Wine"):
    return {"key": key, "name": key.title(), "trade": "merchant", "office": seat, "likes": likes,
            "integrity": integrity, "arms": ARMS}


def definitions():
    """A small council: a head, two seats under it, two under those, and two notables without one."""
    offices = [office("head", 3, fee_discount=0.5, licence_discount=0.3, standing=6, feud_shield=1.0),
               office("upper_a", 2, stipend=20, licence_discount=0.3), office("upper_b", 2),
               office("lower_a", 1, stipend=6, fee_discount=0.25, standing=1), office("lower_b", 1)]
    notables = [notable("hugh", "head"), notable("una", "upper_a", integrity=1.0), notable("ulf", "upper_b", integrity=0.0),
                notable("lena", "lower_a"), notable("lars", "lower_b"), notable("sven"), notable("siri")]
    return offices, notables


@pytest.fixture(autouse=True)
def pinned(monkeypatch):
    for name, value in PINNED.items():
        monkeypatch.setattr(council_module, name, value)


@pytest.fixture
def depot():
    return Depot(money=10_000, fee_rate=0.02, storage_capacity=100, goods=GOODS)


@pytest.fixture
def player():
    return Player(name="Tester", cost_of_living=0)


@pytest.fixture
def rank():
    return SimpleNamespace(level=CHAPMAN)


@pytest.fixture
def goods():
    return [SimpleNamespace(name="Wine", get_price=lambda: 10.0)]


@pytest.fixture
def council(depot, player, rank, goods):
    made = Council(depot, player, rank, goods, seed=1, definitions=definitions())
    made.logged = []
    made.on_log = made.logged.append
    return made


def session_day(session=0):
    return session_moment(session)


def win_over(council, *keys, favour=40.0):
    for key in keys:
        council.notables[key].favour = favour


class TestStanding:
    def test_a_seat_asks_for_its_rank(self, council, rank):
        rank.level = CHAPMAN - 1
        assert not council.can_stand("lower_a").ok
        rank.level = CHAPMAN
        assert council.can_stand("lower_a").ok

    def test_only_one_tier_above_the_one_held(self, council, rank):
        rank.level = BURGHER
        assert council.can_stand("lower_a").ok
        assert not council.can_stand("upper_a").ok
        council.seats["lower_a"].holder = PLAYER
        assert council.can_stand("upper_a").ok
        assert not council.can_stand("head").ok

    def test_the_fee_is_paid_and_the_holder_is_the_rival(self, council, depot):
        assert council.stand("lower_a", START).ok
        assert depot.money == 10_000 - 40
        assert council.candidacy.candidates == [PLAYER, "lena"]
        assert council.candidacy.session == 0

    def test_without_the_fee_no_name_goes_down(self, council, depot):
        depot.money = 39
        assert not council.stand("lower_a", START).ok
        assert council.candidacy is None

    def test_one_name_at_a_time(self, council):
        council.stand("lower_a", START)
        assert not council.can_stand("lower_b").ok

    def test_the_list_closes_as_the_session_day_begins(self, council):
        eve = session_day().replace(hour=0) - datetime.timedelta(minutes=1)
        assert council.session_open_for(eve) == 0
        assert council.session_open_for(session_day().replace(hour=0)) == 1

    def test_withdrawing_keeps_the_fee(self, council, depot):
        council.stand("lower_a", START)
        assert council.withdraw().ok
        assert council.candidacy is None and depot.money == 10_000 - 40

    def test_those_who_vote_are_the_seats_tier_and_the_one_above(self, council):
        assert council.electorate("lower_a", [PLAYER, "lena"]) == ["una", "ulf", "lars"]
        assert council.electorate("upper_a", [PLAYER, "una"]) == ["hugh", "ulf"]
        assert council.electorate("head", [PLAYER, "hugh"]) == ["una", "ulf", "lena", "lars"]


class TestFavour:
    def test_reputation_and_office_are_everyones_regard(self, council, player):
        player.reputation = 40
        assert council.effective_favour("una") == 10.0
        player.reputation = 400
        assert council.effective_favour("una") == 15.0
        council.seats["lower_a"].holder = PLAYER
        assert council.effective_favour("una") == 20.0

    def test_each_coin_wins_less_than_the_last(self, council, depot):
        first = council.gift_gain("lena", 100)
        council.gift_money("lena", 100)
        second = council.gift_gain("lena", 100)
        assert first == pytest.approx(20 * 0.6931, abs=0.01)
        assert 0 < second < first
        assert depot.money == 9_900
        assert depot.donations[GIFT_CATEGORY] == 100

    def test_gifts_stop_at_their_ceiling(self, council):
        council.gift_money("lena", 5_000)
        assert council.notables["lena"].favour == 40.0
        assert council.gift_gain("lena", 5_000) == 0.0

    def test_a_higher_office_expects_more(self, council):
        assert council.gift_gain("hugh", 100) < council.gift_gain("una", 100) < council.gift_gain("lena", 100)
        assert council.means("sven") == council.means("lena")

    def test_the_rich_must_give_more(self, council, depot, monkeypatch):
        monkeypatch.setattr(council_module, "NOTABLE_MEANS_WEALTH_SHARE", 0.02)
        assert council.means("lena") == 200.0
        depot.money = 100_000
        assert council.means("lena") == 2_000.0

    def test_a_gift_one_cannot_pay_for_is_not_made(self, council, depot):
        depot.money = 10
        assert not council.gift_money("lena", 100).ok
        assert council.notables["lena"].favour == 0.0

    def test_the_good_he_is_fond_of_counts_for_more(self, council, depot):
        depot.good_stock["Wine"] = 10
        depot.starting_slots[0].update(good="Wine", quantity=10)
        expected = council.gift_gain("lena", 10 * 10.0 * 1.5)
        assert council.gift_goods("lena", 10).ok
        assert council.notables["lena"].favour == pytest.approx(expected)
        assert depot.good_stock["Wine"] == 0 and depot.money == 10_000

    def test_goods_one_has_not_are_not_sent(self, council):
        assert not council.gift_goods("lena", 10).ok

    def test_a_fair_lot_of_his_good_is_worth_his_means(self, council):
        assert council.liked_lot("lena") == round(100 / 1.5 / 10.0)

    def test_what_courting_won_fades_each_season(self, council):
        win_over(council, "lena")
        council.notables["lena"].gifts = 100
        council.new_season(START + datetime.timedelta(days=7))
        assert council.notables["lena"].favour == 20.0
        assert council.notables["lena"].gifts == 0.0

    def test_favour_has_words(self):
        assert favour_word(70) == "A friend" and favour_word(0) == "Indifferent" and favour_word(-80) == "Hostile"


class TestBanquet:
    def test_it_wins_every_guest_once_a_season(self, council, depot):
        assert council.host_banquet(START).ok
        assert depot.money == 10_000 - 0.25 * (400 + 2 * 200 + 4 * 100)
        assert all(n.favour == 6.0 for n in council.notables.values())
        assert not council.host_banquet(START + datetime.timedelta(days=2)).ok
        assert council.host_banquet(START + datetime.timedelta(days=7)).ok

    def test_those_at_feud_stay_away(self, council, depot):
        council.notables["sven"].grudge = 50
        council.host_banquet(START)
        assert council.notables["sven"].favour == 0.0
        assert depot.money == 10_000 - 0.25 * (400 + 2 * 200 + 3 * 100)


class TestPurseAndDelay:
    def test_the_upright_refuse_and_talk(self, council, depot, player):
        council.stand("lower_a", START)
        money = depot.money
        assert not council.offer_purse("una").ok
        assert council.candidacy.purses == {"una": False}
        assert depot.money == money
        assert council.notables["una"].favour == -10.0 and player.reputation == -1.0

    def test_the_venal_take_it_and_lean_over(self, council, depot):
        council.stand("lower_a", START)
        money = depot.money
        assert council.leaning("ulf")[0] == "lena"
        assert council.offer_purse("ulf").ok
        assert depot.money == money - 3 * 200
        assert council.leaning("ulf") == (None, 0.0)       # 0 + 30 against 20 + 10

    def test_nobody_at_feud_takes_a_purse(self, council):
        council.stand("lower_a", START)
        council.notables["ulf"].grudge = 5
        assert not council.offer_purse("ulf").ok

    def test_only_so_many_purses_and_one_try_each(self, council):
        council.stand("lower_a", START)
        council.offer_purse("ulf")
        assert not council.can_offer_purse("ulf").ok
        council.offer_purse("una")
        assert not council.can_offer_purse("lars").ok

    def test_only_a_voter_can_be_bought_or_delayed(self, council):
        assert not council.can_offer_purse("ulf").ok        # no election
        council.stand("lower_a", START)
        assert not council.can_offer_purse("hugh").ok       # the head has no vote on the lowest seats
        assert not council.can_arrange_delay("lena").ok     # the rival does not vote

    def test_one_voter_may_be_delayed(self, council, depot):
        council.stand("lower_a", START)
        money = depot.money
        assert council.arrange_delay("una").ok
        assert depot.money == money - 2.5 * 200
        assert not council.can_arrange_delay("ulf").ok


class TestSession:
    def test_it_sits_once_at_its_hour(self, council):
        assert council.update(session_day() - datetime.timedelta(minutes=1)) is None
        assert council.update(session_day()) is not None
        assert council.update(session_day() + datetime.timedelta(hours=1)) is None
        assert council.update(session_day(1)) is not None

    def test_a_session_without_the_player_is_not_theirs(self, council):
        assert not council.update(session_day()).concerns_player

    def test_the_favoured_win_the_seat(self, council):
        council.stand("lower_a", START)
        win_over(council, "una", "ulf")
        report = council.update(session_day())
        result = report.results[0]
        assert report.concerns_player and result.winner == PLAYER
        assert result.tally() == {PLAYER: 2, "lena": 1}
        assert council.player_office.key == "lower_a"
        assert council.seats["lower_a"].since == 0
        assert council.candidacy is None
        assert "lena" in council.seatless()

    def test_whoever_is_voted_out_bears_a_grudge(self, council):
        council.stand("lower_a", START)
        win_over(council, "una", "ulf")
        council.update(session_day())
        assert council.notables["lena"].grudge == 45.0
        assert council.in_feud("lena")

    def test_without_favour_the_holder_keeps_the_seat(self, council):
        council.stand("lower_a", START)
        result = council.update(session_day()).results[0]
        assert result.winner == "lena" and result.tally()[PLAYER] == 0
        assert council.player_office is None and council.notables["lena"].grudge == 0.0

    def test_a_tie_leaves_the_seat_with_its_holder(self, council, monkeypatch):
        council.stand("lower_a", START)
        win_over(council, "una")
        council.candidacy.delayed = "lars"
        result = council.update(session_day()).results[0]
        assert result.tally() == {PLAYER: 1, "lena": 1}
        assert result.winner == "lena"

    def test_whoever_is_kept_away_does_not_vote(self, council):
        council.stand("lower_a", START)
        win_over(council, "una", "ulf")
        council.arrange_delay("lars")
        result = council.update(session_day()).results[0]
        vote = next(v for v in result.votes if v.voter == "lars")
        assert vote.choice is None and vote.reason == DELAYED
        assert result.tally() == {PLAYER: 2, "lena": 0}

    def test_a_delay_may_fail_and_be_traced(self, council, player, monkeypatch):
        monkeypatch.setattr(council_module, "DELAY_SUCCESS", 0.0)
        monkeypatch.setattr(council_module, "DELAY_FOUND", 1.0)
        council.stand("lower_a", START)
        council.arrange_delay("lars")
        result = council.update(session_day()).results[0]
        assert next(v for v in result.votes if v.voter == "lars").choice == "lena"
        assert council.notables["lars"].grudge == 40.0
        assert player.reputation == -3.0
        assert council.notables["una"].favour == -5.0
        assert result.notes

    def test_a_purse_talked_of_is_no_pledge(self, council, player, monkeypatch):
        monkeypatch.setattr(council_module, "PURSE_TALK_CHANCE", 1.0)
        council.stand("lower_a", START)
        council.offer_purse("ulf")
        win_over(council, "ulf", favour=5.0)                 # 5 + 30 would win him over, 5 does not
        result = council.update(session_day()).results[0]
        assert next(v for v in result.votes if v.voter == "ulf").choice == "lena"
        assert player.reputation == -3.0
        assert council.notables["una"].favour == -6.0

    def test_a_lost_rank_strikes_the_name(self, council, rank):
        council.stand("lower_a", START)
        win_over(council, "una", "ulf", "lars")
        rank.level = CHAPMAN - 1
        result = council.update(session_day()).results[0]
        assert result.forfeited and result.winner == "lena" and council.player_office is None

    def test_rising_leaves_the_old_seat_to_another(self, council, rank):
        rank.level = MERCHANT
        council.seats["lower_a"].holder = PLAYER
        council.stand("upper_a", START)
        win_over(council, "hugh", "ulf")
        council.update(session_day())
        assert council.player_office.key == "upper_a"
        assert council.seats["lower_a"].holder in ("sven", "siri", "lena")
        assert council.seats["lower_a"].holder != "una"      # the one voted out is not handed it

    def test_the_minutes_keep_what_was_decided(self, council):
        council.stand("lower_a", START)
        council.update(session_day())
        assert council.minutes == ["Lower_A: Lena keeps the seat (You 0, Lena 3)"]
        assert council.logged[-1] == council.minutes[-1]

    def test_the_council_goes_about_its_own_business(self, council, monkeypatch):
        monkeypatch.setattr(council_module, "NPC_CHALLENGE_CHANCE", 1.0)
        assert council.update(session_day()).results == []      # no term is over yet
        result = council.update(session_day(1)).results[0]
        assert not result.concerns_player
        assert len(result.candidates) == 2 and result.candidates[1] in ("sven", "siri")
        assert council.seats[result.office].holder == result.winner
        assert council.seats[result.office].since == 1


class TestTheSeatAgain:
    def seat(self, council):
        council.seats["lower_a"] = council_module.Seat(PLAYER, 0)

    def test_after_its_term_the_seat_is_voted_on(self, council):
        self.seat(council)
        assert council.new_season(START + datetime.timedelta(days=7 * 3)) == []
        notices = council.new_season(START + datetime.timedelta(days=7 * 4))
        assert council.candidacy.defending and council.candidacy.candidates == [PLAYER]
        assert len(notices) == 1 and "term" in notices[0]

    def test_unopposed_it_is_kept(self, council):
        self.seat(council)
        result = council.update(session_day(4)).results[0]
        assert result.winner == PLAYER and not result.votes
        assert council.seats["lower_a"].since == 4

    def test_whoever_has_a_feud_stands_against_the_holder(self, council):
        self.seat(council)
        council.notables["siri"].grudge = 60
        council.new_season(START + datetime.timedelta(days=7 * 4))
        assert council.candidacy.candidates == [PLAYER, "siri"]

    def test_the_holder_is_a_little_ahead(self, council):
        self.seat(council)
        council.notables["siri"].grudge = 60
        win_over(council, "una", "ulf", "lars", favour=15.0)     # 15 + 10 for holding it, against 20
        result = council.update(session_day(4)).results[0]
        assert result.winner == PLAYER
        assert council.notables["siri"].grudge == 60 + 25

    def test_a_defence_lost_loses_the_seat(self, council):
        self.seat(council)
        council.notables["siri"].grudge = 60
        result = council.update(session_day(4)).results[0]
        assert result.winner == "siri" and council.player_office is None
        assert council.seats["lower_a"].holder == "siri"

    def test_without_the_rank_the_seat_is_forfeit(self, council, rank):
        self.seat(council)
        rank.level = 0
        result = council.update(session_day(4)).results[0]
        assert result.forfeited and council.player_office is None
        assert council.seats["lower_a"].holder in ("sven", "siri")

    def test_laying_it_down_hands_it_on(self, council):
        self.seat(council)
        assert council.resign().ok
        assert council.player_office is None and council.seats["lower_a"].holder in ("sven", "siri")


class TestFeuds:
    def season(self, n=1):
        return START + datetime.timedelta(days=7 * n)

    def test_a_deep_grudge_strikes_every_season(self, council, depot, player):
        council.notables["sven"].grudge = 108          # 100 once the season's fading is off: certain
        notices = council.new_season(self.season())
        assert len(notices) == 1 and "Sven" in notices[0]
        hurt = (depot.money < 10_000 or player.reputation < 0
                or all(n.favour == -4.0 for k, n in council.notables.items() if k != "sven"))
        assert hurt

    def test_an_inspection_is_capped(self, council, depot):
        council.notables["sven"].grudge = 108
        for n in range(1, 30):
            council.notables["sven"].grudge = 108
            council.new_season(self.season(n))
        assert depot.money >= 10_000 - 29 * 60

    def test_a_small_grudge_does_nothing(self, council):
        council.notables["sven"].grudge = 30
        assert council.new_season(self.season()) == []
        assert council.notables["sven"].grudge == 22

    def test_grudges_fade(self, council):
        council.notables["sven"].grudge = 5
        council.new_season(self.season())
        assert council.notables["sven"].grudge == 0.0

    def test_an_office_may_ward_the_blows_off(self, council, depot, player):
        council.seats["head"].holder = PLAYER
        council.notables["sven"].grudge = 108
        reputation = player.reputation
        assert council.new_season(self.season()) == []
        assert depot.money == 10_000 and player.reputation == reputation + 6      # only the office's standing

    def test_a_grudge_is_held_against_the_favour(self, council):
        win_over(council, "sven", favour=30.0)
        council.notables["sven"].grudge = 45
        assert council.effective_favour("sven") == -15.0

    def test_amends_end_it(self, council, depot):
        council.notables["sven"].grudge = 80
        assert council.amends_cost("sven") == 4 * 100 * 2
        assert council.make_amends("sven").ok
        assert council.notables["sven"].grudge == 0.0 and depot.money == 10_000 - 800
        assert not council.make_amends("sven").ok


class TestOffice:
    def test_no_office_gives_nothing(self, council):
        assert council.daily_stipend() == 0 and council.fee_discount() == 0 and council.licence_discount() == 0

    def test_an_office_pays_and_spares(self, council):
        council.seats["lower_a"].holder = PLAYER
        assert council.daily_stipend() == 6 and council.fee_discount() == 0.25
        council.seats["lower_a"].holder = "lena"
        council.seats["upper_a"].holder = PLAYER
        assert council.daily_stipend() == 20 and council.licence_discount() == 0.3

    def test_it_brings_reputation_each_season(self, council, player):
        council.seats["lower_a"].holder = PLAYER
        council.new_season(START + datetime.timedelta(days=7))
        assert player.reputation == 1.0

    def test_the_depot_pays_the_lower_fee(self, depot):
        assert depot.trading_fee(1_000) == pytest.approx(20.0)
        depot.fee_discount = 0.25
        assert depot.trading_fee(1_000) == pytest.approx(15.0)
        assert depot.effective_fee_rate == pytest.approx(0.015)

    def test_privileges_read_as_lines(self):
        made = office("x", 1, stipend=6, fee_discount=0.25, standing=1)
        assert made.privileges() == ["6 coins a day", "Market fee -25%", "Reputation +1 a season"]


class TestSameGameSameCouncil:
    def play(self, depot, player, rank, goods, seed, monkeypatch):
        for name, value in (("VOTE_NOISE", 8.0), ("ABSENCE_CHANCE", 0.2), ("NOTABLE_AFFINITY", (0.0, 30.0)),
                            ("NPC_CHALLENGE_CHANCE", 0.5), ("THIRD_CANDIDATE_CHANCE", 0.5)):
            monkeypatch.setattr(council_module, name, value)
        made = Council(depot, player, rank, goods, seed=seed, definitions=definitions())
        made.stand("lower_a", START)
        win_over(made, "una", favour=25.0)
        for session in range(6):
            made.new_season(START + datetime.timedelta(days=7 * session))
            made.update(session_day(session))
        return made.to_save()

    def test_the_same_seed_plays_out_the_same(self, depot, player, rank, goods, monkeypatch):
        first = self.play(depot, player, rank, goods, 7, monkeypatch)
        again = self.play(Depot(money=10_000, fee_rate=0.02, storage_capacity=100, goods=GOODS),
                          Player(name="Tester", cost_of_living=0), rank, goods, 7, monkeypatch)
        assert first == again

    def test_no_notable_ever_sits_twice(self, depot, player, rank, goods, monkeypatch):
        saved = self.play(depot, player, rank, goods, 3, monkeypatch)
        holders = [seat["holder"] for seat in saved["seats"].values() if seat["holder"]]
        assert len(holders) == len(set(holders))


class TestSave:
    def test_it_survives_a_save(self, council, depot, player, rank, goods):
        council.stand("lower_a", START)
        council.offer_purse("ulf")
        council.arrange_delay("lars")
        council.gift_money("una", 100)
        council.notables["sven"].grudge = 33
        council.host_banquet(START)
        council.minutes.append("Something was decided")
        saved = json.loads(json.dumps(council.to_save()))
        loaded = Council(depot, player, rank, goods, seed=99, definitions=definitions())
        loaded.load(saved, START)
        assert loaded.to_save() == council.to_save()
        assert loaded.seed == 1

    def test_a_save_from_before_the_council_starts_with_the_towns(self, council):
        council.seats["lower_a"].holder = PLAYER
        late = session_day(5) + datetime.timedelta(hours=3)
        council.load(None, late)
        assert council.seats["lower_a"].holder == "lena"
        assert council.last_session == 5                      # this season's session has been
        assert council.update(late) is None
        council.load(None, session_day(5) - datetime.timedelta(hours=3))
        assert council.last_session == 4

    def test_loading_puts_away_what_was(self, council):
        fresh = Council(council.depot, council.player, council.merchant_rank, council.goods, seed=1,
                        definitions=definitions()).to_save()
        council.stand("lower_a", START)
        win_over(council, "una", "ulf")
        council.update(session_day())
        council.load(fresh, START)
        assert council.player_office is None and council.notables["lena"].grudge == 0.0
        assert council.minutes == []

    def test_a_notable_gone_from_the_data_leaves_the_seat_empty(self, council):
        saved = council.to_save()
        saved["seats"]["lower_a"]["holder"] = "nobody_known"
        council.load(saved, START)
        assert council.seats["lower_a"].holder is None
        assert council.can_stand("lower_a").ok


class TestDataFile:
    def test_it_loads_into_a_council(self, depot, player, rank, goods):
        made = Council(depot, player, rank, goods)
        assert made.top_tier == 3
        assert sum(1 for o in made.offices.values() if o.tier == made.top_tier) == 1
        assert all(seat.holder in made.notables for seat in made.seats.values())
        assert made.seatless()                                # somebody is left to challenge

    def test_every_tier_has_its_rank_fee_and_means(self):
        offices, _ = load_definitions()
        for made in offices:
            assert made.tier in council_module.COUNCIL_TIER_RANKS
            assert made.tier in council_module.COUNCIL_FILING_FEE
            assert made.tier in council_module.NOTABLE_MEANS
            rank_index(council_module.COUNCIL_TIER_RANKS[made.tier])
            assert 0 <= made.fee_discount < 1 and 0 <= made.licence_discount < 1 and 0 <= made.feud_shield <= 1

    def test_the_notables_are_sound(self):
        _, notables = load_definitions()
        with open(os.path.join(DATA_PATH, "goods.json"), encoding="utf-8") as file:
            data = json.load(file)
        good_names = {good["name"] for good in (data["goods"] if isinstance(data, dict) else data)}
        keys = [entry["key"] for entry in notables]
        seats = [entry["office"] for entry in notables if entry["office"]]
        assert len(keys) == len(set(keys)) and len(seats) == len(set(seats))
        for entry in notables:
            assert entry["likes"] in good_names, entry["key"]
            assert 0 <= entry["integrity"] <= 1
            assert entry["arms"]["charge"] in CHARGES and entry["arms"]["metal"] in ("gold", "silver")

    def test_the_path_is_the_data_folders(self):
        assert os.path.dirname(COUNCIL_DATA_PATH) == DATA_PATH
