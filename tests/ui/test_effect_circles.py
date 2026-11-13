"""The circles of what acts on the player in the Explore map's top left corner: which there are,
how much of a meal's ring is left, their pictograms, the tooltip, and their rects for clicks."""

import datetime
import os
import random
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from src.models import meal_effects
from src.models.player import Player
from src.models.tavern_menu import Dish
from src.models.weather import Weather
from src.ui.effect_pictograms import PICTOGRAMS, pictogram
from src.ui.layout_modules import effect_circles
from src.ui.layout_modules.effect_circles import CIRCLE_SIZE, MARGIN, draw_effect_circles, player_effects

NOON = datetime.datetime(1500, 1, 8, 12)
PIGEONS = Dish("Roast Pigeons", "middle", "main", True, 5.0, "")


@pytest.fixture(autouse=True)
def display():
    pygame.init()
    pygame.display.set_mode((1920, 1080))


def _game(meal_at=None, rain=0.0, wetness=0.0, snow_cover=0.0):
    player = Player("P", 1.0)
    if meal_at is not None:
        meal_effects.eat(player, PIGEONS, meal_at)
    weather = Weather(random.Random(1), kind="clear")
    weather.rain, weather.wetness, weather.snow_cover = rain, wetness, snow_cover
    return SimpleNamespace(player=player, weather=weather)


def test_nothing_on_the_player_nothing_shown():
    assert player_effects(_game(), NOON) == []


def test_a_meals_ring_runs_out_with_its_hours():
    hours = meal_effects.meal_hours(PIGEONS)
    effects = player_effects(_game(meal_at=NOON - datetime.timedelta(hours=1.5)), NOON)
    assert [e.key for e in effects] == [meal_effects.STRONG_HAND]
    meal = effects[0]
    assert meal.share_left == pytest.approx((hours - 1.5) / hours) and not meal.harmful
    assert meal.title == "Strong Hand"
    left = round((hours - 1.5) * 60)
    assert f"{left // 60}h {left % 60:02d}m left of {hours:g}h" in meal.lines
    assert "From the Roast Pigeons" in meal.lines


def test_the_weather_is_a_red_circle_named_after_its_worst_part():
    effects = player_effects(_game(rain=0.5, wetness=1.0), NOON)
    weather = effects[-1]
    assert weather.key == "mud" and weather.harmful and weather.share_left == 1.0
    assert weather.lines[0] == "Walk 8% slower"
    assert player_effects(_game(rain=1.0), NOON)[-1].key == "rain"
    assert player_effects(_game(snow_cover=0.5), NOON)[-1].key == "snow"


def test_the_meal_comes_first_then_the_weather():
    keys = [e.key for e in player_effects(_game(meal_at=NOON, rain=1.0), NOON)]
    assert keys == [meal_effects.STRONG_HAND, "rain"]


def test_every_effect_and_hindrance_has_a_pictogram():
    keys = set(meal_effects.EFFECTS) | set(effect_circles.HINDRANCES)
    assert keys <= set(PICTOGRAMS)
    for key in keys:
        picture = pictogram(key, 36)
        assert picture.get_size() == (36, 36)
        assert picture.get_bounding_rect().height > 18     # something is drawn on it


def test_the_ring_is_drawn_for_what_is_left_and_not_at_all_when_none_is():
    assert effect_circles._ring(False, 0.0) is None
    half = effect_circles._ring(False, 0.5)
    full = effect_circles._ring(False, 1.0)
    painted = lambda s: sum(1 for x in range(CIRCLE_SIZE) for y in range(CIRCLE_SIZE) if s.get_at((x, y)).a > 128)
    assert 0.4 < painted(half) / painted(full) < 0.6
    # The part left starts at the top and runs clockwise: the right half is drawn, the left is not
    mid = CIRCLE_SIZE // 2
    assert half.get_at((CIRCLE_SIZE - 3, mid)).a > 128
    assert half.get_at((2, mid)).a < 128


def test_the_circles_sit_in_the_maps_top_left_corner_and_their_tooltip_shows_on_hover(monkeypatch):
    screen = pygame.display.get_surface()
    font = pygame.font.SysFont(None, 20)
    state = SimpleNamespace(game=_game(meal_at=NOON, rain=1.0), date=NOON, font=font, small_font=font,
                            info_window=None, minigame=None)
    map_rect = pygame.Rect(5, 65, 900, 800)
    shown = []
    monkeypatch.setattr(effect_circles, "_draw_tooltip", lambda *args: shown.append(args[2].key))
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: (5000, 5000))
    draw_effect_circles(screen, map_rect, state)
    first, second = state.effect_circle_rects
    assert first.topleft == (map_rect.left + MARGIN, map_rect.top + MARGIN)
    assert second.left > first.right and second.top == first.top
    assert shown == []
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: second.center)
    draw_effect_circles(screen, map_rect, state)
    assert shown == ["rain"]


def test_the_tooltip_draws():
    screen = pygame.display.get_surface()
    font = pygame.font.SysFont(None, 20)
    state = SimpleNamespace(font=font, small_font=font)
    effect = player_effects(_game(meal_at=NOON), NOON)[0]
    effect_circles._draw_tooltip(screen, state, effect, pygame.Rect(17, 77, CIRCLE_SIZE, CIRCLE_SIZE),
                                 pygame.Rect(5, 65, 900, 800))


def test_the_tooltip_keeps_its_height_whatever_the_time_left_reads():
    """The game's font hangs 3, 4, 5, 7 and 9 below the line and renders each line only as deep
    as its own characters go: the lines are put a fixed pitch apart instead."""
    screen = pygame.display.get_surface()
    font = pygame.font.Font(os.path.join("assets", "fonts", "RomanAntique.ttf"), 19)
    state = SimpleNamespace(font=font, small_font=font)
    circle, map_rect = pygame.Rect(17, 77, CIRCLE_SIZE, CIRCLE_SIZE), pygame.Rect(5, 65, 900, 800)
    assert font.render("1h 02m", True, (0, 0, 0)).get_height() != font.render("3h 37m", True, (0, 0, 0)).get_height()
    heights = set()
    for eaten_ago in (0.25, 1.0, 1.95, 2.4, 4.6):
        effect = player_effects(_game(meal_at=NOON - datetime.timedelta(hours=eaten_ago)), NOON)[0]
        heights.add(effect_circles._draw_tooltip(screen, state, effect, circle, map_rect).height)
    assert len(heights) == 1
