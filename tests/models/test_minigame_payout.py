"""The minigames' payout and shown score: no cap at the max score, but the pay grows slowly beyond it."""

import pytest

from src.models.minigames import base
from src.models.minigames.base import score_to_coins, score_to_display

MAX = 150


@pytest.fixture(autouse=True)
def pinned(monkeypatch):
    monkeypatch.setattr(base, "COINS_AT_MAX", 20.0)
    monkeypatch.setattr(base, "COINS_BEYOND_SCALE", 2.0)
    monkeypatch.setattr(base, "COINS_BEYOND_RATE", 4.0)


def test_a_perfect_session_pays_twenty():
    assert score_to_coins(MAX, MAX) == 20.0
    assert score_to_display(MAX, MAX) == MAX


def test_above_the_max_the_pay_grows_but_slowly():
    pays = [score_to_coins(s, MAX) for s in (150, 165, 195, 225, 300)]
    assert pays == sorted(pays) and pays[-1] > pays[0]
    assert pays[1] - pays[0] < 1.0                       # a tenth more: under a coin more
    assert pays[-1] < 24                                  # twice the max: not even 4 more
    gains = [b - a for a, b in zip(pays, pays[1:])]
    per_point = [g / d for g, d in zip(gains, (15, 30, 30, 75))]
    assert per_point == sorted(per_point, reverse=True)  # each point worth less than the last


def test_the_pay_does_not_jump_at_the_max():
    assert score_to_coins(MAX + 0.5, MAX) - score_to_coins(MAX, MAX) < 0.1


def test_the_shown_score_goes_on_past_the_max_without_a_jump():
    assert score_to_display(MAX + 10, MAX) > MAX
    shown = [score_to_display(s, MAX) for s in range(140, 200, 2)]
    assert shown == sorted(shown)
    steps = [b - a for a, b in zip(shown, shown[1:])]
    assert max(steps) <= 6                               # smooth through the max: about 5 per 2 raw points
