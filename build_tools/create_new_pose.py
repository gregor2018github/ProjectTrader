"""Build 2x2 reference sheets for NPC sprites, let Gemini fill them in, judge
the answers and take the good ones into the game.

Every sheet has the same layout:

    +---------------------------+---------------------------+
    | player_front_static.png   | <npc>_front_static.png    |
    +---------------------------+---------------------------+
    | player_<pose>.png         | (empty - Gemini draws the |
    |                           |  NPC in this pose here)   |
    +---------------------------+---------------------------+

All four cells share one size, derived from the (trimmed) sprites, with a
white margin around each sprite.

Run from anywhere:

    python build_tools/create_new_pose.py

The window can be resized or maximised; F11 switches to full screen.

1. Pick the NPC (every folder in humans/npcs that holds a front standing
   sprite, e.g. vintner_front_static.png). The top row of every sheet always
   shows the player and the NPC standing front on (SHEET_BASE_POSE), never a
   side view, whatever pose is asked for.
2. Pick one or more player poses. Poses the NPC already has a sprite for are
   marked "done"; "Select missing" picks all the others at once.
3. "Settings" (S) chooses the image model, the aspect ratio and the image
   size to ask for, and how many answers to request per sheet.
4. "Generate" (Enter) only writes the sheets and the prompt to
   build_tools/output/<npc>/, to hand in by hand.
   "Generate + Gemini" (Ctrl+Enter) writes them and sends every sheet with
   its prompt to the image model. The requests run in the background, the
   header shows the progress, and each answer is written next to its sheet
   as <prefix>_<pose>_gemini.png. Nothing is overwritten: a repeated run
   adds _2, _3 and so on, so several tries per pose can be compared.
5. "Review" opens the answers that are waiting. Each one shows the image the
   model returned next to the finished sprite it would become.
   - "Accept" cuts the sprite out and writes it into the NPC's folder in
     assets/, exactly as create_new_NPC.py would. The pose counts as done.
   - "Not good enough" leaves the image on disk and marks it rejected, to be
     looked at again, edited by hand or replaced by a new try later.
   - "Regenerate" sends the sheet once more with the current settings.
   White areas enclosed by the sprite (e.g. between arm and body) can be
   clicked in the preview to make them transparent, as in create_new_NPC.py.

The API needs the SDK and a key:

    pip install -r build_tools/requirements.txt
    GEMINI_API_KEY=... in the environment or in .env in the project root
"""

import os
import queue
import sys
import threading
from datetime import datetime
from pathlib import Path

import pygame

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gemini_client  # noqa: E402
import pose_review  # noqa: E402
from gemini_client import GeminiClient, GeminiError, Settings, next_free_path  # noqa: E402
from pose_review import Entry, ReviewStore  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
HUMANS_DIR = ROOT / 'assets' / 'map_sprites' / 'figurines' / 'humans'
PLAYER_DIR = HUMANS_DIR / 'player'
NPC_DIR = HUMANS_DIR / 'npcs'
OUTPUT_DIR = Path(__file__).resolve().parent / 'output'

# Standing poses an NPC can be recognised by, in order of preference
BASE_POSES = ('front_static', 'left_static', 'right_static', 'back_static')
# The pose shown in the top row of every sheet
SHEET_BASE_POSE = 'front_static'

# Sheet appearance
SHEET_SCALE = 2          # integer upscale of the sprites (nearest neighbour)
MARGIN_RATIO = 0.06      # white room around a sprite, relative to its larger side
MIN_MARGIN = 16
FRAME_WIDTH = 4
FRAME_COLOR = (0, 0, 0)
TARGET_FRAME_COLOR = (220, 0, 0)
TARGET_FRAME_WIDTH = 3

# Selector window
WINDOW_SIZE = (1280, 820)  # starting size; the window can be resized, F11 = full screen
CARD_SIZE = (140, 205)
THUMB_SIZE = (116, 150)
NPC_CARD_SIZE = (172, 244)    # the overview cards also carry the counts and a bar
NPC_THUMB_SIZE = (148, 150)
RESULT_CARD_SIZE = (210, 215)
RESULT_THUMB_SIZE = (186, 130)
CARD_GAP = 14
HEADER_HEIGHT = 90
FOOTER_HEIGHT = 70

BG = (38, 36, 34)
CARD_BG = (70, 66, 60)
CARD_HOVER = (95, 89, 80)
CARD_SELECTED = (60, 120, 70)
THUMB_BG = (235, 235, 235)
TEXT = (240, 236, 228)
TEXT_DIM = (160, 154, 144)
DONE_COLOR = (230, 190, 80)
ERROR_COLOR = (240, 110, 90)
BUTTON_BG = (110, 90, 60)
BUTTON_HOVER = (140, 115, 75)
BUTTON_DISABLED = (70, 66, 60)
DIALOG_BG = (52, 49, 45)
DIALOG_LINE = (92, 86, 78)
CHIP_BG = (70, 66, 60)
CHIP_HOVER = (95, 89, 80)
CHIP_ON = (60, 120, 70)
BAR_BG = (52, 49, 45)
SHADE = (0, 0, 0, 170)

# Colour of a review card by state
STATUS_COLORS = {
    pose_review.PENDING: DONE_COLOR,
    pose_review.ACCEPTED: (110, 190, 120),
    pose_review.REJECTED: ERROR_COLOR,
}

# Settings dialog
DIALOG_WIDTH = 700
DIALOG_PAD = 24
MODEL_ROW = 40
MAX_VISIBLE_MODELS = 8   # taller lists (after "Fetch models") scroll
CHIP_HEIGHT = 32
CHIP_GAP = 8
SECTION_GAP = 18

# Detail screen
PANEL_GAP = 20
CHECKER_SIZE = 12

PROMPT_TEMPLATE = """\
The attached picture holds a 2x2 grid of pixel-art sprites for my medieval trading game "Merchant's Rise".
Top left: the main character in a standing pose.
Top right: {npc} in exactly the same standing pose.
Bottom left: the main character in a different pose.
Bottom right (red frame) is empty. Draw {npc} there, in exactly the same pose as the main character in the bottom left.
Keep {npc}'s look, clothing, colours, proportions and pixel-art style from the top right sprite, and keep the same size and white background.
"""


# ---------------------------------------------------------------------------
# Window
# ---------------------------------------------------------------------------

def window_size():
    """Current size of the (resizable) tool window."""
    surface = pygame.display.get_surface()
    return surface.get_size() if surface else WINDOW_SIZE


def open_window(caption):
    screen = pygame.display.set_mode(WINDOW_SIZE, pygame.RESIZABLE)
    pygame.display.set_caption(caption)
    return screen


def toggle_fullscreen():
    """Switch between full screen and a normal resizable window."""
    if pygame.display.get_surface().get_flags() & pygame.FULLSCREEN:
        return pygame.display.set_mode(WINDOW_SIZE, pygame.RESIZABLE)
    return pygame.display.set_mode((0, 0), pygame.FULLSCREEN)


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

class Npc:
    def __init__(self, folder, base_pose, prefix):
        self.folder = folder
        self.name = folder.name
        self.base_pose = base_pose
        self.prefix = prefix
        self.base_path = self.sprite_path(base_pose)

    def sprite_path(self, pose):
        return self.folder / f'{self.prefix}_{pose}.png'

    @property
    def out_dir(self):
        """Where this NPC's sheets, answers and review.json live."""
        return OUTPUT_DIR / self.name


def find_base(folder, poses=BASE_POSES):
    """Return (pose, prefix) of the NPC's first standing sprite, or None.

    'vintner_front_static.png' -> ('front_static', 'vintner')
    """
    for pose in poses:
        matches = sorted(folder.glob(f'*_{pose}.png'))
        if matches:
            return pose, matches[0].stem[:-len(pose) - 1]
    return None


def find_npcs():
    npcs = []
    for folder in sorted(p for p in NPC_DIR.iterdir() if p.is_dir()):
        base = find_base(folder, (SHEET_BASE_POSE,))
        if base:
            npcs.append(Npc(folder, *base))
    return npcs


def find_player_poses():
    """Return {pose: path}, e.g. {'front_move1': .../player_front_move1.png}."""
    poses = {}
    for path in sorted(PLAYER_DIR.glob('player_*.png')):
        poses[path.stem[len('player_'):]] = path
    return poses


# ---------------------------------------------------------------------------
# Sheet generation
# ---------------------------------------------------------------------------

def load_trimmed(path, scale=1):
    """Load a sprite and cut away its transparent border."""
    surface = pygame.image.load(str(path)).convert_alpha()
    surface = surface.subsurface(surface.get_bounding_rect()).copy()
    if scale != 1:
        w, h = surface.get_size()
        surface = pygame.transform.scale(surface, (w * scale, h * scale))
    return surface


def build_sheet(player_base, npc_base, player_pose):
    sprites = [load_trimmed(p, SHEET_SCALE) for p in (player_base, npc_base, player_pose)]
    max_w = max(s.get_width() for s in sprites)
    max_h = max(s.get_height() for s in sprites)
    margin = max(MIN_MARGIN, int(max(max_w, max_h) * MARGIN_RATIO))
    cell_w, cell_h = max_w + 2 * margin, max_h + 2 * margin

    sheet = pygame.Surface((2 * cell_w + 3 * FRAME_WIDTH, 2 * cell_h + 3 * FRAME_WIDTH))
    sheet.fill(FRAME_COLOR)

    cells = []
    for row in range(2):
        for col in range(2):
            rect = pygame.Rect(FRAME_WIDTH + col * (cell_w + FRAME_WIDTH),
                               FRAME_WIDTH + row * (cell_h + FRAME_WIDTH),
                               cell_w, cell_h)
            sheet.fill((255, 255, 255), rect)
            cells.append(rect)

    for sprite, cell in zip(sprites, cells):
        sheet.blit(sprite, sprite.get_rect(center=cell.center))

    pygame.draw.rect(sheet, TARGET_FRAME_COLOR, cells[3], TARGET_FRAME_WIDTH)
    return sheet


def prompt_for(npc):
    """The prompt that belongs to this NPC's sheets."""
    return PROMPT_TEMPLATE.format(npc=f'the {npc.prefix}')


def generate(npc, poses, player_poses):
    """Write one sheet per pose plus the prompt.

    Returns:
        (out_dir, {pose: sheet_path}) - the folder and the written sheets.
    """
    out_dir = npc.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    player_base = player_poses[npc.base_pose]
    sheets = {}
    for pose in poses:
        sheet = build_sheet(player_base, npc.base_path, player_poses[pose])
        path = out_dir / f'{npc.prefix}_{pose}_sheet.png'
        pygame.image.save(sheet, str(path))
        sheets[pose] = path
    (out_dir / 'prompt.txt').write_text(prompt_for(npc), encoding='utf-8')
    return out_dir, sheets


# ---------------------------------------------------------------------------
# Gemini requests (background)
# ---------------------------------------------------------------------------

class GeminiWorker:
    """Sends a list of sheets to Gemini in a background thread.

    The pygame loop stays responsive; the answers are collected by polling
    poll(), which drains the messages the thread has produced so far and
    hands the finished ones to the caller's callback.
    """

    def __init__(self, npc, jobs, prompt, settings, on_result):
        """Starts the requests.

        Args:
            npc: The NPC the sheets belong to.
            jobs: [(pose, sheet_path)], one entry per request; the same pose
                may appear several times (Settings.tries).
            prompt: The prompt sent with every sheet.
            settings: Model and output size to ask for.
            on_result: Called on the main thread with one pose_review.Entry
                per answer that was written.
        """
        self.npc = npc
        self.settings = settings
        self.total = len(jobs)
        self.done = 0
        self.failures = []
        self.finished = False
        self.error = ''
        self._on_result = on_result
        self._queue = queue.Queue()
        self._thread = threading.Thread(
            target=self._run, args=(jobs, prompt), daemon=True)
        self._thread.start()

    def _run(self, jobs, prompt):
        """Thread body: one request per job, answers written to disk."""
        try:
            client = GeminiClient()
        except Exception as exc:  # missing SDK, missing key, bad setup
            self._queue.put(('fatal', str(exc)))
            return
        for pose, sheet_path in jobs:
            try:
                image = client.complete_sheet(prompt, sheet_path.read_bytes(), self.settings)
                out_path = next_free_path(
                    sheet_path.parent, f'{self.npc.prefix}_{pose}_gemini', image.suffix)
                out_path.write_bytes(image.data)
                self._queue.put(('ok', Entry(
                    pose=pose,
                    image=out_path.name,
                    sheet=sheet_path.name,
                    model=self.settings.model,
                    aspect_ratio=self.settings.aspect_ratio,
                    image_size=self.settings.image_size,
                    created=datetime.now().isoformat(timespec='seconds'),
                    note=image.model_text[:200],
                )))
            except (GeminiError, OSError) as exc:
                self._queue.put(('error', f'{pose}: {exc}'))
        self._queue.put(('finished', None))

    def poll(self):
        """Drains the thread's messages and updates the counters."""
        while True:
            try:
                kind, payload = self._queue.get_nowait()
            except queue.Empty:
                return
            if kind == 'ok':
                self.done += 1
                self._on_result(payload)
            elif kind == 'error':
                self.done += 1
                self.failures.append(payload)
            elif kind == 'fatal':
                self.error = payload
                self.finished = True
            elif kind == 'finished':
                self.finished = True

    def status(self):
        """One line describing the current state, for the header."""
        if self.error:
            return f'Gemini: {self.error}'
        if not self.finished:
            return f'Gemini: {self.done}/{self.total} answered ...'
        ok = self.done - len(self.failures)
        if self.failures:
            return f'Gemini: {ok}/{self.total} ok, failed: ' + '; '.join(self.failures[:2])
        return f'Gemini: {self.total}/{self.total} answered, ready for review'


# ---------------------------------------------------------------------------
# Widgets
# ---------------------------------------------------------------------------

def make_thumb(path, size=THUMB_SIZE, trim=True):
    """A sprite or result image, fitted onto a light card-sized tile."""
    if trim:
        sprite = load_trimmed(path)
    else:
        sprite = pygame.image.load(str(path)).convert()
    w, h = sprite.get_size()
    factor = min(size[0] / w, size[1] / h)
    sprite = pygame.transform.smoothscale(sprite, (max(1, int(w * factor)), max(1, int(h * factor))))
    thumb = pygame.Surface(size)
    thumb.fill(THUMB_BG)
    thumb.blit(sprite, sprite.get_rect(center=thumb.get_rect().center))
    return thumb


def fit_text(font, text, width):
    """Shorten a label with an ellipsis until it fits into `width` pixels."""
    if font.size(text)[0] <= width:
        return text
    while text and font.size(text + '...')[0] > width:
        text = text[:-1]
    return text + '...'


class Card:
    def __init__(self, key, label, thumb, note='', note2='', note_color=None,
                 note2_color=None, progress=None, size=CARD_SIZE):
        self.key = key
        self.label = label
        self.thumb = thumb
        self.note = note
        self.note2 = note2
        self.note_color = note_color
        self.note2_color = note2_color
        self.progress = progress   # 0..1, drawn as a bar along the card's foot
        self.rect = pygame.Rect((0, 0), size)


class Button:
    def __init__(self, label, x=0, y=0, w=170, h=44):
        self.label = label
        self.rect = pygame.Rect(x, y, w, h)
        self.enabled = True

    def draw(self, screen, font, mouse):
        if not self.enabled:
            color = BUTTON_DISABLED
        elif self.rect.collidepoint(mouse):
            color = BUTTON_HOVER
        else:
            color = BUTTON_BG
        pygame.draw.rect(screen, color, self.rect, border_radius=6)
        text = font.render(self.label, True, TEXT if self.enabled else TEXT_DIM)
        screen.blit(text, text.get_rect(center=self.rect.center))

    def hit(self, pos):
        return self.enabled and self.rect.collidepoint(pos)


def draw_chips(screen, font, values, labels, chosen, x, y, width, mouse):
    """Draw one row of little choice buttons; returns [(rect, value)]."""
    chips = []
    cx, cy = x, y
    for value in values:
        label = labels(value)
        w = font.size(label)[0] + 22
        if cx > x and cx + w > x + width:
            cx, cy = x, cy + CHIP_HEIGHT + CHIP_GAP
        rect = pygame.Rect(cx, cy, w, CHIP_HEIGHT)
        if value == chosen:
            color = CHIP_ON
        elif rect.collidepoint(mouse):
            color = CHIP_HOVER
        else:
            color = CHIP_BG
        pygame.draw.rect(screen, color, rect, border_radius=6)
        text = font.render(label, True, TEXT)
        screen.blit(text, text.get_rect(center=rect.center))
        chips.append((rect, value))
        cx += w + CHIP_GAP
    return chips, cy + CHIP_HEIGHT


class SettingsDialog:
    """Model and output size to ask the image API for."""

    def __init__(self, settings, fonts):
        """
        Args:
            settings: The gemini_client.Settings to edit.
            fonts: (font, small, title_font).
        """
        self.settings = settings
        self.font, self.small, self.title_font = fonts
        self.models = gemini_client.known_models()
        if settings.model not in self.models:
            self.models.append(settings.model)
        self.status = ''
        self.status_error = False
        self.model_scroll = 0
        self.model_area = pygame.Rect(0, 0, 0, 0)
        self.model_rows = []
        self.ratio_chips = []
        self.size_chips = []
        self.tries_chips = []
        self.fetch_button = Button('Fetch models from API', w=250)
        self.close_button = Button('Done', w=120)

    def fixed_height(self):
        """Everything in the dialog except the model list."""
        return (2 * DIALOG_PAD + 40 + 22
                + 3 * (SECTION_GAP + 22 + CHIP_HEIGHT) + SECTION_GAP + 60)

    def rect(self):
        width, height = window_size()
        rows = min(len(self.models), MAX_VISIBLE_MODELS)
        size = (min(DIALOG_WIDTH, width - 40),
                min(self.fixed_height() + rows * MODEL_ROW, height - 40))
        return pygame.Rect(((width - size[0]) // 2, (height - size[1]) // 2), size)

    def scroll_models(self, steps):
        """Mouse wheel over the model list."""
        hidden = max(0, len(self.models) * MODEL_ROW - self.model_area.h)
        self.model_scroll = max(0, min(hidden, self.model_scroll - steps * MODEL_ROW))

    def fetch_models(self):
        """Ask the API which image models the key can reach and offer them too."""
        try:
            found = GeminiClient().discover_models()
        except GeminiError as exc:
            self.status, self.status_error = str(exc), True
            return
        added = [model for model in found if model not in self.models]
        self.models.extend(added)
        self.status = f'{len(found)} image model(s) found, {len(added)} new'
        self.status_error = False

    # --- drawing ----------------------------------------------------------

    def draw(self, screen, mouse):
        shade = pygame.Surface(window_size(), pygame.SRCALPHA)
        shade.fill(SHADE)
        screen.blit(shade, (0, 0))

        rect = self.rect()
        pygame.draw.rect(screen, DIALOG_BG, rect, border_radius=10)
        pygame.draw.rect(screen, DIALOG_LINE, rect, 2, border_radius=10)

        x = rect.x + DIALOG_PAD
        width = rect.w - 2 * DIALOG_PAD
        y = rect.y + DIALOG_PAD
        screen.blit(self.title_font.render('Image generation', True, TEXT), (x, y))
        y += 40

        label = 'Model' if len(self.models) <= MAX_VISIBLE_MODELS else 'Model  (scroll for more)'
        screen.blit(self.small.render(label, True, TEXT_DIM), (x, y))
        y += 22
        self.model_area = pygame.Rect(x, y, width, max(MODEL_ROW, rect.h - self.fixed_height()))
        self.model_rows = []
        screen.set_clip(self.model_area)
        row_y = y - self.model_scroll
        for model in self.models:
            row = pygame.Rect(x, row_y, width, MODEL_ROW - 4)
            row_y += MODEL_ROW
            if not row.colliderect(self.model_area):
                continue
            if model == self.settings.model:
                color = CHIP_ON
            elif row.collidepoint(mouse):
                color = CHIP_HOVER
            else:
                color = CHIP_BG
            pygame.draw.rect(screen, color, row, border_radius=6)
            name = self.font.render(model, True, TEXT)
            screen.blit(name, name.get_rect(midleft=(row.x + 12, row.centery)))
            note = gemini_client.model_note(model)
            if note:
                text = self.small.render(note, True, TEXT_DIM)
                screen.blit(text, text.get_rect(midright=(row.right - 12, row.centery)))
            self.model_rows.append((row.clip(self.model_area), model))
        screen.set_clip(None)

        y = self.model_area.bottom + SECTION_GAP
        screen.blit(self.small.render('Aspect ratio', True, TEXT_DIM), (x, y))
        y += 22
        self.ratio_chips, y = draw_chips(
            screen, self.small, gemini_client.ASPECT_RATIOS,
            lambda v: v or 'keep sheet', self.settings.aspect_ratio, x, y, width, mouse)

        y += SECTION_GAP
        screen.blit(self.small.render('Image size', True, TEXT_DIM), (x, y))
        y += 22
        self.size_chips, y = draw_chips(
            screen, self.small, gemini_client.IMAGE_SIZES,
            lambda v: v or 'model default', self.settings.image_size, x, y, width, mouse)

        y += SECTION_GAP
        screen.blit(self.small.render('Answers per sheet', True, TEXT_DIM), (x, y))
        y += 22
        self.tries_chips, y = draw_chips(
            screen, self.small, range(1, gemini_client.MAX_TRIES + 1),
            lambda v: f'{v}x', self.settings.tries, x, y, width, mouse)

        self.fetch_button.rect.bottomleft = (x, rect.bottom - DIALOG_PAD)
        self.close_button.rect.bottomright = (rect.right - DIALOG_PAD, rect.bottom - DIALOG_PAD)
        self.fetch_button.draw(screen, self.font, mouse)
        self.close_button.draw(screen, self.font, mouse)
        if self.status:
            text = self.small.render(self.status, True, ERROR_COLOR if self.status_error else DONE_COLOR)
            screen.blit(text, text.get_rect(midleft=(self.fetch_button.rect.right + 16,
                                                     self.fetch_button.rect.centery)))

    # --- input ------------------------------------------------------------

    def click(self, pos):
        """Handles one click; returns 'close' when the dialog is done."""
        if self.close_button.hit(pos):
            return 'close'
        if self.fetch_button.hit(pos):
            self.fetch_models()
            return None
        for row, model in self.model_rows:
            if row.collidepoint(pos):
                self.settings = self.settings.with_values(model=model)
                return None
        for chips, key in ((self.ratio_chips, 'aspect_ratio'), (self.size_chips, 'image_size'),
                           (self.tries_chips, 'tries')):
            for rect, value in chips:
                if rect.collidepoint(pos):
                    self.settings = self.settings.with_values(**{key: value})
                    return None
        if not self.rect().collidepoint(pos):
            return 'close'
        return None


# ---------------------------------------------------------------------------
# One answer, side by side with the sprite it would become
# ---------------------------------------------------------------------------

def checkerboard(size):
    board = pygame.Surface(size)
    colors = ((200, 200, 200), (170, 170, 170))
    for y in range(0, size[1], CHECKER_SIZE):
        for x in range(0, size[0], CHECKER_SIZE):
            board.fill(colors[(x // CHECKER_SIZE + y // CHECKER_SIZE) % 2],
                       (x, y, CHECKER_SIZE, CHECKER_SIZE))
    return board


class Detail:
    """The image of one entry and the sprite the import would make of it."""

    def __init__(self, npc, entry, player_poses, player_shapes):
        self.npc = npc
        self.entry = entry
        self.path = npc.out_dir / entry.image
        self.image = pygame.image.load(str(self.path)).convert()
        self.result = None
        self.error = ''
        try:
            self.result = pose_review.build_sprite(
                self.path, entry.pose, player_poses, player_shapes)
        except Exception as exc:  # cell detection and extraction fail in many ways
            self.error = f'Cannot use this image: {exc}'
        self.preview = None  # (rect, factor) of the sprite in the preview panel

    def toggle_hole(self, pos):
        """Click in the preview: switch an enclosed white area transparent."""
        if not (self.result and self.preview):
            return
        rect, factor = self.preview
        if not rect.collidepoint(pos):
            return
        point = self.result.output_to_cell(
            ((pos[0] - rect.x) / factor, (pos[1] - rect.y) / factor))
        if self.result.target.surface.get_rect().collidepoint(point) \
                and self.result.target.toggle_hole(point):
            self.result.build()


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------

class SheetTool:
    def __init__(self):
        pygame.init()
        self.screen = open_window("Merchant's Rise - NPC pose generator")
        self.font = pygame.font.SysFont('segoeui', 18)
        self.small = pygame.font.SysFont('segoeui', 15)
        self.title_font = pygame.font.SysFont('segoeui', 30, bold=True)
        self.clock = pygame.time.Clock()

        self.npcs = find_npcs()
        self.player_poses = find_player_poses()
        self.npc_thumbs = {n.name: make_thumb(n.base_path, NPC_THUMB_SIZE) for n in self.npcs}
        self.npc_cards = []
        self.totals = (0, 0, 0, 0)
        self.build_npc_cards()
        self.pose_thumbs = {pose: make_thumb(path) for pose, path in self.player_poses.items()}
        self.player_shapes = None  # built on first use, needs create_new_NPC

        self.settings = Settings.load()
        self.dialog = None

        self.view = 'npcs'
        self.npc = None
        self.store = None
        self.pose_cards = []
        self.result_cards = []
        self.detail = None
        self.selected = set()
        self.scroll = 0
        self.status = ''
        self.status_error = False
        self.worker = None
        self.checker = checkerboard((1, 1))  # rebuilt at panel size when drawn

        self.back_button = Button('Back', w=90)
        self.missing_button = Button('Select missing', w=150)
        self.all_button = Button('Select all', w=110)
        self.clear_button = Button('Clear', w=90)
        self.folder_button = Button('Open folder', w=130)
        self.settings_button = Button('Settings', w=110)
        self.review_button = Button('Review', w=140)
        self.generate_button = Button('Generate', w=150)
        self.gemini_button = Button('Generate + Gemini', w=210)
        self.reject_button = Button('Not good enough', w=190)
        self.regenerate_button = Button('Regenerate', w=150)
        self.accept_button = Button('Accept', w=150)
        self.place_footer()

    # --- footer -----------------------------------------------------------

    def footer_buttons(self):
        """(left cluster, right cluster) for the current view."""
        if self.view == 'poses':
            return ((self.back_button, self.missing_button, self.all_button, self.clear_button),
                    (self.settings_button, self.review_button,
                     self.generate_button, self.gemini_button))
        if self.view == 'review':
            return ((self.back_button, self.folder_button), (self.settings_button,))
        if self.view == 'detail':
            return ((self.back_button, self.folder_button),
                    (self.reject_button, self.regenerate_button, self.accept_button))
        return ((), (self.settings_button,))

    def place_footer(self):
        """Put the footer buttons at the bottom of the window (again after a resize)."""
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

    def open_npc(self, npc):
        self.npc = npc
        self.store = ReviewStore(npc.out_dir)
        self.selected = set()
        self.detail = None
        self.worker = None
        self.set_status('')
        self.build_pose_cards()
        self.set_view('poses')

    def build_npc_cards(self):
        """One card per NPC, showing how far his set of sprites has come.

        Also fills self.totals with (npcs, sprites done, sprites possible,
        answers waiting) for the header.
        """
        self.npc_cards = []
        poses = len(self.player_poses)
        done_total = waiting_total = 0
        for npc in self.npcs:
            store = ReviewStore(npc.out_dir)
            done = sum(npc.sprite_path(pose).exists() for pose in self.player_poses)
            waiting = len(store.pending())
            rejected = sum(e.status == pose_review.REJECTED for e in store.entries)
            done_total += done
            waiting_total += waiting

            if waiting:
                note2, note2_color = f'{waiting} to review', STATUS_COLORS[pose_review.PENDING]
            elif rejected:
                note2, note2_color = f'{rejected} rejected', ERROR_COLOR
            else:
                note2, note2_color = '', None
            self.npc_cards.append(Card(
                npc, npc.name, self.npc_thumbs[npc.name],
                note=f'{done}/{poses} sprites',
                note2=note2,
                note_color=STATUS_COLORS[pose_review.ACCEPTED] if done == poses else TEXT_DIM,
                note2_color=note2_color,
                progress=done / max(1, poses),
                size=NPC_CARD_SIZE))
        self.totals = (len(self.npcs), done_total, len(self.npcs) * poses, waiting_total)

    def build_pose_cards(self):
        """One card per player pose, with what is known about it."""
        self.pose_cards = []
        for pose in self.player_poses:
            if self.npc.sprite_path(pose).exists():
                note, color = 'done', DONE_COLOR
            else:
                note = self.store.pose_note(pose)
                color = ERROR_COLOR if note == 'rejected' else STATUS_COLORS[pose_review.PENDING]
            self.pose_cards.append(
                Card(pose, pose, self.pose_thumbs[pose], note, note_color=color if note else None))

    def build_result_cards(self):
        """One card per answer of this NPC, pending ones first."""
        self.result_cards = []
        for entry in self.store.sorted_entries():
            try:
                thumb = make_thumb(self.npc.out_dir / entry.image, RESULT_THUMB_SIZE, trim=False)
            except pygame.error:
                continue
            self.result_cards.append(Card(
                entry, entry.pose, thumb, entry.status, entry.details(),
                note_color=STATUS_COLORS.get(entry.status, TEXT_DIM), size=RESULT_CARD_SIZE))

    def missing_poses(self):
        return {c.key for c in self.pose_cards if c.note != 'done'}

    def busy(self):
        """True while a batch of requests is still running."""
        return self.worker is not None and not self.worker.finished

    def shapes(self):
        """The player pose masks, built once (pulls in create_new_NPC)."""
        if self.player_shapes is None:
            self.player_shapes = pose_review.load_player_shapes(self.player_poses)
        return self.player_shapes

    # --- generating -------------------------------------------------------

    def run_generate(self, send_to_gemini=False):
        """Write the sheets and, if asked, let Gemini answer them."""
        if self.busy():
            return
        poses = [c.key for c in self.pose_cards if c.key in self.selected]
        if not poses:
            return
        out_dir, sheets = generate(self.npc, poses, self.player_poses)
        self.set_status(f'Wrote {len(poses)} sheet(s) to {out_dir.relative_to(ROOT)}')
        if send_to_gemini:
            self.start_requests([(pose, path) for pose, path in sheets.items()
                                 for _ in range(self.settings.tries)])
        elif sys.platform == 'win32':
            os.startfile(out_dir)

    def sheet_path(self, pose, sheet_name=''):
        """The reference sheet of a pose, rebuilt if it is no longer on disk."""
        path = self.npc.out_dir / (sheet_name or f'{self.npc.prefix}_{pose}_sheet.png')
        if not path.is_file():
            path = generate(self.npc, [pose], self.player_poses)[1][pose]
        return path

    def start_requests(self, jobs):
        """Hand a list of (pose, sheet_path) to the background worker."""
        if gemini_client.SDK_ERROR:
            self.set_status(f'Gemini: {gemini_client.SDK_ERROR}', error=True)
            return
        self.worker = GeminiWorker(self.npc, jobs, prompt_for(self.npc),
                                   self.settings, self.store.add)
        self.set_status(self.worker.status())

    def poll_worker(self):
        """Pick up progress from a running batch and refresh the cards."""
        if self.worker is None:
            return
        was_finished = self.worker.finished
        before = len(self.store.entries)
        self.worker.poll()
        self.set_status(self.worker.status(), error=bool(self.worker.error))
        if len(self.store.entries) != before or (self.worker.finished and not was_finished):
            self.build_pose_cards()
            if self.view in ('review', 'detail'):
                self.build_result_cards()

    # --- reviewing --------------------------------------------------------

    def open_review(self):
        self.build_result_cards()
        self.detail = None
        self.set_view('review')

    def open_detail(self, entry):
        try:
            self.detail = Detail(self.npc, entry, self.player_poses, self.shapes())
        except Exception as exc:  # a deleted or unreadable image file
            self.set_status(f'Cannot open {entry.image}: {exc}', error=True)
            return
        self.set_status(self.detail.error or f'Pose "{entry.pose}", {entry.status}',
                        error=bool(self.detail.error))
        self.set_view('detail')

    def accept_detail(self):
        """Write the sprite into the game and mark the answer accepted."""
        detail = self.detail
        if not (detail and detail.result):
            return
        try:
            path = pose_review.save_sprite(detail.result, self.npc, detail.entry.pose)
        except (pygame.error, OSError) as exc:
            self.set_status(f'Could not save: {exc}', error=True)
            return
        self.store.set_status(detail.entry, pose_review.ACCEPTED)
        self.build_pose_cards()
        self.build_result_cards()
        self.detail = None
        self.set_view('review')
        self.set_status(f'Saved {path.relative_to(ROOT)}')

    def reject_detail(self):
        """Mark the answer as not good enough, or put it back to pending."""
        entry = self.detail.entry
        pending = entry.status != pose_review.PENDING
        self.store.set_status(entry, pose_review.PENDING if pending else pose_review.REJECTED)
        self.build_pose_cards()
        self.build_result_cards()
        self.set_status(f'{entry.image} is now {entry.status}')

    def regenerate_detail(self):
        """Ask the model for another answer to the same pose."""
        if self.busy():
            return
        entry = self.detail.entry
        path = self.sheet_path(entry.pose, entry.sheet)
        self.start_requests([(entry.pose, path)] * self.settings.tries)

    def open_folder(self):
        folder = self.npc.out_dir
        folder.mkdir(parents=True, exist_ok=True)
        if sys.platform == 'win32':
            os.startfile(folder)
        else:
            self.set_status(str(folder))

    # --- layout -----------------------------------------------------------

    def current_cards(self):
        if self.view == 'poses':
            return self.pose_cards
        if self.view == 'review':
            return self.result_cards
        if self.view == 'npcs':
            return self.npc_cards
        return []

    def layout(self, cards):
        """Place the cards in a centred grid; returns the maximum scroll."""
        if not cards:
            return 0
        card_w, card_h = cards[0].rect.size
        per_row = max(1, (window_size()[0] - CARD_GAP) // (card_w + CARD_GAP))
        row_w = per_row * card_w + (per_row - 1) * CARD_GAP
        left = (window_size()[0] - row_w) // 2
        for i, card in enumerate(cards):
            row, col = divmod(i, per_row)
            card.rect.topleft = (left + col * (card_w + CARD_GAP),
                                 HEADER_HEIGHT + CARD_GAP + row * (card_h + CARD_GAP) - self.scroll)
        rows = (len(cards) + per_row - 1) // per_row
        content_h = rows * (card_h + CARD_GAP) + CARD_GAP
        visible_h = window_size()[1] - HEADER_HEIGHT - FOOTER_HEIGHT
        return max(0, content_h - visible_h)

    def detail_rects(self):
        """(image panel, preview panel) of the detail view."""
        width, height = window_size()
        top = HEADER_HEIGHT + 10
        panel_h = max(200, height - HEADER_HEIGHT - FOOTER_HEIGHT - 20)
        free = max(400, width - 3 * PANEL_GAP)
        image_w = int(free * 0.55)
        image = pygame.Rect(PANEL_GAP, top, image_w, panel_h)
        preview = pygame.Rect(image.right + PANEL_GAP, top, free - image_w, panel_h)
        return image, preview

    # --- drawing ----------------------------------------------------------

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
        for note, color in ((card.note, card.note_color or TEXT_DIM),
                            (card.note2, card.note2_color or TEXT_DIM)):
            if note:
                y += 18
                text = self.small.render(fit_text(self.small, note, width), True, color)
                self.screen.blit(text, text.get_rect(midtop=(card.rect.centerx, y)))
        if card.progress is not None:
            bar = pygame.Rect(card.rect.x + 12, card.rect.bottom - 13, card.rect.w - 24, 5)
            pygame.draw.rect(self.screen, BAR_BG, bar, border_radius=3)
            share = max(0.0, min(1.0, card.progress))
            filled = round(bar.w * share)
            if filled:
                color = STATUS_COLORS[pose_review.ACCEPTED] if share >= 1 else DONE_COLOR
                pygame.draw.rect(self.screen, color, (bar.x, bar.y, filled, bar.h), border_radius=3)

    def draw_cards(self, mouse):
        clip = pygame.Rect(0, HEADER_HEIGHT, window_size()[0],
                           window_size()[1] - HEADER_HEIGHT - FOOTER_HEIGHT)
        self.screen.set_clip(clip)
        for card in self.current_cards():
            if card.rect.colliderect(clip):
                # Only pose cards are selectable; a review card's key is an Entry.
                self.draw_card(card, mouse, self.view == 'poses' and card.key in self.selected)
        self.screen.set_clip(None)

    def draw_panel(self, rect, title):
        pygame.draw.rect(self.screen, CARD_BG, rect, border_radius=8)
        text = self.small.render(title, True, TEXT_DIM)
        self.screen.blit(text, (rect.x + 10, rect.y - 20))

    def draw_detail(self, mouse):
        image_rect, preview_rect = self.detail_rects()
        detail = self.detail

        self.draw_panel(image_rect, f'What the model returned  ({detail.entry.image})')
        area = image_rect.inflate(-20, -20)
        size = detail.image.get_size()
        factor = min(area.w / size[0], area.h / size[1], 1.0)
        shown = pygame.transform.smoothscale(
            detail.image, (max(1, int(size[0] * factor)), max(1, int(size[1] * factor))))
        self.screen.blit(shown, shown.get_rect(center=area.center))

        self.draw_panel(preview_rect, 'Player and new sprite at the same scale  (click white gaps)')
        area = preview_rect.inflate(-20, -20)
        if not self.checker.get_rect().contains(pygame.Rect((0, 0), area.size)):
            self.checker = checkerboard(area.size)
        self.screen.blit(self.checker, area, pygame.Rect((0, 0), area.size))
        detail.preview = None
        if not detail.result:
            text = self.small.render(detail.error, True, ERROR_COLOR)
            self.screen.blit(text, text.get_rect(center=area.center))
            return

        player, output = detail.result.player, detail.result.output
        gap = 20
        total = (player.get_width() + output.get_width() + gap,
                 max(player.get_height(), output.get_height()))
        factor = min((area.w - 20) / total[0], (area.h - 50) / total[1], 1.5)
        pw, ph = int(player.get_width() * factor), int(player.get_height() * factor)
        ow, oh = int(output.get_width() * factor), int(output.get_height() * factor)
        baseline = area.bottom - 40
        start_x = area.centerx - int(total[0] * factor) // 2
        # Both canvases stand on the player's baseline.
        player_bottom = detail.result.player_offset[1] + player.get_height()
        output_pos = (start_x + pw + int(gap * factor), baseline - int(player_bottom * factor))
        self.screen.blit(pygame.transform.smoothscale(player, (pw, ph)), (start_x, baseline - ph))
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
            npcs, done, possible, waiting = self.totals
            if not npcs:
                return ('1. Choose the NPC',
                        f'No folder in {NPC_DIR.relative_to(ROOT)} has a {SHEET_BASE_POSE} sprite')
            hint = (f'{npcs} NPCs in {NPC_DIR.relative_to(ROOT)}  -  '
                    f'{done} of {possible} sprites drawn ({done * 100 // max(1, possible)}%), '
                    f'{possible - done} still missing')
            if waiting:
                hint += f'  -  {waiting} answer(s) waiting for review'
            return (f'1. Choose the NPC  -  {done}/{possible} sprites', hint)
        if self.view == 'poses':
            return (f'2. Player pose(s) to copy for "{self.npc.name}"',
                    'Click to toggle. Each selected pose becomes one sheet. "done" = the NPC '
                    'already has that sprite. Enter = sheets only, Ctrl+Enter = sheets + Gemini, S = settings.')
        if self.view == 'review':
            waiting = len(self.store.pending())
            return (f'3. Answers for "{self.npc.name}"  -  {waiting} waiting',
                    'Click an answer to judge it. Accepted ones are already in the game.')
        return (f'{self.detail.entry.pose}  -  {self.detail.entry.image}',
                f'{self.detail.entry.details()}  -  Enter = accept, Del = not good enough, S = settings')

    def draw(self):
        mouse = pygame.mouse.get_pos()
        self.screen.fill(BG)
        if self.view == 'detail':
            self.draw_detail(mouse)
        else:
            self.draw_cards(mouse)

        title, hint = self.header_text()
        self.screen.blit(self.title_font.render(title, True, TEXT), (20, 12))
        self.screen.blit(self.small.render(hint, True, TEXT_DIM), (22, 56))
        if self.status:
            text = self.small.render(self.status, True, ERROR_COLOR if self.status_error else DONE_COLOR)
            self.screen.blit(text, text.get_rect(topright=(window_size()[0] - 20, 20)))
        summary = self.small.render(self.settings.summary(), True, TEXT_DIM)
        self.screen.blit(summary, summary.get_rect(topright=(window_size()[0] - 20, 44)))

        pygame.draw.line(self.screen, CARD_BG, (0, window_size()[1] - FOOTER_HEIGHT),
                         (window_size()[0], window_size()[1] - FOOTER_HEIGHT), 2)
        self.update_buttons()
        for group in self.footer_buttons():
            for button in group:
                button.draw(self.screen, self.font, mouse)
        if self.dialog:
            self.dialog.draw(self.screen, mouse)
        pygame.display.flip()

    def update_buttons(self):
        """Labels and enabled state of the footer buttons."""
        if self.view == 'poses':
            ready = bool(self.selected) and not self.busy()
            waiting = len(self.store.pending())
            self.generate_button.label = f'Generate ({len(self.selected)})'
            self.generate_button.enabled = ready
            requests = len(self.selected) * self.settings.tries
            self.gemini_button.label = 'Sending ...' if self.busy() else f'Generate + Gemini ({requests})'
            self.gemini_button.enabled = ready and not gemini_client.SDK_ERROR
            self.review_button.label = f'Review ({waiting})' if waiting else 'Review'
            self.review_button.enabled = bool(self.store.entries)
        elif self.view == 'detail':
            self.accept_button.enabled = bool(self.detail.result)
            self.reject_button.label = ('Back to pending' if self.detail.entry.status != pose_review.PENDING
                                        else 'Not good enough')
            self.regenerate_button.enabled = not self.busy() and not gemini_client.SDK_ERROR

    # --- input ------------------------------------------------------------

    def open_settings(self):
        self.dialog = SettingsDialog(self.settings, (self.font, self.small, self.title_font))

    def close_settings(self):
        self.settings = self.dialog.settings
        self.settings.save()
        self.dialog = None

    def back(self):
        if self.view == 'detail':
            self.detail = None
            self.build_result_cards()
            self.set_view('review')
        elif self.view == 'review':
            self.set_view('poses')
        elif self.view == 'poses':
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
        if self.settings_button.hit(pos) and self.settings_button in self.footer_buttons()[1]:
            self.open_settings()
            return
        if self.view != 'npcs' and self.back_button.hit(pos):
            self.back()
            return
        if self.view == 'poses':
            if self.missing_button.hit(pos):
                self.selected = self.missing_poses()
            elif self.all_button.hit(pos):
                self.selected = {c.key for c in self.pose_cards}
            elif self.clear_button.hit(pos):
                self.selected = set()
            elif self.generate_button.hit(pos):
                self.run_generate()
            elif self.gemini_button.hit(pos):
                self.run_generate(send_to_gemini=True)
            elif self.review_button.hit(pos):
                self.open_review()
            else:
                self.click_card(pos)
            return
        if self.view == 'review':
            if self.folder_button.hit(pos):
                self.open_folder()
            else:
                self.click_card(pos)
            return
        if self.view == 'detail':
            if self.folder_button.hit(pos):
                self.open_folder()
            elif self.accept_button.hit(pos):
                self.accept_detail()
            elif self.reject_button.hit(pos):
                self.reject_detail()
            elif self.regenerate_button.hit(pos):
                self.regenerate_detail()
            else:
                self.detail.toggle_hole(pos)
            return
        self.click_card(pos)

    def click_card(self, pos):
        if not HEADER_HEIGHT <= pos[1] < window_size()[1] - FOOTER_HEIGHT:
            return
        for card in self.current_cards():
            if not card.rect.collidepoint(pos):
                continue
            if self.view == 'npcs':
                self.open_npc(card.key)
            elif self.view == 'poses':
                self.selected ^= {card.key}
            elif self.view == 'review':
                self.open_detail(card.key)
            return

    def key(self, event):
        if self.dialog:
            if event.key == pygame.K_ESCAPE:
                self.close_settings()
            return
        if event.key == pygame.K_F11:
            toggle_fullscreen()
            self.place_footer()
        elif event.key == pygame.K_ESCAPE:
            if not self.back():
                return 'quit'
        elif event.key == pygame.K_s:
            self.open_settings()
        elif self.view == 'poses':
            if event.key == pygame.K_RETURN and self.selected:
                self.run_generate(send_to_gemini=bool(event.mod & pygame.KMOD_CTRL))
            elif event.key == pygame.K_r and self.store.entries:
                self.open_review()
        elif self.view == 'detail':
            if event.key == pygame.K_RETURN:
                self.accept_detail()
            elif event.key == pygame.K_DELETE:
                self.reject_detail()
        return None

    def run(self):
        while True:
            max_scroll = self.layout(self.current_cards())
            self.scroll = min(self.scroll, max_scroll)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return
                if event.type == pygame.VIDEORESIZE:
                    self.place_footer()
                elif event.type == pygame.KEYDOWN:
                    if self.key(event) == 'quit':
                        return
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
    SheetTool().run()
    pygame.quit()
