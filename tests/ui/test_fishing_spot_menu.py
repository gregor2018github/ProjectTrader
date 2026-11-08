"""The way into the fishing from the map: the water's menu at a spot, and the rings there."""

import datetime
import os
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from src.config.constants import TILE_SIZE
from src.models.fishing_spot import FISHING_REACH_TILES, FishingSpot
from src.models.minigames.fishing import FishingMinigame
from src.models.statistics import Statistics
from src.ui.helper_modules.water_click_menu import show_water_menu
from src.ui.layout_modules.map_view import _draw_fishing_spots

TODAY = datetime.datetime(1500, 1, 4, 10)
SPOT = FishingSpot("Wide River", 1000, 1000)


class FakeMap:
    """As much of TMXMap as the menu asks of it."""

    fishing_spots = [SPOT]

    def fishing_spot_near(self, x, y):
        return SPOT if SPOT.in_reach(x, y) else None


@pytest.fixture
def state():
    pygame.init()
    screen = pygame.display.set_mode((1920, 1080))
    warnings = []
    state = SimpleNamespace(date=TODAY, screen=screen, coin_popups=[], log_event=lambda *a: None, time_level=3,
                            previous_time_level=None, minigame=None, info_window=None, active_house_menu=None,
                            font=pygame.font.Font(None, 24), warnings=warnings, show_warning=warnings.append)
    depot = SimpleNamespace(stats=Statistics(), book_labor_income=lambda *a: None)
    player = SimpleNamespace(x=SPOT.x, y=SPOT.y, width=0, height=0)
    game_map = SimpleNamespace(map_player=player, tmx_map=FakeMap())
    state.game = SimpleNamespace(state=state, sounds={}, weather=SimpleNamespace(), depot=depot, game_map=game_map)
    return state


def open_menu(state):
    water = SimpleNamespace(throw_rock=lambda game_state: None)
    show_water_menu(state, water, (100, 100))
    return state.info_window


def press(menu, option):
    rect = next(rect for rect, text in menu.buttons if text == option)
    assert menu.handle_click(rect.center)


def test_within_reach_it_offers_the_fishing_under_the_spots_name(state):
    menu = open_menu(state)
    assert menu.options == ["Go Fishing", "Throw Stone"]
    assert menu.title == "Wide River"


def test_out_of_reach_it_is_only_water(state):
    state.game.game_map.map_player.x = SPOT.x + (FISHING_REACH_TILES + 1) * TILE_SIZE
    menu = open_menu(state)
    assert menu.options == ["Throw Stone"]
    assert menu.title == "Water"


def test_go_fishing_starts_the_minigame_and_uses_the_day_up(state):
    press(open_menu(state), "Go Fishing")
    assert isinstance(state.minigame, FishingMinigame)
    assert state.info_window is None
    assert state.game.depot.stats.last_fishing_day == TODAY.date().isoformat()


def test_a_second_time_the_same_day_it_only_says_so(state):
    state.game.depot.stats.last_fishing_day = TODAY.date().isoformat()
    press(open_menu(state), "Go Fishing")
    assert state.minigame is None
    assert state.warnings


class RecordingSpot:
    def __init__(self):
        self.drawn = 0

    def draw(self, *args):
        self.drawn += 1


def test_the_rings_show_only_while_the_days_fishing_is_to_be_done(state):
    spot = RecordingSpot()
    tmx = SimpleNamespace(fishing_spots=[spot])
    _draw_fishing_spots(state.screen, tmx, None, 0, 0, state)
    assert spot.drawn == 1
    state.game.depot.stats.last_fishing_day = TODAY.date().isoformat()
    _draw_fishing_spots(state.screen, tmx, None, 0, 0, state)
    assert spot.drawn == 1
