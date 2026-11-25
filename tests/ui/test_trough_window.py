"""A trough's menu and sheet: looking in, pouring water, filling it with the player's wheat, tipping it out,
the buttons it greys and why (src/ui/helper_modules/trough_window.py)."""

import os
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from src.models import chicken_troughs as ct
from src.models.chicken_troughs import FEED, WATER, Troughs, trough_title
from src.models.trough import Trough
from src.ui.helper_modules import house_click_menu
from src.ui.helper_modules.trough_window import TroughWindow, refill


@pytest.fixture(autouse=True)
def _pygame(monkeypatch):
    pygame.init()
    pygame.display.set_mode((1, 1))
    monkeypatch.setattr(ct, "FEED_WHEAT_FULL", 2)
    monkeypatch.setattr(house_click_menu.settings_store, "get", lambda *a, **k: False)   # no Inspect


class FakeDepot:
    def __init__(self, wheat):
        self.good_stock = {"Wheat": wheat}

    def use_goods(self, needed):
        if any(self.good_stock.get(name, 0) < n for name, n in needed.items()):
            return False
        for name, n in needed.items():
            self.good_stock[name] -= n
        return True


def _state(wheat=5):
    trough = Trough(x=400, y=400, file_name="troughs/trough_empty.png", tiles_to_right=2, tiles_up=1,
                    collision_to_right=2, collision_up=1, tile_size=32, name="Trough_Test", house_class="Trough")
    trough.tavern_class = trough.fishing_spot = trough.epitaph = ""
    warnings = []
    state = SimpleNamespace(screen=pygame.Surface((1920, 1080)), info_window=None, active_house_menu=None,
                            menu_fade_window=None, menu_fade_timer=0, menu_fade_duration=0.2,
                            font=pygame.font.SysFont("arial", 20), warnings=warnings, date=None)
    state.show_warning = warnings.append
    game = SimpleNamespace(troughs=Troughs([trough.name]), depot=FakeDepot(wheat),
                           flock=SimpleNamespace(hens=[object()] * 5), sounds={})

    def show_troughs():
        s = game.troughs[trough.name]
        trough.show(s.picture(), not s.empty)
        trough.display_name = trough_title(s)

    game.show_troughs = show_troughs
    state.game = game
    return state, trough


def _press(window, key):
    window.draw()
    assert window.handle_click(window.button_rect(key).center)


def test_the_menu_offers_to_look_in_and_to_refill_what_it_holds():
    state, trough = _state()
    house_click_menu.show_house_menu(state, trough, (100, 100))
    assert state.info_window.options == ["Look In"]             # empty: nothing to refill
    state.game.troughs.pour_water(trough.name)
    state.game.troughs[trough.name].amount = 0.3
    house_click_menu.show_house_menu(state, trough, (100, 100))
    assert state.info_window.options == ["Look In", "Refill"]
    state.info_window.callback("Refill")
    assert state.game.troughs[trough.name].full and state.info_window is None
    house_click_menu.show_house_menu(state, trough, (100, 100))
    state.info_window.callback("Look In")
    assert isinstance(state.info_window, TroughWindow) and state.info_window.trough is trough


def test_water_is_poured_in_free_and_shows_on_the_map():
    state, trough = _state()
    window = TroughWindow(state.screen, state, trough)
    _press(window, "water")
    assert state.game.troughs[trough.name].kind == WATER and trough.shown == "trough_water_4"
    assert trough.display_name == "Water Trough" and state.game.depot.good_stock["Wheat"] == 5
    told = dict(window.lines())
    assert told["Holds"] == "Water" and told["Fill"] == "Brim full" and "days" in told["Lasts"]


def test_grain_takes_the_wheat_it_has_room_for_out_of_the_stock():
    state, trough = _state(wheat=5)
    window = TroughWindow(state.screen, state, trough)
    _press(window, "grain")
    assert state.game.troughs[trough.name].full and state.game.depot.good_stock["Wheat"] == 3
    assert trough.shown == "trough_feed_4" and trough.has_contents


def test_with_only_one_wheat_it_is_half_filled_and_with_none_the_button_says_why():
    state, trough = _state(wheat=1)
    window = TroughWindow(state.screen, state, trough)
    _press(window, "grain")
    assert state.game.troughs[trough.name].amount == pytest.approx(0.5)
    _press(window, "grain")
    assert window.note == "You have no Wheat. It is sold at the market."
    assert state.game.troughs[trough.name].amount == pytest.approx(0.5)


def test_it_holds_one_thing_at_a_time_and_tipping_it_out_frees_it():
    state, trough = _state()
    window = TroughWindow(state.screen, state, trough)
    _press(window, "grain")
    _press(window, "water")
    assert window.note == "It is full to the brim." and state.game.troughs[trough.name].kind == FEED
    state.game.troughs[trough.name].amount = 0.5
    _press(window, "water")
    assert window.note == "There is grain in it. Tip it out first."
    _press(window, "tip")
    assert state.game.troughs[trough.name].empty and trough.shown == "trough_empty"
    _press(window, "water")
    assert state.game.troughs[trough.name].kind == WATER


def test_refill_warns_when_there_is_no_wheat():
    state, trough = _state(wheat=0)
    state.game.troughs.add_grain(trough.name, 1)
    refill(state, trough)
    assert state.warnings == ["You have no Wheat to fill it with."]


def test_done_escape_or_a_click_off_the_sheet_puts_it_away():
    state, trough = _state()
    for close in ("done", "escape", "off"):
        window = TroughWindow(state.screen, state, trough)
        state.info_window = window
        window.draw()
        window.draw(0.5)
        if close == "done":
            _press(window, "done")
        elif close == "escape":
            window.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
        else:
            window.handle_click((2, 2))
        assert state.info_window is None and state.menu_fade_window is window
