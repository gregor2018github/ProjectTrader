"""The parchment rolled over a view that changed: over which part, how long, and which page is heard."""

import pygame
import pytest

from src.ui import view_transition as vt_module
from src.ui.view_transition import ViewTransition

MODULE_WIDTH = 825
SCREEN_HEIGHT = 1064


class FakeSound:
    def __init__(self, name, length):
        self.name, self.length = name, length
        self.plays = 0

    def get_length(self):
        return self.length

    def play(self):
        self.plays += 1
        return None


@pytest.fixture(autouse=True)
def pinned(monkeypatch):
    for name, value in (("MODULE_WIDTH", MODULE_WIDTH), ("SCREEN_HEIGHT", SCREEN_HEIGHT),
                        ("ROLL_SECONDS", 0.5), ("ROLL_SECONDS_WIDE", 0.75)):
        monkeypatch.setattr(vt_module, name, value)


@pytest.fixture
def screen():
    pygame.display.init()
    pygame.display.set_mode((1, 1))   # the paper's grain is converted to the display's format
    return pygame.Surface((1760, SCREEN_HEIGHT))


@pytest.fixture
def sounds():
    return {"page_turn_1": FakeSound("page_turn_1", 0.4), "page_turn_2": FakeSound("page_turn_2", 0.45),
            "page_turn_3": FakeSound("page_turn_3", 1.6), "door_1": FakeSound("door_1", 3.0)}


def switch(sounds, screen, before, after):
    transition = ViewTransition(sounds)
    transition.begin_frame(screen, *before, 0.0)
    transition.begin_frame(screen, *after, 0.0)
    return transition


def test_the_longest_page_is_kept_for_both_sides(sounds):
    transition = ViewTransition(sounds)
    assert transition.long_page is sounds["page_turn_3"]
    assert set(transition.short_pages) == {sounds["page_turn_1"], sounds["page_turn_2"]}


def test_nothing_at_the_first_frame_or_without_a_change(sounds, screen):
    transition = ViewTransition(sounds)
    transition.begin_frame(screen, "map", "market", 0.0)
    transition.begin_frame(screen, "map", "market", 0.0)
    assert not transition.active


def test_one_side_changing_rolls_over_that_side(sounds, screen):
    transition = switch(sounds, screen, ("map", "market"), ("depot", "market"))
    assert transition.rect == pygame.Rect(0, 60, MODULE_WIDTH, SCREEN_HEIGHT - 120)
    assert transition.duration == 0.5
    assert sounds["page_turn_3"].plays == 0
    assert sounds["page_turn_1"].plays + sounds["page_turn_2"].plays == 1


def test_a_full_view_splitting_rolls_over_both(sounds, screen):
    transition = switch(sounds, screen, ("map", "map"), ("market", "map"))
    assert transition.rect == pygame.Rect(0, 60, MODULE_WIDTH * 2, SCREEN_HEIGHT - 120)
    assert transition.duration == 0.75
    assert sounds["page_turn_3"].plays == 1


def test_the_roll_is_done_after_its_time(sounds, screen):
    transition = switch(sounds, screen, ("map", "market"), ("depot", "market"))
    transition.draw(screen)
    transition.begin_frame(screen, "depot", "market", 0.3)
    assert transition.active
    transition.begin_frame(screen, "depot", "market", 0.3)
    assert not transition.active
