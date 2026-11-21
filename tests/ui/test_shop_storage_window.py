"""Uncle Gared's shop as the player's first storage: the inventory window on the
starting storage (key START), its name, slots and moving goods across."""

import os
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from src.models.depot import START
from src.models.intro import SHOP_HOUSE, SHOP_NAME
from src.ui.helper_modules.warehouse_inventory import PACK, WAREHOUSE, open_warehouse_inventory
from tests.models.conftest import STARTING_STORAGE_SLOTS
from tests.models.conftest import depot, game_state, make_good, pinned_storage, wood  # noqa: F401 (fixtures)

SHOP = SimpleNamespace(name=SHOP_HOUSE, tmx_id=29, display_name=None)


@pytest.fixture
def window(depot, wood, game_state):
    pygame.init()
    game_state.screen = pygame.display.set_mode((1920, 1080))
    game_state.info_window = None
    game_state.active_house_menu = None
    game_state.game = SimpleNamespace(
        depot=depot, goods=[wood], images={'goods_icon': {}, 'goods_30': {}},
        game_map=SimpleNamespace(tmx_map=SimpleNamespace(houses=[])))
    assert depot.buy(wood, 3, game_state)
    open_warehouse_inventory(game_state, SHOP, START)
    return game_state.info_window


def test_it_shows_the_starting_storage_under_the_shops_name(window, game_state):
    assert window.key == START and window.house is SHOP
    assert game_state.active_house_menu is SHOP
    assert window._titles()[0] == SHOP_NAME
    assert len(window.sections[WAREHOUSE].slot_rects) == STARTING_STORAGE_SLOTS
    window.draw()


def test_a_click_carries_a_slots_goods_into_the_hands(window, depot):
    window.draw()
    window.handle_click(window.sections[WAREHOUSE].slot_rects[0][0].center)
    assert depot.starting_slots[0]["good"] is None
    assert sum(s["qty"] for s in depot.pack_slots if s["good"] == "Wood") == 3
    window.draw()
    window.handle_click(window.sections[PACK].slot_rects[0][0].center)
    assert depot.starting_slots[0]["good"] == "Wood"
