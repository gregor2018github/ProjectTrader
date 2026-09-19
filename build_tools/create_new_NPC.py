"""Turn a Gemini result image into a finished NPC sprite.

Counterpart of create_new_pose.py. Gemini returns the sheet you gave it
with the empty cell filled in. Both layouts are understood:

    1x2 (first sprite of a new NPC)       2x2 (sheet from create_new_pose.py)
    +-----------+-----------+             +-----------+-----------+
    | player    | new NPC   |             | player    | NPC       |
    +-----------+-----------+             +-----------+-----------+
                                          | player    | new NPC   |
                                          | (pose)    | (pose)    |
                                          +-----------+-----------+

The tool finds the cells, cuts the player (reference) and the new NPC sprite
out of their white background, recognises which player pose the reference is,
and scales the NPC by the same factor that brings the reference back to the
size of the real player sprite. That keeps every NPC frame in proportion with
the player and with each other. The result is saved as a transparent PNG in
the player's canvas size, e.g. npcs/trader_vintner/vintner_front_static.png.

Run from anywhere:

    python build_tools/create_new_NPC.py

The window can be resized or maximised; F11 switches to full screen.

1. Pick the NPC. Folders in humans/npcs are grouped by their name:
   trader_<trade> for traders, <class>_<name> for townsfolk, e.g.
   poor_matilda (class: poor, commons, middling, nobility). The "+" card of a
   population class adds a new townsperson: choose woman or man, then type a
   name or roll the dice for a free one from medieval_names.py. Every name
   can be used only once. The folder gets an npc.json with name and gender.
2. Drop the Gemini image onto the window, or click "Open image".
3. Check the pose (it is detected, click another one to change it). Enclosed
   white areas (e.g. a gap between arm and body) stay white; click them in the
   preview to make them transparent, click again to undo.
4. Save (Enter). The Gemini image is kept in build_tools/output/<npc>/results/.
"""

import json
import shutil
import sys
from pathlib import Path

import pygame

sys.path.insert(0, str(Path(__file__).resolve().parent))
from create_new_pose import (  # noqa: E402
    BG, BUTTON_BG, CARD_BG, CARD_GAP, CARD_HOVER, CARD_SIZE, DONE_COLOR, FOOTER_HEIGHT,
    HEADER_HEIGHT, NPC_DIR, OUTPUT_DIR, PLAYER_DIR, ROOT, TEXT, TEXT_DIM, THUMB_BG, THUMB_SIZE,
    Button, Card, find_base, make_thumb, open_window, toggle_fullscreen, window_size,
)
from medieval_names import gender_of, random_name  # noqa: E402

# Cell detection
DARK_TOLERANCE = 70      # a pixel darker than this in every channel counts as frame line
LINE_FILL = 0.85         # share of a row/column that must be dark to be a frame line
BORDER_ZONE = 0.08       # outer frame lines are searched in this share of each edge
CELL_INSET = 0.012       # at most this much frame leftover is trimmed off a cell edge (share of its smaller side)

# Background removal
WHITE_TOLERANCE = 24     # every channel above 255 - this counts as background white
FRINGE_TOLERANCE = 60    # light pixels next to the background are eaten as anti-alias fringe
FRINGE_PASSES = 2
FRAME_RED = (220, 20, 20)  # the red target frame, in case Gemini draws it too
RED_TOLERANCE = 70
SPECK_RATIO = 0.005      # blobs smaller than this share of the largest blob are dropped

POSE_MATCH_SIZE = (32, 52)

# Layout of the import screen (the panels grow with the window, see panel_rects)
POSE_PANEL_WIDTH = 240
SOURCE_SHARE = 0.54      # share of the remaining width for the Gemini image
PANEL_GAP = 20
POSE_ROW = 27
CHECKER = ((200, 200, 200), (170, 170, 170))
CHECKER_SIZE = 12
REF_COLOR = (80, 200, 110)
TARGET_COLOR = (220, 60, 60)
ERROR_COLOR = (240, 110, 90)

# NPC groups on the start screen: (folder name start, title, can add new ones)
CATEGORIES = (
    ('trader', 'Traders', False),
    ('poor', 'Poor', True),
    ('commons', 'Commons', True),
    ('middling', 'Middling Sort', True),
    ('nobility', 'Nobility', True),
)
OTHER = ('other', 'Other folders', False)
GENDERS = (('female', 'Woman'), ('male', 'Man'))
SECTION_HEADER = 42
NAME_MAX_LENGTH = 16
PROFILE_FILE = 'npc.json'   # name and gender of a townsperson, in their folder
DIE_COLOR = (240, 236, 228)
PIP_COLOR = (60, 50, 40)
DIALOG_SIZE = (520, 290)
INPUT_BG = (30, 28, 26)


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

def panel_rects():
    """(source, compare, pose) panel rects of the import screen for the current window."""
    width, height = window_size()
    top = HEADER_HEIGHT + 10
    panel_h = max(200, height - HEADER_HEIGHT - FOOTER_HEIGHT - 20)
    free = max(400, width - POSE_PANEL_WIDTH - 4 * PANEL_GAP)
    source_w = int(free * SOURCE_SHARE)
    source = pygame.Rect(PANEL_GAP, top, source_w, panel_h)
    compare = pygame.Rect(source.right + PANEL_GAP, top, free - source_w, panel_h)
    pose = pygame.Rect(compare.right + PANEL_GAP, top, POSE_PANEL_WIDTH, panel_h)
    return source, compare, pose


class Npc:
    def __init__(self, folder):
        self.folder = folder
        self.name = folder.name
        first = folder.name.split('_', 1)[0]
        keys = [key for key, _, _ in CATEGORIES]
        self.category = first if first in keys else OTHER[0]
        self.is_townsperson = self.category not in ('trader', OTHER[0])
        base = find_base(folder)
        # No sprite yet: 'trader_vintner' -> 'vintner', 'poor_matilda' -> 'matilda'
        self.prefix = base[1] if base else folder.name.rsplit('_', 1)[-1]

        self.display_name = self.prefix.capitalize()
        self.gender = None
        if self.is_townsperson:
            profile = read_profile(folder)
            self.display_name = profile.get('name', self.display_name)
            self.gender = profile.get('gender') or gender_of(self.prefix)

    @property
    def label(self):
        """Card label: the folder for traders, the name for townsfolk."""
        return self.display_name if self.is_townsperson else self.name

    @property
    def title(self):
        if self.is_townsperson:
            details = [dict(GENDERS)[self.gender].lower()] if self.gender else []
            return f'{self.display_name} ({", ".join(details + [self.category])})'
        return self.name

    @property
    def base_path(self):
        """First standing sprite, used as thumbnail; None if there is none."""
        base = find_base(self.folder)
        return self.sprite_path(base[0]) if base else None

    def sprite_path(self, pose):
        return self.folder / f'{self.prefix}_{pose}.png'


def read_profile(folder):
    try:
        return json.loads((folder / PROFILE_FILE).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def find_npcs():
    return [Npc(p) for p in sorted(NPC_DIR.iterdir()) if p.is_dir()]


def find_player_poses():
    """Return {pose: path} for every player sprite, standing poses first."""
    poses = {path.stem[len('player_'):]: path for path in PLAYER_DIR.glob('player_*.png')}
    return dict(sorted(poses.items(), key=lambda item: ('static' not in item[0], item[0])))


# ---------------------------------------------------------------------------
# Cell detection
# ---------------------------------------------------------------------------

def line_fill(dark, length, vertical):
    """Share of dark pixels in every column (vertical) or row of `dark`."""
    w, h = dark.get_size()
    if vertical:
        return [pygame.transform.average_color(dark, (i, 0, 1, h))[0] / 255 for i in range(length)]
    return [pygame.transform.average_color(dark, (0, i, w, 1))[0] / 255 for i in range(length)]


def dark_runs(fills, start, end):
    """Runs [a, b) of consecutive frame lines within [start, end)."""
    runs, run_start = [], None
    for i in range(start, end + 1):
        is_line = i < end and fills[i] >= LINE_FILL
        if is_line and run_start is None:
            run_start = i
        elif not is_line and run_start is not None:
            runs.append((run_start, i))
            run_start = None
    return runs


def split_axis(fills, length):
    """Return (content_start, split_a, split_b, content_end) along one axis.

    split_a..split_b is the inner frame line; both are None if there is none.
    """
    zone = max(1, int(length * BORDER_ZONE))
    first = dark_runs(fills, 0, zone)
    last = dark_runs(fills, length - zone, length)
    start = first[-1][1] if first else 0
    end = last[0][0] if last else length

    inner = dark_runs(fills, int(length * 0.3), int(length * 0.7))
    if not inner:
        return start, None, None, end
    a, b = min(inner, key=lambda run: abs((run[0] + run[1]) / 2 - length / 2))
    return start, a, b, end


def find_cells(image):
    """Return (reference_rect, target_rect, layout) for a Gemini result."""
    w, h = image.get_size()
    dark = pygame.mask.from_threshold(
        image, (0, 0, 0, 255), (DARK_TOLERANCE, DARK_TOLERANCE, DARK_TOLERANCE, 255)).to_surface()
    left, col_a, col_b, right = split_axis(line_fill(dark, w, True), w)
    top, row_a, row_b, bottom = split_axis(line_fill(dark, h, False), h)

    if col_a is None:  # no visible middle line: split in the middle
        col_a = col_b = (left + right) // 2
    if row_a is None:
        layout = '1x2'
        ref = pygame.Rect(left, top, col_a - left, bottom - top)
        target = pygame.Rect(col_b, top, right - col_b, bottom - top)
    else:
        layout = '2x2'
        ref = pygame.Rect(left, row_b, col_a - left, bottom - row_b)
        target = pygame.Rect(col_b, row_b, right - col_b, bottom - row_b)

    # Everything that is not near-white: frame lines plus their blurry edges.
    t = FRINGE_TOLERANCE
    ink = pygame.mask.from_threshold(image, (255, 255, 255, 255), (t, t, t, 255))
    ink.invert()
    ink = ink.to_surface()
    return trim_frame(ink, ref), trim_frame(ink, target), layout


def trim_frame(ink, rect):
    """Shrink `rect` past leftovers of the frame lines along its edges.

    Only rows/columns that are mostly ink are removed, so a sprite that
    reaches right down to the frame keeps its feet.
    """
    limit = int(min(rect.size) * CELL_INSET) + 3

    def fill(r):
        return pygame.transform.average_color(ink, r)[0] / 255

    rect = rect.copy()
    for _ in range(limit):
        if fill((rect.x, rect.y, rect.w, 1)) < LINE_FILL / 2:
            break
        rect.y += 1
        rect.h -= 1
    for _ in range(limit):
        if fill((rect.x, rect.bottom - 1, rect.w, 1)) < LINE_FILL / 2:
            break
        rect.h -= 1
    for _ in range(limit):
        if fill((rect.x, rect.y, 1, rect.h)) < LINE_FILL / 2:
            break
        rect.x += 1
        rect.w -= 1
    for _ in range(limit):
        if fill((rect.right - 1, rect.y, 1, rect.h)) < LINE_FILL / 2:
            break
        rect.w -= 1
    return rect


# ---------------------------------------------------------------------------
# Background removal
# ---------------------------------------------------------------------------

def dilate(mask):
    grown = mask.copy()
    for offset in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        grown.draw(mask, offset)
    return grown


class Extraction:
    """One cell of the Gemini image, cut out of its white background."""

    def __init__(self, cell_surface):
        self.surface = cell_surface
        w, h = cell_surface.get_size()
        t = WHITE_TOLERANCE
        self.background = pygame.mask.from_threshold(cell_surface, (255, 255, 255, 255), (t, t, t, 255))
        self.background.draw(pygame.mask.from_threshold(
            cell_surface, FRAME_RED + (255,), (RED_TOLERANCE, RED_TOLERANCE, RED_TOLERANCE, 255)), (0, 0))

        # Background = every background-coloured area connected to the cell edge.
        self.outside = pygame.Mask((w, h))
        edge = [(x, y) for x in range(w) for y in (0, h - 1)] + [(x, y) for y in range(h) for x in (0, w - 1)]
        for point in edge:
            if self.background.get_at(point) and not self.outside.get_at(point):
                self.outside.draw(self.background.connected_component(point), (0, 0))

        # Eat the light anti-alias fringe between the outline and the background.
        f = FRINGE_TOLERANCE
        light = pygame.mask.from_threshold(cell_surface, (255, 255, 255, 255), (f, f, f, 255))
        for _ in range(FRINGE_PASSES):
            self.outside.draw(light.overlap_mask(dilate(self.outside), (0, 0)), (0, 0))

        self.holes = []  # enclosed background areas the user made transparent
        self.update()

    def update(self):
        sprite = pygame.Mask(self.outside.get_size(), fill=True)
        sprite.erase(self.outside, (0, 0))
        for hole in self.holes:
            sprite.erase(hole, (0, 0))

        blobs = sprite.connected_components()
        self.mask = pygame.Mask(sprite.get_size())
        if blobs:
            largest = max(blob.count() for blob in blobs)
            for blob in blobs:
                if blob.count() >= largest * SPECK_RATIO:
                    self.mask.draw(blob, (0, 0))

        rects = self.mask.get_bounding_rects()
        self.bbox = rects[0].unionall(rects[1:]) if rects else None
        if self.bbox is None:
            self.sprite = None
            return
        rgba = self.surface.convert_alpha()
        alpha = self.mask.to_surface(setcolor=(255, 255, 255, 255), unsetcolor=(0, 0, 0, 0))
        rgba.blit(alpha, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        self.sprite = rgba.subsurface(self.bbox).copy()

    def toggle_hole(self, point):
        """Switch an enclosed white area at `point` (cell coordinates) on/off."""
        for hole in self.holes:
            if hole.get_at(point):
                self.holes.remove(hole)
                self.update()
                return True
        if self.background.get_at(point) and not self.outside.get_at(point):
            self.holes.append(self.background.connected_component(point))
            self.update()
            return True
        return False


def shape_mask(mask, rect):
    """Mask content inside `rect`, squeezed to POSE_MATCH_SIZE."""
    part = pygame.Mask(rect.size)
    part.draw(mask, (-rect.x, -rect.y))
    return part.scale(POSE_MATCH_SIZE)


def detect_pose(extraction, player_shapes):
    ref = shape_mask(extraction.mask, extraction.bbox)

    def similarity(shape):
        overlap = ref.overlap_area(shape, (0, 0))
        return overlap / max(1, ref.count() + shape.count() - overlap)

    return max(player_shapes, key=lambda pose: similarity(player_shapes[pose]))


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

class Result:
    """A loaded Gemini image and the sprite made from it."""

    def __init__(self, path, player_poses, player_shapes):
        self.path = Path(path)
        self.image = pygame.image.load(str(path)).convert()
        self.ref_rect, self.target_rect, self.layout = find_cells(self.image)
        self.ref = Extraction(self.image.subsurface(self.ref_rect).copy())
        self.target = Extraction(self.image.subsurface(self.target_rect).copy())
        if self.ref.bbox is None:
            raise ValueError('No player sprite found in the reference cell.')
        if self.target.bbox is None:
            raise ValueError('The target cell is empty.')
        self.player_poses = player_poses
        self.detected_pose = detect_pose(self.ref, player_shapes)
        self.pose = self.detected_pose
        self.build()

    def build(self):
        """Scale the NPC like the reference and place it on the player's canvas."""
        player = pygame.image.load(str(self.player_poses[self.pose])).convert_alpha()
        self.player = player
        content = player.get_bounding_rect()
        self.scale = content.height / self.ref.bbox.height

        sprite = self.target.sprite
        size = (max(1, round(sprite.get_width() * self.scale)), max(1, round(sprite.get_height() * self.scale)))
        scaled = pygame.transform.smoothscale(sprite, size)

        # Bottom-centred on the player's feet; the canvas grows if the NPC is bigger.
        x, y = content.centerx - size[0] // 2, content.bottom - size[1]
        cw, ch = player.get_size()
        left, top = min(0, x), min(0, y)
        right, bottom = max(cw, x + size[0]), max(ch, y + size[1])
        self.output = pygame.Surface((right - left, bottom - top), pygame.SRCALPHA)
        self.paste = (x - left, y - top)
        self.output.blit(scaled, self.paste)
        # Where the player canvas sits on the output canvas, for the side-by-side preview.
        self.player_offset = (-left, -top)

    def set_pose(self, pose):
        self.pose = pose
        self.build()

    def output_to_cell(self, point):
        """Map a point on the output canvas back to target cell coordinates."""
        x = (point[0] - self.paste[0]) / self.scale + self.target.bbox.x
        y = (point[1] - self.paste[1]) / self.scale + self.target.bbox.y
        return int(x), int(y)


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

def checkerboard(size):
    board = pygame.Surface(size)
    for y in range(0, size[1], CHECKER_SIZE):
        for x in range(0, size[0], CHECKER_SIZE):
            board.fill(CHECKER[(x // CHECKER_SIZE + y // CHECKER_SIZE) % 2], (x, y, CHECKER_SIZE, CHECKER_SIZE))
    return board


def fit(size, box):
    return min(box[0] / size[0], box[1] / size[1])


def ask_open_file():
    """Native file dialog (tkinter ships with Python)."""
    try:
        import tkinter
        from tkinter import filedialog
    except ImportError:
        return None
    root = tkinter.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    downloads = Path.home() / 'Downloads'
    path = filedialog.askopenfilename(
        title='Gemini result', initialdir=str(downloads if downloads.exists() else ROOT),
        filetypes=[('Images', '*.png *.jpg *.jpeg *.webp *.bmp'), ('All files', '*.*')])
    root.destroy()
    return path or None


class NewNpcDialog:
    """Asks for gender and name of a new townsperson."""

    def __init__(self, category, title, taken, fonts):
        """
        Args:
            category: Folder name start, e.g. 'poor'.
            title: Dialog heading.
            taken: {lower-case name: folder name} of every existing townsperson.
            fonts: (font, small, title_font).
        """
        self.category = category
        self.title = title
        self.taken = taken
        self.font, self.small, self.title_font = fonts
        self.gender = None
        self.name = ''
        self.error = ''
        self.rect = pygame.Rect((0, 0), DIALOG_SIZE)
        self.gender_buttons = [(key, Button(label, 0, 0, 120, 40)) for key, label in GENDERS]
        self.input_rect = pygame.Rect(0, 0, self.rect.w - 60 - 54, 40)
        self.dice_button = Button('', 0, 0, 44, 40)
        self.cancel_button = Button('Cancel', 0, 0, 120)
        self.create_button = Button('Create', 0, 0, 120)
        self.center()
        pygame.key.start_text_input()

    def center(self):
        """Place the dialog in the middle of the window."""
        width, height = window_size()
        self.rect.center = (width // 2, height // 2)
        x, y = self.rect.x + 30, self.rect.y + 80
        for i, (_, button) in enumerate(self.gender_buttons):
            button.rect.topleft = (x + i * 140, y)
        self.input_rect.topleft = (x, y + 80)
        self.dice_button.rect.topleft = (self.input_rect.right + 10, self.input_rect.y)
        self.cancel_button.rect.topleft = (self.rect.right - 290, self.rect.bottom - 58)
        self.create_button.rect.topleft = (self.rect.right - 150, self.rect.bottom - 58)

    def folder_name(self):
        return f'{self.category}_{self.name.lower()}'

    def validate(self):
        """Return an error message, or '' if the NPC can be created."""
        if not self.gender:
            return 'Choose woman or man.'
        if not self.name:
            return 'Type a name or roll the dice.'
        if self.name.lower() in self.taken:
            return f'{self.name.capitalize()} is already taken ({self.taken[self.name.lower()]}).'
        if (NPC_DIR / self.folder_name()).exists():
            return f'{self.folder_name()} already exists.'
        return ''

    def type_text(self, text):
        # Letters only: the name becomes part of the folder and file names.
        text = ''.join(c for c in text if c.isascii() and c.isalpha())
        self.name = (self.name + text)[:NAME_MAX_LENGTH]
        self.error = ''

    def roll(self):
        """Propose a random free name for the chosen gender."""
        if not self.gender:
            self.error = 'Choose woman or man first.'
            return
        name = random_name(self.gender, self.taken)
        if name is None:
            self.error = 'Every name in medieval_names.py is taken - type one.'
            return
        self.name = name
        self.error = ''

    def click(self, pos):
        """Return 'create', 'cancel' or None."""
        for key, button in self.gender_buttons:
            if button.hit(pos):
                self.gender = key
                self.error = ''
        if self.dice_button.hit(pos):
            self.roll()
        if self.cancel_button.hit(pos):
            return 'cancel'
        if self.create_button.hit(pos):
            return 'create'
        return None

    def draw_die(self, screen, mouse):
        self.dice_button.draw(screen, self.font, mouse)
        face = self.dice_button.rect.inflate(-14, -12)
        face.width = face.height
        face.center = self.dice_button.rect.center
        pygame.draw.rect(screen, DIE_COLOR, face, border_radius=5)
        step = face.width // 4
        for dx, dy in ((-1, -1), (1, -1), (0, 0), (-1, 1), (1, 1)):  # the five
            pygame.draw.circle(screen, PIP_COLOR, (face.centerx + dx * step, face.centery + dy * step), 3)

    def draw(self, screen, mouse):
        shade = pygame.Surface(window_size(), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 150))
        screen.blit(shade, (0, 0))
        pygame.draw.rect(screen, BG, self.rect, border_radius=10)
        pygame.draw.rect(screen, CARD_HOVER, self.rect, 2, border_radius=10)
        screen.blit(self.title_font.render(self.title, True, TEXT), (self.rect.x + 30, self.rect.y + 22))

        for key, button in self.gender_buttons:
            button.draw(screen, self.font, mouse)
            if key == self.gender:
                pygame.draw.rect(screen, DONE_COLOR, button.rect, 3, border_radius=6)

        label = self.small.render('Name  (type one, or roll the dice for a free one)', True, TEXT_DIM)
        screen.blit(label, (self.input_rect.x, self.input_rect.y - 22))
        pygame.draw.rect(screen, INPUT_BG, self.input_rect, border_radius=4)
        pygame.draw.rect(screen, CARD_HOVER, self.input_rect, 1, border_radius=4)
        cursor = '|' if pygame.time.get_ticks() // 500 % 2 else ''
        text = self.font.render(self.name.capitalize() + cursor, True, TEXT)
        screen.blit(text, text.get_rect(midleft=(self.input_rect.x + 10, self.input_rect.centery)))
        self.draw_die(screen, mouse)

        if self.error:
            message = self.small.render(self.error, True, ERROR_COLOR)
        elif self.gender and self.name:
            message = self.small.render(self.folder_name(), True, TEXT_DIM)
        else:
            message = None
        if message:
            # Errors can be long: they get their own line above the buttons.
            screen.blit(message, (self.rect.x + 30, self.cancel_button.rect.y - 26))
        self.cancel_button.draw(screen, self.font, mouse)
        self.create_button.draw(screen, self.font, mouse)


class ImportTool:
    def __init__(self):
        pygame.init()
        self.screen = open_window("Merchant's Rise - Gemini sprite import")
        self.font = pygame.font.SysFont('segoeui', 18)
        self.small = pygame.font.SysFont('segoeui', 15)
        self.title_font = pygame.font.SysFont('segoeui', 30, bold=True)
        self.clock = pygame.time.Clock()

        self.player_poses = find_player_poses()
        self.player_shapes = {}
        for pose, path in self.player_poses.items():
            sprite = pygame.image.load(str(path)).convert_alpha()
            mask = pygame.mask.from_surface(sprite)
            self.player_shapes[pose] = shape_mask(mask, sprite.get_bounding_rect())

        self.placeholder = pygame.Surface(THUMB_SIZE)
        self.placeholder.fill(THUMB_BG)
        text = self.small.render('no sprite yet', True, (120, 120, 120))
        self.placeholder.blit(text, text.get_rect(center=self.placeholder.get_rect().center))
        self.checker_compare = checkerboard((1, 1))  # rebuilt at panel size when drawn
        self.plus_thumb = pygame.Surface(THUMB_SIZE)
        self.plus_thumb.fill(CARD_BG)
        plus = pygame.font.SysFont('segoeui', 90).render('+', True, TEXT_DIM)
        self.plus_thumb.blit(plus, plus.get_rect(center=self.plus_thumb.get_rect().center))

        self.dialog = None
        self.refresh_npcs()
        self.npc = None
        self.result = None
        self.scroll = 0
        self.status = ''
        self.status_color = DONE_COLOR
        self.compare_layout = None

        self.back_button = Button('Back', 20, 0, 120)
        self.open_button = Button('Open image', 160, 0)
        self.save_button = Button('Save', 0, 0, 220)
        self.place_footer()

    def place_footer(self):
        """Put the footer buttons at the bottom of the window (again after a resize)."""
        self.screen = pygame.display.get_surface()
        width, height = window_size()
        for button in (self.back_button, self.open_button, self.save_button):
            button.rect.y = height - FOOTER_HEIGHT + 13
        self.save_button.rect.right = width - 20
        if self.dialog:
            self.dialog.center()

    # --- state ------------------------------------------------------------

    def make_npc_card(self, npc):
        thumb = make_thumb(npc.base_path) if npc.base_path else self.placeholder
        done = sum(npc.sprite_path(pose).exists() for pose in self.player_poses)
        note = f'{done}/{len(self.player_poses)} sprites'
        if npc.gender:
            note = f'{dict(GENDERS)[npc.gender].lower()}, {note}'
        return Card(npc, npc.label, thumb, note)

    def refresh_npcs(self):
        """Re-read the NPC folders and group their cards into sections."""
        self.npcs = find_npcs()
        self.sections = []  # (title, [cards])
        for key, title, can_add in CATEGORIES + (OTHER,):
            cards = [self.make_npc_card(n) for n in self.npcs if n.category == key]
            if can_add:
                cards.append(Card(('add', key, title), 'Add NPC', self.plus_thumb, 'woman or man'))
            if cards:
                self.sections.append((title, cards))
        self.section_titles = []  # (title, count, x, y), filled by layout_cards

    def open_new_dialog(self, key, title):
        taken = {n.prefix.lower(): n.name for n in self.npcs if n.is_townsperson}
        self.dialog = NewNpcDialog(key, f'New NPC: {title}', taken, (self.font, self.small, self.title_font))

    def create_npc(self):
        error = self.dialog.validate()
        if error:
            self.dialog.error = error
            return
        folder = NPC_DIR / self.dialog.folder_name()
        folder.mkdir()
        profile = {'name': self.dialog.name.capitalize(), 'gender': self.dialog.gender}
        (folder / PROFILE_FILE).write_text(json.dumps(profile, indent=2) + '\n', encoding='utf-8')
        self.dialog = None
        self.refresh_npcs()
        self.open_npc(next(n for n in self.npcs if n.folder == folder))
        self.set_status(f'Created {folder.relative_to(ROOT)}')

    def open_npc(self, npc):
        self.npc = npc
        self.result = None
        self.status = ''

    def back(self):
        self.refresh_npcs()
        self.npc = None
        self.result = None
        self.scroll = 0
        self.status = ''

    def set_status(self, text, error=False):
        self.status = text
        self.status_color = ERROR_COLOR if error else DONE_COLOR

    def load(self, path):
        try:
            self.result = Result(path, self.player_poses, self.player_shapes)
        except (pygame.error, ValueError) as error:
            self.result = None
            self.set_status(f'Could not use {Path(path).name}: {error}', error=True)
            return
        self.set_status(f'{self.result.layout} sheet, pose "{self.result.pose}" detected')

    def target_path(self):
        return self.npc.sprite_path(self.result.pose)

    def save(self):
        path = self.target_path()
        pygame.image.save(self.result.output, str(path))
        results_dir = OUTPUT_DIR / self.npc.name / 'results'
        results_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(self.result.path, results_dir / f'{self.npc.prefix}_{self.result.pose}_gemini{self.result.path.suffix}')
        self.set_status(f'Saved {path.relative_to(ROOT)}')

    # --- npc list ---------------------------------------------------------

    def all_cards(self):
        return [card for _, cards in self.sections for card in cards]

    def layout_cards(self):
        per_row = max(1, (window_size()[0] - CARD_GAP) // (CARD_SIZE[0] + CARD_GAP))
        row_w = per_row * CARD_SIZE[0] + (per_row - 1) * CARD_GAP
        left = (window_size()[0] - row_w) // 2
        top = HEADER_HEIGHT + CARD_GAP
        y = top - self.scroll
        self.section_titles = []
        for title, cards in self.sections:
            count = sum(1 for card in cards if isinstance(card.key, Npc))
            self.section_titles.append((title, count, left, y))
            y += SECTION_HEADER
            for i, card in enumerate(cards):
                row, col = divmod(i, per_row)
                card.rect.topleft = (left + col * (CARD_SIZE[0] + CARD_GAP), y + row * (CARD_SIZE[1] + CARD_GAP))
            rows = (len(cards) + per_row - 1) // per_row
            y += rows * (CARD_SIZE[1] + CARD_GAP) + CARD_GAP
        content_h = y + self.scroll - top
        return max(0, content_h - (window_size()[1] - HEADER_HEIGHT - FOOTER_HEIGHT))

    def draw_card(self, card, mouse):
        color = CARD_HOVER if card.rect.collidepoint(mouse) else CARD_BG
        pygame.draw.rect(self.screen, color, card.rect, border_radius=8)
        self.screen.blit(card.thumb, (card.rect.x + (CARD_SIZE[0] - THUMB_SIZE[0]) // 2, card.rect.y + 10))
        label = self.small.render(card.label, True, TEXT)
        self.screen.blit(label, label.get_rect(midtop=(card.rect.centerx, card.rect.y + THUMB_SIZE[1] + 16)))
        note = self.small.render(card.note, True, TEXT_DIM)
        self.screen.blit(note, note.get_rect(midtop=(card.rect.centerx, card.rect.y + THUMB_SIZE[1] + 34)))

    def draw_npc_list(self, mouse):
        clip = pygame.Rect(0, HEADER_HEIGHT, window_size()[0], window_size()[1] - HEADER_HEIGHT - FOOTER_HEIGHT)
        self.screen.set_clip(clip)
        for title, count, x, y in self.section_titles:
            text = self.font.render(title, True, TEXT)
            self.screen.blit(text, (x, y + 8))
            number = self.small.render(f'{count} NPC{"" if count == 1 else "s"}', True, TEXT_DIM)
            self.screen.blit(number, (x + text.get_width() + 12, y + 11))
            line_x = x + text.get_width() + number.get_width() + 24
            pygame.draw.line(self.screen, CARD_BG, (line_x, y + 21), (window_size()[0] - x, y + 21), 1)
        for card in self.all_cards():
            if card.rect.colliderect(clip):
                self.draw_card(card, mouse)
        self.screen.set_clip(None)

    # --- import screen ----------------------------------------------------

    def draw_panel_title(self, rect, text):
        label = self.small.render(text, True, TEXT_DIM)
        # Cut off at the panel edge rather than run into the next panel.
        self.screen.blit(label, (rect.x, rect.y - 2), pygame.Rect(0, 0, rect.w, label.get_height()))

    def draw_source(self):
        source_rect = panel_rects()[0]
        area = source_rect.inflate(0, -24).move(0, 12)
        pygame.draw.rect(self.screen, CARD_BG, area, border_radius=6)
        self.draw_panel_title(source_rect, 'Gemini image  (green = player, red = new sprite)')
        if not self.result:
            for i, line in enumerate(('Drop the Gemini image here', 'or click "Open image" (Ctrl+O)')):
                text = self.font.render(line, True, TEXT_DIM)
                self.screen.blit(text, text.get_rect(center=(area.centerx, area.centery - 14 + i * 28)))
            return
        image = self.result.image
        factor = fit(image.get_size(), (area.w - 16, area.h - 16))
        preview = pygame.transform.smoothscale(image, (int(image.get_width() * factor), int(image.get_height() * factor)))
        pos = preview.get_rect(center=area.center)
        self.screen.blit(preview, pos)
        for rect, color in ((self.result.ref_rect, REF_COLOR), (self.result.target_rect, TARGET_COLOR)):
            box = pygame.Rect(pos.x + rect.x * factor, pos.y + rect.y * factor, rect.w * factor, rect.h * factor)
            pygame.draw.rect(self.screen, color, box, 3)

    def draw_compare(self):
        compare_rect = panel_rects()[1]
        area = compare_rect.inflate(0, -24).move(0, 12)
        self.draw_panel_title(compare_rect, 'Player and new sprite at the same scale  (click white gaps)')
        if not self.checker_compare.get_rect().contains(pygame.Rect((0, 0), area.size)):
            self.checker_compare = checkerboard(area.size)
        self.screen.blit(self.checker_compare, area, pygame.Rect((0, 0), area.size))
        self.compare_layout = None
        if not self.result:
            return
        player, output = self.result.player, self.result.output
        gap = 20
        total = (player.get_width() + output.get_width() + gap, max(player.get_height(), output.get_height()))
        factor = min(fit(total, (area.w - 20, area.h - 50)), 1.5)
        pw, ph = int(player.get_width() * factor), int(player.get_height() * factor)
        ow, oh = int(output.get_width() * factor), int(output.get_height() * factor)
        baseline = area.bottom - 40
        start_x = area.centerx - int(total[0] * factor) // 2
        # Both canvases stand on the player's baseline.
        player_bottom = self.result.player_offset[1] + player.get_height()
        player_pos = (start_x, baseline - ph)
        output_pos = (start_x + pw + int(gap * factor), baseline - int(player_bottom * factor))
        self.screen.blit(pygame.transform.smoothscale(player, (pw, ph)), player_pos)
        self.screen.blit(pygame.transform.smoothscale(output, (ow, oh)), output_pos)
        pygame.draw.rect(self.screen, TEXT_DIM, (*output_pos, ow, oh), 1)
        self.compare_layout = (pygame.Rect(output_pos, (ow, oh)), factor)

        size = self.small.render(f'{output.get_width()} x {output.get_height()} px, scale {self.result.scale:.2f}',
                                 True, (40, 40, 40))
        self.screen.blit(size, size.get_rect(midbottom=(area.centerx, area.bottom - 10)))

    def pose_rows(self):
        pose_rect = panel_rects()[2]
        # Rows shrink in a small window so every pose stays visible.
        row = max(14, min(POSE_ROW, (pose_rect.h - 12) // max(1, len(self.player_poses))))
        return [(pose, pygame.Rect(pose_rect.x, pose_rect.y + 12 + i * row, pose_rect.w, row - 3))
                for i, pose in enumerate(self.player_poses)]

    def draw_poses(self, mouse):
        self.draw_panel_title(panel_rects()[2], 'Pose')
        for pose, rect in self.pose_rows():
            if self.result and pose == self.result.pose:
                color = BUTTON_BG
            elif self.result and rect.collidepoint(mouse):
                color = CARD_HOVER
            else:
                color = CARD_BG
            pygame.draw.rect(self.screen, color, rect, border_radius=4)
            label = self.small.render(pose, True, TEXT if self.result else TEXT_DIM)
            self.screen.blit(label, label.get_rect(midleft=(rect.x + 8, rect.centery)))
            notes = []
            if self.result and pose == self.result.detected_pose:
                notes.append('detected')
            if self.npc.sprite_path(pose).exists():
                notes.append('done')
            if notes:
                note = self.small.render(', '.join(notes), True, DONE_COLOR)
                self.screen.blit(note, note.get_rect(midright=(rect.right - 8, rect.centery)))

    def draw_import(self, mouse):
        self.draw_source()
        self.draw_compare()
        self.draw_poses(mouse)
        buttons = [self.back_button, self.open_button, self.save_button]
        self.save_button.enabled = self.result is not None
        if self.result:
            exists = self.target_path().exists()
            self.save_button.label = f'{"Overwrite" if exists else "Save"} {self.target_path().name}'
            text_w = self.font.size(self.save_button.label)[0] + 30
            self.save_button.rect.width = max(220, text_w)
            self.save_button.rect.right = window_size()[0] - 20
        else:
            self.save_button.label = 'Save'
        for button in buttons:
            button.draw(self.screen, self.font, mouse)

    # --- drawing ----------------------------------------------------------

    def draw(self):
        mouse = pygame.mouse.get_pos()
        self.screen.fill(BG)
        if self.npc:
            self.draw_import(mouse)
            title = f'2. Load a Gemini result for "{self.npc.title}"'
            hint = f'Sprites are saved as {self.npc.prefix}_<pose>.png in {self.npc.folder.relative_to(ROOT)}'
        else:
            self.draw_npc_list(mouse)
            title = '1. Choose the NPC'
            hint = f'Folders in {NPC_DIR.relative_to(ROOT)}. Click "+" to add a townsperson.'
        self.screen.blit(self.title_font.render(title, True, TEXT), (20, 12))
        self.screen.blit(self.small.render(hint, True, TEXT_DIM), (22, 56))
        if self.dialog:
            self.dialog.draw(self.screen, mouse)

        pygame.draw.line(self.screen, CARD_BG, (0, window_size()[1] - FOOTER_HEIGHT),
                         (window_size()[0], window_size()[1] - FOOTER_HEIGHT), 2)
        if self.status:
            status = self.small.render(self.status, True, self.status_color)
            pos = status.get_rect(midleft=(self.open_button.rect.right + 20, window_size()[1] - FOOTER_HEIGHT // 2))
            right = self.save_button.rect.x - 20 if self.npc else window_size()[0] - 20
            self.screen.blit(status, pos, pygame.Rect(0, 0, max(0, right - pos.x), status.get_height()))
        pygame.display.flip()

    # --- input ------------------------------------------------------------

    def click(self, pos):
        if not self.npc:
            if HEADER_HEIGHT <= pos[1] < window_size()[1] - FOOTER_HEIGHT:
                for card in self.all_cards():
                    if card.rect.collidepoint(pos):
                        if isinstance(card.key, Npc):
                            self.open_npc(card.key)
                        else:
                            self.open_new_dialog(*card.key[1:])
            return

        if self.back_button.hit(pos):
            self.back()
        elif self.open_button.hit(pos):
            self.open_dialog()
        elif self.save_button.hit(pos):
            self.save()
        elif self.result:
            for pose, rect in self.pose_rows():
                if rect.collidepoint(pos):
                    self.result.set_pose(pose)
                    return
            if self.compare_layout and self.compare_layout[0].collidepoint(pos):
                rect, factor = self.compare_layout
                point = self.result.output_to_cell(((pos[0] - rect.x) / factor, (pos[1] - rect.y) / factor))
                if self.result.target.surface.get_rect().collidepoint(point) and self.result.target.toggle_hole(point):
                    self.result.build()

    def dialog_event(self, event):
        action = None
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                action = 'cancel'
            elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                action = 'create'
            elif event.key == pygame.K_BACKSPACE:
                self.dialog.name = self.dialog.name[:-1]
        elif event.type == pygame.TEXTINPUT:
            self.dialog.type_text(event.text)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            action = self.dialog.click(event.pos)
        if action == 'cancel':
            self.dialog = None
        elif action == 'create':
            self.create_npc()

    def open_dialog(self):
        path = ask_open_file()
        if path:
            self.load(path)

    def run(self):
        while True:
            max_scroll = 0 if self.npc else self.layout_cards()
            self.scroll = min(self.scroll, max_scroll)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return
                if event.type == pygame.VIDEORESIZE:
                    self.place_footer()
                    continue
                if event.type == pygame.KEYDOWN and event.key == pygame.K_F11:
                    toggle_fullscreen()
                    self.place_footer()
                    continue
                if self.dialog:
                    self.dialog_event(event)
                    continue
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        if self.npc:
                            self.back()
                        else:
                            return
                    elif event.key == pygame.K_RETURN and self.npc and self.result:
                        self.save()
                    elif event.key == pygame.K_o and event.mod & pygame.KMOD_CTRL and self.npc:
                        self.open_dialog()
                elif event.type == pygame.DROPFILE and self.npc:
                    self.load(event.file)
                elif event.type == pygame.MOUSEWHEEL:
                    self.scroll = max(0, min(max_scroll, self.scroll - event.y * 60))
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self.click(event.pos)
            self.draw()
            self.clock.tick(30)


if __name__ == '__main__':
    ImportTool().run()
    pygame.quit()
