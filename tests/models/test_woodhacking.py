"""The woodhacking minigame's chopping scene, and how the game waits for it."""

import math
import random
from types import SimpleNamespace

import pygame
import pytest

from src.models.minigames import woodhacking as wh
from src.models.minigames.woodhacking_scene import BITE, SHORT, SPLIT, WHIFF, ChoppingScene

DT = 1 / 60


@pytest.fixture(scope="module", autouse=True)
def fonts():
    pygame.font.init()
    yield


@pytest.fixture
def scene():
    return ChoppingScene(pygame.font.SysFont(None, 20), random.Random(0))


def run(scene, seconds):
    sounds = []
    for _ in range(round(seconds / DT)):
        sounds += scene.update(DT)
    return sounds


def swing(scene, outcome, power=0.6):
    scene.charge(power)
    run(scene, 0.3)
    return scene.swing(outcome, 3)


@pytest.mark.parametrize("points, power, expected", [
    (5, 0.6, SPLIT), (3, 0.6, SPLIT), (2, 0.6, BITE), (1, 0.3, BITE),
    (0, 0.1, SHORT), (0, 0.9, WHIFF),
])
def test_the_grade_decides_what_the_axe_does(points, power, expected):
    assert wh.swing_outcome(points, power, opt_lo=0.57) == expected


def test_a_split_chops_on_impact_and_stacks_the_log(scene):
    assert swing(scene, SPLIT) == []           # no swish for a blow that lands
    sounds = run(scene, 0.15)
    assert "chop" in sounds
    assert scene.pile == 1
    assert not scene.log_ready                 # the next log is on its way
    run(scene, 2.0)
    assert scene.log_ready and scene.settled


def test_a_miss_swishes_at_once_and_leaves_the_log(scene):
    assert swing(scene, WHIFF) == ["swoosh"]
    assert "chop" not in run(scene, 2.0)
    assert scene.pile == 0 and scene.log_damage == 0


def test_the_second_bite_splits_the_log(scene):
    swing(scene, BITE)
    run(scene, 2.0)
    assert scene.log_damage == 1 and scene.pile == 0
    swing(scene, BITE)
    run(scene, 2.0)
    assert scene.log_damage == 0 and scene.pile == 1


def test_no_new_swing_until_the_last_one_has_landed(scene):
    swing(scene, SPLIT)
    assert not scene.can_charge
    run(scene, 0.6)
    assert scene.can_charge


def test_the_blade_lands_on_the_log(scene):
    """The axe's length and strike angle are worked out so the blade meets the log's top."""
    from src.models.minigames import woodhacking_scene as ws
    swing(scene, SPLIT)
    while scene.state == "swing":
        scene.update(DT)
    head = scene._axe_head()
    assert abs(head.x - ws._BLOCK_CX) < ws._LOG_W / 2
    assert ws._LOG_TOP - 40 < head.y < ws._LOG_TOP


def test_the_scene_draws_every_moment(scene):
    for outcome in (SPLIT, BITE, WHIFF, SHORT):
        scene.charge(1.0)
        for _ in range(30):
            scene.update(DT)
            scene.draw()
        scene.swing(outcome, 2)
        for _ in range(90):
            scene.update(DT)
            scene.draw()


def _game(tips_seen=(wh.TIP_TUTORIAL, wh.TIP_DOUBLE_PERFECT)):
    """A stand-in game; the how-to page and the explanation of a perfect blow count as seen unless the test says not."""
    stats = SimpleNamespace(woodhacking_highscore=0, minigames_played=0, minigame_income_total=0.0,
                            minigame_tips_seen=list(tips_seen))
    booked = []
    depot = SimpleNamespace(stats=stats, book_labor_income=lambda coins, name: booked.append(coins))
    game = SimpleNamespace(depot=depot, state=SimpleNamespace(log_event=lambda *a: None),
                           sounds={}, play_sound=lambda name: None)
    return game, booked


def test_the_result_waits_for_the_last_swing_to_settle(monkeypatch):
    monkeypatch.setattr(wh, "on_money_received", lambda *a, **k: None)
    game, booked = _game()
    minigame = wh.WoodhackingMinigame(pygame.Surface((10, 10)), game)
    down = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(0, 0))
    up = pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(0, 0))
    while minigame.attempt < minigame.total_swings:   # extra swings earned included
        while not minigame.scene.can_charge:
            minigame.update(DT)
        minigame.handle_event(down)
        for _ in range(50):
            minigame.update(DT)
        minigame.aim = 0.0                       # dead centre
        minigame.handle_event(up)
    assert minigame.attempt == minigame.total_swings >= wh.MAX_SWINGS
    assert not minigame.done                     # the last log is still flying
    minigame.handle_event(down)
    assert not minigame.charging                 # no swing beyond the last
    for _ in range(round(5 / DT)):
        minigame.update(DT)
        if minigame.done:
            break
    assert minigame.done
    assert game.depot.stats.minigames_played == 1
    assert len(booked) <= 1


# ── The streak ────────────────────────────────────────────────────────────────

@pytest.fixture
def minigame(monkeypatch):
    monkeypatch.setattr(wh, "on_money_received", lambda *a, **k: None)
    monkeypatch.setattr(wh, "STREAK_BONUS", 0.05)
    game, _ = _game()
    return wh.WoodhackingMinigame(pygame.Surface((10, 10)), game)


def _swing(minigame, perfect: bool):
    """One swing: dead centre and in the power's sweet spot (5 points, a split),
    or far too weak (nothing). Waits for the scene to take the next one."""
    while not minigame.scene.can_charge or not minigame.scene.log_ready:
        minigame.update(DT)
    minigame.aim = 0.0
    minigame.power = (minigame.opt_lo + minigame.opt_hi) / 2 if perfect else 0.01
    minigame._resolve_swing()
    for _ in range(round(1.5 / DT)):
        minigame.update(DT)


def test_each_split_in_a_row_adds_five_percent_to_the_next_swing(minigame):
    _swing(minigame, True)
    assert minigame.last_gain == 5 and minigame.streak == 1
    _swing(minigame, True)
    assert minigame.last_gain == pytest.approx(5.25) and minigame.streak == 2
    _swing(minigame, True)
    assert minigame.last_gain == pytest.approx(5.5) and minigame.streak == 3
    assert minigame.score == pytest.approx(15.75)


def test_a_swing_that_splits_nothing_ends_the_streak(minigame):
    for _ in range(3):
        _swing(minigame, True)
    _swing(minigame, False)
    assert minigame.streak == 0 and minigame.last_gain == 0
    _swing(minigame, True)
    assert minigame.last_gain == 5                # no bonus left
    assert minigame.best_streak == 3


def _fair_swing(minigame):
    """Fair aim (1 point) and power just under the sweet spot (1 point): the axe bites."""
    while not minigame.scene.can_charge or not minigame.scene.log_ready:
        minigame.update(DT)
    minigame.aim = math.radians(30)
    minigame.power = minigame.opt_lo - 0.05
    minigame._resolve_swing()
    for _ in range(round(1.5 / DT)):
        minigame.update(DT)


def test_a_bite_ends_the_streak_and_the_second_bite_splits_and_starts_one(minigame):
    _swing(minigame, True)
    _fair_swing(minigame)
    assert minigame.scene.log_damage == 1
    assert minigame.streak == 0
    assert minigame.last_gain == pytest.approx(2.1)   # the bite still had the split's 5%
    _fair_swing(minigame)                              # the cracked log splits
    assert minigame.scene.pile == 2
    assert minigame.streak == 1


def test_the_woodpile_has_room_for_a_split_from_every_swing():
    from src.models.minigames import woodhacking_scene as ws
    assert ws._PILE_ROWS * (ws._PILE_ROWS + 1) // 2 >= wh.MAX_SWINGS


# ── Perfect swings ────────────────────────────────────────────────────────────

def test_a_swing_perfect_on_both_gauges_rings_and_holds_still(scene):
    scene.charge(0.6)
    run(scene, 0.3)
    scene.swing(SPLIT, 5, flourish=2)
    sounds = []
    while scene.state == "swing":
        sounds += scene.update(DT)
    assert sounds == ["chop", "ring"]
    angle = scene.angle
    scene.update(DT)                           # the heartbeat: nothing moves
    assert scene.angle == angle and scene.motes
    run(scene, 3.0)
    assert scene.settled                       # the motes and the glow are gone again


def test_an_ordinary_split_does_not_ring(scene):
    swing(scene, SPLIT)
    assert "ring" not in run(scene, 2.0)
    assert not scene.motes


def test_each_perfect_gauge_glints(minigame):
    minigame.aim = 0.0                         # dead centre and the sweet spot's middle
    minigame.power = (minigame.opt_lo + minigame.opt_hi) / 2
    minigame._resolve_swing()
    assert sorted(g["kind"] for g in minigame.glints) == ["aim", "power"]
    assert minigame.scene.flourish == 2
    while not minigame.scene.can_charge or not minigame.scene.log_ready:
        minigame.update(DT)
    minigame.aim = 0.0
    minigame.power = minigame.opt_lo - 0.05    # aim perfect, power only good
    minigame._resolve_swing()
    assert [g["kind"] for g in minigame.glints] == ["aim"]
    assert minigame.scene.flourish == 0
    for _ in range(round(wh._GLINT_S / DT) + 1):
        minigame.update(DT)
    assert minigame.glints == []


# ── The time of day ───────────────────────────────────────────────────────────

def _scene_at(hour: int) -> ChoppingScene:
    import datetime
    return ChoppingScene(pygame.font.SysFont(None, 20), random.Random(0), when=datetime.datetime(1500, 1, 4, hour))


def test_at_noon_the_lanterns_are_out_and_no_stars_show():
    scene = _scene_at(12)
    assert scene.lanterns == 0 and scene.night == 0


def test_at_midnight_the_lanterns_burn_and_the_stars_show():
    scene = _scene_at(0)
    assert scene.lanterns == 1 and scene.night == 1
    scene.draw()


def test_the_night_is_darker_than_the_day_but_the_gauges_still_get_light():
    day, night = _scene_at(12), _scene_at(0)
    x, y = 71, 380                      # low on the power post, away from its lantern
    assert sum(night._lightmap.get_at((x, y))[:3]) < sum(day._lightmap.get_at((x, y))[:3])
    assert min(night._lightmap.get_at((x, y))[:3]) > 60


# ── Chips, the extra swing and the explanation ────────────────────────────────

def test_the_chips_of_each_blow_stay_round_the_stump(scene):
    swing(scene, SPLIT)
    run(scene, 2.0)
    first = scene.chips_lying
    assert first > 0
    swing(scene, SPLIT)
    run(scene, 2.0)
    assert scene.chips_lying > first


def test_a_swing_perfect_on_both_gauges_earns_an_extra_swing(minigame):
    _swing(minigame, True)
    assert minigame.extra_swings == 1 and minigame.total_swings == wh.MAX_SWINGS + 1
    _fair_swing(minigame)
    assert minigame.extra_swings == 1


def test_the_first_perfect_blow_is_explained_once_and_waits_for_ok(monkeypatch):
    monkeypatch.setattr(wh, "on_money_received", lambda *a, **k: None)
    game, _ = _game(tips_seen=(wh.TIP_TUTORIAL,))
    m = wh.WoodhackingMinigame(pygame.Surface((10, 10)), game)
    m.aim, m.power = 0.0, (m.opt_lo + m.opt_hi) / 2
    m._resolve_swing()
    for _ in range(round(1.2 / DT)):
        m.update(DT)
    assert m.tip_open
    assert game.depot.stats.minigame_tips_seen == [wh.TIP_TUTORIAL, wh.TIP_DOUBLE_PERFECT]
    aim = m.aim
    m.update(DT)
    assert m.aim == aim                          # the game waits
    m.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(0, 0)))
    assert m.tip_open and not m.charging         # a click beside OK does nothing
    m.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    assert not m.tip_open
    # The next perfect blow is not explained again
    while not m.scene.can_charge or not m.scene.log_ready:
        m.update(DT)
    m.aim, m.power = 0.0, (m.opt_lo + m.opt_hi) / 2
    m._resolve_swing()
    for _ in range(round(1.2 / DT)):
        m.update(DT)
    assert not m.tip_open


def test_after_the_last_swing_the_bob_comes_to_rest_before_the_result(monkeypatch):
    monkeypatch.setattr(wh, "on_money_received", lambda *a, **k: None)
    monkeypatch.setattr(wh, "MAX_SWINGS", 1)
    game, _ = _game()
    m = wh.WoodhackingMinigame(pygame.Surface((10, 10)), game)
    assert m.attempt == m.total_swings - 1                     # the hint says: last swing
    m.aim, m.power = math.radians(40), 0.01                    # far off, too weak: a miss, no extra swing
    m._resolve_swing()
    assert m._ending
    m.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(0, 0)))
    assert not m.charging                                      # the axe is not taken up again
    swings, last_side = 0, None
    while not m._pendulum_still:
        m.update(DT)
        side = m.aim > 0
        if last_side is not None and side != last_side:
            swings += 1
        last_side = side
        assert not m.done                                      # no result while the bob still swings
    assert m.aim == 0.0 and swings >= 1                        # it swung out before hanging still
    for _ in range(round(1.0 / DT)):
        m.update(DT)
    assert m.done


def test_a_notice_warns_when_three_swings_are_left(monkeypatch):
    monkeypatch.setattr(wh, "on_money_received", lambda *a, **k: None)
    monkeypatch.setattr(wh, "MAX_SWINGS", 5)
    game, _ = _game()
    m = wh.WoodhackingMinigame(pygame.Surface((10, 10)), game)
    m.aim, m.power = math.radians(40), 0.01                    # misses: no extra swings
    m._resolve_swing()
    assert m.notice is None                                    # 4 left
    m.aim, m.power = math.radians(40), 0.01
    m._resolve_swing()
    assert m.notice is not None and m.notice[0] == "3 swings left"
    for _ in range(round((wh._NOTICE_S + 0.1) / DT)):
        m.update(DT)
    assert m.notice is None
    m.aim, m.power = math.radians(40), 0.01
    m._resolve_swing()
    assert m.notice is None                                    # 2 left: no notice again


# ── Time passes at work ───────────────────────────────────────────────────────

def _timed_minigame(monkeypatch, swings=4):
    import datetime
    monkeypatch.setattr(wh, "on_money_received", lambda *a, **k: None)
    monkeypatch.setattr(wh, "MAX_SWINGS", swings)
    monkeypatch.setattr(wh, "HOURS_OF_WORK", 4.0)
    game, booked = _game()
    game.state.date = datetime.datetime(1500, 1, 4, 10, 0)
    return wh.WoodhackingMinigame(pygame.Surface((10, 10)), game), game, booked


def _miss(m):
    m.aim, m.power = math.radians(40), 0.01
    m._resolve_swing()


def test_back_on_the_map_after_a_whole_session_four_hours_have_passed(monkeypatch):
    m, game, _ = _timed_minigame(monkeypatch)
    for _ in range(4):
        _miss(m)
    for _ in range(round(6 / DT)):
        m.update(DT)
        if m.done:
            break
    m.close_rect.center = (50, 50)
    m.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(50 + m.canvas_rect.left, 50 + m.canvas_rect.top)))
    assert not m.active
    assert game.state.date.hour == 14 and game.state.date.minute == 0


def test_leaving_early_takes_the_share_of_the_hours_worked(monkeypatch):
    m, game, _ = _timed_minigame(monkeypatch)
    _miss(m)                                   # one of four swings
    _press(m, pygame.K_ESCAPE)
    _press(m, pygame.K_RETURN)
    assert not m.active and game.state.date.hour == 11


def test_leaving_before_the_first_swing_takes_no_time(monkeypatch):
    m, game, _ = _timed_minigame(monkeypatch)
    _press(m, pygame.K_ESCAPE)
    _press(m, pygame.K_RETURN)
    assert not m.active
    assert game.state.date.hour == 10 and game.state.date.minute == 0


def _press(m, key):
    m.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key))


def _click(m, rect, kind=pygame.MOUSEBUTTONDOWN):
    pos = (rect.centerx + m.canvas_rect.left, rect.centery + m.canvas_rect.top)
    m.handle_event(pygame.event.Event(kind, button=1, pos=pos))


def test_escape_asks_first_and_the_game_waits_for_the_answer(monkeypatch):
    m, _, _ = _timed_minigame(monkeypatch)
    _press(m, pygame.K_ESCAPE)
    assert m.active and m.exit_asked
    aim = m.aim
    m.update(DT)
    assert m.aim == aim
    m.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(0, 0)))
    assert m.exit_asked and not m.charging       # a click beside the buttons does nothing


@pytest.mark.parametrize("answer", ["key", "button"])
def test_going_back_carries_on_with_the_session(monkeypatch, answer):
    m, _, _ = _timed_minigame(monkeypatch)
    _miss(m)
    _press(m, pygame.K_ESCAPE)
    if answer == "key":
        _press(m, pygame.K_ESCAPE)
    else:
        _click(m, m.exit_back_rect)
    assert m.active and not m.exit_asked and m.attempt == 1
    assert not m.charging                        # the click answering is no swing


def test_exiting_early_pays_nothing_and_is_no_session_played(monkeypatch):
    m, game, booked = _timed_minigame(monkeypatch)
    m.aim, m.power = math.radians(-5), (m.opt_lo + m.opt_hi) / 2     # a good swing, worth points
    m._resolve_swing()
    assert m.score > 0
    _press(m, pygame.K_ESCAPE)
    _click(m, m.exit_yes_rect)
    assert not m.active
    assert booked == [] and game.depot.stats.minigames_played == 0
    assert game.depot.stats.woodhacking_highscore == 0


def test_escape_while_gathering_power_lets_the_swing_go_unswung(monkeypatch):
    m, _, _ = _timed_minigame(monkeypatch)
    _click(m, pygame.Rect(0, 200, 2, 2))
    m.update(DT)
    assert m.charging
    _press(m, pygame.K_ESCAPE)
    assert not m.charging and m.power == 0.0
    _click(m, pygame.Rect(0, 200, 2, 2), pygame.MOUSEBUTTONUP)
    _press(m, pygame.K_ESCAPE)
    assert m.attempt == 0                        # no swing was made of it


def test_leaving_right_after_the_last_swing_still_pays_and_takes_the_hours(monkeypatch):
    m, game, booked = _timed_minigame(monkeypatch, swings=1)
    m.aim, m.power = math.radians(-5), (m.opt_lo + m.opt_hi) / 2   # very good aim: a split, no extra swing
    m._resolve_swing()
    assert m._ending and not m.done
    m.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    assert game.depot.stats.minigames_played == 1
    assert game.state.date.hour == 14
