"""Make walk animations for NPC sprites from the base chibi's walk cycles.

For every frame of a walk cycle the tool builds a 2x2 reference sheet:

    +---------------------------+---------------------------+
    | chibi standing            | chibi walking, frame n    |
    | (Idle_Down / Idle_Up)     | (Walk_<strip>_Sheet)      |
    +---------------------------+---------------------------+
    | <npc>_front_static.png    | red frame: the same walk  |
    | (or _back_static.png)     | frame as a faint grey     |
    |                           | ghost, for the image      |
    |                           | model to draw the NPC on  |
    +---------------------------+---------------------------+

and the prompt that goes with it. The image model draws the NPC into the red
frame; the answer is cut out, scaled like the NPC's standing sprite and, once
accepted, saved as <prefix>_<direction>_move<n>.png in the NPC's folder -
the name the game loads walk frames by.

Run from anywhere:

    python build_tools/make_walk_animations/create_walk_sheet.py

The window can be resized or maximised; F11 switches to full screen.

1. Pick the NPC.
2. Pick a direction on the left. Its sheets are rebuilt from the base files
   every time a direction or a frame is clicked, so edits to the chibi or
   ghost strips show up straight away. The box under the directions plays
   the frames the NPC already has.
3. Pick a frame. If it is already done, the frame in the game is shown under
   its sheet next to the ghost it was aimed at, and laid over it. Then either
   - for free, through the Gemini web view: "Copy image" (Ctrl+C) and
     "Copy prompt" (Ctrl+Shift+C), paste both there, copy the answer and
     "Paste answer" (Ctrl+V) - or drop the image file onto the window, or
     "Open image" (Ctrl+O);
   - or through the API: "Send to Gemini" for this frame, or "Send missing"
     in the footer for every frame of the direction that is not done yet.
     "Settings" (S) chooses the model and size, as in create_new_pose.py.
4. Every answer opens for review: the image next to the frame it would
   become. "Accept" (Enter) saves the frame into the game, "Not good enough"
   (Del) keeps it on disk for later. "Review" lists every answer.

Directions: the chibi was drawn walking down, up, right, down-right and
up-right. The left-hand directions are those mirrored; the game mirrors
right-hand frames on its own for an NPC without left-hand ones, so they are
only needed where the NPC is not symmetrical.

Ghosts: Walk_<strip>_Sheet_Ghost.png is used where it exists. For the other
strips a ghost is made on the fly (outline black, skin in greys, face left
out); drawing one by hand gives the model a cleaner guide.

Sheets, prompts, answers and review.json live in build_tools/output/<npc>/walk/.
"""

import io
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pygame

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import gemini_client  # noqa: E402
import pose_review  # noqa: E402
import win_clipboard  # noqa: E402
from create_new_NPC import ask_open_file, read_profile, shape_mask  # noqa: E402
from create_new_pose import (  # noqa: E402
    BAR_BG, BG, CARD_BG, CARD_GAP, CARD_HOVER, CARD_SELECTED, DONE_COLOR, ERROR_COLOR,
    FOOTER_HEIGHT, HEADER_HEIGHT, NPC_CARD_SIZE, NPC_THUMB_SIZE, OUTPUT_DIR, PANEL_GAP,
    RESULT_CARD_SIZE, RESULT_THUMB_SIZE, ROOT, STATUS_COLORS, TEXT, TEXT_DIM, THUMB_BG,
    Button, Card, Detail, GeminiWorker, SettingsDialog, checkerboard, find_npcs, fit_text,
    make_thumb, measure, open_window, toggle_fullscreen, window_size,
)
from gemini_client import Settings, next_free_path  # noqa: E402
from pose_review import Entry, ReviewStore  # noqa: E402

# Base chibi: horizontal strips of 64x64 frames
CHIBI_DIR = HERE / 'base_Chibi'
IDLE_DIR = CHIBI_DIR / 'Idle'
WALK_DIR = CHIBI_DIR / 'Walk'
CHIBI_FRAME_SIZE = 64
GHOST_SUFFIX = '_Ghost'

# The NPC's standing pose the sheet starts from, and the chibi's match for it
BASE_POSES = {
    'front_static': ('Idle_Down', 'facing the viewer'),
    'back_static': ('Idle_Up', 'seen from behind'),
}
DEFAULT_BASE = 'front_static'
WALK_FOLDER = 'walk'
WEB_MODEL = 'web'   # what an answer pasted from the web view is recorded as


@dataclass(frozen=True)
class Direction:
    key: str          # the game's name for it: <prefix>_<key>_move<n>.png
    label: str
    strip: str        # Walk_<strip>_Sheet.png
    mirror: bool      # the chibi was drawn facing the other way
    motion: str       # how the prompt describes the walk
    from_behind: bool = False  # starts from the back view if the NPC has one

    def pose(self, frame):
        """'right_move3' for frame 3 (counted from 1, like the game)."""
        return f'{self.key}_move{frame}'


DIRECTIONS = (
    Direction('front', 'Down', 'Walk_Down', False,
              'walking towards the viewer, down the screen'),
    Direction('front_right', 'Down right', 'Walk_Down_Side', False,
              'seen three-quarters from the front, walking diagonally down and to the right'),
    Direction('right', 'Right', 'Walk_Side', False,
              'seen from the side, walking to the right'),
    Direction('back_right', 'Up right', 'Walk_Up_Side', False,
              'seen three-quarters from behind, walking diagonally up and to the right', True),
    Direction('back', 'Up', 'Walk_Up', False,
              'seen from behind, walking away from the viewer, up the screen', True),
    Direction('back_left', 'Up left', 'Walk_Up_Side', True,
              'seen three-quarters from behind, walking diagonally up and to the left', True),
    Direction('left', 'Left', 'Walk_Side', True,
              'seen from the side, walking to the left'),
    Direction('front_left', 'Down left', 'Walk_Down_Side', True,
              'seen three-quarters from the front, walking diagonally down and to the left'),
)
DIRECTION_BY_KEY = {d.key: d for d in DIRECTIONS}
# Where the game borrows a left-hand walk from when the NPC has none
MIRROR_OF = {'left': 'right', 'front_left': 'front_right', 'back_left': 'back_right'}

# Sheet appearance (same look as create_new_pose.py)
MARGIN_RATIO = 0.06
MIN_MARGIN = 16
FRAME_WIDTH = 4
FRAME_COLOR = (0, 0, 0)
TARGET_FRAME_COLOR = (220, 0, 0)
TARGET_FRAME_WIDTH = 3
GHOST_ALPHA = 110        # 0 = invisible, 255 = solid

# A ghost made on the fly, in the colours of the hand-drawn one
GHOST_LINE = (0, 0, 0)
GHOST_LEVELS = ((185, (179, 179, 179)), (215, (206, 206, 206)), (256, (234, 234, 234)))
OUTLINE_LUMA = 120       # darker than this is outline
FACE_SHARE = 0.5         # this top share of the figure is the head: drawn without a face

PROMPT_TEMPLATE = """\
The attached picture holds a 2x2 grid of pixel-art sprites for my medieval trading game "Merchant's Rise".

Top left: a plain, featureless chibi mannequin standing still, {base_view}.
Top right: the same mannequin in frame {frame} of {count} of a walk cycle, {motion}.
Bottom left: {name}, standing still, {base_view}, in the same pose as the mannequin top left.
Bottom right (red frame): a faint, see-through grey ghost of the mannequin in the same walking pose as top right. It is only a guide. Draw {name} over it, {motion}, so that the head, body, arms, legs and feet sit exactly where the ghost's are: same step, same position of the legs and arms, same lean of the body. No trace of the ghost may remain in the finished drawing.

The mannequin and the ghost show only the pose. Do not copy their proportions, bald head, skin or grey colour. Keep {name}'s own look from the bottom left sprite: proportions, head size, face, hair, headwear, clothing, colours and outline, and the same crisp pixel-art style with hard pixel edges and no anti-aliasing or blur.
Parts that the bottom left sprite does not show should follow on naturally from what it does show.
Keep {name} at the same size as in the bottom left, with the feet on the same ground line, on the plain white background. Do not draw anything outside the red frame and do not change the other three cells.
"""

# Layout
DIR_PANEL_W = 230
DIR_ROW = 34
SHEET_PANEL_MIN_W = 320
SHEET_PANEL_SHARE = 0.3
FRAME_CARD_SIZE = (172, 296)
FRAME_THUMB_SIZE = (150, 232)
BUTTON_H = 40
BUTTON_GAP = 10
PANEL_TITLE = 22
PREVIEW_FRAME_MS = 140
COMPARE_TILES = ('Goal', 'Accepted', 'Both')
COMPARE_PAD = 12
COMPARE_OVERLAY_ALPHA = 150
COMPARE_SHARE = 0.36     # share of the sheet panel the comparison takes, when shown
SELECTED_LINE = (230, 190, 80)


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

class WalkNpc:
    """An NPC folder, seen from this tool: its sprites and its walk output."""

    def __init__(self, npc):
        """
        Args:
            npc: A create_new_pose.Npc (a folder with a front standing sprite).
        """
        self.folder = npc.folder
        self.name = npc.name
        self.prefix = npc.prefix
        self.base_path = npc.base_path
        profile = read_profile(self.folder)
        if profile.get('name'):
            self.display_name = profile['name']
        elif self.name.startswith('trader_'):
            self.display_name = f'the {self.prefix}'
        else:
            self.display_name = self.prefix.capitalize()

    def sprite_path(self, pose):
        return self.folder / f'{self.prefix}_{pose}.png'

    @property
    def out_dir(self):
        """Sheets, prompts, answers and review.json of the walk frames."""
        return OUTPUT_DIR / self.name / WALK_FOLDER

    def base_for(self, direction):
        """The standing pose a direction's sheets start from."""
        if direction.from_behind and self.sprite_path('back_static').is_file():
            return 'back_static'
        return DEFAULT_BASE

    def done(self, direction, count):
        return sum(self.sprite_path(direction.pose(f)).is_file() for f in range(1, count + 1))


@dataclass
class FrameSheet:
    """One frame of a direction: its sheet, prompt and where they were written."""

    direction: Direction
    frame: int        # counted from 1
    count: int
    surface: pygame.Surface
    path: Path
    prompt: str
    auto_ghost: bool
    ghost: pygame.Surface   # the goal pose, at the scale of the saved frames

    @property
    def pose(self):
        return self.direction.pose(self.frame)


def parse_pose(pose):
    """'front_right_move3' -> (Direction, 3), or (None, 0) if it is not a walk frame."""
    key, _, number = pose.rpartition('_move')
    if key in DIRECTION_BY_KEY and number.isdigit():
        return DIRECTION_BY_KEY[key], int(number)
    return None, 0


# ---------------------------------------------------------------------------
# Chibi strips
# ---------------------------------------------------------------------------

def trim(surface):
    """Cut away the transparent border."""
    return surface.subsurface(surface.get_bounding_rect()).copy()


def scaled(surface, factor):
    w, h = surface.get_size()
    return pygame.transform.scale(surface, (w * factor, h * factor))


def strip_path(folder, name, ghost=False):
    return folder / f'{name}_Sheet{GHOST_SUFFIX if ghost else ""}.png'


def load_strip(path, mirror=False):
    """Every frame of a strip, trimmed, in order."""
    sheet = pygame.image.load(str(path)).convert_alpha()
    frames = []
    for index in range(sheet.get_width() // CHIBI_FRAME_SIZE):
        frame = sheet.subsurface((index * CHIBI_FRAME_SIZE, 0, CHIBI_FRAME_SIZE, CHIBI_FRAME_SIZE))
        if frame.get_bounding_rect().w:
            frame = trim(frame)
            frames.append(pygame.transform.flip(frame, True, False) if mirror else frame)
    return frames


def strip_length(direction):
    """How many frames the direction's walk cycle has."""
    image = pygame.image.load(str(strip_path(WALK_DIR, direction.strip)))
    return image.get_width() // CHIBI_FRAME_SIZE


def make_ghost(frame):
    """A grey, faceless version of a chibi frame, like the hand-drawn ghosts.

    The outline stays black and the skin tones of the body become three
    greys. The head is one flat grey: its inner lines and shading are the
    face, which would only tempt the model into copying it.
    """
    w, h = frame.get_size()
    ghost = pygame.Surface((w, h), pygame.SRCALPHA)
    face_limit = int(h * FACE_SHARE)

    def is_outside(x, y):
        return not (0 <= x < w and 0 <= y < h) or frame.get_at((x, y)).a == 0

    for y in range(h):
        for x in range(w):
            color = frame.get_at((x, y))
            if color.a == 0:
                continue
            luma = 0.299 * color.r + 0.587 * color.g + 0.114 * color.b
            if luma < OUTLINE_LUMA:
                on_edge = any(is_outside(x + dx, y + dy)
                              for dx in (-1, 0, 1) for dy in (-1, 0, 1))
                if on_edge or y >= face_limit:
                    ghost.set_at((x, y), GHOST_LINE)
                    continue
            if y < face_limit:
                luma = 255  # the head is one flat grey: no face, no shading
            ghost.set_at((x, y), next(grey for limit, grey in GHOST_LEVELS if luma < limit))
    return ghost


def ghost_frames(direction):
    """(frames, made_on_the_fly) of the direction's ghost strip."""
    path = strip_path(WALK_DIR, direction.strip, ghost=True)
    if path.is_file():
        return load_strip(path, direction.mirror), False
    return [make_ghost(f) for f in load_strip(strip_path(WALK_DIR, direction.strip),
                                              direction.mirror)], True


# ---------------------------------------------------------------------------
# Sheets and prompts
# ---------------------------------------------------------------------------

def build_sheet(idle, walk, ghost, npc):
    """Lay out the three sprites plus the red-framed target cell holding the ghost.

    Every sprite stands on the ground line of its cell, so the walk frame
    keeps the bob of the cycle and the ghost stands where the NPC will.

    Returns:
        (sheet, ghost) - the ghost solid, at the scale of the NPC sprite, which
        is also the scale an accepted frame is saved at.
    """
    # One scale for all chibi sprites, taken from the standing one, so every
    # frame of a cycle comes out the same size.
    factor = max(1, round(npc.get_height() / idle.get_height()))
    sprites = [scaled(idle, factor), scaled(walk, factor), npc]
    solid_ghost = scaled(ghost, factor)
    ghost = solid_ghost.copy()
    ghost.set_alpha(GHOST_ALPHA)

    max_w = max(s.get_width() for s in sprites + [ghost])
    max_h = max(s.get_height() for s in sprites + [ghost])
    margin = max(MIN_MARGIN, int(max(max_w, max_h) * MARGIN_RATIO))
    cell_w, cell_h = max_w + 2 * margin, max_h + 2 * margin

    sheet = pygame.Surface((2 * cell_w + 3 * FRAME_WIDTH, 2 * cell_h + 3 * FRAME_WIDTH))
    sheet.fill(FRAME_COLOR)
    cells = []
    for row in range(2):
        for col in range(2):
            rect = pygame.Rect(FRAME_WIDTH + col * (cell_w + FRAME_WIDTH),
                               FRAME_WIDTH + row * (cell_h + FRAME_WIDTH), cell_w, cell_h)
            sheet.fill((255, 255, 255), rect)
            cells.append(rect)

    for sprite, cell in zip(sprites + [ghost], cells):
        sheet.blit(sprite, sprite.get_rect(midbottom=(cell.centerx, cell.bottom - margin)))
    pygame.draw.rect(sheet, TARGET_FRAME_COLOR, cells[3], TARGET_FRAME_WIDTH)
    return sheet, solid_ghost


def prompt_for(npc, direction, frame, count):
    base_view = BASE_POSES[npc.base_for(direction)][1]
    return PROMPT_TEMPLATE.format(base_view=base_view, frame=frame, count=count,
                                  motion=direction.motion, name=npc.display_name)


def write_sheets(npc, direction, frames=None):
    """Build a direction's sheets from the base files and write them.

    Args:
        npc: The WalkNpc.
        direction: The Direction.
        frames: Frame numbers (from 1) to build; None builds them all.

    Returns:
        [FrameSheet], in frame order.
    """
    base = npc.base_for(direction)
    idle = load_strip(strip_path(IDLE_DIR, BASE_POSES[base][0]))[0]
    reference = trim(pygame.image.load(str(npc.sprite_path(base))).convert_alpha())
    walks = load_strip(strip_path(WALK_DIR, direction.strip), direction.mirror)
    ghosts, auto_ghost = ghost_frames(direction)
    count = len(walks)

    npc.out_dir.mkdir(parents=True, exist_ok=True)
    sheets = []
    for frame in frames or range(1, count + 1):
        surface, ghost = build_sheet(idle, walks[frame - 1], ghosts[min(frame, len(ghosts)) - 1],
                                     reference)
        stem = f'{npc.prefix}_{direction.pose(frame)}'
        path = npc.out_dir / f'{stem}_sheet.png'
        prompt = prompt_for(npc, direction, frame, count)
        pygame.image.save(surface, str(path))
        (npc.out_dir / f'{stem}_prompt.txt').write_text(prompt, encoding='utf-8')
        sheets.append(FrameSheet(direction, frame, count, surface, path, prompt, auto_ghost, ghost))
    return sheets


def reference_shapes(npc, pose, base):
    """({pose: path}, {pose: mask}) that make create_new_NPC's extraction scale
    the answer like the NPC's own standing sprite instead of the player."""
    path = npc.sprite_path(base)
    sprite = pygame.image.load(str(path)).convert_alpha()
    mask = shape_mask(pygame.mask.from_surface(sprite), sprite.get_bounding_rect())
    return {pose: path}, {pose: mask}


def comparison(ghost, sprite):
    """Goal, accepted frame and both on top of each other, as COMPARE_TILES tiles.

    The ghost and a saved frame are both at the scale of the NPC's standing
    sprite, so they are compared pixel for pixel: trimmed, standing on one
    ground line and centred alike. In the third tile the frame is see-through
    over the solid ghost, so it shows where the pose drifted from the goal.
    """
    ghost, sprite = trim(ghost), trim(sprite)
    tile_w = max(ghost.get_width(), sprite.get_width()) + 2 * COMPARE_PAD
    tile_h = max(ghost.get_height(), sprite.get_height()) + 2 * COMPARE_PAD
    overlay = sprite.copy()
    overlay.set_alpha(COMPARE_OVERLAY_ALPHA)
    layers = ((ghost,), (sprite,), (ghost, overlay))
    image = pygame.Surface((len(layers) * tile_w + (len(layers) - 1) * COMPARE_PAD, tile_h))
    image.fill(CARD_BG)
    for index, tile_layers in enumerate(layers):
        tile = pygame.Rect(index * (tile_w + COMPARE_PAD), 0, tile_w, tile_h)
        image.fill(THUMB_BG, tile)
        for layer in tile_layers:
            image.blit(layer, layer.get_rect(midbottom=(tile.centerx, tile.bottom - COMPARE_PAD)))
    return image


def fitted(surface, size, background=THUMB_BG):
    """A surface scaled into a tile of `size`, centred."""
    w, h = surface.get_size()
    factor = min(size[0] / w, size[1] / h)
    image = pygame.transform.smoothscale(surface, (max(1, int(w * factor)), max(1, int(h * factor))))
    tile = pygame.Surface(size)
    tile.fill(background)
    tile.blit(image, image.get_rect(center=tile.get_rect().center))
    return tile


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------

class WalkTool:
    def __init__(self):
        pygame.init()
        self.screen = open_window("Merchant's Rise - walk animations")
        self.font = pygame.font.SysFont('segoeui', 18)
        self.small = pygame.font.SysFont('segoeui', 15)
        self.title_font = pygame.font.SysFont('segoeui', 30, bold=True)
        self.clock = pygame.time.Clock()

        self.counts = {d.key: strip_length(d) for d in DIRECTIONS}
        self.npcs = [WalkNpc(n) for n in find_npcs()]
        self.npc_thumbs = {n.name: make_thumb(n.base_path, NPC_THUMB_SIZE) for n in self.npcs}
        self.settings = Settings.load()
        self.dialog = None

        self.view = 'npcs'
        self.return_view = 'frames'   # where the detail view goes back to
        self.npc = None
        self.store = None
        self.direction = DIRECTION_BY_KEY['right']
        self.sheets = []
        self.current = 0              # index into self.sheets
        self.npc_cards = []
        self.frame_cards = []
        self.result_cards = []
        self.detail = None
        self.preview = []             # the NPC's own frames of the direction
        self.preview_note = ''
        self.comparison = None        # accepted frame vs. goal, when there is one
        self.scroll = 0
        self.worker = None
        self.status = ''
        self.status_error = False
        self.checker = checkerboard((1, 1))
        self.preview_checker = checkerboard((1, 1))
        self.dir_rows = []

        self.back_button = Button('Back', w=90)
        self.folder_button = Button('Open folder', w=130)
        self.review_button = Button('Review', w=140)
        self.settings_button = Button('Settings', w=110)
        self.missing_button = Button('Send missing', w=220)
        self.reject_button = Button('Not good enough', w=190)
        self.regenerate_button = Button('Regenerate', w=150)
        self.accept_button = Button('Accept', w=150)
        self.copy_image_button = Button('Copy image', h=BUTTON_H)
        self.copy_prompt_button = Button('Copy prompt', h=BUTTON_H)
        self.paste_button = Button('Paste answer', h=BUTTON_H)
        self.open_button = Button('Open image', h=BUTTON_H)
        self.send_button = Button('Send to Gemini', h=BUTTON_H)
        self.build_npc_cards()
        self.place_footer()

    # --- footer -----------------------------------------------------------

    def footer_buttons(self):
        """(left cluster, right cluster) for the current view."""
        if self.view == 'frames':
            return ((self.back_button, self.folder_button, self.review_button),
                    (self.settings_button, self.missing_button))
        if self.view == 'review':
            return (self.back_button, self.folder_button), (self.settings_button,)
        if self.view == 'detail':
            return ((self.back_button, self.folder_button),
                    (self.reject_button, self.regenerate_button, self.accept_button))
        return (), (self.settings_button,)

    def place_footer(self):
        self.screen = pygame.display.get_surface()
        width, height = window_size()
        y = height - FOOTER_HEIGHT + 13
        left, right = self.footer_buttons()
        x = 20
        for button in left:
            button.rect.topleft = (x, y)
            x += button.rect.w + 12
        x = width - 20
        for button in reversed(right):
            button.rect.topright = (x, y)
            x -= button.rect.w + 12

    # --- state ------------------------------------------------------------

    def set_status(self, text, error=False):
        self.status = text
        self.status_error = error

    def set_view(self, view):
        self.view = view
        self.scroll = 0
        self.place_footer()

    def busy(self):
        return self.worker is not None and not self.worker.finished

    def total_frames(self):
        return sum(self.counts.values())

    def build_npc_cards(self):
        """One card per NPC, with how many walk frames he already has."""
        self.npc_cards = []
        total = self.total_frames()
        for npc in self.npcs:
            done = sum(npc.done(d, self.counts[d.key]) for d in DIRECTIONS)
            waiting = len(ReviewStore(npc.out_dir).pending())
            extra = [(f'{waiting} to review', STATUS_COLORS[pose_review.PENDING])] if waiting else []
            self.npc_cards.append(Card(
                npc, npc.name, self.npc_thumbs[npc.name],
                note=f'{done}/{total} walk frames',
                note_color=STATUS_COLORS[pose_review.ACCEPTED] if done == total else TEXT_DIM,
                extra=extra, progress=done / max(1, total), size=NPC_CARD_SIZE))

    def open_npc(self, npc):
        self.npc = npc
        self.store = ReviewStore(npc.out_dir)
        self.worker = None
        self.detail = None
        self.set_status('')
        self.set_view('frames')
        self.select_direction(self.direction)

    def select_direction(self, direction, frame_index=0):
        """Rebuild the direction's sheets from the base files and show them."""
        self.direction = direction
        try:
            self.sheets = write_sheets(self.npc, direction)
        except (pygame.error, OSError, IndexError) as exc:
            self.sheets = []
            self.set_status(f'Cannot build the {direction.label.lower()} sheets: {exc}', error=True)
        self.current = min(frame_index, max(0, len(self.sheets) - 1))
        self.scroll = 0
        self.build_frame_cards()
        self.load_preview()
        if self.sheets and self.sheets[0].auto_ghost and not self.status_error:
            ghost = strip_path(WALK_DIR, direction.strip, ghost=True).name
            self.set_status(f'Ghost made on the fly - draw {ghost} for a cleaner one')

    def rebuild_current(self):
        """Rebuild the chosen frame's sheet, so it matches the base files on disk."""
        sheet = self.current_sheet()
        if not sheet:
            return None
        try:
            fresh = write_sheets(self.npc, sheet.direction, [sheet.frame])[0]
        except (pygame.error, OSError, IndexError) as exc:
            self.set_status(f'Cannot rebuild the sheet: {exc}', error=True)
            return sheet
        self.sheets[self.current] = fresh
        self.build_frame_cards()
        return fresh

    def current_sheet(self):
        return self.sheets[self.current] if self.sheets else None

    def frame_note(self, pose):
        """(text, colour) of a frame's state."""
        if self.npc.sprite_path(pose).is_file():
            return 'done', STATUS_COLORS[pose_review.ACCEPTED]
        note = self.store.pose_note(pose)
        if note == 'rejected':
            return note, ERROR_COLOR
        return note, STATUS_COLORS[pose_review.PENDING]

    def build_frame_cards(self):
        self.frame_cards = []
        for index, sheet in enumerate(self.sheets):
            note, color = self.frame_note(sheet.pose)
            self.frame_cards.append(Card(
                index, f'Frame {sheet.frame}  ({sheet.pose})', fitted(sheet.surface, FRAME_THUMB_SIZE),
                note, note_color=color, size=FRAME_CARD_SIZE))
        self.build_comparison()

    def build_comparison(self):
        """The accepted frame next to its goal, if the chosen frame is done."""
        self.comparison = None
        sheet = self.current_sheet()
        path = self.npc.sprite_path(sheet.pose) if sheet else None
        if not (path and path.is_file()):
            return
        try:
            sprite = pygame.image.load(str(path)).convert_alpha()
        except pygame.error as exc:
            self.set_status(f'Cannot read {path.name}: {exc}', error=True)
            return
        if sprite.get_bounding_rect().w:
            self.comparison = comparison(sheet.ghost, sprite)

    def load_preview(self):
        """The frames the NPC already has for this direction, for the little player."""
        self.preview, self.preview_note = [], ''
        direction = self.direction
        count = self.counts[direction.key]
        paths = [self.npc.sprite_path(direction.pose(f)) for f in range(1, count + 1)]
        mirrored = False
        if not any(p.is_file() for p in paths) and direction.key in MIRROR_OF:
            # What the game shows: the right-hand walk, mirrored.
            source = DIRECTION_BY_KEY[MIRROR_OF[direction.key]]
            paths = [self.npc.sprite_path(source.pose(f)) for f in range(1, count + 1)]
            mirrored = True
        frames = []
        for path in paths:
            if path.is_file():
                image = pygame.image.load(str(path)).convert_alpha()
                frames.append(pygame.transform.flip(image, True, False) if mirrored else image)
        if not frames:
            self.preview_note = 'no frames yet'
            return
        # All frames share the standing sprite's canvas; crop them alike.
        rects = [f.get_bounding_rect() for f in frames if f.get_bounding_rect().w]
        box = rects[0].unionall(rects[1:]) if rects else frames[0].get_rect()
        self.preview = [f.subsurface(box.clip(f.get_rect())).copy() for f in frames]
        self.preview_note = f'{len(frames)}/{count} frames'
        if mirrored:
            self.preview_note += ', mirrored from right as in the game'

    def refresh(self):
        """Cards and preview after answers or accepted frames changed."""
        if self.view in ('frames', 'detail') and self.sheets:
            self.build_frame_cards()
            self.load_preview()
        if self.view in ('review', 'detail'):
            self.build_result_cards()

    # --- getting answers --------------------------------------------------

    def copy_image(self):
        sheet = self.rebuild_current()
        if not sheet:
            return
        try:
            win_clipboard.copy_image(sheet.surface)
        except win_clipboard.ClipboardError as exc:
            self.set_status(str(exc), error=True)
            return
        self.set_status(f'Sheet of {sheet.pose} copied - paste it into Gemini, then the prompt')

    def copy_prompt(self):
        sheet = self.rebuild_current()
        if not sheet:
            return
        try:
            win_clipboard.copy_text(sheet.prompt)
        except win_clipboard.ClipboardError as exc:
            self.set_status(str(exc), error=True)
            return
        self.set_status(f'Prompt of {sheet.pose} copied')

    def paste_answer(self):
        """Take the image on the clipboard as the answer for the chosen frame."""
        try:
            found = win_clipboard.paste_image()
        except win_clipboard.ClipboardError as exc:
            self.set_status(str(exc), error=True)
            return
        if not found:
            self.set_status('No image on the clipboard - copy the answer in Gemini first', error=True)
            return
        kind, data = found
        if kind == 'file':
            self.import_answer(Path(data))
        else:
            self.import_answer(data, kind)

    def open_answer(self):
        path = ask_open_file()
        if path:
            self.import_answer(Path(path))

    def import_answer(self, source, kind=''):
        """Store an answer from the web view and open it for review.

        Args:
            source: A file path, or the encoded image bytes.
            kind: 'png' or 'bmp' when source is bytes.
        """
        sheet = self.current_sheet()
        if not sheet:
            return
        try:
            if isinstance(source, Path):
                pygame.image.load(str(source))  # refuse what is not an image
                data, suffix = source.read_bytes(), source.suffix.lower() or '.png'
            else:
                image = pygame.image.load(io.BytesIO(source), f'answer.{kind}')
                buffer = io.BytesIO()
                pygame.image.save(image, buffer, 'answer.png')
                data, suffix = buffer.getvalue(), '.png'
        except (pygame.error, OSError) as exc:
            self.set_status(f'Not an image I can read: {exc}', error=True)
            return
        self.npc.out_dir.mkdir(parents=True, exist_ok=True)
        path = next_free_path(self.npc.out_dir, f'{self.npc.prefix}_{sheet.pose}_{WEB_MODEL}', suffix)
        path.write_bytes(data)
        entry = Entry(pose=sheet.pose, image=path.name, sheet=sheet.path.name, model=WEB_MODEL,
                      created=datetime.now().isoformat(timespec='seconds'))
        measure(path, entry)
        self.store.add(entry)
        self.build_frame_cards()
        self.open_detail(entry, 'frames')

    def send(self, sheets):
        """Send sheets with their prompts to the API in the background."""
        if self.busy() or not sheets:
            return
        if gemini_client.SDK_ERROR:
            self.set_status(f'Gemini: {gemini_client.SDK_ERROR}', error=True)
            return
        npc, store = self.npc, self.store  # the answers belong to these

        def record(entry):
            measure(npc.out_dir / entry.image, entry)
            store.add(entry)

        jobs = [(s.pose, s.path, s.prompt) for s in sheets for _ in range(self.settings.tries)]
        self.worker = GeminiWorker(npc, jobs, '', self.settings, record)
        self.set_status(self.worker.status())

    def send_current(self):
        sheet = self.rebuild_current()
        if sheet:
            self.send([sheet])

    def missing_sheets(self):
        return [s for s in self.sheets if not self.npc.sprite_path(s.pose).is_file()]

    def send_missing(self):
        self.select_direction(self.direction, self.current)
        self.send(self.missing_sheets())

    def poll_worker(self):
        if self.worker is None:
            return
        was_finished = self.worker.finished
        before = len(self.store.entries)
        self.worker.poll()
        self.set_status(self.worker.status(), error=bool(self.worker.error))
        if len(self.store.entries) != before or (self.worker.finished and not was_finished):
            self.refresh()

    # --- reviewing --------------------------------------------------------

    def build_result_cards(self):
        """One card per answer, pending ones first."""
        self.result_cards = []
        for entry in self.store.sorted_entries():
            try:
                thumb = make_thumb(self.npc.out_dir / entry.image, RESULT_THUMB_SIZE, trim=False)
            except pygame.error:
                continue
            measure(self.npc.out_dir / entry.image, entry, self.store)
            self.result_cards.append(Card(
                entry, entry.pose, thumb, entry.status,
                note_color=STATUS_COLORS.get(entry.status, TEXT_DIM),
                extra=[(entry.delivered() or 'size unknown', TEXT_DIM),
                       (entry.asked_for(), TEXT_DIM),
                       (entry.short_warning(), DONE_COLOR)],
                size=RESULT_CARD_SIZE))

    def open_review(self):
        self.build_result_cards()
        self.detail = None
        self.set_view('review')

    def open_detail(self, entry, return_view):
        direction, _ = parse_pose(entry.pose)
        if direction is None:
            self.set_status(f'{entry.pose} is not a walk frame', error=True)
            return
        base = self.npc.base_for(direction)
        try:
            poses, shapes = reference_shapes(self.npc, entry.pose, base)
            self.detail = Detail(self.npc, entry, poses, shapes)
        except Exception as exc:  # a deleted or unreadable file
            self.set_status(f'Cannot open {entry.image}: {exc}', error=True)
            return
        self.detail.base = base
        self.return_view = return_view
        if self.detail.error:
            self.set_status(self.detail.error, error=True)
        elif entry.warning:
            self.set_status(entry.warning)
        else:
            self.set_status(f'{entry.pose}, {entry.status}')
        self.set_view('detail')

    def close_detail(self):
        self.detail = None
        self.set_view(self.return_view)
        self.refresh()

    def accept_detail(self):
        """Save the frame into the game and mark the answer accepted."""
        detail = self.detail
        if not (detail and detail.result):
            return
        try:
            path = pose_review.save_sprite(detail.result, self.npc, detail.entry.pose)
        except (pygame.error, OSError) as exc:
            self.set_status(f'Could not save: {exc}', error=True)
            return
        self.store.set_status(detail.entry, pose_review.ACCEPTED)
        self.close_detail()
        self.set_status(f'Saved {path.relative_to(ROOT)}')

    def reject_detail(self):
        """Mark the answer as not good enough, or put it back to pending."""
        entry = self.detail.entry
        back = entry.status != pose_review.PENDING
        self.store.set_status(entry, pose_review.PENDING if back else pose_review.REJECTED)
        self.refresh()
        self.set_status(f'{entry.image} is now {entry.status}')

    def regenerate_detail(self):
        """Ask the API for another answer to the same frame, from a fresh sheet."""
        direction, frame = parse_pose(self.detail.entry.pose)
        if self.busy() or direction is None:
            return
        try:
            self.send(write_sheets(self.npc, direction, [frame]))
        except (pygame.error, OSError, IndexError) as exc:
            self.set_status(f'Cannot rebuild the sheet: {exc}', error=True)

    def open_folder(self):
        folder = self.npc.out_dir
        folder.mkdir(parents=True, exist_ok=True)
        if sys.platform == 'win32':
            os.startfile(folder)
        else:
            self.set_status(str(folder))

    # --- layout -----------------------------------------------------------

    def body(self):
        """The area between header and footer."""
        width, height = window_size()
        top = HEADER_HEIGHT + PANEL_TITLE
        return pygame.Rect(PANEL_GAP, top, width - 2 * PANEL_GAP,
                           height - FOOTER_HEIGHT - 10 - top)

    def frame_areas(self):
        """(directions, cards, sheet) panels of the frames view."""
        body = self.body()
        sheet_w = max(SHEET_PANEL_MIN_W, int(body.w * SHEET_PANEL_SHARE))
        dirs = pygame.Rect(body.x, body.y, DIR_PANEL_W, body.h)
        sheet = pygame.Rect(body.right - sheet_w, body.y, sheet_w, body.h)
        cards = pygame.Rect(dirs.right + PANEL_GAP, body.y,
                            sheet.x - dirs.right - 2 * PANEL_GAP, body.h)
        return dirs, cards, sheet

    def layout(self, cards, area):
        """Place cards in a centred grid inside `area`; returns the maximum scroll."""
        if not cards:
            return 0
        card_w, card_h = cards[0].rect.size
        per_row = max(1, (area.w + CARD_GAP) // (card_w + CARD_GAP))
        row_w = per_row * card_w + (per_row - 1) * CARD_GAP
        left = area.x + max(0, (area.w - row_w) // 2)
        for i, card in enumerate(cards):
            row, col = divmod(i, per_row)
            card.rect.topleft = (left + col * (card_w + CARD_GAP),
                                 area.y + row * (card_h + CARD_GAP) - self.scroll)
        rows = (len(cards) + per_row - 1) // per_row
        return max(0, rows * (card_h + CARD_GAP) - CARD_GAP - area.h)

    def card_area(self):
        if self.view == 'frames':
            return self.frame_areas()[1]
        body = self.body()
        return body.inflate(0, -CARD_GAP)

    def current_cards(self):
        return {'npcs': self.npc_cards, 'frames': self.frame_cards,
                'review': self.result_cards}.get(self.view, [])

    def place_sheet_buttons(self, sheet_rect):
        """The copy / paste / send buttons along the foot of the sheet panel."""
        inner = sheet_rect.inflate(-20, -20)
        half = (inner.w - BUTTON_GAP) // 2
        rows = ((self.copy_image_button, self.copy_prompt_button),
                (self.paste_button, self.open_button),
                (self.send_button,))
        y = inner.bottom - len(rows) * (BUTTON_H + BUTTON_GAP) + BUTTON_GAP
        for row in rows:
            if len(row) == 1:
                row[0].rect = pygame.Rect(inner.x, y, inner.w, BUTTON_H)
            else:
                row[0].rect = pygame.Rect(inner.x, y, half, BUTTON_H)
                row[1].rect = pygame.Rect(inner.right - half, y, half, BUTTON_H)
            y += BUTTON_H + BUTTON_GAP
        # What is left above the buttons shows the sheet.
        return pygame.Rect(inner.x, inner.y, inner.w, self.copy_image_button.rect.y - BUTTON_GAP - inner.y)

    # --- drawing ----------------------------------------------------------

    def draw_panel(self, rect, title):
        pygame.draw.rect(self.screen, CARD_BG, rect, border_radius=8)
        text = self.small.render(fit_text(self.small, title, rect.w), True, TEXT_DIM)
        self.screen.blit(text, (rect.x + 4, rect.y - 20))

    def draw_card(self, card, mouse, selected):
        if selected:
            color = CARD_SELECTED
        elif card.rect.collidepoint(mouse):
            color = CARD_HOVER
        else:
            color = CARD_BG
        pygame.draw.rect(self.screen, color, card.rect, border_radius=8)
        thumb_w, thumb_h = card.thumb.get_size()
        self.screen.blit(card.thumb, (card.rect.x + (card.rect.w - thumb_w) // 2, card.rect.y + 10))
        y = card.rect.y + thumb_h + 16
        width = card.rect.w - 12
        label = self.small.render(fit_text(self.small, card.label, width), True, TEXT)
        self.screen.blit(label, label.get_rect(midtop=(card.rect.centerx, y)))
        for note, note_color in card.lines():
            y += 18
            text = self.small.render(fit_text(self.small, note, width), True, note_color)
            self.screen.blit(text, text.get_rect(midtop=(card.rect.centerx, y)))
        if card.progress is not None:
            bar = pygame.Rect(card.rect.x + 12, card.rect.bottom - 13, card.rect.w - 24, 5)
            pygame.draw.rect(self.screen, BAR_BG, bar, border_radius=3)
            share = max(0.0, min(1.0, card.progress))
            if round(bar.w * share):
                bar_color = STATUS_COLORS[pose_review.ACCEPTED] if share >= 1 else DONE_COLOR
                pygame.draw.rect(self.screen, bar_color, (bar.x, bar.y, round(bar.w * share), bar.h),
                                 border_radius=3)

    def draw_cards(self, mouse, area):
        self.screen.set_clip(area)
        for card in self.current_cards():
            if card.rect.colliderect(area):
                selected = self.view == 'frames' and card.key == self.current
                self.draw_card(card, mouse, selected)
        self.screen.set_clip(None)

    def draw_directions(self, rect, mouse):
        self.draw_panel(rect, 'Direction')
        self.dir_rows = []
        y = rect.y + 8
        for direction in DIRECTIONS:
            row = pygame.Rect(rect.x + 8, y, rect.w - 16, DIR_ROW - 4)
            y += DIR_ROW
            if direction == self.direction:
                color = CARD_SELECTED
            elif row.collidepoint(mouse):
                color = CARD_HOVER
            else:
                color = BG
            pygame.draw.rect(self.screen, color, row, border_radius=5)
            label = self.small.render(direction.label, True, TEXT)
            self.screen.blit(label, label.get_rect(midleft=(row.x + 10, row.centery)))
            count = self.counts[direction.key]
            done = self.npc.done(direction, count)
            waiting = sum(parse_pose(e.pose)[0] == direction for e in self.store.pending())
            if done:
                note, note_color = f'{done}/{count}', STATUS_COLORS[pose_review.ACCEPTED]
            elif direction.key in MIRROR_OF:
                note, note_color = 'optional', TEXT_DIM
            else:
                note, note_color = f'0/{count}', TEXT_DIM
            if waiting:
                note, note_color = f'{note}  +{waiting}', DONE_COLOR
            text = self.small.render(note, True, note_color)
            self.screen.blit(text, text.get_rect(midright=(row.right - 10, row.centery)))
            self.dir_rows.append((row, direction))

        # The frames the NPC already has, playing in a loop
        box = pygame.Rect(rect.x + 8, y + PANEL_TITLE, rect.w - 16, rect.bottom - 8 - y - PANEL_TITLE)
        if box.h < 60:
            return
        title = self.small.render(fit_text(self.small, f'In the game: {self.preview_note}', box.w),
                                  True, TEXT_DIM)
        self.screen.blit(title, (box.x, box.y - 20))
        if not self.preview_checker.get_rect().contains(pygame.Rect((0, 0), box.size)):
            self.preview_checker = checkerboard(box.size)
        self.screen.blit(self.preview_checker, box, pygame.Rect((0, 0), box.size))
        if self.preview:
            frame = self.preview[pygame.time.get_ticks() // PREVIEW_FRAME_MS % len(self.preview)]
            w, h = frame.get_size()
            factor = min((box.w - 20) / w, (box.h - 20) / h, 2.0)
            image = pygame.transform.smoothscale(frame, (max(1, int(w * factor)), max(1, int(h * factor))))
            self.screen.blit(image, image.get_rect(midbottom=(box.centerx, box.bottom - 10)))

    def draw_sheet(self, rect, mouse):
        sheet = self.current_sheet()
        self.draw_panel(rect, f'Sheet for {sheet.pose}' if sheet else 'Sheet')
        area = self.place_sheet_buttons(rect)
        if sheet and self.comparison:
            compare_area = pygame.Rect(area.x, area.bottom - int(area.h * COMPARE_SHARE),
                                       area.w, int(area.h * COMPARE_SHARE))
            area.h = compare_area.y - area.y - BUTTON_GAP
            self.draw_comparison(compare_area)
        if sheet:
            self.screen.blit(fitted(sheet.surface, area.size, CARD_BG), area)
        ready = bool(sheet)
        for button in (self.copy_image_button, self.copy_prompt_button,
                       self.paste_button, self.open_button):
            button.enabled = ready and (button is self.open_button or win_clipboard.AVAILABLE)
        self.send_button.enabled = ready and not self.busy() and not gemini_client.SDK_ERROR
        tries = self.settings.tries
        self.send_button.label = 'Sending ...' if self.busy() else (
            f'Send to Gemini ({tries}x)' if tries > 1 else 'Send to Gemini')
        for button in (self.copy_image_button, self.copy_prompt_button, self.paste_button,
                       self.open_button, self.send_button):
            button.draw(self.screen, self.font, mouse)

    def draw_comparison(self, area):
        """The accepted frame between its goal and the two laid over each other."""
        image = self.comparison
        label_h = self.small.get_linesize()
        w, h = image.get_size()
        factor = min(area.w / w, (area.h - label_h) / h)
        shown = pygame.transform.smoothscale(image, (max(1, int(w * factor)), max(1, int(h * factor))))
        pos = shown.get_rect(midbottom=(area.centerx, area.bottom))
        self.screen.blit(shown, pos)
        tile_w = (w - (len(COMPARE_TILES) - 1) * COMPARE_PAD) / len(COMPARE_TILES)
        for index, name in enumerate(COMPARE_TILES):
            centre = pos.x + (index * (tile_w + COMPARE_PAD) + tile_w / 2) * factor
            label = self.small.render(name, True, TEXT_DIM)
            self.screen.blit(label, label.get_rect(midbottom=(centre, pos.y - 2)))

    def draw_frames(self, mouse):
        dirs, cards, sheet = self.frame_areas()
        self.draw_directions(dirs, mouse)
        self.screen.blit(self.small.render(
            f'Frames of the walk {self.direction.label.lower()}  -  rebuilt from the base files on every click',
            True, TEXT_DIM), (cards.x + 4, cards.y - 20))
        self.draw_cards(mouse, cards)
        self.draw_sheet(sheet, mouse)

    def draw_detail(self):
        detail = self.detail
        body = self.body()
        image_rect = pygame.Rect(body.x, body.y, int((body.w - PANEL_GAP) * 0.55), body.h)
        preview_rect = pygame.Rect(image_rect.right + PANEL_GAP, body.y,
                                   body.right - image_rect.right - PANEL_GAP, body.h)

        returned = f'{detail.image.get_width()} x {detail.image.get_height()} px'
        tokens = detail.entry.token_detail()
        self.draw_panel(image_rect, f'The answer  -  {returned}' + (f'  -  {tokens}' if tokens else ''))
        area = image_rect.inflate(-20, -20)
        self.screen.blit(fitted(detail.image, area.size, CARD_BG), area)

        self.draw_panel(preview_rect, f'{self.npc.prefix}_{detail.base} and the new frame, '
                                      'same scale  (click white gaps)')
        area = preview_rect.inflate(-20, -20)
        if not self.checker.get_rect().contains(pygame.Rect((0, 0), area.size)):
            self.checker = checkerboard(area.size)
        self.screen.blit(self.checker, area, pygame.Rect((0, 0), area.size))
        detail.preview = None
        if not detail.result:
            text = self.small.render(detail.error, True, ERROR_COLOR)
            self.screen.blit(text, text.get_rect(center=area.center))
            return

        reference, output = detail.result.player, detail.result.output
        gap = 20
        total = (reference.get_width() + output.get_width() + gap,
                 max(reference.get_height(), output.get_height()))
        factor = min((area.w - 20) / total[0], (area.h - 50) / total[1], 1.5)
        rw, rh = int(reference.get_width() * factor), int(reference.get_height() * factor)
        ow, oh = int(output.get_width() * factor), int(output.get_height() * factor)
        baseline = area.bottom - 40
        start_x = area.centerx - int(total[0] * factor) // 2
        # Both canvases stand on the reference's baseline.
        reference_bottom = detail.result.player_offset[1] + reference.get_height()
        output_pos = (start_x + rw + int(gap * factor), baseline - int(reference_bottom * factor))
        self.screen.blit(pygame.transform.smoothscale(reference, (rw, rh)), (start_x, baseline - rh))
        self.screen.blit(pygame.transform.smoothscale(output, (ow, oh)), output_pos)
        pygame.draw.rect(self.screen, TEXT_DIM, (*output_pos, ow, oh), 1)
        detail.preview = (pygame.Rect(output_pos, (ow, oh)), factor)

        caption = self.small.render(
            f'{output.get_width()} x {output.get_height()} px, scale {detail.result.scale:.2f} '
            f'-> {self.npc.sprite_path(detail.entry.pose).name}', True, (40, 40, 40))
        self.screen.blit(caption, caption.get_rect(midbottom=(area.centerx, area.bottom - 10)))

    def header_text(self):
        """(title, hint) of the current view."""
        if self.view == 'npcs':
            return ('1. Choose the NPC',
                    f'Every NPC with a front standing sprite. {self.total_frames()} walk frames '
                    f'make a full set ({len(DIRECTIONS)} directions); the left-hand ones are optional.')
        if self.view == 'frames':
            return (f'2. Walk frames for "{self.npc.name}"',
                    'Up/Down = direction, Left/Right = frame. Ctrl+C = copy sheet, Ctrl+Shift+C = copy '
                    'prompt, Ctrl+V or drop a file = answer from the web view, S = settings.')
        if self.view == 'review':
            waiting = len(self.store.pending())
            return (f'3. Answers for "{self.npc.name}"  -  {waiting} waiting',
                    'Click an answer to judge it. Accepted ones are already in the game.')
        entry = self.detail.entry
        got = f'got {entry.delivered()}' if entry.delivered() else 'size unknown'
        return (f'{entry.pose}  -  {entry.image}',
                f'from {entry.asked_for()}  -  {got}  -  Enter = accept, Del = not good enough')

    def update_footer(self):
        if self.view == 'frames':
            waiting = len(self.store.pending())
            self.review_button.label = f'Review ({waiting})' if waiting else 'Review'
            self.review_button.enabled = bool(self.store.entries)
            missing = len(self.missing_sheets()) * self.settings.tries
            self.missing_button.label = 'Sending ...' if self.busy() else f'Send missing ({missing})'
            self.missing_button.enabled = bool(missing) and not self.busy() and not gemini_client.SDK_ERROR
        elif self.view == 'detail':
            self.accept_button.enabled = bool(self.detail.result)
            self.reject_button.label = ('Back to pending' if self.detail.entry.status != pose_review.PENDING
                                        else 'Not good enough')
            self.regenerate_button.enabled = not self.busy() and not gemini_client.SDK_ERROR

    def draw(self):
        mouse = pygame.mouse.get_pos()
        self.screen.fill(BG)
        if self.view == 'frames':
            self.draw_frames(mouse)
        elif self.view == 'detail':
            self.draw_detail()
        else:
            self.draw_cards(mouse, self.card_area())

        title, hint = self.header_text()
        self.screen.blit(self.title_font.render(title, True, TEXT), (20, 12))
        if self.status:
            text = self.small.render(self.status, True, ERROR_COLOR if self.status_error else DONE_COLOR)
            self.screen.blit(text, text.get_rect(topright=(window_size()[0] - 20, 20)))
        summary = self.small.render(self.settings.summary(), True, TEXT_DIM)
        summary_rect = summary.get_rect(topright=(window_size()[0] - 20, 44))
        self.screen.blit(summary, summary_rect)
        hint = fit_text(self.small, hint, summary_rect.x - 40)
        self.screen.blit(self.small.render(hint, True, TEXT_DIM), (22, 56))

        pygame.draw.line(self.screen, CARD_BG, (0, window_size()[1] - FOOTER_HEIGHT),
                         (window_size()[0], window_size()[1] - FOOTER_HEIGHT), 2)
        self.update_footer()
        for group in self.footer_buttons():
            for button in group:
                button.draw(self.screen, self.font, mouse)
        if self.dialog:
            self.dialog.draw(self.screen, mouse)
        pygame.display.flip()

    # --- input ------------------------------------------------------------

    def open_settings(self):
        self.dialog = SettingsDialog(self.settings, (self.font, self.small, self.title_font))

    def close_settings(self):
        self.settings = self.dialog.settings
        self.settings.save()
        self.dialog = None

    def back(self):
        if self.view == 'detail':
            self.close_detail()
        elif self.view == 'review':
            self.set_view('frames')
            self.refresh()
        elif self.view == 'frames':
            self.npc = None
            self.store = None
            self.worker = None
            self.set_status('')
            self.build_npc_cards()
            self.set_view('npcs')
        else:
            return False
        return True

    def click(self, pos):
        if self.dialog:
            if self.dialog.click(pos) == 'close':
                self.close_settings()
            return
        left, right = self.footer_buttons()
        if self.settings_button in right and self.settings_button.hit(pos):
            self.open_settings()
        elif self.back_button in left and self.back_button.hit(pos):
            self.back()
        elif self.folder_button in left and self.folder_button.hit(pos):
            self.open_folder()
        elif self.view == 'frames':
            self.click_frames(pos)
        elif self.view == 'detail':
            if self.accept_button.hit(pos):
                self.accept_detail()
            elif self.reject_button.hit(pos):
                self.reject_detail()
            elif self.regenerate_button.hit(pos):
                self.regenerate_detail()
            else:
                self.detail.toggle_hole(pos)
        else:
            self.click_card(pos)

    def click_frames(self, pos):
        actions = ((self.review_button, self.open_review),
                   (self.missing_button, self.send_missing),
                   (self.copy_image_button, self.copy_image),
                   (self.copy_prompt_button, self.copy_prompt),
                   (self.paste_button, self.paste_answer),
                   (self.open_button, self.open_answer),
                   (self.send_button, self.send_current))
        for button, action in actions:
            if button.hit(pos):
                action()
                return
        for row, direction in self.dir_rows:
            if row.collidepoint(pos):
                self.select_direction(direction)
                return
        self.click_card(pos)

    def click_card(self, pos):
        area = self.card_area()
        if not area.collidepoint(pos):
            return
        for card in self.current_cards():
            if not card.rect.collidepoint(pos):
                continue
            if self.view == 'npcs':
                self.open_npc(card.key)
            elif self.view == 'frames':
                self.current = card.key
                self.rebuild_current()
            elif self.view == 'review':
                self.open_detail(card.key, 'review')
            return

    def key(self, event):
        if self.dialog:
            if event.key == pygame.K_ESCAPE:
                self.close_settings()
            return None
        ctrl = event.mod & pygame.KMOD_CTRL
        if event.key == pygame.K_F11:
            toggle_fullscreen()
            self.place_footer()
        elif event.key == pygame.K_ESCAPE:
            if not self.back():
                return 'quit'
        elif event.key == pygame.K_s and not ctrl:
            self.open_settings()
        elif self.view == 'frames':
            if event.key == pygame.K_c and ctrl:
                if event.mod & pygame.KMOD_SHIFT:
                    self.copy_prompt()
                else:
                    self.copy_image()
            elif event.key == pygame.K_v and ctrl:
                self.paste_answer()
            elif event.key == pygame.K_o and ctrl:
                self.open_answer()
            elif event.key in (pygame.K_LEFT, pygame.K_RIGHT) and self.sheets:
                step = 1 if event.key == pygame.K_RIGHT else -1
                self.current = (self.current + step) % len(self.sheets)
                self.rebuild_current()
            elif event.key in (pygame.K_UP, pygame.K_DOWN):
                step = 1 if event.key == pygame.K_DOWN else -1
                index = DIRECTIONS.index(self.direction)
                self.select_direction(DIRECTIONS[(index + step) % len(DIRECTIONS)])
            elif event.key == pygame.K_r and self.store.entries:
                self.open_review()
        elif self.view == 'detail':
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.accept_detail()
            elif event.key == pygame.K_DELETE:
                self.reject_detail()
        return None

    def run(self):
        while True:
            max_scroll = self.layout(self.current_cards(), self.card_area())
            self.scroll = min(self.scroll, max_scroll)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return
                if event.type == pygame.VIDEORESIZE:
                    self.place_footer()
                elif event.type == pygame.KEYDOWN:
                    if self.key(event) == 'quit':
                        return
                elif event.type == pygame.DROPFILE and self.view == 'frames' and not self.dialog:
                    self.import_answer(Path(event.file))
                elif event.type == pygame.MOUSEWHEEL:
                    if self.dialog:
                        self.dialog.scroll_models(event.y)
                    else:
                        self.scroll = max(0, min(max_scroll, self.scroll - event.y * 60))
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self.click(event.pos)
            self.poll_worker()
            self.draw()
            self.clock.tick(30)


if __name__ == '__main__':
    WalkTool().run()
    pygame.quit()
