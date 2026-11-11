"""The intro's address (ui/helper_modules/address_note.py): a glowing packet at the top
of the map that unfolds into a sheet when clicked, and folds away at the next click."""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from src.ui.helper_modules import address_note as mod
from src.ui.helper_modules.address_note import FOLDED, FOLDING, OPEN, UNFOLDING, AddressNote, phase_amounts

AREA = pygame.Rect(0, 60, 1800, 950)


@pytest.fixture(scope="module", autouse=True)
def _pygame():
    pygame.init()
    pygame.display.set_mode((1, 1))
    yield


def test_constants_the_tests_rely_on():
    assert mod.UNFOLD_S == 0.75 and mod.FOLD_S == 0.5
    assert mod.PHASES[-1] == 1.0


def _drawn(note):
    screen = pygame.Surface((AREA.right, AREA.bottom))
    note.begin_frame()
    note.draw(screen, AREA)
    return screen


def test_a_click_on_the_item_unfolds_it_and_any_click_folds_it_again():
    note = AddressNote()
    _drawn(note)
    assert note.state == FOLDED
    assert not note.handle_click((AREA.left + 5, AREA.bottom - 5))   # elsewhere: the game's
    assert note.handle_click(note.item_rect.center)
    assert note.state == UNFOLDING
    note.update(mod.UNFOLD_S)
    assert note.state == OPEN and note.t == 1.0
    assert note.handle_click((AREA.left + 5, AREA.bottom - 5))       # anywhere: taken, folds
    assert note.state == FOLDING
    note.update(mod.FOLD_S)
    assert note.state == FOLDED and note.t == 0.0


def test_a_click_while_unfolding_folds_it_back_from_where_it_got():
    note = AddressNote()
    _drawn(note)
    note.handle_click(note.item_rect.center)
    note.update(mod.UNFOLD_S / 2)
    assert note.handle_click((10, 900))
    assert note.state == FOLDING and 0.0 < note.t < 1.0


def test_no_click_is_taken_unless_it_was_drawn_this_frame():
    note = AddressNote()
    _drawn(note)
    note.begin_frame()                          # not drawn: the map is hidden, or the intro is over
    assert not note.handle_click(note.item_rect.center)
    assert note.state == FOLDED


def test_the_steps_follow_one_another():
    assert phase_amounts(0.0) == (0.0, 0.0, 0.0, 0.0)
    assert phase_amounts(1.0) == (1.0, 1.0, 1.0, 1.0)
    come, flaps, middle, last = phase_amounts(mod.PHASES[1])
    assert come == 1.0 and flaps == 1.0 and middle == 0.0 and last == 0.0


@pytest.mark.parametrize("t", [0.0, 0.05, 0.2, 0.3, 0.4, 0.6, 0.9, 1.0])
def test_every_moment_of_the_unfolding_draws_within_the_map(t):
    note = AddressNote()
    note.state, note.t = (UNFOLDING if 0 < t < 1 else OPEN if t == 1 else FOLDED), t
    note.update = lambda dt: None
    _drawn(note)
    assert AREA.contains(note.sheet_rect) and AREA.contains(note.item_rect)
    assert note.item_rect.midtop == note.sheet_rect.midtop


def test_the_item_is_the_parcel_picture_cut_to_its_shape():
    note = AddressNote()
    _drawn(note)
    assert note.item_rect.height == mod.ITEM_HEIGHT
    assert note.item_rect.width < 2 * mod.ITEM_HEIGHT     # the stray speck in its corner left out
