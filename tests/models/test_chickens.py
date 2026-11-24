"""The pen's chickens: the flock (drawn, ageing, replaced, saved, loaded) and a chicken wandering its pen."""

import datetime
import math
import random

import pygame
import pytest

from src.models.chickens import (ADULT_DAYS, ADULT_KG, ADULT_SIZE, CHICK_SIZE, COLOUR_NAMES, FLOCK_SIZE, HEAD_NAMES,
                                 LIFESPAN_DAYS, TAIL_NAMES, ChickenLook, Flock, Hen, build, describe_age,
                                 describe_weight, draw_flock, rarity)
from src.models.figurines.animals import chicken_look
from src.models.figurines.animals.chicken import FLEE_TILES, SIZE_PX, Chicken
from src.models.figurines.animals.chicken_look import COLOUR_ODDS, COLOURS, FRAME_H, FRAME_W, HEADS, TAILS

TILE = 32
PEN = pygame.Rect(0, 0, 10 * TILE, 8 * TILE)


@pytest.fixture(autouse=True, scope="module")
def _pygame():
    pygame.init()
    yield


NOW = datetime.datetime(1500, 3, 1, 12, 0)


def test_the_same_seed_draws_the_same_flock_and_another_seed_another():
    assert draw_flock(7, NOW) == draw_flock(7, NOW)
    assert len(draw_flock(7, NOW)) == FLOCK_SIZE
    assert draw_flock(7, NOW) != draw_flock(8, NOW)
    for hen in draw_flock(7, NOW):
        look = hen.look
        assert look.head in HEADS and look.tail in TAILS and look.colour in COLOURS


def test_no_two_chickens_of_a_flock_look_the_same():
    assert all(len({hen.look for hen in draw_flock(seed, NOW)}) == FLOCK_SIZE for seed in range(2000))
    assert len({hen.look for hen in draw_flock(1694322938, NOW)}) == FLOCK_SIZE  # drew three alike before


def test_the_colours_are_drawn_by_their_odds_and_the_parts_evenly():
    assert sum(COLOUR_ODDS.values()) == 10_000 and set(COLOUR_ODDS) == set(COLOURS)
    rng = random.Random(1)
    drawn = [chicken_look.random_chicken(rng) for _ in range(20_000)]
    share = sum(colour == "buff" for _, _, colour in drawn) / len(drawn)
    assert share == pytest.approx(COLOUR_ODDS["buff"] / 10_000, abs=0.015)
    assert not any(colour == "rainbow" for _, _, colour in drawn[:100])  # 1 in 2,500
    assert {head for head, _, _ in drawn} == set(HEADS) and {tail for _, tail, _ in drawn} == set(TAILS)


def test_a_new_flock_is_of_all_ages_and_mostly_of_the_usual_size():
    hens = [hen for seed in range(400) for hen in draw_flock(seed, NOW)]
    lifespans = [hen.lifespan_days for hen in hens]
    assert min(lifespans) >= LIFESPAN_DAYS[0] and max(lifespans) <= LIFESPAN_DAYS[1]
    assert all(hen.hatched <= NOW and hen.dies > NOW for hen in hens)        # none dead yet
    young = sum(hen.age_days(NOW) < ADULT_DAYS for hen in hens) / len(hens)
    assert 0.08 < young < 0.3                       # now and then a chick
    sizes = [hen.adult_size for hen in hens]
    assert min(sizes) >= ADULT_SIZE[0] and max(sizes) <= ADULT_SIZE[1] and max(sizes) > 1.1
    big = sum(size > 1.12 for size in sizes) / len(sizes)
    small = sum(size < 0.88 for size in sizes) / len(sizes)
    usual = sum(0.94 <= size <= 1.06 for size in sizes) / len(sizes)
    assert big < 0.08 and small < 0.08 and usual > 0.55


def test_a_chick_is_small_and_pale_and_grows_into_its_own_size_and_colour():
    hen = Hen(ChickenLook("F", "fan", "black"), NOW, 100.0, 1.15)
    assert hen.size(NOW) == pytest.approx(CHICK_SIZE) and hen.youth(NOW) == 1.0
    half = NOW + datetime.timedelta(days=ADULT_DAYS / 2)
    assert CHICK_SIZE < hen.size(half) < 1.15 and 0 < hen.youth(half) < 1
    grown = NOW + datetime.timedelta(days=ADULT_DAYS)
    assert hen.size(grown) == pytest.approx(1.15) and hen.youth(grown) == 0.0
    chick = chicken_look.standing("F", "fan", "black", youth=1.0)
    adult = chicken_look.standing("F", "fan", "black")
    lightness = lambda s: sum(sum(s.get_at((x, y))[:3]) for x in range(FRAME_W) for y in range(FRAME_H)
                              if s.get_at((x, y)).a)
    assert lightness(chick) > 2 * lightness(adult)


def test_a_hen_whose_days_are_over_is_replaced_by_a_chick_hatched_that_day():
    flock = Flock.new(3, NOW)
    first = min(range(FLOCK_SIZE), key=lambda i: flock.hens[i].dies)
    old = flock.hens[first]
    assert flock.update(old.dies - datetime.timedelta(minutes=1)) == []
    assert flock.update(old.dies) == [first]
    chick = flock.hens[first]
    assert chick.hatched == old.dies and chick.youth(old.dies) == 1.0
    assert len(flock.hens) == FLOCK_SIZE and len(set(flock.looks)) == FLOCK_SIZE
    again = Flock.new(3, NOW)                       # the same game, the same chick
    again.update(old.dies)
    assert again.hens[first] == chick


def test_after_a_long_time_unseen_every_hen_is_one_alive_now():
    flock = Flock.new(4, NOW)
    later = NOW + datetime.timedelta(days=20 * LIFESPAN_DAYS[1])
    flock.update(later)
    assert all(hen.hatched <= later < hen.dies for hen in flock.hens)


def test_a_flock_is_saved_and_loaded_as_it_was():
    flock = Flock.new(3, NOW)
    loaded = Flock()
    loaded.load(flock.to_save(), seed=3, now=NOW + datetime.timedelta(days=50))
    assert loaded.hens == [Hen(h.look, h.hatched, round(h.lifespan_days, 3), round(h.adult_size, 4))
                           for h in flock.hens]


def test_a_save_without_chickens_gets_the_flock_its_seed_draws():
    for data in (None, [], "nonsense"):
        flock = Flock()
        flock.load(data, seed=5, now=NOW)
        assert flock.hens == draw_flock(5, NOW)


def test_a_save_with_only_the_looks_keeps_them_and_gets_the_rest_drawn():
    kept = ChickenLook("F", "fan", "white")
    flock = Flock()
    flock.load([kept.to_save(), {"head": "Z", "tail": "fan", "colour": "white"}], seed=5, now=NOW)
    spare = draw_flock(5, NOW)
    assert flock.hens[0] == Hen(kept, spare[0].hatched, spare[0].lifespan_days, spare[0].adult_size)
    assert flock.hens[1].look == spare[1].look


def test_every_frame_is_the_frame_size():
    poses = chicken_look.frames("A", "plume", "calico")
    for frame in [poses["stand"], *poses["walk"], *poses["peck"]]:
        assert frame.get_size() == (FRAME_W, FRAME_H)
    assert len(poses["walk"]) == 4 and len(poses["peck"]) == 3


def _chicken(seed=1, size=1.0, now=None):
    hen = Hen(ChickenLook("F", "short", "buff"), NOW, 100.0, size)
    return Chicken(PEN, TILE, hen, now, rng=random.Random(seed))


def test_a_chicken_wanders_all_over_its_pen_and_never_out_of_it():
    chicken = _chicken()
    seen = set()
    for _ in range(20_000):                         # about 5.5 minutes at 60 frames a second
        chicken.update(1 / 60)
        x, y = chicken.feet
        assert PEN.left <= x <= PEN.right and PEN.top <= y <= PEN.bottom
        seen.add((int(x // (2 * TILE)), int(y // (2 * TILE))))
    assert len(seen) >= 12                          # of 5 x 4 blocks of 2 tiles
    assert chicken.sprite.get_size() == (round(FRAME_W * SIZE_PX / 16), SIZE_PX)


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


def test_it_feeds_its_way_forward_and_turns_about_at_its_pens_edge():
    chicken = _chicken()
    chicken.place_feet(PEN.centerx, PEN.centery)
    chicken.direction = "left"
    chicken._start("peck")
    chicken.timer = 100.0
    x0 = chicken.feet[0]
    for _ in range(300):                            # 5 seconds of pecking
        chicken.update(1 / 60)
    assert x0 - 4 * TILE < chicken.feet[0] < x0 - 8   # a few small steps on to the west
    chicken.place_feet(PEN.left + 1, PEN.centery)
    for _ in range(300):
        chicken.update(1 / 60)
    assert chicken.direction == "right" and PEN.collidepoint(chicken.feet)


def test_the_eye_shows_when_it_pecks():
    for head in HEADS:
        for colour in ("buff", "black", "ghost"):
            eye = chicken_look.palette_of(colour)["E"]
            for frame in chicken_look.frames(head, "short", colour)["peck"]:
                pixels = [frame.get_at((x, y))[:3] for x in range(FRAME_W) for y in range(FRAME_H)
                          if frame.get_at((x, y)).a]
                assert tuple(eye) in pixels, (head, colour)


def test_a_chicken_on_the_map_grows_with_its_hen_its_feet_kept():
    chicken = _chicken(now=NOW)
    chick_height = chicken.sprite_height
    assert chick_height == round(SIZE_PX * CHICK_SIZE)
    chicken.place_feet(PEN.centerx, PEN.centery)
    feet = chicken.feet
    chicken.grow(NOW + datetime.timedelta(days=ADULT_DAYS))
    assert chicken.sprite_height == SIZE_PX and chicken.feet == pytest.approx(feet)
    assert chicken.sprite.get_height() == SIZE_PX
    big = _chicken(size=1.2, now=NOW + datetime.timedelta(days=ADULT_DAYS))
    assert big.sprite_height == round(SIZE_PX * 1.2)


def test_its_age_is_told_in_the_calendars_terms():
    assert describe_age(0.4) == "Hatched today"
    assert describe_age(1) == "1 day" and describe_age(3.9) == "3 days"
    assert describe_age(9) == "1 season and 2 days" and describe_age(14) == "2 seasons"
    assert describe_age(30) == "1 year and 2 days" and describe_age(64) == "2 years and 1 season"


def test_a_colours_rarity_and_a_hens_build_are_told_in_words():
    assert [rarity(c) for c in ("buff", "black", "blue", "golden", "mint", "lava", "midnight", "rainbow")] == [
        "Common", "Uncommon", "Uncommon", "Rare", "Rare", "Very rare", "Legendary", "Legendary"]
    assert [build(size) for size in (0.82, 0.9, 1.0, 1.08, 1.2)] == [
        "Small", "Smallish", "Average", "Large", "Very large"]
    assert set(COLOUR_NAMES) == set(COLOURS) and set(HEAD_NAMES) == set(HEADS) and set(TAIL_NAMES) == set(TAILS)


def test_it_weighs_by_its_size_cubed_and_a_chick_a_few_dozen_grams():
    hen = Hen(ChickenLook("F", "fan", "buff"), NOW, 100.0, 1.0)
    grown = NOW + datetime.timedelta(days=ADULT_DAYS)
    assert hen.weight_kg(grown) == pytest.approx(ADULT_KG)
    assert Hen(hen.look, NOW, 100.0, 1.2).weight_kg(grown) == pytest.approx(ADULT_KG * 1.2 ** 3)
    assert 0.03 < hen.weight_kg(NOW) < 0.08
    assert describe_weight(hen.weight_kg(NOW)) == "60 g" and describe_weight(2.234) == "2.2 kg"


def test_its_stage_of_life():
    hen = Hen(ChickenLook("F", "fan", "buff"), NOW, 100.0, 1.0)
    at = lambda days: hen.stage(NOW + datetime.timedelta(days=days))
    assert [at(1), at(ADULT_DAYS - 1), at(40), at(90)] == ["Chick", "Young hen", "Hen", "Old hen"]


def test_walking_mostly_up_or_down_it_faces_the_back_or_the_front_and_feeds_its_way_on_so():
    chicken = _chicken()
    chicken.place_feet(PEN.centerx, PEN.centery)
    chicken._start("walk")
    chicken.target = (PEN.centerx + TILE, PEN.centery + 3 * TILE)       # mostly down the picture
    chicken.update(1 / 60)
    assert chicken.direction == "front"
    chicken.target = (PEN.centerx - TILE, PEN.centery - 3 * TILE)       # mostly up it
    chicken.update(1 / 60)
    assert chicken.direction == "back"
    assert chicken.sprite is chicken._sized[id(chicken.poses["back"]["walk"][chicken.frame_index])]
    chicken.place_feet(PEN.centerx, PEN.centery)
    chicken._start("peck")
    chicken.timer = 100.0
    y0 = chicken.feet[1]
    for _ in range(300):
        chicken.update(1 / 60)
    assert chicken.feet[1] < y0 - 8 and chicken.feet[0] == pytest.approx(PEN.centerx)   # on up the picture


def test_seen_from_the_front_and_behind_every_frame_is_the_frame_size_and_every_tail_its_own():
    backs = set()
    for tail in TAILS:
        for view in ("front", "back"):
            poses = chicken_look.upright_frames(view, "F", tail, "buff")
            for frame in [poses["stand"], *poses["walk"], *poses["peck"]]:
                assert frame.get_size() == (FRAME_W, FRAME_H)
        backs.add(pygame.image.tobytes(chicken_look.upright_frames("back", "F", tail, "buff")["stand"], "RGBA"))
    assert len(backs) == len(TAILS)
