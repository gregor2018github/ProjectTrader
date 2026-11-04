"""The simulation's one random generator, and its state as plain JSON.

Every simulation owns a single ``random.Random(seed)`` and hands it to the
systems that draw from it, so a run repeats exactly from its seed. Nothing in
``src/sim/`` may call the ``random`` module's own functions (``random.random()``,
``random.normalvariate()``, ...): they share one stream with the whole game.
"""
import random
from typing import Any, List

SEED_LIMIT = 2 ** 32


def make_rng(seed: int) -> random.Random:
    """A generator that draws the same numbers as ``random.seed(seed)`` would."""
    return random.Random(seed)


def new_seed() -> int:
    """A fresh seed for a new game, from the operating system's entropy."""
    return random.SystemRandom().randrange(SEED_LIMIT)


def state_to_json(rng: random.Random) -> List[Any]:
    """The generator's state as a JSON-ready list: [version, [625 ints], gauss_next]."""
    version, internal, gauss_next = rng.getstate()
    return [version, list(internal), gauss_next]


def state_from_json(rng: random.Random, data: List[Any]) -> None:
    """Put the generator back into a state written by ``state_to_json``.

    Raises:
        ValueError: If *data* is not such a state.
    """
    try:
        version, internal, gauss_next = data
        rng.setstate((int(version), tuple(int(v) for v in internal), gauss_next))
    except (TypeError, ValueError) as error:
        raise ValueError(f"not a random generator state: {error}") from error
