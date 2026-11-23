# Figure Restyler

Makes a new townsperson out of an existing one's frames by code, no image
model: the walk stays exactly the original's, the looks change.

`konrad.py` turns Bartholomew (`middling_bartholomew`) into Konrad
(`middling_konrad`):

```bash
python build_tools/Figure_Restyler/konrad.py --preview out.png   # contact sheet only
python build_tools/Figure_Restyler/konrad.py                     # writes the 28 frames
```

How it works:

1. `segment.py` splits every frame into materials (skin, eyes, cap, coat,
   fur collar, buckle, hair, belt, boots, outline) by colour, and by place
   where colour cannot tell (cap above the collar, coat below; hair, belt and
   boots by height).
2. The body is repainted material by material through new colour ramps, by
   each pixel's brightness, so the original shading and texture stay. The
   collar becomes a woollen cape with a dagged hem, the coat gets a hem band
   and cuffs, and outlines take the tint of what they border.
3. The head is drawn once per direction on the standing frame: the cap taken
   off, a bowl-cut dome of hair drawn on the sprites' 4-pixel grid, a beard
   over the lower face. On every frame, Bartholomew's head is found by the
   shift that best matches his standing head, removed, and the new head is
   pasted at that shift. The heads are rigid in his walk cycles, so they
   follow the bob exactly. Right is left mirrored, as it is in his frames.

For another variant, copy `konrad.py` and change `PAL` (the colours), `HEADS`
(the hair dome's centre, size and fringe per direction), and the folder and
file names. A source figure other than Bartholomew needs its own colour
thresholds in `segment.py`.
