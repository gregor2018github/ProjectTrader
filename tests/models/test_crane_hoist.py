"""The harbour cranes' hoists (models/crane_hoist.py): scenes, trips, the gate crane's hood, the swing.

A made-up crane throughout: its rope's top at y 100, the barge's waterline at
y 400, so a load lands well below; every random draw comes from a seeded
random.Random. The numbers a test relies on are pinned at the top.
"""

import os
import random

import pygame
import pytest

from src.models import crane_hoist as ch
from src.models.crane_hoist import (BARGE_FLOOR_ABOVE_WATER, BARGE_SLOTS, HANG, HOISTS, LOAD_SIZES, MAX_CARGO,
                                    RESCENE_UNSEEN_S, SLOT_OFFSETS, TOP_LENGTH, Hoist, working_hours)


def test_pinned_numbers():
    assert ch.HANG == 22 and ch.HOOK_HEIGHT == 13
    assert ch.TOP_LENGTH == 8.0 and ch.REST_LENGTH == 10.0 and ch.HOOD_REST_LENGTH == 4.0
    assert BARGE_SLOTS == 5 and MAX_CARGO == 4 and SLOT_OFFSETS == (-46, -23, 0, 23, 46)
    assert ch.RESCENE_UNSEEN_S == 30.0
    assert (ch.WORK_FROM, ch.WORK_TO) == (6.5, 19.0)


def jib(seed=1, **kwargs):
    return Hoist("Jib", 500, 100, 400, rng=random.Random(seed), **kwargs)


def gate_crane(seed=1):
    return Hoist("Gate", 500, 100, 400, stow_y=100, barge_shift=46, rng=random.Random(seed))


def run(hoist, seconds, seen=True, working=True, day=True, wind=0.0, step=1 / 30):
    for _ in range(round(seconds / step)):
        hoist.update(step, seen, working, day, wind)


# --- where it is -----------------------------------------------------------------------------------

def test_on_building_scales_the_rope_point_with_the_sprite():
    spec = ch.HoistSpec(rope_x=100, rope_top=40, waterline=-6)
    hoist = Hoist.on_building("Crane", 1000, 2000, sprite_height=400, scale=0.5, spec=spec,
                              rng=random.Random(0))
    assert (hoist.rope_x, hoist.rope_top) == (1050, 2000 - 200 + 20)
    assert hoist.waterline_y == 1994 and hoist.floor_y == 1994 - BARGE_FLOOR_ABOVE_WATER
    assert hoist.base_y == 2000


def test_a_barge_shift_must_put_a_slot_under_the_rope():
    assert gate_crane().hook_slot == 0
    assert gate_crane().slot_x(0) == 500
    assert jib().hook_slot == 2
    with pytest.raises(ValueError):
        jib(barge_shift=40)


def test_a_load_landing_stands_on_the_barge_floor():
    hoist = jib()
    for kind, (_, h) in LOAD_SIZES.items():
        length = hoist.landing_length(kind)
        assert hoist.rope_top + length + HANG + h == hoist.floor_y


def test_every_crane_sprite_has_its_rope_on_the_sprite():
    for file_name, spec in HOISTS.items():
        sprite = pygame.image.load(os.path.join("assets", "map_sprites", "houses", file_name))
        assert 0 <= spec.rope_x < sprite.get_width() and 0 <= spec.rope_top < sprite.get_height()
        assert -spec.barge_shift in SLOT_OFFSETS


def test_the_cargo_pictures_are_twice_their_world_size():
    for kind, (w, h) in LOAD_SIZES.items():
        picture = pygame.image.load(os.path.join("assets", "map_sprites", "cranes", f"{kind}.png"))
        assert picture.get_size() == (2 * w, 2 * h)
    for name in ("hook", "barge_back", "barge_front"):
        assert os.path.exists(os.path.join("assets", "map_sprites", "cranes", f"{name}.png"))


def test_working_hours():
    assert working_hours(12.0, 0.0, 0.0)
    assert not working_hours(5.0, 0.0, 0.0) and not working_hours(20.0, 0.0, 0.0)
    assert not working_hours(12.0, 0.5, 0.0)          # a thunderstorm
    assert not working_hours(12.0, 0.0, 0.9)          # a downpour
    assert working_hours(12.0, 0.0, 0.3)              # a drizzle does not stop it


# --- scenes ----------------------------------------------------------------------------------------

def test_the_scenes():
    hoist = jib()
    hoist.set_scene("idle")
    assert not hoist.barge and hoist.load is None and hoist.length == ch.REST_LENGTH
    hoist.set_scene("hanging")
    assert not hoist.barge and hoist.load in LOAD_SIZES
    assert TOP_LENGTH <= hoist.length < hoist.landing_length(hoist.load)
    for seed in range(30):
        hoist = jib(seed)
        hoist.set_scene("working")
        assert hoist.barge and 1 <= hoist.cargo + (hoist.load is not None) <= MAX_CARGO


def test_a_gate_crane_has_nothing_left_hanging():
    hoist = gate_crane()
    hoist.set_scene("hanging")
    assert hoist.load is None and hoist.length == ch.HOOD_REST_LENGTH


def test_no_barge_comes_by_night():
    hoist = jib()
    assert {hoist.draw_scene(False) for _ in range(200)} <= {"idle", "hanging"}


def test_a_scene_changes_only_while_nobody_sees_the_crane():
    hoist = jib(3)
    hoist.set_scene("idle")
    run(hoist, 300, seen=True)
    assert not hoist.barge and hoist.load is None     # watched: nothing comes or goes
    changed = False
    for seed in range(10):
        hoist = jib(seed)
        hoist.set_scene("idle")
        run(hoist, RESCENE_UNSEEN_S * 6, seen=False)
        changed |= hoist.barge or hoist.load is not None
    assert changed


# --- trips -----------------------------------------------------------------------------------------

def busy_jib(seed=2):
    hoist = jib(seed)
    hoist.set_scene("idle")
    hoist.barge = True
    hoist.slots = [None, "crate", None, None, None]
    hoist.wait = 0.0
    return hoist


def test_a_jib_crane_hoists_a_load_out_of_the_barge_and_holds_it_high():
    hoist = busy_jib()
    deepest = 0.0
    for _ in range(30 * 60):
        hoist.update(1 / 30, True, True, True, 0.0)
        deepest = max(deepest, hoist.length)
        if hoist.load is not None and not hoist.busy:
            break
    assert hoist.load == "crate" and hoist.cargo == 0
    assert deepest == pytest.approx(hoist.landing_length("crate"))
    assert hoist.length == TOP_LENGTH


def test_then_lowers_it_back_into_the_barge():
    hoist = busy_jib()
    lifted = False
    for _ in range(30 * 300):
        hoist.update(1 / 30, True, True, True, 0.0)
        lifted |= hoist.load is not None
        if lifted and hoist.load is None and not hoist.busy:
            break
    assert lifted and hoist.slots[hoist.hook_slot] == "crate"
    assert hoist.length == ch.REST_LENGTH


def test_a_load_is_shoved_under_the_hook_first():
    hoist = busy_jib()
    run(hoist, 0.1)
    assert hoist.slide is not None and hoist.slide[:3] == (1, 2, "crate")
    assert hoist.cargo == 1


def test_the_hook_takes_hold_of_the_load_before_lifting_it():
    hoist = busy_jib()
    seen = False
    for _ in range(30 * 60):
        hoist.update(1 / 30, True, True, True, 0.0)
        if hoist.hooking == "crate":
            seen = True
            assert hoist.length == pytest.approx(hoist.landing_length("crate"))
        if hoist.load:
            break
    assert seen


def test_no_trip_is_begun_out_of_working_hours():
    hoist = busy_jib()
    run(hoist, 120, working=False)
    assert hoist.load is None and hoist.length == ch.REST_LENGTH and hoist.cargo == 1


def test_a_gate_crane_stows_loads_in_its_hood_and_fetches_them_out():
    hoist = gate_crane(5)
    hoist.set_scene("idle")
    hoist.barge = True
    hoist.slots = ["sacks", "crate", "crate", "bale", None]
    hoist.wait = 0.0
    run(hoist, 60)                                      # a full barge: it must stow first
    assert hoist.cargo == 3
    stowed = fetched = False
    for _ in range(30 * 60 * 10):
        before = hoist.cargo
        hoist.update(1 / 30, True, True, True, 0.0)
        stowed |= hoist.cargo < before and hoist.slide is None and hoist.load is not None
        fetched |= hoist.cargo > before
        if hoist.load is not None and hoist.length <= hoist.inside_length:
            # Wholly up in the hood: out of sight
            assert hoist.rope_top + hoist.length + HANG + LOAD_SIZES[hoist.load][1] < hoist.stow_y
    assert stowed and fetched


def test_the_barge_never_overflows():
    for seed in range(20):
        for hoist in (jib(seed), gate_crane(seed)):
            hoist.set_scene("working")
            for i in range(30 * 600):
                hoist.update(1 / 30, (i // 1500) % 2 == 0, True, True, 0.2)
                assert hoist.cargo + (hoist.load is not None) <= MAX_CARGO


# --- the swing -------------------------------------------------------------------------------------

def test_the_wind_pushes_a_hanging_load_to_its_side():
    for wind in (0.3, -0.3):
        hoist = jib()
        hoist.set_scene("hanging")
        run(hoist, 40, working=False, wind=wind)
        assert hoist.angle * wind > 0
        assert abs(hoist.angle) < 0.2


def test_in_still_air_a_swing_dies_away():
    hoist = jib()
    hoist.set_scene("hanging")
    hoist.angle = 0.15
    run(hoist, 60, working=False)
    assert abs(hoist.angle) < 0.01
