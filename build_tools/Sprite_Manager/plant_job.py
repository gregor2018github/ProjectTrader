"""Making a new plant: the job, its split image and its prompt.

A job starts from a plant sprite clicked in the overview, the example. Its
folder build_tools/output/plants/<job>/ holds everything about it:

    job.json      the kind, the optional subcategory ("oak"), the colour,
                  the example's name, and which answers became which sprite
    example.png   the example, as it was when the job started
    sketch.png    the rough shape drawn with the mouse, as a mask
    sheet.png     the split image sent to the model, and prompt.txt with it
    review.json   the answers, as for the humans (pose_review.py)

The split image is two square white cells side by side: the example blown up
by whole pixels on the left, and on the right, inside a red frame, the sketch
filled flat with the chosen colour, at the same scale. The model is asked to
draw a plant of the kind in the red frame, shaped like the sketch and mainly
in its colour, in the example's style.
"""

import colorsys
import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import pygame

from images import scaled
from plants import KINDS_BY_KEY, PLANT_OUTPUT
from sheets import FRAME_COLOR, FRAME_WIDTH, TARGET_FRAME_COLOR, TARGET_FRAME_WIDTH

JOB_FILE = 'job.json'
EXAMPLE_FILE = 'example.png'
SKETCH_FILE = 'sketch.png'
SHEET_FILE = 'sheet.png'
PROMPT_FILE = 'prompt.txt'
POSE = 'plant'                  # what the answers are booked under in review.json

CELL_TARGET = 640               # the example is blown up by whole pixels to about this size
CELL_MARGIN = 0.1               # white room around the example, a share of the cell
DEFAULT_COLOUR = (70, 125, 50)
UNDO_STEPS = 30

PROMPT_TEMPLATE = """\
The attached picture is a split view for my medieval trading game "Merchant's Rise". The left cell shows an existing pixel-art map sprite: {example}. The right cell, inside the red frame, holds a rough flat {colour_name} shape that I scribbled with the mouse. It is not a drawing to keep, only a sketch of the outline, size and position of a new sprite.

Draw a new {noun}{sub} in the right cell:
- Its outline and size follow the sketch: where the sketch is wide it is wide, where it is tall it is tall, and it stands on the ground where the sketch's lowest point is. Turn the wobbly mouse lines into a natural shape for a {noun}.
- The flat colour of the sketch, {colour_name} ({hex}), is the main colour of its {main_part}. Shade it with darker and lighter tones of that colour, and give the parts the colour does not stand for (such as stems, trunk or soil) natural colours.
- No trace of the flat sketch or its edge may remain.

The most important thing is that the new {noun} looks like it comes from the exact same game as the sprite on the left:
- Copy its art style exactly: the same size of pixels (not finer), the same outline, the same way of shading with few shades per colour, the same amount of detail, the same viewing angle and the same light from the same side.
- Draw it at the scale the sketch shows next to the left sprite, not at the left sprite's size.
- Plain white background. No shadow, ground or grass beyond what the left sprite has at its foot.

Draw nothing outside the red frame and leave the left cell exactly as it is. Output the full split image.
"""


# ---------------------------------------------------------------------------
# Colours in words
# ---------------------------------------------------------------------------

HUES = ((15, 'red'), (40, 'orange'), (65, 'yellow'), (85, 'yellow-green'), (150, 'green'),
        (190, 'teal'), (250, 'blue'), (285, 'purple'), (330, 'magenta'), (360, 'red'))


def colour_name(rgb):
    """A plain name for a colour, e.g. 'dark green' or 'pale pink'."""
    h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in rgb))
    if v < 0.15:
        return 'black'
    if s < 0.15:
        return 'white' if v > 0.85 else 'light grey' if v > 0.6 else 'grey' if v > 0.35 else 'dark grey'
    hue = next(name for limit, name in HUES if h * 360 < limit)
    if hue in ('red', 'orange') and v < 0.6:
        hue = 'brown'
    elif hue in ('red', 'magenta') and s < 0.5 and v > 0.7:
        return 'pink'
    if s < 0.35:
        return f'greyish {hue}'
    if v < 0.4:
        return f'dark {hue}'
    if s < 0.45 and v > 0.75:
        return f'pale {hue}'
    if v > 0.85 and s > 0.8:
        return f'bright {hue}'
    return hue


def hex_colour(rgb):
    return '#{:02x}{:02x}{:02x}'.format(*rgb)


# ---------------------------------------------------------------------------
# The job
# ---------------------------------------------------------------------------

@dataclass
class PlantSheet:
    """The split image and its prompt, shaped like a sheets.FrameSheet for the API and the answers."""

    surface: pygame.Surface
    path: Path
    prompt: str
    pose: str = POSE
    name: str = 'New plant'


class PlantJob:
    """One new plant in the making, kept in its folder."""

    prefix = 'plant'   # answers are named plant_plant_web.png, plant_plant_gemini.png, ...
    is_new = False
    is_player = False

    def __init__(self, folder):
        self.folder = Path(folder)
        data = json.loads((self.folder / JOB_FILE).read_text(encoding='utf-8'))
        self.kind = data.get('kind', 'needle_tree')
        self.subcategory = data.get('subcategory', '')
        self.colour = tuple(data.get('colour', DEFAULT_COLOUR))
        self.example_label = data.get('example', '')
        self.example_kind = data.get('example_kind', self.kind)
        self.created = data.get('created', '')
        self.accepted = data.get('accepted', {})   # {answer image: saved sprite path}
        self.example = pygame.image.load(str(self.folder / EXAMPLE_FILE)).convert_alpha()
        self.factor, self.cell, self.margin = self.geometry()
        self.sketch = self._load_sketch()
        self.undo_stack = []

    @classmethod
    def create(cls, sprite):
        """A new job with a listed PlantSprite as its example."""
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        folder = PLANT_OUTPUT / f'{sprite.kind}_{stamp}'
        folder.mkdir(parents=True, exist_ok=True)
        pygame.image.save(sprite.surface, str(folder / EXAMPLE_FILE))
        kind = sprite.kind if sprite.kind in KINDS_BY_KEY else 'needle_tree'
        data = {'kind': kind, 'subcategory': '', 'colour': list(DEFAULT_COLOUR),
                'example': sprite.label if sprite.path is None else sprite.path.name,
                'example_kind': sprite.kind, 'created': datetime.now().isoformat(timespec='seconds'),
                'accepted': {}}
        (folder / JOB_FILE).write_text(json.dumps(data, indent=1) + '\n', encoding='utf-8')
        return cls(folder)

    # --- what the app needs of a figure ------------------------------------

    @property
    def name(self):
        return self.folder.name

    @property
    def out_dir(self):
        return self.folder

    @property
    def label(self):
        kind = KINDS_BY_KEY[self.kind].noun
        return f'{self.subcategory} ({kind})' if self.subcategory else kind

    # --- state --------------------------------------------------------------

    def save(self):
        """job.json and sketch.png."""
        data = {'kind': self.kind, 'subcategory': self.subcategory, 'colour': list(self.colour),
                'example': self.example_label, 'example_kind': self.example_kind, 'created': self.created,
                'accepted': self.accepted}
        (self.folder / JOB_FILE).write_text(json.dumps(data, indent=1) + '\n', encoding='utf-8')
        pygame.image.save(self.sketch.to_surface(setcolor=(0, 0, 0, 255), unsetcolor=(0, 0, 0, 0)),
                          str(self.folder / SKETCH_FILE))

    def _load_sketch(self):
        try:
            image = pygame.image.load(str(self.folder / SKETCH_FILE)).convert_alpha()
        except (pygame.error, OSError):
            return pygame.Mask((self.cell, self.cell))
        if image.get_size() != (self.cell, self.cell):
            image = pygame.transform.scale(image, (self.cell, self.cell))
        return pygame.mask.from_surface(image, 128)

    def discard(self):
        """Delete the job's folder and all its answers."""
        shutil.rmtree(self.folder, ignore_errors=True)

    def has_sketch(self):
        return self.sketch.count() > 0

    # --- sketching ----------------------------------------------------------

    def begin_stroke(self):
        """Remember the sketch before a stroke, for undo()."""
        self.undo_stack.append(self.sketch.copy())
        del self.undo_stack[:-UNDO_STEPS]

    def paint(self, a, b, radius, erase=False):
        """A brush line from a to b (right-cell coordinates), kept inside the red frame."""
        brush = _brush(radius)
        stroke = pygame.Mask(self.sketch.get_size())
        steps = max(1, int(max(abs(b[0] - a[0]), abs(b[1] - a[1])) / max(1, radius / 2)))
        for i in range(steps + 1):
            x = a[0] + (b[0] - a[0]) * i / steps
            y = a[1] + (b[1] - a[1]) * i / steps
            stroke.draw(brush, (int(x) - radius, int(y) - radius))
        inside = pygame.Mask(self.sketch.get_size())
        inside.draw(pygame.Mask(self.drawable().size, fill=True), self.drawable().topleft)
        stroke = stroke.overlap_mask(inside, (0, 0))
        if erase:
            self.sketch.erase(stroke, (0, 0))
        else:
            self.sketch.draw(stroke, (0, 0))

    def fill_enclosed(self):
        """Fill every area the sketch closes in: a drawn outline becomes a shape."""
        empty = self.sketch.copy()
        empty.invert()
        outside = empty.connected_component((0, 0))   # the band inside the red frame is always empty
        outside.invert()
        self.sketch = outside

    def undo(self):
        if self.undo_stack:
            self.sketch = self.undo_stack.pop()
            return True
        return False

    def clear(self):
        self.begin_stroke()
        self.sketch.clear()

    # --- the split image ----------------------------------------------------

    def geometry(self):
        """(factor, cell side, margin): the example blown up by whole pixels in a square cell."""
        w, h = self.example.get_size()
        factor = max(1, CELL_TARGET // max(w, h))
        side = int(max(w, h) * factor / (1 - 2 * CELL_MARGIN))
        return factor, side, int(side * CELL_MARGIN)

    def cells(self):
        """(left cell, right cell) on the sheet."""
        return [pygame.Rect(FRAME_WIDTH + col * (self.cell + FRAME_WIDTH), FRAME_WIDTH, self.cell, self.cell)
                for col in range(2)]

    def drawable(self):
        """Where the sketch may go, in right-cell coordinates: inside the red frame."""
        inset = TARGET_FRAME_WIDTH + 4
        return pygame.Rect(inset, inset, self.cell - 2 * inset, self.cell - 2 * inset)

    def ground(self):
        """The example's foot line, in cell coordinates."""
        return self.cell - self.margin

    def build_sheet_size(self):
        return 2 * self.cell + 3 * FRAME_WIDTH, self.cell + 2 * FRAME_WIDTH

    def build_sheet(self, with_sketch=True):
        left, right = self.cells()
        sheet = pygame.Surface(self.build_sheet_size())
        sheet.fill(FRAME_COLOR)
        sheet.fill((255, 255, 255), left)
        sheet.fill((255, 255, 255), right)
        example = scaled(self.example, self.factor)
        sheet.blit(example, example.get_rect(midbottom=(left.centerx, left.y + self.ground())))
        if with_sketch:
            sheet.blit(self.sketch_surface(), right)
        pygame.draw.rect(sheet, TARGET_FRAME_COLOR, right, TARGET_FRAME_WIDTH)
        return sheet

    def sketch_surface(self):
        return self.sketch.to_surface(setcolor=self.colour + (255,), unsetcolor=(0, 0, 0, 0))

    def prompt(self):
        kind = KINDS_BY_KEY[self.kind]
        example_kind = KINDS_BY_KEY.get(self.example_kind)
        example = f'a {example_kind.noun}' if example_kind else 'a plant'
        name = colour_name(self.colour)
        return PROMPT_TEMPLATE.format(
            example=example, colour_name=name, hex=hex_colour(self.colour), noun=kind.noun,
            sub=f', more exactly: {self.subcategory}' if self.subcategory else '', main_part=kind.main_part)

    def write_sheet(self):
        """Write sheet.png and prompt.txt as they are now; returns the PlantSheet."""
        self.save()
        surface = self.build_sheet()
        path = self.folder / SHEET_FILE
        prompt = self.prompt()
        pygame.image.save(surface, str(path))
        (self.folder / PROMPT_FILE).write_text(prompt, encoding='utf-8')
        return PlantSheet(surface, path, prompt)


@lru_cache(maxsize=8)
def _brush(radius):
    """A round brush tip; not to be changed, it is shared."""
    brush = pygame.Mask((2 * radius + 1, 2 * radius + 1))
    for x in range(2 * radius + 1):
        for y in range(2 * radius + 1):
            if (x - radius) ** 2 + (y - radius) ** 2 <= radius * radius:
                brush.set_at((x, y))
    return brush


def find_jobs():
    """Every plant job on disk, newest first; a broken folder is skipped."""
    jobs = []
    if PLANT_OUTPUT.is_dir():
        for folder in PLANT_OUTPUT.iterdir():
            if (folder / JOB_FILE).is_file() and (folder / EXAMPLE_FILE).is_file():
                try:
                    jobs.append(PlantJob(folder))
                except (pygame.error, OSError, ValueError):
                    continue
    jobs.sort(key=lambda job: job.created, reverse=True)
    return jobs
