"""The simulation: state, random generator, scheduler and event queue in one object.

The game (or the headless runner) builds one ``Simulation``, moves its clock
with ``advance_to()`` and reads ``state``; the systems run on the scheduler's
ticks in the order they are subscribed in ``_subscribe_systems()``:

    price tick   each good: noise step (one draw), chart point
    hour         in market hours, a trading slice: households buy, then
                 merchants import and export, each good in turn;
                 every hour, happiness glides towards its target
    day          each good: close the day's flows, the outside price's walk
                 (one draw), the well wish's countdown, the target stock;
                 each class: rate yesterday, earn, plan today, target happiness;
                 migration; daily records

``docs/sim_core.md`` has the structure, ``docs/p1_living_market.md`` the model.
"""
import datetime
from typing import Any, Dict, Optional, Sequence

from ..config.constants import MARKET_CLOSE_HOUR, MARKET_OPEN_HOUR
from . import calendar
from .data import ClassNeedsDef, GoodDef
from .events import EventQueue, PopulationChanged, PriceShockEnded
from .rng import make_rng, state_from_json, state_to_json
from .scheduler import Scheduler
from .state import GoodState, SimState, TownSpec
from .systems import households, market, population

SIM_VERSION = 2     # the save's "sim" block; raise it (and migrate in load()) when its shape changes
SLICES_PER_DAY = MARKET_CLOSE_HOUR - MARKET_OPEN_HOUR


class SimVersionError(ValueError):
    """A save's sim block is newer than this simulation can read."""


def is_market_hour(moment: datetime.datetime) -> bool:
    """Whether the hour ending at *moment* was a trading slice (MARKET_OPEN_HOUR to MARKET_CLOSE_HOUR)."""
    return MARKET_OPEN_HOUR < moment.hour <= MARKET_CLOSE_HOUR


def slices_left(moment: datetime.datetime) -> int:
    """Trading slices left today, the one ending at *moment* included."""
    return MARKET_CLOSE_HOUR - moment.hour + 1


class Simulation:
    """The headless economy: goods, their market and the outside world, the town's people."""

    def __init__(self, goods: Sequence[GoodDef], needs: Sequence[ClassNeedsDef], now: datetime.datetime,
                 seed: int, town: Optional[TownSpec] = None) -> None:
        """Create the goods and, if given, the town.

        Args:
            goods: The goods' definitions, in order.
            needs: Each class's needs (needs.json), in order.
            now: Where the clock starts; nothing fires for it.
            seed: The random generator's seed.
            town: The town to found now; ``found_town()`` can do it later.
        """
        self.seed: int = seed
        self.rng = make_rng(seed)
        self.events = EventQueue()
        self.definitions: Dict[str, GoodDef] = {d.name: d for d in goods}
        self.needs: Dict[str, ClassNeedsDef] = {n.name: n for n in needs}
        self.state = SimState(goods={d.name: market.create_good(d, now) for d in goods})
        self.scheduler = Scheduler(now)
        if town is not None:
            self.found_town(town)
        self._subscribe_systems()

    # -- clock -------------------------------------------------------------

    @property
    def now(self) -> datetime.datetime:
        return self.scheduler.now

    def advance_to(self, moment: datetime.datetime) -> None:
        """Run every tick up to *moment* (see the module's docstring for their order)."""
        self.scheduler.advance_to(moment)

    def advance(self, delta: datetime.timedelta) -> None:
        self.advance_to(self.now + delta)

    def _subscribe_systems(self) -> None:
        self.scheduler.subscribe(calendar.PRICE_TICK, self._market_tick)
        self.scheduler.subscribe(calendar.HOUR, self._market_slice)
        self.scheduler.subscribe(calendar.HOUR, self._happiness_hour)
        self.scheduler.subscribe(calendar.DAY, self._market_day)
        self.scheduler.subscribe(calendar.DAY, self._households_day)
        self.scheduler.subscribe(calendar.DAY, self._population_day)

    # -- the systems on their ticks -----------------------------------------

    def _market_tick(self, moment: datetime.datetime) -> None:
        for good in self.state.goods.values():
            market.step_noise(good, self.definitions[good.name], self.rng)
            market.record_tick(good)

    def _market_slice(self, moment: datetime.datetime) -> None:
        if not is_market_hour(moment):
            return
        goods = self.state.goods
        pop = self.state.population
        prices = {name: market.price(g) for name, g in goods.items()}
        left = slices_left(moment)
        orders = ({c.name: households.slice_orders(c, left, prices) for c in pop.classes.values()}
                  if pop is not None else {})
        for name, good in goods.items():
            buyers = {cls: o[name] for cls, o in orders.items() if o.get(name, 0.0) > 0}
            if buyers:
                self._sell_to_households(good, buyers)
            imported, exported, paid = market.merchants(good, self.definitions[name], SLICES_PER_DAY)
            good.today.imported += imported
            good.today.exported += exported
            self.state.market_cash -= paid

    def _sell_to_households(self, good: GoodState, buyers: Dict[str, float]) -> None:
        """One slice's household purchases of a good, cleared together at one price."""
        pop = self.state.population
        filled, unit_price = market.clear_buyers(good, buyers)
        for name, units in filled.items():
            cls = pop.classes[name]
            paid = units * unit_price
            if paid > cls.purse:                # slippage beyond what the purse holds: give the rest back
                units = cls.purse / unit_price if unit_price > 0 else 0.0
                good.stock += filled[name] - units
                paid = cls.purse
            households.receive(cls, good.name, units, paid)
            good.today.bought += units
            self.state.market_cash += paid

    def _happiness_hour(self, moment: datetime.datetime) -> None:
        pop = self.state.population
        if pop is not None:
            population.glide_happiness(pop)
            population.record_happiness(pop)

    def _market_day(self, moment: datetime.datetime) -> None:
        for good in self.state.goods.values():
            definition = self.definitions[good.name]
            market.close_day(good)
            market.step_outside(good, definition, moment, self.rng)
            if market.tick_well_shock_day(good):
                self.events.push(PriceShockEnded(moment, good.name))
            market.update_target(good, definition, good.yesterday.wanted)

    def _households_day(self, moment: datetime.datetime) -> None:
        pop = self.state.population
        if pop is None:
            return
        prices = {name: market.price(g) for name, g in self.state.goods.items()}
        for cls in pop.classes.values():
            needs = self.needs[cls.name]
            households.start_day(cls, needs, prices, moment)
            population.set_target(cls, households.needs_happiness(cls, needs))
            for item in cls.plan:
                self.state.goods[item.good].today.wanted += item.wanted

    def _population_day(self, moment: datetime.datetime) -> None:
        pop = self.state.population
        if pop is not None:
            old_total, new_total = population.update_population(pop)
            population.record_population(pop)
            if new_total != old_total:
                self.events.push(PopulationChanged(moment, old_total, new_total))
        for good in self.state.goods.values():
            market.record_day(good)

    # -- setting up --------------------------------------------------------

    def found_town(self, town: TownSpec) -> None:
        """Give the simulation its town's people, the houses STARTING_OCCUPANCY full.

        Each class gets its starting purse and today's plan; each good's target
        stock is set from that demand, and the market holds its target.
        """
        pop = population.create_population(town)
        self.state.population = pop
        for cls in pop.classes.values():
            households.give_start_purse(cls, self.needs[cls.name])
        self._settle_demand(stock_to_target=True)

    def _settle_demand(self, stock_to_target: bool) -> None:
        """Plan the classes' day now and set each good's target stock from that demand at once."""
        demand = {name: 0.0 for name in self.state.goods}
        pop = self.state.population
        if pop is not None:
            prices = {name: market.price(g) for name, g in self.state.goods.items()}
            for cls in pop.classes.values():
                needs = self.needs[cls.name]
                households.plan(cls, needs, prices, self.now, min(cls.purse, households.daily_income(cls, needs)))
                for item in cls.plan:
                    demand[item.good] += item.wanted
        for name, good in self.state.goods.items():
            good.today.wanted = demand[name]
            market.update_target(good, self.definitions[name], demand[name], glide=1.0)
            if stock_to_target:
                good.stock = good.target_stock

    def presimulate(self, days: int) -> None:
        """Run the whole economy *days* days before now, so the game opens on a market with a history.

        The clock is put back, run forward to now, and the people's histories
        are cut to their last entry: the game's charts of the town start today.
        """
        start = self.now
        self.scheduler.reset(start - datetime.timedelta(days=days))
        self.advance_to(start)
        pop = self.state.population
        if pop is not None:
            for cls in pop.classes.values():
                cls.happiness_history = cls.happiness_history[-1:] or [cls.happiness]
                cls.population_history = cls.population_history[-1:] or [cls.count]
            pop.average_happiness_history = pop.average_happiness_history[-1:] or [pop.happiness]
            pop.total_population_history = pop.total_population_history[-1:] or [pop.citizens]

    # -- commands from the game ---------------------------------------------

    def good(self, name: str) -> GoodState:
        return self.state.goods[name]

    def apply_well_shock(self, name: str, up: bool) -> None:
        market.apply_well_shock(self.state.goods[name], up)

    def trade_with_player(self, name: str, quantity: int, buying: bool) -> float:
        """The player buys from (or sells to) the market: unit by unit with slippage.

        Returns:
            What the player pays (buying) or is paid (selling), before the trading fee.
        """
        good = self.state.goods[name]
        amount = market.quote(good, quantity, buying)
        if buying:
            good.stock -= quantity
            good.today.player_bought += quantity
            self.state.market_cash += amount
        else:
            good.stock += quantity
            good.today.player_sold += quantity
            self.state.market_cash -= amount
        market.show_current_price(good)
        return amount

    # -- saving --------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """The save's ``"sim"`` block: plain JSON, the random generator's state as a list."""
        return {
            "sim_version": SIM_VERSION,
            "seed": self.seed,
            "rng": state_to_json(self.rng),
            "now": self.now.isoformat(),
            "state": self.state.to_dict(),
        }

    def load(self, data: Dict[str, Any], now: Optional[datetime.datetime] = None) -> None:
        """Take over a ``"sim"`` block written by ``to_dict()`` (this version or an older one).

        Goods saved but no longer defined are dropped; goods defined but not in
        the save keep what they have and get a flat history as long as the
        saved ones'. A block of sim_version 1 (P0, before the living market)
        keeps its histories and people, and each good's stock as a share of its
        new target (as scarce or glutted as it was); everything new starts from
        defaults: the outside price at its mean, a purse of PURSE_START_DAYS,
        targets and today's plan from the current demand. Its prices jump to
        the new model. The random generator is restored last, so a loaded game
        draws exactly what the saved one would have.

        Args:
            data: The block.
            now: Where the clock goes on from; the block's own ``"now"`` if omitted.

        Raises:
            SimVersionError: If the block is newer than ``SIM_VERSION``.
        """
        version = int(data.get("sim_version", 1))
        if version > SIM_VERSION:
            raise SimVersionError(f"the save's simulation is version {version}, this game reads up to {SIM_VERSION}")
        moment = now if now is not None else datetime.datetime.fromisoformat(data["now"])
        self.scheduler.reset(moment)
        saved = SimState.from_dict(data["state"])
        ticks = max((len(g.price_history_ticks) for g in saved.goods.values()), default=1)
        days = max((len(g.price_history_daily) for g in saved.goods.values()), default=1)
        goods: Dict[str, GoodState] = {}
        for name, definition in self.definitions.items():
            good = saved.goods.get(name)
            if good is None:
                good = self.state.goods[name]
                market.fill_history(good, ticks, days)
            elif good.outside_base <= 0:                      # sim_version 1: the outside price at its mean
                fresh = market.create_good(definition, moment)
                good.outside_base = good.outside_price = fresh.outside_base
            if good.target_stock <= 0:                        # until _settle_demand works out the real one
                good.target_stock = definition.min_target_stock
            goods[name] = good
        self.state = SimState(goods=goods, population=saved.population or self.state.population,
                              market_cash=saved.market_cash)
        pop = self.state.population
        if pop is not None:
            for cls in pop.classes.values():
                if cls.purse < 0:                             # sim_version 1: a starting purse
                    households.give_start_purse(cls, self.needs[cls.name])
                cls.plan = [item for item in cls.plan if item.good in goods]   # goods no longer defined
        if version < 2 or any(g.target_stock <= 0 for g in goods.values()):
            self._settle_demand(stock_to_target=False)
        if version < 2:
            # P0 measured stock against a "normal" volume of thousands; the living market against
            # days of demand. Keep how scarce or glutted each good was, not its units.
            for saved_good in data["state"].get("goods", []):
                name, normal = saved_good["name"], saved_good.get("normal_quantity")
                if name in goods:
                    share = saved_good.get("market_quantity", 0) / normal if normal else 1.0
                    goods[name].stock = goods[name].target_stock * share
        self.seed = int(data.get("seed", self.seed))
        if "rng" in data:
            state_from_json(self.rng, data["rng"])
