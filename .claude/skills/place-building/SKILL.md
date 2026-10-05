---
name: place-building
description: Put a building sprite made in the Sprite Manager (assets/map_sprites/houses/House_<n>.png) onto the game map, either as a new object, swapped in for an existing one, or moving one already placed, including buyable warehouses and homes with their door, window lights and chimney smoke. Use when the user wants a new house, barn, workshop, warehouse or other building "in the game", "on the map", or wants an existing building's texture replaced.
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
   Buildings are y-sorted on their base, so a tall house *south* of a street
   draws its roof over anything standing on the street's north side: on the
   main street west of x ≈ 3800 (Fine Weaver, Grey Griffin) a building's base
   has to sit north of their roof tops (y ≈ 4265), which is why House_21 is
   set back at y 4256 and the Guildhall at y 4304 (its base may dip a little
   below their roof tops where only a chimney reaches over it). Positions off
   the tile grid take `--no-snap` (`place` and `move`; no Tiled preview then). Put a figure on every door in the render to check.

3. **Check the scale against a figure.** Figures are 32 px (one tile) wide and
   ~52 px tall. Judge by the door, measured in the drawn size: a house door
   about 1x a figure, a public building's main door about 1.4x (the
   Guildhall's arch is 70 px at `Scale` 0.7), barn/cart doors about 2x.
   Sprites are usually right at native size. If not, add `--prop Scale=<f>`
   ("one tile smaller" = `(width - 32) / width`; the Old Barn is 0.92). The
   collision box and margins scale with it, so keep the catalog's values.
   Plain `House` and `Warehouse` objects honour `Scale`; `Mill`, `Well`,
   `Bank`, `Church`, `Town` and `Market` don't pass it on, so add it in
   `map.py` first if one of those needs it. Tile-stamped Tiled previews are
   native size on whole tiles, so a scaled or off-grid building instead gets
   an image layer `Preview <name>` (just before `Houses 1`, so most houses
   overlap it) showing a scaled copy from `assets/tiles/previews/`; `place`
   makes it and `move` keeps it in place. Not a tile object: that needs a
   tileset after `forest_floor_mix`, whose gids the forest builder grows into.
   A sprite redrawn at double resolution (the PNG is 2x the catalog `rect`'s
   size, like House_24 the Guildhall) starts from `Scale=0.5`, then the door
   decides (the Guildhall ended at 0.7). Every number you pass
   is then in the PNG's own pixels: `Collision_to_right`/`Collision_up` in
   tiles of the big PNG (twice the catalog's), margins, door, lights and smoke
   in its pixels, and `Tiles_to_right`/`Tiles_up` = ceil(PNG size / 32).

4. **Trim the collision to the visible walls.** Sprites often carry
   transparent margins, and the catalog's collision guess can span them
   (House_22's walls are x 69–292 of 360 px, its bottom 20 rows empty).
   Measure with `pygame.image.load(p).get_bounding_rect()` and scan a row
   near the bottom for opaque pixels. Then `Col_margin_left_pixel = -<left wall x>`
   and `Col_margin_right_pixel = <right wall x> - Collision_to_right*32`.
   Keep the rect's bottom at Y even when the sprite's bottom rows are empty, so
   nobody can stand in that strip and be drawn behind the wall.

5. **If people live there (a home, a shop, any `Max_inhabitants`): door,
   lights, smoke.** Make a gridded zoom of the sprite (scale 3, a line every
   10 px, labels every 50) and read off, in sprite pixels:
   - **door** `--door SX,SY,down`: centre of the door, a few px above its
     bottom (inside the wall, i.e. inside the collision rect). The game finds
     the step and entry itself and warns if it can't.
   - **lights** `--light SX,SY,W,H`: one per glass pane (not the frame), roughly
     18x22 px for a normal window. They only count within the collision rect's
     x range and up to 5 tiles above it.
   - **smoke** `--smoke SX,SY,W`: the top of the chimney pots, as wide as the
     pots. Smoke is only read for buildings named `House_<n>`, so give a home
     the next free `House_<n>` name (`grep -o 'name="House_[0-9]*"' Map1.tmx`).
   Render afterwards: doors show as blue dots, lights as yellow boxes, smoke as
   cyan bars, so a misplaced one is obvious.

   **Arched, pointed or round windows** (a public building, a church) get
   polygon lights instead of `--light` boxes, like the Townhall, Church and
   Guildhall: one polygon per pane on the `Lights` layer, named after the
   building. Every polygon there is a building light, grouped by that name and
   switched on and off together each night (`TMXMap._load_lights`,
   `BuildingLight` in `src/models/light.py`); they are not tied to a house, so
   knocking does not toggle them. Read each pane's corners off a zoomed grid
   of the sprite (colour tracing fails on leaded glass and dark arcades), as
   rectangles, lancets (straight sides, two slopes to a point) and round tops,
   in sprite pixels; convert with x = X + sx*Scale, y = Y - PNG height*Scale +
   sy*Scale; write each as `<object name="<Building>" x y><polygon points=
   "relative to x,y"/></object>` with a fresh id from `nextobjectid`. Check by
   drawing them filled over a 3x zoom of the sprite (mullions must stay dark),
   then on a darkened render through `BuildingLight.get_render_data(1.0)`.

6. **Place it** (try `--dry-run` first):
   ```
   python .claude/skills/place-building/place_building.py place House_26.png 5600 5728 \
       --replace 337 --name Barn --prop Buy_price=600 --prop Buy_storage=250 \
       --prop Buy_type=Warehouse "--prop=Display_name=Old Barn"

   python .claude/skills/place-building/place_building.py place House_22.png 3808 4384 \
       --name House_21 --layer "Houses 4" --prop Col_margin_left_pixel=-69 \
       --prop Col_margin_right_pixel=-92 --prop Max_inhabitants=25 \
       --door 113,333,down --light 102,136,18,22 --light 174,283,19,25 \
       --smoke 229,39,21
   ```
   X,Y is the bottom-left of the sprite, snapped to tiles. `--replace ID` keeps
   the object id, which matters for warehouses: saves record owned ones by
   `tmx_id` (`depot.properties["warehouses"]`, restored in `Game`), and clears
   the replaced sprite's own preview cells; given new `--door/--light/--smoke`,
   it also removes the old building's ones (that is how to rescale one). It also stamps the atlas cells into a `Houses N` tile layer (`--layer`, default
   `Houses 6`) so Tiled shows the building; the script refuses if a cell is
   taken, so try another layer (`near` shows which are busy there).
   Town houses: 15–35 inhabitants.

   To **move** a building that is already placed, use
   `place_building.py move ID X Y [--dry-run]`: it carries its door, its
   lights (the ones the game gives it), its smoke and its preview along. Read
   the "moved" list: a light zone reaches 5 tiles above the base, so at some
   spots the game hands a neighbour's window to it, and `move` takes that too.
   Compare per-house light counts before and after (load `TMXMap` on `git show
   HEAD:assets/tiles/Map1.tmx` written to a temp file inside `assets/tiles/`,
   so its tileset paths resolve).

7. **Render again** with figures in front of the door and look at it.

8. **Load it headless** and check the wiring (door attached with a step,
   every light on this house, smoke present, no overlapping collision):
   ```
   SDL_VIDEODRIVER=dummy PYTHONPATH=. python -c "
   import pygame; pygame.init(); pygame.display.set_mode((1760,1064))
   from src.models.map import TMXMap
   m=TMXMap('assets/tiles/Map1.tmx'); h=[h for h in m.houses if h.name=='House_21'][0]
   print(h.collision_rect, h.inhabitants, len(h.associated_lights), [(d.direction, d.step) for d in h.doors])
   print([x.name for x in m.houses if x is not h and x.collision_rect.colliderect(h.collision_rect)])"
   ```
   A light goes to the candidate building with the nearest base below it
   (`TMXMap._load_lights`), so fewer lights than you placed means one of them
   is outside the 5-tiles-above zone.

9. Tick its item in `docs/TODO.md` (move it to "Finished Features") and
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
- A public building nobody lives in (the Guildhall) still gets a door, so
  townsfolk can walk to it, and window lights; no `Max_inhabitants`, and
  smoke only if it has a chimney.

## Pitfalls

- `Map1.tmx` is LF; git on Windows warns "LF will be replaced by CRLF", ignore
  it. Don't hand-write CRLF into it; the script keeps the file's endings.
- Edit the TMX as text (the script does), never by re-saving through pytmx.
- The catalog's atlas `rect` is the sprite's own box, bottom-aligned in a
  tile-aligned slot, so the first atlas row is `(y + h) // 32 - Tiles_up`.
- `nextobjectid` in the `<map>` tag must be bumped for a new object (the script does).
