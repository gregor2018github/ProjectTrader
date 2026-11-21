"""Every NPC going through the gates on their way (models/gate_passing.py), on a made-up pen: walls round a
yard on a 20 x 20 tile map, a gate in its north side, a townsperson walked frame by frame across it.

The NavGrid takes no notice of the gate, so routes run through it; the walker stops short of it, opens it if
it is shut, goes through, turns and shuts it behind him, open as he found it or not, unless somebody stands
in the gateway, whom he waits for and at last leaves it open to."""

import datetime
import os
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from src.models import gate_passing as passing_module
from src.models.figurines.humans.npcs.townsperson import AT_HOME, Townsperson
from src.models.gate import Gate
from src.models.gate_passing import CLEAR_PX, GateKeeper, gate_stops
from src.models.navigation import NavGrid

TILE = 32
FRAME = 1 / 60
NOW = datetime.datetime(1500, 1, 1, 12)
# Walls from x 160 to 480 and y 320 to 496, the north side open at x 320..352 for the gate
WALLS = [pygame.Rect(160, 320, 160, 16), pygame.Rect(352, 320, 128, 16), pygame.Rect(160, 480, 320, 16),
         pygame.Rect(160, 320, 16, 176), pygame.Rect(464, 320, 16, 176)]
OUTSIDE, INSIDE = (336.0, 200.0), (336.0, 440.0)


@pytest.fixture(autouse=True)
def display():
    pygame.display.init()
    pygame.display.set_mode((1, 1))


def door(spot, facing_in="front", facing_out="back"):
    return SimpleNamespace(id=id(spot), entry=spot, step=spot, facing_in=facing_in, facing_out=facing_out)


class Pen:
    def __init__(self):
        self.gate = Gate(320, 336, "", 1, 1, 1, 1, TILE, name="Gate_Pen", house_class="Gate",
                         col_margin_up_pixel=-16)              # its gateway (320, 320) 32 x 16
        walls = [SimpleNamespace(collision_rects=[wall], image=None) for wall in WALLS]
        tmx = SimpleNamespace(tile_size=TILE, width=20, height=20, houses=walls + [self.gate], trees=[],
                              waters=[], water_tiles=set(), bridges=[])
        self.nav = NavGrid(tmx)
        self.bodies = []
        self.keeper = GateKeeper([self.gate], lambda: self.bodies)
        self.person = Townsperson("poor_roland", "Roland", TILE, "male")
        self.person.speed = 52.0
        self.person.gate_keeper = self.keeper
        self.events = []

    def send(self, start=OUTSIDE, goal=INSIDE):
        self.person.go_indoors(door(start))
        self.person.rest_left = 0.0
        assert self.person.begin_outing(self.nav.find_route(start, goal), door(goal))

    def run(self, seconds, until=None):
        for _ in range(int(seconds / FRAME)):
            was = self.gate.is_open
            self.person.update(FRAME, NOW)
            if self.gate.is_open != was:
                self.events.append(("open" if self.gate.is_open else "shut", round(self.person.feet[1])))
            if until is not None and until(self):
                return


def test_the_grid_leaves_the_gateway_open_and_a_route_runs_through_it():
    pen = Pen()
    assert not pen.gate.is_open and pen.nav.is_free_at(336, 328)
    route = pen.nav.find_route(OUTSIDE, INSIDE)
    [stop] = gate_stops(route, [pen.gate])
    assert stop.gate is pen.gate and stop.hi - stop.lo >= 16 + 2 * CLEAR_PX - 1


def test_a_path_past_the_gate_is_not_stopped_by_it():
    pen = Pen()
    assert gate_stops([(200.0, 300.0), (480.0, 300.0)], [pen.gate]) == []    # along the wall, a step off it


def test_he_opens_the_shut_gate_goes_through_and_shuts_it_behind_him():
    pen = Pen()
    pen.send()
    pen.run(20, until=lambda p: p.person.state == AT_HOME)
    assert [event for event, _ in pen.events] == ["open", "shut"]
    (_, opened_at), (_, shut_at) = pen.events
    assert opened_at < 320 and shut_at > 336                    # opened from the north, shut from the south
    assert not pen.gate.is_open and pen.person.state == AT_HOME and pen.person.feet == INSIDE


def test_a_gate_he_finds_open_he_shuts_behind_him_all_the_same():
    pen = Pen()
    pen.gate.set_open(True)
    pen.send()
    pen.run(20, until=lambda p: p.person.state == AT_HOME)
    assert [event for event, _ in pen.events] == ["shut"] and not pen.gate.is_open


def test_he_goes_through_it_the_other_way_too():
    pen = Pen()
    pen.send(INSIDE, OUTSIDE)
    pen.run(20, until=lambda p: p.person.state == AT_HOME)
    (_, opened_at), (_, shut_at) = pen.events
    assert opened_at > 336 and shut_at < 320 and pen.person.feet == OUTSIDE


def test_he_waits_for_whoever_stands_in_the_gateway_and_at_last_leaves_it_open(monkeypatch):
    monkeypatch.setattr(passing_module, "GIVE_UP_S", 3.0)
    pen = Pen()
    pen.bodies = [pygame.Rect(320, 322, 32, 14)]
    pen.send()
    pen.run(20, until=lambda p: p.person.gate_passing.phase == passing_module.SHUTTING)
    pen.run(2.0)
    assert pen.gate.is_open and pen.person.gate_passing.phase == passing_module.SHUTTING
    pen.run(20, until=lambda p: p.person.state == AT_HOME)
    assert pen.gate.is_open and [event for event, _ in pen.events] == ["open"]


def test_once_the_gateway_is_clear_he_shuts_it():
    pen = Pen()
    pen.bodies = [pygame.Rect(320, 322, 32, 14)]
    pen.send()
    pen.run(20, until=lambda p: p.person.gate_passing.phase == passing_module.SHUTTING)
    pen.run(1.0)
    assert pen.gate.is_open
    pen.bodies = []
    pen.run(20, until=lambda p: p.person.state == AT_HOME)
    assert [event for event, _ in pen.events] == ["open", "shut"]


def test_put_indoors_at_the_gate_he_shuts_what_he_opened():
    pen = Pen()
    pen.send()
    pen.run(20, until=lambda p: p.person.gate_passing.phase == passing_module.THROUGH)
    assert pen.gate.is_open
    pen.person.go_indoors(door(INSIDE))
    assert not pen.gate.is_open and not pen.person.gate_passing.active


def test_walking_a_path_backwards_as_a_homebody_walks_home_he_stops_at_the_gate_the_same():
    from src.models.figurines.patrol_path import PatrolPath
    pen = Pen()
    walker = pen.person
    path = PatrolPath(pen.nav.find_route(OUTSIDE, INSIDE), closed=False)
    walker.set_path(path, path.length)                        # inside the pen, heading out along it
    walker.walk_to_distance(0.0)
    for _ in range(int(20 / FRAME)):                          # as Homebody.update walks him
        was = pen.gate.is_open
        if not walker._pass_gates(FRAME) and not walker._follow_path(FRAME):
            break
        if pen.gate.is_open != was:
            pen.events.append(("open" if pen.gate.is_open else "shut", round(walker.feet[1])))
    (_, opened_at), (_, shut_at) = pen.events
    assert opened_at > 336 and shut_at < 320 and not pen.gate.is_open
    assert walker.path_distance == 0.0
