"""The Gourmet Collection at the guildhall: a page per kind of dish, the tasted ones named,
the others greyed out with a question mark, the pictures made a few at a time, the tooltip."""

import datetime
import os
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from src.models.statistics import Statistics
from src.models.tavern_menu import DISH_TYPES, Dish, all_dishes
from src.ui.helper_modules import gourmet_window
from src.ui.helper_modules.gourmet_window import (GourmetWindow, UNKNOWN_NAME, dishes_of, eaten_text,
                                                  open_gourmet_window)
from tests.fakes import FakeGameState

# Dishes no picture is made for, so the tests need not read the large pictures
STEW = Dish("Test Stew", "middle", "pottage", True, 2.5, "A stew for the tests", "bowl")
GRUEL = Dish("Test Gruel", "low", "pottage", False, 0.25, "Thin gruel", "bowl")
CAKE = Dish("Test Cake", "high", "sweet", False, 10.0, "A cake", "plate")
PIE = Dish("Test Pie", "low", "main", True, 1.5, "A pie", "plate")
BEER = Dish("Test Beer", "middle", "drink", False, 1.0, "A beer", "drink")
DISHES = [STEW, GRUEL, CAKE, PIE, BEER]


@pytest.fixture
def state():
    pygame.init()
    screen = pygame.display.set_mode((1920, 1080))
    stats = Statistics()
    stats.dishes_tried = {"test_stew": 3, "test_beer": 1}
    game_state = FakeGameState(datetime.datetime(1500, 1, 8, 12))
    game_state.screen = screen
    game_state.game = SimpleNamespace(depot=SimpleNamespace(stats=stats))
    game_state.info_window = None
    game_state.active_house_menu = None
    game_state.menu_fade_duration = 0.2
    return game_state


@pytest.fixture
def window(state):
    state.info_window = GourmetWindow(state.screen, state, DISHES)
    return state.info_window


def test_a_page_for_plates_bowls_and_drinks_each_in_order_of_tavern_and_course(window):
    assert DISH_TYPES == ("plate", "bowl", "drink")
    assert window.pages == {"plate": [PIE, CAKE], "bowl": [GRUEL, STEW], "drink": [BEER]}
    every = all_dishes()
    assert sum(len(dishes_of(kind)) for kind in DISH_TYPES) == len(every)


def test_the_window_fits_the_screen_and_the_plates_fit_the_window():
    assert GourmetWindow.W <= 1810 and GourmetWindow.H <= 1080 - 40
    assert len(dishes_of("plate")) <= GourmetWindow.COLUMNS * GourmetWindow.ROWS
    assert max(len(dishes_of(kind)) for kind in DISH_TYPES) == len(dishes_of("plate"))


def test_a_dish_tasted_shows_its_name_and_the_others_a_question_mark(window, monkeypatch):
    shown = []
    monkeypatch.setattr(gourmet_window, "_wrap", lambda text, font, width: shown.append(text) or [text])
    window.page = "bowl"
    window.draw()
    assert set(shown) == {"Test Stew"}                 # only the tasted one is named on its card
    assert window.tasted(STEW) and not window.tasted(GRUEL)


def test_how_often_it_was_eaten():
    assert eaten_text(0) == "Not yet tasted"
    assert eaten_text(1) == "Eaten once"
    assert eaten_text(4) == "Eaten 4 times"


def test_the_tabs_change_the_page(window):
    window.handle_click(window.tab_rects["drink"].center)
    assert window.page == "drink"
    window.draw()
    window.handle_click(window.tab_rects["plate"].center)
    assert window.page == "plate"


def test_hovering_a_tasted_card_tells_all_and_an_untasted_one_only_where_it_is_served(window, monkeypatch):
    window.page = "bowl"
    stew = window.tooltip_lines(STEW)
    texts = [text for text, _colour in stew]
    assert "A stew for the tests" in texts
    assert any("Served at a good inn" in t for t in texts)
    assert any(t.startswith("Well Fed") for t in texts)          # a pottage
    assert "Eaten 3 times" in texts
    gruel = [text for text, _colour in window.tooltip_lines(GRUEL)]
    assert gruel == ["Not yet tasted", "Served at a plain tavern"]
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: window.card_rect(1).center)
    assert window.hovered_dish(window.card_rect(1).center) is STEW
    window.draw()


def test_the_pictures_are_made_a_few_a_frame_and_greyed_for_a_dish_not_tasted(state):
    pigeons = next(d for d in all_dishes() if d.name == "Roast Pigeons")
    peacock = next(d for d in all_dishes() if d.name == "Peacock in its Feathers")
    state.game.depot.stats.dishes_tried = {"roast_pigeons": 1}
    gourmet_window._thumbs.clear()
    window = GourmetWindow(state.screen, state, [pigeons, peacock])
    window.draw()
    while window._waiting.get("plate"):
        window.draw()
    tasted = gourmet_window._thumbs[(gourmet_window.dish_picture_path(pigeons), True)]
    untasted = gourmet_window._thumbs[(gourmet_window.dish_picture_path(peacock), False)]
    assert tasted.get_width() <= GourmetWindow.PICTURE_W and tasted.get_height() <= GourmetWindow.PICTURE_H
    r, g, b, a = untasted.get_at((untasted.get_width() // 2, untasted.get_height() // 2))
    assert r == g == b and a < 255                        # grey and faded


def test_the_guildhall_offers_it(state):
    from src.ui.helper_modules import house_click_menu
    import inspect
    source = inspect.getsource(house_click_menu)
    assert '"Gourmet Collection"' in source and "open_gourmet_window(game_state)" in source
    open_gourmet_window(state)
    assert isinstance(state.info_window, GourmetWindow)
    assert UNKNOWN_NAME == "?"
