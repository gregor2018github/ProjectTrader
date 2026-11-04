"""The town's population as the depot charts read it: a thin view over the simulation.

The happiness drift and migration rules, and every number they work on, live
in the simulation (``src/sim/systems/population.py``, ``PopulationState``).
This view only passes the histories through under the names the charts use.
It is a seam kept for P0 (see ``docs/sim_core.md``).
"""
from typing import TYPE_CHECKING, Dict, List

from ..sim.systems import population

if TYPE_CHECKING:
    from ..sim import Simulation
    from ..sim.state import PopulationState
    from .institutions.town import Town


class PopulationManager:
    """The simulation's population histories, per class and for the whole town.

    - happiness_history / average_happiness_history: per class and aggregate, hourly
    - population_history / total_population_history: per class and aggregate, daily
    """

    def __init__(self, sim: "Simulation", town: "Town") -> None:
        """Args:
            sim: The simulation whose town this shows; it must have one.
            town: The town hall on the map, shown alongside.
        """
        self._sim = sim
        self.town = town

    @property
    def _pop(self) -> "PopulationState":
        return self._sim.state.population

    @property
    def base_groups(self) -> Dict[str, int]:
        return {c.name: c.base for c in self._pop.classes.values()}

    @property
    def happiness_history(self) -> Dict[str, List[float]]:
        return {c.name: c.happiness_history for c in self._pop.classes.values()}

    @property
    def population_history(self) -> Dict[str, List[int]]:
        return {c.name: c.population_history for c in self._pop.classes.values()}

    @property
    def average_happiness_history(self) -> List[float]:
        return self._pop.average_happiness_history

    @property
    def total_population_history(self) -> List[int]:
        return self._pop.total_population_history

    @property
    def average_happiness(self) -> float:
        """Population-weighted average happiness across all classes."""
        return population.average_happiness(self._pop)
