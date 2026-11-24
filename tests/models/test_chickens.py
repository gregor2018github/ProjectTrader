"""The pen's chickens: the flock's looks (drawn, saved, loaded) and a chicken wandering its pen."""

import math
import random

import pygame
import pytest

from src.models.chickens import FLOCK_SIZE, ChickenLook, Flock, draw_flock
from src.models.figurines.animals import chicken_look
from src.models.figurines.animals.chicken import FLEE_TILES, SIZE_PX, Chicken
from src.models.figurines.animals.chicken_look import COLOUR_ODDS, COLOURS, FRAME, HEADS, TAILS

TILE = 32
PEN = pygame.Rect(0, 0, 10 * TILE, 8 * TILE)


@pytest.fixture(autouse=True, scope="module")
def _pygame():
    pygame.init()
    yield


def test_the_same_seed_draws_the_same_flock_and_another_seed_another():
    assert draw_flock(7) == draw_flock(7)
    assert len(draw_flock(7)) == FLOCK_SIZE
    assert draw_flock(7) != draw_flock(8)
    for look in draw_flock(7):
        assert look.head in HEADS and look.tail in TAILS and look.colour in COLOURS


def test_no_two_chickens_of_a_flock_look_the_same():
    assert all(len(set(draw_flock(seed))) == FLOCK_SIZE for seed in range(3000))
    assert len(set(draw_flock(1694322938))) == FLOCK_SIZE    # drew three alike before


def test_the_colours_are_drawn_by_their_odds_and_the_parts_evenly():
    assert sum(COLOUR_ODDS.values()) == 10_000 and set(COLOUR_ODDS) == set(COLOURS)
    rng = random.Random(1)
    drawn = [chicken_look.random_chicken(rng) for _ in range(20_000)]
    share = sum(colour == "buff" for _, _, colour in drawn) / len(drawn)
    assert share == pytest.approx(COLOUR_ODDS["buff"] / 10_000, abs=0.015)
    assert not any(colour == "rainbow" for _, _, colour in drawn[:100])  # 1 in 2,500
    assert {head for head, _, _ in drawn} == set(HEADS) and {tail for _, tail, _ in drawn} == set(TAILS)


def test_a_flock_is_saved_and_loaded_as_it_was():
    flock = Flock.new(3)
    loaded = Flock()
    loaded.load(flock.to_save(), seed=99)
    assert loaded.looks == flock.looks


def test_a_save_without_chickens_gets_the_flock_its_seed_draws():
    for data in (None, [], "nonsense"):
        flock = Flock()
        flock.load(data, seed=5)
        assert flock.looks == draw_flock(5)


def test_a_saved_look_naming_a_part_no_longer_there_is_drawn_afresh_alone():
    kept = ChickenLook("F", "fan", "white")
    flock = Flock()
    flock.load([kept.to_save(), {"head": "Z", "tail": "fan", "colour": "white"}], seed=5)
    assert flock.looks[0] == kept
    assert flock.looks[1] == draw_flock(5, 2)[1]


def test_every_frame_is_the_frame_size():
    poses = chicken_look.frames("A", "plume", "calico")
    for frame in [poses["stand"], *poses["walk"], *poses["peck"]]:
        assert frame.get_size() == (FRAME, FRAME)
    assert len(poses["walk"]) == 4 and len(poses["peck"]) == 2


def _chicken(seed=1):
    return Chicken(PEN, TILE, ChickenLook("F", "short", "buff"), rng=random.Random(seed))


def test_a_chicken_wanders_all_over_its_pen_and_never_out_of_it():
    chicken = _chicken()
    seen = set()
    for _ in range(20_000):                         # about 5.5 minutes at 60 frames a second
        chicken.update(1 / 60)
        x, y = chicken.feet
        assert PEN.left <= x <= PEN.right and PEN.top <= y <= PEN.bottom
        seen.add((int(x // (2 * TILE)), int(y // (2 * TILE))))
    assert len(seen) >= 12                          # of 5 x 4 blocks of 2 tiles
    assert chicken.sprite.get_size() == (SIZE_PX, SIZE_PX)


def test_it_runs_from_the_player_and_stays_in_its_pen_doing_so():
    chicken = _chicken()
    chicken.place_feet(PEN.centerx, PEN.centery)
    player = (PEN.centerx + TILE * 0.5, PEN.centery)
    chicken.update(1 / 60, player)
    assert chicken.fleeing and chicken.wants_sound == "alarm"
    for _ in range(60):
        chicken.update(1 / 60, player)
    assert math.dist(chicken.feet, player) > FLEE_TILES * TILE
    assert chicken.feet[0] < player[0]              # away from the player, to the west
    assert PEN.collidepoint(chicken.feet)


def test_it_faces_the_way_it_walks():
    chicken = _chicken()
    chicken.place_feet(PEN.centerx, PEN.centery)
    chicken._start("walk")
    chicken.target = (PEN.centerx + 3 * TILE, PEN.centery)
    chicken.update(1 / 60)
    assert chicken.direction == "right"
    chicken.target = (PEN.centerx - 3 * TILE, PEN.centery)
    chicken.update(1 / 60)
    assert chicken.direction == "left"
