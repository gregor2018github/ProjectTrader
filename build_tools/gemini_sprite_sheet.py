"""Build 2x2 reference sheets for generating NPC sprites with Gemini.

Every sheet has the same layout:

    +---------------------------+---------------------------+
    | player_<base>.png         | <npc>_<base>.png          |
    +---------------------------+---------------------------+
    | player_<pose>.png         | (empty - Gemini draws the |
    |                           |  NPC in this pose here)   |
    +---------------------------+---------------------------+

All four cells share one size, derived from the (trimmed) sprites, with a
white margin around each sprite.

Run from anywhere:

    python build_tools/gemini_sprite_sheet.py

The window can be resized or maximised; F11 switches to full screen.

1. Pick the NPC (every folder in humans/npcs that holds a standing sprite,
   e.g. vintner_front_static.png; see BASE_POSES). The player is shown in
   the same standing pose next to it.
2. Pick one or more player poses. Poses the NPC already has a sprite for are
   marked "done"; "Select missing" picks all the others at once.
3. Generate. One sheet per pose is written to build_tools/output/<npc>/,
   together with a prompt.txt to paste into Gemini.
"""

import os
import sys
from pathlib import Path

import pygame

ROOT = Path(__file__).resolve().parent.parent
HUMANS_DIR = ROOT / 'assets' / 'map_sprites' / 'figurines' / 'humans'
PLAYER_DIR = HUMANS_DIR / 'player'
NPC_DIR = HUMANS_DIR / 'npcs'
OUTPUT_DIR = Path(__file__).resolve().parent / 'output'

# Standing poses an NPC sheet can start from, in order of preference
BASE_POSES = ('front_static', 'left_static', 'right_static', 'back_static')

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
BUTTON_BG = (110, 90, 60)
BUTTON_HOVER = (140, 115, 75)
BUTTON_DISABLED = (70, 66, 60)

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


def find_base(folder):
    """Return (pose, prefix) of the NPC's first standing sprite, or None.

    'vintner_front_static.png' -> ('front_static', 'vintner')
    """
    for pose in BASE_POSES:
        matches = sorted(folder.glob(f'*_{pose}.png'))
        if matches:
            return pose, matches[0].stem[:-len(pose) - 1]
    return None


def find_npcs():
    npcs = []
    for folder in sorted(p for p in NPC_DIR.iterdir() if p.is_dir()):
        base = find_base(folder)
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


def generate(npc, poses, player_poses):
    out_dir = OUTPUT_DIR / npc.name
    out_dir.mkdir(parents=True, exist_ok=True)
    player_base = player_poses[npc.base_pose]
    for pose in poses:
        sheet = build_sheet(player_base, npc.base_path, player_poses[pose])
        pygame.image.save(sheet, str(out_dir / f'{npc.prefix}_{pose}_sheet.png'))
    (out_dir / 'prompt.txt').write_text(
        PROMPT_TEMPLATE.format(npc=f'the {npc.prefix}'), encoding='utf-8')
    return out_dir


# ---------------------------------------------------------------------------
# Selector UI
# ---------------------------------------------------------------------------

def make_thumb(path):
    sprite = load_trimmed(path)
    w, h = sprite.get_size()
    factor = min(THUMB_SIZE[0] / w, THUMB_SIZE[1] / h)
    sprite = pygame.transform.smoothscale(sprite, (max(1, int(w * factor)), max(1, int(h * factor))))
    thumb = pygame.Surface(THUMB_SIZE)
    thumb.fill(THUMB_BG)
    thumb.blit(sprite, sprite.get_rect(center=thumb.get_rect().center))
    return thumb


class Card:
    def __init__(self, key, label, thumb, note=''):
        self.key = key
        self.label = label
        self.thumb = thumb
        self.note = note
        self.rect = pygame.Rect((0, 0), CARD_SIZE)


class Button:
    def __init__(self, label, x, y, w=170, h=44):
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


class SheetTool:
    def __init__(self):
        pygame.init()
        self.screen = open_window("Merchant's Rise - Gemini sprite sheet builder")
        self.font = pygame.font.SysFont('segoeui', 18)
        self.small = pygame.font.SysFont('segoeui', 15)
        self.title_font = pygame.font.SysFont('segoeui', 30, bold=True)
        self.clock = pygame.time.Clock()

        self.npcs = find_npcs()
        self.player_poses = find_player_poses()
        self.npc_cards = [Card(n, n.name, make_thumb(n.base_path), n.base_path.name) for n in self.npcs]
        self.pose_thumbs = {pose: make_thumb(path) for pose, path in self.player_poses.items()}

        self.npc = None
        self.pose_cards = []
        self.selected = set()
        self.scroll = 0
        self.status = ''

        self.back_button = Button('Back', 20, 0, 120)
        self.missing_button = Button('Select missing', 160, 0)
        self.all_button = Button('Select all', 350, 0, 130)
        self.clear_button = Button('Clear', 500, 0, 110)
        self.generate_button = Button('Generate', 0, 0, 220)
        self.place_footer()

    def place_footer(self):
        """Put the footer buttons at the bottom of the window (again after a resize)."""
        self.screen = pygame.display.get_surface()
        width, height = window_size()
        for button in (self.back_button, self.missing_button, self.all_button,
                       self.clear_button, self.generate_button):
            button.rect.y = height - FOOTER_HEIGHT + 13
        self.generate_button.rect.right = width - 20

    # --- state ------------------------------------------------------------

    def open_npc(self, npc):
        self.npc = npc
        self.pose_cards = []
        for pose in self.player_poses:
            done = npc.sprite_path(pose).exists()
            self.pose_cards.append(Card(pose, pose, self.pose_thumbs[pose], 'done' if done else ''))
        self.selected = set()
        self.scroll = 0
        self.status = ''

    def missing_poses(self):
        return {c.key for c in self.pose_cards if not c.note}

    def run_generate(self):
        poses = [c.key for c in self.pose_cards if c.key in self.selected]
        out_dir = generate(self.npc, poses, self.player_poses)
        self.status = f'Wrote {len(poses)} sheet(s) to {out_dir.relative_to(ROOT)}'
        if sys.platform == 'win32':
            os.startfile(out_dir)

    # --- layout -----------------------------------------------------------

    def layout(self, cards):
        per_row = max(1, (window_size()[0] - CARD_GAP) // (CARD_SIZE[0] + CARD_GAP))
        row_w = per_row * CARD_SIZE[0] + (per_row - 1) * CARD_GAP
        left = (window_size()[0] - row_w) // 2
        for i, card in enumerate(cards):
            row, col = divmod(i, per_row)
            card.rect.topleft = (left + col * (CARD_SIZE[0] + CARD_GAP),
                                 HEADER_HEIGHT + CARD_GAP + row * (CARD_SIZE[1] + CARD_GAP) - self.scroll)
        rows = (len(cards) + per_row - 1) // per_row
        content_h = rows * (CARD_SIZE[1] + CARD_GAP) + CARD_GAP
        visible_h = window_size()[1] - HEADER_HEIGHT - FOOTER_HEIGHT
        return max(0, content_h - visible_h)

    def current_cards(self):
        return self.pose_cards if self.npc else self.npc_cards

    # --- drawing ----------------------------------------------------------

    def draw_card(self, card, mouse, selected):
        if selected:
            color = CARD_SELECTED
        elif card.rect.collidepoint(mouse):
            color = CARD_HOVER
        else:
            color = CARD_BG
        pygame.draw.rect(self.screen, color, card.rect, border_radius=8)
        thumb_pos = (card.rect.x + (CARD_SIZE[0] - THUMB_SIZE[0]) // 2, card.rect.y + 10)
        self.screen.blit(card.thumb, thumb_pos)
        label = self.small.render(card.label, True, TEXT)
        self.screen.blit(label, label.get_rect(midtop=(card.rect.centerx, card.rect.y + THUMB_SIZE[1] + 16)))
        if card.note:
            note_color = DONE_COLOR if card.note == 'done' else TEXT_DIM
            note = self.small.render(card.note, True, note_color)
            self.screen.blit(note, note.get_rect(midtop=(card.rect.centerx, card.rect.y + THUMB_SIZE[1] + 34)))

    def draw(self):
        mouse = pygame.mouse.get_pos()
        self.screen.fill(BG)
        cards = self.current_cards()

        clip = pygame.Rect(0, HEADER_HEIGHT, window_size()[0], window_size()[1] - HEADER_HEIGHT - FOOTER_HEIGHT)
        self.screen.set_clip(clip)
        for card in cards:
            if card.rect.colliderect(clip):
                self.draw_card(card, mouse, card.key in self.selected)
        self.screen.set_clip(None)

        if self.npc:
            title = f'2. Player pose(s) to copy for "{self.npc.name}"'
            hint = 'Click to toggle. Each selected pose becomes one sheet. "done" = the NPC already has that sprite.'
        else:
            title = '1. Choose the NPC'
            hint = f'Folders in {NPC_DIR.relative_to(ROOT)} that contain a standing sprite ({", ".join(BASE_POSES)})'
            if not cards:
                hint = 'No NPC found. ' + hint
        self.screen.blit(self.title_font.render(title, True, TEXT), (20, 12))
        self.screen.blit(self.small.render(hint, True, TEXT_DIM), (22, 56))

        pygame.draw.line(self.screen, CARD_BG, (0, window_size()[1] - FOOTER_HEIGHT),
                         (window_size()[0], window_size()[1] - FOOTER_HEIGHT), 2)
        if self.npc:
            self.generate_button.label = f'Generate ({len(self.selected)})'
            self.generate_button.enabled = bool(self.selected)
            for button in (self.back_button, self.missing_button, self.all_button,
                           self.clear_button, self.generate_button):
                button.draw(self.screen, self.font, mouse)
        if self.status:
            status = self.small.render(self.status, True, DONE_COLOR)
            self.screen.blit(status, status.get_rect(midright=(window_size()[0] - 260,
                                                               window_size()[1] - FOOTER_HEIGHT // 2)))
        pygame.display.flip()

    # --- input ------------------------------------------------------------

    def click(self, pos):
        if self.npc:
            if self.back_button.hit(pos):
                self.npc = None
                self.scroll = 0
                self.status = ''
                return
            if self.missing_button.hit(pos):
                self.selected = self.missing_poses()
                return
            if self.all_button.hit(pos):
                self.selected = {c.key for c in self.pose_cards}
                return
            if self.clear_button.hit(pos):
                self.selected = set()
                return
            if self.generate_button.hit(pos):
                self.run_generate()
                return

        if not HEADER_HEIGHT <= pos[1] < window_size()[1] - FOOTER_HEIGHT:
            return
        for card in self.current_cards():
            if card.rect.collidepoint(pos):
                if self.npc:
                    self.selected ^= {card.key}
                    self.status = ''
                else:
                    self.open_npc(card.key)
                return

    def run(self):
        while True:
            max_scroll = self.layout(self.current_cards())
            self.scroll = min(self.scroll, max_scroll)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return
                if event.type == pygame.VIDEORESIZE:
                    self.place_footer()
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_F11:
                    toggle_fullscreen()
                    self.place_footer()
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        if self.npc:
                            self.npc = None
                            self.scroll = 0
                        else:
                            return
                    elif event.key == pygame.K_RETURN and self.npc and self.selected:
                        self.run_generate()
                elif event.type == pygame.MOUSEWHEEL:
                    self.scroll = max(0, min(max_scroll, self.scroll - event.y * 60))
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self.click(event.pos)
            self.draw()
            self.clock.tick(30)


if __name__ == '__main__':
    SheetTool().run()
    pygame.quit()
