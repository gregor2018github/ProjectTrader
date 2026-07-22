"""General statistics overlay for the Town Hall.

Displays lifetime counters from depot.stats in categorised rows.
Follows the same overlay pattern as PopulationStats.
"""

import pygame
import os
from typing import Tuple, TYPE_CHECKING

from ...config.colors import (
    BLACK, WHITE, DARK_BROWN, SANDY_BROWN, BEIGE, DARK_GREEN
)
from ...config.constants import SCREEN_WIDTH, SCREEN_HEIGHT, SIDEBAR_WIDTH, FONTS_PATH
from ...models.minigames.woodhacking import MAX_SCORE as _WOODHACKING_MAX_SCORE
from ..ui_utils import draw_9slice

if TYPE_CHECKING:
    from ...game_state import GameState


# (label, stat_attr, format_fn)
# format_fn receives the raw value and returns a display string.
def _fmt_int(v):   return f"{int(v):,}"
def _fmt_gold(v):  return f"{v:,.0f} g"
def _fmt_tiles(v): return f"{int(v):,}"
def _fmt_woodhacking_score(v): return f"{int(v)} / {_WOODHACKING_MAX_SCORE}"

SECTIONS = [
    ("Movement", [
        ("Tiles walked",          "tiles_walked",      _fmt_tiles),
    ]),
    ("Trading", [
        ("Goods bought",          "goods_bought",      _fmt_int),
        ("Goods sold",            "goods_sold",        _fmt_int),
        ("Ledger entries",        "ledger_entries",    _fmt_int),
        ("Revenue received",      "money_received",    _fmt_gold),
        ("Spent on goods",        "money_spent_goods", _fmt_gold),
    ]),
    ("Assets & Licenses", [
        ("Properties bought",     "properties_bought", _fmt_int),
        ("Licenses acquired",     "licenses_acquired", _fmt_int),
    ]),
    ("Finance", [
        ("Loans taken",           "loans_taken",       _fmt_int),
        ("Total donated",         "donations_total",   _fmt_gold),
        ("Overdraft penalties",   "overdraft_count",   _fmt_int),
    ]),
    ("Minigames", [
        ("Minigames played",        "minigames_played",        _fmt_int),
        ("Minigame income",         "minigame_income_total",   _fmt_gold),
        ("Woodhacking Highscore",   "woodhacking_highscore",   _fmt_woodhacking_score),
    ]),
    ("Progress", [
        ("Days played",           "days_played",       _fmt_int),
    ]),
]


class StatisticsView:
    """Overlay window displaying general lifetime statistics."""

    def __init__(self, screen: pygame.Surface, game_state: 'GameState') -> None:
        self.screen = screen
        self.game_state = game_state
        self.house = game_state.active_house_menu  # enables distance-based auto-close in map_view

        # Fonts
        try:
            self.title_font   = pygame.font.Font(os.path.join(FONTS_PATH, "Medici Text.ttf"), 36)
            self.section_font = pygame.font.Font(os.path.join(FONTS_PATH, "Augusta.ttf"), 22)
            self.row_font     = pygame.font.Font(os.path.join(FONTS_PATH, "Augusta.ttf"), 19)
        except Exception:
            self.title_font   = pygame.font.SysFont("arial", 30)
            self.section_font = pygame.font.SysFont("arial", 20, bold=True)
            self.row_font     = pygame.font.SysFont("arial", 16)

        # Panel
        total_w  = SCREEN_WIDTH + SIDEBAR_WIDTH
        panel_w  = int(total_w * 0.40)
        panel_h  = int(SCREEN_HEIGHT * 0.74)
        self.panel_rect = pygame.Rect(
            (total_w - panel_w) // 2,
            (SCREEN_HEIGHT - panel_h) // 2,
            panel_w,
            panel_h,
        )

        # Close button (top-right corner)
        cb = 28
        self.close_rect = pygame.Rect(
            self.panel_rect.right - cb - 8,
            self.panel_rect.top + 8,
            cb, cb,
        )

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------

    def handle_click(self, pos: Tuple[int, int]) -> bool:
        if self.close_rect.collidepoint(pos) or not self.panel_rect.collidepoint(pos):
            self._close()
        return True

    def _close(self) -> None:
        gs = self.game_state
        gs.menu_fade_window = self
        gs.menu_fade_timer  = gs.menu_fade_duration
        gs.info_window      = None
        gs.active_house_menu = None

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def draw(self, alpha_scale: float = 1.0) -> None:
        if alpha_scale <= 0:
            return

        pw, ph = self.panel_rect.width, self.panel_rect.height
        surf = pygame.Surface((pw, ph), pygame.SRCALPHA)

        # Frame — same image used by InfoWindow, HouseMenu, LoanDialog, etc.
        game = getattr(self.game_state, 'game', None)
        if game and hasattr(game, 'pic_info_window'):
            draw_9slice(surf, game.pic_info_window, pygame.Rect(0, 0, pw, ph))
        else:
            surf.fill((*SANDY_BROWN, 255))
            pygame.draw.rect(surf, DARK_BROWN, pygame.Rect(0, 0, pw, ph), 4)

        # Title
        title = self.title_font.render("General Statistics", True, DARK_BROWN)
        title_rect = title.get_rect(centerx=pw // 2, top=16)
        surf.blit(title, title_rect)

        # Divider under title
        line_y = title_rect.bottom + 12
        pygame.draw.line(surf, DARK_BROWN, (30, line_y), (pw - 30, line_y), 2)

        # Close button (local coords)
        lc = self.close_rect.move(-self.panel_rect.x, -self.panel_rect.y)
        hovered = alpha_scale >= 1.0 and self.close_rect.collidepoint(pygame.mouse.get_pos())
        bg = (180, 60, 60) if hovered else DARK_BROWN
        pygame.draw.rect(surf, bg, lc)
        m = 5
        pygame.draw.line(surf, WHITE, (lc.left+m, lc.top+m), (lc.right-m, lc.bottom-m), 2)
        pygame.draw.line(surf, WHITE, (lc.left+m, lc.bottom-m), (lc.right-m, lc.top+m), 2)

        # Retrieve stats
        stats = getattr(getattr(self.game_state, 'game', None), 'depot', None)
        stats = getattr(stats, 'stats', None)

        # Content area
        pad_x = 30
        y = line_y + 18

        row_h = self.row_font.get_height() + 6

        for section_label, rows in SECTIONS:
            # Section heading
            sec_surf = self.section_font.render(section_label, True, DARK_BROWN)
            surf.blit(sec_surf, (pad_x, y))
            y += sec_surf.get_height() + 2

            # Thin rule under section heading
            pygame.draw.line(surf, DARK_BROWN, (pad_x, y), (pw - pad_x, y), 1)
            y += 6

            # Draw a single background block behind all rows in this section
            group_h = row_h * len(rows)
            group_rect = pygame.Rect(pad_x - 4, y - 2, pw - pad_x * 2 + 8, group_h + 4)
            pygame.draw.rect(surf, WHITE, group_rect)
            pygame.draw.rect(surf, DARK_BROWN, group_rect, 1)

            for label, attr, fmt in rows:
                raw = getattr(stats, attr, 0) if stats else 0
                value_str = fmt(raw)

                lbl_surf = self.row_font.render(label, True, BLACK)
                surf.blit(lbl_surf, (pad_x, y))

                val_surf = self.row_font.render(value_str, True, DARK_GREEN if raw else DARK_BROWN)
                val_rect = val_surf.get_rect(right=pw - pad_x, top=y)
                surf.blit(val_surf, val_rect)

                y += row_h

            y += 12  # gap between sections

        # Darken background behind the panel
        total_w = SCREEN_WIDTH + SIDEBAR_WIDTH
        overlay = pygame.Surface((total_w, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, int(120 * alpha_scale)))
        self.screen.blit(overlay, (0, 0))

        if alpha_scale < 1.0:
            surf.set_alpha(int(255 * alpha_scale))
        self.screen.blit(surf, self.panel_rect)
