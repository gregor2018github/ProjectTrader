"""The outdoors of the minigames played outside: the sky, the light and the weather."""

import datetime
import random
from types import SimpleNamespace

import pygame

from src.models.minigames.outdoors import Conditions, Outdoors

SIZE, HORIZON = (400, 300), 200
NOON = datetime.datetime(1500, 1, 4, 12)
MIDNIGHT = datetime.datetime(1500, 1, 4, 0)


def outdoors(when=NOON, **weather) -> Outdoors:
    return Outdoors(SIZE, HORIZON, when, Conditions(**weather), lamps=[((50, 50), 80)], rng=random.Random(0))


def run(o: Outdoors, seconds: float, dt: float = 1 / 60):
    sounds = []
    for _ in range(round(seconds / dt)):
        sounds += o.update(dt)
    return sounds


def test_the_conditions_come_from_the_games_weather_and_are_clear_without_one():
    assert Conditions.of(None) == Conditions()
    weather = SimpleNamespace(rain=0.5, snow=0.0, clouds=0.8, fog=0.1, storm=0.0, wind=-0.3, snow_cover=0.0)
    assert Conditions.of(weather) == Conditions(rain=0.5, clouds=0.8, fog=0.1, wind=-0.3)


def test_by_day_nothing_is_dimmed_and_the_lamps_are_out():
    o = outdoors()
    assert not o.lit and o.lamps == 0 and o.night == 0


def test_at_night_the_lamps_burn_and_light_round_them():
    o = outdoors(MIDNIGHT)
    assert o.lamps == 1 and o.night == 1
    near, far = o.lightmap.get_at((50, 50)), o.lightmap.get_at((390, 290))
    assert sum(near[:3]) > sum(far[:3])


def test_clouds_and_a_storm_darken_the_day():
    clear, grey, storm = outdoors(), outdoors(clouds=1.0), outdoors(clouds=1.0, storm=1.0)
    assert sum(storm.light_colour) < sum(grey.light_colour) < sum(clear.light_colour)


def test_it_rains_and_snows_as_hard_as_the_weather_says():
    assert outdoors(rain=1.0)._drops and not outdoors()._drops
    assert len(outdoors(rain=1.0)._drops) > len(outdoors(rain=0.3)._drops)
    o = outdoors(snow=0.5)
    run(o, 2.0)
    world = pygame.Surface(SIZE, pygame.SRCALPHA)
    o.draw_weather(world)
    assert world.get_bounding_rect().width > 0


def test_a_storm_strikes_and_its_thunder_follows():
    o = outdoors(rain=1.0, clouds=1.0, storm=1.0)
    assert "thunder" in run(o, 40.0)
    assert "thunder" not in run(outdoors(rain=1.0, clouds=1.0), 40.0)


def test_snow_lies_on_the_ground_only_when_it_has_settled():
    assert outdoors().snow_ground is None
    ground = outdoors(snow_cover=0.8).snow_ground
    assert ground.get_at((10, HORIZON - 20)).a == 0          # not on the sky
    assert ground.get_at((10, HORIZON + 40)).a > 0


def test_the_moons_dark_side_is_not_painted():
    """Not full, its shadow is cut out, so the glow and the sky show there (no dark disc)."""
    half = Outdoors._moon(0.25)
    full = Outdoors._moon(0.5)
    assert sum(1 for x in range(half.get_width()) for y in range(half.get_height()) if half.get_at((x, y)).a) < \
        sum(1 for x in range(full.get_width()) for y in range(full.get_height()) if full.get_at((x, y)).a)
    r = half.get_width() // 2 - 1
    assert half.get_at((2 * r - 1, r + 1)).a == 0               # its shadowed edge: see-through
    assert half.get_at((3, r + 1)).a == 255                     # its lit edge


def test_compose_puts_the_sky_where_the_world_is_see_through():
    o = outdoors(fog=0.0)
    world = pygame.Surface(SIZE, pygame.SRCALPHA)
    world.fill((10, 200, 10, 255), (0, HORIZON, SIZE[0], SIZE[1] - HORIZON))
    frame = pygame.Surface(SIZE)
    o.compose(frame, world)
    assert frame.get_at((5, 5))[:3] == o.sky.get_at((5, 5))[:3]
    assert frame.get_at((5, HORIZON + 50))[:3] == (10, 200, 10)
