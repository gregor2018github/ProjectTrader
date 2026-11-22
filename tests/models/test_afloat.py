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


def test_the_fishing_boat_floats():
    root = ElementTree.parse(os.path.join("assets", "tiles", "Map1.tmx")).getroot()
    boat = next(o for o in root.iter("object") if o.get("name") == "Fishing_Boat")
    assert {p.get("name"): p.get("value") for p in boat.iter("property")}["Afloat"] == "true"
