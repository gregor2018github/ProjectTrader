# The simulation core (`src/sim/`)

The economy's state and rules, without pygame. The game drives it and reads it; the headless runner simulates decades of it in seconds. Roadmap project P0 (`roadmap.md`) built it. P1, the living market (`p1_living_market.md`), fills it in.

It holds:
- **The market** (`pricing.md` is its spec): each good's stock against a target of days of demand, an outside price walking slowly around its mean, merchants importing and exporting between two lines, a little noise, and well wishes.
- **The town's people**: per social class a head count, a purse, a basket of needs in three tiers bought from the market, happiness from how well the needs were met, jobs, and migration.
- **Workshops and their owners**: each workshop runs its building's recipe as hard as its margin says. It hires from one class (pro rata when hands are short), sells into the market, grows after busy spells and shrinks after losses. Its owner tops it up and takes its profits. No rule reads what kind of owner it is.
- **Money**: the market place holds none (the merchants own the stock), so the town's money changes by exactly what crosses its border, and `market_balance` checks it.

The 30 goods and their chains (P1.3) are in; so is the health report's full set of checks over 20 seeds × 50 years (P1.4); a minimal UI (P1.5) comes next. The goldens in `tests/sim/golden/` pin the living market as it stands, and are regenerated whenever its behaviour is meant to change.

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
| `state.py` | `GoodState` (stock, target, demand average, outside price and its walk, noise, shock, histories, the day's flows), `ClassState` (head count, base, housing share, jobs, purse, happiness and its target, fulfilment per tier, today's `PlanItem`s, the day's money flows, histories), `PopulationState`, `OwnerState`, `WorkshopState`, `TownMoney` (the town's border flows and the `market_balance`), `MerchantFlows` (the merchants' book), and `SimState` (all of it), each with `to_dict` / `from_dict`. Also `TownSpec`, the plain input a town is founded from (its houses' capacities). |
| `systems/market.py` | The market's rules as functions on a `GoodState`: `price`, `reference`, `volume_factor`, `ratio_for_factor`, `quote`, `clear_buyers` (a slice's household purchases), `merchants` (imports and exports), `step_outside`, `step_noise`, `update_target`, `apply_well_shock` / `tick_well_shock_day`, `record_*`. |
| `systems/households.py` | Each class's day: `start_day` (rate yesterday, earn base income, wages and payouts, cap savings, plan), `plan` (tier by tier, buying less of a good the dearer it is above its outside price: `dearness_factor`), `slice_orders`, `receive`, `fulfilment` (against the whole basket), `needs_happiness`. |
| `systems/production.py` | Workshops and owners: `batch_margin`, `wanted_utilisation`, `plan_wants` and `hire` (planning in two halves, so a class's hands are shared pro rata), `move_wage` (a class's wage with the demand for its hands), `slice_orders`, `run_slice`, `settle_day` (wages, the owner's top-up and profit), `owner_day` / `treasury_cap` (the owner's surplus rule), `change_capacity` (growth and shrinking). |
| `systems/population.py` | Head counts and mood: `create_population`, `split_into_classes`, `crowding_shift` (against the class's share of the housing), `set_target`, `glide_happiness`, `update_population` (migration, held within 0.3–1.05 × the class's housing), `record_*`. |
| `events.py` | `SimEvent`s (`PriceShockEnded`, `PopulationChanged`, `CapacityChanged`) on an `EventQueue`. |
| `data.py` | `load_definitions()` reads goods, needs, recipes and building types from `assets/data/` into a `Definitions` (`GoodDef`, `ClassNeedsDef` / `NeedDef`, `RecipeDef`, `BuildingDef`); `load_scenario()` reads `scenarios/<name>.json` into a `ScenarioDef` (`OwnerDef`, `WorkshopSeed`). Each raises `DataError` with the file, entry and field. |
| `simulation.py` | `Simulation`: state, definitions, generator, scheduler and events together. It subscribes the systems, founds the town and establishes the scenario's workshops, runs the economy ahead (`presimulate`), takes commands (`trade_with_player`, `apply_well_shock`), keeps the books (`town_money`, `_close_books`), and saves and loads its block, migrating older ones. |
| `health.py` | The health report for a headless run (`python -m src.sim.health runs/<name> ...`): every check of `p1_living_market.md` ("Health metrics"), each a `Finding` in `CHECKS`, and the tradability measure. |
| `sweep.py` | Many seeds at once (`python -m src.sim.sweep`, default 20 seeds × 50 years into `runs/sweep/`): runs them in parallel, checks each, and writes the table over them (`summary.md`, `summary.csv`). |
| `scenario/tmx_town.py` | An adapter, used only by the runner: reads the houses' `Max_inhabitants` from `Map1.tmx` with `xml.etree` into a `TownSpec`. The core never knows about TMX. The strategic map's towns (P7) will have no map file. |
| `run.py` | The headless runner. |

## Tick order

At each price tick the scheduler fires, in this order (the handlers of one kind as subscribed in `Simulation._subscribe_systems()`):

1. **price tick** (every `PRICE_TICK_MINUTES`, 30): for each good, `step_noise` (one draw), `record_tick`.
2. **hour**:
   - From `MARKET_OPEN_HOUR` to `MARKET_CLOSE_HOUR` (the slices ending at 07:00 … 18:00), a trading slice:
     1. every class's and every workshop's orders at the current prices;
     2. each good's buyers cleared together (`clear_buyers`, one price, pro rata when short), paying the merchants;
     3. each workshop runs its share of the day's batches as far as its inputs allow (`run_slice`), and the merchants buy the outputs, one price per good;
     4. the merchants import and export (`merchants`), paying the outside price and transport themselves.
   - Every hour: `glide_happiness`, `record_happiness`.
3. **day** (midnight):
   1. The books close (`_close_books`): the town's money is checked against the day's border flows (`market_balance`).
   2. For each good: `close_day`, `step_outside` (one draw), `tick_well_shock_day` (`PriceShockEnded`), `update_target` from yesterday's demand (households' wants plus workshops' input wants).
   3. For each workshop: `settle_day` (pay yesterday's workers at the wage they were hired at; the owner tops it up to working capital and takes the rest); then each owner's `owner_day`: its average income moves, and its `surplus_to` acts (keep, pay out per head, or treasury up to its cap and the rest as tribute, out of town).
   4. For each class: `start_day` (rate yesterday's shopping, earn base income for the heads without a job plus wages and payouts, cap savings, plan today), and its target happiness from needs and crowding.
   5. Migration (`update_population`, `PopulationChanged`).
   6. For each workshop: `plan_wants` at its class's wage; each class's wage moves with the tension between the workers wanted and its free hands (`move_wage`); the hands shared pro rata (`hire`); input wants; `change_capacity` (`CapacityChanged`, growth paid to builders out of town).
   7. The daily price records.
4. **week**, **season**, **year**: nothing subscribed yet. With `DAYS_PER_SEASON` 7, a week and a season begin on the same day.

The random draws follow from this order: one noise draw per good per price tick, and one outside-walk draw per good per day. Households, workshops and the population draw nothing.

The game calls `sim.advance_to(game_state.date)` once per update, right after `GameState.update()`, then does its own hourly and daily work (crops, the church bell, the depot's books, licences, the merchant rank) on `GameState`'s flags. The player's trades (`Good.buy` / `Good.sell` → `Simulation.trade_with_player`) fall between the scheduler's ticks.

`Simulation.presimulate(days)` puts the clock back `days` and runs the whole economy forward to now. Then it cuts the people's histories to their last entry: the game's town charts start today, while the price charts open with history. A new game (and the runner) founds the town, establishes the `home_town` scenario's workshops, and then presimulates `MARKET_PRESIMULATION_DAYS`.

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
 "now": "1500-02-26T08:05:28", "state": {"goods": [...], "population": {...}, "owners": [...], "workshops": [...],
           "money_today": {...}, "money_mark": 8123.4, "merchants_today": {...}, ...}}
```

`"rng"` is `Random.getstate()` as a plain list, not a pickle. `Simulation.load()` restores the generator last, so a loaded game draws exactly what the saved one would have, and a save made mid-morning goes on with its plan half bought. Other rules on loading:
- Goods saved but no longer defined are dropped, and so are plan items for them.
- Goods defined but not saved get a flat history as long as the others'.
- A block without workshops (sim_version 1, or saved before P1.2) gets the established scenario's owners and workshops, fresh.
- A block newer than `SIM_VERSION` is refused (`SimVersionError`).
- **sim_version 1 (P0)** blocks migrate: each good keeps its histories, and its stock as a share of its new target. Each class keeps its count and happiness and gets a starting purse. Targets and today's plan are worked out from the current demand, and the outside prices start at their means.

Saves before `SAVE_VERSION` 3 have no `"sim"` block: `save_manager._legacy_sim_block()` builds a sim_version 1 block from their old `"goods"` and `"population"` entries, which then migrates the same way.

The seed is shown on the settings' weather page (debug overlay on). It reproduces a new game's economy until the player first trades or wishes at the well. A headless run with that seed shows the same economy without the player.

## The headless runner

```bash
python -m src.sim.run --years 20 --seed 1 --out runs/baseline
python -m src.sim.run --help        # --map, --scenario, --presim-days
python -m src.sim.health runs/baseline runs/other    # the health report, one or more runs
python -m src.sim.sweep                               # 20 seeds x 50 years, checked, into runs/sweep (about 25 s)
```

It starts as a new game does (the game's start moment, the town from `Map1.tmx`, the economy run ahead) and writes into the folder (`runs/` is git-ignored). Rows are taken at each midnight, after that day's systems ran; the flows are the day just ended. All files share `day, year, season, day_of_season`.

| File | One row per | Columns |
|---|---|---|
| `goods_daily.csv` | day × good | `good, price, outside_price, reference, stock, target_stock, wanted, bought, unmet, input_wanted, input_bought, produced, imported, exported, player_bought, player_sold, least_share` (`unmet`: what households asked for in a slice that the market had run out of; `least_share`: the smallest share of its whole basket of the good any class bought that day, read after the market closed, 1 if none wanted it) |
| `population_daily.csv` | day × class (and `All`) | `class, count, employed, labour_wanted, wage, happiness, happiness_target, purse, income, wages, payouts, spent, leaked, fulfilment_basic, fulfilment_comfort, fulfilment_luxury` |
| `workshops_daily.csv` | day × workshop | `workshop, owner, building, capacity, utilisation, margin, planned, done_yesterday, workers, cash` |
| `town_daily.csv` | day | `citizens, money_supply, purses, workshop_cash, owner_cash, money_created, money_leaked, money_invested, money_tribute, paid_to_merchants, paid_by_merchants, market_balance`, and the merchants' book: `merchant_sales, merchant_purchases, merchant_import_cost, merchant_export_revenue, merchant_transport, merchant_profit` |
| `meta.json` | – | seed, years, days, start, `sim_version`, git commit and whether the tree was dirty, Python version, the definitions, scenario and town, every relevant constant, row counts, runtime |

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

50 years (1,400 days) take about 6 s here.

**The health report** (`src/sim/health.py`) prints one line per check: `ok`, `warn` or `FAIL`, and the worst offender with its days. The checks and their thresholds are in `p1_living_market.md` ("Health metrics") and the module's docstring; the thresholds are its constants. It fails a run for broken books (`market_balance` not zero within `BALANCE_TOLERANCE` of the money supply on any day), NaNs or negative stocks, purses or counts, a price pinned at a volume factor clamp, hunger, a runaway money supply or population, or a workshop long in debt. It warns about prices far from outside, poorly supplied or unhappy classes, dead workshops and structural shortages. It also warns unless the town runs slightly short: each class's mean comfort fulfilment in `COMFORT_BAND` (0.80–0.95) and luxury in `LUXURY_BAND` (0.30–0.70), and at least `SHORT_GOODS_MIN` (3) goods the town ran short of (some class bought less than `SHORT_BELOW`, 90 %, of its whole basket of it, for any reason: `least_share`) on more than `SHORT_DAYS_SHARE` (5 %) of days. It also prints the tradability measure: per good, the median 30-day price range against the price, and how often that range on a lot worth `TRADE_LOT_VALUE` (100) at the day's price (whole units, at least 1) beats twice that lot's round trip (two fees plus slippage both ways). The range is an upper bound on what a trader could catch, since it ignores whether the high came before the low.

**The sweep** (`src/sim/sweep.py`) is the health report over many seeds: `python -m src.sim.sweep [--seeds 20] [--years 50] [--out runs/sweep] [--jobs N] [--reuse]`. It writes each run to `<out>/seed<N>/`, prints its progress, then the table: per check, the counts of ok, warn and fail, the median and the worst seed's number; a grid of every check per seed; the worst case of every check that missed; and the tradability per good, its median over the seeds. It writes the same as `summary.md`, and one row per seed and check to `summary.csv`, to compare a calibration change before and after. It exits with 1 when any seed fails.

## Data files

`assets/data/` lives under `assets/` because the release build copies exactly the tracked files there (`build_tools/Release/build_release.py`), and `DATA_PATH` follows the game into the exe's `_internal/`. Unknown fields are refused everywhere, so a typo does not pass silently.

**`goods.json`**: `{"goods": [...]}`, the game's one list of goods.
- **Identity:** `name` (unique), `color` (a colour's name in `src/config/colors.py`, checked by the game), `chart_index` (unique), `show_in_charts`.
- **Market:** `outside_price`, `outside_reversion`, `outside_volatility`, optional `outside_seasons`, `transport_cost`, `import_limit`, `export_limit`, `target_stock_days`, `min_target_stock` and `noise_sigma` (`pricing.md` §1 explains them).
- **Licence:** `license`, the licence (a guild's) it is traded under. That is a good's name, its own if left out. The good a licence is named after sets `license_fee` (per season) and `starting_license_seasons`, and no other good may. `Definitions.licenses()` gives the licences, each with the goods it covers.
- **Booths:** `sold_at`, the market booths that carry it besides those named after it.
- **Order:** the list's order is the order of the random draws (so a new good goes at the end), and of the goods everywhere in the game.

**`needs.json`**: `{"classes": [...]}`, one entry per class in `systems.population.class_shares()`, all of them:

| Field | Meaning |
|---|---|
| `class` | Poor, Commons, Middling Sort or Nobility |
| `base_income` | Per head per day, from the work that is not simulated |
| `labour_share` | The share of heads that can take a job |
| `wage_cap` | The most its wage rises to when its hands are short (at least `base_income`, the least its wage falls to) |
| `elasticity` | `{"basic": e, "comfort": e, "luxury": e}`: above a good's outside price the class buys `basket × (price / outside price) ^ −e` of it (no more than its basket below it); a need may set its own `"elasticity"` |
| `happiness_weights` | `{"basic": w, "comfort": w, "luxury": w}`, adding up to 1 |
| `basic`, `comfort`, `luxury` | `{good: units per head per day}`. A value may be `{"units": x, "seasons": {"Winter": 1.6}, "elasticity": e}` to change with the seasons or have its own elasticity. |

The tiers are bought in that order.

**`recipes.json`**: `{"recipes": [...]}`. Each entry has `id` (unique), optional `name` and `description`, `inputs` (good → units per batch, numbers > 0, fractions allowed for wear; may be empty for a raw good), `outputs` (the same, at least one; several make byproducts) and `labour` (worker-days per batch, ≥ 0). Every good named must be in `goods.json`.

**`buildings.json`**: `{"buildings": [...]}`. Each entry has `type` (unique), `name`, `recipe` (an id in `recipes.json`), `workers_class` (the class it hires from, at that class's wage), `max_capacity` (batches a day), `growth_cost` (money per batch a day of growth, paid out of town), and `working_capital` (cash it keeps before profits go to its owner).

**`scenarios/<name>.json`**: `{"owners": [...], "workshops": [...]}`.
- An owner has `id`, `kind` (a label; no rule reads it), `name`, `cash`, `reserve`, and `surplus_to`: `keep`; `townsfolk` (cash above the reserve paid out per head); or `treasury_with_tribute` (kept up to `TREASURY_CAP_DAYS` of its average net income, or its reserve, the rest paid to the lord out of town; the home town's).
- A workshop has `id`, `owner`, `building` (a type in `buildings.json`), `capacity` (batches a day) and `cash`.
- `home_town.json` is the game's.

## Seams to collapse later

`Good` (`src/models/good.py`), `Town` (`src/models/institutions/town.py`) and `PopulationManager` (`src/models/population.py`) are kept as **pass-through views**, so the depot, the charts and the menus did not have to change. They hold no numbers of their own: every property reads the sim's state on each access (`tests/sim/test_views.py` changes the state directly and checks they show it). What they still keep is UI state only: a good's colours, chart index, visibility and hover. Do not build new features on them. New code should read `sim.state` or call `systems.*`, and the views should shrink away as their callers move over. `Town.treasury` is not part of the sim yet (P6).

## Next candidates for the sim

Not moved yet, in rough order of value:

- **The depot's daily books** (cost of living, loans, overdraft, wealth history). P3 turns the player into an owner like the town (`OwnerState`, `p1_living_market.md` "Owners"), so the player, the AI dynasties and the town share them.
- **Weather** (`src/models/weather.py`), which already runs on game time, is saved, imports no pygame (its sounds live in `Ambience` and `Lightning`) and takes a `random.Random` of its own (the game passes none, so it makes an unseeded one). It would need a generator seeded from the sim's, and its state in the sim's block.
- **Crop growth** (`src/models/crop_growth.py`), already a pure function of the date. Harvests are cosmetic so far, a decision now under reconsideration (`roadmap.md`, "Seasons & fields"): the farms' output could follow the fields, or at least a farm's look could follow its workshop.
- **The well's odds and cooldown** (`src/models/institutions/well.py`), still on the global `random`.
- **The merchant rank's daily check and reputation decay** (`src/models/merchant_rank.py`), once prestige (P2) becomes a currency.
