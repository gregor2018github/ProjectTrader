"""What a meal at a tavern does for the player: which effect, how strong by its price, how
long, one at a time; and where each effect acts: the walk (with the weather slowing it),
the tiredness, the fishing's strike and the woodhacking's points."""

import datetime
import os
import random
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from src.models import meal_effects as me
from src.models import weather as weather_module
from src.models.meal_effects import (LIGHT_STEP, STEADY_HAND, STRONG_HAND, WELL_FED, MealEffect, bonus,
                                     current_meal, eat, effect_kind, effect_strength, game_bonus)
from src.models.minigames import woodhacking as wh
from src.models.minigames.fishing_pond import SPECIES, Fish, Hook
from src.models.player import Player
from src.models.rest import HOURS_TO_EXHAUSTION, Tiredness
from src.models.statistics import Statistics
from src.models.tavern_menu import Dish, all_dishes
from src.models.weather import Weather

NOON = datetime.datetime(1500, 1, 8, 12)


def dish(course="main", meat=False, price=5.0, name="Some Dish"):
    return Dish(name, "middle", course, meat, price, "")


def test_the_constants_the_tests_rely_on():
    assert (me.STRENGTH_MIN, me.STRENGTH_MAX) == (0.02, 0.15)
    assert (me.PRICE_FLOOR, me.PRICE_CEILING) == (0.25, 60.0)
    assert me.MEAL_HOURS == 6.0
    assert (weather_module.WALK_SLOW_RAIN, weather_module.WALK_SLOW_MUD,
            weather_module.WALK_SLOW_SNOW, weather_module.WALK_SLOW_MAX) == (0.06, 0.05, 0.12, 0.15)


# ── Which effect, how strong ─────────────────────────────────────────────────

def test_each_course_gives_its_effect():
    assert effect_kind(dish("main", meat=True)) == STRONG_HAND
    assert effect_kind(dish("main", meat=False)) == WELL_FED
    assert effect_kind(dish("pottage")) == WELL_FED
    assert effect_kind(dish("side")) == WELL_FED
    assert effect_kind(dish("sweet")) == LIGHT_STEP
    assert effect_kind(dish("drink")) == STEADY_HAND


def test_the_strength_runs_from_two_to_fifteen_percent_by_the_price():
    assert effect_strength(0.25) == 0.02
    assert effect_strength(60.0) == 0.15
    assert effect_strength(0.1) == 0.02 and effect_strength(500.0) == 0.15   # never beyond either end
    prices = [0.25, 0.5, 1.5, 5.0, 15.0, 30.0, 60.0]
    strengths = [effect_strength(p) for p in prices]
    assert strengths == sorted(strengths) and len(set(strengths)) == len(strengths)


def test_only_the_dearest_dishes_come_near_fifteen_percent():
    dishes = all_dishes()
    assert max(effect_strength(d.price) for d in dishes) <= 0.15
    dearest = max(d.price for d in dishes)
    for d in dishes:
        if effect_strength(d.price) >= 0.14:
            assert d.tavern_class == "high" and d.price >= dearest / 2
    for d in dishes:
        if d.tavern_class == "low":
            assert effect_strength(d.price) <= 0.07


# ── One meal at a time ───────────────────────────────────────────────────────

def test_a_meal_lasts_six_hours():
    player = Player("P", 1.0)
    eat(player, dish("sweet", price=5.0), NOON)
    strength = effect_strength(5.0)
    assert bonus(player, LIGHT_STEP, NOON + datetime.timedelta(hours=5, minutes=59)) == strength
    assert bonus(player, LIGHT_STEP, NOON + datetime.timedelta(hours=6)) == 0.0
    assert bonus(player, WELL_FED, NOON) == 0.0           # only its own kind


def test_a_new_meal_replaces_the_last():
    player = Player("P", 1.0)
    eat(player, dish("main", meat=True, price=30.0, name="Venison"), NOON)
    eat(player, dish("drink", price=0.25, name="Small Ale"), NOON + datetime.timedelta(hours=1))
    assert bonus(player, STRONG_HAND, NOON + datetime.timedelta(hours=2)) == 0.0
    assert current_meal(player, NOON + datetime.timedelta(hours=2)).dish == "Small Ale"


def test_a_meal_is_saved_and_anything_odd_is_dropped():
    meal = MealEffect("Roast Pigeons", STRONG_HAND, 0.09, NOON)
    assert MealEffect.from_save(meal.to_save()) == meal
    assert MealEffect.from_save(None) is None
    assert MealEffect.from_save({"kind": "flying", "dish": "x", "strength": 1, "until": NOON.isoformat()}) is None
    assert MealEffect.from_save({"kind": STRONG_HAND}) is None


def test_the_save_keeps_the_meal():
    from src.persistence import save_manager
    import inspect
    source = inspect.getsource(save_manager)
    assert '"meal": player.meal.to_save()' in source
    assert 'MealEffect.from_save(p.get("meal"))' in source


def test_a_game_without_a_player_has_no_bonus():
    assert game_bonus(SimpleNamespace(), STRONG_HAND) == 0.0
    player = Player("P", 1.0)
    eat(player, dish("drink", price=15.0), NOON)
    game = SimpleNamespace(player=player, state=SimpleNamespace(date=NOON))
    assert game_bonus(game, STEADY_HAND) == effect_strength(15.0)


# ── Where each acts ──────────────────────────────────────────────────────────

def test_well_fed_tires_more_slowly():
    player = Player("P", 1.0)
    eat(player, dish("pottage", price=60.0), NOON)        # the dearest: 15 %
    tiredness = Tiredness(player, NOON)
    tiredness.update(NOON + datetime.timedelta(hours=4))
    assert player.tiredness == pytest.approx(4 / HOURS_TO_EXHAUSTION * 0.85)


def test_bad_weather_slows_the_walk_by_at_most_fifteen_percent():
    w = Weather(random.Random(1), kind="clear")
    w.rain = w.wetness = w.snow_cover = 0.0
    assert w.walking_slowdown() == 0.0
    w.rain = 1.0
    assert w.walking_slowdown() == pytest.approx(0.06)
    w.wetness = 1.0
    assert w.walking_slowdown() == pytest.approx(0.11)
    w.rain, w.wetness, w.snow_cover = 0.0, 1.0, 1.0       # the snow hides the mud
    assert w.walking_slowdown() == pytest.approx(0.12)
    w.rain = 1.0
    assert w.walking_slowdown() == 0.15


def test_a_steady_hand_holds_the_bait_longer_but_grades_the_strike_as_before():
    fish = Fish(SPECIES["roach"], random.Random(1))
    fish._take(Hook(hold_extra=0.1), [])
    assert fish.take_window == SPECIES["roach"].take_window
    assert fish.timer == pytest.approx(SPECIES["roach"].take_window * 1.1)


def test_a_strong_hand_adds_its_share_to_every_swing(monkeypatch):
    pygame.init()
    monkeypatch.setattr(wh, "on_money_received", lambda *a, **k: None)
    stats = Statistics()
    stats.minigame_tips_seen = [wh.TIP_TUTORIAL, wh.TIP_DOUBLE_PERFECT]
    player = Player("P", 1.0)
    eat(player, dish("main", meat=True, price=60.0), NOON)   # 15 %
    game = SimpleNamespace(depot=SimpleNamespace(stats=stats, book_labor_income=lambda *a: None),
                           state=SimpleNamespace(log_event=lambda *a: None, date=NOON),
                           sounds={}, play_sound=lambda name: None, player=player)
    minigame = wh.WoodhackingMinigame(pygame.Surface((10, 10)), game)
    assert minigame.strong_hand == 0.15
    while not minigame.scene.can_charge or not minigame.scene.log_ready:
        minigame.update(1 / 60)
    minigame.aim = 0.0
    minigame.power = (minigame.opt_lo + minigame.opt_hi) / 2
    minigame._resolve_swing()
    assert minigame.last_gain == pytest.approx(5 * 1.15)
