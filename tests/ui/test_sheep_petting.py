"""Petting a sheep: a little reputation, but only the first time each game day,
shown afterwards as "+0.2" and the laurel rising from the player's head."""

import datetime
import os
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from src.config.constants import SHEEP_PET_REPUTATION
from src.models.figurines.animals.sheep import Sheep
from src.models.statistics import Statistics
from src.ui.transaction_feedback import ReputationPopup
from src.ui.helper_modules.figurine_click_menu import (
    PET_SHEEP_OPTION, FigurineMenu, _pet_sheep, show_figurine_menu,
)

assert SHEEP_PET_REPUTATION == 0.2

VIEW = pygame.Rect(0, 0, 900, 900)


class Player:
    x, y, width, height = 420, 420, 32, 32
    sprite_draw_offset = (0, -16)

    def __init__(self):
        self.reputation = 0.0

    def _get_scaled_sprite(self, zoom):
        return pygame.Surface((32, 48), pygame.SRCALPHA)

    def change_reputation(self, amount):
        self.reputation += amount


class Lamb(Sheep):
    """A sheep without its sprites, as much of one as the menu asks of it."""

    sprite_draw_offset = (0, 0)
    is_hidden = False
    display_name = "Sheep"

    def __init__(self):  # Skips the sprite loading
        self.x, self.y, self.width, self.height = 400, 400, 32, 32
        self.petted = 0

    def pet(self, player_center_x):
        self.petted += 1

    def _get_scaled_sprite(self, zoom):
        return pygame.Surface((32, 32), pygame.SRCALPHA)


@pytest.fixture
def state():
    pygame.init()
    log = []
    player = Player()
    camera = SimpleNamespace(zoom=1.0, apply=lambda x, y: (x, y))
    state = SimpleNamespace(
        screen=pygame.display.set_mode((1920, 1080)), font=pygame.font.Font(None, 24),
        date=datetime.datetime(1500, 3, 1, 10, 0), info_window=None, coin_popups=[], active_house_menu=None,
        menu_fade_window=None, menu_fade_timer=0, menu_fade_duration=0.2,
        log_event=lambda category, text: log.append(category), log=log,
    )
    state.game = SimpleNamespace(
        game_map=SimpleNamespace(map_player=player, camera=camera), player=player,
        depot=SimpleNamespace(stats=Statistics()), sheep_sounds=[], play_sound=lambda name: None,
    )
    return state


def pet(state):
    _pet_sheep(state, Lamb(), VIEW)


def open_menu(state):
    assert show_figurine_menu(state, Lamb(), VIEW)
    menu = state.info_window
    assert isinstance(menu, FigurineMenu)
    return menu


def test_the_first_petting_of_the_day_earns_reputation_and_the_rest_nothing(state):
    pet(state)
    pet(state)
    state.date += datetime.timedelta(hours=10)
    pet(state)
    assert state.game.player.reputation == pytest.approx(SHEEP_PET_REPUTATION)
    assert state.log == ["RANK"]


def test_the_next_day_earns_it_again(state):
    pet(state)
    state.date += datetime.timedelta(days=1)
    pet(state)
    assert state.game.player.reputation == pytest.approx(2 * SHEEP_PET_REPUTATION)


def test_the_gain_rises_from_the_players_head_once_the_sheep_is_petted(state):
    menu = open_menu(state)
    assert not state.coin_popups                    # nothing shown before the petting
    rect = next(rect for rect, text in menu.buttons if text == PET_SHEEP_OPTION)
    menu.handle_click(rect.center)
    [popup] = state.coin_popups
    assert isinstance(popup, ReputationPopup)
    # Centred over the sprite's top, the player's head (VIEW less its 5 px border)
    head_x, head_y = 5 + 420 + 16, 5 + 420 - 16
    assert popup._x + popup._surf.get_width() // 2 == pytest.approx(head_x, abs=1)
    assert popup._y + popup.height < head_y
    popup.draw()


def test_a_petting_that_earns_nothing_shows_nothing(state):
    pet(state)
    pet(state)
    assert len(state.coin_popups) == 1


def test_the_day_is_saved():
    stats = Statistics()
    stats.last_sheep_pet_day = "1500-03-01"
    assert Statistics.from_dict(stats.to_dict()).last_sheep_pet_day == "1500-03-01"
    assert Statistics.from_dict({}).last_sheep_pet_day is None
