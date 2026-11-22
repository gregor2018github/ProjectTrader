# Harbor Builder

Lays the harbour's piers onto `assets/tiles/Map1.tmx` as ground tiles, painted by code:
a timber jetty (A) and two paved stone piers (B, C).

```bash
python build_tools/Harbor_Builder/lay_piers.py --sheet     # the pieces and a sample pier of each material
python build_tools/Harbor_Builder/lay_piers.py --preview   # render the piers, map left alone
python build_tools/Harbor_Builder/lay_piers.py             # write (close Tiled first)
```

Pictures go to `build_tools/output/piers/`. Every run rebuilds the `harbor_piers`
tileset from nothing and lays every pier again, so it can be run any number of
times; two runs write the same bytes.

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

## A new pier

Add a `Pier` to `PIERS`:

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
