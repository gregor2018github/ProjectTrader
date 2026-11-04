# P1 · The living market: design

Status: **approved**, with the decisions below. Phases 1 and 2 are built together on the branch `p1-living-market` and merged together; phase 1 alone (imports only) is a development state, not a playable one.

Progress: **phases 1 and 2 built** (demand, the outside world and production, on today's 15 goods; see "Built: what changed on the way" at the end); phase 3 (the new goods) next. Roadmap project P1 (`roadmap.md`), built on the sim core (`sim_core.md`). It replaces the placeholder economy described in `pricing.md` §2, §3 and §9.

## Goal in one paragraph

The town's people eat, drink, dress and heat their homes. They buy all of it from the one market, with money earned from work, and the town's workshops make it from what other workshops make. When something is short the price climbs, and merchants bring it in from outside. When there is too much it falls, and the surplus is shipped out. How well each class gets what it needs sets its happiness, and happiness sets who moves in or out. The player trades in the same market: buying up the bread at ten in the morning leaves the poor without it at eleven.

## What stays, what goes

| Today (P0) | P1 |
|---|---|
| `price = walk_price × volume_factor(market_quantity / normal_quantity)` | `price = reference × volume_factor(stock / target_stock) × noise`, where `reference` is the good's outside price (times a well wish's shock). The volume factor and its constants stay as they are. |
| `walk_price`: a ±10 %-per-tick random walk inside a random corridor | A small mean-reverting noise (a few per cent). The corridor goes away. |
| `normal_quantity`: the starting stock | `target_stock`: `TARGET_STOCK_DAYS` (per good) of the town's daily demand, recomputed daily |
| `recover_volume()`: stock drifts back to normal | Removed. Stock changes only through trades: households, workshops, the outside world, the player. |
| Happiness: a random drift towards 70 | Moves towards a target set by need fulfilment, plus the existing crowding effect. No randomness. |
| Migration on average happiness | Unchanged (threshold 70, at most ±1 %/day, clamps per class) |
| Well wish: walk and corridor ×1.4 / ×0.6 for 5 days | The good's outside price ×1.4 / ×0.6 for 5 days, so the import and export lines move with it (open question 5) |
| A fixed starting price | The outside price follows a slow mean-reverting walk of its own (see "The outside world") |
| Player trades with slippage (`quote`) | Unchanged |

## Data

Everything with a balancing meaning lives in data files, each loaded and checked by `src/sim/data.py` with the same file / entry / field error messages as now.

| File | Holds |
|---|---|
| `assets/data/goods.json` | Per good, besides today's fields: `outside_price` (the long-run mean of the outside price), `outside_reversion` (share of its log deviation undone a day), `outside_volatility` (its daily log step), optional `outside_seasons` (`{season: factor}`), `transport_cost` (per unit), `import_limit` and `export_limit` (units a day; 0 means none), `target_stock_days`, `noise_sigma`, and `sold_at` (which booths carry it, see open question 11). `start_price` and `start_quantity` go: the price starts at `outside_price`, the stock at its target. |
| `assets/data/needs.json` | Per class: `base_income` (per head per day), `labour_share` (how many heads can take a job), and three tiers, `basic`, `comfort`, `luxury`, each listing `{good: units per head per day}`. Also the happiness weights per tier. |
| `assets/data/recipes.json` | As now, plus `building` (the building type that runs it). Amounts may be fractions (a tool wears out by 0.05 a batch). Several outputs make byproducts. |
| `assets/data/buildings.json` | Building types: `recipe`, `workers_class`, `wage` (per worker-day), `capacity` (batches a day at the start), `max_capacity`, `growth_cost` (money per batch of capacity), `working_capital` (cash kept before profits go to the owner) |
| `assets/data/scenarios/home_town.json` | Which workshops stand in the home town, their owner (`"town"`), capacity and starting cash. Other scenarios (a test town, P7's towns) are other files. |
| `src/config/constants.py` | Rules that are not per good or per class: market hours, happiness glide, savings cap, hysteresis rates, health thresholds. Each one has a comment. |

## The model

### Owners

```python
@dataclass
class Owner:
    id: str            # "town"; later "player", "dynasty:<name>"
    kind: str          # "town" | "player" | "dynasty"
    name: str
    cash: float
```

`SimState.owners` holds them. Every workshop names its `owner_id`. Nothing in the systems reads `kind`: the town's workshops run on the same functions a player's or a rival's will (pillar 1). The only owner in P1 is the town. Its cash is the town's treasury, which P6 will spend. The player's money stays in the `Depot` for now. P3 decides whether `Depot.money` becomes the player's `Owner.cash` (I recommend it does).

### Households (one per class)

`ClassState` gains `purse`, `employed`, and per tier yesterday's `fulfilment`.

- **Income, daily.** Unemployed heads earn `base_income` (all the work that is not simulated). Employed heads earn their workshop's `wage` instead, paid by the workshop (open question 7). Heads available for work: `labour_share × count`.
- **Budget, daily.** The day's income plus, when needs went unmet yesterday, up to `SAVINGS_RELEASE` of the savings.
- **Spending, in tier order.** The basic tier's goods are bought for all heads if the budget allows. If not, every good of the tier is bought at the same fraction. The rest of the budget goes to comfort, then to luxury.
- **Fulfilment per tier (0..1)** is what was actually received, weighted by value: units bought ÷ units wanted, averaged over the tier's goods with today's prices as weights. Two things lower it: an empty purse, and a market that had nothing left.
- **Savings cap.** Money left over is saved up to `SAVINGS_CAP_DAYS` of income. Anything above that leaves the town ("rents and dues paid outside"). This keeps the money supply bounded, and the health report tracks how much leaves.

### Workshops

```python
@dataclass
class WorkshopState:
    id: str
    owner_id: str
    building: str           # key into buildings.json, which names the recipe
    capacity: float         # batches a day it could run
    utilisation: float      # 0..1, the share of capacity it runs at
    cash: float
    input_stock: Dict[str, float]
    output_stock: Dict[str, float]
    workers: int
    unprofitable_days: int  # hysteresis counters
    busy_days: int
```

- **Planning (daily).** The margin of one batch at today's prices is `(outputs × price − inputs × price − labour × wage) / costs`, counting byproducts as revenue. `utilisation` glides towards `clamp((margin − MARGIN_FLOOR) / (MARGIN_FULL − MARGIN_FLOOR), 0, 1)` at `UTILISATION_GLIDE` a day. The day's batches are `capacity × utilisation`, limited by the workers available, by cash for inputs and wages, and by inputs on the market.
- **Running (hourly, in market hours).** Each hour runs its share of the day's batches: it buys inputs from the market, makes outputs, and sells them into the market. Wages are paid at the end of the day, out of the workshop's cash, into the workers' class purse.
- **Capacity, with hysteresis** (`pricing.md` §9):
  - **Growth:** after `GROWTH_AFTER_DAYS` busy days (utilisation ≥ 0.9) and with enough cash, capacity grows by `GROWTH_STEP`, paid in money to the outside. P3 makes this materials.
  - **Shrinking:** after `SHRINK_AFTER_DAYS` unprofitable days, capacity shrinks by `SHRINK_STEP`, slower than growth, down to 0. The building stays, so the workshop can come back. A trade beaten down to nothing therefore takes long to return.
- **Profits.** Cash above `working_capital` goes to the owner each day. A workshop short of cash runs less. It never borrows in P1.
- **Workers** come from the class in `workers_class` (Poor or Commons), as far as that class has heads free for work. They are filled in workshop id order, so the result is deterministic.

### The market

There is one stock pool per good (`GoodState.stock`, a float, see open question 2). The pool is not an owner. It is the town's market place, where everyone trades at the posted price:

- **Households and workshops** trade in hourly slices during `MARKET_HOURS` (06:00–18:00, so 12 slices). In each slice, every buyer's and seller's order for a good is added up. The *net* order is executed once, and everyone in the slice pays or receives that net order's average price (`quote` of the net quantity ÷ quantity). When the stock cannot meet the buys, every buyer gets the same fraction (pro rata, see open question 3).
- **The player** trades whenever a booth is open, unit by unit with slippage, exactly as today. The player's orders are not batched.
- **Price.** `reference` is the good's current outside price (below) times a running well wish's shock; noise is a mean-reverting factor stepped every price tick (`n ← n·ρ + N(0, σ)`, `noise = exp(n)`, clamped to ±`NOISE_CLAMP`), drawn from the sim's generator. The chart keeps a point per price tick. Within a day, prices now move through the slices' trades and the player's.
- **Target stock.** `target_stock = target_stock_days × daily demand`, where daily demand is households' wanted units plus workshops' planned inputs, recomputed daily. It is smoothed (`TARGET_GLIDE`), so a lean day does not swing it.

### The outside world

**The outside price moves.** Each good's outside price follows a slow mean-reverting walk in logs, stepped on the day tick from the sim's generator:

```
x ← x · (1 − outside_reversion) + outside_volatility · N(0, 1)
outside price = outside_price (the mean) × season factor × exp(x)
```

With a reversion of 0.03 and a volatility of 0.03 a day, it strays about ±12 % and halves a deviation in about three weeks: trends a player can read over weeks to months. The optional `outside_seasons` factors work like the needs' (open question 10): one factor per season, blended smoothly between the seasons' middles, so a season's turn shows no jump. The runner's CSVs record the outside price. P7 replaces this walk with the other towns' own markets.

**A well wish shocks the outside price.** For the wish's `WELL_WISH_DURATION_DAYS`, the good's reference is its outside price × (1 ± `WELL_WISH_SHOCK_FACTOR`). The import and export lines move with it, so merchants follow the new level instead of undoing it, and the local price settles there as stock adjusts. A second wish while one runs multiplies in and restarts the count. When it ends, the reference is the outside price again.

Merchants act in every slice, after the households and workshops:

- **Import** when the price is above `outside_price + transport_cost`: enough to bring the price back to that line, at most the slice's share of `import_limit`. They are paid `outside_price + transport_cost` per unit, and that money leaves the town.
- **Export** when the price is below `outside_price − transport_cost`, the same way in reverse, at `outside_price − transport_cost`. That money enters the town.
- **Effect.** The local price is held between the import and export lines, except when a daily limit binds. Since the volume factor is 1.0 between 90 % and 110 % of the target, a good with a 15 % transport cost floats between about 74 % and 139 % of its target stock.
- **Import-only goods** (Spices, Wine, Iron; see open question 13) have no recipe and `export_limit` 0. An `import_limit` of 0 makes a good local-only.
- P7 replaces "outside" with the other towns, each running this same sim on a weekly tick, linked by these same import and export rules.

### Money

**The market place holds no money, by construction.** The stock in it belongs to the merchants. Buyers (households, workshops, the player) pay the merchants, and sellers (workshops, the player) are paid by them, at the posted price. The merchants pay the outside price and the transport for what they import, and get the outside price less the transport for what they export. Transport is borne by the merchants out of the margin between the lines, and by buyers through the price, never by the pool.

The town's money (purses, workshops' and owners' cash; the player's stays in the game's `Depot`) therefore changes each day by exactly what crosses its border: base income created, minus the savings leak, minus money paid to builders for growth, minus payments to the merchants, plus payments from them (`TownMoney`). The `market_balance` is whatever those flows don't explain, and the health report fails unless it is zero within float tolerance. The merchants' own book (sales, purchases, import cost, export revenue, transport) is recorded for analysis. It lies outside the town.

### Happiness and migration

- **Target, per class.** `target = 100 × (w_basic·f_basic + w_comfort·f_comfort + w_luxury·f_luxury)`, using yesterday's fulfilment and per-class weights from `needs.json`. For example, the Poor weigh 0.75 / 0.20 / 0.05 and the Nobility 0.30 / 0.40 / 0.30, so nobles without luxuries are unhappy and the poor are content with bread and beer.
  - **Hunger:** a basic fulfilment below `HUNGER_THRESHOLD` (0.6) takes `HUNGER_PENALTY` more points.
  - **Crowding:** the bonuses and penalties work as today, shifting the target.
- **Glide.** Each hour, happiness moves `HAPPINESS_GLIDE` (0.05, today's reversion) of the way towards the target.
- **Calibration.** Full basic and comfort with half the luxury should land at about 75 for every class, a little above the migration threshold of 70, so a well-supplied town grows slowly.
- **Migration** is unchanged.

## Goods (15 → 31)

New goods are marked **new**. Raw goods are made by labour-only recipes ("primary" workshops: a farm, a fishery, a quarry). Fields stay cosmetic, as the roadmap decides: a farm's output does not follow the crops on the map.

| Tier | Good | Made by (recipe: in → out) | Notes |
|---|---|---|---|
| raw | Wheat | farm: labour, Tools 0.02 → 10 | |
| raw | **Flax** | farm: labour, Tools 0.02 → 6 | |
| raw | Wool | sheep farm: labour → 4 | |
| raw | **Livestock** | pasture: labour → 2 | the butcher's input |
| raw | Fish | fishery: labour, Tools 0.01 → 8 | |
| raw | Wood | forester: labour, Tools 0.02 → 12 | also firewood (a basic need) |
| raw | **Clay** | clay pit: labour → 10 | |
| raw | Stone | quarry: labour, Tools 0.05 → 6 | no local demand until P3 builds; it exports |
| raw | Salt | salt works: labour → 5 | |
| raw | Herbs | herb garden: labour → 4 | |
| import | Iron | — | no mine near town |
| import | Wine | — | no vineyards |
| import | **Spices** | — | luxury |
| 2 | **Flour** | mill: Wheat 10 → Flour 9 | |
| 2 | **Charcoal** | charcoal burner: Wood 6 → Charcoal 2 | |
| 2 | Hide | (butcher's byproduct) | |
| 2 | **Tallow** | (butcher's byproduct) | |
| 2 | **Leather** | tannery: Hide 2, Salt 0.5 → Leather 2 | |
| 2 | **Cloth** | weaver: Wool 3 → Cloth 2 | |
| 2 | Linen | linen weaver: Flax 3 → Linen 2 | |
| 3 | **Bread** | bakery: Flour 4, Wood 1 → Bread 12 | |
| 3 | Beer | brewery: Wheat 5, Wood 1 → Beer 4 | ale, brewed from wheat |
| 3 | Meat | butcher: Livestock 1 → Meat 4, Hide 1, Tallow 2 | byproducts |
| 3 | **Salted Fish** | salter: Fish 4, Salt 1 → Salted Fish 4 | |
| 3 | **Garments** | tailor: Cloth 2, Linen 1 → Garments 2 | |
| 3 | **Shoes** | cobbler: Leather 1, Tools 0.02 → Shoes 2 | |
| 3 | Candle | chandler: Tallow 2 → Candle 6 | |
| 3 | Pottery | potter: Clay 4, Wood 1 → Pottery 4 | |
| 3 | **Tools** | smith: Iron 2, Charcoal 2, Tools 0.05 → Tools 2 | wears out in other recipes |
| 3 | **Furniture** | joiner: Wood 4, Tools 0.05 → Furniture 1 | |

The recipe amounts are first guesses that set the shape of each chain. Phase 2 calibrates them so that each workshop is profitable at outside prices with some slack.

### Baskets

The units are trade units (a sack, a cask, a bolt), so they are small per head per day. These are first guesses. Phase 1 calibrates them so that at outside prices each class's basic tier costs about 60 % of its income and basic plus comfort about 90 %.

| Class (income/head/day) | Basic | Comfort | Luxury |
|---|---|---|---|
| Poor (0.5 g) | Bread, Beer, Wood | Salted Fish, Garments, Shoes | Meat, Candle |
| Commons (1.0 g) | Bread, Beer, Wood, Salted Fish | Meat, Garments, Shoes, Candle, Pottery | Wine, Linen |
| Middling Sort (2.5 g) | Bread, Beer, Wood, Meat | Fish, Garments, Shoes, Candle, Pottery, Linen, Herbs | Wine, Furniture, Spices |
| Nobility (10 g) | Bread, Meat, Wine, Wood | Fish, Garments, Shoes, Candle, Linen, Furniture, Herbs | Spices, Wine (more), Furniture (more) |

What only workshops use (Wheat, Flour, Flax, Wool, Livestock, Clay, Charcoal, Iron, Hide, Tallow, Leather, Cloth, Tools, Salt) has demand only through them. Stone has none until P3, so its price sits at the export line.

**Phase 1's stand-ins.** Phase 1 runs on today's 15 goods, so the baskets use the nearest good there is: Wheat for Bread, Fish for Salted Fish, Linen for Garments, Hide for Shoes. `needs.json` names goods, so Phase 3 swaps them by editing data only.

Example `needs.json` entry:

```json
{"class": "Poor", "base_income": 0.5, "labour_share": 0.6,
 "happiness_weights": {"basic": 0.75, "comfort": 0.2, "luxury": 0.05},
 "basic":   {"Bread": 0.12, "Beer": 0.02, "Wood": 0.04},
 "comfort": {"Salted Fish": 0.02, "Garments": 0.003, "Shoes": 0.003},
 "luxury":  {"Meat": 0.01, "Candle": 0.01}}
```

## Tick order

Fixed and deterministic: classes in `needs.json` order, goods in `goods.json` order, workshops by id.

| Tick | Systems, in order |
|---|---|
| **day** (00:00) | 1. Workshops pay yesterday's wages; owners take profits above working capital. 2. Purses get base income; the savings leak. 3. Yesterday's fulfilment → happiness target per class. 4. Migration (as today), then `employed` is reassigned. 5. Target stock per good from yesterday's demand. 6. Workshops plan: margin → utilisation → today's batches; capacity hysteresis. 7. Households plan: budget → wanted units per tier. 8. Well-shock countdown; daily records; events. |
| **hour**, inside `MARKET_HOURS` | 1. Workshops run the slice's batches (buy inputs, make outputs, sell). 2. Households buy the slice's share, tier by tier. 3. Each good's net order clears. 4. Merchants import and export. |
| **hour**, every hour | Happiness glides towards its target. |
| **price tick** (30 min) | Noise step; chart point. |
| week, season, year | Nothing yet (see open question 10 for seasonal demand) |

The player's trades fall between ticks, when the game calls `Good.buy` / `Good.sell`. A slice that comes after a player's purchase sees the stock the player left.

## Health metrics (Phase 4)

`python -m src.sim.health runs/<name>` reads a run's CSVs and checks:

| Check | Fails when | Starting threshold |
|---|---|---|
| Price stuck at a clamp | any good's volume factor at `MARKET_VOLUME_FACTOR_MIN` or `_MAX` for more than N consecutive days | N = 14 |
| Price far from outside | any good's price outside [0.5, 2] × `outside_price` for more than N days | N = 28 (warning) |
| Hunger | any class's basic fulfilment below X for more than N consecutive days | X = 0.6, N = 7 |
| Poorly supplied | any class's mean basic fulfilment over the run below X | X = 0.9 (warning) |
| Money supply | total money (purses + workshop cash + owners) over the last 10 years outside [1/3, 3] × its median | — |
| Bad numbers | any NaN, negative stock or negative purse | always |
| Population | total outside [0.5, 1.2] × start, or a trend over the last 10 years above X %/year | X = 2 |
| Happiness | any class's mean outside [50, 90] | warning |
| Workshop cash | any workshop with negative cash for more than N consecutive days | N = 56 (two seasons) |
| Dead workshop | any workshop at utilisation 0 for more than a year | warning |
| Structural shortage | any good importing at its limit on more than X % of days | X = 50 (warning) |
| Market balance | any day's `market_balance` not zero within float tolerance (the market place holds no money) | 1e-9 of the money supply |
| Tradability (warning, no threshold yet) | per good, the median over the run of (30-day max − min price) / price, and the share of days that range on 20 units beats twice a 20-unit round trip (two fees plus slippage both ways) | — |

The report is a short text summary per run, plus a table over the 20 seeds × 50 years. Phase 4's CSVs add daily consumption, production, imports and exports per good, purse and fulfilment per class and tier, and per workshop its cash, utilisation, capacity and output.

**Speed target:** 50 years (1,400 days, 16,800 slices) under 30 s. Clearing nets one order per good per slice (about 30 goods × 12 slices a day) instead of summing units, so the cost does not grow with volume.

## Same rules for everyone

- Workshops know their `owner_id`, never their owner's `kind`. Growth, shrinking, wages and profit-taking are the same functions for any owner.
- The town has no subsidy, no free inputs and no first claim on stock. Its only special trait is that it is the only owner so far.
- Households and the player are not owners but buyers. Rationing is pro rata among all buyers in a slice. The player is the one exception, trading between slices.

## Saving

`sim_version` 2:

- Each good gets `stock` (from `market_quantity`), `target_stock`, `noise`, `shock`, `shock_days`, and daily demand/supply counters. `walk_price`, the corridor and `base_price` go.
- Each class gets `purse`, set from 5 days of income, and fulfilment, set to 1.
- Owners and workshops are seeded from `scenarios/home_town.json`.
- Migration from version 1 fills the missing state from these defaults. Prices jump to the new model on loading (see open question 9).
- The P0 goldens are replaced by a golden per phase. The determinism and no-pygame tests stay.

## Phases (after approval)

1. **Demand and the outside world** (developed together with phase 2 on `p1-living-market`), on today's 15 goods with stand-in baskets: needs, purses, base income, consumption, imports and exports, the new price rule, happiness from fulfilment. `recover_volume` and the drift go. With no production yet, all supply comes from imports, so prices sit at the import line. That is expected, and phase 2 brings local supply below it.
2. **Production:** owners, workshops, recipes with byproducts, wages, employment, margin-driven output, capacity hysteresis, and the home-town scenario.
3. **Goods to 31:** data, chart colours, placeholder icons (`<good>_30.png`), `sold_at` booths, licences under the existing system, placeholder contract texts, and baskets swapped from stand-ins to the real goods.
4. **Runner and health:** the CSVs above, `src.sim.health`, and 20 seeds × 50 years, reported.
5. **Minimal UI:**
   - The town hall's population stats show fulfilment per class and tier.
   - The market view shows daily demand and supply per good.

## Open questions

All decided: the recommendations were accepted as written, except question 5 (changed, see there). Added in review: the outside price moves (see "The outside world").

1. **Daily or hourly trading?** The roadmap says production and consumption run per day. **Recommendation: plan daily, trade in hourly slices during market hours.** That is what makes the player's 10 o'clock purchase leave the poor short at 11, and it keeps prices moving during the day. The cost is 12 netted orders per good a day.
2. **Stock as float or int?** Per-head amounts are fractions. **Recommendation: float internally.** The UI shows whole units, and the player's trades stay whole.
3. **Rationing when stock runs short in a slice.** **Recommendation: pro rata among all buyers.** The alternatives are fixed priority (the poor last, or first) or first come, first served (unfair by id order).
4. **One price per slice for everyone (the net order's average) or slippage for each agent?** **Recommendation: one price per slice.** It is fair, cheap, and order-independent. The player keeps per-unit slippage, because the player trades alone.
5. **Well wish.** **Decided: the shock applies to the good's outside price (the reference) for the wish's duration**, so the import and export lines move with it and merchants do not undo it. `WELL_WISH_SHOCK_FACTOR` stays as it is.
6. **Fixed baskets or substitutes (bread or salted fish as "food")?** **Recommendation: fixed baskets in P1.** Substitution groups would be a later, optional field in `needs.json`.
7. **Employment.** **Recommendation: a job replaces base income with the wage.** Jobs then matter only when the wage beats base income. Adding wages on top of base income would make every job pure money creation.
8. **Where surplus money goes.** **Recommendation: purses above `SAVINGS_CAP_DAYS` leak out.** The town's treasury collects workshop profits, is reported, and is not checked for bounds until P6 spends it.
9. **Old saves.** Prices jump to the new model on the first load. **Recommendation: accept the jump** (dev saves only), log it, and keep the old price history.
10. **Seasonal demand (more firewood and candles in winter).** The roadmap keeps seasons cosmetic for *production* only. **Recommendation: allow an optional per-season factor on a need in `needs.json`, used for Wood and Candle.** It is cheap and visible.
11. **Booths for new goods.** `Market.get_trade_options` parses booth names ("Wine & Beer Market"). **Recommendation: a `sold_at` list per good in `goods.json`** (Bread and Flour at the Wheat Market, Salted Fish at the Fish and Salt markets, ...), which `get_trade_options` also reads. No Tiled work is needed. New booths can come later.
12. **Fractional recipe amounts** (tool wear) change P0's schema, which requires whole units. **Recommendation: allow numbers > 0.**
13. **Import-only goods.** **Recommendation: Iron, Wine and Spices are import-only, and Stone has no local demand until P3.** Iron is the one that matters: the tools chain then depends on trade.
14. **Phase 1 without production** leaves prices at the import line for a phase. **Recommendation: accept it.** The alternative, a temporary "hinterland supply" curve, would be thrown away in phase 2.
15. **Market depth.** At the start, stock equals its target (`target_stock_days` × demand, about 14 days). Wheat would hold about 1,000 units instead of today's 5,000. The player's 100g then visibly moves a staple's price, which is the point of "the player's trades matter". **Recommendation: 14 days for staples and 30 for durables.** Calibrate in phase 1 so that the starting player (100g) moves a staple by about 5 %, not 50 %.
16. **The player's money and P3.** **Recommendation: leave `Depot` as it is in P1**, and turn `Depot.money` into the player's `Owner.cash` when P3 lets the player own a workshop.

## Risks

- **Calibration is the work.** Baskets, incomes, wages, recipe yields and transport costs must line up so that every chain is profitable somewhere between the import and export lines. Phase 4's health report is how that is judged, and the first runs will fail it.
- **Positive feedback.** More people means more demand, which means more workshop profit and more jobs, which means more income, more happiness, and more people. The population clamps (0.4–1.2 × base) and the crowding penalty hold it, so they stay.
- **Charts.** With the walk reduced to noise, the price charts get calmer. Their life now comes from real shortages and gluts, which phase 5 makes visible.

## Built: what changed on the way

Decisions taken while building phases 1 and 2, beyond the ones above.

**Phase 1**
- Merchants judge the market by its stock, not by the noise: they compare `reference × volume_factor` with the lines. Reacting to the noise made them buy on every upward wobble and sell into the next dip, a loss on every swing.
- Saves from P0 keep each good's stock as a share of its new target (as scarce or glutted as it was), not its units. P0's "normal" volumes were thousands, so moving the units loaded every old save as a glut at the price floor.

**Before phase 2 (review changes)**
- Crowding is measured against each class's share of the housing (`ClassState.capacity`), not against the starting head count, so a town at its starting size (80 % full) is not penalised. Migration's min/max clamps still measure against the starting head count (open question below).
- The market place holds no money (see "Money"). The `market_balance` check is exactly zero, and the tradability measure is reported (`python -m src.sim.health`).

**Phase 2**
- **Owners settle with their workshops daily.** An owner tops each workshop's cash up to its working capital out of its own cash, and takes whatever is above it. Without the top-up, a workshop that had spent its cash on growth planned zero batches, never earned again, and stayed dead.
- **Surplus.** Each owner's `surplus_to` (data, in the scenario) decides what it does with its cash:
  - `keep`: it keeps all of it.
  - `townsfolk`: cash above its `reserve` is paid to the classes per head.
  - `treasury_with_tribute` (the town, decided in review): it keeps its profits up to `TREASURY_CAP_DAYS` of its average net income (profits less top-ups, smoothed by `TREASURY_INCOME_GLIDE`), or its reserve if that is more. Anything above leaves town as tribute to the lord, counted in the border flows (`TownMoney.tribute`, `town_daily.csv` `money_tribute`) like the households' savings leak. P6 will spend the treasury.
- **Hiring is pro rata.** When a class has fewer free hands than its workshops want, each gets the same share, as buyers do in a short market. Hiring in id order gave the first farm every poor worker and the forester none.
- **Wages move with the demand for hands** (decided in review). Each class has one wage (`ClassState.wage`), paid by every workshop hiring from it; buildings have no wage of their own any more.
  - Each day the tension, how far the workers wanted overshoot the class's free hands (within ±1), moves the wage `WAGE_GLIDE` × tension of the way towards `wage_cap` (in `needs.json`) when hands are short.
  - It moves the same of the way down towards the class's base income when hands are spare.
  - So it stays between the two. Margins, and so how hard workshops run, follow it.
- **A busy day** needs the workshop to *plan* near its capacity, not just to want it. Otherwise workshops without workers grew to their maximum.
- **No output stock.** A workshop sells what it makes in the same slice. It keeps an input stock (bought, not yet used), so a recipe with several inputs can run when they arrive at different rates.
- **Recipes** have no `days` field any more (capacity is in batches a day), and amounts may be fractions.
- **Scenario** (`assets/data/scenarios/home_town.json`): eleven town-owned workshops on today's 15 goods (farms, forester, herb garden, sheep farm, fishery, cattle farm with hides as a byproduct, salt works, quarry, brewery, pottery). Iron, Wine, Linen and Candle stay imported until phase 3's chains.
- **Calibration.**
  - Wages just above base income: Poor 0.7, Commons 1.15.
  - Base income trimmed, because part of the "unsimulated" work is now simulated: Poor 0.45, Commons 0.9, Nobility 11.
  - Larger luxury tiers. Some of the nobility's wine moved from basic to luxury.

**Migration's floor and ceiling** (decided in review) measure against each class's share of the housing too: 0.3–1.05 × housing. Crowding and needs, not the clamp, now set the town's size: it settles at about 100 % of its housing (597–601 of 599 places, 10 seeds × 50 years).

**Calibration target** (decided in review): without the player, the town should run slightly short. The health report warns unless each class's mean comfort fulfilment lies in 0.80–0.95 and its luxury fulfilment in 0.30–0.70, and at least 3 goods run out of stock on more than 5 % of days.

**Price-sensitive demand** (decided in review, built; open question 17):
- **The rule.** Above a good's outside price, a class buys `basket × (price / outside price) ^ −elasticity` of it, and never more than its basket when the good is cheap. The elasticity is per tier and class in `needs.json` (basic 0.1, comfort 0.5, luxury 1.2; the poor's comfort 0.8), with an optional per-good override.
- **Spending.** Money not spent because a class bought less stays in the day's budget for the next tier.
- **Fulfilment** still counts against the whole basket, so dearness lowers happiness.

**Calibration result, with price-sensitive demand** (10 seeds × 50 years):
- **Bands:** every class lies inside both. Comfort is 0.93–0.94 and luxury 0.36–0.67 (Poor 0.66, Commons 0.42, Middling Sort 0.34–0.36, Nobility 0.67); basic is 0.98–0.99, never below 0.95 on any day.
- **What did it:** price-sensitive demand, the poor's comfort elasticity of 0.8, and import limits near the average imports for wood (30 a day), wine (24), linen (18) and candles (14). Their winter peaks now raise their prices, and the town buys less.
- **Stock-outs: none.** In a market that rations by price, a good runs out only when its stock falls below one slice's orders, and the rising price stops that from happening. Wood falls to 4 % of its target at 3× its outside price and still does not run out. Tightening supply further (shorter target stocks, imports of wood, fish, beer and meat capped at their average) only added days at the price ceiling (runs of up to 10 days, 330–400 days per run beyond 2× the outside price) and still no stock-outs, so it was reverted. Open question 18.

## Open questions after phase 2

17. **Price-sensitive demand.** Decided and built (see "Price-sensitive demand" above).
18. **What "running short" means in a market that rations by price.** Stock-outs (households wanting more than the market has) practically never happen, because the price rises first. **Recommendation:** count the days households got less than their basket of a good for any reason, dearness or a stock-out (`bought < wanted`), and aim at least 3 goods at more than 5 % of days. That counts every day the town did without, whether the price or an empty market caused it.
