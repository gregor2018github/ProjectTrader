"""The quest for Flip, the shepherdess's black sheep (models/lost_sheep.py): its rules alone.

Flip slips out only through a fold gate the player opened and left open, in
the evening or night, with the player gone and the fold out of sight; once a
game. The shepherdess keeps the fold from the next morning to the day she has
thanked the player. Her talks follow the stages; lying costs 3 reputation,
owning up 0.5; bread lures him, and she gives one once; brought home by night,
she thanks the player the next morning. The sun hour is pinned to the clock,
so nothing hangs on the season.
"""

import datetime

import pytest

from src.models import lost_sheep as ls
from src.models.lost_sheep import LostSheep

DAY = datetime.datetime(1500, 1, 4)
AFTERNOON = DAY.replace(hour=15)
EVENING = DAY.replace(hour=21)
NEXT_MORNING = (DAY + datetime.timedelta(days=1)).date()


@pytest.fixture(autouse=True)
def clock_daylight(monkeypatch):
    monkeypatch.setattr(ls, "sun_hour", lambda t: t.hour + t.minute / 60.0)


def left_open() -> LostSheep:
    quest = LostSheep()
    quest.gate_opened_by_player()
    return quest


def escaped() -> LostSheep:
    quest = left_open()
    assert quest.check_escape(EVENING, player_away=True, fold_seen=False)
    return quest


def searching(confess=True) -> LostSheep:
    quest = escaped()
    quest.answer_missing(confess)
    return quest


def test_the_numbers_the_quest_was_asked_for():
    assert ls.LIE_REPUTATION == -3.0
    assert ls.CONFESS_REPUTATION == -0.5
    assert ls.BREAD_GIFT == {"Bread": 1} and ls.LURE_GOODS == {"Bread": 1}
    assert 0 < ls.LEASH_SLOWDOWN < 0.5


def test_a_gate_left_open_in_the_evening_lets_him_out_once_the_player_is_gone():
    quest = left_open()
    assert quest.check_escape(EVENING, player_away=True, fold_seen=False)
    assert quest.stage == ls.ESCAPED and quest.flip_at == ls.ON_ISLAND
    assert quest.missed_on == NEXT_MORNING


@pytest.mark.parametrize("now, away, seen", [
    (AFTERNOON, True, False),     # not yet evening
    (EVENING, False, False),      # the player is still by the fold
    (EVENING, True, True),        # the fold is in sight
])
def test_not_while_any_of_it_is_missing(now, away, seen):
    quest = left_open()
    assert not quest.check_escape(now, player_away=away, fold_seen=seen)
    assert quest.stage == ls.QUIET


def test_not_through_a_gate_the_player_did_not_leave_open():
    quest = LostSheep()
    assert not quest.check_escape(EVENING, player_away=True, fold_seen=False)


def test_a_gate_shut_again_undoes_the_danger():
    quest = left_open()
    quest.note_gates(any_open=False)
    assert not quest.check_escape(EVENING, player_away=True, fold_seen=False)
    quest.note_gates(any_open=True)        # someone else opening it does not count
    assert not quest.check_escape(EVENING, player_away=True, fold_seen=False)


def test_the_night_counts_as_evening_and_is_found_out_that_morning():
    quest = left_open()
    small_hours = DAY.replace(hour=2)
    assert quest.check_escape(small_hours, player_away=True, fold_seen=False)
    assert quest.missed_on == DAY.date()


def test_a_night_slept_through_counts_too():
    # The gate left open in the afternoon, then a rest till the next morning: the clock jumps
    # over the evening, which still lets him out, and she finds him gone that morning
    quest = left_open()
    assert not quest.check_escape(AFTERNOON, player_away=True, fold_seen=False)
    morning = (DAY + datetime.timedelta(days=1)).replace(hour=7)
    assert quest.check_escape(morning, player_away=True, fold_seen=False)
    assert quest.missed_on == NEXT_MORNING and quest.on_meadow(NEXT_MORNING)


def test_a_jump_within_the_day_does_not():
    quest = left_open()
    quest.check_escape(DAY.replace(hour=8), player_away=True, fold_seen=False)
    assert not quest.check_escape(AFTERNOON, player_away=True, fold_seen=False)


def test_it_happens_once_a_game():
    quest = searching()
    quest.lure(has_bread=True)
    quest.bring_home(shepherdess_there=True)
    quest.finish(NEXT_MORNING)
    quest.gate_opened_by_player()
    assert not quest.check_escape(EVENING, player_away=True, fold_seen=False)
    assert quest.stage == ls.DONE


def test_she_keeps_the_fold_from_the_next_morning_to_the_day_she_thanks_the_player():
    quest = escaped()
    assert not quest.on_meadow(DAY.date())
    assert quest.on_meadow(NEXT_MORNING)
    quest.answer_missing(confess=False)
    quest.lure(has_bread=True)
    quest.bring_home(shepherdess_there=True)
    later = NEXT_MORNING + datetime.timedelta(days=3)
    assert quest.on_meadow(later)
    quest.finish(later)
    assert quest.on_meadow(later)
    assert not quest.on_meadow(later + datetime.timedelta(days=1))
    assert not LostSheep().on_meadow(NEXT_MORNING)


def test_lying_costs_three_and_owning_up_half_a_point():
    liar, honest = escaped(), escaped()
    assert liar.answer_missing(confess=False) == -3.0
    assert honest.answer_missing(confess=True) == -0.5
    assert liar.stage == honest.stage == ls.SEARCHING
    assert liar.confessed is False and honest.confessed is True
    assert liar.answer_missing(confess=False) == 0.0      # asked once


def test_her_talks_follow_the_stages():
    quest = escaped()
    assert quest.talk(has_bread=False) == ls.MISSING and quest.has_news(False)
    quest.answer_missing(confess=True)
    assert quest.talk(has_bread=False) == ls.SEARCH and not quest.has_news(False)
    assert not quest.lure(has_bread=False)
    assert quest.needs_bread and quest.stage == ls.SEARCHING
    assert quest.talk(has_bread=False) == ls.BREAD and quest.has_news(False)
    assert quest.talk(has_bread=True) == ls.SEARCH
    quest.give_bread()
    assert quest.talk(has_bread=False) == ls.NO_BREAD and not quest.has_news(False)
    assert quest.lure(has_bread=True) and quest.leading and quest.flip_at == ls.ON_LEASH
    assert quest.talk(has_bread=False) == ls.LEADING_TALK
    assert quest.bring_home(shepherdess_there=True)
    assert quest.talk(has_bread=False) == ls.THANKS and quest.has_news(False)
    assert quest.flip_at == ls.AT_FOLD
    quest.finish(NEXT_MORNING)
    assert quest.talk(has_bread=False) is None


def test_brought_home_by_night_the_player_flocks_him_and_she_thanks_them_in_the_morning():
    quest = searching()
    quest.lure(has_bread=True)
    assert quest.bring_home(shepherdess_there=False)
    assert quest.at_night and quest.talk(has_bread=False) == ls.THANKS_NIGHT
    assert not quest.bring_home(shepherdess_there=True)     # only once


def test_he_is_named_once_she_has_told_the_player():
    quest = escaped()
    assert not quest.flip_named
    quest.answer_missing(confess=True)
    assert quest.flip_named


def test_every_page_and_answer_leads_somewhere():
    for name, page in ls.PAGES.items():
        assert page.text and page.answers, name
        for answer in page.answers:
            assert answer.next is None or answer.next in ls.PAGES, (name, answer.label)
            assert answer.does in (None, "lie", "confess", "bread", "accept", "decline")
    for first in (ls.MISSING, ls.SEARCH, ls.BREAD, ls.NO_BREAD, ls.LEADING_TALK, ls.THANKS, ls.THANKS_NIGHT):
        assert first in ls.PAGES


def test_the_save_round_trip():
    quest = searching(confess=False)
    quest.lure(has_bread=False)
    quest.give_bread()
    again = LostSheep()
    again.load(quest.to_save())
    assert again.to_save() == quest.to_save()
    assert again.stage == ls.SEARCHING and again.missed_on == NEXT_MORNING
    assert again.needs_bread and again.bread_given and again.confessed is False
    assert not again.gate_left_open


@pytest.mark.parametrize("data", [None, {}, {"stage": "nonsense"}, {"stage": "searching", "missed_on": "junk"}])
def test_an_older_or_broken_save_starts_quiet(data):
    quest = LostSheep()
    quest.load(data)
    assert quest.stage == ls.QUIET and quest.flip_at == ls.AT_FOLD
