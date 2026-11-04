"""The headless simulation core: the economy's state and rules, without pygame.

Nothing in this package imports pygame or the game's UI, handlers or drawing
models (``tests/sim/test_no_pygame.py`` holds it to that), so it runs in tests
and in the headless runner (``python -m src.sim.run``) as it does in the game.
``docs/sim_core.md`` describes its structure and how to extend it.
"""
from .data import DataError, GoodDef, RecipeDef, load_goods, load_recipes
from .simulation import SIM_VERSION, Simulation, SimVersionError
from .state import TownSpec

__all__ = [
    "DataError", "GoodDef", "RecipeDef", "SIM_VERSION", "Simulation", "SimVersionError",
    "TownSpec", "load_goods", "load_recipes",
]
