"""Reading a gravestone: "Read" in its menu, the stone opening with its inscription, and putting it away."""

import os
import re
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from src.config.constants import SCREEN_HEIGHT
from src.models.epitaphs import BY_KEY, EPITAPHS
from src.ui.helper_modules import house_click_menu
from src.ui.helper_modules.gravestone_window import (
    BUILDERS, DEFAULT_DESIGN, DESIGNS, STONE_BRIGHTNESS, GravestoneWindow, _font, open_gravestone,
    sprite_stone_colour,
)

ROOT = Path(__file__).resolve().parents[2]
MAP = ROOT / 'assets' / 'tiles' / 'Map1.tmx'
SPRITES = ROOT / 'assets' / 'map_sprites' / 'houses'
SMALLEST_TEXT = 18   # the smallest point size a design carves in


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
    return SimpleNamespace(name='Deco_21', display_name='Gravestone', epitaph=key, tavern_class='', fishing_spot='', doors=[])


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


@pytest.mark.parametrize('design', sorted(BUILDERS))
@pytest.mark.parametrize('inscription', EPITAPHS, ids=[e.key for e in EPITAPHS])
def test_every_inscription_fits_every_stone(design, inscription):
    window = GravestoneWindow(_state().screen, _state(), None, inscription, design=design)
    built = window.built
    assert window.stone.get_height() + 60 < SCREEN_HEIGHT
    assert window.stone.get_width() < 1000
    smallest = _font(SMALLEST_TEXT).size("Mg")[1]
    for font, text, rect in built.texts:   # every line carved wholly on the stone, none off its edge
        assert built.mask.overlap_area(pygame.mask.Mask(rect.size, fill=True), rect.topleft) == rect.w * rect.h, text
        assert font.size("Mg")[1] >= smallest, f'too small to read: {text}'
    carved = " ".join(window.carved_text())
    for word in " ".join((inscription.name.upper(),) + inscription.lines).split():
        assert word in carved


def test_each_gravestone_on_the_map_has_its_design():
    text = MAP.read_text(encoding='utf-8')
    for block in re.findall(r'<object [^>]*>.*?</object>', text, re.S):
        if 'name="Epitaph"' in block:
            name = re.search(r'<property name="File_name" value="([^"]*)"', block).group(1)
            assert name in DESIGNS, name
    assert set(DESIGNS.values()) <= set(BUILDERS)


def test_a_stone_takes_its_sprites_colour_made_readable():
    assert sprite_stone_colour(None) is None
    low, high = STONE_BRIGHTNESS
    for name in DESIGNS:
        image = pygame.image.load(str(SPRITES / name))
        colour = sprite_stone_colour(image)
        assert colour is not None, name
        assert low - 1 <= 0.3 * colour[0] + 0.59 * colour[1] + 0.11 * colour[2] <= high + 1, name
    teal = sprite_stone_colour(pygame.image.load(str(SPRITES / 'Deco_16.png')))
    assert teal[2] > teal[0] + 20          # the Gothic stone stays blue-green


def test_a_stone_not_listed_is_a_rounded_slab():
    house = SimpleNamespace(file_name='Deco_99.png', image=None)
    assert GravestoneWindow(_state().screen, _state(), house, BY_KEY['knight']).design == DEFAULT_DESIGN
