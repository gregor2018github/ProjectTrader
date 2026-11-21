---
name: paint-pixel-sprite
description: Paint a map sprite for Merchant's Rise by code, pixel by pixel, instead of asking the image model, e.g. fence and wall pieces (build_tools/Sprite_Manager/stone_wall_painter.py) and gates, and later other regular, repetitive sprites (paving, railings, crates, roofs' details). Also how to design and lay the fences the user drew in the Placing Helper's fence mode (build_tools/Placing_Helper/fence_plans.json). Use when the user asks to build, design or place the fences they drew, when the user asks Claude to draw/design/paint a sprite itself, when Gemini's answers for a sprite keep coming back crooked, in perspective or inconsistent, or when a new fence/wall style should get painted pieces.
---

# Paint a sprite by code

Gemini is good at organic, one-off things (people, trees, houses). It is bad at
long, regular, exactly aligned ones: walls drift into perspective, courses
wander, pieces don't join. Those are better painted here, deterministic and on
the exact raster. The working example is
`build_tools/Sprite_Manager/stone_wall_painter.py` (the churchyard wall); read
it first and extend it rather than starting over.

## Fences the user drew (Placing Helper, fence mode)

The user draws fences in the Placing Helper (W) and leaves them in
`build_tools/Placing_Helper/fence_plans.json`. Per fence: `material`,
`description` (how it is to look, in their words: follow it), `plan` (the
pieces between corners and gates, `[orientation, tiles, x, y]` from the
top-left post), `gate_plan` and `origin_px` (that post's foot). To build one:

1. Make a style for it with the Sprite Manager's fences code
   (`fences.create_style`, or a folder `assets/map_sprites/houses/fences/<style>/`
   with a `fence.json`: material, `posts_every`, height, the description, the
   `lengths` the plan needs per orientation, and the `plan` copied over).
2. Paint every piece the plan names (below; `stone_wall_painter.py` for a stone
   wall with pillars at its ends, `wood_fence_painter.py` for a wooden rail
   fence, a painter of its own for anything else), preview the whole plan laid
   out, show it to the user. Check the plan is closed where it should be: a
   run the user forgot to draw (a missing corner side) leaves a gap; add it to
   the style's plan and say so.
3. A gate gap of 2 tiles in a row gets a `Gate`; paint its three pictures
   (shut, open down, open up) like `iron_gate_painter.py`. A gap in a vertical
   run has no gate yet (the game's Gate only swings up or down the picture).
4. Lay it: `python build_tools/Sprite_Manager/place_fence.py <style> <origin x> <origin y>
   --name <Name> [--gate <pictures>]` (`--dry-run` first), render the spot
   with the place-building skill's `render`, load the map headless, and check
   the gates on the `NavGrid`.
5. Take the fence out of `fence_plans.json` once it is on the map (or ask).

## Workflow

1. **Measure a reference the user likes, don't guess.** Load it with pygame and
   print, per row, the first/last opaque x and the colour at a couple of
   columns; per column, the first/last opaque y. That gives the heights (coping
   top, course and mortar rows, base line), widths and the palette. Write those
   numbers down as constants relative to a geometric anchor (for fences: the
   run's foot line, `Raster.start`), never as absolute pixels.
2. **Paint on the real canvas.** Use the same size and anchor the game and the
   Sprite Manager use (`Piece.raster.pixels`; `Piece.save` writes on it). Then
   pieces line up by construction: no cutting, no nudging.
3. **Preview at 1x laid out as in the game, then crop at 5x.** Compose the
   pieces as placed (the style's `plan`) and sort them as the game sorts
   buildings: lower bottom edge drawn later. Look at the whole at 2x for
   proportion, and at the corners/joins at 5x for pixel faults. Use the Read
   tool on the PNG to see it.
4. **Write with backups**: `--write` copies what it replaces to
   `build_tools/output/fences/<style>/replaced/`. Check that a second run is
   byte-identical (seed from the style and piece name with `zlib.crc32`, never
   `hash()`, which changes per process) and delete backups of your own output.
5. **Check the tool's own view**: `view_fence.yard(style)` renders what the
   user sees under "As planned"; render it headless (SDL dummy driver) and look.

## Tricks that make it look hand-drawn

- **Colour = palette colour × shade.** Keep a small palette (stone, coping,
  pillar, mortar, outline, an accent such as lichen) and get every pixel by
  multiplying with a factor. Light from the upper left: top row of a stone
  ×1.10, bottom row ×0.94, left column ×1.06, right ×0.90.
- **Per-element variation, small.** Each stone gets its own brightness
  (×0.92 to 1.06) and a warm/cool tint of a few levels (`jitter`); about 1 in 8
  is darker (weathered). More than that reads as noise.
- **Speckle sparingly**: ~5 % of pixels ×0.92, ~3 % ×1.05. It gives stone grain
  without blurring the joints.
- **Stagger courses**: random joint spacing within a range (13 to 20 px for
  ashlar), and push a joint that comes within 3 px of one in the course above.
- **Ambient occlusion by depth**: the row under an overhang (coping, cap) in
  shadow (×0.70, lightening downwards); courses darker towards the ground
  (×1.0 to 0.87). A dark outline along the ground line seats it.
- **Cast shadows**: what stands proud (a pillar) darkens the wall to its right
  with a 4 px falloff (×0.74 to 0.93). Do it before painting the proud thing.
  A free-standing run casts a few pixels of translucent dark on the grass
  (alpha 62, 46, 30).
- **Small details sell it**: a chipped corner (one mortar pixel), a 3-pixel
  lichen spot on the lowest courses, a lit edge on the left of each slab, a
  shaded arris on the right.
- **Noble = proud pillars**: plinth wider than the shaft, a cap overhanging it,
  the shadow under the cap, a low pyramid on top lit on its left half.

## The game's projection (no perspective!)

The map is drawn from above at one fixed slant, with no vanishing point:

- An east–west wall shows its **front face** (courses) under a thin band of its
  top (the coping).
- A north–south wall shows **only its top**: a straight band of even width
  running down the picture, plus at most a 2 to 3 px shaded strip of side face
  for readability. Its top is drawn `TOP_TO_GROUND` (34 px) above the ground
  under it.
- Something standing south of something else is in front of it: a vertical
  wall starting at a corner pillar comes out of the pillar's front face and is
  drawn over it. Keep the band narrower than the pillar so the pillar's edges
  still show.
- Where a vertical wall goes **behind** the pillar at its far end, stop it
  where the pillar's cap begins and leave out the pixels of the cap's pyramid
  (`Canvas.skip`). Then it looks right whichever sprite the game draws last,
  since pieces whose bottom edges tie are sorted by x only.

## Things that move: the gate

`build_tools/Sprite_Manager/iron_gate_painter.py` paints the churchyard's iron
gate, shut and open. An open leaf is the flat leaf turned about its hinge:
each column `u` goes to `x = hinge ± u·cos θ` and down (towards the viewer)
or up the picture by `u·sin θ`, since a step north or south on the ground is
the same step in the picture. Lay the farther columns first. A leaf only
half open (50°) still stands in the gateway and the walker passing through
overlaps it: check the room left against the player's 32 px. The churchyard
gate swings 80°, nearly back against the wall, so each leaf reaches 4 px in
and shows as a thin dark sliver, which reads right from this angle. Leave
ornament (rings, short bars) off a slanted leaf. Don't span a gateway
overhead (an arch, a sign): it is drawn over whoever walks under it as soon
as they are a step behind the wall line, and cuts them off.

## Wooden fences

`wood_fence_painter.py` paints the field fence (`field_fence`, round the field
south-west of town) and its farm gate (`--gate field_gate`, two leaves of three
rails and a brace, swung like the iron gate with its `place_leaf`). Posts stand
evenly about every 2 tiles, so any length works; the corner and gate posts are
the horizontal pieces' end posts, upright at exactly `POST_TOP`, so the
vertical pieces and gates know where they are. Seen from above, a north-south
run's two rails fall on one line: draw them as one narrow band (lit top, a
pixel of side face, its shadow east of it on the grass) and the posts **over**
it, whole, or the run reads as a plank. Keep it off the corner posts' pixels at
both ends (`Canvas.skip`). "Not always perfect" is a few small faults, not
many: posts ±2 px tall, 1 in 5 leaning a pixel, rails sagging or askew by one,
about 1 in 14 slipped off its nail at one end, cracks and knots, some boards
weathered grey.

## A gate in a gap that is already there

`board_gate_painter.py` hangs gates in openings of walls that were drawn by
hand (the sheep's yard): measure each gap from the sprites' opaque pixels and
the objects' collision boxes (stone edge to stone edge, the wall's foot row),
cut the gate to it on a canvas of whole tiles, let each leaf reach one pixel
under the stone at both ends and sort the gate a pixel or two before the walls
(`Sort_up_pixel`), so the stone is drawn over the joint. Render it shut and
open (copy the open picture over the shut one for the render, then put it
back) with a figure in the gateway, zoomed 4x, before calling it done.

## Adding a new kind

Give it a `paint_<kind>(raster, rng, pal)` next to the wall's, sharing
`Canvas`, `shade`, `jitter`, `_speckle` and `_joints`, and select it in
`paint()` by the style's material. Metal railings or wooden fences follow the
same rules: measure a reference, paint on the raster, post centres from
`raster.posts()`.
