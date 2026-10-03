"""Making a new sprite from an example: the job, its split image and its prompt.

A job starts from a plant or building sprite clicked in the overview, the
example, and belongs to that sprite's sprite_library.Domain. Its folder
build_tools/output/<domain>/<job>/ holds everything about it:

    job.json      the kind, the optional subcategory ("oak"), the colour,
                  the example's name, and which answers became which sprite
    example.png   the example, as it was when the job started
    sketch.png    the rough shape drawn with the mouse, as a mask
    sheet.png     the split image sent to the model, and prompt.txt with it
    review.json   the answers, as for the humans (pose_review.py)

The split image is two square white cells side by side: the example blown up
by whole pixels on the left, and on the right, inside a red frame, the sketch
filled flat with the chosen colour, at the same scale. The model is asked to
draw a sprite of the kind in the red frame, shaped like the sketch and mainly
in its colour, in the example's style; the domain's prompt template says
how.
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
from sheets import FRAME_COLOR, FRAME_WIDTH, TARGET_FRAME_COLOR, TARGET_FRAME_WIDTH

JOB_FILE = 'job.json'
EXAMPLE_FILE = 'example.png'
SKETCH_FILE = 'sketch.png'
SHEET_FILE = 'sheet.png'
PROMPT_FILE = 'prompt.txt'
POSE = 'plant'                  # what the answers are booked under in review.json

CELL_TARGET = 640               # the example is blown up by whole pixels to about this size
EXAMPLE_SHARE = 0.6             # of the cell's side the example takes, leaving room for a bigger sprite
GROUND_SHARE = 0.06             # of the cell's side below the foot line
LEGACY_LAYOUT = (0.8, 0.1)      # (example share, ground share) of jobs made before the room was grown
UNDO_STEPS = 30



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
class JobSheet:
    """The split image and its prompt, shaped like a sheets.FrameSheet for the API and the answers."""

    surface: pygame.Surface
    path: Path
    prompt: str
    pose: str = POSE
    name: str = 'New sprite'


class SpriteJob:
    """One new sprite in the making, kept in its folder."""

    prefix = 'plant'   # answers are named plant_plant_web.png, ... as the first jobs had them
    is_new = False
    is_player = False

    def __init__(self, domain, folder):
        """
        Args:
            domain: The sprite_library.Domain the job makes a sprite of.
            folder: Its folder in the domain's output.
        """
        self.domain = domain
        self.folder = Path(folder)
        data = json.loads((self.folder / JOB_FILE).read_text(encoding='utf-8'))
        self.kind = data.get('kind', '')
        if self.kind not in domain.kinds_by_key:
            self.kind = domain.kinds[0].key
        self.subcategory = data.get('subcategory', '')
        self.colour = tuple(data.get('colour', domain.default_colour))
        self.example_label = data.get('example', '')
        self.example_kind = data.get('example_kind', self.kind)
        self.created = data.get('created', '')
        self.accepted = data.get('accepted', {})   # {answer image: saved sprite path}
        # The cell's layout is kept with the job, so its sketch stays where it was drawn
        self.layout = tuple(data.get('layout', LEGACY_LAYOUT))
        self.example = pygame.image.load(str(self.folder / EXAMPLE_FILE)).convert_alpha()
        self.factor, self.cell, self.margin = self.geometry()
        self.sketch = self._load_sketch()
        self.undo_stack = []

    @classmethod
    def create(cls, domain, sprite):
        """A new job with a listed sprite_library.LibrarySprite as its example."""
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        folder = domain.output / f'{sprite.kind}_{stamp}'
        count = 2
        while folder.exists():   # two jobs started in one second
            folder = domain.output / f'{sprite.kind}_{stamp}_{count}'
            count += 1
        folder.mkdir(parents=True)
        pygame.image.save(sprite.surface, str(folder / EXAMPLE_FILE))
        kind = sprite.kind if sprite.kind in domain.kinds_by_key else domain.kinds[0].key
        data = {'kind': kind, 'subcategory': '', 'colour': list(domain.default_colour),
                'example': sprite.label if sprite.path is None else sprite.path.name,
                'example_kind': sprite.kind, 'created': datetime.now().isoformat(timespec='seconds'),
                'accepted': {}, 'layout': [EXAMPLE_SHARE, GROUND_SHARE]}
        (folder / JOB_FILE).write_text(json.dumps(data, indent=1) + '\n', encoding='utf-8')
        return cls(domain, folder)

    # --- what the app needs of a figure ------------------------------------

    @property
    def name(self):
        return self.folder.name

    @property
    def out_dir(self):
        return self.folder

    @property
    def label(self):
        kind = self.domain.kinds_by_key[self.kind].noun
        return f'{self.subcategory} ({kind})' if self.subcategory else kind

    # --- state --------------------------------------------------------------

    def save(self):
        """job.json and sketch.png."""
        data = {'kind': self.kind, 'subcategory': self.subcategory, 'colour': list(self.colour),
                'example': self.example_label, 'example_kind': self.example_kind, 'created': self.created,
                'accepted': self.accepted, 'layout': list(self.layout)}
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
        """(factor, cell side, room below the foot): the example blown up by whole pixels in a square cell.

        The example takes the layout's share of the cell, so the new sprite can
        be sketched bigger than it.
        """
        share, ground = self.layout
        w, h = self.example.get_size()
        factor = max(1, CELL_TARGET // max(w, h))
        side = int(max(w, h) * factor / share)
        return factor, side, int(side * ground)

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
        kinds = self.domain.kinds_by_key
        kind = kinds[self.kind]
        example_kind = kinds.get(self.example_kind)
        example = f'a {example_kind.noun}' if example_kind else f'a {self.domain.noun}'
        name = colour_name(self.colour)
        return self.domain.prompt_template.format(
            example=example, colour_name=name, hex=hex_colour(self.colour), noun=kind.noun,
            sub=f' ({self.subcategory})' if self.subcategory else '', main_part=kind.main_part)

    def write_sheet(self):
        """Write sheet.png and prompt.txt as they are now; returns the JobSheet."""
        self.save()
        surface = self.build_sheet()
        path = self.folder / SHEET_FILE
        prompt = self.prompt()
        pygame.image.save(surface, str(path))
        (self.folder / PROMPT_FILE).write_text(prompt, encoding='utf-8')
        return JobSheet(surface, path, prompt)


@lru_cache(maxsize=8)
def _brush(radius):
    """A round brush tip; not to be changed, it is shared."""
    brush = pygame.Mask((2 * radius + 1, 2 * radius + 1))
    for x in range(2 * radius + 1):
        for y in range(2 * radius + 1):
            if (x - radius) ** 2 + (y - radius) ** 2 <= radius * radius:
                brush.set_at((x, y))
    return brush


def find_jobs(domain):
    """Every job of a domain on disk, newest first; a broken folder is skipped."""
    jobs = []
    if domain.output.is_dir():
        for folder in domain.output.iterdir():
            if (folder / JOB_FILE).is_file() and (folder / EXAMPLE_FILE).is_file():
                try:
                    jobs.append(SpriteJob(domain, folder))
                except (pygame.error, OSError, ValueError):
                    continue
    jobs.sort(key=lambda job: job.created, reverse=True)
    return jobs
