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
    unmet: float = 0.0              # what households asked for in a slice and the market had not got (a stock-out)
    input_wanted: float = 0.0       # what workshops planned to use
    input_bought: float = 0.0       # what workshops got
    produced: float = 0.0           # what workshops made and sold into the market
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
    income: float = 0.0             # all of it: base income, wages and payouts
    wages: float = 0.0              # of which wages from workshops
    payouts: float = 0.0            # of which owners' surplus paid out to the townsfolk
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
    base: int                       # its head count when the game started
    happiness: float
    capacity: int = 0               # its share of the town's housing: crowding and migration's min/max measure against it (0: not saved yet)
    employed: float = 0.0           # heads working in workshops today (earning wages instead of base income)
    wage: float = 0.0               # what its workshops pay a worker a day, moving with the demand for hands (0: not saved yet)
    labour_wanted: float = 0.0      # workers its workshops wanted today, before sharing out
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
            capacity=int(data.get("capacity", 0)),
            employed=float(data.get("employed", 0.0)),
            wage=float(data.get("wage", 0.0)),
            labour_wanted=float(data.get("labour_wanted", 0.0)),
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
class OwnerState:
    """Someone who owns workshops: the town now, the player and rival dynasties later.

    No rule reads ``kind``; what an owner does with its surplus is its own
    ``surplus_to`` (data), the same choice open to every owner.
    """
    id: str
    kind: str
    name: str
    cash: float
    reserve: float                  # cash it keeps; above it, surplus_to decides
    surplus_to: str                 # "keep", "townsfolk" (paid out per head) or "treasury_with_tribute"
    income_avg: float = 0.0         # its net income a day (profits taken less top-ups given), smoothed
    profits_today: float = 0.0      # taken from its workshops today
    topped_up_today: float = 0.0    # given to its workshops today
    paid_out_today: float = 0.0     # paid to the townsfolk today
    tribute_today: float = 0.0      # paid to the lord today (gone out of town)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OwnerState":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class WorkshopState:
    """A workshop: one building of a type, running its recipe for its owner."""
    id: str
    owner_id: str
    building: str                   # key into buildings.json, which names the recipe
    capacity: float                 # batches a day it could run
    cash: float
    utilisation: float = 0.0        # 0..1, the share of capacity it means to run at
    margin: float = 0.0             # what a batch earned on its costs at the day's prices
    planned: float = 0.0            # batches it means to run today
    done: float = 0.0               # batches run so far today
    workers: float = 0.0            # heads hired for today
    wage: float = 0.0               # what it pays each of them (its class's wage when it hired)
    input_stock: Dict[str, float] = field(default_factory=dict)   # bought, not yet used
    busy_log: List[bool] = field(default_factory=list)   # the last GROWTH_WINDOW_DAYS: was it busy (wanted and planned near capacity)?
    loss_log: List[bool] = field(default_factory=list)   # the last SHRINK_WINDOW_DAYS: was its margin negative?
    done_yesterday: float = 0.0     # batches run yesterday

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkshopState":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class TownMoney:
    """The town's money crossing its border in a day.

    The market place holds no money: the stock in it belongs to the merchants,
    so buyers pay merchants and sellers are paid by them. The town's money
    (purses, workshops' and owners' cash; the player's is in the game's
    Depot) therefore changes by exactly ``created − leaked − invested −
    tribute − to_merchants + from_merchants``; whatever else appeared or vanished is the
    ``market_balance``, which must be zero.
    """
    created: float = 0.0            # base income (all the work that is not simulated)
    leaked: float = 0.0             # savings above the cap, gone out of town
    invested: float = 0.0           # paid to builders out of town for workshops' growth
    tribute: float = 0.0            # owners' treasuries above their cap, paid to the lord out of town
    to_merchants: float = 0.0       # paid by town buyers for goods from the market
    from_merchants: float = 0.0     # paid to town sellers for goods into the market
    market_balance: float = 0.0     # set when the day closes: what the flows above do not explain

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "TownMoney":
        return cls(**{k: float(v) for k, v in (data or {}).items() if k in cls.__dataclass_fields__})


@dataclass
class MerchantFlows:
    """The merchants' money in a day: they own the market's stock, buy it in and sell it on.

    Transport is theirs to pay, out of the margin between the import and
    export lines; buyers bear it through the price.
    """
    sales: float = 0.0              # paid to them by buyers (the town's and the player)
    purchases: float = 0.0          # paid by them to sellers (workshops and the player)
    import_cost: float = 0.0        # the outside price of what they brought in
    export_revenue: float = 0.0     # the outside price of what they took out
    transport: float = 0.0          # carrying it either way

    @property
    def profit(self) -> float:
        return self.sales - self.purchases - self.import_cost + self.export_revenue - self.transport

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "MerchantFlows":
        return cls(**{k: float(v) for k, v in (data or {}).items() if k in cls.__dataclass_fields__})


@dataclass
class SimState:
    """Everything the simulation keeps, except its random generator and clock."""
    goods: Dict[str, GoodState] = field(default_factory=dict)      # in the goods' definition order
    population: Optional[PopulationState] = None
    owners: Dict[str, OwnerState] = field(default_factory=dict)
    workshops: Dict[str, WorkshopState] = field(default_factory=dict)  # in id order (hiring follows it)
    money_today: TownMoney = field(default_factory=TownMoney)
    money_yesterday: TownMoney = field(default_factory=TownMoney)
    money_mark: Optional[float] = None      # the town's money when the day began (None: not yet known)
    merchants_today: MerchantFlows = field(default_factory=MerchantFlows)
    merchants_yesterday: MerchantFlows = field(default_factory=MerchantFlows)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goods": [g.to_dict() for g in self.goods.values()],
            "population": self.population.to_dict() if self.population is not None else None,
            "owners": [o.to_dict() for o in self.owners.values()],
            "workshops": [w.to_dict() for w in self.workshops.values()],
            "money_today": asdict(self.money_today),
            "money_yesterday": asdict(self.money_yesterday),
            "money_mark": self.money_mark,
            "merchants_today": asdict(self.merchants_today),
            "merchants_yesterday": asdict(self.merchants_yesterday),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SimState":
        goods = [GoodState.from_dict(g) for g in data.get("goods", [])]
        population = data.get("population")
        mark = data.get("money_mark")
        return cls(
            goods={g.name: g for g in goods},
            population=PopulationState.from_dict(population) if population else None,
            owners={o["id"]: OwnerState.from_dict(o) for o in data.get("owners", [])},
            workshops={w["id"]: WorkshopState.from_dict(w) for w in data.get("workshops", [])},
            money_today=TownMoney.from_dict(data.get("money_today")),
            money_yesterday=TownMoney.from_dict(data.get("money_yesterday")),
            money_mark=float(mark) if mark is not None else None,
            merchants_today=MerchantFlows.from_dict(data.get("merchants_today")),
            merchants_yesterday=MerchantFlows.from_dict(data.get("merchants_yesterday")),
        )
