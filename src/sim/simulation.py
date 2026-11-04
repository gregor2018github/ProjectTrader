"""The simulation: state, random generator, scheduler and event queue in one object.

The game (or the headless runner) builds one ``Simulation``, moves its clock
with ``advance_to()`` and reads ``state``; the systems run on the scheduler's
ticks in the order they are subscribed in ``_subscribe_systems()``:

    price tick   market: recover volume, step the walk, chart point (each good)
    hour         population: happiness drift, history
    day          market: bookkeeping point, well shock countdown (each good);
                 population: migration, history

That is the order ``Game.run()`` ran them in before they moved here.
"""
import datetime
from typing import Any, Dict, Optional, Sequence

from ..config.constants import PRICE_TICKS_PER_DAY
from . import calendar
from .data import GoodDef
from .events import EventQueue, PopulationChanged, PriceShockEnded
from .rng import make_rng, state_from_json, state_to_json
from .scheduler import Scheduler
from .state import GoodState, SimState, TownSpec
from .systems import market, population

SIM_VERSION = 1     # the save's "sim" block; raise it (and migrate in load()) when its shape changes


class SimVersionError(ValueError):
    """A save's sim block is newer than this simulation can read."""


class Simulation:
    """The headless economy: goods' prices and volumes, the town's people."""

    def __init__(self, goods: Sequence[GoodDef], now: datetime.datetime, seed: int,
                 town: Optional[TownSpec] = None) -> None:
        """Create the goods (two corridor draws each, in order) and, if given, the town.

        Args:
            goods: The goods' definitions, in creation order.
            now: Where the clock starts; nothing fires for it.
            seed: The random generator's seed.
            town: The town to found now; ``found_town()`` can do it later.
        """
        self.seed: int = seed
        self.rng = make_rng(seed)
        self.events = EventQueue()
        self.definitions: Dict[str, GoodDef] = {d.name: d for d in goods}
        self.state = SimState(goods={
            d.name: market.create_good(d.name, d.start_price, d.start_quantity, self.rng) for d in goods
        })
        if town is not None:
            self.found_town(town)
        self.scheduler = Scheduler(now)
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
        self.scheduler.subscribe(calendar.HOUR, self._population_hour)
        self.scheduler.subscribe(calendar.DAY, self._market_day)
        self.scheduler.subscribe(calendar.DAY, self._population_day)

    def _market_tick(self, moment: datetime.datetime) -> None:
        for good in self.state.goods.values():
            market.recover_volume(good)
            market.step_walk(good, self.rng)
            market.record_tick(good)

    def _market_day(self, moment: datetime.datetime) -> None:
        for good in self.state.goods.values():
            market.record_day(good)
            if market.tick_well_shock_day(good):
                self.events.push(PriceShockEnded(moment, good.name))

    def _population_hour(self, moment: datetime.datetime) -> None:
        pop = self.state.population
        if pop is not None:
            population.update_happiness(pop, self.rng)
            population.record_happiness(pop)

    def _population_day(self, moment: datetime.datetime) -> None:
        pop = self.state.population
        if pop is not None:
            old_total, new_total = population.update_population(pop)
            population.record_population(pop)
            if new_total != old_total:
                self.events.push(PopulationChanged(moment, old_total, new_total))

    # -- setting up --------------------------------------------------------

    def found_town(self, town: TownSpec) -> None:
        """Give the simulation its town's people, the houses STARTING_OCCUPANCY full."""
        self.state.population = population.create_population(town)

    def presimulate(self, days: int) -> None:
        """Run the price walk *days* days without moving the clock, so the charts open with a history.

        Only the walk and the histories: no volume recovery (the markets are at
        normal), no people, as the game has always done before its first frame.
        """
        goods = list(self.state.goods.values())
        for _ in range(days):
            for _ in range(PRICE_TICKS_PER_DAY):
                for good in goods:
                    market.step_walk(good, self.rng)
                    market.record_tick(good)
            for good in goods:
                market.record_day(good)

    # -- commands from the game ---------------------------------------------

    def good(self, name: str) -> GoodState:
        return self.state.goods[name]

    def apply_well_shock(self, name: str, up: bool) -> None:
        market.apply_well_shock(self.state.goods[name], up)

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
        """Take over a ``"sim"`` block written by ``to_dict()``.

        Goods saved but no longer defined are dropped; goods defined but not in
        the save keep what they have and get a made-up history as long as the
        saved ones'. The random generator is restored last, so a loaded game
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
        saved = SimState.from_dict(data["state"])
        ticks = max((len(g.price_history_ticks) for g in saved.goods.values()), default=1)
        days = max((len(g.price_history_daily) for g in saved.goods.values()), default=1)
        goods: Dict[str, GoodState] = {}
        for name in self.definitions:
            if name in saved.goods:
                goods[name] = saved.goods[name]
            else:
                good = self.state.goods[name]
                market.simulate_history(good, ticks, days, self.rng)
                goods[name] = good
        self.state = SimState(goods=goods, population=saved.population or self.state.population)
        self.seed = int(data.get("seed", self.seed))
        if "rng" in data:
            state_from_json(self.rng, data["rng"])
        self.scheduler.reset(now if now is not None else datetime.datetime.fromisoformat(data["now"]))
