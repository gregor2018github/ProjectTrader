"""The Town Plan's marks for where the minigames are played: only once explored, named when hovered."""

import os
import xml.etree.ElementTree as ElementTree
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from src.models.fishing_spot import FishingSpot
from src.ui.layout_modules.town_plan import glyphs, ornaments
from src.ui.layout_modules.town_plan.view import STUMP_MARK_SIZE, TownPlan

STUMP_AT = (1000, 1000)
SPOT_AT = (2000, 1000)      # far enough from the stump that their marks do not touch


def plan(explored=True, stump=True):
    pygame.init()
    collision = pygame.Rect(0, 0, 32, 16)
    collision.center = STUMP_AT
    tmx = SimpleNamespace(width=100, height=100, tile_size=32,
                          fishing_spots=[FishingSpot("Wide River", *SPOT_AT)],
                          chopping_stump=SimpleNamespace(collision_rect=collision) if stump else None)
    fog = SimpleNamespace(is_explored=lambda x, y: explored)
    town_plan = TownPlan(SimpleNamespace(tmx_map=tmx, map_fog=fog))
    town_plan._inner = pygame.Rect(0, 0, 800, 800)
    town_plan.center = [1200, 1000]
    return town_plan


def painted(surface, rect=None):
    area = surface.subsurface(rect) if rect else surface
    return pygame.mask.from_surface(area, 0).count()


def test_the_map_has_a_chopping_stump():
    root = ElementTree.parse(os.path.join("assets", "tiles", "Map1.tmx")).getroot()
    assert [o for o in root.iter("object") if o.get("name") == "Stomp"]


def test_the_stump_drawing_stays_within_its_size_at_its_place():
    surface = pygame.Surface((100, 100), pygame.SRCALPHA)
    glyphs.chopping_stump(surface, (50, 50), STUMP_MARK_SIZE)
    painted_box = pygame.mask.from_surface(surface, 0).get_bounding_rects()[0]
    limit = pygame.Rect(0, 0, STUMP_MARK_SIZE + 4, STUMP_MARK_SIZE + 4)
    limit.center = (50, 50)
    assert painted_box.width >= STUMP_MARK_SIZE // 2
    assert limit.contains(painted_box)


def test_explored_stump_is_drawn_and_named_when_hovered():
    town_plan = plan()
    x, y = town_plan.world_to_screen(*STUMP_AT)
    surface = pygame.Surface((800, 800), pygame.SRCALPHA)
    town_plan._draw_minigame_marks(surface)
    around = pygame.Rect(0, 0, STUMP_MARK_SIZE, STUMP_MARK_SIZE)
    around.center = (x, y)
    assert painted(surface, around) > 0
    assert town_plan._minigame_mark_at((round(x), round(y)))[0] == "Chopping Stump"
    assert town_plan._minigame_mark_at((round(x) + STUMP_MARK_SIZE, round(y))) is None


def test_unexplored_stump_is_neither_drawn_nor_named():
    town_plan = plan(explored=False)
    surface = pygame.Surface((800, 800), pygame.SRCALPHA)
    town_plan._draw_minigame_marks(surface)
    assert painted(surface) == 0
    x, y = town_plan.world_to_screen(*STUMP_AT)
    assert town_plan._minigame_mark_at((round(x), round(y))) is None


def test_a_fishing_spot_is_still_marked_and_named():
    town_plan = plan()
    x, y = town_plan.world_to_screen(*SPOT_AT)
    assert town_plan._minigame_mark_at((round(x), round(y))) == ("Wide River", "Fishing spot")


def test_a_map_without_a_stump_only_has_its_fishing_spots():
    town_plan = plan(stump=False)
    surface = pygame.Surface((800, 800), pygame.SRCALPHA)
    town_plan._draw_minigame_marks(surface)
    x, y = town_plan.world_to_screen(*STUMP_AT)
    assert town_plan._minigame_mark_at((round(x), round(y))) is None


def test_the_legend_shows_the_stump():
    assert "Chopping stump" in ornaments.LEGEND_ROWS
    sample = pygame.Surface((80, 40), pygame.SRCALPHA)
    ornaments._legend_sample(sample, "Chopping stump", pygame.Rect(20, 12, 40, 16))
    assert painted(sample) > 0
