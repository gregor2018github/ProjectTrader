"""A fence piece's sketch, the split image and prompt made from it, and cutting the answer back onto the raster.

A piece is drawn from a reference piece (fences.reference_options()) and a
sketch, as a crop's stage sprite is (crop_sheets.py). Both lie on the tile
raster at one scale, blown up by whole pixels: a horizontal piece's sheet has
the reference on top and the sketch under it, a vertical one's side by side:

    +------------------------------+          +----------+----------+
    | . . . . . . . . . . . . .    |          | .  .  .  | .  .  .  |
    |  P=======P=======P   (ref)   |          |    P     |    P     |
    +------------------------------+          |    |     |    |     |
    | . . . . . . . . . . . . .    |  red     |   ref    |  sketch  |
    |  P-------P-------P  sketch   |  frame   |    P     |    P     |
    +------------------------------+          +----------+----------+

Each raster starts PAD_TILES in from its cell's corner, so the reference's
posts and the sketch's line up. On the sketch screen the raster's tiles, the
run's foot line and where the posts stand are drawn over both (draw_guides());
they are never sent. The brush keeps to the piece's raster.

The sketch is kept per piece, in raster coordinates, so trying another
reference keeps it: <output>/sketches/<pose>.png at TILE px a tile, beside
sketches.json with the colour in hand, the colours painted with and the
reference chosen for each piece. draft() paints a first sketch from the
raster and the material: posts where they stand, and rails, a wall or bars
between.

Every sheet is written with a .json of where its cells and rasters were
(sketch_<pose>__<reference>.json), and the answer is cut out by it
(FenceResult): the cells are found in the answer (extraction.find_cells),
the reference in its cell gives the answer's scale and where the cell's
corner really is, the sketch cell is taken as lying the same, and the piece's
raster is cut out of it, freed of its white background and scaled down to the
game's TILE px a tile. Arrow keys on the answers screen nudge the cut by a
game pixel, should the posts not sit on the raster.
"""

import json
from dataclasses import dataclass
from pathlib import Path

import pygame

from extraction import Extraction, find_cells
from fences import FENCES_OUTPUT, HORIZONTAL, OTHER_STYLE, SAME_RUN, TILE, TURNED, mode_of
from images import scaled
from sheets import FRAME_COLOR, FRAME_WIDTH, TARGET_FRAME_COLOR, TARGET_FRAME_WIDTH
from sprite_job import CLEAR, SketchCanvas, colour_name, hex_colour

LAYOUTS = {HORIZONTAL: '2x1', 'v': '1x2'}   # stacked, the reference on top; or side by side, it on the left
CELL_TARGET = 960            # the longer side of the larger raster is blown up by whole pixels to about this
PAD_TILES = 0.5              # white from the cell's corner to its raster
GRID_COLOR = (205, 205, 215)
FOOT_COLOR = (150, 150, 150)
POST_COLOR = (60, 110, 220)
GUIDE_DASH = (10, 7)
DONE_COLOR = (80, 180, 90)

SKETCH_DIR = 'sketches'
SKETCH_STATE = 'sketches.json'
SHEET_PREFIX = 'sketch'
MAX_SCALE_DOUBT = 0.25       # the reference's scale may differ this much from the cells' before it is not trusted
HOLE_MIN_GAME_PX = 3         # enclosed white at least this many game pixels big is see-through from the start

# The draft's parts, in tiles
POST_W = 0.22
WALL_PILLAR_W = 0.36
RAIL_W = 0.11
BAR_W = 0.07
BAR_EVERY = 0.25
FOOT_DEPTH = 0.12            # how far below the foot line a post's foot shows
VERTICAL_BODY_W = 0.5        # a vertical wall's or railing's strip

PROMPT_TEMPLATE = """\
The attached picture is a split view for my medieval trading game "Merchant's Rise", a pixel-art game seen from above at a slant, the way old 16-bit role-playing games show their towns. Its fences and walls are put together from straight pieces laid end to end on the map's tile grid.

The {ref_place} cell shows {reference}.

Inside the red frame in the {target_place} cell is a rough sketch in flat colours of {target}. Turn the sketch into that finished piece, drawn over it so that nothing of the sketch is left:
- Follow the sketch closely: the piece keeps its outline, length, height and place in the frame exactly. Do not make it longer or shorter and do not move it.
- {run_rule}
- {post_rule}
- Both ends finish in a {post} cut off cleanly where the sketch ends, nothing beyond it, so that pieces laid end to end meet {post} on {post} without a seam.
- {colour_rule}
- {rule}

It must look like it comes from the exact same game as the {ref_noun} in the {ref_place} cell:
- Copy its art style exactly: the same size of pixels (not finer), the same outline, the same way of shading with few shades per colour, the same amount of detail, the same viewing angle and the same light from the same side.
- Plain white background. No ground, grass, shadow or plants around it: only the {noun}.

Draw nothing outside the red frame and leave the {ref_place} cell exactly as it is. Output the full split image.
"""

RUN_RULES = {
    HORIZONTAL: 'The piece runs straight across the picture from left to right, seen from the front: the {posts} stand '
                'side by side with {body} between them along its whole length.',
    'v': 'The piece runs straight away from the viewer, from the back (the top of the picture) to the front (the '
         'bottom): seen from above at a slant it is a narrow upright strip, the {posts} one behind the other down it, '
         'with {body} between them seen end-on and foreshortened. Only the front end shows its face.',
}
BODIES = {'wood': 'the rails', 'stone': 'the wall', 'metal': 'the railing\'s bars'}
POSTS_RULE = ('It has {count} {posts}: at both ends and every {every} tile{s} between, evenly spaced, exactly where the '
              'sketch has them - no more and no fewer.')
ENDS_RULE = 'It has a {post} at each end only, where the sketch has them, and none between: the {noun} runs on unbroken.'
ONE_COLOUR_RULE = ('The flat colour of the sketch, {name} ({hex}), is the {noun}\'s main colour. Shade it with darker and '
                   'lighter tones of that colour.')
COLOURS_RULE = ('The sketch is painted in flat colours: {listed}. They show which part goes where ({post}s, {body}); '
                'each part takes the colour sketched where it is. Shade every colour with darker and lighter tones of '
                'itself.')
SAME_RUN_RULE = ('It is the same {noun} as in the {ref_place} cell, only {how}: its {posts}, {body} and colours are drawn '
                 'just like those there, repeated over its own length, with small natural differences so it does not '
                 'look copied.')
AGAIN_RULE = ('It is the same piece of {noun} as in the {ref_place} cell, drawn anew: just as long, with its {posts}, '
              '{body} and colours drawn like those there.')
TURNED_RULE = ('It is the same {noun} as in the {ref_place} cell, which runs {ref_way}, only this piece of it runs '
               '{way}: its {posts}, {body}, materials and colours are the same, only seen from that side.')
OTHER_STYLE_RULE = ('Only the style and the scale come from the {ref_place} cell, which shows another fence of the game. '
                    'The piece itself is {what}, and it has to look like that.')
WAYS = {HORIZONTAL: 'across the picture from left to right', 'v': 'away from the viewer, from the back to the front'}


def plural(n, word):
    return f'{n} {word}' + ('' if n == 1 else 's')


# ---------------------------------------------------------------------------
# The sketch screen's state per style
# ---------------------------------------------------------------------------

def load_state(style):
    """The style's sketches.json: {'colour', 'palette', 'references': {pose: reference key}}."""
    try:
        data = json.loads((style.out_dir / SKETCH_DIR / SKETCH_STATE).read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(style, state):
    folder = style.out_dir / SKETCH_DIR
    folder.mkdir(parents=True, exist_ok=True)
    (folder / SKETCH_STATE).write_text(json.dumps(state, indent=1) + '\n', encoding='utf-8')


def chosen_reference(piece, options, default):
    """The reference chosen for a piece on the sketch screen, if it can still be drawn from; else `default`."""
    key = load_state(piece.style).get('references', {}).get(piece.pose)
    for refs in options.values():
        for reference in refs:
            if reference.key == key:
                return reference
    return default


def choose_reference(piece, reference):
    """Keep the reference a piece is drawn from.

    Raises:
        OSError: If sketches.json cannot be written.
    """
    state = load_state(piece.style)
    state.setdefault('references', {})[piece.pose] = reference.key
    save_state(piece.style, state)


# ---------------------------------------------------------------------------
# The sketch and its sheet
# ---------------------------------------------------------------------------

@dataclass
class FenceSheet:
    """One piece's split image and prompt, shaped like a sheets.FrameSheet for the API and the answers."""

    piece: object
    reference: object
    surface: pygame.Surface
    path: Path
    prompt: str
    layout: str
    sketched: bool = True

    @property
    def pose(self):
        return self.piece.pose

    @property
    def name(self):
        return self.piece.name


class FenceSketch(SketchCanvas):
    """The sketch of one piece, drawn from one reference, on the piece's raster."""

    recent_folder = FENCES_OUTPUT   # the colours used last, shared by every style

    def __init__(self, piece, reference):
        """
        Raises:
            pygame.error, OSError: If the reference cannot be read.
        """
        self.piece = piece
        self.style = piece.style
        self.reference = reference
        self.mode = mode_of(piece, reference)
        self.raster = piece.raster
        self.example = reference.load()
        self.layout = LAYOUTS[piece.orientation]
        span = [max(a, b) for a, b in zip(self.raster.pixels, reference.raster.pixels)]
        self.factor = max(1, CELL_TARGET // max(span))
        self.pad = round(PAD_TILES * TILE * self.factor)
        self.cell_size = (span[0] * self.factor + 2 * self.pad, span[1] * self.factor + 2 * self.pad)
        state = load_state(self.style)
        self.colour = tuple(state.get('colour', self.style.material.body_colour))
        self.palette = [tuple(c) for c in state.get('palette', [self.colour])]
        self.sketch = self._load_sketch()
        self._start_canvas()

    # --- where it lives -----------------------------------------------------

    @property
    def pose(self):
        return self.piece.pose

    @property
    def sketch_path(self):
        return self.style.out_dir / SKETCH_DIR / f'{self.pose}.png'

    @property
    def sheet_path(self):
        """sketch_<pose>__<reference>.png; its .json says where the cells were."""
        return self.style.out_dir / f'{SHEET_PREFIX}_{self.pose}__{self.reference.key}.png'

    def mode_label(self):
        """'from Horizontal 4', 'turned from Vertical 2', 'in the look of Old stone wall h4'."""
        words = {SAME_RUN: 'from', TURNED: 'turned from', OTHER_STYLE: 'in the look of'}[self.mode]
        label = self.reference.label()
        if self.mode == OTHER_STYLE and self.reference.piece:
            label = f'{self.reference.style_title} {self.reference.piece.key}'
        return f'{words} {label}'

    def raster_rect(self):
        """The piece's raster in sketch-cell coordinates."""
        w, h = self.raster.pixels
        return pygame.Rect(self.pad, self.pad, w * self.factor, h * self.factor)

    def drawable(self):
        """The brush keeps to the piece's raster: nothing outside it is cut out of the answer."""
        return self.raster_rect()

    def save(self):
        """The sketch, at TILE px a tile, and the colours in sketches.json."""
        state = load_state(self.style)
        state['colour'] = list(self.colour)
        palette = [tuple(c) for c in state.get('palette', [])]
        palette += [c for c in self.palette if c not in palette]
        state['palette'] = [list(c) for c in palette]
        save_state(self.style, state)
        raster = self.sketch.subsurface(self.raster_rect())
        pygame.image.save(pygame.transform.scale(raster, self.raster.pixels), str(self.sketch_path))

    def _load_sketch(self):
        sketch = pygame.Surface(self.cell_size, pygame.SRCALPHA)
        sketch.fill(CLEAR)
        try:
            image = pygame.image.load(str(self.sketch_path)).convert_alpha()
        except (pygame.error, OSError):
            return sketch
        rect = self.raster_rect()
        sketch.blit(pygame.transform.scale(image, rect.size), rect)
        return sketch

    # --- the split image ------------------------------------------------------

    def cells(self):
        """(reference cell, sketch cell) on the sheet."""
        cw, ch = self.cell_size
        if self.layout == '2x1':
            return [pygame.Rect(FRAME_WIDTH, FRAME_WIDTH + i * (ch + FRAME_WIDTH), cw, ch) for i in range(2)]
        return [pygame.Rect(FRAME_WIDTH + i * (cw + FRAME_WIDTH), FRAME_WIDTH, cw, ch) for i in range(2)]

    def build_sheet_size(self):
        cw, ch = self.cell_size
        if self.layout == '2x1':
            return cw + 2 * FRAME_WIDTH, 2 * ch + 3 * FRAME_WIDTH
        return 2 * cw + 3 * FRAME_WIDTH, ch + 2 * FRAME_WIDTH

    def build_sheet(self, with_sketch=True):
        """The split image: the reference, and the sketch in the red frame. No raster."""
        ref_cell, sketch_cell = self.cells()
        sheet = pygame.Surface(self.build_sheet_size())
        sheet.fill(FRAME_COLOR)
        sheet.fill((255, 255, 255), ref_cell)
        sheet.fill((255, 255, 255), sketch_cell)
        sheet.blit(scaled(self.example, self.factor), (ref_cell.x + self.pad, ref_cell.y + self.pad))
        if with_sketch:
            sheet.blit(self.sketch, sketch_cell)
        pygame.draw.rect(sheet, TARGET_FRAME_COLOR, sketch_cell, TARGET_FRAME_WIDTH)
        return sheet

    def to_sheet(self, cell, point):
        """A point in tiles on a raster in `cell` as sheet pixels."""
        f = TILE * self.factor
        return round(cell.x + self.pad + point[0] * f), round(cell.y + self.pad + point[1] * f)

    def draw_guides(self, sheet):
        """The tiles of both rasters, and over the sketch its foot line and where its posts stand."""
        ref_cell, sketch_cell = self.cells()
        self._grid(sheet, ref_cell, self.reference.raster)
        self._grid(sheet, sketch_cell, self.raster)
        raster = self.raster
        start, end = self.to_sheet(sketch_cell, raster.start), self.to_sheet(sketch_cell, raster.end())
        self._dashed(sheet, start, end, FOOT_COLOR, 3)
        radius = max(3, round(TILE * self.factor * 0.09))
        top = self.to_sheet(sketch_cell, (raster.start[0], 0))
        for index, post in enumerate(raster.posts()):
            foot = self.to_sheet(sketch_cell, post)
            if raster.orientation == HORIZONTAL or index == 0:   # a vertical run's posts would hide each other
                self._dashed(sheet, (foot[0], top[1] + radius), foot, POST_COLOR, 2)
            pygame.draw.circle(sheet, POST_COLOR, foot, radius, 3)

    def _grid(self, sheet, cell, raster):
        w, h = raster.size
        for x in range(w + 1):
            pygame.draw.line(sheet, GRID_COLOR, self.to_sheet(cell, (x, 0)), self.to_sheet(cell, (x, h)), 1)
        for y in range(h + 1):
            pygame.draw.line(sheet, GRID_COLOR, self.to_sheet(cell, (0, y)), self.to_sheet(cell, (w, y)), 1)

    @staticmethod
    def _dashed(sheet, a, b, colour, width):
        length = max(abs(b[0] - a[0]), abs(b[1] - a[1]))
        if not length:
            return
        line, gap = GUIDE_DASH
        at = 0
        while at < length:
            stop = min(at + line, length)
            p = (a[0] + (b[0] - a[0]) * at / length, a[1] + (b[1] - a[1]) * at / length)
            q = (a[0] + (b[0] - a[0]) * stop / length, a[1] + (b[1] - a[1]) * stop / length)
            pygame.draw.line(sheet, colour, p, q, width)
            at += line + gap

    def with_result(self, sprite):
        """The sheet with a piece in the frame instead of the sketch, for the cards."""
        sheet = self.build_sheet(with_sketch=False)
        cell = self.cells()[1]
        sheet.blit(scaled(sprite, self.factor), (cell.x + self.pad, cell.y + self.pad))
        pygame.draw.rect(sheet, DONE_COLOR, cell, TARGET_FRAME_WIDTH)
        return sheet

    # --- the draft --------------------------------------------------------------

    def draft(self):
        """Paint a first sketch over the raster: the posts where they stand, and between them the rails, the
        wall or the bars, in the material's two colours. Undo takes it back."""
        self.begin_stroke()
        self.sketch.fill(CLEAR)
        material = self.style.material
        post, body = material.post_colour, material.body_colour
        self._painting_with(body)
        self._painting_with(post)
        rise = self.raster.height - 0.5 - 0.15          # how tall a post stands above its foot, in tiles
        posts = self.raster.posts()
        if self.raster.orientation == HORIZONTAL:
            self._draft_across(material.key, posts, rise, post, body)
        else:
            self._draft_away(material.key, posts, rise, post, body)
        self.colour = body

    def _box(self, x, y, w, h, colour):
        """A rectangle in raster tiles, painted on the sketch."""
        rect = self.raster_rect()
        f = TILE * self.factor
        box = pygame.Rect(round(rect.x + x * f), round(rect.y + y * f), max(1, round(w * f)), max(1, round(h * f)))
        self.sketch.fill(tuple(colour) + (255,), box.clip(rect))

    def _draft_across(self, material, posts, rise, post, body):
        (x0, foot), (x1, _) = posts[0], posts[-1]
        if material == 'stone':
            self._box(x0, foot - rise * 0.8, x1 - x0, rise * 0.8 + FOOT_DEPTH, body)
            for x, _ in posts:
                self._box(x - WALL_PILLAR_W / 2, foot - rise, WALL_PILLAR_W, rise + FOOT_DEPTH, post)
            return
        if material == 'metal':
            for y in (foot - rise * 0.85, foot - rise * 0.15):
                self._box(x0, y, x1 - x0, RAIL_W * 0.7, body)
            bars = int((x1 - x0) / BAR_EVERY)
            for i in range(1, bars):
                self._box(x0 + i * BAR_EVERY - BAR_W / 2, foot - rise * 0.95, BAR_W, rise * 0.95, body)
        else:
            for y in (foot - rise * 0.75, foot - rise * 0.35):
                self._box(x0, y, x1 - x0, RAIL_W, body)
        for x, _ in posts:
            self._box(x - POST_W / 2, foot - rise, POST_W, rise + FOOT_DEPTH, post)

    def _draft_away(self, material, posts, rise, post, body):
        (x, top), (_, bottom) = posts[0], posts[-1]
        width = VERTICAL_BODY_W if material == 'stone' else RAIL_W * 1.6
        # The run seen end-on: its top runs down from the far post's top to the near one's
        self._box(x - width / 2, top - rise * 0.8, width, bottom - top + rise * 0.8 - (0 if material == 'stone'
                                                                                         else rise * 0.2), body)
        post_w = WALL_PILLAR_W if material == 'stone' else POST_W
        for _, y in posts:
            self._box(x - post_w / 2, y - rise, post_w, rise + FOOT_DEPTH, post)

    # --- the prompt -----------------------------------------------------------

    def places(self):
        """(where the reference is, where the sketch is) in the prompt's words."""
        return ('top', 'bottom') if self.layout == '2x1' else ('left', 'right')

    def colour_rule(self, noun, post, body):
        colours = self.prompt_colours()
        if len(colours) == 1:
            return ONE_COLOUR_RULE.format(name=colour_name(colours[0]), hex=hex_colour(colours[0]), noun=noun)
        listed = ', '.join(f'{colour_name(c)} ({hex_colour(c)})' for c in colours)
        return COLOURS_RULE.format(listed=listed, post=post, body=body.replace('the ', ''))

    def prompt(self):
        piece, style, ref = self.piece, self.style, self.reference
        material = style.material
        noun, post = material.noun, material.post
        body = BODIES[material.key]
        ref_place, target_place = self.places()
        about = f' ({style.description})' if style.description else ''
        what = f'{style.title.lower()}{about}, {material.words}'
        way = WAYS[piece.orientation]
        target = (f'a straight piece of {what}, {plural(piece.length, "tile")} long between its end {post}s, running '
                  f'{way}')
        ref_way = WAYS[ref.orientation]
        reference = (f'a straight piece of {ref.style_title.lower()} ({ref.description}), already in the game, '
                     f'{plural(ref.length, "tile")} long, running {ref_way}')
        raster = self.raster
        if raster.posts_every > 0:
            post_rule = POSTS_RULE.format(count=len(raster.posts()), posts=f'{post}s', every=raster.posts_every,
                                          s='' if raster.posts_every == 1 else 's')
        else:
            post_rule = ENDS_RULE.format(post=post, noun=noun)
        if self.mode == SAME_RUN:
            if ref.length == piece.length:
                rule = AGAIN_RULE.format(noun=noun, ref_place=ref_place, posts=f'{post}s', body=body.replace('the ', ''))
            else:
                how = f'{"longer" if piece.length > ref.length else "shorter"}: {plural(piece.length, "tile")} ' \
                      f'instead of {ref.length}'
                rule = SAME_RUN_RULE.format(noun=noun, ref_place=ref_place, how=how, posts=f'{post}s',
                                            body=body.replace('the ', ''))
        elif self.mode == TURNED:
            rule = TURNED_RULE.format(noun=noun, ref_place=ref_place, ref_way=ref_way, way=way, posts=f'{post}s',
                                      body=body.replace('the ', ''))
        else:
            rule = OTHER_STYLE_RULE.format(ref_place=ref_place, what=what)
        return PROMPT_TEMPLATE.format(
            ref_place=ref_place, target_place=target_place, reference=reference, target=target,
            run_rule=RUN_RULES[piece.orientation].format(posts=f'{post}s', body=body), post_rule=post_rule, post=post,
            colour_rule=self.colour_rule(noun, post, body), rule=rule,
            ref_noun='piece' if self.mode != OTHER_STYLE else 'fence', noun=noun)

    # --- writing it -------------------------------------------------------------

    def geometry(self):
        """Where everything was on the sheet, for cutting the answer out (FenceResult)."""
        ref_cell, sketch_cell = self.cells()
        bbox = self.example.get_bounding_rect()
        return {'layout': self.layout, 'factor': self.factor, 'pad': self.pad,
                'sheet': list(self.build_sheet_size()), 'cells': [list(ref_cell), list(sketch_cell)],
                'raster': list(self.raster.pixels), 'orientation': self.piece.orientation,
                'reference_bbox': [bbox.x * self.factor + self.pad, bbox.y * self.factor + self.pad,
                                   bbox.w * self.factor, bbox.h * self.factor],
                'reference': self.reference.key}

    def sheet(self, write=True):
        """The FenceSheet as the sketch is now; written with its prompt and geometry if `write` and sketched.

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
            path.with_suffix('.json').write_text(json.dumps(self.geometry(), indent=1) + '\n', encoding='utf-8')
        return FenceSheet(self.piece, self.reference, surface, path, prompt, self.layout, sketched)

    def write_sheet(self):
        return self.sheet()


# ---------------------------------------------------------------------------
# From the answer to the piece
# ---------------------------------------------------------------------------

class FenceResult:
    """An answer, and the piece cut out of its sketch cell onto the raster."""

    def __init__(self, path, geometry):
        """
        Raises:
            ValueError, pygame.error: If the cells or the piece cannot be found.
        """
        self.image = pygame.image.load(str(path)).convert()
        self.geometry = geometry
        self.nudge = [0, 0]        # game pixels the cut is moved by, from the arrow keys
        self.holes = []            # crop points made see-through, kept across nudges
        ref_rect, target_rect, _ = find_cells(self.image, geometry['layout'])
        ref_sent, target_sent = (pygame.Rect(c) for c in geometry['cells'])
        cell_scale = (target_rect.w / target_sent.w + target_rect.h / target_sent.h) / 2
        self.scale = cell_scale
        self.origin = target_rect.topleft     # the found cell, if the reference says nothing better
        # The reference in its cell tells the answer's scale and where that cell's corner really is; the
        # sketch cell lies as far from it as on the sheet, scaled alike. (The found sketch cell is a poor
        # guide to its corner: the red frame is trimmed off it with the black lines.)
        ref = Extraction(self.image.subsurface(ref_rect).copy())
        if ref.bbox is not None:
            sent = pygame.Rect(geometry['reference_bbox'])
            if geometry['orientation'] == HORIZONTAL:
                scale = (ref.bbox.w - 1) / max(1, sent.w - 1)
            else:
                scale = (ref.bbox.h - 1) / max(1, sent.h - 1)
            if abs(scale / cell_scale - 1) <= MAX_SCALE_DOUBT:
                ref_x = ref_rect.x + ref.bbox.x - sent.x * scale
                ref_y = ref_rect.y + ref.bbox.y - sent.y * scale
                origin = (ref_x + (target_sent.x - ref_sent.x) * scale, ref_y + (target_sent.y - ref_sent.y) * scale)
                doubt = max(abs(origin[0] - target_rect.x), abs(origin[1] - target_rect.y))
                if doubt <= MAX_SCALE_DOUBT * min(target_rect.size) / 4:
                    self.scale, self.origin = scale, origin
        self.build()

    def crop_rect(self):
        """The piece's raster in the answer, moved by the nudge."""
        g = self.geometry
        unit = g['factor'] * self.scale                 # answer pixels per game pixel
        w, h = g['raster']
        x = self.origin[0] + (g['pad'] + self.nudge[0] * g['factor']) * self.scale
        y = self.origin[1] + (g['pad'] + self.nudge[1] * g['factor']) * self.scale
        return pygame.Rect(round(x), round(y), max(1, round(w * unit)), max(1, round(h * unit)))

    def build(self):
        rect = self.crop_rect()
        crop = pygame.Surface(rect.size)
        crop.fill((255, 255, 255))
        inside = rect.clip(self.image.get_rect())
        if inside.w and inside.h:
            crop.blit(self.image, (inside.x - rect.x, inside.y - rect.y), inside)
        self.target = Extraction(crop, drop_red=False)
        # The white between rails and bars is enclosed, yet it is background: all of it goes, but for specks
        # smaller than a few game pixels, a highlight more likely. A click brings a patch back (toggle_hole).
        unit = self.geometry['factor'] * self.scale
        enclosed = self.target.background.copy()
        enclosed.erase(self.target.outside, (0, 0))
        self.target.holes = [blob for blob in enclosed.connected_components()
                             if blob.count() >= HOLE_MIN_GAME_PX * unit * unit]
        self.target.update()
        for point in self.holes:
            self.target.toggle_hole(point)
        if self.target.bbox is None:
            raise ValueError('Nothing drawn on the piece\'s raster.')
        canvas = pygame.Surface(crop.get_size(), pygame.SRCALPHA)
        canvas.blit(self.target.sprite, self.target.bbox)
        self.output = pygame.transform.smoothscale(canvas, tuple(self.geometry['raster']))

    def move(self, dx, dy):
        """Nudge the cut by game pixels."""
        self.nudge[0] += dx
        self.nudge[1] += dy
        self.holes = []
        self.build()

    def toggle_hole(self, point):
        """A point on the output: switch the white area there see-through, or back."""
        crop_w, crop_h = self.target.surface.get_size()
        w, h = self.output.get_size()
        at = (int(point[0] * crop_w / w), int(point[1] * crop_h / h))
        if self.target.surface.get_rect().collidepoint(at) and self.target.toggle_hole(at):
            self.holes.append(at)
            canvas = pygame.Surface((crop_w, crop_h), pygame.SRCALPHA)
            if self.target.sprite is not None:
                canvas.blit(self.target.sprite, self.target.bbox)
            self.output = pygame.transform.smoothscale(canvas, (w, h))


class FenceDetail:
    """One answer and the piece accepting it would make."""

    def __init__(self, style, entry):
        """
        Raises:
            pygame.error, OSError: If the answer's image cannot be read.
        """
        self.style = style
        self.entry = entry
        self.path = style.out_dir / entry.image
        image = pygame.image.load(str(self.path))
        entry.width, entry.height = image.get_size()
        self.result = None
        self.error = ''
        try:
            geometry = json.loads((style.out_dir / entry.sheet).with_suffix('.json').read_text(encoding='utf-8'))
            self.result = FenceResult(self.path, geometry)
        except Exception as exc:  # a sheet's geometry gone, or cell detection and extraction failing
            self.error = f'Cannot use this image: {exc}'
        self.preview = None   # (rect, factor) of the piece where it was last drawn

    def toggle_hole(self, pos):
        """Click on the preview: switch an enclosed white area see-through, or back."""
        if not (self.result and self.preview):
            return
        rect, factor = self.preview
        if rect.collidepoint(pos):
            self.result.toggle_hole(((pos[0] - rect.x) / factor, (pos[1] - rect.y) / factor))

    def move(self, dx, dy):
        if self.result:
            try:
                self.result.move(dx, dy)
            except ValueError as exc:
                self.result.move(-dx, -dy)
                self.error = str(exc)
