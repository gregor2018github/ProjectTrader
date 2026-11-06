"""A good's picture for the menus: its sketch, the split image and prompt made from it, and the files an answer makes.

A good's menu pictures (goods.py) all come from one painting, so that is what the model draws, on a
2x2 split image:

    +----------------+----------------+
    |  another good  |  another good  |
    +----------------+----------------+
    |  another good  |  red frame:    |
    |                |  the sketch    |
    +----------------+----------------+

Three goods that have a painting of their own, picked at random, show the style; each is cut out of its
painting's plain background (cut_good_icons.cut_out) and put on white, so all four cells are alike and the
frame lines are easy to find in the answer. Bottom right, inside the red frame, the sketch of the new good
in flat colours, painted on the sketch screen (view_good_design.py). Which three goods are shown is kept
with the sketch and drawn again on asking ("Other goods").

What the good is comes from its description, <output>/goods/<good>/description.txt, written from
DESCRIPTIONS the first time and edited by hand after; the prompt follows the file as it is saved.

Accepting an answer (view_good_answers.py) cuts the good out of the red frame as a plant is cut out of
its answer (extraction.Extraction: white is background, enclosed white can be clicked see-through) and
writes all three pictures the game loads: the painting, the figure on white in a 1024px square
(<good>_full.jpeg), the cut-out (<good>_icon.png, ICON_SIZE on its longer side) and the 30px icon
(<good>_30.png), which replaces the placeholder. Whatever they replace is kept in
<output>/goods/<good>/replaced/ first.
"""

import importlib.util
import json
import random
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pygame

from extraction import Extraction, find_cells
from goods import OK
from images import smooth_fit
from sheets import FRAME_COLOR, FRAME_WIDTH, TARGET_FRAME_COLOR, TARGET_FRAME_WIDTH
from sprite_extraction import strip_red_frame
from sprite_job import SketchCanvas, colour_name, hex_colour
from theme import OUTPUT_DIR, ROOT

GOODS_OUTPUT = OUTPUT_DIR / 'goods'
LAYOUT = '2x2'
POSE = 'painting'            # a good has one picture to make; answers are booked under this pose
CELL_SIZE = (480, 540)       # a little taller than wide: extraction.find_cells() knows a 2x2 answer by that
FIGURE_SHARE = 0.78          # of a cell a reference good fills, along its longer side
REFERENCES = 3
PAINTING_SIZE = 1024
PAINTING_FILL = 0.8          # of the painting the new good fills, along its longer side
ICON_SIZE = 128              # as cut_good_icons.py makes them
SMALL_SIZE = 30
SMALL_FILL = 0.94            # of the 30px icon the good fills
WHITE = (255, 255, 255)
CLEAR = (0, 0, 0, 0)
DEFAULT_COLOUR = (150, 110, 70)

SKETCH_DIR = 'sketches'
SKETCH_STATE = 'sketches.json'
SKETCH_FILE = 'sketch.png'
SHEET_FILE = 'sheet.png'
DESCRIPTION_FILE = 'description.txt'
REPLACED_DIR = 'replaced'

CUT_GOOD_ICONS = ROOT / 'build_tools' / 'Good_Icons' / 'cut_good_icons.py'

# What each good is, for the prompt; written into its description.txt the first time, edited there after
DESCRIPTIONS = {
    'Wood': 'logs of timber',
    'Stone': 'blocks of building stone',
    'Iron': 'bars of iron',
    'Wool': 'raw sheep\'s wool, a fleece',
    'Hide': 'a raw animal hide',
    'Fish': 'fresh fish',
    'Wheat': 'a sheaf of wheat',
    'Wine': 'red wine',
    'Beer': 'beer, a tankard of ale',
    'Meat': 'fresh meat',
    'Pottery': 'clay pots and jugs',
    'Linen': 'linen cloth',
    'Candle': 'candles',
    'Herbs': 'healing herbs',
    'Salt': 'salt',
    'Flax': 'a bundle of harvested flax stalks, dried and tied with a cord, a few seed heads at the top',
    'Livestock': 'livestock for the butcher: the head of a brown cow in profile, facing left, with its neck',
    'Clay': 'a lump of freshly dug, wet potter\'s clay, reddish brown, on a board',
    'Spices': 'spices from beyond the sea: small open sacks and a wooden bowl of pepper, cinnamon sticks and '
              'saffron',
    'Flour': 'a sack of flour, open at the top, the white flour showing, a wooden scoop in it',
    'Charcoal': 'a heap of black charcoal lumps',
    'Tallow': 'tallow: a block of pale, rendered animal fat in a shallow wooden dish',
    'Leather': 'a roll of tanned brown leather, tied',
    'Cloth': 'a bolt of woven woollen cloth, dyed a warm colour, partly unrolled',
    'Bread': 'a round loaf of brown bread, a piece cut off',
    'Salted Fish': 'salted fish: split, dried cod in a small barrel, with salt crystals',
    'Garments': 'garments: a folded medieval tunic with a hood or cloak on top',
    'Shoes': 'a pair of medieval leather shoes',
    'Tools': 'tools: a smith\'s hammer and a saw',
    'Furniture': 'furniture: a wooden stool beside a small wooden chest',
}

PROMPT_TEMPLATE = """\
The attached picture is a 2x2 split image for my medieval trading game "Merchant's Rise". In the game's menus - the market, the depot, the warehouses - every good that can be traded is shown as a picture like the ones in three of the cells: one good as rough, chunky, low-resolution pixel art with black outlines, on a plain white background.

The other three cells show goods already in the game: {references}. They are only there to show the style. Do not change them.

Inside the red frame in the bottom right cell is a rough sketch in flat colours of a new good: {good}. Turn the sketch into that good's finished picture, drawn over it so that nothing of the sketch is left:
- Follow the sketch: the good takes its outline, size and place in the frame. Where the sketch is drawn in square blocks with black outlines, those blocks are exactly the pixel size to keep: refine its shapes and add shading on that same coarse grid, never on a finer one.
- {colour_rule}
- It has to be clearly recognisable as {name} at a glance, even when the game shows it only 30 pixels tall: one clear object or a small group of objects with a bold, simple silhouette.

The most important thing is that it looks like it belongs to the exact same set as the other three pictures, which are rough, chunky, low-resolution pixel art:
- Big, blocky pixels on a coarse grid, exactly as large as the pixels in the other three cells. Draw it as if on a canvas only 32 pixels wide and 36 pixels tall, then blown up without smoothing so that every pixel is a clearly visible square block, about 1/32 of the cell's width. Never use finer pixels than that, not even for small parts, edges or highlights.
- A thick black outline, one of those big pixels wide, around the whole good, and black lines between its main parts, as in the other cells.
- Flat colours with only 2 or 3 shades each, in hard-edged blocks. No smooth gradients, no soft or blurred edges, no anti-aliasing, no fine texture, no small highlights or tiny details: simplify, as the other pictures do. When in doubt, leave detail out.
- The same viewing angle and the same light from the same side as the other three.
- About as big in its cell as they are in theirs.
- Plain white background. No shadow on the ground, no table or surface under it, no text or labels.

Draw nothing outside the red frame and leave the other three cells exactly as they are. Output the full split image.
"""

ONE_COLOUR_RULE = ("The flat colour of the sketch, {name} ({hex}), is the good's main colour. Shade it with darker "
                   "and lighter tones of that colour.")
COLOURS_RULE = ('The sketch is painted in flat colours: {listed}. They show which part goes where: each part '
                'takes the colour sketched where it is. Shade every colour with darker and lighter tones of itself.')
CELL_NAMES = ('top left', 'top right', 'bottom left')


def slug(name):
    """'salted_fish': a good's name in folder and file names."""
    return name.lower().replace(' ', '_')


_cutter = None


def cut_good_icons():
    """build_tools/Good_Icons/cut_good_icons.py, loaded once: cut_out(), HOLES."""
    global _cutter
    if _cutter is None:
        spec = importlib.util.spec_from_file_location('cut_good_icons', CUT_GOOD_ICONS)
        _cutter = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_cutter)
    return _cutter


class GoodSubject:
    """A good while its picture is made: what the app keeps as its `npc` (out_dir, prefix, title) for the
    answers, the API and the browser."""

    def __init__(self, good):
        self.good = good
        self.name = good.name
        self.title = good.name
        self.prefix = slug(good.name)
        self.out_dir = GOODS_OUTPUT / self.prefix

    @property
    def description_path(self):
        return self.out_dir / DESCRIPTION_FILE

    def description(self):
        """What the good is, from description.txt, or DESCRIPTIONS if it has none yet."""
        try:
            text = self.description_path.read_text(encoding='utf-8').strip()
        except OSError:
            text = ''
        return text or DESCRIPTIONS.get(self.name, self.name.lower())

    def ensure_description(self):
        """description.txt, written from DESCRIPTIONS if it is not there; returns its path.

        Raises:
            OSError: If it cannot be written.
        """
        path = self.description_path
        if not path.is_file():
            self.out_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(DESCRIPTIONS.get(self.name, self.name.lower()) + '\n', encoding='utf-8')
        return path


def painted_goods(goods, besides=''):
    """The goods with a painting of their own (not `besides`), the ones that can show the style."""
    return [g for g in goods if g.name != besides and g.status('painting') == OK]


_figures = {}   # {(painting path, its time): the figure cut out of it}


def figure_of(good):
    """The good cut out of its painting's background, see-through around it.

    Raises:
        pygame.error, OSError, ValueError: If the painting cannot be read or cut.
    """
    path = good.path('painting')
    key = (path, path.stat().st_mtime)
    if key not in _figures:
        cutter = cut_good_icons()
        image = pygame.image.load(str(path)).convert_alpha()
        _figures[key] = cutter.cut_out(image, cutter.HOLES.get(good.name, ())).copy()
    return _figures[key]


def load_state(subject):
    """sketches.json: {'colour', 'palette', 'references': [good names]}."""
    try:
        data = json.loads((subject.out_dir / SKETCH_DIR / SKETCH_STATE).read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(subject, state):
    folder = subject.out_dir / SKETCH_DIR
    folder.mkdir(parents=True, exist_ok=True)
    (folder / SKETCH_STATE).write_text(json.dumps(state, indent=1) + '\n', encoding='utf-8')


# ---------------------------------------------------------------------------
# The sketch and its sheet
# ---------------------------------------------------------------------------

@dataclass
class GoodSheet:
    """A good's split image and prompt, shaped like a sheets.FrameSheet for the API and the answers."""

    subject: GoodSubject
    references: list         # the goods.Good shown for the style
    surface: pygame.Surface
    path: Path
    prompt: str
    sketched: bool = True
    layout: str = LAYOUT
    pose: str = POSE

    @property
    def name(self):
        return f'{self.subject.title} painting'


class GoodSketch(SketchCanvas):
    """The sketch of a good's picture and the three goods shown beside it, kept in the good's output."""

    recent_folder = GOODS_OUTPUT   # the colours used last, shared by every good

    def __init__(self, subject, goods):
        """
        Args:
            subject: The GoodSubject.
            goods: Every goods.Good, to pick the three shown from.
        """
        self.subject = subject
        self.goods = goods
        self.cell_size = CELL_SIZE
        state = load_state(subject)
        self.colour = tuple(state.get('colour', DEFAULT_COLOUR))
        self.palette = [tuple(c) for c in state.get('palette', [self.colour])]
        by_name = {g.name: g for g in painted_goods(goods, subject.name)}
        kept = [by_name[n] for n in state.get('references', []) if n in by_name]
        self.references = kept if len(kept) == min(REFERENCES, len(by_name)) else []
        if not self.references:
            self.pick_references()
        self.sketch = self._load_sketch()
        self.unreadable = []     # goods shown whose painting could not be cut out, as last built
        self._start_canvas()

    # --- where it lives -------------------------------------------------------

    @property
    def sketch_path(self):
        return self.subject.out_dir / SKETCH_DIR / SKETCH_FILE

    @property
    def sheet_path(self):
        return self.subject.out_dir / SHEET_FILE

    def pick_references(self):
        """Three other goods with paintings, at random, other ones than shown now if there are enough."""
        pool = painted_goods(self.goods, self.subject.name)
        fresh = [g for g in pool if g not in getattr(self, 'references', [])]
        if len(fresh) < REFERENCES:
            fresh = pool
        self.references = random.sample(fresh, min(REFERENCES, len(fresh)))

    def save(self):
        """The sketch, and the colours and the goods shown in sketches.json."""
        state = load_state(self.subject)
        state['colour'] = list(self.colour)
        palette = [tuple(c) for c in state.get('palette', [])]
        palette += [c for c in self.palette if c not in palette]
        state['palette'] = [list(c) for c in palette]
        state['references'] = [g.name for g in self.references]
        save_state(self.subject, state)
        pygame.image.save(self.sketch, str(self.sketch_path))

    def _load_sketch(self):
        sketch = pygame.Surface(self.cell_size, pygame.SRCALPHA)
        sketch.fill(CLEAR)
        try:
            image = pygame.image.load(str(self.sketch_path)).convert_alpha()
        except (pygame.error, OSError):
            return sketch
        if image.get_size() != self.cell_size:
            image = pygame.transform.scale(image, self.cell_size)
        sketch.blit(image, (0, 0))
        return sketch

    # --- the split image ------------------------------------------------------

    def cells(self):
        """Top left, top right, bottom left, bottom right."""
        cw, ch = self.cell_size
        return [pygame.Rect(FRAME_WIDTH + col * (cw + FRAME_WIDTH), FRAME_WIDTH + row * (ch + FRAME_WIDTH), cw, ch)
                for row in range(2) for col in range(2)]

    def sketch_cell(self):
        return self.cells()[3]

    def build_sheet_size(self):
        cw, ch = self.cell_size
        return 2 * cw + 3 * FRAME_WIDTH, 2 * ch + 3 * FRAME_WIDTH

    def build_sheet(self, with_sketch=True):
        """The split image: three goods for the style, and the sketch in the red frame."""
        sheet = pygame.Surface(self.build_sheet_size())
        sheet.fill(FRAME_COLOR)
        cells = self.cells()
        for cell in cells:
            sheet.fill(WHITE, cell)
        box = (int(self.cell_size[0] * FIGURE_SHARE), int(self.cell_size[1] * FIGURE_SHARE))
        self.unreadable = []
        for good, cell in zip(self.references, cells):
            try:
                figure = smooth_fit(figure_of(good), box)
            except (pygame.error, OSError, ValueError) as exc:
                self.unreadable.append(f'{good.name} ({exc})')   # its cell stays white; the view says so
                continue
            sheet.blit(figure, figure.get_rect(center=cell.center))
        if with_sketch:
            sheet.blit(self.sketch, cells[3])
        pygame.draw.rect(sheet, TARGET_FRAME_COLOR, cells[3], TARGET_FRAME_WIDTH)
        return sheet

    # --- the prompt -----------------------------------------------------------

    def colour_rule(self):
        colours = self.prompt_colours()
        if len(colours) == 1:
            return ONE_COLOUR_RULE.format(name=colour_name(colours[0]), hex=hex_colour(colours[0]))
        return COLOURS_RULE.format(listed=', '.join(f'{colour_name(c)} ({hex_colour(c)})' for c in colours))

    def prompt(self):
        parts = [f'{where} {good.name.lower()} ({DESCRIPTIONS.get(good.name, good.name.lower())})'
                 for where, good in zip(CELL_NAMES, self.references)]
        references = ', '.join(parts[:-1]) + ' and ' + parts[-1] if len(parts) > 1 else ''.join(parts)
        name = self.subject.name.lower()
        return PROMPT_TEMPLATE.format(references=references, good=f'{name} - {self.subject.description()}',
                                      name=name, colour_rule=self.colour_rule())

    def sheet(self, write=True):
        """The GoodSheet as the sketch is now; written to disk with its prompt if `write` and sketched.

        Raises:
            pygame.error, OSError: If it cannot be written.
        """
        surface = self.build_sheet()
        sketched = self.has_sketch()
        prompt = self.prompt() if sketched else ''
        path = self.sheet_path
        if self.unreadable:
            raise OSError('cannot cut out ' + ', '.join(self.unreadable) + ' - try other goods (R)')
        if write and sketched:
            self.save()
            pygame.image.save(surface, str(path))
            path.with_suffix('.txt').write_text(prompt, encoding='utf-8')
        return GoodSheet(self.subject, list(self.references), surface, path, prompt, sketched)

    def write_sheet(self):
        return self.sheet()


# ---------------------------------------------------------------------------
# From the answer to the good's pictures
# ---------------------------------------------------------------------------

class GoodResult:
    """An answer cut out: the new good from the bottom right cell, see-through around it."""

    scale = 1.0

    def __init__(self, path):
        """
        Raises:
            ValueError, pygame.error: If the cells or the good cannot be found.
        """
        self.image = pygame.image.load(str(path)).convert()
        _, target_rect, layout = find_cells(self.image, LAYOUT)
        if layout != LAYOUT:
            raise ValueError('the answer is not a 2x2 split image any more')
        cell, _ = strip_red_frame(self.image.subsurface(target_rect).copy())
        self.target = Extraction(cell, drop_red=False)
        if self.target.bbox is None:
            raise ValueError('nothing drawn in the red frame')
        self.build()

    def build(self):
        self.output = self.target.sprite

    def output_to_cell(self, point):
        return int(point[0] + self.target.bbox.x), int(point[1] + self.target.bbox.y)


# The licence's picture is the good toned sepia: each pixel's brightness (0.299 R + 0.587 G + 0.114 B) becomes
# a brown, alpha kept. Measured off the licence pictures made by hand for the first fifteen goods, which this
# gives back to within one step per channel.
LICENCE_TONE = ((0, (1, 0, 0)), (16, (14, 9, 6)), (32, (36, 27, 21)), (48, (50, 38, 30)), (64, (71, 55, 44)),
                (80, (85, 67, 54)), (96, (100, 79, 65)), (112, (119, 94, 77)), (128, (133, 106, 87)),
                (144, (148, 118, 97)), (160, (164, 130, 108)), (176, (180, 143, 119)), (192, (197, 157, 131)),
                (208, (216, 173, 145)), (224, (223, 186, 162)), (240, (230, 202, 186)), (255, (236, 215, 203)))


def licence_picture(figure):
    """The good on its licence: `figure` (see-through around it) toned by LICENCE_TONE.

    Raises:
        ValueError: If numpy, which pygame.surfarray needs, is not installed.
    """
    try:
        import numpy
    except ImportError as exc:
        raise ValueError('the licence picture needs numpy (pip install -r build_tools/requirements.txt)') from exc
    figure = figure.convert_alpha()
    rgb = pygame.surfarray.array3d(figure).astype(numpy.float32)
    brightness = rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114
    levels = [level for level, _ in LICENCE_TONE]
    toned = figure.copy()
    pixels = pygame.surfarray.pixels3d(toned)
    for channel in range(3):
        pixels[..., channel] = numpy.interp(brightness, levels, [c[channel] for _, c in LICENCE_TONE]).round()
    del pixels   # unlock the surface
    return toned


def pictures_of(figure, kinds=('painting', 'icon', 'small', 'licence')):
    """{kind: Surface} of the pictures the game loads (those of `kinds`), made from the good cut out of an
    answer or of its painting."""
    w, h = figure.get_size()
    painting = pygame.Surface((PAINTING_SIZE, PAINTING_SIZE))
    painting.fill(WHITE)
    big = smooth_fit(figure, (int(PAINTING_SIZE * PAINTING_FILL),) * 2)
    painting.blit(big, big.get_rect(center=painting.get_rect().center))
    icon = smooth_fit(figure, (ICON_SIZE, ICON_SIZE))
    small = pygame.Surface((SMALL_SIZE, SMALL_SIZE), pygame.SRCALPHA)
    small.fill(CLEAR)
    tiny = smooth_fit(figure, (int(SMALL_SIZE * SMALL_FILL),) * 2)
    small.blit(tiny, tiny.get_rect(center=small.get_rect().center))
    pictures = {'painting': painting, 'icon': icon, 'small': small}
    if 'licence' in kinds:
        pictures['licence'] = licence_picture(figure)
    return {kind: picture for kind, picture in pictures.items() if kind in kinds}


GOODS_PICTURES = 'goods pictures'   # what the app's GIMP watch files a good's picture under


def remake_from_painting(subject):
    """The good's cut-out, 30px icon and licence picture made again from its painting,
    cut out of its plain background as cut_good_icons.py does; what they replace goes to replaced/ first.

    Returns:
        The file names written.

    Raises:
        pygame.error, OSError, ValueError: If the painting cannot be read or cut.
    """
    figure = figure_of(subject.good)
    return save_pictures(subject, figure, kinds=('icon', 'small', 'licence'))


def save_pictures(subject, figure, kinds=('painting', 'icon', 'small', 'licence')):
    """Write the good's painting, cut-out, 30px icon and licence picture (those of `kinds`); what they replace
    goes to replaced/ first.

    Returns:
        The file names written.

    Raises:
        pygame.error, OSError: If a file cannot be written.
    """
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    written = []
    kinds = [kind for kind in kinds if subject.good.needs(kind)]
    for kind, surface in pictures_of(figure, kinds).items():
        path = subject.good.path(kind)
        if path.is_file():
            backup = subject.out_dir / REPLACED_DIR / f'{stamp}_{path.name}'
            backup.parent.mkdir(parents=True, exist_ok=True)
            backup.write_bytes(path.read_bytes())
        pygame.image.save(surface, str(path))
        written.append(path.name)
    return written


class GoodDetail:
    """One answer and the pictures accepting it would make."""

    def __init__(self, subject, entry):
        """
        Raises:
            pygame.error, OSError: If the answer's image cannot be read.
        """
        self.subject = subject
        self.entry = entry
        self.path = subject.out_dir / entry.image
        image = pygame.image.load(str(self.path))
        entry.width, entry.height = image.get_size()
        self.result = None
        self.error = ''
        try:
            self.result = GoodResult(self.path)
        except Exception as exc:  # cell detection and extraction fail in many ways
            self.error = f'Cannot use this image: {exc}'
        self.preview = None   # (rect, factor) of the cut-out good where it was last drawn

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
