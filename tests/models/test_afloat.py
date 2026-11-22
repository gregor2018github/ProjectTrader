"""A boat on the water: how far it bobs and rocks, and that two boats do not keep step."""

import os
import xml.etree.ElementTree as ElementTree

from src.models import afloat
from src.models.afloat import BOB_PX, ROLL_DEG, ROLL_STEP_DEG, motion

TIMES = [n * 0.05 for n in range(2000)]


def test_it_stays_within_its_bob_and_roll():
    for t in TIMES:
        bob, roll = motion(t, 5024)
        assert abs(bob) <= BOB_PX + 1e-9
        assert abs(roll) <= ROLL_DEG + ROLL_STEP_DEG / 2


def test_it_moves_both_ways():
    bobs, rolls = zip(*(motion(t, 5024) for t in TIMES))
    assert min(bobs) < -0.7 * BOB_PX and max(bobs) > 0.7 * BOB_PX
    assert min(rolls) < 0 < max(rolls)


def test_the_roll_comes_in_steps():
    for t in TIMES[:200]:
        _, roll = motion(t, 5024)
        assert abs(roll / ROLL_STEP_DEG - round(roll / ROLL_STEP_DEG)) < 1e-9


def test_two_boats_apart_do_not_keep_step():
    apart = afloat.PHASE_SPREAD_PX / 4
    assert any(motion(t, 0) != motion(t, apart) for t in TIMES[:50])


def test_a_longer_boat_rocks_less_and_slower():
    ship = afloat.REFERENCE_LENGTH_PX * 3
    small = [abs(motion(t, 5024)[1]) for t in TIMES]
    big = [abs(motion(t, 5024, ship)[1]) for t in TIMES]
    assert max(big) < max(small)
    assert max(big) <= ROLL_DEG / 3 ** 0.5 + ROLL_STEP_DEG / 2
    # slower: its roll changes step less often
    changes = lambda rolls: sum(a != b for a, b in zip(rolls, rolls[1:]))
    assert changes(big) < changes(small)


def test_a_shorter_boat_moves_like_the_reference():
    assert motion(1.7, 5024, 60) == motion(1.7, 5024)


def test_the_boats_float():
    root = ElementTree.parse(os.path.join("assets", "tiles", "Map1.tmx")).getroot()
    for name in ("Fishing_Boat", "Trading_Cog", "Rowing_Skiff", "Sailing_Boat"):
        boat = next(o for o in root.iter("object") if o.get("name") == name)
        afloat_prop = next(p for p in boat.iter("property") if p.get("name") == "Afloat")
        assert (afloat_prop.get("type"), afloat_prop.get("value")) == ("bool", "true"), name
