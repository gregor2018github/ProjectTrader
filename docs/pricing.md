# Pricing: How Goods Are Priced

An orientation page for anyone (human or coding agent) about to touch market prices. It explains the model at a high level, then points to where each piece lives in the code. Line numbers drift, so search for the named function or constant rather than trusting them.

The market is part of the headless simulation core (`src/sim/`, see `sim_core.md`). Its state is `GoodState` (`src/sim/state.py`), and its rules are functions in `src/sim/systems/market.py`. The game's `Good` (`src/models/good.py`) is only a view of them. The design behind it is `p1_living_market.md` (P1, the living market). Its phases P1.1 to P1.3 are built: demand from the town's households, supply from the town's workshops in chains of 30 goods, and the outside world's merchants between them.

---

## The model in one paragraph

Every tradeable good has **one price**, the same at every market booth:

```
price = reference × volume_factor(stock / target_stock) × noise
reference = outside price × a running well wish's shock
outside price = mean × season factor × slow walk × news
```

- **The outside price** is what the good costs beyond the town. It moves on three time scales: a **season factor** (firewood dear in winter, corn cheap after the harvest), a **slow walk** around the long-run mean over months, and **news** that moves it at a stroke and fades over a few days. Merchants **import** when the town's price climbs above it plus the transport cost, and **export** when the price falls below it minus the transport cost, within a daily limit. So the local price lives between those two lines.
- **The volume factor** comes from how much the market holds against its **target stock**, which is a number of days of the town's demand. When the stock is short, the price rises; when there is a glut, it falls.
- **The noise** is the day's haggling: a mean-reverting wobble of some per cent that is gone within a day.

The stock changes only through trades:
- the households buy their daily needs in hourly slices;
- the workshops buy their inputs and sell what they make, in the same slices;
- the merchants import and export;
- the player buys and sells.

So **everyone's trades move the price**. The player's are priced unit by unit (**slippage**), plus the market's **fee**, a share of the trade, and profit is measured **FIFO** against what was paid.

**What this is balanced for** (decided after the first playtest of P1, `p1_living_market.md`, "After the first playtest"): a small trader can live off the swings, and a large one cannot grow on them. The noise and the news give a price enough life within a day or a week to pay for a round trip of a small lot; the seasons pay whoever stocks up and waits; and slippage caps it all, since a market holds only days of a small town's demand. `python -m src.sim.trader` measures it (§10).

---

## 1. The goods and their data

Each good is defined in `assets/data/goods.json` and loaded by `src/sim/data.py` (`GoodDef`). The fields and what they mean:

| Field | Meaning |
|---|---|
| `outside_price` | The long-run mean of the outside price |
| `outside_reversion`, `outside_volatility` | The outside price's daily walk: the share of its log deviation undone each day, and the size of its daily step |
| `outside_seasons` | Optional `{season: factor}` on the outside price, blended smoothly between the seasons' middles (`calendar.season_factor`) |
| `transport_cost` | Per unit, between town and outside. It sets how far the import and export lines lie from the reference. |
| `import_limit`, `export_limit` | Units merchants move a day at most |
| `target_stock_days`, `min_target_stock` | The target stock: that many days of demand, but at least that many units |
| `noise_sigma` | The noise's step per price tick |
| `news_chance`, `news_size`, `news_reversion` | News from outside: how often a day it arrives, how far it moves the outside price (a log; 0.2 is about a fifth, up or down), and the share of the move that fades a day. Optional; a good without `news_chance` has none. |

When a town is founded (`Simulation.found_town`), each good's target is set from the households' demand, and the market holds exactly its target. Before the first frame, `Simulation.presimulate()` runs the whole economy for `MARKET_PRESIMULATION_DAYS` (224, two years) days, so the charts open with history and wages, purses and workshops have nearly settled.

## 2. The outside price and the noise

A price moves on four time scales, from the slowest to the fastest. The first three are the outside price's, so the merchants' import and export lines move with them and the town's price follows; the last is the town's own.

- **The seasons.** `outside_seasons` gives a factor per season, blended smoothly between the seasons' middles. Firewood, herbs, candles, charcoal and fish are cheapest in Summer and dearest in Winter (Wood and Herbs by about half, on the town's market), corn, flour, meat and livestock cheapest in Autumn and dearest in Spring. Stocking up and waiting half a year pays: `src.sim.trader`'s hoarder gains 50–70 % on Wood, Herbs and Candles, with no losing year.
- **The slow walk.** `market.step_outside()` runs once a day: `x ← x·(1 − reversion) + volatility·N(0,1)`, drawing from the simulation's one seeded generator. With 0.03 and 0.03 it strays about ±12 % and halves a deviation in about three weeks (most of a game year): the long lines of a chart.
- **The news.** `market.step_news()` runs every price tick. With a chance of `news_chance` a day a piece of news arrives (a ship lost, a fat harvest abroad) and moves the outside price at a stroke by `news_size`, up or down (`NEWS_SIZE_SPREAD` more or less); `news_reversion` of what news has moved fades a day, so a jump is mostly gone in two to five days. A good gets one about every four to seven days, staples fewer and smaller ones (a tenth), fresh food and imported luxuries more and larger (a quarter). Each is reported as an `OutsideNews` event; the game shows nothing for it yet. A price that has just jumped will come back: that is the trade.
- **The noise.** `market.step_noise()` runs every price tick (`PRICE_TICK_MINUTES`, 30): `n ← n·PRICE_NOISE_PERSISTENCE + noise_sigma·N(0,1)`, clamped to ±`PRICE_NOISE_CLAMP`. With a persistence of 0.96 it forgets half of itself in about 8 game hours; a `noise_sigma` of 0.024 lets a price stray about ±9 % within a day (0.015 for the staples, about ±5 %). The merchants ignore it; the households buy less of what it makes dear. The price chart gets a point after it.

`outside price = mean × season factor × exp(slow walk + news)`.

## 3. The volume factor and the target stock

`market.volume_factor(good, quantity=None)` looks at `ratio = quantity / target_stock`:

| Ratio | Factor |
|---|---|
| between `MARKET_VOLUME_SCARCE_RATIO` (0.9) and `MARKET_VOLUME_GLUT_RATIO` (1.1) | 1.0, "normal" |
| below the scarce ratio, "too little" | `(0.9 / ratio) ^ MARKET_VOLUME_ELASTICITY` (0.7) |
| above the glut ratio, "too much" | `(1.1 / ratio) ^ 0.7` |
| always clamped to | `MARKET_VOLUME_FACTOR_MIN` (0.4) … `MARKET_VOLUME_FACTOR_MAX` (3.0) |

Some values: half the target gives ×1.5, a quarter gives ×2.45, double the target gives ×0.66. `market.ratio_for_factor()` is its inverse, which the merchants use.

**The target stock** follows demand. Each day the households' wanted units (their full baskets) feed a smoothed demand average (`TARGET_STOCK_GLIDE`), and the target is `max(min_target_stock, target_stock_days × average)`. A growing town needs more stock to feel normal. Seasonal demand (firewood in winter) moves it with the seasons.

## 4. Who trades, and at what price

The market place holds no money: the stock in it belongs to the **merchants**. Every buyer pays them and every seller is paid by them, at the price of the moment. They pay the outside price and the transport for what they bring in, and get the outside price less the transport for what they take out. The town's money therefore changes by exactly what crosses its border, which the books check every day (`market_balance`, `sim_core.md`).

- **Households** (`systems/households.py`) plan their day at midnight, tier by tier. Above a good's outside price they buy less of it, `basket × (price / outside price) ^ −elasticity` (the elasticity per tier and class in `needs.json`), and the money saved stays for the next tier. So a scarce good's price stops climbing where the town gives up part of its want. They buy in hourly slices from `MARKET_OPEN_HOUR` to `MARKET_CLOSE_HOUR` (12 slices). In each slice every class's order for a good is added up and cleared once (`market.clear_buyers`): one price for all, the order's average with slippage. When the stock runs short, each class gets the same share. A slice that came up short is made up in later slices if stock comes back. Households pay the merchants.
- **Workshops** (`systems/production.py`) buy their inputs in the same clearing as the households: one price, the same share when short. They run their share of the day's batches, as far as their inputs allow, and sell the outputs to the merchants in one order per good at one price, with slippage. Byproducts are sold the same way. How many batches a workshop runs follows its margin at the day's prices. Local supply therefore undercuts imports while it pays, pushes the price down towards the export line when there is too much of it, and shrinks when it stops paying.
- **Merchants** (`market.merchants`) act last in every slice. They judge by the stock, not the noise: when `reference × volume_factor` is above the **import line** (`reference + transport_cost`), they bring in enough to get back to it, at most `import_limit / 12` in the slice, paying the outside price and the transport. Below the **export line** (`reference − transport_cost`), they take the surplus out the same way, for the outside price less the transport. Between the lines nobody moves.
- **The player** trades through `Depot.buy()` / `Depot.sell()` (`src/models/depot.py`). The amount comes from `Good.quote(quantity, buying)` (`market.quote()`), and the trade itself from `Simulation.trade_with_player()`:
  - **Slippage.** Each unit is priced at its own stock. A unit you buy is priced at the stock before it is taken, so the first one costs the shown price. A unit you sell is priced at the stock after it is added. So buying and then selling back the same units is zero-sum before fees, and a large order moves the price against the trader as it goes.
  - **The fee.** `Depot.trading_fee(amount)` is `fee_rate` of what the goods come to (`MARKET_FEE_RATE`, 1 %; stored on the depot and in the save, so a council can set it later). **Buy:** pays `quote + fee`. **Sell:** receives `quote − fee`. A small lot pays little, a large one much. (Until the first playtest it was a flat 2 per trade, which ate a small lot's whole gain; saves from then get today's rate.)
  - The **unit price recorded** (purchase history, ledger, trade cycles, log) is the order's average, `quote / quantity`.
  - After the trade the stock has changed and the **latest chart point** is overwritten with the new price, so the chart reacts at once.
  - The player's trades fall between the slices, so a slice after a purchase sees the stock the player left. **Buying up the bread at ten leaves the poor short at eleven**, unless merchants can bring more in.
  - `QuickTradeMenu` shows the current price per unit and, on hover, the slipped total.

Before a player's trade, several gates must pass. They block the trade but don't change the price:
1. `GameState.is_good_sold_here()`: does the market square the player stands in have a booth for this good?
2. `GameState.is_good_tradable()`: is one of those booths open right now? (Booths close when their trader goes home; see CLAUDE.md, Map System.)
3. `Depot.has_license()`: the player needs a valid licence for the good, which is its guild's (a good's `license` in `goods.json`; Flour and Bread go under Wheat, Tools under Iron). One licence covers its whole chain, and its fee per season is the head good's `license_fee`.
4. A positive quantity, the market's stock (whole units, `Good.market_quantity`), money, and storage capacity.

**Profit accounting.** Each buy is pushed onto `purchase_history[good]` with its unit price. A sell consumes those entries oldest-first (FIFO), and each consumed chunk is recorded by `_record_trade_cycle()` as a trade cycle. `Depot.avg_buy_price()` gives the FIFO-weighted average cost of what is still held.

**Wealth.** `Depot.update_wealth()` and the depot views value stock at the current price, not at what selling it all would fetch after slippage.

## 5. What does *not* affect price (yet)

- **Which market or booth.** There is one `GoodState` per good, shared by all booths. Booths only decide *whether* you may trade: a booth carries the goods its name gives plus those whose `sold_at` names it.

## 6. Well wishes: the deliberate price shock

Throwing a coin in the well (`Well`, `src/models/institutions/well.py`) has a `WELL_WISH_PROBABILITY` chance, when the well is not on cooldown, of opening a `WishMenu`. There the player picks a good and a direction (`"Price goes up"` / `"Price goes down"`). `Good.apply_well_shock()` (`market.apply_well_shock()`) then multiplies the good's **outside price** by `1 ± WELL_WISH_SHOCK_FACTOR` (40 %) for `WELL_WISH_DURATION_DAYS` days:

- The import and export lines move with it. Merchants follow the new level instead of undoing it, and the local price settles there as the stock adjusts.
- A second wish while one runs multiplies in and restarts the count.
- When the count runs out (`market.tick_well_shock_day()`, on the day tick), the reference is the outside price again, and a `PriceShockEnded` event is reported.

## 7. Price history (charts and bookkeeping)

| List | Appended by | When | Used by |
|---|---|---|---|
| `price_history_ticks` (`Good.price_history_hourly`) | `market.record_tick()` | every price tick, right after the noise step (its last entry is also overwritten after each player trade) | market chart (`chart_view.py`) |
| `price_history_daily` | `market.record_day()` | every day | depot detail / bookkeeping (`depot_view_detail.py`) |

Both lists store the full price. They grow for the whole session and are saved in full. Each good also counts its day's flows (`GoodState.today` / `yesterday`: wanted, bought, imported, exported, player_bought, player_sold), which the headless runner writes out.

## 8. Saving and loading

The save's `"sim"` block (`Simulation.to_dict()`, see `sim_core.md`) holds every `GoodState` in full (stock, target, outside price with its walk and news, noise, shock, histories, flows), the town's books and the merchants' book, the workshops and owners, and the random generator's state. The save's `"goods"` keeps only chart visibility and colour.

Older blocks and saves migrate on loading:
- **`sim_version` 1 (P0) and saves from before the `"sim"` block** (`SAVE_VERSION` < 3, through `save_manager._legacy_sim_block()`): each good keeps its histories, and its stock as a share of its new target (as scarce or glutted as it was against P0's normal volume, or at its target if the save had none). The outside price starts at its mean, so prices jump to the new model on the first load.
- **Goods the save lacks** get a flat history as long as the saved goods'.

## 9. Where this is heading

- **The fee** becomes a market toll the council sets (P6); it is already a rate on the depot.
- **News you can hear.** The sim reports every piece of news (`OutsideNews`), but the player only sees the price jump. A town crier, rumours and couriers are P9's (earned information): knowing *why* a price jumped, and that it will come back, is worth money.
- **The player as a maker.** Trading is capped by the market's depth (§10). P3 lets the player own workshops: a made good is sold into the same market, with the same slippage, but its cost is the inputs' and the wages', not a price to buy low at. The seasons then matter twice: a maker stocks his inputs when they are cheap.
- **Hysteresis.** A workshop's capacity already grows slowly after busy spells and shrinks more slowly after losses (`production.change_capacity`). That makes flooding a market to drive out its makers a strategy once the player can own workshops (P3).
- **Other towns.** P7 replaces the outside price's walk with the other towns' own markets, linked by the same import and export rules.

---

## 10. How much trading pays, and where it stops

`python -m src.sim.trader` lets a headless trader with no foresight play new games by the player's rules (money, slots of `SLOT_SIZE`, the fee, slippage, booth hours): it buys what is some per cent under its mean of the last days and sells for a few per cent more than it paid. Its gain a day, with the best of eight such rules (4 seeds, 56 days, the cost of living not counted):

| Trader | Before (flat fee 2, calm prices) | Now |
|---|---:|---:|
| A new game: 100g, 5 slots, Wood and Stone | 0.1 g | 4.2 g (4 % of its money a day) |
| 300g, 5 slots, 4 goods | 0.4 g | 5.0 g |
| 1,000g, 10 slots, 8 goods | −0.1 g | 12.6 g |
| 5,000g, 40 slots, 16 goods | 0.6 g | 103 g (2 %) |
| 30,000g, 150 slots, 16 goods | 7.9 g | 105 g (0.35 %) |

- **A small trader earns from the first day**, more than the cost of living (`INITIAL_DAILY_COST_OF_LIVING`, 2), and a player who reads the chart does better than the rule.
- **Storage holds the middle back.** Between 300g and 1,000g the trader has more money than its slots of cheap goods can hold: the step is a warehouse and dearer goods.
- **It stops at about 100 g a day** on 16 goods (more with every licence, but the whole market's stock is worth only about 50,000g): an order of more than a tenth of a good's stock moves its price by the whole swing, so six times the money earns nothing more. From there the money has to come from making goods (P3) and from other towns (P7).

When you change the noise, the news, the fee, the volume curve or the target stocks, run it again, with `python -m src.sim.sweep` for the town's side.

## File map

| What | Where |
|---|---|
| Price state (stock, target, outside price with its walk and news, noise, shock, histories, flows) | `src/sim/state.py` (`GoodState`) |
| The price, volume factor, quote/slippage, outside walk, news, noise, merchants, clearing, well shock | `src/sim/systems/market.py` |
| What the households buy and when | `src/sim/systems/households.py` |
| What the workshops make, buy and sell | `src/sim/systems/production.py`; recipes and building types in `assets/data/recipes.json`, `buildings.json`; the home town's workshops in `assets/data/scenarios/home_town.json` |
| The order things happen in, player trades | `src/sim/simulation.py` (`Simulation`) |
| The view the depot and UI use (plus colours, chart visibility) | `src/models/good.py` (`Good`) |
| Every good's outside price and its seasons, transport, limits, target days, noise, news | `assets/data/goods.json`, loaded by `src/sim/data.py` |
| What each class wants, by tier | `assets/data/needs.json` |
| Global market constants (`MARKET_VOLUME_*`, `MARKET_OPEN_HOUR`, `PRICE_NOISE_*`, `NEWS_SIZE_SPREAD`, `TARGET_STOCK_GLIDE`, `WELL_WISH_*`, `MARKET_FEE_RATE`) | `src/config/constants.py` |
| Decades of prices without the game | `python -m src.sim.run` (`sim_core.md`) |
| What a trader earns, by the size of his purse | `python -m src.sim.trader` (`src/sim/trader.py`) |
| Buying, selling, fees, FIFO profit, wealth, licenses | `src/models/depot.py` (`Depot`) |
| Can this good be traded here / now? | `src/game_state.py`, `is_good_sold_here()`, `is_good_tradable()` |
| Booth opening hours | `src/models/institutions/market.py`, `src/models/figurines/humans/npcs/trader.py` |
| Well wish trigger and menu | `src/models/institutions/well.py` |
| Trade input (click / keyboard / quick-trade popup) | `src/handlers/mouse_handler.py`, `src/handlers/keyboard_handler.py`, `src/ui/helper_modules/quick_trade_menu.py` |
| Price chart (also shows the market's stock as `V.`) | `src/ui/layout_modules/chart_view.py` |
| Depot views (stock value, avg buy price, history) | `src/ui/layout_modules/depot_view.py`, `depot_view_detail.py`, `src/ui/general_layout/layout.py` |
| Save / load of prices | `Simulation.to_dict()` / `load()`; older saves in `src/persistence/save_manager.py` (`_legacy_sim_block`) |

Building prices (warehouses' `Buy_price` from Tiled) are a separate fixed number and have nothing to do with this system. See `src/models/institutions/warehouse.py`.
