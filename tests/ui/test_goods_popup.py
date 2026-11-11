"""Goods given for nothing (a gift, a reward) rise over the cursor as "+3" and the
good's picture, like the coins of a trade, and fade away."""

import os
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from src.ui import transaction_feedback
from src.ui.transaction_feedback import CoinPopup, GoodsPopup, on_goods_received


@pytest.fixture
def state():
    pygame.init()
    pygame.display.set_mode((1920, 1080))
    return SimpleNamespace(screen=pygame.display.get_surface(), coin_popups=[], game=None)


def test_each_good_rises_over_the_cursor_one_above_the_other(state, monkeypatch):
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: (500, 600))
    on_goods_received(state, {"Wood": 3, "Stone": 2, "Iron": 0})
    first, second = state.coin_popups
    assert isinstance(first, GoodsPopup) and isinstance(second, GoodsPopup)
    assert first._y < 600 and second._y + second.height <= first._y


def test_it_fades_away_like_the_coins(state):
    popup = GoodsPopup(state.screen, (500, 600), "Wood", 3)
    coins = CoinPopup(state.screen, (500, 600), 3.0, is_spent=False)
    popup.draw()
    popup.update(transaction_feedback._DURATION / 2)
    assert popup.alive
    popup.update(transaction_feedback._DURATION)
    coins.update(transaction_feedback._DURATION * 1.5)
    assert not popup.alive and not coins.alive


def test_a_good_without_a_picture_still_shows_its_amount(state):
    GoodsPopup(state.screen, (500, 600), "No Such Good", 1).draw()
