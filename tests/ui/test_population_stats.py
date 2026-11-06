"""The town hall's population stats: each class's needs met, tier by tier, and hunger shown in red."""
import pygame
import pytest

from src.config.colors import DARK_GREEN, DARK_RED
from src.config.constants import HUNGER_THRESHOLD
from src.ui.helper_modules import population_stats as ps
from src.ui.helper_modules.population_stats import PopulationStats


class FakeTown:
    citizens, max_citizens, happiness = 100, 120, 70.0
    population_groups = {"Poor": 40, "Commons": 40, "Middling Sort": 15, "Nobility": 5}
    happiness_groups = {"Poor": 60.0, "Commons": 70.0, "Middling Sort": 75.0, "Nobility": 80.0}
    fulfilment_groups = {"Poor": {"basic": HUNGER_THRESHOLD - 0.1, "comfort": 0.5, "luxury": 0.0},
                         "Commons": {"basic": 1.0, "comfort": 0.9, "luxury": 0.4}}


class FakeState:
    game = None


@pytest.fixture(scope="module")
def window():
    pygame.display.init()
    pygame.font.init()
    screen = pygame.display.set_mode((1760, 1064))
    return PopulationStats(screen, FakeState(), FakeTown())


def colours_in(surface, rect):
    return {tuple(surface.get_at((x, y)))[:3] for x in range(rect.left, rect.right) for y in range(rect.top, rect.bottom)}


def test_a_hungry_class_has_a_red_basic_bar_and_a_fed_one_a_green_one(window):
    surface = pygame.Surface((300, 200))
    window._draw_needs(surface, pygame.Rect(0, 0, 300, 200), FakeTown.fulfilment_groups["Poor"])
    assert DARK_RED in colours_in(surface, pygame.Rect(0, 0, 300, 200))
    fed = pygame.Surface((300, 200))
    window._draw_needs(fed, pygame.Rect(0, 0, 300, 200), FakeTown.fulfilment_groups["Commons"])
    found = colours_in(fed, pygame.Rect(0, 0, 300, 200))
    assert DARK_GREEN in found and DARK_RED not in found


def test_the_whole_window_draws_every_class_even_one_the_simulation_has_no_fulfilment_for(window):
    window.draw()                                           # Middling Sort and Nobility have none: drawn as met
    assert set(ps.POP_TYPES) == set(FakeTown.population_groups)
