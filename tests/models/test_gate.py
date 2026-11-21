"""A gate in a wall (models/gate.py), as the churchyard's: it blocks only while shut, won't shut on
someone in the gateway, is drawn in order with its wall, and plays its sound if it has one; and the churchyard's two on the map."""

import random
import xml.etree.ElementTree as ET
from pathlib import Path

import pygame
import pytest

from src.models.gate import OPEN_DOWN_SORT, Gate

ROOT = Path(__file__).resolve().parents[2]
HOUSES = ROOT / "assets" / "map_sprites" / "houses"


def _gate(opens="down"):
    # The churchyard's north gate without its pictures: its point (6032, 4400), its gateway
    # (6041, 4360) 45 x 16, drawn in order 16 px up, with the wall
    return Gate(6032, 4400, "", 2, 3, 1, 1, 32, name="Gate_Test", house_class="Gate",
                col_margin_left_pixel=-9, col_margin_right_pixel=22,
                col_margin_up_pixel=8, col_margin_down_pixel=-24,
                opens=opens, sort_up_pixel=16)


def _in_gateway(gate):
    box = gate.collision_rect
    return pygame.Rect(box.centerx - 16, box.bottom - 14, 32, 14)


def test_the_gateway_is_the_collision_box_and_blocks_while_shut():
    gate = _gate()
    assert gate.collision_rect == pygame.Rect(6041, 4360, 45, 16)
    assert not gate.is_open
    assert _in_gateway(gate).collidelist(gate.collision_rects) >= 0


def test_opened_it_blocks_nothing_but_keeps_its_box_for_the_reach():
    gate = _gate()
    assert gate.toggle([])
    assert gate.is_open and gate.collision_rects == []
    assert gate.collision_rect == pygame.Rect(6041, 4360, 45, 16)


def test_it_will_not_shut_on_someone_in_the_gateway():
    gate = _gate()
    gate.toggle([])
    assert not gate.toggle([_in_gateway(gate)])
    assert gate.is_open
    beside = _in_gateway(gate).move(0, 40)
    assert gate.toggle([beside])
    assert not gate.is_open and gate.collision_rects


def test_it_sorts_with_its_wall_and_a_little_lower_open_towards_the_viewer():
    down, up = _gate("down"), _gate("up")
    assert down.y_sort == up.y_sort == 4384
    down.toggle([])
    up.toggle([])
    assert down.y_sort == 4384 + OPEN_DOWN_SORT
    assert up.y_sort == 4384


def test_anything_but_up_opens_down():
    assert _gate("UP ").opens == "up"
    assert _gate("sideways").opens == "down"


def test_it_plays_a_take_of_its_own_sounds_open_or_shut_and_none_while_it_has_none():
    gate = _gate()
    rng = random.Random(1)
    available = {"gate_open", "gate_open_2", "gate_close_1", "gate_opener", "door_1"}
    gate.toggle([])
    assert gate.sound(available, rng) in {"gate_open", "gate_open_2"}
    gate.toggle([])
    assert gate.sound(available, rng) == "gate_close_1"
    assert gate.sound({"door_1", "knock_1"}) is None


def test_without_pictures_it_has_no_hit_box():
    assert _gate().hit_box() is None


@pytest.fixture(scope="module")
def map_gates():
    root = ET.parse(ROOT / "assets" / "tiles" / "Map1.tmx").getroot()
    houses = next(g for g in root.iter("objectgroup") if g.get("name") == "Houses")
    return {obj.get("name"): {p.get("name"): p.get("value") for p in obj.iter("property")}
            for obj in houses.iter("object") if obj.get("type") == "Gate"}


def test_the_map_has_its_gates_with_both_pictures(map_gates):
    assert set(map_gates) == {"Gate_Churchyard_North", "Gate_Churchyard_South", "Gate_Farm_Field_North",
                              "Gate_Sheep_Yard_North", "Gate_Sheep_Yard_South"}
    assert map_gates["Gate_Churchyard_North"]["Opens"] == "down"   # into the yard, south of it
    assert map_gates["Gate_Churchyard_South"]["Opens"] == "up"     # into the yard, north of it
    assert map_gates["Gate_Farm_Field_North"]["Opens"] == "down"   # into the field
    assert map_gates["Gate_Sheep_Yard_North"]["Opens"] == "down"   # into the sheep's yard
    assert map_gates["Gate_Sheep_Yard_South"]["Opens"] == "up"
    for props in map_gates.values():
        for key in ("File_name", "Open_file_name"):
            assert (HOUSES / props[key]).is_file(), props[key]


def test_a_gate_is_never_named_as_something_the_map_loads_otherwise(map_gates):
    for name in map_gates:
        assert not name.startswith(("Church", "Townhall", "Mill", "Well", "Bank", "Fence"))
        assert "Market" not in name
