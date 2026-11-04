# The simulation core (`src/sim/`)

The economy's state and rules, without pygame. The game drives it and reads it; the headless runner simulates decades of it in seconds. Roadmap project P0 (`roadmap.md`) built it. P1, the living market (`p1_living_market.md`), fills it in.

It holds:
- **The market** (`pricing.md` is its spec): each good's stock against a target of days of demand, an outside price walking slowly around its mean, merchants importing and exporting between two lines, a little noise, and well wishes.
- **The town's people**: per social class a head count, a purse, a basket of needs in three tiers bought from the market, happiness from how well the needs were met, and migration.

Production by the town's workshops (P1 phase 2) comes next. The goldens in `tests/sim/golden/` pin the behaviour of each phase.

---

## Rules

- **No pygame, no game.** Nothing in `src/sim/` imports pygame, `src/ui`, `src/handlers`, `src/models`, `src/game` or `src/game_state`. `tests/sim/test_no_pygame.py` imports every module of the package with `sys.modules["pygame"] = None` and fails on any of them.
- **One random generator.** Each `Simulation` owns one `random.Random(seed)` (`sim.rng`) and passes it to the systems that draw. No `random.random()`, `random.gauss()` or the like anywhere in `src/sim/`; the same test checks the source for them. The game's other randomness (weather, NPCs, sounds, the well's own odds) stays on the global `random` and does not touch the sim's stream.
- **Every number once.** The state lives in the dataclasses of `state.py` and nowhere else. The game's `Good`, `Town` and `PopulationManager` are views that look it up on every access (see "Seams" below).
- **The sim never calls out.** What the game may want to show goes on the event queue (`events.py`). The game drains it every update.
- **Definitions are data.** Goods, needs and recipes are JSON in `assets/data/`, checked when they are loaded. Global rules with a balancing meaning are in `src/config/constants.py`, each with a comment. Systems hold no magic numbers.
- **Same rules for everyone.** No code path special-cases an actor in a way the player or a rival dynasty couldn't use later (`roadmap.md`, pillar 1).

## Structure

| Module | What it holds |
|---|---|
| `calendar.py` | The game calendar (seasons of `DAYS_PER_SEASON` days, years of four seasons, weekdays, Lent, formatting), the ticks (`TICK_ORDER`: `price_tick`, `hour`, `day`, `week`, `season`, `year`), and `tick_numbers(moment)`, a number per kind of tick that changes exactly when that tick happens. Also `season_factor()`, a per-season factor blended smoothly between the seasons' middles. It is the only calendar; the game's `GameState.update()` counts its ticks with it too. |
| `scheduler.py` | `Scheduler`: handlers subscribe to a kind of tick. `advance_to(moment)` steps from price tick to price tick and fires every kind that changed at each, finest first, the handlers of one kind in the order they subscribed. `reset(moment)` moves the clock without firing (after loading, and for the pre-simulation). |
| `rng.py` | `make_rng(seed)`, `new_seed()` for a new game, and the generator's state as a plain JSON list (`state_to_json` / `state_from_json`). |
| `state.py` | `GoodState` (stock, target, demand average, outside price and its walk, noise, shock, histories, the day's flows), `ClassState` (head count, base, purse, happiness and its target, fulfilment per tier, today's `PlanItem`s, the day's money flows, histories), `PopulationState`, and `SimState` (all of it plus the market place's cash), each with `to_dict` / `from_dict`. Also `TownSpec`, the plain input a town is founded from (its houses' capacities). |
| `systems/market.py` | The market's rules as functions on a `GoodState`: `price`, `reference`, `volume_factor`, `ratio_for_factor`, `quote`, `clear_buyers` (a slice's household purchases), `merchants` (imports and exports), `step_outside`, `step_noise`, `update_target`, `apply_well_shock` / `tick_well_shock_day`, `record_*`. |
| `systems/households.py` | Each class's day: `start_day` (rate yesterday, earn, cap savings, plan), `plan`, `slice_orders`, `receive`, `fulfilment`, `needs_happiness`. |
| `systems/population.py` | Head counts and mood: `create_population`, `split_into_classes`, `crowding_shift`, `set_target`, `glide_happiness`, `update_population` (migration), `record_*`. |
| `events.py` | `SimEvent`s (`PriceShockEnded`, `PopulationChanged`) on an `EventQueue`. |
| `data.py` | `load_goods()`, `load_needs()` and `load_recipes()` read `assets/data/` into `GoodDef`, `ClassNeedsDef` / `NeedDef` and `RecipeDef`, raising `DataError` with the file, entry and field. |
| `simulation.py` | `Simulation`: state, definitions, generator, scheduler and events together. It subscribes the systems, founds the town, runs the economy ahead (`presimulate`), takes commands (`trade_with_player`, `apply_well_shock`), and saves and loads its block, migrating older ones. |
| `scenario/tmx_town.py` | An adapter, used only by the runner: reads the houses' `Max_inhabitants` from `Map1.tmx` with `xml.etree` into a `TownSpec`. The core never knows about TMX. The strategic map's towns (P7) will have no map file. |
| `run.py` | The headless runner. |

## Tick order

At each price tick the scheduler fires, in this order (the handlers of one kind as subscribed in `Simulation._subscribe_systems()`):

1. **price tick** (every `PRICE_TICK_MINUTES`, 30): for each good, `step_noise` (one draw), `record_tick`.
2. **hour**:
   - From `MARKET_OPEN_HOUR` to `MARKET_CLOSE_HOUR` (the slices ending at 07:00 … 18:00), a trading slice: every class's `slice_orders` at the current prices. Then for each good, the households' orders cleared together (`clear_buyers`, paid from the purses into the market's cash), then the merchants (`merchants`).
   - Every hour: `glide_happiness`, `record_happiness`.
3. **day** (midnight):
   - For each good: `close_day` (today's flows become yesterday's), `step_outside` (one draw), `tick_well_shock_day` (`PriceShockEnded` when one runs out), `update_target` from yesterday's demand.
   - For each class: `start_day` (rate yesterday's shopping, earn, cap savings, plan today at today's prices), and its target happiness from needs and crowding.
   - Then migration (`update_population`, `PopulationChanged` when the count moved), and the daily price records.
4. **week**, **season**, **year**: nothing subscribed yet. With `DAYS_PER_SEASON` 7, a week and a season begin on the same day.

The random draws follow from this order: one noise draw per good per price tick, and one outside-walk draw per good per day. The households and population draw nothing.

The game calls `sim.advance_to(game_state.date)` once per update, right after `GameState.update()`, then does its own hourly and daily work (crops, the church bell, the depot's books, licences, the merchant rank) on `GameState`'s flags. The player's trades (`Good.buy` / `Good.sell` → `Simulation.trade_with_player`) fall between the scheduler's ticks.

`Simulation.presimulate(days)` puts the clock back `days` and runs the whole economy forward to now. Then it cuts the people's histories to their last entry: the game's town charts start today, while the price charts open with history. A new game (and the runner) founds the town first and then presimulates `MARKET_PRESIMULATION_DAYS`.

## How to add a system

1. Put its state in `state.py`: a dataclass with `to_dict` / `from_dict`, hung off `SimState`. Defaults for fields older blocks lack go in `from_dict`.
2. Put its rules in `systems/<name>.py` as functions on that state (and `rng: random.Random` where they draw). Import balance values from `config/constants.py` by name, so tests can pin them. Per-good or per-class values go into the data files.
3. Subscribe it in `Simulation._subscribe_systems()` at the tick it runs on. **Where** it goes in the list decides the order of the random draws. Adding a draw anywhere changes every later number, so expect to regenerate the goldens (`python -m tests.sim.golden_harness --write`). Do that only when behaviour is *meant* to change, and say so in the commit.
4. Report what the game should show as an event in `events.py`, not by calling the game.
5. If the save's shape changes, raise `SIM_VERSION` and migrate the older block in `Simulation.load()`. The save's own `SAVE_VERSION` stays as it is.
6. Tests in `tests/sim/`: the rules on hand-made state with pinned constants (`tests/sim/builders.py` makes small definitions), and a save round trip.
7. Add its numbers to the runner's CSVs if they are worth looking at over decades.

## Saving

The save's `"sim"` block is `Simulation.to_dict()`:

```json
{"sim_version": 2, "seed": 2973952474, "rng": [3, [625 ints], null],
 "now": "1500-02-26T08:05:28", "state": {"goods": [...], "population": {...}, "market_cash": 1234.5}}
```

`"rng"` is `Random.getstate()` as a plain list, not a pickle. `Simulation.load()` restores the generator last, so a loaded game draws exactly what the saved one would have, and a save made mid-morning goes on with its plan half bought. Other rules on loading:
- Goods saved but no longer defined are dropped, and so are plan items for them.
- Goods defined but not saved get a flat history as long as the others'.
- A block newer than `SIM_VERSION` is refused (`SimVersionError`).
- **sim_version 1 (P0)** blocks migrate: each good keeps its histories, and its stock as a share of its new target. Each class keeps its count and happiness and gets a starting purse. Targets and today's plan are worked out from the current demand, and the outside prices start at their means.

Saves before `SAVE_VERSION` 3 have no `"sim"` block: `save_manager._legacy_sim_block()` builds a sim_version 1 block from their old `"goods"` and `"population"` entries, which then migrates the same way.

The seed is shown on the settings' weather page (debug overlay on). It reproduces a new game's economy until the player first trades or wishes at the well. A headless run with that seed shows the same economy without the player.

## The headless runner

```bash
python -m src.sim.run --years 20 --seed 1 --out runs/baseline
python -m src.sim.run --help        # --map, --presim-days
```

It starts as a new game does (the game's start moment, the town from `Map1.tmx`, the economy run ahead) and writes into the folder (`runs/` is git-ignored). Rows are taken at each midnight, after that day's systems ran; the flows are the day just ended. All files share `day, year, season, day_of_season`.

| File | One row per | Columns |
|---|---|---|
| `goods_daily.csv` | day × good | `good, price, outside_price, reference, stock, target_stock, wanted, bought, imported, exported, player_bought, player_sold` |
| `population_daily.csv` | day × class (and `All`) | `class, count, happiness, happiness_target, purse, income, spent, leaked, fulfilment_basic, fulfilment_comfort, fulfilment_luxury` |
| `town_daily.csv` | day | `citizens, purses, market_cash, money_supply` |
| `meta.json` | – | seed, years, days, start, `sim_version`, git commit and whether the tree was dirty, Python version, the goods, needs and town, every relevant constant, row counts, runtime |

`day` counts days since the calendar's first one. Floats are written as `repr`, so the same seed gives byte-identical CSVs. Reading them:

```python
import pandas as pd
goods = pd.read_csv("runs/baseline/goods_daily.csv")
goods.pivot(index="day", columns="good", values="price").plot(logy=True)
wheat = goods[goods.good == "Wheat"]
wheat.plot(x="day", y=["price", "outside_price"])
people = pd.read_csv("runs/baseline/population_daily.csv")
people[people["class"] != "All"].pivot(index="day", columns="class", values="fulfilment_luxury").plot()
```

50 years (1,400 days) take about 2 s here.

## Data files

`assets/data/` lives under `assets/` because the release build copies exactly the tracked files there (`build_tools/Release/build_release.py`), and `DATA_PATH` follows the game into the exe's `_internal/`. Unknown fields are refused everywhere, so a typo does not pass silently.

**`goods.json`**: `{"goods": [...]}`. Each entry has `name` (unique), `color` (a colour's name in `src/config/colors.py`, checked by the game), `chart_index` (unique), `show_in_charts`, and the market's fields: `outside_price`, `outside_reversion`, `outside_volatility`, optional `outside_seasons`, `transport_cost`, `import_limit`, `export_limit`, `target_stock_days`, `min_target_stock` and `noise_sigma` (`pricing.md` §1 explains them). The list's order is the order of the random draws, so a new good goes at the end.

**`needs.json`**: `{"classes": [...]}`, one entry per class in `systems.population.class_shares()`, all of them:

| Field | Meaning |
|---|---|
| `class` | Poor, Commons, Middling Sort or Nobility |
| `base_income` | Per head per day, from the work that is not simulated |
| `labour_share` | The share of heads that can take a job (phase 2) |
| `happiness_weights` | `{"basic": w, "comfort": w, "luxury": w}`, adding up to 1 |
| `basic`, `comfort`, `luxury` | `{good: units per head per day}`. A value may be `{"units": x, "seasons": {"Winter": 1.6}}` to change with the seasons. |

The tiers are bought in that order. Phase 1 uses stand-ins until the new goods exist (Wheat for Bread, Fish for Salted Fish, Linen for Garments, Hide for Shoes, Salt for Spices); swapping them is a data edit.

**`recipes.json`**: `{"recipes": [...]}`. Each entry has `id` (unique), optional `name` and `description`, `inputs` (good → whole units ≥ 1 per batch, may be empty for a raw good), `outputs` (the same, at least one), `labour` (worker-days per batch, ≥ 0) and `days` (how long a batch takes, > 0). Every good named must be in `goods.json`. There is one example entry. Phase 2 runs them, adds `building`, and allows fractions for tool wear.

## Seams to collapse later

`Good` (`src/models/good.py`), `Town` (`src/models/institutions/town.py`) and `PopulationManager` (`src/models/population.py`) are kept as **pass-through views**, so the depot, the charts and the menus did not have to change. They hold no numbers of their own: every property reads the sim's state on each access (`tests/sim/test_views.py` changes the state directly and checks they show it). What they still keep is UI state only: a good's colours, chart index, visibility and hover. Do not build new features on them. New code should read `sim.state` or call `systems.*`, and the views should shrink away as their callers move over. `Town.treasury` is not part of the sim yet (P6).

## Next candidates for the sim

Not moved yet, in rough order of value:

- **The depot's daily books** (cost of living, loans, overdraft, wealth history). P3 turns the player into an owner like the town (`p1_living_market.md`, "Owners"), so the player, the AI dynasties and the town share them.
- **Weather** (`src/models/weather.py`), which already runs on game time and is saved. It would need the sim's generator and a pygame-free split of `Weather` from its sounds.
- **Crop growth** (`src/models/crop_growth.py`), already a pure function of the date. The roadmap keeps harvests cosmetic, but a farm's look could follow its workshop.
- **The well's odds and cooldown** (`src/models/institutions/well.py`), still on the global `random`.
- **The merchant rank's daily check and reputation decay** (`src/models/merchant_rank.py`), once prestige (P2) becomes a currency.
