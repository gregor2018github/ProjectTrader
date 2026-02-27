# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Game

```bash
# Install dependencies
pip install -r requirements.txt

# Run the game
python main.py
```

Dependencies: `pygame==2.6.1` and `PyTMX==3.32`. There are no tests or build steps.

## Architecture Overview

**Merchant's Rise** is a medieval trading simulation built with Pygame. The game has no persistent save state yet — everything starts fresh each run.

### Core Object Graph

`Game` (src/game.py) is the central orchestrator that owns all major objects and runs the main loop. It creates and holds:
- `GameState` — session data and transient UI state (passed everywhere as `game_state`)
- `Depot` — player inventory, money, bookkeeping
- `Player` — player character with map position logic
- `GameMap` — TMX-based tiled map, camera, collision
- `EventHandler` — dispatches pygame events to keyboard/mouse handlers
- Lists of `Good` objects — the 12 tradeable commodities

`GameState` (src/game_state.py) is the shared data bus. It does **not** own logic — it stores flags like `left_side_mode`, `right_side_mode`, `info_window`, `warning`, `contract_acquisition`, `time_level`, and `date`. UI components read and write `game_state` directly rather than using signals/callbacks.

### Screen Layout

Total window: **1760×1064** (SCREEN_WIDTH=1650 + SIDEBAR_WIDTH=110).

The content area (1650px wide) is split into two equal **modules** (MODULE_WIDTH = 825px each). Each side can independently show `'map'`, `'market'`, or `'depot'`. When both sides show the same module, it takes the full width. The top bar (60px) and bottom bar (60px) are always visible. The 110px right sidebar holds the navigation pictograms.

Rendering layers in the main loop (src/game.py `run()`):
1. Background fill
2. Left/right content modules
3. Persistent UI bars (`draw_layout`, `draw_right_bar`)
4. Overlays in order: dropdowns → dialogue → info_window → fading menu → contract_acquisition → warning/message → custom cursor

### UI Pattern: Modal Overlays

Any modal dialog (quit confirm, house menus, donation menu, contract overview, population stats) is assigned to `game_state.info_window`. The `EventHandler` routes clicks to `game_state.info_window.handle_click()` and keyboard events to `handle_event()` before routing to the rest of the game. Setting `game_state.info_window = None` closes the modal.

`game_state.contract_acquisition` is a special full-screen overlay that **consumes all input** while active.

### Time System

5 speed levels controlled by `game_state.time_level` (1=paused, 3=normal, 5=fastest). When the map is visible, speed is clamped to 1 or 3. The simulation time (`game_state.date`) advances via `GameState.update()` which returns a `TimeChanges` namedtuple. The main loop fires:
- **Hourly**: price updates, church bell check
- **Daily**: cost-of-living deduction, wealth/stock bookkeeping

### Map System

`GameMap` (src/models/map.py) loads a Tiled `.tmx` file via `pytmx`. Map objects are parsed into typed Python objects: `House`, `Town` (extends House — the town hall), `Church`, `Market`, `Tree`. Population is initialized on `Town` by summing `max_inhabitants` from all House objects. The `Camera` class handles zoom and panning.

### Trading System

`Depot` (src/models/depot.py) manages money, `good_stock` (Dict[str, int]), and FIFO `purchase_history` for profit tracking. Trading licenses are required per good — they expire after a duration and are tracked per good name. The `Good` model (src/models/good.py) tracks current price, market quantity, hourly/daily price history, and chart visibility.

### Key Directories

| Path | Purpose |
|------|---------|
| `src/config/constants.py` | All game balance values, screen dims, paths, speed levels |
| `src/config/colors.py` | Named color constants (imported with `*` in many files) |
| `src/ui/general_layout/layout.py` | Top bar, bottom bar, right sidebar drawing |
| `src/ui/layout_modules/` | Main content modules: market chart, map view, depot views |
| `src/ui/helper_modules/` | Overlay components: menus, dialogs, contract UI, etc. |
| `src/handlers/mouse_handler.py` | All mouse click routing logic |
| `assets/tiles/` | Tiled tilesets and `.tmx` map file |
| `assets/pictures/` | All PNG assets (icons, portraits, buttons, goods) |
| `docs/TODO.md` | Active feature backlog and known bugs |
