# Forest Builder

`grow_forest.py` plants a forest on `assets/tiles/Map1.tmx`. Hand-placing a
hundred trees in Tiled is slow, and each tree has to be added twice. The script
does both halves of that and keeps them in sync.

## How trees are stored in the map

| Where | Read by | What |
|---|---|---|
| `Trees` **object** layer | the game | One point per tree, at the **bottom-left corner** of its sprite, on a tile corner. Properties: `File_name` (`Tree_NN.png`), `Stem_Position` (stem centre from the left, in tiles), `Stem_Thick` (stem collision width, in tiles), `Tiles_to_right`, and optionally `Scale`. |
| `Trees 2` … `Trees 7` **tile** layers | only Tiled | The sprite's tiles from the `Trees` tileset (`assets/map_sprites/trees/Trees.png`). The bottom-left tile sits just above the object point. The game never draws these; they're only there so you can see the trees while planning. |
| `Ground_High_Plus`, `Ground_Flowers_Mushrooms` | the game | Forest floor and flowers under the trees. Every `Ground*` tile layer is drawn in game. |

`Scale` (for example `0.9` or `1.12`) draws the tree smaller or larger. It grows
from its bottom-left corner, and the stem moves and thickens with it. Tiled
can't scale tiles, so a scaled tree shows at its normal size in Tiled.

A tile layer holds one tile per cell. Overlapping trees therefore need
different layers, and the tree in front needs the later layer. A dense forest
overlaps more deeply than six layers can always get right. The script gives
each tree the free layer with the fewest wrong overlaps, and prints how many
cells still came out wrong. Those only show in Tiled; the game sorts trees by
their bottom edge itself.

## Steps

1. **Close Tiled.** If it still has the map open, its next save overwrites the
   script's changes.
2. **Pick the spot.** Open the map in Tiled (or look at
   `build_tools/output/forest/forest_game.png` from an earlier run) and note
   tile coordinates. Tiled shows them in the status bar; a pixel position ÷ 32
   gives the tile.
3. **Edit `FOREST`** at the top of `grow_forest.py`:
   - `area`: the box tree points may land in.
   - `shapes`: ellipses whose union is the forest. A wavy edge is added on top.
   - `clearings`: ellipses kept free, such as a yard, the ground in front of a
     door, or a glade.
   - `keep_out`: rectangles nothing may go into, both trees and forest floor.
     Use it for roads.
   - `oaks`: how many broadleaves (`Tree_23`) to plant first.
   - `floor_source`: a box around one forest-floor patch on `Ground_High_Plus`
     to copy. `floor_spots`: where to centre the copies. Every other copy is
     mirrored.
   - `flowers_source` / `flower_patches`: patches on `Ground_Flowers_Mushrooms`
     to scatter, and how many.
4. **Preview:**
   `python build_tools/Forest_Builder/grow_forest.py --preview`
   This writes `forest_game.png` (as in game) and `forest_tiled.png` (as in
   Tiled, tile layers only) to `build_tools/output/forest/` and leaves the map
   alone. Try `--seed N` for a different layout of the same forest.
5. **Write it:** run the same command without `--preview`, with the seed you
   liked.
6. **Check:**
   - The script reloads the map and warns if any door lost its way out.
   - Start the game and look for `Door … has nowhere to step out to` messages.
   - Open the map in Tiled to see the trees.

Running it again over the same area doesn't plant on top of existing trees. It
keeps its distance from every tree already in the map and only fills the gaps.
To redo a forest, undo the map with git (`git checkout assets/tiles/Map1.tmx`)
and run again.

## What it avoids

- Building collision rects, other trees' stems, and water, with a tile to spare.
- The ground in front of any house sprite.
- Within 4 tiles of every door's step, so nobody's way out gets blocked.
- `keep_out` rectangles and `clearings`.

Trees thin out towards the edge of the forest, with more young, small trees
there and a few strays just outside. A forest also blocks walking routes
through it, since walkers hidden behind trees count as blocked in `NavGrid`.
That is intended, but keep forests off paths people need.

## Adding a new tree sprite

1. Paint it into `Trees.png` (the tileset Tiled uses) and save it on its own
   as `assets/map_sprites/trees/Tree_NN.png` (the file the game loads). The
   left edge must be on a tile boundary in `Trees.png`; the bottom should end
   on one or within a few pixels of it.
2. Add `NN: (left_px, top_px, stem_position, stem_thick)` to `SPRITES`.
   `left_px` and `top_px` are where the sprite's top-left corner sits in
   `Trees.png`. On startup the script checks every entry against its PNG and
   stops if one doesn't match.
3. If it is a young or small tree, add it to `YOUNG`.
