# The simulation core (`src/sim/`)

The economy's state and rules, without pygame. The game drives it and reads it; the headless runner simulates decades of it in seconds. Roadmap project P0 (`roadmap.md`). P1 (supply, demand, needs, production) is built on top of it.

So far it holds the market (the price walk, the volume factor, slippage, the volume's recovery, the well shock; `pricing.md` is their spec) and the town's population (hourly happiness drift, daily migration). That is the behaviour the game had before, moved here unchanged: the golden tests (`tests/sim/golden/`) pin it to the last bit.

---

## Rules

- **No pygame, no game.** Nothing in `src/sim/` imports pygame, `src/ui`, `src/handlers`, `src/models`, `src/game` or `src/game_state`. `tests/sim/test_no_pygame.py` imports every module of the package with `sys.modules["pygame"] = None` and fails on any of them.
- **One random generator.** Each `Simulation` owns one `random.Random(seed)` (`sim.rng`) and passes it to the systems that draw. No `random.random()`, `random.normalvariate()` or the like anywhere in `src/sim/`; the same test checks the source for them. The game's other randomness (weather, NPCs, sounds, the well's own odds) stays on the global `random` and does not touch the sim's stream.
- **Every number once.** The state lives in the dataclasses of `state.py` and nowhere else. The game's `Good`, `Town` and `PopulationManager` are views that look it up on every access (see "Seams" below).
- **The sim never calls out.** What the game may want to show goes on the event queue (`events.py`). The game drains it every update.
- **Definitions are data.** Goods (and recipes, for later) are JSON in `assets/data/`, checked when they are loaded.

## Structure

| Module | What it holds |
|---|---|
| `calendar.py` | The game calendar (seasons of `DAYS_PER_SEASON` days, years of four seasons, weekdays, Lent, formatting) and the ticks: `TICK_ORDER` (`price_tick`, `hour`, `day`, `week`, `season`, `year`) and `tick_numbers(moment)`, a number per kind of tick that changes exactly when that tick happens. It is the only calendar. The game's `GameState.update()` counts its ticks with it too. |
| `scheduler.py` | `Scheduler`: handlers subscribe to a kind of tick; `advance_to(moment)` steps from price tick to price tick and fires every kind that changed at each, finest first, the handlers of one kind in the order they subscribed. `reset(moment)` moves the clock without firing (after loading). |
| `rng.py` | `make_rng(seed)`, `new_seed()` for a new game, and the generator's state as a plain JSON list (`state_to_json` / `state_from_json`). |
| `state.py` | `GoodState` (walk price, base price, market and normal quantity, corridor, well shock, chart and daily histories), `ClassState` and `PopulationState` (head count, base, happiness, histories), `SimState` (both), each with `to_dict` / `from_dict`; and `TownSpec`, the plain input a town is founded from (its houses' capacities). |
| `systems/market.py` | The market's rules as functions on a `GoodState`: `create_good`, `price`, `volume_factor`, `quote`, `take` / `put` (a trade), `recover_volume`, `step_walk`, `record_tick` / `record_day`, `simulate_history`, `apply_well_shock` / `tick_well_shock_day`. |
| `systems/population.py` | The town's people as functions on a `PopulationState`: `create_population`, `split_into_classes`, `update_happiness`, `update_population`, `record_*`. |
| `events.py` | `SimEvent`s (`PriceShockEnded`, `PopulationChanged`) on an `EventQueue`. |
| `data.py` | `load_goods()` / `load_recipes()` read `assets/data/goods.json` and `recipes.json` into `GoodDef` / `RecipeDef`, raising `DataError` naming file, entry and field. |
| `simulation.py` | `Simulation`: state, generator, scheduler and events together; subscribes the systems, pre-simulates the market, takes commands (`apply_well_shock`), saves and loads its block. |
| `scenario/tmx_town.py` | An adapter, used only by the runner: reads the houses' `Max_inhabitants` from `Map1.tmx` with `xml.etree` into a `TownSpec`. The core never knows about TMX. The strategic map's towns (P7) will have no map file. |
| `run.py` | The headless runner. |

## Tick order

At each price tick the scheduler fires, in this order (handlers of one kind as subscribed in `Simulation._subscribe_systems()`):

1. **price tick** (every `PRICE_TICK_MINUTES`, 30): for each good, `recover_volume`, `step_walk`, `record_tick`.
2. **hour**: `update_happiness` (one draw per class), `record_happiness`.
3. **day** (midnight): for each good, `record_day` and `tick_well_shock_day` (`PriceShockEnded` when one runs out); then `update_population` (`PopulationChanged` when the head count moved) and `record_population`.
4. **week**, **season**, **year**: nothing subscribed yet. With `DAYS_PER_SEASON` 7, a week and a season begin on the same day.

That is the order `Game.run()` ran them in before. The random draws follow from it: two corridor draws per good when it is created (in `goods.json` order), one walk draw per good per price tick, one happiness draw per class per hour.

The game calls `sim.advance_to(game_state.date)` once per update, right after `GameState.update()`, then does its own hourly and daily work (crops, the church bell, the depot's books, licences, the merchant rank) on `GameState`'s flags. None of that changes prices, so the order between the two does not matter.

`Simulation.presimulate(days)` runs only the walk and the histories, without moving the clock, as a new game always has: the charts open with `MARKET_PRESIMULATION_DAYS` of history.

## How to add a system

1. Put its state in `state.py`: a dataclass with `to_dict` / `from_dict`, hung off `SimState`. Defaults for fields that old saves lack go in `from_dict`.
2. Put its rules in `systems/<name>.py` as functions on that state (and `rng: random.Random` where they draw). Import balance values from `config/constants.py` by name, so tests can pin them.
3. Subscribe it in `Simulation._subscribe_systems()` at the tick it runs on. **Where** it goes in the list decides the order of the random draws. Adding a draw anywhere changes every later number, so expect to regenerate the goldens (`python -m tests.sim.golden_harness --write`) only when behaviour is *meant* to change, and say so in the commit.
4. Report what the game should show as an event in `events.py`, not by calling the game.
5. If the save's shape changes, raise `SIM_VERSION` and migrate the older block in `Simulation.load()`. The save's own `SAVE_VERSION` stays as it is.
6. Tests in `tests/sim/`: the rules on hand-made state with pinned constants, and a save round trip.
7. Add its numbers to the runner's CSVs if they are worth looking at over decades.

## Saving

The save's `"sim"` block is `Simulation.to_dict()`:

```json
{"sim_version": 1, "seed": 2973952474, "rng": [3, [625 ints], null],
 "now": "1500-02-26T08:05:28", "state": {"goods": [...], "population": {...}}}
```

`"rng"` is `Random.getstate()` as a plain list, not a pickle. `Simulation.load()` restores the generator last, so a loaded game draws exactly what the saved one would have. Goods saved but no longer defined are dropped. Goods defined but not saved get a made-up history as long as the others' (`market.simulate_history`). A block newer than `SIM_VERSION` is refused (`SimVersionError`).

Saves before `SAVE_VERSION` 3 have no `"sim"` block: `save_manager._legacy_sim_block()` builds one from their old `"goods"` and `"population"` entries, with the same fallbacks the loader always had (corridor, normal volume, the classes' base head counts from the new game; their generator is not restored, there being none saved). The save's `"goods"` keeps only how the UI shows each good (chart visibility, colour).

The seed is shown on the settings' weather page (debug overlay on). It reproduces a new game's market until the player first trades or wishes at the well. A headless run with that seed shows the same economy without the player.

## The headless runner

```bash
python -m src.sim.run --years 20 --seed 1 --out runs/baseline
python -m src.sim.run --help        # --map, --presim-days
```

It starts as a new game does (the game's start moment, the pre-simulated market, the town from `Map1.tmx`) and writes into the folder (`runs/` is git-ignored):

| File | One row per | Columns |
|---|---|---|
| `goods_daily.csv` | day × good | `day, year, season, day_of_season, good, price, walk_price, market_quantity, normal_quantity, upper_bound, lower_bound` |
| `population_daily.csv` | day × class (and `All` for the town) | `day, year, season, day_of_season, class, count, happiness` |
| `meta.json` | – | seed, years, days, start, `sim_version`, git commit and whether the tree was dirty, Python version, the goods and the town, every relevant constant, row counts, runtime |

Rows are taken at each midnight, after that day's systems ran. `day` counts days since the calendar's first one. Floats are written as `repr`, so the same seed gives byte-identical CSVs. Reading them:

```python
import pandas as pd
goods = pd.read_csv("runs/baseline/goods_daily.csv")
goods.pivot(index="day", columns="good", values="price").plot(logy=True)
people = pd.read_csv("runs/baseline/population_daily.csv")
people[people["class"] == "All"].plot(x="day", y=["count", "happiness"], secondary_y="happiness")
```

20 years (560 days, 29,760 price ticks for 15 goods) take about 0.3 s here.

## Data files

`assets/data/` lives under `assets/` because the release build copies exactly the tracked files there (`build_tools/Release/build_release.py`), and `DATA_PATH` follows the game into the exe's `_internal/`.

**`goods.json`**: `{"goods": [...]}`, each entry:

| Field | Type | Meaning |
|---|---|---|
| `name` | string, unique | The good's name everywhere (save, depot, pictures `<name>_30.png`) |
| `start_price` | number > 0 | The walk's starting price |
| `start_quantity` | whole number ≥ 1 | The market's starting and normal volume |
| `color` | string | A colour's name in `src/config/colors.py` (the game checks it exists) |
| `chart_index` | whole number ≥ 0, unique | Its place in the charts and lists |
| `show_in_charts` | true / false | In the price chart when a game starts |

The order of the list is the order the goods are created in, and so the order of the random draws. A new good goes at the end. Unknown fields are refused, so a typo does not pass silently.

**`recipes.json`**: `{"recipes": [...]}`, each entry `id` (string, unique), optional `name` and `description`, `inputs` (good → whole units ≥ 1 per batch, may be empty for a raw good), `outputs` (the same, at least one), `labour` (worker-days per batch, ≥ 0), `days` (how long a batch takes, > 0). Every good named must be in `goods.json`. There is one example entry. Nothing runs recipes yet.

## Seams to collapse later

`Good` (`src/models/good.py`), `Town` (`src/models/institutions/town.py`) and `PopulationManager` (`src/models/population.py`) are kept for P0 as **pass-through views**, so the depot, the charts and the menus did not have to change. They hold no numbers of their own: every property reads the sim's state on each access (`tests/sim/test_views.py` changes the state directly and checks they show it). What they still keep is UI state only: a good's colours, chart index, visibility and hover. Do not build new features on them. New code should read `sim.state` or call `systems.*`, and the views should shrink away as their callers move over. `Town.treasury` is not part of the sim yet (P6).

## Next candidates for the sim

Not moved in P0, in rough order of value:

- **The depot's daily books** (cost of living, loans, overdraft, wealth history), as P1/P3's owners (player, AI dynasties, the town) will share them: "same rules for everyone".
- **Weather** (`src/models/weather.py`), which already runs on game time and is saved. It would need the sim's generator and a pygame-free split of `Weather` from its sounds.
- **Crop growth** (`src/models/crop_growth.py`), already a pure function of the date; production in P1 may want to read it even though the roadmap keeps harvests cosmetic.
- **The well's odds and cooldown** (`src/models/institutions/well.py`), still on the global `random`.
- **The merchant rank's daily check and reputation decay** (`src/models/merchant_rank.py`), once prestige (P2) becomes a currency.

## Hooks for P1

- `normal_quantity` and `market_quantity` are separate on purpose. Production adds to `market_quantity`, consumption takes from it, and `normal_quantity` becomes days of demand held. A demand system on the `day` tick replaces `recover_volume` in `_market_tick`.
- `PopulationState` per class is where a purse and a needs basket go. `update_happiness` becomes "how well were the needs met", in place of the random drift.
- `RecipeDef` is loaded and checked already, so workshops only need state, a `systems/production.py` and a subscription.
- Prices are meant to move per day rather than per price tick in P1. That is a change of the subscription in `_subscribe_systems()` and of the goldens, nothing else.
