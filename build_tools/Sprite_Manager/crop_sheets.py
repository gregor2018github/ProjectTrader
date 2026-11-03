"""A crop's stage sprite: its sketch, the split image and prompt made from it, and cutting the answer out.

Every stage sprite is drawn from a reference sprite and a sketch, as a new
plant is drawn from its example (sprite_job.py):

    +----------------+----------------+
    | the reference  |  red frame     |
    |                |  - - - - - - - |  <- how tall the stage grows (on screen only)
    |     (plant)    |     sketch     |
    |  ------------  |  - - - - - - - |  <- the ground line (on screen only)
    +----------------+----------------+

Left the reference, blown up by whole pixels; right, inside the red frame,
the sketch in flat colours, painted with the mouse on the sketch screen
(view_crop_design.py). There two dashed help lines are drawn over it: red at
the height the stage grows to, measured from the ground line the reference
stands on (the reference's height times the stage's height over the
reference stage's), and grey along that ground line. They are not in the
image the model gets, which shows only the reference and the sketch.

What the reference is decides the prompt (mode_of()):

* GROW: the same crop at another stage, e.g. the ripe one for a smaller
  plant. The model draws the crop at this stage, grown as far as it is.
* VARIATION: another variant of the same stage. The model draws another
  clump just as far grown, a neighbour in the same field.
* OTHER_CROP: another crop's ripe sprite, for a crop with no sprite of its
  own yet; only its style and scale count.

The reference of a stage sprite is chosen on the sketch screen, else it is
crops.Crop.reference_for(). Each stage sprite keeps one sketch per reference
it was drawn from, so trying another reference loses nothing:
<output>/sketches/<pose>__<reference>.png, beside sketches.json with the
colour in hand, the colours painted with and the reference chosen for each
stage sprite.

The answer's new sprite is cut out of the red frame as for a plant
(sprite_extraction.py): the frame is cut off its edges and red stays, since
a crop may be red itself. Answers to the sheets made before the sketches
(sheet_*.png) had a red line across the frame, so for them red is taken for
background. The sprite is scaled back by what brings the reference to its
real size.
"""

import json
from dataclasses import dataclass
from pathlib import Path

import pygame

from crops import CROPS_DIR, CROPS_OUTPUT, Reference
from extraction import Extraction, find_cells
from images import scaled, trim
from sheets import FRAME_COLOR, FRAME_WIDTH, TARGET_FRAME_COLOR, TARGET_FRAME_WIDTH
from sprite_extraction import SpriteResult, strip_red_frame
from sprite_job import SketchCanvas, colour_name, hex_colour

LAYOUT = '1x2'
CELL_TARGET = 600            # the taller of reference and new sprite is blown up by whole pixels to about this
CONTENT_SHARE = 0.78         # of the cell's height the taller of the two takes
CELL_MIN_ASPECT = 0.75       # a cell is at least this wide for its height
GROUND_SHARE = 0.07          # of the cell's height below the ground line
GUIDE_WIDTH = 3
GUIDE_DASH = (16, 10)        # (line, gap)
GUIDE_INSET = 18             # from the red frame to the ends of a line
GROUND_GUIDE_COLOR = (150, 150, 150)
DONE_COLOR = (80, 180, 90)   # the target frame once its sprite is accepted (cards only)
SPARSE_BELOW = 0.3           # a stage lower than this share of the ripe height is only a few shoots

SKETCH_DIR = 'sketches'      # under a crop's output
SKETCH_STATE = 'sketches.json'
SHEET_PREFIX = 'sketch'      # sketch_<pose>__<reference>.png; the sheets before the sketches were sheet_*
OLD_SHEET_PREFIX = 'sheet'
CLEAR = (0, 0, 0, 0)
DEFAULT_COLOUR = (90, 140, 50)

GROW, VARIATION, OTHER_CROP = 'grow', 'variation', 'other crop'
MODE_TITLES = {GROW: 'Grow from another stage',
               VARIATION: 'Variation of this stage',
               OTHER_CROP: 'Style of another crop'}

PROMPT_TEMPLATE = """\
The attached picture is a split view for my medieval trading game "Merchant's Rise". Its fields are sown with crops that grow in stages, and every stage is drawn as small pixel-art sprites like the one in the left cell, scattered over the field side by side.

The left cell shows {reference}.

Inside the red frame in the right cell is a rough sketch in flat colours of {target}. Turn the sketch into that finished sprite, drawn over it so that nothing of the sketch is left:
- Follow the sketch closely: the plant takes its outline, size and place in the frame, with gaps where the sketch leaves the paper white. It stands on the ground at the same level as the plant in the left cell. Its edges may be more ragged and detailed than the brush strokes of the sketch.
- {colour_rule}
- {rule}{notes}

The most important thing is that it looks like it comes from the exact same game as the sprite in the left cell:
- Copy its art style exactly: the same size of pixels (not finer), the same outline, the same way of shading with few shades per colour, the same amount of detail, the same viewing angle and the same light from the same side.
- Plain white background. No soil, shadow or grass around it: only the plant, as in the left cell.

Draw nothing outside the red frame and leave the left cell exactly as it is. Output the full split image.
"""

GROW_RULE = ('It is the same crop as in the left cell, only {when} in its growth: its leaves, stalks and ears are '
             'drawn like those on the left, changed only by what growing changes - their height, the size and '
             'number of the leaves and ears, and their colour as they ripen.')
SAME_CLUMP = ' It is even the same clump: as far as the sketch allows, its stalks rise from the same spots.'
VARIATION_RULE = ('It is another clump of the same crop at the very same stage, for the same field: just as far '
                  'grown, with leaves, stalks and ears drawn like those on the left, but a clump of its own, shaped '
                  'as the sketch is, not a copy of the one on the left. The two must look like neighbours in one '
                  'field.')
OTHER_CROP_RULE = ('Only the style and the scale come from the left cell; the plant itself is {crop}{about}, and it '
                   'has to look like it.')
SPARSE_NOTE = '\n- At this height it is only a few small shoots: keep them sparse, with gaps between them.'
ONE_COLOUR_RULE = ('The flat colour of the sketch, {name} ({hex}), is the plant\'s main colour. Shade it with darker '
                   'and lighter tones of that colour.')
COLOURS_RULE = ('The sketch is painted in flat colours: {listed}. They show which part goes where: leaves, stalks, '
                'ears and flowers each take the colour sketched where they are. Shade every colour with darker and '
                'lighter tones of itself.')


# ---------------------------------------------------------------------------
# References
# ---------------------------------------------------------------------------

def reference_key(reference):
    """'wheat_ripe_1': how a reference is named in file names and sketches.json."""
    return f'{reference.crop.name}_{reference.stage.key}_{reference.variant}'


def mode_of(crop, stage, reference):
    """GROW, VARIATION or OTHER_CROP: what drawing `crop` at `stage` from `reference` is."""
    if reference.crop.name != crop.name:
        return OTHER_CROP
    return VARIATION if reference.stage.key == stage.key else GROW


def reference_options(crop, stage_index, variant, others=()):
    """{mode: [Reference]} of every sprite a stage sprite can be drawn from, the modes that have one.

    Growing: this crop's sprites at the other stages, the ripe end first and,
    within a stage, the same variant first. A variation: the stage's other
    variants. Another crop: the other crops' ripe sprites.
    """
    stage = crop.stages[stage_index]
    stages = sorted((s for s in crop.growing if s.key != stage.key), key=crop.stages.index, reverse=True)
    variants = sorted(range(1, crop.variants + 1), key=lambda v: (v != variant, v))
    options = {
        GROW: [Reference(crop, s, v) for s in stages for v in variants if crop.has(s.key, v)],
        VARIATION: [Reference(crop, stage, v) for v in variants if v != variant and crop.has(stage.key, v)],
        OTHER_CROP: [Reference(other, other.ripe, v) for other in others if other.name != crop.name
                     for v in range(1, other.variants + 1) if other.has(other.ripe.key, v)],
    }
    return {mode: refs for mode, refs in options.items() if refs}


def load_state(crop):
    """The crop's sketches.json: {'colour', 'palette', 'references': {pose: reference key}}."""
    try:
        data = json.loads((crop.out_dir / SKETCH_DIR / SKETCH_STATE).read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(crop, state):
    folder = crop.out_dir / SKETCH_DIR
    folder.mkdir(parents=True, exist_ok=True)
    (folder / SKETCH_STATE).write_text(json.dumps(state, indent=1) + '\n', encoding='utf-8')


def chosen_reference(crop, stage_index, variant, others=()):
    """The Reference chosen for a stage sprite on the sketch screen, if it is still there; else the default."""
    pose = crop.pose(crop.stages[stage_index].key, variant)
    key = load_state(crop).get('references', {}).get(pose)
    if key:
        for refs in reference_options(crop, stage_index, variant, others).values():
            for reference in refs:
                if reference_key(reference) == key:
                    return reference
    return crop.reference_for(stage_index, variant, others)


def choose_reference(crop, pose, reference):
    """Keep the reference a stage sprite is drawn from.

    Raises:
        OSError: If sketches.json cannot be written.
    """
    state = load_state(crop)
    state.setdefault('references', {})[pose] = reference_key(reference)
    save_state(crop, state)


def crop_sketch(crop, stage_index, variant, others=(), reference=None):
    """The CropSketch of a stage sprite from `reference` (else the chosen one); None if there is none.

    Raises:
        pygame.error, OSError: If a sprite cannot be read.
    """
    stage = crop.stages[stage_index]
    if stage.bare:
        return None
    reference = reference or chosen_reference(crop, stage_index, variant, others)
    return CropSketch(crop, stage_index, variant, reference) if reference else None


def reference_path(sheet):
    """The reference sprite a sheet named by CropSketch.sheet_path was drawn from; None for another name."""
    _, _, rest = Path(sheet).stem.partition('__')
    parts = rest.split('_')
    if len(parts) != 3:
        return None
    crop, stage, variant = parts
    return CROPS_DIR / crop / f'{crop}_{stage}_{variant}.png'


# ---------------------------------------------------------------------------
# The sketch and its sheet
# ---------------------------------------------------------------------------

@dataclass
class CropSheet:
    """One stage sprite's split image and prompt, shaped like a sheets.FrameSheet for the API and the answers."""

    crop: object
    stage: object
    variant: int
    reference: object        # crops.Reference
    surface: pygame.Surface
    path: Path
    prompt: str
    sketched: bool = True    # False: only the reference, nothing to send yet
    layout: str = LAYOUT

    @property
    def pose(self):
        return self.crop.pose(self.stage.key, self.variant)

    @property
    def name(self):
        return f'{self.stage.title} {self.variant}'


class CropSketch(SketchCanvas):
    """The sketch of one stage sprite drawn from one reference, kept in the crop's output."""

    recent_folder = CROPS_OUTPUT   # the colours used last, shared by every crop

    def __init__(self, crop, stage_index, variant, reference):
        """
        Raises:
            pygame.error, OSError: If the reference cannot be read.
        """
        self.crop = crop
        self.stage_index = stage_index
        self.stage = crop.stages[stage_index]
        self.variant = variant
        self.reference = reference
        self.mode = mode_of(crop, self.stage, reference)
        self.example = trim(pygame.image.load(str(reference.path)).convert_alpha())
        self.height = self._target_height()
        self.factor, self.cell_size, self.ground = self._geometry()
        state = load_state(crop)
        self.colour = tuple(state.get('colour', DEFAULT_COLOUR))
        self.palette = [tuple(c) for c in state.get('palette', [self.colour])]
        self.sketch = self._load_sketch()
        self._start_canvas()

    # --- where it lives -----------------------------------------------------

    @property
    def pose(self):
        return self.crop.pose(self.stage.key, self.variant)

    @property
    def sketch_path(self):
        return self.crop.out_dir / SKETCH_DIR / f'{self.pose}__{reference_key(self.reference)}.png'

    @property
    def sheet_path(self):
        """sketch_<pose>__<crop>_<stage>_<variant>.png: the reference is in the name, so an answer, which
        records its sheet's name, still knows what it was drawn from once the stage's reference changed."""
        return self.crop.out_dir / f'{SHEET_PREFIX}_{self.pose}__{reference_key(self.reference)}.png'

    def source_label(self):
        """'Ripe 1', or 'Barley (another crop)'."""
        ref = self.reference
        if self.mode == OTHER_CROP:
            return f'{ref.crop.title} (another crop)'
        return f'{ref.stage.title} {ref.variant}'

    def mode_label(self):
        """'grown from Ripe 1', 'variation of Young 2', 'in the style of Barley (another crop)'."""
        words = {GROW: 'grown from', VARIATION: 'variation of', OTHER_CROP: 'in the style of'}[self.mode]
        return f'{words} {self.source_label()}'

    def save(self):
        """The sketch, and the colours in sketches.json."""
        state = load_state(self.crop)
        state['colour'] = list(self.colour)
        palette = [tuple(c) for c in state.get('palette', [])]
        palette += [c for c in self.palette if c not in palette]
        state['palette'] = [list(c) for c in palette]
        save_state(self.crop, state)
        pygame.image.save(self.sketch, str(self.sketch_path))

    def _load_sketch(self):
        sketch = pygame.Surface(self.cell_size, pygame.SRCALPHA)
        sketch.fill(CLEAR)
        try:
            image = pygame.image.load(str(self.sketch_path)).convert_alpha()
        except (pygame.error, OSError):
            return sketch
        if image.get_size() != self.cell_size:   # the stage's height changed the cell
            image = pygame.transform.scale(image, self.cell_size)
        sketch.blit(image, (0, 0))
        return sketch

    # --- the split image ------------------------------------------------------

    def _target_height(self):
        """How tall the new sprite grows, in the reference sprite's pixels."""
        ref_stage = self.reference.stage
        if self.mode == OTHER_CROP:
            share = self.stage.height   # the other crop's ripe plant stands for this crop's ripe one
        else:
            share = self.stage.height / ref_stage.height if ref_stage.height else 1.0
        return max(4, round(self.example.get_height() * share))

    def _geometry(self):
        """(factor, cell size, ground line in cell coordinates)."""
        w, h = self.example.get_size()
        tallest = max(h, self.height)
        factor = max(1, CELL_TARGET // max(w, tallest))
        ch = int(tallest * factor / CONTENT_SHARE)
        cw = max(int(w * factor / CONTENT_SHARE), int(ch * CELL_MIN_ASPECT))
        return factor, (cw, ch), ch - int(ch * GROUND_SHARE)

    def cells(self):
        """(reference cell, sketch cell) on the sheet."""
        cw, ch = self.cell_size
        return [pygame.Rect(FRAME_WIDTH + i * (cw + FRAME_WIDTH), FRAME_WIDTH, cw, ch) for i in range(2)]

    def build_sheet_size(self):
        cw, ch = self.cell_size
        return 2 * cw + 3 * FRAME_WIDTH, ch + 2 * FRAME_WIDTH

    def build_sheet(self, with_sketch=True):
        """The split image: the reference, and the sketch in the red frame. No help lines."""
        ref_cell, sketch_cell = self.cells()
        sheet = pygame.Surface(self.build_sheet_size())
        sheet.fill(FRAME_COLOR)
        sheet.fill((255, 255, 255), ref_cell)
        sheet.fill((255, 255, 255), sketch_cell)
        image = scaled(self.example, self.factor)
        sheet.blit(image, image.get_rect(midbottom=(ref_cell.centerx, ref_cell.y + self.ground)))
        if with_sketch:
            sheet.blit(self.sketch, sketch_cell)
        pygame.draw.rect(sheet, TARGET_FRAME_COLOR, sketch_cell, TARGET_FRAME_WIDTH)
        return sheet

    def draw_guides(self, sheet):
        """The dashed lines of the ground and of the height the stage grows to, across the sketch cell."""
        cell = self.cells()[1]
        ground = cell.y + self.ground
        self._dashed(sheet, cell, ground, GROUND_GUIDE_COLOR)
        self._dashed(sheet, cell, ground - self.height * self.factor, TARGET_FRAME_COLOR)

    @staticmethod
    def _dashed(sheet, cell, y, colour):
        x = cell.x + TARGET_FRAME_WIDTH + GUIDE_INSET
        end = cell.right - TARGET_FRAME_WIDTH - GUIDE_INSET
        line, gap = GUIDE_DASH
        while x < end:
            pygame.draw.line(sheet, colour, (x, y), (min(x + line, end), y), GUIDE_WIDTH)
            x += line + gap

    def with_result(self, sprite):
        """The sheet with the accepted sprite in the frame instead of the sketch, for the cards."""
        sheet = self.build_sheet(with_sketch=False)
        cell = self.cells()[1]
        image = scaled(trim(sprite), self.factor)
        sheet.blit(image, image.get_rect(midbottom=(cell.centerx, cell.y + self.ground)))
        pygame.draw.rect(sheet, DONE_COLOR, cell, TARGET_FRAME_WIDTH)
        return sheet

    # --- the prompt -----------------------------------------------------------

    def colour_rule(self):
        colours = self.prompt_colours()
        if len(colours) == 1:
            return ONE_COLOUR_RULE.format(name=colour_name(colours[0]), hex=hex_colour(colours[0]))
        return COLOURS_RULE.format(listed=', '.join(f'{colour_name(c)} ({hex_colour(c)})' for c in colours))

    def prompt(self):
        crop, stage, ref = self.crop, self.stage, self.reference
        crop_words = crop.title.lower()
        stage_words = f'the stage "{stage.title}": {stage.description}' if stage.description \
            else f'the stage "{stage.title}"'
        about = f' ({crop.description})' if crop.description else ''
        if self.mode == OTHER_CROP:
            reference = (f'one clump of {ref.crop.title.lower()}, fully grown, from another field of the game - '
                         f'not the crop to draw')
            target = f'a clump of {crop_words}{about}, at {stage_words}'
            rule = OTHER_CROP_RULE.format(crop=crop_words, about=about)
        else:
            reference = f'one clump of {crop_words} at the stage "{ref.stage.title}": {ref.stage.description}'
            if self.mode == VARIATION:
                target = f'another clump of {crop_words}, at the same stage'
                rule = VARIATION_RULE
            else:
                when = 'earlier' if crop.stages.index(ref.stage) > self.stage_index else 'further on'
                target = f'the same crop, {crop_words}, {when} in its growth, at {stage_words}'
                rule = GROW_RULE.format(when=when) + (SAME_CLUMP if ref.variant == self.variant else '')
        notes = SPARSE_NOTE if stage.height < SPARSE_BELOW else ''
        return PROMPT_TEMPLATE.format(reference=reference, target=target, colour_rule=self.colour_rule(),
                                      rule=rule, notes=notes)

    def sheet(self, write=True):
        """The CropSheet as the sketch is now; written to disk with its prompt if `write` and sketched.

        Raises:
            pygame.error, OSError: If it cannot be written.
        """
        surface = self.build_sheet()
        sketched = self.has_sketch()
        prompt = self.prompt() if sketched else ''
        path = self.sheet_path
        if write and sketched:
            self.save()
            pygame.image.save(surface, str(path))
            path.with_suffix('.txt').write_text(prompt, encoding='utf-8')
        return CropSheet(self.crop, self.stage, self.variant, self.reference, surface, path, prompt, sketched)

    def write_sheet(self):
        """For the sketch screen: the sheet written as it is now."""
        return self.sheet()


# ---------------------------------------------------------------------------
# From the answer to the stage sprite
# ---------------------------------------------------------------------------

class CropResult(SpriteResult):
    """An answer cut out: the reference from the left cell, the new sprite from the red frame."""

    def __init__(self, path, reference_sprite, drop_red=False):
        """
        Args:
            drop_red: Take red for background too, for an answer to a sheet with a red height line.

        Raises:
            ValueError, pygame.error: If the cells or the sprites cannot be found.
        """
        self.image = pygame.image.load(str(path)).convert()
        ref_rect, target_rect, _ = find_cells(self.image, LAYOUT)
        self.ref = Extraction(self.image.subsurface(ref_rect).copy())
        cell, _ = strip_red_frame(self.image.subsurface(target_rect).copy())
        self.target = Extraction(cell, drop_red=drop_red)
        if self.ref.bbox is None:
            raise ValueError('No plant found in the left cell.')
        if self.target.bbox is None:
            raise ValueError('Nothing drawn in the red frame.')
        self.example = reference_sprite
        self.build()


class CropDetail:
    """One answer and the stage sprite accepting it would make."""

    def __init__(self, crop, entry):
        """
        Raises:
            pygame.error, OSError: If the answer's image cannot be read.
        """
        self.crop = crop
        self.entry = entry
        self.path = crop.out_dir / entry.image
        image = pygame.image.load(str(self.path))
        entry.width, entry.height = image.get_size()
        self.reference = None
        self.result = None
        self.error = ''
        source = reference_path(entry.sheet)
        try:
            if source is None:
                raise ValueError(f'the sheet {entry.sheet} does not say what it was drawn from')
            self.reference = trim(pygame.image.load(str(source)).convert_alpha())
            old_sheet = Path(entry.sheet).name.startswith(OLD_SHEET_PREFIX + '_')
            self.result = CropResult(self.path, self.reference, drop_red=old_sheet)
        except Exception as exc:  # a reference gone, or cell detection and extraction failing
            self.error = f'Cannot use this image: {exc}'
        self.preview = None   # (rect, factor) of the sprite where it was last drawn

    def toggle_hole(self, pos):
        """Click on the preview: switch an enclosed white area see-through, or back."""
        if not (self.result and self.preview):
            return
        rect, factor = self.preview
        if not rect.collidepoint(pos):
            return
        point = self.result.output_to_cell(((pos[0] - rect.x) / factor, (pos[1] - rect.y) / factor))
        target = self.result.target
        if target.surface.get_rect().collidepoint(point) and target.toggle_hole(point):
            self.result.build()
