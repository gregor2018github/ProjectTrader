# Harbor Builder

Lays the harbour's piers and quay onto `assets/tiles/Map1.tmx` as ground tiles, painted
by code: a timber jetty (A) off the west shore, and the stone south quay with the two
stone piers (B, C) running out from it, paved as one surface.

```bash
python build_tools/Harbor_Builder/lay_piers.py --sheet     # the pieces and a sample pier of each material
python build_tools/Harbor_Builder/lay_piers.py --preview   # render the piers, map left alone
python build_tools/Harbor_Builder/lay_piers.py             # write (close Tiled first)
```

Pictures go to `build_tools/output/piers/`. Every run rebuilds the `harbor_piers`
tileset from nothing and lays everything again, so it can be run any number of
times; two runs write the same bytes. What it changes on the map it first notes
in `underlay.json` (each touched cell's tile per layer, as it was before the tool
ever ran) and puts back at the start of every run, so the ground under the paving
(a road's ragged edge) is never lost. Commit `underlay.json` with the map.

## How it works

- `pier_materials.py` paints the **pieces**, each one tile (32 px): wood deck
  middle (4 variants), edge beam (3), end header (2), corner (1); stone cobbles
  (4), kerb (4), corner (2); and the front faces (`wood_face`, `stone_face`). A
  piece is colour, a height map and what each pixel is (cobble, flagstone, board,
  beam, joint). The variants of a kind share their borders, so they mix without
  seams.
- `lay_piers.py` lays them per pier in the pieces' own orientation (land end
  left, water end right), then:
  - gives every connected stone and board its own colour from the pier's seed
    (bricks among the cobbles, red kerbs, pale or dark boards);
  - frays the land end onto the grass;
  - adds wet wood, salt and tar, or the cart track, puddles and damp patches;
  - turns it the way the pier points and lights it from the height map (upper
    left, mostly overhead, like the sprites);
  - adds the front face on a south edge over water, a 1 px lip on the other
    water edges, and a 6 px shadow on the water.
- The canvas is cut into tiles by `Forest_Builder/floor_painter.FloorPainter`,
  as `paint_ground.py` does, onto `Ground_High`. The game draws that layer over
  the animated water, and the Placing Helper shows it as is. The grass fringe
  tiles that hung over the water round a pier are taken off that layer.

## The quay

`stone_paving.py`: a `Paving` (`PAVINGS`) is the land within `depth` tiles (3) of the
water inside its `quay` box, plus its `piers`, paved whole. Each cell's piece comes
from where the water is round it: a kerb with its outer side to the water, an outer
corner (a pier's tip), an inner corner where the kerb turns in (a pier meeting the
quay), cobbles elsewhere. Away from the water it frays into the grass stone by
stone; a kerb running out of the paving ends on a joint. The water cells beside it
lose the shore's grass: their fringe tiles on `Ground_High` come off and their bank
tiles in `Ground_Mid` become open water (still water to the game). The piers' cart
tracks (`tracks`) fade out on the quay. The stone is kept quiet on purpose: it is
ground, not a building.

## A new pier

A stone pier off the quay: add its box to the paving's `piers` (and a track if you
like). A wooden one, or a stone one standing alone, is a `Pier` in `PIERS`:

```python
Pier("D_timber_landing", "wood", (x0, y0, x1, y1), root="N", seed=41)
```

- **box:** the land cells the Water polygon goes round, in tiles, x1/y1 exclusive.
  At least 3 tiles wide.
- **root:** the side joined to the land (`W`, `E`, `S`, `N`).
- **material:** `"wood"` or `"stone"` (`fender=True` hangs a timber fender on a
  stone face).

Only south edges over water show a front face. Change the look in the palettes
and constants at the top of `pier_materials.py` and `lay_piers.py`.
