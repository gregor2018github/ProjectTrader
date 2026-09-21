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

The `Movements` object layer drives map inhabitants: a rectangle named `Sheep` becomes a grazing zone, and each class in `TMXMap.TRADER_TYPES` (a `Trader` subclass) is placed from objects named after its `TILED_PREFIX`: `<prefix>_Market_Stall` (polygon/polyline he walks at work), and optionally `<prefix>_Homeway_Path` plus the points `<prefix>_Homeway_Start` / `<prefix>_Homeway_End` (his way from the stall to his front door). His `MARKET_NAME` links him to his `Market` booth, which is open only while one of its traders is on his stall path: it shuts once the last of them steps onto his homeway, so each booth (and each good, via `GameState.is_good_tradable`) has slightly different hours. Each trader keeps his own `MarketHours`, drawn nightly from `MARKET_CLOSE_WINDOW`/`MARKET_OPEN_WINDOW`; goods a trader sells beyond his market's name go in `EXTRA_GOODS`. An optional `margin` float property on a polygon, **in tiles**, pulls the walked outline inwards so the NPC keeps clear of its own edges (`inset_polygon` in `src/models/figurines/patrol_path.py`); a margin too large to fit is ignored. Add a trader by drawing his shapes in Tiled, writing a small `Trader` subclass, and adding it to `TRADER_TYPES`.

The `Doors` object layer holds one Tiled **point per front door**, named after the direction a person faces walking out of it (`down`, `up`, `left`, `right`); the Tiled object *id* identifies the door and is what a townsperson remembers. Each `Door` (`src/models/door.py`) keeps three spots on one line: the *threshold* (the Tiled point itself, inside the wall — nobody ever stands there), the *step*, the first spot that many whole tiles out which is grid-free, standable, and has a clear line to its own cell centre (a route's first hop is onto the grid, and that hop is validated nowhere else); and between them the *entry*, felt out pixel by pixel as the deepest spot `TMXMap.is_standable()` still allows. A door meeting none of that within `MAX_STEP_TILES` is dropped with a warning naming it, which is a thing to fix in Tiled.

Townsfolk walk entry-to-entry, never onto the point itself — reaching it would put them behind the building, which y-sorts on its own baseline. They come to a **stop at the entry** and only then fade, over `DOORWAY_FADE_SECONDS`, facing the door (`Door.facing_in` / `facing_out`); a doorway fade is not interruptible, not even for a chat.

`NavGrid` (`src/models/navigation.py`) rasterizes house/tree collision rects and the water polygons into one walkable cell per tile, and answers `find_route()` with A* plus line-of-sight smoothing. It also blocks what collision does not: cells where `OCCLUSION_COVER` of a walker's sprite would be hidden behind a building drawn in front of them. Coverage is counted in painted pixels via `pygame.mask`, which is what distinguishes a wall from a fence. Without this, routes run through the band of walkable ground behind tall buildings and walkers simply disappear into them. It is built once, after every blocker has been parsed, and is told the walkers' sprite size so it knows how much of them there is to hide.

`StreetLife` (`src/models/town_life.py`) keeps `STROLLERS_BY_DAY` / `STROLLERS_BY_NIGHT` townsfolk out at a time. A `Townsperson` (`src/models/figurines/humans/npcs/townsperson.py`) steps out of their door fading in, walks a cached door-to-door route — stopping to look at something now and then — and fades out into the door they arrive at, which becomes their home for the next outing. Nobody is out twice, because there is only one object per person. There is no `Townsperson` subclass per person: `discover_townsfolk()` creates one per sprite folder holding an `npc.json`, so adding a townsperson is adding the folder. Their positions are session state, not saved. `StreetLife.update()` only directs; the townsfolk themselves are walked by `update_npcs()` like any other NPC.

### Trading System

`Depot` (src/models/depot.py) manages money, `good_stock` (Dict[str, int]), and FIFO `purchase_history` for profit tracking. Trading licenses are required per good — they expire after a duration and are tracked per good name. The `Good` model (src/models/good.py) tracks current price, market quantity, hourly/daily price history, and chart visibility.

### Key Directories

| Path | Purpose |
|------|---------|
| `src/config/constants.py` | All game balance values, screen dims, paths, speed levels |
| `src/config/colors.py` | Named color constants (imported with `*` in many files) |
| `src/models/figurines/` | Animated map entities: `Figurine` ABC → `Human`/`Animal` → `MapPlayer`, `NPC` → `Trader` → `TraderButcher` etc., `Sheep`. Mirrors `assets/map_sprites/figurines/`. |
| `src/ui/general_layout/layout.py` | Top bar, bottom bar, right sidebar drawing |
| `src/ui/layout_modules/` | Main content modules: market chart, map view, depot views |
| `src/ui/helper_modules/` | Overlay components: menus, dialogs, contract UI, etc. |
| `src/handlers/mouse_handler.py` | All mouse click routing logic |
| `assets/tiles/` | Tiled tilesets and `.tmx` map file |
| `assets/pictures/` | All PNG assets (icons, portraits, buttons, goods) |
| `docs/TODO.md` | Active feature backlog and known bugs |
| `build_tools/` | Standalone dev scripts, not part of the game. `create_new_pose.py` builds 2x2 reference sheets for new NPC poses (top row always the front standing sprite), sends them to a Gemini image model through `gemini_client.py`, and lets every answer be accepted into the sprite folder or marked as not good enough; `pose_review.py` keeps that verdict per answer in `output/<npc>/review.json` and does the accepting. `create_new_NPC.py` turns a Gemini answer into a finished transparent sprite by hand and adds townsfolk as `npcs/<class>_<name>/` with an `npc.json` holding name and gender, names from `medieval_names.py`; prompts live in `sprite_prompts/`. The API needs `pip install -r build_tools/requirements.txt` and a key: `GEMINI_API_KEY` in the environment or in `.env`, or the raw key in `trade_envi/GEMINI_API_KEY.txt` (the venv is git-ignored). Image models are not in Gemini's free tier, so the key's project needs billing. |
