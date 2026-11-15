"""The fences and walls of the map, made piece by piece: their styles, pieces, and how a piece lies on the tiles.

A style is a folder assets/map_sprites/houses/fences/<style>/ holding a
fence.json and its pieces, so adding one is adding the folder (create_style()):

    {"title": "Wattle fence",
     "material": "wood",                        # wood, stone or metal (city walls later)
     "description": "hazel rods woven between rough oak stakes",   # for the prompt
     "posts_every": 2,                          # tiles from post to post; 0: only at the ends
     "height": 2,                               # tiles the raster is tall (see below)
     "lengths": {"h": [2, 4, 6], "v": [2, 4]}}  # the pieces wanted, in tiles

A piece is a straight run of the fence, horizontal (h, across the picture) or
vertical (v, down the picture, north to south), so many tiles long between its end posts:
<style>_h4.png, <style>_v2.png. The game loads it like any building, by
File_name, as fences/<style>/<style>_h4.png (house.py joins it to houses/).

Every piece is drawn and saved on its raster, at the game's scale (TILE px a
tile), so pieces laid end to end on the tile grid meet post on post:

    horizontal, 4 tiles, height 2:          vertical, 2 tiles, height 2:

    +--+---+---+---+---+--+                 +---+---+
    |  .   .   .   .   .  |                 |   .   |   the near end's rise
    |  P-------P-------P  |  <- the run     |   P   |   <- first post's foot
    +--+---+---+---+---+--+                 |   |   |
     1/2  4 tiles     1/2                   |   P   |
                                            |   |   |
                                            |   P   |
                                            +---+---+   1/2 tile below

A horizontal raster is (length + 1) x height tiles: half a tile beyond each
end post, the run half a tile above its foot. A vertical one is 2 x (length +
height) tiles: the run down its middle, the first post's foot height - 1/2
tiles from the top (room for the post to rise), half a tile below the last.
Posts stand at both ends and every posts_every tiles between; a stone wall
(posts_every 0) has pillars at its ends only, where it turns a corner or
opens for a gate, and only on its horizontal pieces: a vertical piece of it
is plain wall, its ends running in under the corner pillars of the
horizontal pieces it meets, as the old yard's walls do.

The pieces of a style are the lengths wanted plus any piece on disk, so one
taken off the list but drawn is still shown.

Every piece is drawn from a reference (fence_sheets.py): another piece of the
same style (another length, or turned), another style's piece for the style
only, or, before any piece exists, a cut of the old hand-made walls
(OLD_REFERENCES). assemble() makes a piece of another length from one of the
same style without the model, by laying its post-to-post segments end to end.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

import pygame

from sprite_library import MAP_SPRITES
from theme import OUTPUT_DIR

TILE = 32
HOUSES_DIR = MAP_SPRITES / 'houses'
FENCES_DIR = HOUSES_DIR / 'fences'
FENCE_FILE = 'fence.json'
FENCES_OUTPUT = OUTPUT_DIR / 'fences'
NAME_MAX_LENGTH = 24
MAX_LENGTH = 12                       # the longest piece offered, in tiles
HEIGHTS = (2, 3, 4)                   # raster heights offered; a city wall will want more than a fence
DEFAULT_HEIGHT = 2

HORIZONTAL, VERTICAL = 'h', 'v'
ORIENTATIONS = (HORIZONTAL, VERTICAL)
ORIENTATION_TITLES = {HORIZONTAL: 'Horizontal', VERTICAL: 'Vertical'}
VERTICAL_WIDTH = 2                    # tiles a vertical raster is wide
COLLISION_THICKNESS = 0.5             # tiles, across the run
END_POST_HALF = 0.3                   # tiles a horizontal piece's end posts stand out beyond its run


@dataclass(frozen=True)
class Material:
    key: str
    title: str
    posts_every: int                  # the default for a new style
    noun: str                         # what the prompt calls it
    post: str                         # what the prompt calls a post
    words: str                        # what it is made of, for the prompt
    description: str                  # a new style's description, until one is written
    post_colour: tuple                # the draft's colours (fence_sheets.draft)
    body_colour: tuple
    lengths: dict                     # a new style's pieces


MATERIALS = (
    Material('wood', 'Wood', 2, 'fence', 'post', 'made of wood',
             'weathered wooden rails between rough wooden posts',
             (96, 64, 34), (156, 112, 64), {HORIZONTAL: [2, 4, 6], VERTICAL: [2, 4]}),
    Material('stone', 'Stone', 0, 'wall', 'pillar', 'built of stone',
             'a low wall of rough grey fieldstones, mossy here and there',
             (104, 104, 98), (150, 148, 138), {HORIZONTAL: [1, 2, 4, 6], VERTICAL: [1, 2, 4]}),
    Material('metal', 'Metal', 2, 'railing', 'post', 'made of wrought iron',
             'a wrought-iron railing of thin upright bars with pointed tips between iron posts',
             (44, 44, 50), (86, 88, 98), {HORIZONTAL: [2, 4, 6], VERTICAL: [2, 4]}),
)
MATERIALS_BY_KEY = {m.key: m for m in MATERIALS}
DEFAULT_MATERIAL = 'wood'


def style_folder_name(title):
    """The folder (and file name start) for a style's title: lower case, words joined by _."""
    return re.sub(r'[^a-z0-9]+', '_', title.lower()).strip('_')[:NAME_MAX_LENGTH].strip('_')


# ---------------------------------------------------------------------------
# A piece on its raster
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Raster:
    """Where a piece of `length` tiles lies on its raster; all in tiles. No pygame."""

    orientation: str
    length: int
    height: int
    posts_every: int

    @property
    def size(self):
        """(width, height) in tiles."""
        if self.orientation == HORIZONTAL:
            return self.length + 1, self.height
        return VERTICAL_WIDTH, self.length + self.height

    @property
    def pixels(self):
        w, h = self.size
        return w * TILE, h * TILE

    @property
    def start(self):
        """The first post's foot: the left one, or the far (top) one."""
        if self.orientation == HORIZONTAL:
            return 0.5, self.height - 0.5
        return VERTICAL_WIDTH / 2, self.height - 0.5

    @property
    def step(self):
        """One tile along the run."""
        return (1, 0) if self.orientation == HORIZONTAL else (0, 1)

    def along(self, distance):
        """The point `distance` tiles along the run from its start."""
        (x, y), (dx, dy) = self.start, self.step
        return x + dx * distance, y + dy * distance

    def post_distances(self):
        """How far along the run each post stands: both ends, and every posts_every tiles between."""
        every = self.posts_every
        if every <= 0:
            return [0, self.length] if self.length else [0]
        posts = list(range(0, self.length, every))
        return posts + [self.length]

    @property
    def pillared(self):
        """False for a vertical piece of a wall with pillars at its ends only: its corners' pillars belong to
        the horizontal pieces it meets, and its own ends are plain wall that runs in under them."""
        return not (self.orientation == VERTICAL and self.posts_every <= 0)

    def posts(self):
        """Each post's foot, in tiles on the raster; none for a piece that is not pillared."""
        return [self.along(d) for d in self.post_distances()] if self.pillared else []

    def end(self):
        return self.along(self.length)

    def segment(self):
        """Tiles a segment repeats over in assemble(): from post to post, or one tile for a wall."""
        return self.posts_every if self.posts_every > 0 else 1

    def collision(self):
        """The blocking box (x, y, w, h) in tiles on the raster: a band of COLLISION_THICKNESS along the run.

        A horizontal piece's band takes in the half of each end post beyond its run (END_POST_HALF), so a
        gate between two pieces is no wider than it looks; a vertical one's ends lie under those posts."""
        half = COLLISION_THICKNESS / 2
        x, y = self.start
        if self.orientation == HORIZONTAL:
            return x - END_POST_HALF, y - half, self.length + 2 * END_POST_HALF, COLLISION_THICKNESS
        return x - half, y, COLLISION_THICKNESS, self.length

    def tiled_properties(self):
        """The Tiled properties of a "Fence_Frontal" point at the raster's bottom-left corner.

        The collision box is anchored at the point (house.py): Collision_to_right x Collision_up whole
        tiles, moved by the margins in pixels. Here it is worked back from collision()."""
        x, y, w, h = (round(v * TILE) for v in self.collision())
        raster_w, raster_h = self.pixels
        tiles_right = max(1, -(-w // TILE))
        tiles_up = max(1, -(-h // TILE))
        down = (y + h) - raster_h                      # bottom = point + down
        left = -x                                      # left = point - left margin
        right = w - tiles_right * TILE - left
        up = h - tiles_up * TILE - down
        return {'Tiles_to_right': raster_w // TILE, 'Tiles_up': raster_h // TILE,
                'Collision_to_right': tiles_right, 'Collision_up': tiles_up,
                'Col_margin_left_pixel': left, 'Col_margin_right_pixel': right,
                'Col_margin_up_pixel': up, 'Col_margin_down_pixel': down}


def lengths_offered(posts_every):
    """The lengths a piece can have so its posts keep their spacing: multiples of posts_every."""
    step = posts_every if posts_every > 0 else 1
    return list(range(step, MAX_LENGTH + 1, step))


# ---------------------------------------------------------------------------
# Styles and pieces
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Piece:
    style: 'FenceStyle'
    orientation: str
    length: int

    @property
    def key(self):
        """'h4': in its file name, and the pose its answers are booked under."""
        return f'{self.orientation}{self.length}'

    pose = key

    @property
    def title(self):
        return f'{ORIENTATION_TITLES[self.orientation]} {self.length}'

    @property
    def name(self):
        """What the answers screen calls it."""
        return f'{self.style.title} {self.title.lower()}'

    @property
    def raster(self):
        return Raster(self.orientation, self.length, self.style.height, self.style.posts_every)

    @property
    def path(self):
        return self.style.folder / f'{self.style.name}_{self.key}.png'

    @property
    def file_name(self):
        """Its File_name in Tiled, relative to houses/."""
        return f'{FENCES_DIR.name}/{self.style.name}/{self.path.name}'

    def exists(self):
        return self.path.is_file()

    def sprite(self):
        """The piece as saved, or None.

        Its canvas is its raster; one that is not (drawn by hand) is put on it by its bottom-left corner."""
        try:
            image = pygame.image.load(str(self.path)).convert_alpha()
        except (pygame.error, OSError):
            return None
        size = self.raster.pixels
        if image.get_size() != size:
            canvas = pygame.Surface(size, pygame.SRCALPHA)
            canvas.blit(image, (0, size[1] - image.get_height()))
            image = canvas
        return image

    def save(self, surface):
        """Save the piece on its raster's canvas; True if it replaced one.

        Raises:
            pygame.error, OSError: If it cannot be written.
        """
        replaced = self.path.is_file()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        canvas = pygame.Surface(self.raster.pixels, pygame.SRCALPHA)
        canvas.blit(surface, (0, 0))
        pygame.image.save(canvas, str(self.path))
        return replaced

    def tiled_hint(self):
        """The status line after saving: the object's Tiled properties."""
        props = self.raster.tiled_properties()
        listed = ', '.join(f'{k} {v}' for k, v in props.items() if v or k.startswith(('Tiles', 'Collision')))
        return f'Tiled: a Fence_Frontal point at its bottom-left corner, File_name {self.file_name}, {listed}'


def _tiles(value):
    """A number of tiles from fence.json, whole if it is."""
    value = float(value)
    return int(value) if value.is_integer() else value


_PIECE_FILE = re.compile(r'^(?P<style>.+)_(?P<o>[hv])(?P<n>\d+)$')


class FenceStyle:
    """One kind of fence or wall: its fence.json and its pieces."""

    is_new = False
    is_player = False

    def __init__(self, folder, data):
        self.folder = Path(folder)
        self.name = self.folder.name
        self.title = str(data.get('title') or self.name.replace('_', ' ').title())
        material = data.get('material', DEFAULT_MATERIAL)
        self.material = MATERIALS_BY_KEY.get(material, MATERIALS_BY_KEY[DEFAULT_MATERIAL])
        self.description = str(data.get('description', ''))
        self.posts_every = max(0, int(data.get('posts_every', self.material.posts_every)))
        height = int(data.get('height', DEFAULT_HEIGHT))
        self.height = height if height >= 2 else DEFAULT_HEIGHT
        # The draft's colours, which name the fence's colours in the prompt: its own, else its material's
        colours = data.get('colours') or {}
        self.own_colours = {k: tuple(colours[k]) for k in ('post', 'body') if k in colours}
        # Where its pieces go, for the style screen's picture: [[orientation, length, x, y]], each piece's first
        # post in tiles (a layout to judge them by; the map itself is laid out in Tiled)
        self.plan = [(str(o), int(n), _tiles(x), _tiles(y)) for o, n, x, y in data.get('plan', ())
                     if o in ORIENTATIONS]
        lengths = data.get('lengths') or self.material.lengths
        self.lengths = {o: sorted({int(n) for n in lengths.get(o, ()) if 0 < int(n) <= MAX_LENGTH})
                        for o in ORIENTATIONS}

    # --- as the tool's other subjects ---------------------------------------

    @property
    def prefix(self):
        """Answers are named <prefix>_<pose>_web.png."""
        return self.name

    @property
    def out_dir(self):
        return FENCES_OUTPUT / self.name

    # --- pieces -------------------------------------------------------------

    def piece(self, orientation, length):
        return Piece(self, orientation, length)

    def drawn_lengths(self, orientation):
        """The lengths of the pieces on disk, whether wanted or not."""
        found = set()
        for path in self.folder.glob(f'{self.name}_{orientation}*.png'):
            match = _PIECE_FILE.match(path.stem)
            if match and match['style'] == self.name and match['o'] == orientation:
                found.add(int(match['n']))
        return found

    def pieces(self, orientation=None):
        """Every piece wanted or drawn, horizontal ones first, short ones first."""
        orientations = ORIENTATIONS if orientation is None else (orientation,)
        return [self.piece(o, n) for o in orientations
                for n in sorted(set(self.lengths[o]) | self.drawn_lengths(o))]

    def done(self, orientation=None):
        return sum(p.exists() for p in self.pieces(orientation) if p.length in self.lengths[p.orientation])

    def needed(self, orientation=None):
        orientations = ORIENTATIONS if orientation is None else (orientation,)
        return sum(len(self.lengths[o]) for o in orientations)

    def thumb_sprite(self):
        """The longest horizontal piece drawn, else the longest vertical one; None if none."""
        for orientation in ORIENTATIONS:
            drawn = [p for p in self.pieces(orientation) if p.exists()]
            if drawn:
                return drawn[-1].sprite()
        return None

    # --- changing it ----------------------------------------------------------

    @property
    def post_colour(self):
        return self.own_colours.get('post', self.material.post_colour)

    @property
    def body_colour(self):
        return self.own_colours.get('body', self.material.body_colour)

    def to_dict(self):
        data = {'title': self.title, 'material': self.material.key, 'description': self.description,
                'posts_every': self.posts_every, 'height': self.height,
                'lengths': {o: list(self.lengths[o]) for o in ORIENTATIONS}}
        if self.own_colours:
            data['colours'] = {k: list(v) for k, v in self.own_colours.items()}
        if self.plan:
            data['plan'] = [[o, n, x, y] for o, n, x, y in self.plan]
        return data

    def save(self):
        """Write fence.json.

        Raises:
            OSError: If it cannot be written.
        """
        self.folder.mkdir(parents=True, exist_ok=True)
        (self.folder / FENCE_FILE).write_text(json.dumps(self.to_dict(), indent=1) + '\n', encoding='utf-8')

    def toggle_length(self, orientation, length):
        """Want a piece of that length, or no longer want it (its sprite, if drawn, stays)."""
        lengths = set(self.lengths[orientation])
        lengths ^= {length}
        self.lengths[orientation] = sorted(lengths)

    def set_posts_every(self, every):
        """Space the posts anew; lengths that no longer fit the spacing are dropped from the list."""
        self.posts_every = every
        offered = set(lengths_offered(every))
        for orientation in ORIENTATIONS:
            self.lengths[orientation] = [n for n in self.lengths[orientation] if n in offered]

    def set_material(self, key):
        """Another material; the posts take its spacing."""
        self.material = MATERIALS_BY_KEY[key]
        self.set_posts_every(self.material.posts_every)


def create_style(title, description='', material=DEFAULT_MATERIAL):
    """Make a new style's folder and fence.json; returns the FenceStyle.

    Raises:
        ValueError: If the title makes no name, or the style exists.
        OSError: If it cannot be written.
    """
    name = style_folder_name(title)
    if not name:
        raise ValueError('Type a name.')
    folder = FENCES_DIR / name
    if folder.exists():
        raise ValueError(f'fences/{name}/ exists already.')
    chosen = MATERIALS_BY_KEY.get(material, MATERIALS_BY_KEY[DEFAULT_MATERIAL])
    style = FenceStyle(folder, {'title': title.strip(), 'material': chosen.key,
                                'description': description.strip() or chosen.description})
    style.save()
    return style


def find_styles():
    """Every style with a fence.json, by title; a broken one is skipped."""
    styles = []
    if FENCES_DIR.is_dir():
        for folder in sorted(FENCES_DIR.iterdir()):
            try:
                data = json.loads((folder / FENCE_FILE).read_text(encoding='utf-8'))
                styles.append(FenceStyle(folder, data))
            except (OSError, ValueError, TypeError, AttributeError):
                continue
    return sorted(styles, key=lambda s: s.title.lower())


# ---------------------------------------------------------------------------
# What a piece is drawn from
# ---------------------------------------------------------------------------

SAME_RUN, TURNED, OTHER_STYLE = 'length', 'turned', 'other style'
MODE_TITLES = {SAME_RUN: 'Another length of this style',
               TURNED: 'This style turned',
               OTHER_STYLE: 'Another style, for the look only'}


@dataclass(frozen=True)
class OldReference:
    """A cut of the walls drawn by hand before the pieces, for a first piece's look.

    `parts` are sprite files of houses/ put together as they stand on the map, each at its offset; the cut is
    taken out of them and put on the reference's raster at `at`, so that its corner or gate end stands where
    a piece's end post would."""

    key: str
    title: str
    parts: tuple          # ((file, (x, y)), ...)
    orientation: str
    length: int
    cut: tuple            # (x, y, w, h) of the parts put together
    at: tuple             # where the cut goes on the raster
    what: str = ''        # what it shows, for the prompt and the tool
    material: str = 'stone'
    description: str = 'a low wall of rough grey fieldstones'
    rank: int = 0         # the lower, the sooner it is offered: the yard's walls before the field wall


# The yard north of the market: Fence_4 (its top wall, corners and a gate) over Fence_3 (its long sides)
_OLD_YARD = (('Fence_4.png', (0, 0)), ('Fence_3.png', (0, 192)))
OLD_REFERENCES = (
    OldReference('yard_corner_gate', 'Yard wall', _OLD_YARD, HORIZONTAL, 5, (17, 0, 192, 56), (0, 8),
                 'the top wall of a walled yard from its corner on the left to a gate opening on the right'),
    OldReference('yard_gate_corner', 'Yard wall', _OLD_YARD, HORIZONTAL, 9, (265, 0, 320, 56), (0, 8),
                 'the top wall of a walled yard from a gate opening on the left to its corner on the right'),
    OldReference('yard_side', 'Yard wall', _OLD_YARD, VERTICAL, 11, (1, 38, 64, 400), (0, 16),
                 'the side wall of a walled yard, running straight down the picture, with no pillars'),
    OldReference('old_wall_h', 'Old stone wall', (('Fence_2.png', (0, 0)),), HORIZONTAL, 4, (16, 8, 160, 56),
                 (0, 0), 'a stretch of a field wall', rank=1),
    OldReference('old_wall_v', 'Old stone wall', (('Fence_3.png', (0, 0)),), VERTICAL, 4, (0, 0, 64, 176),
                 (0, 16), 'a stretch of a side wall, with no pillars', rank=1),
)


@dataclass(frozen=True)
class Reference:
    """The piece a piece is drawn from: of a style, or an OldReference."""

    piece: object = None      # Piece
    old: object = None        # OldReference

    @property
    def key(self):
        """'wattle_fence_h4', 'old_wall_h': in file names and sketches.json."""
        return self.old.key if self.old else f'{self.piece.style.name}_{self.piece.key}'

    @property
    def orientation(self):
        return (self.old or self.piece).orientation

    @property
    def length(self):
        return (self.old or self.piece).length

    @property
    def height(self):
        return DEFAULT_HEIGHT if self.old else self.piece.style.height

    @property
    def style_title(self):
        return self.old.title if self.old else self.piece.style.title

    @property
    def description(self):
        return self.old.description if self.old else self.piece.style.description

    @property
    def material(self):
        return MATERIALS_BY_KEY[self.old.material] if self.old else self.piece.style.material

    @property
    def raster(self):
        if self.old:
            return Raster(self.old.orientation, self.old.length, DEFAULT_HEIGHT, 0)
        return self.piece.raster

    @property
    def path(self):
        return HOUSES_DIR / self.old.parts[0][0] if self.old else self.piece.path

    @property
    def what(self):
        """What the reference shows beyond a straight run, for the prompt; '' for a piece of a style."""
        return self.old.what if self.old else ''

    def label(self):
        """'Horizontal 4', or 'Old stone wall h4'."""
        if self.old:
            return f'{self.old.title} {self.old.orientation}{self.old.length}'
        return self.piece.title

    def load(self):
        """The reference on its raster, at the game's scale.

        Raises:
            pygame.error, OSError: If its file cannot be read.
        """
        if self.old is None:
            sprite = self.piece.sprite()
            if sprite is None:
                raise OSError(f'{self.piece.path.name} is gone')
            return sprite
        x, y, w, h = self.old.cut
        source = pygame.Surface((w, h), pygame.SRCALPHA)
        for file, (px, py) in self.old.parts:
            source.blit(pygame.image.load(str(HOUSES_DIR / file)).convert_alpha(), (px - x, py - y))
        canvas = pygame.Surface(self.raster.pixels, pygame.SRCALPHA)
        canvas.blit(source, self.old.at)
        return canvas


def mode_of(piece, reference):
    """SAME_RUN, TURNED or OTHER_STYLE: what drawing `piece` from `reference` is."""
    if reference.old or reference.piece.style.name != piece.style.name:
        return OTHER_STYLE
    return SAME_RUN if reference.orientation == piece.orientation else TURNED


def reference_options(piece, styles=()):
    """{mode: [Reference]} of every piece `piece` can be drawn from, the modes that have one.

    This style's other lengths, the nearest first; this style turned, the
    nearest length first; then the other styles' pieces running the same way
    and the old walls, those of the same material first.
    """
    style = piece.style

    def nearest(p):
        return abs(p.length - piece.length), p.length

    same = sorted((p for p in style.pieces(piece.orientation) if p.exists() and p.length != piece.length),
                  key=nearest)
    if piece.exists():
        same.insert(0, piece)                   # drawn anew from itself
    other_way = VERTICAL if piece.orientation == HORIZONTAL else HORIZONTAL
    turned = sorted((p for p in style.pieces(other_way) if p.exists()), key=nearest)
    others = []
    for other in styles:
        if other.name == style.name:
            continue
        drawn = [p for p in other.pieces(piece.orientation) if p.exists()]
        if drawn:
            others.append(Reference(min(drawn, key=nearest)))
    others += [Reference(old=o) for o in OLD_REFERENCES if o.orientation == piece.orientation]
    # Those of the same material first (a stone wall looks to the old stone walls before a wooden fence),
    # then the nearest in length
    others.sort(key=lambda r: (r.material.key != style.material.key, r.old.rank if r.old else 0,
                               abs(r.length - piece.length), r.style_title.lower()))
    options = {SAME_RUN: [Reference(p) for p in same],
               TURNED: [Reference(p) for p in turned],
               OTHER_STYLE: others}
    return {mode: refs for mode, refs in options.items() if refs}


def default_reference(piece, styles=()):
    """The first of reference_options(): the nearest length of this style, else it turned, else another."""
    for refs in reference_options(piece, styles).values():
        return refs[0]
    return None


# ---------------------------------------------------------------------------
# Assembling a piece from another length
# ---------------------------------------------------------------------------

def can_assemble(piece, source):
    """True if `piece` can be laid out of `source`'s segments: same style and way, other length, both whole
    segments long."""
    if source is None or not source.exists() or source.style.name != piece.style.name:
        return False
    if source.orientation != piece.orientation or source.length == piece.length:
        return False
    unit = piece.raster.segment()
    return piece.length % unit == 0 and source.length % unit == 0


def segment_order(count, available):
    """Which of the source's `available` segments each of `count` goes from: its own ends at the ends, the
    middle ones taken in turn between, so a longer piece does not repeat one segment over and over."""
    if count == 1:
        return [0]
    middle = list(range(1, available - 1)) or list(range(available))
    order = [0] + [middle[i % len(middle)] for i in range(count - 2)] + [available - 1]
    return order


def assemble(piece, source, sprite):
    """`piece` made of `source`'s segments: its start (with the first post), segments from post to post laid
    end to end, and its end (with the last post). Each post is cut through its middle, where all of them look
    alike, so the joins do not show.

    Args:
        sprite: The source piece on its raster.

    Returns:
        The new piece on its raster.
    """
    raster, src = piece.raster, source.raster
    unit = raster.segment() * TILE
    count, available = piece.length // raster.segment(), source.length // src.segment()
    canvas = pygame.Surface(raster.pixels, pygame.SRCALPHA)
    horizontal = piece.orientation == HORIZONTAL
    start = round((raster.start[0] if horizontal else raster.start[1]) * TILE)
    src_end = start + source.length * TILE
    src_w, src_h = src.pixels
    end_w = (src_w if horizontal else src_h) - src_end

    def copy(src_from, length, to):
        if horizontal:
            canvas.blit(sprite, (to, 0), pygame.Rect(src_from, 0, length, src_h))
        else:
            canvas.blit(sprite, (0, to), pygame.Rect(0, src_from, src_w, length))

    copy(0, start, 0)                                           # before the first post's middle
    for index, segment in enumerate(segment_order(count, available)):
        copy(start + segment * unit, unit, start + index * unit)
    copy(src_end, end_w, start + count * unit)                  # after the last post's middle
    return canvas
