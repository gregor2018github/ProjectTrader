"""The headless simulation core: the economy's state and rules, without pygame.

Nothing in this package imports pygame or the game's UI, handlers or drawing
models (``tests/sim/test_no_pygame.py`` holds it to that), so it runs in tests
and in the headless runner (``python -m src.sim.run``) as it does in the game.
``docs/sim_core.md`` describes its structure and how to extend it.
"""
from .data import (
    BuildingDef, ClassNeedsDef, DataError, Definitions, GoodDef, NeedDef, OwnerDef, RecipeDef, ScenarioDef,
    WorkshopSeed, load_definitions, load_goods, load_needs, load_recipes, load_scenario,
)
from .simulation import SIM_VERSION, Simulation, SimVersionError
from .state import TownSpec

__all__ = [
    "BuildingDef", "ClassNeedsDef", "DataError", "Definitions", "GoodDef", "NeedDef", "OwnerDef", "RecipeDef",
    "SIM_VERSION", "ScenarioDef", "Simulation", "SimVersionError", "TownSpec", "WorkshopSeed",
    "load_definitions", "load_goods", "load_needs", "load_recipes", "load_scenario",
]
