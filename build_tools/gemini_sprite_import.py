"""Turn a Gemini result image into a finished NPC sprite.

Counterpart of gemini_sprite_sheet.py. Gemini returns the sheet you gave it
with the empty cell filled in. Both layouts are understood:

    1x2 (first sprite of a new NPC)       2x2 (sheet from gemini_sprite_sheet.py)
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
the player's canvas size, e.g. npcs/trader_vintner/vintner_left_static.png.

Run from anywhere:

    python build_tools/gemini_sprite_import.py

1. Pick the NPC (every folder in humans/npcs, empty ones included).
2. Drop the Gemini image onto the window, or click "Open image".
3. Check the pose (it is detected, click another one to change it). Enclosed
   white areas (e.g. a gap between arm and body) stay white; click them in the
   preview to make them transparent, click again to undo.
4. Save (Enter). The Gemini image is kept in build_tools/output/<npc>/results/.
"""

import shutil
import sys
from pathlib import Path

import pygame

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gemini_sprite_sheet import (  # noqa: E402
    BG, BUTTON_BG, CARD_BG, CARD_GAP, CARD_HOVER, CARD_SIZE, DONE_COLOR, FOOTER_HEIGHT,
    HEADER_HEIGHT, NPC_DIR, OUTPUT_DIR, PLAYER_DIR, ROOT, TEXT, TEXT_DIM, THUMB_BG, THUMB_SIZE,
    WINDOW_SIZE, BASE_SUFFIX, Button, Card, make_thumb,
)

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

# Layout of the import screen
SOURCE_RECT = pygame.Rect(20, HEADER_HEIGHT + 10, 520, WINDOW_SIZE[1] - HEADER_HEIGHT - FOOTER_HEIGHT - 20)
COMPARE_RECT = pygame.Rect(560, SOURCE_RECT.y, 440, SOURCE_RECT.height)
POSE_RECT = pygame.Rect(1020, SOURCE_RECT.y, 240, SOURCE_RECT.height)
POSE_ROW = 27
CHECKER = ((200, 200, 200), (170, 170, 170))
CHECKER_SIZE = 12
REF_COLOR = (80, 200, 110)
TARGET_COLOR = (220, 60, 60)
ERROR_COLOR = (240, 110, 90)


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

class Npc:
    def __init__(self, folder):
        self.folder = folder
        self.name = folder.name
        bases = sorted(folder.glob(f'*{BASE_SUFFIX}.png'))
        if bases:
            # 'butcher_left_static.png' -> 'butcher'
            self.prefix = bases[0].stem[:-len(BASE_SUFFIX)]
        else:
            # 'trader_vintner' -> 'vintner'
            self.prefix = folder.name.split('_', 1)[-1]

    @property
    def base_path(self):
        return self.sprite_path(BASE_SUFFIX[1:])

    def sprite_path(self, pose):
        return self.folder / f'{self.prefix}_{pose}.png'


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


class ImportTool:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode(WINDOW_SIZE)
        pygame.display.set_caption("Merchant's Rise - Gemini sprite import")
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
        self.checker_compare = checkerboard(COMPARE_RECT.size)

        self.npcs = find_npcs()
        self.npc_cards = [self.make_npc_card(n) for n in self.npcs]
        self.npc = None
        self.result = None
        self.scroll = 0
        self.status = ''
        self.status_color = DONE_COLOR
        self.compare_layout = None

        footer_y = WINDOW_SIZE[1] - FOOTER_HEIGHT + 13
        self.back_button = Button('Back', 20, footer_y, 120)
        self.open_button = Button('Open image', 160, footer_y)
        self.save_button = Button('Save', WINDOW_SIZE[0] - 240, footer_y, 220)

    # --- state ------------------------------------------------------------

    def make_npc_card(self, npc):
        thumb = make_thumb(npc.base_path) if npc.base_path.exists() else self.placeholder
        done = sum(npc.sprite_path(pose).exists() for pose in self.player_poses)
        return Card(npc, npc.name, thumb, f'{done}/{len(self.player_poses)} sprites')

    def open_npc(self, npc):
        self.npc = npc
        self.result = None
        self.status = ''

    def back(self):
        self.npc_cards = [self.make_npc_card(n) for n in self.npcs]
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

    def layout_cards(self):
        per_row = max(1, (WINDOW_SIZE[0] - CARD_GAP) // (CARD_SIZE[0] + CARD_GAP))
        row_w = per_row * CARD_SIZE[0] + (per_row - 1) * CARD_GAP
        left = (WINDOW_SIZE[0] - row_w) // 2
        for i, card in enumerate(self.npc_cards):
            row, col = divmod(i, per_row)
            card.rect.topleft = (left + col * (CARD_SIZE[0] + CARD_GAP),
                                 HEADER_HEIGHT + CARD_GAP + row * (CARD_SIZE[1] + CARD_GAP) - self.scroll)
        rows = (len(self.npc_cards) + per_row - 1) // per_row
        content_h = rows * (CARD_SIZE[1] + CARD_GAP) + CARD_GAP
        return max(0, content_h - (WINDOW_SIZE[1] - HEADER_HEIGHT - FOOTER_HEIGHT))

    def draw_card(self, card, mouse):
        color = CARD_HOVER if card.rect.collidepoint(mouse) else CARD_BG
        pygame.draw.rect(self.screen, color, card.rect, border_radius=8)
        self.screen.blit(card.thumb, (card.rect.x + (CARD_SIZE[0] - THUMB_SIZE[0]) // 2, card.rect.y + 10))
        label = self.small.render(card.label, True, TEXT)
        self.screen.blit(label, label.get_rect(midtop=(card.rect.centerx, card.rect.y + THUMB_SIZE[1] + 16)))
        note = self.small.render(card.note, True, TEXT_DIM)
        self.screen.blit(note, note.get_rect(midtop=(card.rect.centerx, card.rect.y + THUMB_SIZE[1] + 34)))

    def draw_npc_list(self, mouse):
        clip = pygame.Rect(0, HEADER_HEIGHT, WINDOW_SIZE[0], WINDOW_SIZE[1] - HEADER_HEIGHT - FOOTER_HEIGHT)
        self.screen.set_clip(clip)
        for card in self.npc_cards:
            if card.rect.colliderect(clip):
                self.draw_card(card, mouse)
        self.screen.set_clip(None)

    # --- import screen ----------------------------------------------------

    def draw_panel_title(self, rect, text):
        label = self.small.render(text, True, TEXT_DIM)
        self.screen.blit(label, (rect.x, rect.y - 2))

    def draw_source(self):
        area = SOURCE_RECT.inflate(0, -24).move(0, 12)
        pygame.draw.rect(self.screen, CARD_BG, area, border_radius=6)
        self.draw_panel_title(SOURCE_RECT, 'Gemini image  (green = player, red = new sprite)')
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
        area = COMPARE_RECT.inflate(0, -24).move(0, 12)
        self.draw_panel_title(COMPARE_RECT, 'Player and new sprite at the same scale  (click white gaps)')
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
        return [(pose, pygame.Rect(POSE_RECT.x, POSE_RECT.y + 12 + i * POSE_ROW, POSE_RECT.w, POSE_ROW - 3))
                for i, pose in enumerate(self.player_poses)]

    def draw_poses(self, mouse):
        self.draw_panel_title(POSE_RECT, 'Pose')
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
            self.save_button.rect.right = WINDOW_SIZE[0] - 20
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
            title = f'2. Load a Gemini result for "{self.npc.name}"'
            hint = f'Sprites are saved as {self.npc.prefix}_<pose>.png in {self.npc.folder.relative_to(ROOT)}'
        else:
            self.draw_npc_list(mouse)
            title = '1. Choose the NPC'
            hint = f'Folders in {NPC_DIR.relative_to(ROOT)}'
        self.screen.blit(self.title_font.render(title, True, TEXT), (20, 12))
        self.screen.blit(self.small.render(hint, True, TEXT_DIM), (22, 56))

        pygame.draw.line(self.screen, CARD_BG, (0, WINDOW_SIZE[1] - FOOTER_HEIGHT),
                         (WINDOW_SIZE[0], WINDOW_SIZE[1] - FOOTER_HEIGHT), 2)
        if self.status:
            status = self.small.render(self.status, True, self.status_color)
            self.screen.blit(status, status.get_rect(midleft=(self.open_button.rect.right + 20,
                                                              WINDOW_SIZE[1] - FOOTER_HEIGHT // 2)))
        pygame.display.flip()

    # --- input ------------------------------------------------------------

    def click(self, pos):
        if not self.npc:
            if HEADER_HEIGHT <= pos[1] < WINDOW_SIZE[1] - FOOTER_HEIGHT:
                for card in self.npc_cards:
                    if card.rect.collidepoint(pos):
                        self.open_npc(card.key)
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
