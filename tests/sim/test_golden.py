"""The market and the population behave to the last bit as before the sim core was extracted.

The goldens hold to the last bit only on the platform that wrote them: the maths
library's last bits differ between Windows and Linux (70.76439818089338 against
...337). So every platform compares the numbers to ``REL_TOL``, the digests of
float histories left out (their samples stand in), and the platform that wrote
them also checks every bit, digests included.
"""
import json
import math
from typing import Any, List

import pytest

from tests.sim.golden_harness import SEEDS, golden_path, platform_tag, run_scenario

REL_TOL = 1e-12
ABS_TOL = 1e-9      # for values that are zero on one platform and a rounding speck on another


def _load(seed: int):
    with open(golden_path(seed), encoding="utf-8") as f:
        golden = json.load(f)
    # Through JSON, so tuples and lists compare alike; floats survive it exactly
    actual = json.loads(json.dumps(run_scenario(seed)))
    return golden, actual


def _differences(expected: Any, actual: Any, path: str = "") -> List[str]:
    """Where ``actual`` differs from ``expected`` beyond the tolerance, skipping float histories' digests."""
    if isinstance(expected, dict) and isinstance(actual, dict):
        if expected.keys() != actual.keys():
            return [f"{path}: keys {sorted(expected.keys() ^ actual.keys())} on one side only"]
        found = []
        for key in expected:
            if key.endswith("_sha256") and key[:-len("_sha256")] + "_sample" in expected:
                continue
            found += _differences(expected[key], actual[key], f"{path}/{key}")
        return found
    if isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            return [f"{path}: {len(actual)} items, expected {len(expected)}"]
        found = []
        for i, (e, a) in enumerate(zip(expected, actual)):
            found += _differences(e, a, f"{path}[{i}]")
        return found
    numbers = (int, float)
    if (isinstance(expected, float) or isinstance(actual, float)) and \
            isinstance(expected, numbers) and isinstance(actual, numbers) and \
            not isinstance(expected, bool) and not isinstance(actual, bool):
        if math.isclose(actual, expected, rel_tol=REL_TOL, abs_tol=ABS_TOL):
            return []
    elif expected == actual and type(expected) is type(actual):
        return []
    return [f"{path}: {actual!r}, expected {expected!r}"]


@pytest.mark.parametrize("seed", SEEDS)
def test_the_scenario_matches_its_golden_file(seed):
    golden, actual = _load(seed)
    assert _differences(golden["snapshot"], actual) == []


@pytest.mark.parametrize("seed", SEEDS)
def test_the_scenario_matches_its_golden_file_to_the_bit(seed):
    golden, actual = _load(seed)
    if golden["written_on"] != platform_tag():
        pytest.skip(f"the goldens hold to the bit on {golden['written_on']}, not {platform_tag()}")
    assert actual == golden["snapshot"]


def test_the_comparison_tolerates_last_bit_noise_but_not_drift():
    golden = {"x": 70.76439818089338, "n": 3, "h_sha256": "a", "h_sample": [1.0, 0.0], "rng_sha256": "r"}
    noisy = {"x": 70.76439818089337, "n": 3, "h_sha256": "b", "h_sample": [1.0 + 1e-15, 1e-17], "rng_sha256": "r"}
    assert _differences(golden, noisy) == []
    assert _differences(golden, dict(noisy, x=70.7644)) != []
    assert _differences(golden, dict(noisy, n=4)) != []
    assert _differences(golden, dict(noisy, rng_sha256="s")) != []
    assert _differences(golden, dict(noisy, h_sample=[1.0])) != []
