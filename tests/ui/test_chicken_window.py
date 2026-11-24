"""Observing a chicken: "Observe" in its menu, its sheet with its age, weight and look, put away by a click."""

import datetime
import os
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from src.models.chickens import ADULT_DAYS, ChickenLook, Hen
from src.models.figurines.animals.chicken import Chicken
from src.ui.helper_modules import figurine_click_menu
from src.ui.helper_modules.chicken_window import ChickenWindow
from src.ui.helper_modules.figurine_click_menu import OBSERVE_OPTION, FigurineMenu, show_figurine_menu

VIEW = pygame.Rect(0, 0, 900, 900)
NOW = datetime.datetime(1500, 3, 1, 10, 0)


@pytest.fixture
def state(monkeypatch):
    pygame.init()
    monkeypatch.setattr(figurine_click_menu.settings_store, "get", lambda *a, **k: False)   # no Inspect
    player = SimpleNamespace(x=420, y=420, width=32, height=32)
    camera = SimpleNamespace(zoom=1.0, apply=lambda x, y: (x, y))
    state = SimpleNamespace(
        screen=pygame.display.set_mode((1920, 1080)), font=pygame.font.Font(None, 24), date=NOW,
        info_window=None, active_house_menu=None, menu_fade_window=None, menu_fade_timer=0,
        menu_fade_duration=0.2)
    state.game = SimpleNamespace(game_map=SimpleNamespace(map_player=player, camera=camera), player=player)
    return state


def _chicken(hatched):
    hen = Hen(ChickenLook("B", "plume", "barred"), hatched, 100.0, 1.1)
    chicken = Chicken(pygame.Rect(300, 300, 200, 200), 32, hen, NOW)
    chicken.place_feet(400, 400)
    return chicken


def test_a_chicken_offers_to_be_observed_and_its_sheet_opens_and_a_click_puts_it_away(state):
    chicken = _chicken(NOW - datetime.timedelta(days=40))
    assert show_figurine_menu(state, chicken, VIEW)
    menu = state.info_window
    assert isinstance(menu, FigurineMenu) and [text for _, text in menu.buttons] == [OBSERVE_OPTION]
    rect = next(rect for rect, text in menu.buttons if text == OBSERVE_OPTION)
    menu.handle_click(rect.center)
    window = state.info_window
    assert isinstance(window, ChickenWindow) and window.chicken is chicken
    window.draw()
    assert window.handle_click((5, 5)) and state.info_window is None


def test_the_sheet_tells_its_age_weight_build_colour_head_and_tail(state):
    window = ChickenWindow(state.screen, state, _chicken(NOW - datetime.timedelta(days=40)))
    told = dict(window.lines)
    assert window.title == "Hen"
    assert told["Age"] == "1 year and 1 season old"         # 40 days; a year old, the days no longer told
    assert told["Weight"] == "2.9 kg" and told["Build"] == "Large"
    assert told["Colour"] == "Barred (Uncommon)"
    assert told["Head"] == "Square, with a three-spiked comb" and told["Tail"] == "A big plume"


def test_a_chicks_sheet_says_so_and_draws_it_smaller(state):
    chick = ChickenWindow(state.screen, state, _chicken(NOW - datetime.timedelta(days=1)))
    grown = ChickenWindow(state.screen, state, _chicken(NOW - datetime.timedelta(days=ADULT_DAYS)))
    told = dict(chick.lines)
    assert chick.title == "Chick" and told["Build"] == "Still growing" and told["Weight"].endswith(" g")
    assert "still pale" in told["Colour"]
    assert chick.picture_zoom < grown.picture_zoom
