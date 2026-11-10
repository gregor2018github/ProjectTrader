"""A door whose front a neighbour drawn in front of it hides is still a door.

NavGrid blocks the ground a walker would be hidden on, so strolling townsfolk
do not vanish into walls. A front door can open onto such ground when another
house stands just in front of it; the door then keeps its step, and the grid
opens the hidden way from it to the open street (NavGrid.open_way_out), never
through anything solid. Also which house a window light belongs to where two
houses stand one behind the other (TMXMap._light_owner).
"""

import pygame
import pytest

from src.models import navigation
from src.models.door import Door
from src.models.map import TMXMap
from src.models.navigation import NavGrid

TILE = 32
SIZE = 30            # tiles each way: enough open ground for OPEN_GROUND_CELLS
FIGURE = (32, 54)


class FakeHouse:
    """What NavGrid and _light_owner read of a house: its sprite, base and collision box."""

    def __init__(self, x, y, width, height, collision, name=''):
        self.x, self.y = x, y
        self.image = pygame.Surface((width, height), pygame.SRCALPHA)
        self.image.fill((120, 100, 80, 255))
        self.collision_rect = pygame.Rect(collision)
        self.tile_size = TILE
        self.name = name

    @property
    def y_sort(self):
        return self.y


class FakeMap:
    def __init__(self, houses):
        self.tile_size, self.width, self.height = TILE, SIZE, SIZE
        self.houses = houses
        self.trees, self.waters, self.water_tiles, self.bridges = [], [], [], []

    def is_standable(self, x, y):
        return not any(h.collision_rect.collidepoint(x, y) for h in self.houses)


def street():
    """House A, and house B tall enough in front of it to hide A's doorstep.

    A's base is at y 256; B's sprite covers x 96..352 from y 152 down to its
    base at 352, its collision the bottom tile of it. Between them, rows 8
    and 9, the ground is free but hidden behind B.
    """
    back = FakeHouse(128, 256, 160, 160, (128, 192, 160, 64), 'A')
    front = FakeHouse(96, 352, 256, 200, (96, 320, 256, 32), 'B')
    return FakeMap([back, front])


@pytest.fixture(autouse=True)
def _pins(monkeypatch):
    # The constants these tests are built around
    monkeypatch.setattr(navigation, 'OCCLUSION_COVER', 0.7)
    monkeypatch.setattr(navigation, 'OPEN_GROUND_CELLS', 200)
    monkeypatch.setattr(navigation, 'MAX_HIDDEN_WAY_CELLS', 400)


def test_the_doorstep_is_hidden_ground():
    m = street()
    nav = NavGrid(m, FIGURE)
    assert nav.is_open_at(208, 282)          # nothing solid in front of A's door
    assert not nav.is_free_at(208, 282)      # but a walker there is behind B


def test_a_hidden_doorstep_still_makes_a_door():
    m = street()
    nav = NavGrid(m, FIGURE)
    door = Door(1, 'down', 208, 250, TILE, nav, m.is_standable)
    assert door.is_usable
    assert door.step == (208, 282)


def test_the_door_can_be_reached_from_the_open_street():
    m = street()
    nav = NavGrid(m, FIGURE)
    door = Door(1, 'down', 208, 250, TILE, nav, m.is_standable)
    route = nav.find_route((24 * TILE, 24 * TILE), door.step)
    assert route, 'no route to a door behind a neighbour'


def test_the_way_out_never_opens_anything_solid():
    m = street()
    nav = NavGrid(m, FIGURE)
    Door(1, 'down', 208, 250, TILE, nav, m.is_standable)
    for i, solid in enumerate(nav.solid):
        if solid:
            assert nav.blocked[i], f'cell {i % SIZE},{i // SIZE} is solid but was opened'


def test_hidden_ground_off_the_doors_way_stays_blocked():
    """Only the door's way is opened; strollers still go round the rest of what B hides."""
    m = street()
    nav = NavGrid(m, FIGURE)
    hidden_before = sum(1 for b, s in zip(nav.blocked, nav.solid) if b and not s)
    Door(1, 'down', 208, 250, TILE, nav, m.is_standable)
    hidden_after = sum(1 for b, s in zip(nav.blocked, nav.solid) if b and not s)
    assert 0 < hidden_before - hidden_after < hidden_before


def test_a_door_walled_in_by_collision_has_no_step():
    m = street()
    # A wall right across the doorstep and every tile out to MAX_STEP_TILES
    m.houses.append(FakeHouse(0, 0, 1, 1, (96, 260, 288, 200), 'wall'))
    nav = NavGrid(m, FIGURE)
    assert not Door(1, 'down', 208, 250, TILE, nav, m.is_standable).is_usable


class LightOwnerMap:
    """Just what TMXMap._light_owner reads."""

    def __init__(self, houses):
        self.houses = houses


def test_a_window_belongs_to_the_house_drawn_in_front():
    m = street()
    back, front = m.houses
    # A window painted on B's sprite but within A's old zone (5 tiles above A's base)
    assert TMXMap._light_owner(LightOwnerMap(m.houses), 200, 250) is front


def test_a_window_on_no_sprite_falls_back_to_the_nearest_base_below():
    back = FakeHouse(128, 256, 160, 160, (128, 192, 160, 64), 'A')
    back.image = pygame.Surface((160, 160), pygame.SRCALPHA)   # nothing painted
    assert TMXMap._light_owner(LightOwnerMap([back]), 200, 150) is back
