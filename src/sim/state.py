"""The simulation's state: plain dataclasses, every number of the economy kept once.

Systems (``systems/``) change it; the game reads it through thin views
(``Good``, ``PopulationManager``, ``Town``) that hold no numbers of their own.
Each class turns into JSON-ready dicts and back (``to_dict`` / ``from_dict``),
which is what the save's ``"sim"`` block holds.
"""
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TownSpec:
    """What the simulation needs to know about a town to found its population.

    Plain data: the game takes it from the map's houses, the headless runner
    from the map file (``scenario/tmx_town.py``), a test from a list.
    """
    house_capacities: List[int]     # Max_inhabitants of every house; 0 for one nobody lives in
    name: str = "Town"


@dataclass
class GoodState:
    """One good on the market: its price walk, its volume and their histories.

    The price is ``walk_price`` times the volume factor of ``market_quantity``
    against ``normal_quantity`` (``systems.market.price``).
    """
    name: str
    base_price: float               # the starting price, from which a missing history is made up
    walk_price: float               # the random walk part of the price
    market_quantity: int            # units the market holds now
    normal_quantity: int            # the volume the market thinks is normal
    upper_bound: float              # above this the walk drifts down
    lower_bound: float              # below this the walk drifts up
    well_shock_remaining_days: int = 0
    well_shock_saved_upper: float = 0.0     # the corridor to restore when a well shock runs out
    well_shock_saved_lower: float = 0.0
    price_history_ticks: List[float] = field(default_factory=list)   # one price per price tick (the chart)
    price_history_daily: List[float] = field(default_factory=list)   # one price per day (bookkeeping)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GoodState":
        return cls(
            name=data["name"],
            base_price=float(data["base_price"]),
            walk_price=float(data["walk_price"]),
            market_quantity=int(data["market_quantity"]),
            normal_quantity=int(data["normal_quantity"]),
            upper_bound=float(data["upper_bound"]),
            lower_bound=float(data["lower_bound"]),
            well_shock_remaining_days=int(data.get("well_shock_remaining_days", 0)),
            well_shock_saved_upper=float(data.get("well_shock_saved_upper", 0.0)),
            well_shock_saved_lower=float(data.get("well_shock_saved_lower", 0.0)),
            price_history_ticks=list(data.get("price_history_ticks", [])),
            price_history_daily=list(data.get("price_history_daily", [])),
        )


@dataclass
class ClassState:
    """One social class of the town: a head count and a mood."""
    name: str
    count: int
    base: int                       # the map's head count for it, which min/max and crowding are measured against
    happiness: float
    happiness_history: List[float] = field(default_factory=list)   # hourly
    population_history: List[int] = field(default_factory=list)    # daily

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ClassState":
        return cls(
            name=data["name"],
            count=int(data["count"]),
            base=int(data["base"]),
            happiness=data["happiness"],
            happiness_history=list(data.get("happiness_history", [])),
            population_history=list(data.get("population_history", [])),
        )


@dataclass
class PopulationState:
    """The town's people, by class (in the order of ``systems.population.CLASS_SHARES``)."""
    classes: Dict[str, ClassState]
    max_citizens: int               # the houses' capacity summed
    happiness: float                # the town's mood: the classes' weighted average as of the last hourly update
    average_happiness_history: List[float] = field(default_factory=list)   # hourly
    total_population_history: List[int] = field(default_factory=list)      # daily

    @property
    def citizens(self) -> int:
        """Heads in all classes together."""
        return sum(c.count for c in self.classes.values())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "classes": [c.to_dict() for c in self.classes.values()],
            "max_citizens": self.max_citizens,
            "happiness": self.happiness,
            "average_happiness_history": list(self.average_happiness_history),
            "total_population_history": list(self.total_population_history),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PopulationState":
        classes = [ClassState.from_dict(c) for c in data["classes"]]
        return cls(
            classes={c.name: c for c in classes},
            max_citizens=int(data["max_citizens"]),
            happiness=data["happiness"],
            average_happiness_history=list(data.get("average_happiness_history", [])),
            total_population_history=list(data.get("total_population_history", [])),
        )


@dataclass
class SimState:
    """Everything the simulation keeps, except its random generator and clock."""
    goods: Dict[str, GoodState] = field(default_factory=dict)      # in the goods' definition order
    population: Optional[PopulationState] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goods": [g.to_dict() for g in self.goods.values()],
            "population": self.population.to_dict() if self.population is not None else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SimState":
        goods = [GoodState.from_dict(g) for g in data.get("goods", [])]
        population = data.get("population")
        return cls(
            goods={g.name: g for g in goods},
            population=PopulationState.from_dict(population) if population else None,
        )
