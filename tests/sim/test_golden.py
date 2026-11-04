"""The market and the population behave to the last bit as before the sim core was extracted."""
import json

import pytest

from tests.sim.golden_harness import SEEDS, golden_path, run_scenario


@pytest.mark.parametrize("seed", SEEDS)
def test_the_scenario_matches_its_golden_file(seed):
    with open(golden_path(seed), encoding="utf-8") as f:
        expected = json.load(f)
    # Through JSON, so tuples and lists compare alike; floats survive it exactly
    actual = json.loads(json.dumps(run_scenario(seed)))
    assert actual == expected
