"""The quest for Flip on the map (models/lost_sheep_map.py), and the shepherdess's days at the fold.

On a made-up fold, island and gate: Flip slips out through the gate the player
opened once they are away with the fold out of sight, and grazes on the
island; on the leash he follows the player, is no obstacle, and once inside the
fold he walks back to his own strip, the shepherdess being there or not
deciding whether it was by day. Loading puts him where the quest has him. The
stall rota passes the shepherdess over on her fold days, she changes over only
while at home, keeps the fold's hours there and goes through its gate.
"""

import datetime
import math
import os
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from src.models import lost_sheep as ls
from src.models.figurines.animals.sheep import Sheep
from src.models.figurines.humans.npcs import trader_shepherdess as shepherdess_module
from src.models.figurines.humans.npcs.trader import AT_HOME, StallRota, Trader
from src.models.figurines.humans.npcs.trader_shepherdess import TraderShepherdess
from src.models.figurines.humans.npcs.trader_weaver import TraderWeaver
from src.models.figurines.patrol_path import PatrolPath
from src.models.gate import Gate
from src.models.lost_sheep import LostSheep
from src.models.lost_sheep_map import ESCAPED_NOW, HOME_NOW, LostSheepOnMap

TILE = 32
DAY = datetime.datetime(1500, 1, 4)
EVENING = DAY.replace(hour=21)
FOLD = pygame.Rect(1000, 1000, 400, 400)
ISLAND = pygame.Rect(100, 3000, 300, 32)
FLIP_ZONE = (1050, 1100, 300, 32)
FAR = (3000.0, 3000.0)


@pytest.fixture(autouse=True)
def pinned(monkeypatch):
    pygame.display.init()
    pygame.display.set_mode((1, 1))
    monkeypatch.setattr(ls, "sun_hour", lambda t: t.hour + t.minute / 60.0)
    monkeypatch.setattr(shepherdess_module, "sun_hour", lambda t: t.hour + t.minute / 60.0)
    monkeypatch.setattr(shepherdess_module, "FOLD_OUT_WINDOW", (7.0, 7.0))
    monkeypatch.setattr(shepherdess_module, "FOLD_IN_WINDOW", (19.0, 19.0))


def setup(shepherdess=None):
    flip = Sheep(*FLIP_ZONE, TILE, "dark", ls.FLIP)
    gate = Gate(1100, 1000, "", 2, 3, 1, 1, TILE, name=ls.FOLD_GATES[0], house_class="Gate")
    rects = {ls.FOLD_AREA: FOLD, ls.ISLAND_ZONE: ISLAND}
    tmx = SimpleNamespace(tile_size=TILE, npcs=[shepherdess] if shepherdess else [], houses=[gate],
                          sheep_named=lambda name: flip if name == ls.FLIP else None,
                          movement_rect=lambda name: rects.get(name))
    quest = LostSheep()
    return quest, LostSheepOnMap(quest, tmx), flip, gate


def test_flip_slips_out_through_the_gate_the_player_left_open_once_they_are_gone():
    quest, on_map, flip, gate = setup()
    gate.set_open(True)
    on_map.player_opened(gate)
    assert on_map.update(EVENING, (1200.0, 1200.0), None) is None          # still by the fold
    assert on_map.update(EVENING, FAR, pygame.Rect(900, 900, 600, 600)) is None   # the fold in sight
    assert on_map.update(EVENING, FAR, None) == ESCAPED_NOW
    assert quest.stage == ls.ESCAPED
    assert ISLAND.left <= flip.feet[0] <= ISLAND.right and flip.feet[1] == ISLAND.bottom


def test_a_gate_shut_before_the_evening_keeps_him_in():
    quest, on_map, flip, gate = setup()
    gate.set_open(True)
    on_map.player_opened(gate)
    gate.set_open(False)
    on_map.update(DAY.replace(hour=15), FAR, None)
    assert on_map.update(EVENING, FAR, None) is None and quest.stage == ls.QUIET


def lead(quest, on_map, player=(200.0, 3000.0)):
    quest.load({"stage": ls.LEADING, "missed_on": "1500-01-05"})
    on_map.sync(player)


def test_on_the_leash_he_follows_and_blocks_nobody():
    quest, on_map, flip, gate = setup()
    lead(quest, on_map)
    assert flip.leashed and math.dist(flip.feet, (200.0, 3000.0)) < 2 * TILE
    player = (200.0, 3000.0)
    for _ in range(240):
        player = (player[0] + 2.0, player[1])
        on_map.step_leash(1 / 60, player, 120.0)
    assert 30 < math.dist(flip.feet, player) < 80 and flip.direction == "right"
    hand, neck = on_map.rope_ends(SimpleNamespace(feet=player, width=32, height=54))
    assert hand[0] < player[0] and neck[0] < hand[0]


def test_led_at_a_steady_pace_his_walk_runs_on_and_goes_up_and_down_too():
    quest, on_map, flip, gate = setup()
    lead(quest, on_map)
    player = (200.0, 3000.0)
    moving, frames_seen = [], set()
    for step in range(360):
        # Right, then straight down
        player = (player[0] + 2.0, player[1]) if step < 180 else (player[0], player[1] + 2.0)
        on_map.step_leash(1 / 60, player, 120.0)
        flip.update(1 / 60)
        if step > 30:
            moving.append(flip.is_moving)
        if step > 250:
            frames_seen.add(flip.animator.current_frame_index)
    assert all(moving)                                   # never stopped and started afresh
    assert len(frames_seen) > 1 and flip.direction == "right"   # going down, still walking


def test_led_into_the_fold_he_goes_back_to_his_strip_and_by_day_she_was_there():
    her = SimpleNamespace(at_fold=True, is_hidden=False, keeps_fold=None)
    quest, on_map, flip, gate = setup()
    on_map.shepherdess = her
    lead(quest, on_map, (1100.0, 1300.0))
    flip.place_feet(1100.0, 1250.0)
    assert on_map.update(DAY.replace(hour=12), (1100.0, 1300.0), None) == HOME_NOW
    assert quest.stage == ls.RETURNED and not quest.at_night
    assert not flip.leashed and flip.in_home_zone and flip.walk_target is not None
    for _ in range(600):
        flip.update(1 / 60)
    assert flip.walk_target is None and flip.feet[1] == pytest.approx(FLIP_ZONE[1] + FLIP_ZONE[3])


def test_by_night_the_player_flocks_him_alone():
    quest, on_map, flip, gate = setup()
    lead(quest, on_map, (1100.0, 1300.0))
    flip.place_feet(1100.0, 1250.0)
    assert on_map.update(EVENING, (1100.0, 1300.0), None) == HOME_NOW
    assert quest.at_night


def test_loading_puts_him_where_the_quest_has_him():
    quest, on_map, flip, gate = setup()
    quest.load({"stage": ls.SEARCHING, "missed_on": "1500-01-05"})
    on_map.sync(FAR)
    assert flip.zone_foot_y == ISLAND.bottom and flip.name_known
    quest.load(None)
    on_map.sync(FAR)
    assert flip.in_home_zone and not flip.leashed and not flip.name_known


# ── The shepherdess ──────────────────────────────────────────────────────────

def shepherdess(fold_days=()):
    her = TraderShepherdess(0.0, 0.0, TILE)
    stall = PatrolPath([(0.0, 0.0), (64.0, 0.0), (64.0, 64.0), (0.0, 64.0)], closed=True)
    her.set_workplace(stall, None)
    her.set_homeway(PatrolPath([(0.0, 0.0), (0.0, 400.0)], closed=False))
    fold_round = PatrolPath([(500.0, 500.0), (600.0, 500.0), (600.0, 600.0), (500.0, 600.0)], closed=True)
    her.set_fold(fold_round, PatrolPath([(500.0, 500.0), (0.0, 400.0)], closed=False))
    her.keeps_fold = lambda day: day in fold_days
    return her


def test_the_rota_passes_her_over_on_her_fold_days():
    her = shepherdess(fold_days={DAY.date()})
    weaver = TraderWeaver(0.0, 0.0, TILE)
    rota = StallRota([her, weaver])
    for hour in range(24):
        assert rota.whose_turn(DAY.replace(hour=hour)) is weaver
    # Drawn for her already, she is swapped out once her fold day turns out to have begun
    other = shepherdess()
    rota = StallRota([other, TraderWeaver(0.0, 0.0, TILE)])
    rota.on_duty, rota.last_draw_date = other, DAY.strftime("%Y-%m-%d")
    other.keeps_fold = lambda day: True
    assert rota.whose_turn(DAY) is not other


def test_she_changes_over_only_at_home_and_keeps_the_folds_hours():
    her = shepherdess(fold_days={DAY.date()})
    her.update(1 / 30, DAY.replace(hour=12))           # unseen till now: she is placed, at the fold
    assert her.at_fold and her.passes_gates and not her.is_at_stall(DAY.replace(hour=12))
    assert her.stall_path is her.fold_round
    assert not her._off_duty(DAY.replace(hour=12)) and her._off_duty(DAY.replace(hour=20))
    # Next day is no fold day: she stays till she is home, then her stall is hers again
    tomorrow = DAY + datetime.timedelta(days=1)
    her.state = "At work"
    her.last_update_time = tomorrow.replace(hour=1)
    her.update(1 / 30, tomorrow.replace(hour=1))
    assert her.at_fold or her.state != "At work"
    her.state = AT_HOME
    her.last_update_time = tomorrow.replace(hour=2)
    her.update(1 / 30, tomorrow.replace(hour=2))
    assert not her.at_fold and her.stall_path is not her.fold_round and not her.passes_gates


def test_other_traders_are_never_kept_away():
    assert not Trader.kept_away(TraderWeaver(0.0, 0.0, TILE), DAY)
