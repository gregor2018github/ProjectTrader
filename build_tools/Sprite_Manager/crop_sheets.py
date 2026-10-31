"""The split image a crop's stage sprite is drawn on, its prompt, and cutting the answer out.

Two white cells side by side, as for a new plant (sprite_job.py):

    +----------------+----------------+
    | the reference  |  red frame     |
    |                |  - - - - - - - |  <- how tall the new sprite grows
    |     (plant)    |                |
    +----------------+----------------+

Left the reference (crops.Crop.reference_for()), blown up by whole pixels;
right, inside the red frame, nothing but a dashed red line at the height the
stage grows to, measured from the ground line the reference stands on: the
reference's height times the stage's height over the reference stage's. The
model draws the plant at that stage into the frame, in the reference's style.

The answer's red - frame and line - is taken for background when the sprite
is cut out (extraction.Extraction with drop_red), so the line goes with the
frame; a crop that is pure red itself would lose that red too. The sprite is
scaled back by what brings the reference to its real size, as for a plant.
"""

from dataclasses import dataclass
from pathlib import Path

import pygame

from crops import CROPS_DIR
from extraction import Extraction, find_cells
from images import scaled, trim
from sheets import FRAME_COLOR, FRAME_WIDTH, TARGET_FRAME_COLOR, TARGET_FRAME_WIDTH
from sprite_extraction import SpriteResult, strip_red_frame

LAYOUT = '1x2'
CELL_TARGET = 600            # the taller of reference and new sprite is blown up by whole pixels to about this
CONTENT_SHARE = 0.78         # of the cell's height the taller of the two takes
CELL_MIN_ASPECT = 0.75       # a cell is at least this wide for its height
GROUND_SHARE = 0.07          # of the cell's height below the ground line
GUIDE_WIDTH = 3
GUIDE_DASH = (16, 10)        # (line, gap)
GUIDE_INSET = 18             # from the red frame to the ends of the line
DONE_COLOR = (80, 180, 90)   # the target frame once its sprite is accepted (cards only)

PROMPT_TEMPLATE = """\
The attached picture is a split view for my medieval trading game "Merchant's Rise". Its fields are sown with crops that grow in stages, and every stage is drawn as small pixel-art sprites like the one in the left cell, scattered over the field side by side.

The left cell shows {reference}.

In the right cell, inside the red frame, draw {target}.
- {rule}
- It stands on the ground at the same level as the plant in the left cell, and its highest tips reach up to the dashed red line across the frame, no higher. The line only marks the height: leave it as it is and draw nothing over it.
- About as wide as the plant on the left, so it fills the same patch of field.{notes}

The most important thing is that it looks like it comes from the exact same game as the sprite in the left cell:
- Copy its art style exactly: the same size of pixels (not finer), the same outline, the same way of shading with few shades per colour, the same amount of detail, the same viewing angle and the same light from the same side.
- Plain white background. No soil, shadow or grass around it: only the plant, as in the left cell.

Draw nothing outside the red frame and leave the left cell exactly as it is. Output the full split image.
"""

SAME_PLANT_RULE = ('Keep it the same plant: the stalks rise from the same spots and lean the same way, as they {when}. '
                   'Only what growing changes may change: their height, the size and number of their leaves '
                   'and ears, and their colour as they ripen.')
OTHER_PLANT_RULE = ('Make it a clump of its own, not a copy of the one on the left: other stalks, standing and leaning '
                    'otherwise, but {how}, so the two look like neighbours in one field.')
OTHER_CROP_RULE = ('Only the style and the scale come from the left cell; the plant itself is {crop}{about}, and it '
                   'has to look like it.')


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
    target: pygame.Rect      # the red-framed cell on the surface
    ground: int              # the y both stand on, on the surface
    factor: int
    layout: str = LAYOUT

    @property
    def pose(self):
        return self.crop.pose(self.stage.key, self.variant)

    @property
    def name(self):
        return f'{self.stage.title} {self.variant}'

    def with_result(self, sprite):
        """The sheet with the accepted sprite in the red frame instead of the line, for the cards."""
        sheet = self.surface.copy()
        sheet.fill((255, 255, 255), self.target)
        image = scaled(trim(sprite), self.factor)
        sheet.blit(image, image.get_rect(midbottom=(self.target.centerx, self.ground)))
        pygame.draw.rect(sheet, DONE_COLOR, self.target, TARGET_FRAME_WIDTH)
        return sheet


def target_height(reference, stage):
    """How tall the new sprite is drawn, in the reference sprite's pixels."""
    sprite = trim(pygame.image.load(str(reference.path)).convert_alpha())
    share = stage.height / reference.stage.height if reference.stage.height else 1.0
    return sprite, max(4, round(sprite.get_height() * share))


def build_surface(sprite, height):
    """(surface, target cell, ground y, factor) of the split image."""
    w, h = sprite.get_size()
    tallest = max(h, height)
    factor = max(1, CELL_TARGET // max(w, tallest))
    ch = int(tallest * factor / CONTENT_SHARE)
    cw = max(int(w * factor / CONTENT_SHARE), int(ch * CELL_MIN_ASPECT))
    cells = [pygame.Rect(FRAME_WIDTH + i * (cw + FRAME_WIDTH), FRAME_WIDTH, cw, ch) for i in range(2)]
    surface = pygame.Surface((2 * cw + 3 * FRAME_WIDTH, ch + 2 * FRAME_WIDTH))
    surface.fill(FRAME_COLOR)
    for cell in cells:
        surface.fill((255, 255, 255), cell)
    ground = FRAME_WIDTH + ch - int(ch * GROUND_SHARE)
    image = scaled(sprite, factor)
    surface.blit(image, image.get_rect(midbottom=(cells[0].centerx, ground)))

    target = cells[1]
    pygame.draw.rect(surface, TARGET_FRAME_COLOR, target, TARGET_FRAME_WIDTH)
    y = ground - height * factor
    x, end = target.x + TARGET_FRAME_WIDTH + GUIDE_INSET, target.right - TARGET_FRAME_WIDTH - GUIDE_INSET
    line, gap = GUIDE_DASH
    while x < end:
        pygame.draw.line(surface, TARGET_FRAME_COLOR, (x, y), (min(x + line, end), y), GUIDE_WIDTH)
        x += line + gap
    return surface, target, ground, factor


def build_prompt(crop, stage_index, variant, reference):
    stage = crop.stages[stage_index]
    ref_stage = reference.stage
    own = reference.crop.name == crop.name
    crop_words = crop.title.lower()
    if own:
        ref_words = f'one clump of {crop_words} at the stage "{ref_stage.title}": {ref_stage.description}'
    else:
        ref_words = (f'one clump of {reference.crop.title.lower()}, fully grown, from another field of the game - '
                     f'not the crop to draw')
    stage_words = f'the stage "{stage.title}": {stage.description}' if stage.description else f'the stage "{stage.title}"'
    ref_index = reference.crop.stages.index(ref_stage) if own else len(crop.stages)
    if own and reference.variant == variant:
        when = 'earlier' if ref_index > stage_index else 'further on'
        target = f'the very same clump of {crop_words} {when} in its growth, at {stage_words}'
        rule = SAME_PLANT_RULE.format(when='would have stood there' if when == 'earlier' else 'will stand there')
    elif own:
        same_stage = ref_stage.key == stage.key
        target = f'another clump of {crop_words}, at {stage_words}'
        how = 'just as dense and tall' if same_stage else f'grown as far as {stage.title.lower()} {crop_words} is'
        rule = OTHER_PLANT_RULE.format(how=how)
    else:
        about = f' ({crop.description})' if crop.description else ''
        target = f'a clump of {crop_words}{about}, at {stage_words}'
        rule = OTHER_CROP_RULE.format(crop=crop_words, about=about)
    if stage.height < 0.3:
        notes = '\n- At this height it is only a few small shoots: keep them sparse, with gaps between them.'
    else:
        notes = ''
    return PROMPT_TEMPLATE.format(reference=ref_words, target=target, rule=rule, notes=notes)


def write_sheet(crop, stage_index, variant, others=()):
    """Build, write and return the CropSheet of a stage sprite; None if there is nothing to draw it from.

    Raises:
        pygame.error, OSError: If a file cannot be read or written.
    """
    stage = crop.stages[stage_index]
    reference = crop.reference_for(stage_index, variant, others)
    if stage.bare or reference is None:
        return None
    sprite, height = target_height(reference, stage)
    surface, target, ground, factor = build_surface(sprite, height)
    prompt = build_prompt(crop, stage_index, variant, reference)
    crop.out_dir.mkdir(parents=True, exist_ok=True)
    path = crop.out_dir / sheet_name(crop.pose(stage.key, variant), reference)
    pygame.image.save(surface, str(path))
    path.with_suffix('.txt').write_text(prompt, encoding='utf-8')
    return CropSheet(crop, stage, variant, reference, surface, path, prompt, target, ground, factor)


def sheet_name(pose, reference):
    """sheet_<pose>__<crop>_<stage>_<variant>.png: the reference is in the name, so an answer, which
    records its sheet's name, still knows what it was drawn from once the stage's reference changed."""
    return f'sheet_{pose}__{reference.crop.name}_{reference.stage.key}_{reference.variant}.png'


def reference_path(sheet):
    """The reference sprite a sheet named by sheet_name() was drawn from; None for another name."""
    _, _, rest = Path(sheet).stem.partition('__')
    parts = rest.split('_')
    if len(parts) != 3:
        return None
    crop, stage, variant = parts
    return CROPS_DIR / crop / f'{crop}_{stage}_{variant}.png'


# ---------------------------------------------------------------------------
# From the answer to the stage sprite
# ---------------------------------------------------------------------------

class CropResult(SpriteResult):
    """An answer cut out: the reference from the left cell, the new sprite from the red frame."""

    def __init__(self, path, reference_sprite):
        """
        Raises:
            ValueError, pygame.error: If the cells or the sprites cannot be found.
        """
        self.image = pygame.image.load(str(path)).convert()
        ref_rect, target_rect, _ = find_cells(self.image, LAYOUT)
        self.ref = Extraction(self.image.subsurface(ref_rect).copy())
        cell, _ = strip_red_frame(self.image.subsurface(target_rect).copy())
        self.target = Extraction(cell)   # red is background: the height line goes too
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
            self.result = CropResult(self.path, self.reference)
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
