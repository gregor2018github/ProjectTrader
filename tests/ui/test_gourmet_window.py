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


def test_the_pictures_are_made_a_few_a_frame_and_a_dish_not_tasted_shows_only_its_grey_outline(state):
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
    # Only the one grey, solid in the middle, see-through at the corners: nothing of the dish but its shape
    w, h = untasted.get_size()
    colours = {untasted.get_at((x, y))[:3] for x in range(w) for y in range(h) if untasted.get_at((x, y)).a > 0}
    assert colours == {gourmet_window.SILHOUETTE}
    assert untasted.get_at((w // 2, h // 2)).a >= 250              # solid, but for the scaling's rounding
    assert untasted.get_at((0, 0)).a == 0


def test_the_outline_is_found_on_a_painted_background_and_comes_out_solid():
    """A dish drawn on a wall and a table, its inside the table's colour: the shape is the whole dish."""
    pygame.init()
    picture = pygame.Surface((160, 120))
    picture.fill((158, 146, 120))                                   # the wall
    pygame.draw.rect(picture, (140, 126, 96), (0, 70, 160, 50))     # the table
    for y in range(72, 120, 6):
        pygame.draw.line(picture, (130, 116, 88), (0, y), (160, y))  # its grain
    pygame.draw.ellipse(picture, (30, 24, 20), (30, 30, 100, 70))    # the dish's dark outline
    pygame.draw.ellipse(picture, (140, 126, 96), (34, 34, 92, 62))   # filled with the table's colour
    pygame.draw.circle(picture, (150, 120, 80), (8, 112), 2)        # a crumb by itself
    mask = gourmet_window.dish_mask(picture)
    assert mask.get_at((80, 65)) == 1                               # the middle is the dish, not a hole
    assert mask.get_at((5, 5)) == 0 and mask.get_at((150, 110)) == 0
    assert mask.get_at((8, 112)) == 0                               # the crumb is trimmed off
    assert len(mask.connected_components()) == 1


def test_clicking_a_tasted_dish_shows_it_large_and_a_click_comes_back(state):
    from src.ui.helper_modules.tavern_menu_window import DishServedWindow
    pigeons = next(d for d in all_dishes() if d.name == "Roast Pigeons")
    peacock = next(d for d in all_dishes() if d.name == "Peacock in its Feathers")
    state.game.depot.stats.dishes_tried = {"roast_pigeons": 2}
    window = GourmetWindow(state.screen, state, [pigeons, peacock])
    state.info_window = window
    window.handle_click(window.card_rect(1).center)                 # not tasted: nothing to see
    assert state.info_window is window
    window.handle_click(window.card_rect(0).center)
    served = state.info_window
    assert isinstance(served, DishServedWindow) and served.dish is pigeons
    assert "Click to see it larger" in [text for text, _ in window.tooltip_lines(pigeons)]
    served.draw()
    served.handle_click(served.panel.center)
    assert state.info_window is window


def test_the_guildhall_offers_it(state):
    from src.ui.helper_modules import house_click_menu
    import inspect
    source = inspect.getsource(house_click_menu)
    assert '"Gourmet Collection"' in source and "open_gourmet_window(game_state)" in source
    open_gourmet_window(state)
    assert isinstance(state.info_window, GourmetWindow)
    assert UNKNOWN_NAME == "?"
