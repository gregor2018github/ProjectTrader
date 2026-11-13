"""The tavern's bill of fare: a box per dish, ordering one, and the picture brought to the table."""

import datetime
import os
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from src.models.statistics import Statistics
from src.models.tavern_menu import Dish
from src.ui.helper_modules import tavern_menu_window
from src.ui.helper_modules.tavern_menu_window import DishServedWindow, TavernMenuWindow
from tests.fakes import FakeGameState

PIGEONS = Dish("Roast Pigeons", "middle", "main", True, 5.0, "Young pigeons roasted with herbs")
# A dish no picture is made for, so the menu stays open when it is ordered
ALE = Dish("Test Ale", "middle", "drink", False, 0.5, "A mug of the house ale")


class FakeDepot:
    def __init__(self, money):
        self.money = money
        self.cost_of_living = 0.0
        self.stats = Statistics()

    def book_cost_of_living(self, amount):
        self.money -= amount
        self.cost_of_living += amount


@pytest.fixture
def state(monkeypatch):
    pygame.init()
    screen = pygame.display.set_mode((1920, 1080))
    monkeypatch.setattr(tavern_menu_window, "daily_menu",
                        lambda day, cls, key: [("main", [PIGEONS]), ("drink", [ALE])])
    monkeypatch.setattr(tavern_menu_window, "on_money_spent", lambda gs, amount: gs.money_feedback.append(("spent", amount)))
    game_state = FakeGameState(datetime.datetime(1500, 1, 8, 12))
    game_state.screen = screen
    game_state.game = SimpleNamespace(depot=FakeDepot(10.0))
    game_state.info_window = None
    game_state.active_house_menu = None
    game_state.menu_fade_duration = 0.2
    return game_state


@pytest.fixture
def window(state):
    house = SimpleNamespace(name="House_9", x=100, y=200, tavern_class="middle", display_name="Grey Griffin Inn")
    state.info_window = TavernMenuWindow(state.screen, state, house)
    return state.info_window


def test_each_dish_is_a_box_that_is_drawn(window):
    assert window.dishes == [PIGEONS, ALE]
    first, second = window.card_rect(0), window.card_rect(1)
    assert window.panel.contains(first) and window.panel.contains(second)
    assert second.top > first.bottom
    window.draw()


def test_ordering_a_dish_pays_and_records_it_and_brings_its_picture(window, state):
    window.handle_click(window.card_rect(0).center)
    depot = state.game.depot
    assert depot.money == pytest.approx(5.0)
    assert depot.cost_of_living == pytest.approx(5.0)
    assert depot.stats.dishes_tried == {"roast_pigeons": 1}
    assert state.money_feedback == [("spent", 5.0)]
    served = state.info_window
    assert isinstance(served, DishServedWindow)      # assets/pictures/dish_roast_pigeons.png exists
    served.draw()
    served.handle_click(served.panel.center)
    assert state.info_window is window


def test_a_dish_without_a_picture_keeps_the_menu_open(window, state):
    window.handle_click(window.card_rect(1).center)
    assert state.info_window is window
    assert state.game.depot.stats.dishes_tried == {"test_ale": 1}


def test_no_coins_no_dish(window, state):
    state.game.depot.money = 1.0
    window.handle_click(window.card_rect(0).center)
    assert state.info_window is window
    assert state.game.depot.stats.dishes_tried == {}
    assert state.warnings


def test_an_ordered_dish_becomes_the_players_meal_and_the_next_says_it_replaces_it(window, state):
    from src.models.meal_effects import STRONG_HAND, current_meal, effect_strength
    from src.models.player import Player
    state.game.player = Player("P", 1.0)
    assert window._replaced_mark(ALE) is None
    window.handle_click(window.card_rect(0).center)       # the pigeons, with meat: a strong hand
    meal = current_meal(state.game.player, state.date)
    assert meal.kind == STRONG_HAND and meal.strength == effect_strength(PIGEONS.price)
    assert window._replaced_mark(PIGEONS) is None           # the same dish again only starts it afresh
    assert window._replaced_mark(ALE) is not None
    window.draw()
