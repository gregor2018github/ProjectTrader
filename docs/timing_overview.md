# Timing & Calculation Overview

This document maps out **when** everything in the game is computed — useful for spotting future performance bottlenecks. The main performance concern is drawing the map while zoomed out far; the economy itself is cheap (the headless runner does 50 game years in about 6 seconds). Line numbers drift, so search for the named function rather than trusting a line. `build_tools/Perf_Probe/perf_probe.py` measures frame times on a fixed walk; run it before and after a change that may cost frame time.

---

## Main Loop Structure

```
game.py: run()
├── clock.tick(fps_limit)                → the "FPS Limit" setting (default MAX_FRAMES_PER_SEC = 100; 0 runs free)
├── [time gate] every ≥16.67 ms          → GameState.update(), weather, sim.advance_to(), game's hourly/daily work
├── [always]                             → notices, reset hover state, update map/sounds, render modules, bars, overlays
├── [always]                             → input events, coin popups, MapWarmup.step(), autosave
└── pygame.display.update()
```

The time gate (`MAX_RECULCULATIONS_PER_SEC = 60`, sic) decouples the game clock from the frame rate, so the two can drift independently.

---

## Every Frame

These run on every iteration of the main loop.

| What | File | Notes |
|---|---|---|
| Show one queued notice (licence expiry, rank change) as an `InfoWindow` if no dialog is open | game.py | Trivial |
| Reset hover/box state for all 30 goods | game.py | Trivial |
| `ViewTransition.begin_frame()` (grabs the old view if a module changed) | view_transition.py | A screen copy only when a view changes |
| Update the map, if shown and not paused (see "Map View" below) | game.py, map.py | Main cost when the map is shown |
| `Ambience.update()`, `Lightning.update()`, `Coughs`, `Owls`, `Dogs` | ambience.py, lightning.py, ... | Volume glides and timers, trivial |
| Church bell volume while it rings | game.py | Trivial |
| Draw active content modules (map / market chart / depot / town plan) | game.py `render_module` | Cost depends on mode; see sections below |
| Parchment roll over a changed view | view_transition.py | Only while it runs |
| Draw top bar, bottom bar, right sidebar | layout.py | Text + icons — moderate |
| Debug overlay, menu, time and sound controls, pause overlay | game.py | Trivial |
| Draw active overlays (dropdowns, dialogue, info window, contract, minigame, warning, message) | game.py | Only when active |
| Handle input events | event_handler.py | Event-driven, see below |
| Update + draw coin popups | game.py | Trivial; usually 0–2 alive |
| `MapWarmup.step()` | map_warmup.py | Pre-scales what the map needs at other zoom levels, at most `WARMUP_BUDGET_S` (1.5 ms) a frame, until all is done |
| Autosave timer, save indicator, fade cover | game.py | An autosave writes the save file and a thumbnail: a one-off spike |
| `pygame.display.update()` | game.py | Flip (frames are scaled to the window on the GPU, see `main.py`) |

---

## Time Gate (up to 60×/sec, every ≥16.67 ms)

`GameState.update()` is called at most 60 times per second. It advances the game clock by the speed level's `TIME_STEP_LEVEL_*` (game minutes per update; 0.05 at normal speed, so a day takes 8 real minutes) and returns a `TimeChanges` namedtuple with flags `minute`, `price_tick`, `hour`, `day`, `season`, `year`. The calendar's ticks come from `src/sim/calendar.py` (`tick_numbers()`).

Then, in order:

| What | File | Cost |
|---|---|---|
| `Weather.update(date)`: spells, rain, clouds, wind, fog, storm, wetness | weather.py | Trivial |
| Street life told whether it rains; `Puddles.update(wetness)` (places new puddles over a few updates, at most `PLACE_BUDGET_S` each) | town_life.py, puddles.py | Trivial, a little while puddles are placed |
| `sim.advance_to(date)`: the simulation's scheduler fires every tick passed (see below) | src/sim/simulation.py | Low; more at the fast speeds, when several ticks pass per update |
| `Game._handle_sim_events()`: drains the sim's event queue | game.py | Trivial (nothing is shown for the events yet) |
| The game's hourly and daily work on the flags (see below) | game.py | Low |

---

## The Simulation's Ticks (`src/sim/`)

Fired by `Simulation.advance_to()` inside the time gate, from price tick to price tick; `docs/sim_core.md` has the exact order.

| Tick | What | Cost |
|---|---|---|
| Price tick (every 30 game minutes, 48 a day) | Each good's noise step (one draw) and a chart point × 30 goods | Trivial |
| Hour, in market hours (slices ending 07:00–18:00) | Orders of every class (4) and workshop (26); each good's buyers cleared at one price; workshops run their share of the day's batches and sell; merchants import and export | O(goods × (classes + workshops)) — low |
| Hour, every hour | Happiness glides towards its target, history point | Trivial |
| Day (midnight) | Books close (`market_balance`); per good: close the day, outside price's walk, well shock, target stock; workshops settle wages and owners' surplus; classes earn and plan; migration; workshops plan, hire, wages move, capacity grows or shrinks; daily records | Low |
| Week, season, year | Nothing subscribed | — |

---

## The Game's Hourly Work

Triggered when `hour` changed.

| What | File | Cost |
|---|---|---|
| `TMXMap.update_crops(date)`: each field's growth stage from the date | map.py, crop_growth.py | Trivial |
| Church bell at hours 0 and 12 | game.py | Sound play — trivial |

---

## The Game's Daily Work

Triggered when `day` changed.

| What | File | Cost |
|---|---|---|
| `depot.stats.days_played += 1` | game.py | Trivial |
| `depot.update_income_and_expenditures()` — archive yesterday's counters | depot.py | Trivial |
| `depot.update_wealth(goods)`, `update_total_stock()`, `update_stock_history()` | depot.py | 30-good loop — trivial |
| Cost-of-living deduction | game.py | Trivial |
| Loan processing (principal + interest per loan, settle at maturity) | game.py | O(loans) — trivial |
| Overdraft penalty (`OVERDRAFT_DAILY_RATE` of a negative balance) | game.py | Trivial |
| Licence expiry check — notice if any licence expires tomorrow | game.py | O(licences), trivial |
| Each season: `MerchantRank.new_season()` (reputation fades) | merchant_rank.py | Trivial |
| `MerchantRank.daily_check()` — rise or slip | merchant_rank.py | Trivial |

The week and year flags are not acted on by the game yet (`TimeChanges` has no week flag; the sim's week tick has no subscriber).

---

## Map View — Per Frame (when the map is visible)

### Updates (only when not paused)
| What | File | Cost |
|---|---|---|
| Read held keys, apply player velocity | game.py, map.py | Trivial |
| `GameMap.update()`: move the player, reveal the fog of war around him, sheep, NPCs and street life (a new route is worked out over several frames, at most `ROUTE_BUDGET_S` each), crops' sway, chimney smoke, mill blades, ripples, camera | map.py, town_life.py, navigation.py | Moderate; a route search is capped per frame |
| `Rainfall.update()`, `Fog.update()`, `Puddles.update_walkers()` | rain.py, fog.py, puddles.py | Scales with the rain's drops / fog layers; low when dry and clear |
| Tiles walked stat, sheep sounds, door sounds | game.py | O(sheep) distance checks — trivial |
| Player's market area (which booths are near) | game.py | Trivial |

### Drawing (`draw_map_view`, map_view.py)
| What | File | Cost |
|---|---|---|
| Ground: cached chunks of `CHUNK_TILES`² tiles per zoom level, below and above the animated water | ground_chunks.py | A few blits per frame; a chunk not yet made costs a one-off spike (`MapWarmup` makes them ahead) |
| Animated water, wet ground (redrawn only when the camera moved a quarter tile or the wetness changed), bridges | map_view.py, wet_ground.py | Moderate |
| Light and market states updated | map.py | O(lights) — trivial |
| Hover detection: houses checked linearly, then figurines | house_click_menu.py, figurine_click_menu.py | O(houses) — moderate |
| Build the render queue: houses, figurines, smoke, and the lights, crops and trees near the view from `SpatialIndex`es | map_view.py, spatial_index.py | O(objects in view) — moderate |
| Y-sort the render queue, puddles (with reflections), blit the queue | map_view.py, puddles.py | O(n log n) + blits — moderate |
| Lighting overlay (ambient colour from the sun hour, season tint, clouds, storm; lights added) | map_view.py | One surface fill and blits — moderate |
| Fog (worked out at 2 px a tile, 15×/s or when the camera crosses a pixel), rain drops in one `blits()` call, lightning flash | fog.py, rain.py | Moderate in fog or rain |

**Why zoom-out hurts:** at low zoom the viewport covers more world, so more chunks, trees, crops and figurines fall in view. The first frame at a new zoom level used to rescale everything; `MapWarmup` now does that ahead, while loading and a little each frame, so only something it does not know about stutters (see CLAUDE.md, Map System).

---

## Town Plan — Per Frame (when the 'building' view is visible)

| What | File | Cost |
|---|---|---|
| The engraved plan for the zoom level (made once while loading, `TownPlan.prepare()`) | town_plan/ | One blit |
| Parchment, unexplored land's cover, player mark, camera frame, stalls, names, hover tooltip | town_plan/ornaments.py, view.py | Moderate |

---

## Chart View — Per Frame (when the market chart is visible)

| What | File | Cost |
|---|---|---|
| Compute max price across visible goods' price-tick history | chart_view.py | O(goods × history length) — moderate |
| Draw chart background and axes | chart_view.py | Trivial |
| For each visible good: draw price line | chart_view.py | O(visible goods × points) |
| Mouse hover: find closest good + draw tooltip | chart_view.py | O(visible goods) distance calc |
| Draw good selection boxes with hover effects and pin markers | chart_view.py | O(30 goods) |

---

## Depot View — Per Frame (when depot is visible)

Mostly text and rect blitting; redraws fully every frame.

| What | File | Cost |
|---|---|---|
| Header, date range, navigation buttons | depot_view.py | Trivial |
| Goods stock list (scroll if needed) | depot_view.py | O(30 goods) |
| Trade statistics, profit/loss breakdown | depot_view.py | Trivial |
| Wealth / stock / population history charts | depot_view_chart.py | O(history length) line drawing |

No caching: text surfaces are re-rendered every frame even when values haven't changed.

---

## Event-Driven (not per-frame)

### Mouse clicks — `mouse_handler.py`
- **Info window active:** all clicks routed there exclusively, nothing else fires.
- **Trade buy/sell:** check booth, opening hours, licence, money and storage; `Simulation.trade_with_player()` prices each unit at its stock — O(units), low.
- **Chart toggle:** flip good visibility flag — trivial.
- **House click on map:** open info window — trivial.
- **Town plan:** drag and wheel go to `TownPlan` first while it is drawn.
- **All other clicks:** set a flag or toggle state — trivial.

### Keyboard — `keyboard_handler.py`
- WASD / arrows: set player velocity — trivial.
- 1–6, M: change the view — trivial (the view transition starts).
- Space, + / –: pause, speed or zoom — trivial.
- Everything else: trivial.

### Contract acquisition
- **Creation:** file I/O + image loading for parchment UI — one-time ~10–50ms, pauses simulation.
- **Per-frame while active:** advance quill/particle animation — trivial.
- **On approval:** date arithmetic to set licence expiry — trivial.

---

## Startup (once, behind the loading screen)

| What | File | Cost |
|---|---|---|
| Load the definitions (`assets/data/`) and create the `Simulation` with a fresh seed | game.py, src/sim/data.py | Trivial |
| Load TMX map + parse houses, markets, trees, fields, doors, bridges, roofs; build `NavGrid`, `Cover`, spatial indexes | map.py | Expensive — file I/O and rasterising |
| `TownPlan.prepare()`: the plan engraved at every zoom level | town_plan/ | Expensive |
| Found the town, establish the scenario's workshops, `Simulation.presimulate(MARKET_PRESIMULATION_DAYS)` (224 days of the whole economy, 4 ms a day) | game.py, simulation.py | Moderate — about 0.9 s |
| Load all PNG assets and sounds | game.py | Expensive — disk reads |
| `MapWarmup.prepare()`: the starting zoom and the ground around the player | map_warmup.py | Moderate |

---

## Summary: Cost by Category

| Category | Frequency | Relative Cost |
|---|---|---|
| Map drawing (zoomed in) | Every frame | Moderate |
| Map drawing (zoomed out) ⚠️ | Every frame | **High** |
| Chunks or sprites not yet warmed up at a zoom level | First frames after a zoom | Spike (mostly avoided by `MapWarmup`) |
| Fog and heavy rain | Every frame (map) | Moderate to high |
| Render queue build + Y-sort | Every frame (map) | Moderate |
| House hover detection | Every frame (map) | Moderate |
| Chart line drawing | Every frame (chart) | Moderate |
| Depot view text rendering | Every frame (depot) | Moderate |
| Simulation: price ticks, hourly slices | Per game tick | Low |
| Simulation: day | Daily (game time) | Low |
| Game's daily bookkeeping, loans | Daily (game time) | Low |

---

## Known Gaps / Future Slots

- The week and year ticks have no subscribers yet, in the game or the simulation — free slots for tax cycles, ageing (once a year), etc.
- Depot view text surfaces are not cached — a text-surface cache keyed on value would eliminate repeated font renders.
- House hover detection checks every house linearly — the spatial indexes used for trees, crops and lights (`SpatialIndex`) could serve it too.
- At the fastest speed (`TIME_STEP_LEVEL_5`, 6 game minutes an update) a day passes in about 4 real seconds, so the simulation's slices and the game's daily work come often; still cheap, but worth watching as the sim grows.
