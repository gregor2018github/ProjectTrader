"""Ledger window — scrollable event log with category filtering."""

import os
import pygame
from typing import List, Dict, Tuple, Optional, TYPE_CHECKING

from ...config.colors import (
    DARK_BROWN, BLACK, WHITE, SANDY_BROWN, BEIGE, WHEAT,
    DARK_GREEN, DARK_RED, DARK_ORANGE, DARK_GRAY, GRAY,
    DARK_BLUE,
)
from ...config.constants import FONTS_PATH, SCREEN_WIDTH, SCREEN_HEIGHT, SIDEBAR_WIDTH
from ..ui_utils import draw_9slice

if TYPE_CHECKING:
    from ...game_state import GameState

# ── layout constants ─────────────────────────────────────────────────────────
_W, _H = 860, 600
_HDR = 48       # header height
_FROW = 38      # filter-button row height
_PAD = 10
_ROW_H = 26     # height of each log row
_SCROLL_W = 12  # scrollbar width
_CLOSE = 24     # close-button size

# ── categories ───────────────────────────────────────────────────────────────
CATEGORIES = ["ALL", "TRADE", "LICENSE", "LOAN", "DONATION", "FINANCE", "SYSTEM"]

_BADGE_COLOR: Dict[str, Tuple[int, int, int]] = {
    "TRADE":    (60, 140, 60),
    "LICENSE":  (160, 120, 20),
    "LOAN":     (160, 40, 40),
    "DONATION": (100, 40, 140),
    "FINANCE":  (180, 90, 20),
    "SYSTEM":   (80, 80, 80),
}

_BADGE_W = 70   # badge pill width
_TS_W = 128     # timestamp column width


def _load_fonts():
    try:
        title = pygame.font.Font(os.path.join(FONTS_PATH, "Medici Text.ttf"), 28)
    except Exception:
        title = pygame.font.SysFont("serif", 24)
    try:
        body = pygame.font.Font(os.path.join(FONTS_PATH, "Augusta.ttf"), 17)
    except Exception:
        body = pygame.font.SysFont("arial", 15)
    return title, body


def _close(game_state: "GameState") -> None:
    game_state.info_window = None


class LedgerWindow:
    """Scrollable event-log modal with category filtering."""

    def __init__(self, screen: pygame.Surface, game_state: "GameState") -> None:
        self.screen = screen
        self.game_state = game_state
        self.title_font, self.body_font = _load_fonts()

        total_w = SCREEN_WIDTH + SIDEBAR_WIDTH
        self.panel = pygame.Rect(
            (total_w - _W) // 2,
            (SCREEN_HEIGHT - _H) // 2,
            _W, _H,
        )
        self.close_rect = pygame.Rect(
            self.panel.right - _CLOSE - 4,
            self.panel.top + 4,
            _CLOSE, _CLOSE,
        )

        # filter bar button rects
        self._filter_rects: List[pygame.Rect] = []
        self._build_filter_rects()

        self.active_filter: str = "ALL"
        self.scroll_offset: int = 0

    # ── geometry helpers ─────────────────────────────────────────────────────

    def _build_filter_rects(self) -> None:
        btn_w = (_W - 2 * _PAD) // len(CATEGORIES)
        fy = self.panel.top + _HDR
        self._filter_rects = []
        for i, _ in enumerate(CATEGORIES):
            r = pygame.Rect(self.panel.left + _PAD + i * btn_w, fy, btn_w - 2, _FROW - 4)
            self._filter_rects.append(r)

    def _list_area(self) -> pygame.Rect:
        top = self.panel.top + _HDR + _FROW + 2
        return pygame.Rect(
            self.panel.left + _PAD,
            top,
            _W - 2 * _PAD - _SCROLL_W - 2,
            self.panel.bottom - top - _PAD,
        )

    def _scrollbar_rect(self) -> pygame.Rect:
        la = self._list_area()
        return pygame.Rect(la.right + 2, la.top, _SCROLL_W, la.height)

    def _visible_rows(self) -> int:
        return self._list_area().height // _ROW_H

    def _filtered(self) -> List[Dict]:
        log = self.game_state.event_log
        if self.active_filter == "ALL":
            return list(reversed(log))
        return [e for e in reversed(log) if e["category"] == self.active_filter]

    def _max_scroll(self, entries: List[Dict]) -> int:
        vis = self._visible_rows()
        return max(0, len(entries) - vis)

    # ── drawing ──────────────────────────────────────────────────────────────

    def draw(self, alpha_scale: float = 1.0) -> None:
        if alpha_scale <= 0:
            return

        use_temp = alpha_scale < 1.0
        if use_temp:
            surf = pygame.Surface((_W + 20, _H + 20), pygame.SRCALPHA)
            off = (-self.panel.left + 10, -self.panel.top + 10)
        else:
            surf = self.screen
            off = (0, 0)

        self._draw_panel(surf, off)
        self._draw_close_btn(surf, off)
        self._draw_header(surf, off)
        self._draw_filters(surf, off)
        self._draw_entries(surf, off)
        self._draw_scrollbar(surf, off)

        if use_temp:
            surf.set_alpha(int(255 * alpha_scale))
            self.screen.blit(surf, (self.panel.left - 10, self.panel.top - 10))

    def _draw_panel(self, surf: pygame.Surface, off: Tuple[int, int]) -> None:
        r = self.panel.move(*off)
        game = self.game_state.game
        if game and hasattr(game, "pic_info_window"):
            draw_9slice(surf, game.pic_info_window, r)
        else:
            pygame.draw.rect(surf, SANDY_BROWN, r)
            pygame.draw.rect(surf, DARK_BROWN, r, 3)

    def _draw_close_btn(self, surf: pygame.Surface, off: Tuple[int, int]) -> None:
        r = self.close_rect.move(*off)
        hovered = self.close_rect.collidepoint(pygame.mouse.get_pos())
        bg = (180, 60, 60) if hovered else DARK_BROWN
        pygame.draw.rect(surf, bg, r)
        mg = 5
        pygame.draw.line(surf, WHITE, (r.left + mg, r.top + mg), (r.right - mg, r.bottom - mg), 2)
        pygame.draw.line(surf, WHITE, (r.left + mg, r.bottom - mg), (r.right - mg, r.top + mg), 2)

    def _draw_header(self, surf: pygame.Surface, off: Tuple[int, int]) -> None:
        p = self.panel.move(*off)
        ts = self.title_font.render("Ledger", True, DARK_BROWN)
        surf.blit(ts, ts.get_rect(centerx=p.centerx, top=p.top + 10))
        # divider below filter row
        div_y = p.top + _HDR + _FROW + 1
        pygame.draw.line(surf, DARK_BROWN, (p.left + _PAD, div_y), (p.right - _PAD, div_y), 1)

    def _draw_filters(self, surf: pygame.Surface, off: Tuple[int, int]) -> None:
        mouse = pygame.mouse.get_pos()
        for i, cat in enumerate(CATEGORIES):
            r = self._filter_rects[i].move(*off)
            active = self.active_filter == cat
            bg = (160, 120, 50) if active else SANDY_BROWN
            pygame.draw.rect(surf, bg, r)
            pygame.draw.rect(surf, DARK_BROWN, r, 1)
            if r.collidepoint(mouse) and not active:
                ov = pygame.Surface(r.size, pygame.SRCALPHA)
                ov.fill((0, 0, 0, 25))
                surf.blit(ov, r)
            label = self.body_font.render(cat.title(), True, WHITE if active else DARK_BROWN)
            surf.blit(label, label.get_rect(center=r.center))

    def _draw_entries(self, surf: pygame.Surface, off: Tuple[int, int]) -> None:
        entries = self._filtered()
        la = self._list_area().move(*off)

        # clip so rows never escape the list area
        clip_surf = pygame.Surface((la.width, la.height), pygame.SRCALPHA)

        vis = self._visible_rows()
        for i, entry in enumerate(entries[self.scroll_offset: self.scroll_offset + vis]):
            row_y = i * _ROW_H
            # alternating background
            if i % 2 == 0:
                pygame.draw.rect(clip_surf, (230, 215, 180, 120), pygame.Rect(0, row_y, la.width, _ROW_H))

            # timestamp
            dt = entry["timestamp"]
            ts_str = f"{dt.hour:02d}:{dt.minute:02d} {dt.day:02d}.{dt.month:02d}.{dt.year}"
            ts_surf = self.body_font.render(ts_str, True, DARK_GRAY)
            clip_surf.blit(ts_surf, ts_surf.get_rect(left=0, centery=row_y + _ROW_H // 2))

            # category badge
            cat = entry["category"]
            badge_color = _BADGE_COLOR.get(cat, (100, 100, 100))
            badge_rect = pygame.Rect(_TS_W + 2, row_y + 3, _BADGE_W, _ROW_H - 6)
            pygame.draw.rect(clip_surf, badge_color, badge_rect, border_radius=3)
            bl = self.body_font.render(cat.title(), True, WHITE)
            clip_surf.blit(bl, bl.get_rect(center=badge_rect.center))

            # event text
            text_x = _TS_W + _BADGE_W + 6
            txt = self.body_font.render(entry["text"], True, BLACK)
            clip_surf.blit(txt, txt.get_rect(left=text_x, centery=row_y + _ROW_H // 2))

        surf.blit(clip_surf, la.topleft)

        if not entries:
            empty = self.body_font.render("No entries yet.", True, GRAY)
            surf.blit(empty, empty.get_rect(center=la.move(0, la.height // 2 - _ROW_H).center))

    def _draw_scrollbar(self, surf: pygame.Surface, off: Tuple[int, int]) -> None:
        entries = self._filtered()
        total = len(entries)
        vis = self._visible_rows()
        if total <= vis:
            return

        sb = self._scrollbar_rect().move(*off)
        pygame.draw.rect(surf, WHEAT, sb)
        pygame.draw.rect(surf, DARK_BROWN, sb, 1)

        ratio = vis / total
        thumb_h = max(20, int(sb.height * ratio))
        max_scroll = total - vis
        thumb_y = sb.top + int((sb.height - thumb_h) * (self.scroll_offset / max_scroll))
        thumb = pygame.Rect(sb.left, thumb_y, sb.width, thumb_h)
        pygame.draw.rect(surf, DARK_BROWN, thumb)

    # ── event interface ───────────────────────────────────────────────────────

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEWHEEL:
            entries = self._filtered()
            self.scroll_offset = max(0, min(self._max_scroll(entries), self.scroll_offset - event.y))

    def handle_click(self, pos: Tuple[int, int]) -> bool:
        if self.close_rect.collidepoint(pos):
            _close(self.game_state)
            return True
        if not self.panel.collidepoint(pos):
            _close(self.game_state)
            return True

        # filter buttons
        for i, r in enumerate(self._filter_rects):
            if r.collidepoint(pos):
                self.active_filter = CATEGORIES[i]
                self.scroll_offset = 0
                return True

        return True
