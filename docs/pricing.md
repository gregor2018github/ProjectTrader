# Pricing: How Goods Are Priced

An orientation page for anyone (human or coding agent) about to touch market prices. It explains the model at a high level, then points to where each piece lives in the code. Line numbers drift, so search for the named function or constant rather than trusting them.

---

## The model in one paragraph

Every tradeable good has **one global price**: it is the same at every market booth and for buying and selling. Once per in-game hour, each price takes a **random multiplicative step** (`price *= N(mu, sigma)`). Each good has a **soft corridor** (`lower_bound` … `upper_bound`), rolled at random when the good is created. Inside the corridor the walk is free and volatile; outside it the walk becomes calm and drifts back. **Player trades do not move the price.** The only thing that moves it on purpose is a **well wish**. The player pays the price per unit plus a flat **transaction fee** per trade. Profit is measured with **FIFO** against the purchase prices.

---

## 1. Starting prices

Each good is created with a hand-set starting price and market quantity in `Game._create_goods()` (`src/game.py`), e.g. Wood 1, Stone 2, Wine 10, Salt 6.

At creation (`Good.__init__`, `src/models/good.py`):

| Field | Value | Meaning |
|---|---|---|
| `price` | starting price | Current price |
| `base_price` | starting price | Kept only to re-simulate history (see §5) |
| `upper_bound` | `price × U(1.5, 3.5)` | Above this, the price drifts down |
| `lower_bound` | `price × U(0.05, 0.80)` | Below this, the price drifts up |

Before the first frame, `Game._presimulate_market_history()` runs the hourly update forward for `MARKET_PRESIMULATION_DAYS` (60) days, so the charts open with history and the game starts at an already-drifted price, not the hand-set one.

## 2. The hourly price step

`Good.update_price()` is called once per in-game hour from the main loop in `Game.run()` (`if hour_changed:`). The new price is `price × random.normalvariate(mu, sigma)`:

| Situation | `mu` | `sigma` | Effect |
|---|---|---|---|
| Inside the corridor | 1.00 | 0.10 | Free random walk, about ±10 % per hour |
| Above `upper_bound` | 0.999 | 0.01 | Slow, calm decline |
| Below `lower_bound` | 1.02 | 0.01 | Calm recovery of about 2 % per hour |
| Price < 1 (on top of the above) | +0.03 | – | Extra push up so cheap goods don't collapse toward 0 |

The bounds are **soft**. A single in-corridor step can jump well past a bound, and the drift back is gradual.

The speed level (`time_level`) only changes how fast in-game hours pass. It does not change the formula.

## 3. What does *not* affect price

People often assume these affect the price, but in the current code they don't:

- **Trade volume / supply.** `Depot.buy` / `Depot.sell` call `Good.buy()` / `Good.sell()`, which only change `market_quantity`. The quantity limits how much you can buy ("Market cannot fulfill the order"), but it never feeds into `update_price()`.
- **Which market or booth.** There is one `Good` object per good, shared by all booths. Booths only decide *whether* you may trade (see §4).
- **Population, happiness, season, time of day.** None of these are read by the price step.

If you add supply/demand or regional pricing, this section and §2 are the ones to rewrite.

## 4. What it costs the player to trade

Trading goes through `Depot.buy()` / `Depot.sell()` (`src/models/depot.py`). Both use `good.get_price()` at that moment:

- **Buy:** pays `price × qty + transaction_cost`.
- **Sell:** receives `price × qty − transaction_cost`.
- `transaction_cost` is a flat fee per trade, not per unit. It starts at `INITIAL_TRANSACTION_COST` (2) and is stored on the depot and in the save.

Before a trade, a series of gates must pass. They block the trade but never change the price:
1. `GameState.is_good_sold_here()`: does the market square the player stands in have a booth for this good?
2. `GameState.is_good_tradable()`: is one of those booths open right now? (Booths close when their trader goes home; see CLAUDE.md, Map System.)
3. `Depot.has_license()`: the player needs a valid trading license per good.
4. Money, storage capacity and the market quantity.

**Profit accounting.** Each buy is pushed onto `purchase_history[good]` with its unit price. A sell consumes those entries oldest-first (FIFO), and each consumed chunk is recorded by `_record_trade_cycle()` as a trade cycle with its buy price, sell price and profit. `Depot.avg_buy_price()` gives the FIFO-weighted average cost of what is still held. This is what the depot views and the top bar show next to the market value.

**Wealth.** `Depot.update_wealth()` values stock at the current market prices.

## 5. Well wishes: the one deliberate price shock

Throwing a coin in the well (`Well`, `src/models/institutions/well.py`) has a `WELL_WISH_PROBABILITY` chance, when the well is not on cooldown, of opening a `WishMenu`. In that menu the player picks a good and a direction. `Good.apply_well_shock()` then:

- multiplies the price **and both bounds** by `1 ± WELL_WISH_SHOCK_FACTOR` (40 %), so the corridor moves with the price and the price settles at the new level instead of snapping back;
- after `WELL_WISH_DURATION_DAYS` daily ticks (`Good.tick_well_shock_day()`, called from the daily block in `Game.run()`), restores the original bounds. The price then drifts back by the normal corridor rules.

Note: the direction string compared against is `"Price goes up"` (the menu label). The docstring's `"Up"`/`"Down"` is out of date.

## 6. Price history (charts and bookkeeping)

| List | Appended by | When | Used by |
|---|---|---|---|
| `price_history_hourly` | `update_price_history_chart()` | every hour, right after `update_price()` | market chart (`chart_view.py`) |
| `price_history_daily` | `update_price_history()` | every day | depot detail / bookkeeping (`depot_view_detail.py`) |

Both lists grow without limit for the whole session and are saved in full.

## 7. Saving and loading

`src/persistence/save_manager.py` saves per good: `price`, `market_quantity`, both histories, chart visibility and colour.

**Not saved:** `upper_bound`, `lower_bound`, `base_price` and the well-shock state. On load the goods are created fresh, so the **corridor is re-rolled** around the hand-set starting price (not the saved price), and any active well shock is lost. A loaded price that falls outside the new corridor simply drifts back in. Keep this in mind if you make the bounds matter more.

A good that was added to the game after a save was made has no saved data. It gets a made-up history of matching length from `Good.simulate_history()`.

---

## File map

| What | Where |
|---|---|
| Price state and the hourly step, bounds, well shock, histories | `src/models/good.py` (`Good`) |
| Starting prices and quantities of every good | `src/game.py`, `Game._create_goods()` |
| Pre-game simulation | `src/game.py`, `Game._presimulate_market_history()` |
| Hourly / daily calls into goods | `src/game.py`, `Game.run()` (`if hour_changed:` / `if day_changed:`) |
| Balance constants (`MARKET_PRESIMULATION_DAYS`, `INITIAL_TRANSACTION_COST`, `STARTING_LICENSES`, `WELL_WISH_*`) | `src/config/constants.py` |
| Buying, selling, fees, FIFO profit, wealth, licenses | `src/models/depot.py` (`Depot`) |
| Can this good be traded here / now? | `src/game_state.py`, `is_good_sold_here()`, `is_good_tradable()` |
| Booth opening hours | `src/models/institutions/market.py`, `src/models/figurines/humans/npcs/trader.py` |
| Well wish trigger and menu | `src/models/institutions/well.py` |
| Trade input (click / keyboard / quick-trade popup) | `src/handlers/mouse_handler.py`, `src/handlers/keyboard_handler.py`, `src/ui/helper_modules/quick_trade_menu.py` |
| Price chart | `src/ui/layout_modules/chart_view.py` |
| Depot views (stock value, avg buy price, history) | `src/ui/layout_modules/depot_view.py`, `depot_view_detail.py`, `src/ui/general_layout/layout.py` |
| Save / load of prices | `src/persistence/save_manager.py` |

Building prices (warehouses' `Buy_price` from Tiled) are a separate fixed number and have nothing to do with this system. See `src/models/institutions/warehouse.py`.
