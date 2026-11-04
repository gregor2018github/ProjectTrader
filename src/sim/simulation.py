"""The simulation: state, definitions, random generator, scheduler and event queue in one object.

The game (or the headless runner) builds one ``Simulation``, founds its town
and establishes its workshops, moves its clock with ``advance_to()`` and reads
``state``; the systems run on the scheduler's ticks in the order they are
subscribed in ``_subscribe_systems()``:

    price tick   each good: noise step (one draw), chart point
    hour         in market hours, a trading slice: households and workshops
                 buy (each good cleared at one price, short stock shared pro
                 rata), workshops run their share of the day's batches and
                 sell the outputs, then merchants import and export;
                 every hour, happiness glides towards its target
    day          the books close (the town's money checked against its border
                 flows); each good: close the day's flows, the outside price's
                 walk (one draw), the well wish's countdown, the target stock;
                 each workshop: pay yesterday's workers, the owner covers a loss
                 or takes the profit; owners pay out their surplus; each class:
                 rate yesterday, earn, plan today, target happiness; migration;
                 each workshop plans and hires, and grows or shrinks;
                 daily records

``docs/sim_core.md`` has the structure, ``docs/p1_living_market.md`` the model.
"""
import datetime
from typing import Any, Dict, Hashable, Optional

from ..config.constants import MARKET_CLOSE_HOUR, MARKET_OPEN_HOUR
from . import calendar
from .data import BuildingDef, Definitions, RecipeDef, ScenarioDef
from .events import CapacityChanged, EventQueue, PopulationChanged, PriceShockEnded
from .rng import make_rng, state_from_json, state_to_json
from .scheduler import Scheduler
from .state import GoodState, MerchantFlows, OwnerState, SimState, TownMoney, TownSpec, WorkshopState
from .systems import households, market, population, production

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
    """The headless economy: goods and their market, the outside world, the town's people and workshops."""

    def __init__(self, definitions: Definitions, now: datetime.datetime, seed: int,
                 town: Optional[TownSpec] = None, scenario: Optional[ScenarioDef] = None) -> None:
        """Create the goods and, if given, the town and its workshops.

        Args:
            definitions: Goods, needs, recipes and building types (``data.load_definitions``).
            now: Where the clock starts; nothing fires for it.
            seed: The random generator's seed.
            town: The town to found now; ``found_town()`` can do it later.
            scenario: The owners and workshops to establish now; ``establish()`` can do it later.
        """
        self.seed: int = seed
        self.rng = make_rng(seed)
        self.events = EventQueue()
        self.definitions = {d.name: d for d in definitions.goods}
        self.needs = {n.name: n for n in definitions.needs}
        self.recipes: Dict[str, RecipeDef] = {r.id: r for r in definitions.recipes}
        self.buildings: Dict[str, BuildingDef] = {b.type: b for b in definitions.buildings}
        self.scenario: Optional[ScenarioDef] = None
        # Handed from _workshops_settle to _households_day within one midnight (never saved)
        self._wages: Dict[str, float] = {}
        self._payouts: Dict[str, float] = {}
        self.state = SimState(goods={d.name: market.create_good(d, now) for d in definitions.goods})
        self.scheduler = Scheduler(now)
        if town is not None:
            self.found_town(town)
        if scenario is not None:
            self.establish(scenario)
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
        self.scheduler.subscribe(calendar.DAY, self._close_books)
        self.scheduler.subscribe(calendar.DAY, self._market_day)
        self.scheduler.subscribe(calendar.DAY, self._workshops_settle)
        self.scheduler.subscribe(calendar.DAY, self._households_day)
        self.scheduler.subscribe(calendar.DAY, self._population_day)
        self.scheduler.subscribe(calendar.DAY, self._workshops_plan)
        self.scheduler.subscribe(calendar.DAY, self._record_day)

    # -- helpers -------------------------------------------------------------

    def _prices(self) -> Dict[str, float]:
        return {name: market.price(g) for name, g in self.state.goods.items()}

    def _recipe(self, ws: WorkshopState) -> RecipeDef:
        return self.recipes[self.buildings[ws.building].recipe]

    def town_money(self) -> float:
        """The money in the town: purses, workshops' cash and owners' cash."""
        state = self.state
        pop = state.population
        purses = sum(c.purse for c in pop.classes.values()) if pop is not None else 0.0
        return (purses + sum(w.cash for w in state.workshops.values())
                + sum(o.cash for o in state.owners.values()))

    # -- the market's slices ---------------------------------------------------

    def _market_tick(self, moment: datetime.datetime) -> None:
        for good in self.state.goods.values():
            market.step_noise(good, self.definitions[good.name], self.rng)
            market.record_tick(good)

    def _market_slice(self, moment: datetime.datetime) -> None:
        """One trading slice: buyers clear good by good, workshops produce and sell, merchants restock."""
        if not is_market_hour(moment):
            return
        state = self.state
        prices = self._prices()
        left = slices_left(moment)

        orders: Dict[Hashable, Dict[str, float]] = {}
        if state.population is not None:
            for cls in state.population.classes.values():
                orders[("class", cls.name)] = households.slice_orders(cls, left, prices)
        for ws in state.workshops.values():
            orders[("workshop", ws.id)] = production.slice_orders(ws, self._recipe(ws), left, prices)
        for name, good in state.goods.items():
            buyers = {who: o[name] for who, o in orders.items() if o.get(name, 0.0) > 0}
            if buyers:
                self._sell_to_buyers(good, buyers)

        sales: Dict[str, Dict[str, float]] = {}
        for ws in state.workshops.values():
            for good, units in production.run_slice(ws, self._recipe(ws), left).items():
                sales.setdefault(good, {})[ws.id] = units
        for name, sellers in sales.items():
            self._buy_from_workshops(state.goods[name], sellers)

        for name, good in state.goods.items():
            definition = self.definitions[name]
            imported, exported = market.merchants(good, definition, SLICES_PER_DAY)
            if imported or exported:
                good.today.imported += imported
                good.today.exported += exported
                book = state.merchants_today
                book.import_cost += imported * market.reference(good)
                book.export_revenue += exported * market.reference(good)
                book.transport += (imported + exported) * definition.transport_cost

    def _sell_to_buyers(self, good: GoodState, buyers: Dict[Hashable, float]) -> None:
        """One slice's purchases of a good by households and workshops, cleared together at one price."""
        filled, unit_price = market.clear_buyers(good, buyers)
        for (kind, key), units in filled.items():
            holder = self.state.population.classes[key] if kind == "class" else self.state.workshops[key]
            money = holder.purse if kind == "class" else holder.cash
            paid = units * unit_price
            if paid > money:                     # slippage beyond what they hold: give the rest back
                units = max(0.0, money) / unit_price if unit_price > 0 else 0.0
                good.stock += filled[(kind, key)] - units
                paid = units * unit_price
            if kind == "class":
                households.receive(holder, good.name, units, paid)
                good.today.bought += units
            else:
                holder.cash -= paid
                holder.input_stock[good.name] = holder.input_stock.get(good.name, 0.0) + units
                good.today.input_bought += units
            self.state.merchants_today.sales += paid
            self.state.money_today.to_merchants += paid

    def _buy_from_workshops(self, good: GoodState, sellers: Dict[str, float]) -> None:
        """Merchants buy a slice's output of a good from the workshops that made it, at one price."""
        total = sum(sellers.values())
        if total <= 0:
            return
        unit_price = market.quote(good, total, buying=False) / total
        good.stock += total
        good.today.produced += total
        for ws_id, units in sellers.items():
            paid = units * unit_price
            self.state.workshops[ws_id].cash += paid
            self.state.merchants_today.purchases += paid
            self.state.money_today.from_merchants += paid

    def _happiness_hour(self, moment: datetime.datetime) -> None:
        pop = self.state.population
        if pop is not None:
            population.glide_happiness(pop)
            population.record_happiness(pop)

    # -- the day ------------------------------------------------------------------

    def _close_books(self, moment: datetime.datetime) -> None:
        """The day's money is checked: the town's money changed by exactly what crossed its border."""
        state = self.state
        now = self.town_money()
        if state.money_mark is not None:
            m = state.money_today
            border = m.created - m.leaked - m.invested - m.to_merchants + m.from_merchants
            m.market_balance = (now - state.money_mark) - border
        state.money_yesterday, state.money_today = state.money_today, TownMoney()
        state.merchants_yesterday, state.merchants_today = state.merchants_today, MerchantFlows()
        for owner in state.owners.values():
            owner.profits_today = owner.paid_out_today = 0.0
        state.money_mark = now

    def _market_day(self, moment: datetime.datetime) -> None:
        for good in self.state.goods.values():
            definition = self.definitions[good.name]
            market.close_day(good)
            market.step_outside(good, definition, moment, self.rng)
            if market.tick_well_shock_day(good):
                self.events.push(PriceShockEnded(moment, good.name))
            market.update_target(good, definition, good.yesterday.wanted + good.yesterday.input_wanted)

    def _workshops_settle(self, moment: datetime.datetime) -> None:
        """Workshops pay yesterday's workers; owners cover losses, take profits and pay out their surplus."""
        state = self.state
        self._wages = {}
        for ws in state.workshops.values():
            building = self.buildings[ws.building]
            wages = production.settle_day(ws, building, state.owners[ws.owner_id])
            self._wages[building.workers_class] = self._wages.get(building.workers_class, 0.0) + wages
        self._payouts = {}
        pop = state.population
        heads = pop.citizens if pop is not None else 0
        for owner in state.owners.values():
            surplus = production.owner_surplus(owner)
            if surplus > 0 and heads > 0:
                for cls in pop.classes.values():
                    self._payouts[cls.name] = self._payouts.get(cls.name, 0.0) + surplus * cls.count / heads
            elif surplus > 0:
                owner.cash += surplus                      # nobody to pay it to
                owner.paid_out_today -= surplus

    def _households_day(self, moment: datetime.datetime) -> None:
        pop = self.state.population
        if pop is None:
            return
        prices = self._prices()
        wages, payouts = self._wages, self._payouts
        for cls in pop.classes.values():
            needs = self.needs[cls.name]
            base_before = households.daily_income(cls, needs)
            households.start_day(cls, needs, prices, moment, wages.get(cls.name, 0.0), payouts.get(cls.name, 0.0))
            self.state.money_today.created += base_before
            self.state.money_today.leaked += cls.today.leaked
            population.set_target(cls, households.needs_happiness(cls, needs))
            for item in cls.plan:
                self.state.goods[item.good].today.wanted += item.wanted
        self._wages, self._payouts = {}, {}

    def _population_day(self, moment: datetime.datetime) -> None:
        pop = self.state.population
        if pop is not None:
            old_total, new_total = population.update_population(pop)
            population.record_population(pop)
            if new_total != old_total:
                self.events.push(PopulationChanged(moment, old_total, new_total))

    def _workshops_plan(self, moment: datetime.datetime) -> None:
        """Workshops plan the day: what each wants, then each class's hands shared out pro rata; then growth."""
        state = self.state
        pop = state.population
        prices = self._prices()
        wanted: Dict[str, float] = {}
        for ws in state.workshops.values():
            building = self.buildings[ws.building]
            workers = production.plan_wants(ws, building, self.recipes[building.recipe], prices)
            wanted[building.workers_class] = wanted.get(building.workers_class, 0.0) + workers
        shares = {}
        for name, workers in wanted.items():
            cls = pop.classes.get(name) if pop is not None else None
            shares[name] = (production.labour_share_given(self.needs[name].labour_share, cls.count, workers)
                            if cls is not None else 0.0)
        hired: Dict[str, float] = {}
        for ws in state.workshops.values():
            building = self.buildings[ws.building]
            recipe = self.recipes[building.recipe]
            hired[building.workers_class] = hired.get(building.workers_class, 0.0) + production.hire(
                ws, recipe, shares[building.workers_class])
            for good, units in production.input_wants(ws, recipe).items():
                state.goods[good].today.input_wanted += units
            owner = state.owners[ws.owner_id]
            change, cost = production.change_capacity(ws, building, owner)
            if change:
                state.money_today.invested += cost
                self.events.push(CapacityChanged(moment, ws.id, ws.capacity - change, ws.capacity))
        if pop is not None:
            for cls in pop.classes.values():
                cls.employed = hired.get(cls.name, 0.0)

    def _record_day(self, moment: datetime.datetime) -> None:
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

    def establish(self, scenario: ScenarioDef) -> None:
        """Set up the scenario's owners and workshops (each workshop starts idle and plans at the next midnight)."""
        self.scenario = scenario
        self.state.owners = {
            o.id: OwnerState(id=o.id, kind=o.kind, name=o.name, cash=o.cash, reserve=o.reserve, surplus_to=o.surplus_to)
            for o in scenario.owners
        }
        self.state.workshops = {
            w.id: WorkshopState(id=w.id, owner_id=w.owner, building=w.building, capacity=w.capacity, cash=w.cash)
            for w in sorted(scenario.workshops, key=lambda w: w.id)
        }
        self.state.money_mark = None                     # the town's money changed outside the books

    def _settle_demand(self, stock_to_target: bool) -> None:
        """Plan the classes' day now and set each good's target stock from that demand at once."""
        demand = {name: 0.0 for name in self.state.goods}
        pop = self.state.population
        if pop is not None:
            prices = self._prices()
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
        """The player buys from (or sells to) the merchants: unit by unit with slippage.

        The player's money is the game's Depot's, not the town's, so it is on the
        merchants' book only.

        Returns:
            What the player pays (buying) or is paid (selling), before the trading fee.
        """
        good = self.state.goods[name]
        amount = market.quote(good, quantity, buying)
        if buying:
            good.stock -= quantity
            good.today.player_bought += quantity
            self.state.merchants_today.sales += amount
        else:
            good.stock += quantity
            good.today.player_sold += quantity
            self.state.merchants_today.purchases += amount
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

        - Goods saved but no longer defined are dropped (and plan items for them);
          goods defined but not in the save get a flat history as long as the
          saved ones'.
        - A block without workshops (sim_version 1, or saved before them) gets
          the established scenario's owners and workshops, fresh.
        - A block of sim_version 1 (P0, before the living market) keeps its
          histories and people, and each good's stock as a share of its new
          target (as scarce or glutted as it was); everything new starts from
          defaults: the outside price at its mean, a purse of PURSE_START_DAYS,
          targets and today's plan from the current demand. Its prices jump to
          the new model.
        - The random generator is restored last, so a loaded game draws exactly
          what the saved one would have.

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
        saved.goods = goods
        saved.population = saved.population or self.state.population
        saved.workshops = {k: w for k, w in saved.workshops.items() if w.building in self.buildings}
        self.state = saved
        if not saved.workshops and self.scenario is not None:
            self.establish(self.scenario)
        pop = self.state.population
        if pop is not None:
            population.give_housing(pop)
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
