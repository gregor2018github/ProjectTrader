# Pricing: How Goods Are Priced

An orientation page for anyone (human or coding agent) about to touch market prices. It explains the model at a high level, then points to where each piece lives in the code. Line numbers drift, so search for the named function or constant rather than trusting them.

---

## The model in one paragraph

Every tradeable good has **one global price**, the same at every market booth. That price is two factors multiplied:

```
price = walk_price × volume_factor(market_quantity)
```

- **`walk_price`** is a random walk. Once per in-game hour it takes a random multiplicative step. It is held loosely inside a randomly rolled **corridor** (`lower_bound` … `upper_bound`): inside, the walk is free and volatile; outside, it is calm and drifts back.
- **`volume_factor`** comes from how much of the good the market holds, compared with what it considers **normal**. When the good is scarce it costs more; when the market is glutted it costs less.

Trades change the volume, so **player trades move the price**. A big order is priced unit by unit as the volume moves, which is called **slippage**. Until the town has real supply and demand, the volume drifts slowly back toward normal. A **well wish** shifts the walk. The player also pays a flat **transaction fee** per trade, and profit is measured **FIFO** against what was paid.

---

## 1. Starting prices and volumes

Each good is created with a hand-set starting price and market quantity in `Game._create_goods()` (`src/game.py`), e.g. Wood 1 / 5000, Wine 10 / 500.

At creation (`Good.__init__`, `src/models/good.py`):

| Field | Value | Meaning |
|---|---|---|
| `walk_price` | starting price | Random-walk part of the price |
| `market_quantity` | starting quantity | Units the market holds now |
| `normal_quantity` | starting quantity | The volume the market thinks is normal |
| `base_price` | starting price | Kept only to re-simulate history (see §8) |
| `upper_bound` | `walk_price × U(1.5, 3.5)` | Above this, the walk drifts down |
| `lower_bound` | `walk_price × U(0.05, 0.80)` | Below this, the walk drifts up |

`price` is a **property**: reading it computes `walk_price × volume_factor()`. Setting it changes `walk_price` so that the price shown at the current volume becomes the given value.

Before the first frame, `Game._presimulate_market_history()` runs the hourly update forward for `MARKET_PRESIMULATION_DAYS` (60) days. The charts therefore open with history, and the game starts at an already-drifted price, not the hand-set one.

## 2. The hourly random walk

`Good.update_price()` is called once per in-game hour from the main loop in `Game.run()` (`if hour_changed:`). It sets `walk_price = walk_price × random.normalvariate(mu, sigma)`:

| Situation | `mu` | `sigma` | Effect |
|---|---|---|---|
| Inside the corridor | 1.00 | 0.10 | Free random walk, about ±10 % per hour |
| Above `upper_bound` | 0.999 | 0.01 | Slow, calm decline |
| Below `lower_bound` | 1.02 | 0.01 | Calm recovery of about 2 % per hour |
| Walk < 1 (on top of the above) | +0.03 | – | Extra push up so cheap goods don't collapse toward 0 |

The bounds are **soft**: one in-corridor step can jump well past a bound, and the drift back is gradual. The corridor bounds only the walk, never the volume factor, so a price raised by scarcity is not pulled back by the corridor.

The speed level (`time_level`) only changes how fast in-game hours pass. It does not change the formula.

## 3. The volume factor

`Good.volume_factor(quantity=None)` looks at `ratio = quantity / normal_quantity`:

| Ratio | Factor |
|---|---|
| between `MARKET_VOLUME_SCARCE_RATIO` (0.9) and `MARKET_VOLUME_GLUT_RATIO` (1.1) | 1.0, "normal" |
| below the scarce ratio, "too little" | `(0.9 / ratio) ^ MARKET_VOLUME_ELASTICITY` (0.7) |
| above the glut ratio, "too much" | `(1.1 / ratio) ^ 0.7` |
| always clamped to | `MARKET_VOLUME_FACTOR_MIN` (0.4) … `MARKET_VOLUME_FACTOR_MAX` (3.0) |

The curve is continuous at the thresholds and grows steeper the further the volume strays. Some values: half the normal volume gives ×1.5, a quarter gives ×2.45, double the normal volume gives ×0.66, and four times gives ×0.40.

All the numbers are in `src/config/constants.py` under "MARKET VOLUME".

**Placeholder recovery.** Every hour, before the walk step, `Good.recover_volume()` closes part of the gap to `normal_quantity`: `MARKET_VOLUME_DAILY_RECOVERY` (10 %) per day, and at least one unit per hour while any gap remains. This stands in for traders restocking and townsfolk buying. It is meant to be replaced by real supply and demand (see §9).

## 4. What a trade costs

Trading goes through `Depot.buy()` / `Depot.sell()` (`src/models/depot.py`). The amount comes from `Good.quote(quantity, buying)`:

- **Slippage.** Each unit is priced at its own volume. A unit you buy is priced at the volume before it is taken, so the first one costs the shown price. A unit you sell is priced at the volume after it is added. As a result, buying and then selling back the same units is zero-sum before fees, and a large order moves the price against the trader as it goes.
- **Buy:** pays `quote + transaction_cost`. **Sell:** receives `quote − transaction_cost`. `transaction_cost` is a flat fee per trade (starts at `INITIAL_TRANSACTION_COST` = 2), stored on the depot and in the save.
- The **unit price recorded** (purchase history, ledger, trade cycles, log) is the order's average, `quote / quantity`.
- After the trade, `Good.buy()` / `sell()` change `market_quantity` and overwrite the **latest chart point** with the new price, so the chart reacts at once instead of waiting for the next hour.
- `QuickTradeMenu` shows the current price per unit and, on hover, the slipped total.

Before a trade, several gates must pass. They block the trade but don't change the price:
1. `GameState.is_good_sold_here()`: does the market square the player stands in have a booth for this good?
2. `GameState.is_good_tradable()`: is one of those booths open right now? (Booths close when their trader goes home; see CLAUDE.md, Map System.)
3. `Depot.has_license()`: the player needs a valid trading license per good.
4. A positive quantity, the market's stock, money, and storage capacity.

**Profit accounting.** Each buy is pushed onto `purchase_history[good]` with its unit price. A sell consumes those entries oldest-first (FIFO), and each consumed chunk is recorded by `_record_trade_cycle()` as a trade cycle. `Depot.avg_buy_price()` gives the FIFO-weighted average cost of what is still held.

**Wealth.** `Depot.update_wealth()` and the depot views value stock at the current price, not at what selling it all would fetch after slippage.

## 5. What does *not* affect price (yet)

- **Which market or booth.** There is one `Good` object per good, shared by all booths. Booths only decide *whether* you may trade.
- **Population, happiness, production, season, time of day.** Nothing reads these for the price yet; see §9.

## 6. Well wishes: the deliberate price shock

Throwing a coin in the well (`Well`, `src/models/institutions/well.py`) has a `WELL_WISH_PROBABILITY` chance, when the well is not on cooldown, of opening a `WishMenu`. In that menu the player picks a good and a direction (the strings `"Price goes up"` / `"Price goes down"`). `Good.apply_well_shock()` then:

- multiplies `walk_price` **and both bounds** by `1 ± WELL_WISH_SHOCK_FACTOR` (40 %), so the corridor moves with the walk and the price settles at the new level;
- after `WELL_WISH_DURATION_DAYS` daily ticks (`Good.tick_well_shock_day()`, from the daily block in `Game.run()`), restores the original bounds. The walk then drifts back by the normal corridor rules.

## 7. Price history (charts and bookkeeping)

| List | Appended by | When | Used by |
|---|---|---|---|
| `price_history_hourly` | `update_price_history_chart()` | every hour, right after `update_price()` (its last entry is also overwritten after each trade) | market chart (`chart_view.py`) |
| `price_history_daily` | `update_price_history()` | every day | depot detail / bookkeeping (`depot_view_detail.py`) |

Both lists store the full price (walk × volume factor). They grow for the whole session and are saved in full.

## 8. Saving and loading

`src/persistence/save_manager.py` saves per good: `price` (for reference), `walk_price`, `market_quantity`, `normal_quantity`, both histories, the corridor (`upper_bound`, `lower_bound`), the well-shock state (days left and the bounds to restore afterwards), chart visibility and colour.

Saves older than a field fall back gracefully:
- **No `walk_price`:** the walk is derived from the saved `price` at the saved volume, so the price shown is unchanged.
- **No `normal_quantity`:** the starting stock is used as normal.
- **No corridor:** a freshly rolled corridor is kept.

`base_price` is not saved. It only matters for `simulate_history()`, which runs only for goods a save doesn't have.

## 9. Where this is heading (planned, not implemented)

The intended direction, so changes now don't block it later:

- **Supply.** Town production per good responds slowly to price: low prices shrink production, high prices grow it over the long run. Production feeds `market_quantity` and should move `normal_quantity`, replacing `recover_volume()`.
- **Demand.** Demand comes from the inhabitants and depends on their population type. Unmet demand makes people move out, which lowers demand. Met demand raises happiness and draws people in. Consumption takes from `market_quantity`.
- **Randomness and the player** stay on top: the random walk and the player's trades.
- **Hysteresis / endgame.** When supply or demand is beaten down very low, it recovers slowly; when it is high, it absorbs hits more easily. That makes flooding a market to drive out the competition a viable strategy, and keeping a city well developed harder.

Hooks for this: `normal_quantity` (what the market expects) and `market_quantity` (what is there) are separate on purpose. The volume factor already turns any imbalance between them into a price.

---

## File map

| What | Where |
|---|---|
| Price state, random walk, volume factor, quote/slippage, recovery, bounds, well shock, histories | `src/models/good.py` (`Good`) |
| Starting prices and quantities of every good | `src/game.py`, `Game._create_goods()` |
| Pre-game simulation | `src/game.py`, `Game._presimulate_market_history()` |
| Hourly / daily calls into goods | `src/game.py`, `Game.run()` (`if hour_changed:` / `if day_changed:`) |
| Balance constants (`MARKET_VOLUME_*`, `MARKET_PRESIMULATION_DAYS`, `INITIAL_TRANSACTION_COST`, `STARTING_LICENSES`, `WELL_WISH_*`) | `src/config/constants.py` |
| Buying, selling, fees, FIFO profit, wealth, licenses | `src/models/depot.py` (`Depot`) |
| Can this good be traded here / now? | `src/game_state.py`, `is_good_sold_here()`, `is_good_tradable()` |
| Booth opening hours | `src/models/institutions/market.py`, `src/models/figurines/humans/npcs/trader.py` |
| Well wish trigger and menu | `src/models/institutions/well.py` |
| Trade input (click / keyboard / quick-trade popup) | `src/handlers/mouse_handler.py`, `src/handlers/keyboard_handler.py`, `src/ui/helper_modules/quick_trade_menu.py` |
| Price chart (also shows the market volume as `V.`) | `src/ui/layout_modules/chart_view.py` |
| Depot views (stock value, avg buy price, history) | `src/ui/layout_modules/depot_view.py`, `depot_view_detail.py`, `src/ui/general_layout/layout.py` |
| Save / load of prices | `src/persistence/save_manager.py` |

Building prices (warehouses' `Buy_price` from Tiled) are a separate fixed number and have nothing to do with this system. See `src/models/institutions/warehouse.py`.
