"""The map's fishing spots: where they are, how far they reach and their rings on the water."""

import os
import xml.etree.ElementTree as ElementTree
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from src.config.constants import TILE_SIZE
from src.models import fishing_spot
from src.models.fishing_spot import FISHING_REACH_TILES, FishingSpot
from src.models.water import Water


def layer(root, name):
    return next(group for group in root.findall("objectgroup") if group.get("name") == name)


@pytest.fixture(scope="module")
def tiled():
    """The fishing spots and the water, as Map1.tmx has them."""
    root = ElementTree.parse(os.path.join("assets", "tiles", "Map1.tmx")).getroot()
    polygon = layer(root, "Water").find("object").find("polygon").get("points")
    water = Water("Water", [tuple(float(n) for n in point.split(",")) for point in polygon.split()])
    spots = {o.get("name"): (float(o.get("x")), float(o.get("y"))) for o in layer(root, "Fishing")}
    return spots, water


def test_the_map_has_the_three_spots(tiled):
    assert set(tiled[0]) == {"Wide River", "River Fork", "Harbor Pier"}


def test_every_spot_lies_in_the_water(tiled):
    spots, water = tiled
    for x, y in spots.values():
        assert water.contains_point(x, y)


def test_every_spot_can_be_reached_from_the_land(tiled):
    """Land lies within reach of it, so there is somewhere to stand and fish from."""
    spots, water = tiled
    reach = FISHING_REACH_TILES * TILE_SIZE
    for x, y in spots.values():
        assert not all(water.contains_point(x + dx, y + dy)
                       for dx in (-reach * 0.7, 0, reach * 0.7) for dy in (-reach * 0.7, 0, reach * 0.7))


def test_the_reach():
    spot = FishingSpot("Here", 1000, 1000)
    edge = FISHING_REACH_TILES * TILE_SIZE
    assert spot.in_reach(1000, 1000)
    assert spot.in_reach(1000 + edge, 1000)
    assert not spot.in_reach(1000 + edge + 1, 1000)
    assert not spot.in_reach(1000 + edge, 1000 + edge)


def test_a_ring_grows_and_fades():
    period = fishing_spot._RING_PERIOD_S
    (young, young_alpha), *_ = FishingSpot.rings(0.1 * period)
    (old, old_alpha), *_ = FishingSpot.rings(0.8 * period)
    assert young < old
    assert young_alpha > old_alpha


def camera(x_at, y_at):
    return SimpleNamespace(zoom=2.0, screen_width=200, screen_height=200, apply=lambda x, y: (x_at, y_at))


def painted(surface):
    return pygame.mask.from_surface(surface, 0).count()


def test_the_rings_show_in_view_and_are_skipped_out_of_it():
    pygame.init()
    spot = FishingSpot("Here", 0, 0)
    seconds = 0.5 * fishing_spot._RING_PERIOD_S

    seen = pygame.Surface((200, 200), pygame.SRCALPHA)
    spot.draw(seen, camera(100, 100), 0, 0, seconds)
    assert painted(seen) > 0

    far = pygame.Surface((200, 200), pygame.SRCALPHA)
    spot.draw(far, camera(1000, 100), 0, 0, seconds)
    assert painted(far) == 0
