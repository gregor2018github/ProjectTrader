"""The main menu's new game page (ui/new_game_page.py): a rolled name to start with,
the die rolling another, typing replacing it, Start and Back by click and key."""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from src.models import player_names
from src.ui.new_game_page import BACK, START, NewGamePage


@pytest.fixture(scope="module", autouse=True)
def _pygame():
    pygame.init()
    pygame.display.set_mode((1, 1))
    yield


@pytest.fixture
def page():
    font = pygame.font.SysFont("arial", 20)
    return NewGamePage(font, font, font)


def _type(page, text):
    return page.handle_event(pygame.event.Event(pygame.TEXTINPUT, text=text))


def _key(page, key):
    return page.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, unicode="", mod=0))


def test_it_opens_with_a_rolled_name_chosen_as_a_whole(page):
    assert not player_names.is_legacy(page.text)
    assert page.selected
    assert page.name == page.text


def test_the_die_rolls_another_name(page):
    before = page.text
    assert page.handle_click(page.die.center) is None
    assert page.text != before and page.selected


def test_typing_replaces_the_rolled_name_then_adds_to_it(page):
    _type(page, "Hans")
    _type(page, " Sachs")
    assert page.text == "Hans Sachs" and not page.selected
    _key(page, pygame.K_BACKSPACE)
    assert page.text == "Hans Sach"


def test_backspace_on_the_chosen_name_clears_it(page):
    _key(page, pygame.K_BACKSPACE)
    assert page.text == ""


def test_the_field_takes_no_more_than_the_longest_name(page):
    _type(page, "x" * 40)
    assert len(page.text) == player_names.MAX_NAME_LENGTH


def test_an_empty_field_starts_with_a_rolled_name(page):
    _key(page, pygame.K_BACKSPACE)
    assert not player_names.is_legacy(page.name)


def test_start_and_back_by_click_and_key(page):
    assert page.handle_click(page.start_button.center) == START
    assert page.handle_click(page.back_button.center) == BACK
    assert _key(page, pygame.K_RETURN) == START
    assert _key(page, pygame.K_ESCAPE) == BACK


def test_it_draws(page):
    screen = pygame.Surface((1920, 1080))
    page.draw(screen, page.die.center)
    page.selected = False
    page.draw(screen, (0, 0))


def test_the_player_stands_under_the_name_above_the_buttons(page):
    from src.ui.new_game_page import PREVIEW_H
    assert page.preview is not None
    assert page.preview.get_height() == PREVIEW_H
    assert page.field.bottom < page.preview_rect.top
    assert page.preview_rect.bottom < page.start_button.top
    assert page.panel.contains(page.preview_rect) and page.panel.contains(page.back_button)
