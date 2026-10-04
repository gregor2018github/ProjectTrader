---
name: place-building
description: Put a building sprite made in the Sprite Manager (assets/map_sprites/houses/House_<n>.png) onto the game map, either as a new object or swapped in for an existing one, including buyable warehouses. Use when the user wants a new house, barn, workshop, warehouse or other building "in the game", "on the map", or wants an existing building's texture replaced.
---

# Place a building on the map

Everything a building needs lives in `assets/tiles/Map1.tmx`. The game parses it
on its own (`TMXMap._load_houses` in `src/models/map.py`): collision, NavGrid,
occlusion and the Town Plan all follow from the object. No Python is needed
unless the building is a new *kind*.

Helper (run from the repo root): `python .claude/skills/place-building/place_building.py`
with `near`, `render` and `place`. Its docstring has the arguments.

## Steps

1. **Find the sprite's catalog entry.** `build_tools/Sprite_Manager/building_catalog.json`
   → `files["houses/House_<n>.png"]`: `kind`/`subcategory` (what it is; the user
   may say "barn", grep for it), `rect` (where it sits in the `Houses.png` atlas)
   and `tiled` (the object's properties: `Tiles_to_right`, `Tiles_up`,
   `Collision_to_right`, `Collision_up`, `Col_margin_*_pixel`). The sprite is
   often uncommitted; that is fine. If `tiled.layer` is `Bridges`, this skill
   does not apply (see the bridge section of CLAUDE.md).

2. **Find the spot.** If replacing, find the object: `grep -n 'Buy_type\|name="<name>"' assets/tiles/Map1.tmx`.
   Then `place_building.py near X Y` lists neighbours, and
   `place_building.py render X0 Y0 X1 Y1 <scratchpad>/before.png --figure X,Y`
   shows the area as the game draws it (open the PNG with Read). Leave walking
   room round it and don't let its roof cover another building's front.

3. **Check the scale against a figure.** Figures are 32 px (one tile) wide and
   ~52 px tall; a house door is about 1.2x a figure, barn/cart doors about 2x.
   Sprites are usually right at native size. If not, add `--prop Scale=<f>`
   ("one tile smaller" = `(width - 32) / width`; the Old Barn is 0.92). The
   collision box and margins scale with it, so keep the catalog's values.
   Plain `House` and `Warehouse` objects honour `Scale`; `Mill`, `Well`,
   `Bank`, `Church`, `Town` and `Market` don't pass it on, so add it in
   `map.py` first if one of those needs it. Tiled previews are native size
   only, so the script stamps none for a scaled building.

4. **Place it** (try `--dry-run` first):
   ```
   python .claude/skills/place-building/place_building.py place House_26.png 5600 5728 \
       --replace 337 --name Barn --prop Buy_price=600 --prop Buy_storage=250 \
       --prop Buy_type=Warehouse "--prop=Display_name=Old Barn"
   ```
   X,Y is the bottom-left of the sprite, snapped to tiles. `--replace ID` keeps
   the object id, which matters for warehouses: saves record owned ones by
   `tmx_id` (`depot.properties["warehouses"]`, restored in `Game`), and clears
   the replaced sprite's own preview cells. It also stamps the atlas cells into a `Houses N` tile layer (`--layer`, default
   `Houses 6`) so Tiled shows the building; the script refuses if a cell is taken.

5. **Render again** with figures in front of the door and look at it.

6. **Load it headless** to catch parse warnings:
   ```
   SDL_VIDEODRIVER=dummy python -c "import pygame; pygame.init(); pygame.display.set_mode((1760,1064)); from src.models.map import TMXMap; m=TMXMap('assets/tiles/Map1.tmx'); print([(h.name, h.display_name, h.collision_rect) for h in m.houses if h.name=='Barn'])"
   ```

7. Tick its item in `docs/TODO.md` (move it to "Finished Features") and
   commit the map with the sprite, `Houses.png` and `building_catalog.json` if
   they are still uncommitted.

## What the object's name and properties decide

`TMXMap._load_houses` picks the class from the name first: starts with
`Church`, `Townhall`, contains `Market`, starts with `Mill`, `Well`, `Bank`
(the `elif` chain); then any
object with a `Buy_type` property becomes a `Warehouse`
(`src/models/institutions/warehouse.py`); else a plain `House`.

- **Warehouse**: `Buy_price` (gold), `Buy_storage` (added to
  `depot.storage_capacity` on purchase, `Depot.buy_warehouse`), `Buy_type`
  (`Warehouse`). The "Buy Building" option, the buy dialog and the Town Plan's
  "For sale"/"Your property" come with it. Reference prices: Fred's Shed
  (id 63) 100 gold / +100; Old Barn (id 337, `Scale` 0.92) 600 / +250; start money 100,
  start storage 100 (`src/config/constants.py`).
- `Display_name` is shown in menus and labels the Town Plan.
- `Max_inhabitants` makes it a home (adds to the town's population). Townsfolk
  need a point on the `Doors` layer inside its collision rect (named after the
  direction one faces walking out) to come and go; warehouses have none.
- Town Plan kind (`src/ui/layout_modules/town_plan/landmarks.py`, `_kind`):
  names starting with `House` are dwellings, other names are workshops.

## Pitfalls

- `Map1.tmx` is LF; git on Windows warns "LF will be replaced by CRLF", ignore
  it. Don't hand-write CRLF into it; the script keeps the file's endings.
- Edit the TMX as text (the script does), never by re-saving through pytmx.
- The catalog's atlas `rect` is the sprite's own box, bottom-aligned in a
  tile-aligned slot, so the first atlas row is `(y + h) // 32 - Tiles_up`.
- `nextobjectid` in the `<map>` tag must be bumped for a new object (the script does).
