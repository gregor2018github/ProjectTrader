"""Paths, colours, sizes and the window: what every screen of the Sprite Manager shares."""

from pathlib import Path

import pygame

import pose_review
from win_window import snap_left

ROOT = Path(__file__).resolve().parents[2]
HUMANS_DIR = ROOT / 'assets' / 'map_sprites' / 'figurines' / 'humans'
PLAYER_DIR = HUMANS_DIR / 'player'
NPC_DIR = HUMANS_DIR / 'npcs'
OUTPUT_DIR = ROOT / 'build_tools' / 'output'

# Window
WINDOW_SIZE = (1280, 820)  # starting size where it cannot be snapped into the left half of the screen
HEADER_HEIGHT = 90
FOOTER_HEIGHT = 70

# Cards
CARD_SIZE = (140, 205)
THUMB_SIZE = (116, 150)
NPC_THUMB_SIZE = (148, 150)
RESULT_CARD_SIZE = (222, 234)
RESULT_THUMB_SIZE = (198, 130)
CARD_GAP = 14
PANEL_GAP = 20
CHECKER_SIZE = 12

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

# Dialogs
DIALOG_PAD = 24
CHIP_HEIGHT = 32
CHIP_GAP = 8


def window_size():
    """Current size of the (resizable) tool window."""
    surface = pygame.display.get_surface()
    return surface.get_size() if surface else WINDOW_SIZE


def open_window(caption):
    """The resizable tool window, in the left half of the screen (win_window.py)."""
    screen = pygame.display.set_mode(WINDOW_SIZE, pygame.RESIZABLE)
    pygame.display.set_caption(caption)
    snap_left()
    return pygame.display.get_surface() or screen


def toggle_fullscreen():
    """Switch between full screen and a normal resizable window."""
    if pygame.display.get_surface().get_flags() & pygame.FULLSCREEN:
        screen = pygame.display.set_mode(WINDOW_SIZE, pygame.RESIZABLE)
        snap_left()
        return pygame.display.get_surface() or screen
    return pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
