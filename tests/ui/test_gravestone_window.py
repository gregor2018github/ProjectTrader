"""Reading a gravestone: "Read" in its menu, the stone opening with its inscription, and putting it away."""

import os
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from src.config.constants import SCREEN_HEIGHT
from src.models.epitaphs import BY_KEY, EPITAPHS
from src.ui.helper_modules import house_click_menu
from src.ui.helper_modules.gravestone_window import SLAB_WIDTH, GravestoneWindow, open_gravestone


@pytest.fixture(autouse=True)
def _pygame():
    pygame.init()
    pygame.display.set_mode((1, 1))
    yield


def _state():
    warnings = []
    state = SimpleNamespace(screen=pygame.Surface((1920, 1080)), info_window=None, active_house_menu=None,
                            menu_fade_window=None, menu_fade_timer=0, menu_fade_duration=0.2, game=None,
                            font=pygame.font.SysFont("arial", 20), warnings=warnings, date=None)
    state.show_warning = warnings.append
    return state


def _grave(key='knight'):
    return SimpleNamespace(name='Deco_21', display_name='Gravestone', epitaph=key, tavern_class='', doors=[])


def test_read_is_offered_only_on_a_gravestone(monkeypatch):
    monkeypatch.setattr(house_click_menu.settings_store, "get", lambda *a, **k: False)
    state = _state()
    house_click_menu.show_house_menu(state, _grave(), (100, 100))
    assert state.info_window.options == ["Read"]
    state.info_window = None
    house_click_menu.show_house_menu(state, _grave(''), (100, 100))
    assert state.info_window is None       # a plain decoration has nothing to offer


def test_read_opens_the_stone_and_a_click_puts_it_away(monkeypatch):
    monkeypatch.setattr(house_click_menu.settings_store, "get", lambda *a, **k: False)
    state = _state()
    grave = _grave()
    house_click_menu.show_house_menu(state, grave, (100, 100))
    state.info_window.callback("Read")
    window = state.info_window
    assert isinstance(window, GravestoneWindow)
    assert window.epitaph is BY_KEY['knight'] and window.house is grave
    window.draw()
    window.draw(0.5)
    assert window.handle_click((5, 5))
    assert state.info_window is None and state.menu_fade_window is window


def test_escape_puts_it_away():
    state = _state()
    open_gravestone(state, _grave())
    state.info_window.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    assert state.info_window is None


def test_an_unknown_inscription_cannot_be_read():
    state = _state()
    assert not open_gravestone(state, _grave('nobody'))
    assert state.info_window is None and state.warnings


@pytest.mark.parametrize('inscription', EPITAPHS, ids=[e.key for e in EPITAPHS])
def test_every_inscription_fits_its_stone(inscription):
    window = GravestoneWindow(_state().screen, _state(), None, inscription)
    assert window.stone.get_width() == SLAB_WIDTH
    assert window.stone.get_height() + 60 < SCREEN_HEIGHT
    carved = [text for _, text in window.text_lines() if text]
    assert any(inscription.name.upper().startswith(t) for t in carved)
    assert all(font.size(text)[0] <= SLAB_WIDTH - 100 for font, text in window.text_lines())
