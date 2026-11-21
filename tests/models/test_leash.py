"""A sheep on the leash (models/leash.py): it keeps to the player's trail, a little behind them,
stands while they are near, catches up, is put behind them if left far, and the rope sags with
its slack and runs straight once taut."""

import math

import pytest

from src.models import leash
from src.models.leash import Leash, rope_points

FRAME = 1 / 60
SPEED = 120.0


def walked(points, step=2.0):
    """The trail of a walk through `points`, every `step` px."""
    trail = Leash()
    trail.reset(points[0])
    for a, b in zip(points, points[1:]):
        n = max(1, int(math.dist(a, b) / step))
        for i in range(1, n + 1):
            trail.record((a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n))
    return trail


def test_the_target_lies_behind_the_player_along_their_trail_round_a_corner():
    trail = walked([(0.0, 0.0), (100.0, 0.0), (100.0, 20.0)])
    x, y = trail.target(leash.FOLLOW_GAP)
    # 20 px down the second leg, the rest back along the first
    assert y == pytest.approx(0.0, abs=0.5)
    assert x == pytest.approx(100.0 - (leash.FOLLOW_GAP - 20.0), abs=1.0)


def test_only_the_last_stretch_of_trail_is_kept():
    trail = Leash()
    trail.reset((0.0, 0.0))
    trail.progress = 1900.0                  # the sheep has kept up: nothing behind it is needed
    for i in range(1, 1001):
        trail.record((2.0 * i, 0.0))
    kept = sum(math.dist(a, b) for a, b in zip(list(trail.trail), list(trail.trail)[1:]))
    assert leash.TRAIL_KEEP <= kept <= leash.TRAIL_KEEP + 2 * leash.TRAIL_STEP


def test_it_stands_while_the_player_is_near():
    trail = walked([(0.0, 0.0), (30.0, 0.0)])
    spot, moved = trail.step((0.0, 0.0), (30.0, 0.0), SPEED, FRAME)
    assert spot == (0.0, 0.0) and not moved


def test_it_keeps_up_with_a_walking_player_and_never_strays_off_the_trail():
    trail = Leash()
    player = (0.0, 0.0)
    sheep = (-leash.FOLLOW_GAP, 0.0)
    trail.reset(player, sheep)
    worst = 0.0
    for frame in range(600):
        player = (player[0] + SPEED * FRAME, 0.0) if frame < 300 else (player[0], player[1] + SPEED * FRAME)
        trail.record(player)
        sheep, _ = trail.step(sheep, player, SPEED, FRAME)
        worst = max(worst, math.dist(sheep, player))
        # Along the L the player walked, never across its corner: on the first leg or the second
        assert abs(sheep[1]) < 0.01 or abs(sheep[0] - player[0]) < 0.01
    assert worst < leash.LENGTH + 5


def test_left_far_behind_it_is_put_behind_the_player():
    trail = walked([(0.0, 0.0), (400.0, 0.0)])
    spot, moved = trail.step((-500.0, 0.0), (400.0, 0.0), SPEED, FRAME)
    assert not moved and math.dist(spot, (400.0, 0.0)) <= leash.FOLLOW_GAP + 1


def test_taut_it_hurries_more_than_slack():
    trail = walked([(0.0, 0.0), (300.0, 0.0)])
    slack_at = 300.0 - (leash.FOLLOW_GAP + leash.LENGTH) / 2      # between its spot and the rope's length
    taut_at = 300.0 - leash.LENGTH - 30
    slack, _ = trail.step((slack_at, 0.0), (300.0, 0.0), SPEED, FRAME)
    taut, _ = trail.step((taut_at, 0.0), (300.0, 0.0), SPEED, FRAME)
    assert taut[0] - taut_at > slack[0] - slack_at > 0


def test_ahead_of_its_spot_it_waits_rather_than_backing_off():
    trail = walked([(0.0, 0.0), (300.0, 0.0)])
    ahead = (300.0 - leash.FOLLOW_GAP + 3, 0.0)
    assert trail.step(ahead, (300.0, 0.0), SPEED, FRAME) == (ahead, False)


def test_the_trail_it_still_has_to_walk_is_never_forgotten():
    trail = walked([(0.0, 0.0), (2000.0, 0.0)])
    assert trail.trail[0] == (0.0, 0.0)


def test_where_the_trail_doubles_back_it_neither_jumps_nor_shakes():
    # Out to the right and back past the sheep: it must not hop between the two legs
    trail = Leash()
    sheep, player = (0.0, 0.0), (50.0, 0.0)
    trail.reset(player, sheep)
    path = [(50.0 + 2 * i, 0.0) for i in range(1, 60)] + [(168.0 - 2 * i, 4.0) for i in range(1, 140)]
    last, steps = sheep, []
    for player in path:
        trail.record(player)
        sheep, _ = trail.step(sheep, player, SPEED, FRAME)
        steps.append(sheep[0] - last[0])
        assert math.dist(sheep, last) <= SPEED * leash.TAUT_CATCH_UP * FRAME + leash.SHORTCUT + 0.01
        last = sheep
    # No back-and-forth: once it turned round to follow, it never turned again
    turns = sum(1 for a, b in zip(steps, steps[1:]) if a * b < 0 and abs(a) > 0.01 and abs(b) > 0.01)
    assert turns <= 1


def test_the_rope_runs_from_hand_to_neck():
    points = rope_points((0.0, 0.0), (40.0, 10.0), 0.0)
    assert points[0] == (0.0, 0.0) and points[-1] == pytest.approx((40.0, 10.0))
    assert len(points) == leash.ROPE_SEGMENTS + 1


def test_slack_it_sags_about_its_length_and_taut_it_is_straight():
    slack = rope_points((0.0, 0.0), (30.0, 0.0), 0.0)
    assert max(y for _, y in slack) > 5
    length = sum(math.dist(a, b) for a, b in zip(slack, slack[1:]))
    assert length == pytest.approx(leash.LENGTH, rel=0.15)
    taut = rope_points((0.0, 0.0), (leash.LENGTH + 10, 0.0), 1.0)
    assert all(abs(y) < 1e-9 for _, y in taut)
