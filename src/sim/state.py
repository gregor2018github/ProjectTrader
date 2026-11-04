"""The simulation's state: plain dataclasses, every number of the economy kept once.

Systems (``systems/``) change it; the game reads it through thin views
(``Good``, ``PopulationManager``, ``Town``) that hold no numbers of their own.
Each class turns into JSON-ready dicts and back (``to_dict`` / ``from_dict``),
which is what the save's ``"sim"`` block holds. ``from_dict`` fills fields an
older block lacks with defaults; ``Simulation.load`` then works out what
follows from the rest (a target stock, a day's plan).
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
class GoodFlows:
    """How much of a good moved in a day, and through whom."""
    wanted: float = 0.0             # what households wanted (their full baskets)
    bought: float = 0.0             # what households got
    imported: float = 0.0
    exported: float = 0.0
    player_bought: float = 0.0
    player_sold: float = 0.0

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "GoodFlows":
        return cls(**{k: float(v) for k, v in (data or {}).items() if k in cls.__dataclass_fields__})


@dataclass
class GoodState:
    """One good on the market: its stock, its prices, and their histories.

    Its price is ``reference × volume_factor(stock / target_stock) × noise``
    (``systems.market.price``); the reference is the outside price times a
    running well wish's shock.
    """
    name: str
    stock: float                    # units the market holds now
    target_stock: float             # what it likes to hold: days of demand (0: work it out on loading)
    demand_avg: float = 0.0         # the town's daily demand, smoothed
    outside_base: float = 0.0       # the outside price's mean times today's season factor
    outside_dev: float = 0.0        # the outside price's log deviation from that (the slow walk)
    outside_price: float = 0.0      # outside_base × exp(outside_dev)
    noise: float = 0.0              # the price noise, as a log
    shock_factor: float = 1.0       # a running well wish's factor on the outside price
    shock_days: int = 0             # days the wish has left
    price_history_ticks: List[float] = field(default_factory=list)   # one price per price tick (the chart)
    price_history_daily: List[float] = field(default_factory=list)   # one price per day (bookkeeping)
    today: GoodFlows = field(default_factory=GoodFlows)
    yesterday: GoodFlows = field(default_factory=GoodFlows)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GoodState":
        stock = data.get("stock", data.get("market_quantity", 0.0))     # sim_version 1 had market_quantity
        return cls(
            name=data["name"],
            stock=float(stock),
            target_stock=float(data.get("target_stock", 0.0)),
            demand_avg=float(data.get("demand_avg", 0.0)),
            outside_base=float(data.get("outside_base", 0.0)),
            outside_dev=float(data.get("outside_dev", 0.0)),
            outside_price=float(data.get("outside_price", 0.0)),
            noise=float(data.get("noise", 0.0)),
            shock_factor=float(data.get("shock_factor", 1.0)),
            shock_days=int(data.get("shock_days", 0)),
            price_history_ticks=list(data.get("price_history_ticks", [])),
            price_history_daily=list(data.get("price_history_daily", [])),
            today=GoodFlows.from_dict(data.get("today")),
            yesterday=GoodFlows.from_dict(data.get("yesterday")),
        )


@dataclass
class PlanItem:
    """One good of one tier a class means to buy today."""
    good: str
    tier: str
    wanted: float                   # units its whole basket asks for today
    planned: float                  # units it can afford to buy (wanted, or less for want of money)
    price: float                    # the price it planned at: the item's weight in the tier's fulfilment
    bought: float = 0.0             # units bought so far today

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlanItem":
        return cls(good=data["good"], tier=data["tier"], wanted=float(data["wanted"]),
                   planned=float(data["planned"]), price=float(data["price"]), bought=float(data.get("bought", 0.0)))


@dataclass
class ClassFlows:
    """A class's money in a day."""
    income: float = 0.0
    spent: float = 0.0
    leaked: float = 0.0             # savings above the cap, gone out of town

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "ClassFlows":
        return cls(**{k: float(v) for k, v in (data or {}).items() if k in cls.__dataclass_fields__})


@dataclass
class ClassState:
    """One social class of the town: a head count, a purse, a mood."""
    name: str
    count: int
    base: int                       # the map's head count for it, which min/max and crowding are measured against
    happiness: float
    happiness_target: float = 0.0   # where its happiness glides to, from yesterday's fulfilment
    purse: float = 0.0
    fulfilment: Dict[str, float] = field(default_factory=dict)   # tier -> share of yesterday's wants it got (0..1)
    plan: List[PlanItem] = field(default_factory=list)          # today's shopping
    today: ClassFlows = field(default_factory=ClassFlows)
    yesterday: ClassFlows = field(default_factory=ClassFlows)
    happiness_history: List[float] = field(default_factory=list)   # hourly
    population_history: List[int] = field(default_factory=list)    # daily

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ClassState":
        happiness = data["happiness"]
        return cls(
            name=data["name"],
            count=int(data["count"]),
            base=int(data["base"]),
            happiness=happiness,
            happiness_target=data.get("happiness_target", happiness),
            purse=float(data.get("purse", -1.0)),            # -1: not saved (sim_version 1), give it a start
            fulfilment={k: float(v) for k, v in data.get("fulfilment", {}).items()},
            plan=[PlanItem.from_dict(p) for p in data.get("plan", [])],
            today=ClassFlows.from_dict(data.get("today")),
            yesterday=ClassFlows.from_dict(data.get("yesterday")),
            happiness_history=list(data.get("happiness_history", [])),
            population_history=list(data.get("population_history", [])),
        )


@dataclass
class PopulationState:
    """The town's people, by class (in the order of ``systems.population.class_shares``)."""
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
    market_cash: float = 0.0        # the market place's traders' cash: paid by buyers, paid out to sellers

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goods": [g.to_dict() for g in self.goods.values()],
            "population": self.population.to_dict() if self.population is not None else None,
            "market_cash": self.market_cash,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SimState":
        goods = [GoodState.from_dict(g) for g in data.get("goods", [])]
        population = data.get("population")
        return cls(
            goods={g.name: g for g in goods},
            population=PopulationState.from_dict(population) if population else None,
            market_cash=float(data.get("market_cash", 0.0)),
        )
