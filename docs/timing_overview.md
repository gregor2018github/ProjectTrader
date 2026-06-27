# Timing & Calculation Overview

This document maps out **when** everything in the game is computed — useful for spotting future performance bottlenecks. The main performance concern is rendering while zoomed out far, which increases tile count dramatically.

---

## Main Loop Structure

```
game.py: run()
├── clock.tick(100)              → cap at MAX_FRAMES_PER_SEC = 100 FPS
├── [time gate] every 16.67ms   → GameState.update() + simulation events
├── [always]                    → reset hover state
├── [always]                    → render modules, bars, overlays
└── pygame.display.update()
```

The simulation gate (`MAX_RECALCULATIONS_PER_SEC = 60`) decouples game logic from the render rate so the two can drift independently.

---

## Every Frame (up to 100×/sec)

These run unconditionally on every iteration of the main loop.

| What | File | Notes |
|---|---|---|
| Drain pending license-expiry warning into `info_window` (if queue non-empty and no dialog open) | game.py | Trivial |
| Reset hover/box state for all 12 goods | game.py:451–455 | Trivial |
| Draw active content modules (map / chart / depot) | game.py:554–588 | Cost depends on mode; see sections below |
| Draw top bar, bottom bar | layout.py | Text + progress bars — moderate |
| Draw right sidebar pictograms | layout.py | Trivial |
| Draw active overlays (menu, dialogue, info window, etc.) | game.py:615–680 | Only drawn when active |
| Update + draw coin popups | game.py:668–672 | Trivial; usually 0–2 alive |
| Blit custom cursor | game.py:679 | Trivial |
| `pygame.display.update()` | game.py:681 | GPU flip |

---

## Simulation Gate (up to 60×/sec, every ≥16.67ms)

`GameState.update()` is called at most 60 times per second. It advances the simulated clock and returns a `TimeChanges` namedtuple with flags `minute_changed`, `hour_changed`, `day_changed`, `week_changed`, `month_changed`, `year_changed`.

The main loop then fires the appropriate event handlers based on those flags.

---

## Hourly Events

Triggered when `hour_changed` is True. The simulation speed (`time_level`) controls how fast real time maps to in-game hours.

| What | File | Cost |
|---|---|---|
| `good.update_price()` × 12 | game.py:372–375, good.py:58–77 | `random.normalvariate()` + mean reversion per good — moderate |
| `good.update_price_history_chart()` × 12 | game.py:374–375, good.py:83–85 | Append to hourly list — trivial |
| `population_manager.update_happiness()` | game.py:377, population.py:68–111 | Random noise + equilibrium drift per group (4 groups) — moderate |
| `population_manager.record_happiness_history()` | game.py:379 | Append per-group + aggregate — trivial |
| Church bell at hours 0 and 12 | game.py:382–389 | Sound play + volume set — trivial |

---

## Daily Events

Triggered when `day_changed` is True.

| What | File | Cost |
|---|---|---|
| `depot.stats.days_played += 1` | game.py:393 | Trivial |
| `depot.update_income_and_expenditures()` | game.py:394, depot.py:420–443 | Archive day's counters — trivial |
| Cost-of-living deduction | game.py:395–397 | Arithmetic — trivial |
| Loan processing (principal + interest per loan, settle at maturity) | game.py:400–431 | Scales with loan count; currently O(loans) — moderate |
| Overdraft penalty (2% of negative balance) | game.py:434–437 | Trivial |
| License expiry check — warn if any license expires tomorrow | game.py, `day_changed` block | Dict scan O(licenses), trivial |
| `depot.update_wealth(goods)` — money + stock×price − loans | game.py:439, depot.py | 12-good loop — moderate |
| Total stock sum + append to history | game.py:440 | Trivial |
| Per-good stock history append × 12 | game.py:441 | Trivial |
| `good.update_price_history()` × 12 | game.py:442–443 | Append to daily list — trivial |
| `good.tick_well_shock_day()` × 12 | game.py:444 | Decrement counter, restore bounds if expired — trivial |
| `population_manager.update_population()` | game.py:446, population.py:119–142 | Compute delta from happiness, redistribute into groups with clamping — moderate |
| `population_manager.record_population_history()` | game.py:448 | Append — trivial |

---

## Weekly / Monthly / Yearly Events

The `TimeChanges` flags `week_changed`, `month_changed`, and `year_changed` are **computed but not yet acted on** in the main loop. These slots are available for future logic at no extra cost.

---

## Map View — Per Frame (when map is visible)

These run every frame while at least one side shows the map.

### Movement & Sound
| What | File | Cost |
|---|---|---|
| Read held keys, apply player velocity | game.py:473–474 | Trivial |
| `game_map.update(delta_time, date)` — move player, advance animation frame | game.py:475 | Trivial |
| Accumulate tiles_walked stat | game.py:476–477 | Trivial |
| Sheep sound distance check per sheep | game.py:478–492 | O(sheep) Euclidean distance calc — moderate |

### Camera
| What | File | Cost |
|---|---|---|
| `Camera.update()` — center on player with zoom + map-bound clamping | map_view.py:51–52 | Float math — moderate |
| Compute `scaled_tile_size`, `scale_factor`, pixel offsets | map_view.py | Derived from camera — trivial |

### Tile Rendering ⚠️ Main bottleneck when zoomed out
| What | File | Cost |
|---|---|---|
| Calculate tile range from viewport | map_view.py:233–240 | Trivial |
| For each visible tile × each ground layer: lookup/scale/blit | map_view.py:241–272 | **Expensive** — scales with visible tile count |
| Tile scale cache lookup (`_get_scaled_tile`) | map.py:572–596 | Cache hit: trivial. Cache miss (zoom change): `smoothscale` per tile |

**Why zoom-out hurts:** At low zoom the viewport covers more world, so more tiles fall in the visible range and get blitted per frame. A zoom change also invalidates the tile scale cache for that zoom level, forcing `smoothscale` on every visible tile in that first frame.

### Object Rendering
| What | File | Cost |
|---|---|---|
| House hover detection — collision check against all houses | map_view.py:62–91 | O(houses) per frame — moderate |
| Build render queue — houses, mills, lights, smoke, trees, fields, player | map_view.py:95, 275–391 | O(objects) — moderate |
| Y-sort the render queue | map_view.py:114 | O(n log n) — moderate |
| Blit each object in sorted order | map_view.py:116–127 | Scales with object count |

### Lighting
| What | File | Cost |
|---|---|---|
| `light.update(time)` per light — check on/off + flicker | map_view.py:58, light.py | O(lights) — trivial per light |
| Compute ambient color from hour keyframes | map_view.py:130–145 | Interpolation — trivial |
| Create lighting surface, fill, blit lights with ADD blend | map_view.py:147–188 | O(active lights) surface ops — moderate |
| Blit lighting surface over scene with MULT blend | map_view.py:186–188 | One blit — trivial |

---

## Chart View — Per Frame (when market chart is visible)

| What | File | Cost |
|---|---|---|
| Compute max price across visible goods' hourly history | chart_view.py | O(goods × history length) — moderate |
| Draw chart background and axes | chart_view.py | Trivial |
| For each visible good: draw price line | chart_view.py | O(visible goods × points) |
| Mouse hover: find closest good + draw tooltip | chart_view.py | O(visible goods) distance calc |
| Draw good selection boxes with hover effects | chart_view.py | O(12 goods) |

---

## Depot View — Per Frame (when depot is visible)

Mostly text and rect blitting; redraws fully every frame.

| What | File | Cost |
|---|---|---|
| Header, date range, navigation buttons | depot_view.py | Trivial |
| Goods stock list (scroll if needed) | depot_view.py | O(12 goods) |
| Trade statistics, profit/loss breakdown | depot_view.py | Trivial |
| Wealth / stock / population history charts | depot_view_chart.py | O(history length) line drawing |

No caching: text surfaces are re-rendered every frame even when values haven't changed.

---

## Event-Driven (not per-frame)

### Mouse clicks — `mouse_handler.py`
- **Info window active:** all clicks routed there exclusively, nothing else fires.
- **Trade buy/sell:** check license, compute cost, update depot and price — moderate.
- **Chart toggle:** flip good visibility flag — trivial.
- **House click on map:** open info window — trivial.
- **All other clicks:** set a flag or toggle state — trivial.

### Keyboard — `keyboard_handler.py`
- WASD / arrows: set player velocity — trivial.
- 1–5: change `time_level` — trivial.
- Space: toggle pause — trivial.
- Everything else: trivial.

### Contract acquisition
- **Creation:** file I/O + image loading for parchment UI — one-time ~10–50ms, pauses simulation.
- **Per-frame while active:** advance quill/particle animation — trivial.
- **On approval:** date arithmetic to set license expiry — trivial.

---

## Startup (once)

| What | File | Cost |
|---|---|---|
| Load TMX map + parse houses, towns, churches, markets, trees | game.py:96, map.py | Expensive — file I/O |
| Load all PNG assets | game.py:112–287 | Expensive — disk reads |
| Load all sounds | game.py:114–311 | Expensive — disk reads |
| Market presimulation: 60 days × 24 hours of price updates | game.py:83 | ~1440 `update_price()` calls — moderate total |
| Population initialization from house sum | game.py:98–106 | Trivial |

---

## Summary: Cost by Category

| Category | Frequency | Relative Cost |
|---|---|---|
| Tile rendering (zoomed in) | Every frame | Moderate |
| Tile rendering (zoomed out) ⚠️ | Every frame | **High** |
| Tile rescaling on zoom change ⚠️ | First frame after zoom | **High (spike)** |
| Render queue build + Y-sort | Every frame (map) | Moderate |
| Sheep sound distance checks | Every frame (map) | Moderate |
| Lighting overlay | Every frame (map) | Moderate |
| House hover detection | Every frame (map) | Moderate |
| Chart line drawing | Every frame (chart) | Moderate |
| Depot view text rendering | Every frame (depot) | Moderate |
| Hourly price updates × 12 | Hourly (simulated) | Low |
| Hourly happiness updates | Hourly (simulated) | Low |
| Daily wealth calculation | Daily (simulated) | Low |
| Daily population redistribution | Daily (simulated) | Low |
| Loan processing | Daily (simulated) | Low (scales with loan count) |

---

## Known Gaps / Future Slots

- `week_changed`, `month_changed`, `year_changed` flags are computed but unused — free slots for seasonal events, tax cycles, etc.
- Depot view text surfaces are not cached — a text-surface cache keyed on value would eliminate repeated font renders.
- House hover detection checks every house linearly — spatial partitioning (grid or quadtree) would help on large maps.
- Sheep sound calculation is O(sheep) per frame — could be bounded by checking only sheep within `SHEEP_SOUND_MAX_DISTANCE` using a spatial index.
