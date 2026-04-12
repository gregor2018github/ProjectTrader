"""Main menu screen shown before the game starts."""

import os
import pygame
import datetime
from typing import Any, Dict, List, Optional, Tuple
from ..config.colors import (
    BEIGE, SANDY_BROWN, DARK_BROWN, TAN, PALE_BROWN,
    LIGHT_GRAY, DARK_GRAY, GRAY, WHITE, DARK_GREEN, BLACK,
)
from ..config.constants import SCREEN_WIDTH, SCREEN_HEIGHT, SIDEBAR_WIDTH, PICTURES_PATH, FONTS_PATH
from ..persistence.save_manager import get_save_slots, load_game as _sm_load_game
from ..config import settings_store

_TOTAL_WIDTH = SCREEN_WIDTH + SIDEBAR_WIDTH

# Button dimensions
_BTN_W = 320
_BTN_H = 56
_BTN_SPACING = 14


class MainMenu:
    """Standalone main menu displayed before any game session starts.

    Call ``run()`` to enter the event loop. It blocks until the user makes a
    choice and returns one of: ``"new_game"``, ``"load_game"``,
    ``"settings"``, or ``"exit"``.
    """

    def __init__(self) -> None:
        if not pygame.get_init():
            pygame.init()
        existing = pygame.display.get_surface()
        if existing is None:
            self.screen = pygame.display.set_mode((_TOTAL_WIDTH, SCREEN_HEIGHT))
        else:
            self.screen = existing
        pygame.display.set_caption("Merchant's Rise")
        self.clock = pygame.time.Clock()

        try:
            icon = pygame.image.load(os.path.join(PICTURES_PATH, "Icon.png"))
            pygame.display.set_icon(icon)
        except Exception:
            pass

        # Fonts
        try:
            self.title_font = pygame.font.Font(
                os.path.join(FONTS_PATH, "Medici Text.ttf"), 52
            )
            self.subtitle_font = pygame.font.Font(
                os.path.join(FONTS_PATH, "Augusta.ttf"), 22
            )
            self.button_font = pygame.font.Font(
                os.path.join(FONTS_PATH, "RomanAntique.ttf"), 28
            )
        except Exception:
            self.title_font = pygame.font.SysFont("arial", 52, bold=True)
            self.subtitle_font = pygame.font.SysFont("arial", 22)
            self.button_font = pygame.font.SysFont("arial", 28)

        # Custom cursor
        self.cursor_img: Optional[pygame.Surface] = None
        try:
            cursor_path = os.path.join(PICTURES_PATH, "cursor_1.png")
            if os.path.exists(cursor_path):
                raw_cursor = pygame.image.load(cursor_path).convert_alpha()
                self.cursor_img = pygame.transform.smoothscale(raw_cursor, (30, 41))
        except Exception:
            pass
        pygame.mouse.set_visible(self.cursor_img is None)

        # Game icon displayed inside the panel
        self.icon_surf: Optional[pygame.Surface] = None
        try:
            raw = pygame.image.load(
                os.path.join(PICTURES_PATH, "Icon.png")
            ).convert_alpha()
            self.icon_surf = pygame.transform.smoothscale(raw, (90, 90))
        except Exception:
            pass

        # Panel geometry
        panel_w = 440
        panel_h = 530
        self.panel_rect = pygame.Rect(
            (_TOTAL_WIDTH - panel_w) // 2,
            (SCREEN_HEIGHT - panel_h) // 2,
            panel_w,
            panel_h,
        )

        # Buttons: (rect, label, action, enabled)
        self.buttons: List[Tuple[pygame.Rect, str, str, bool]] = []
        entries = [
            ("Start New Game", "new_game", True),
            ("Load Game",      "load_game", True),
            ("Settings",       "settings",  True),
            ("Exit",           "exit",      True),
        ]
        btn_area_top = self.panel_rect.top + 248
        cx = self.panel_rect.centerx
        for i, (label, action, enabled) in enumerate(entries):
            rect = pygame.Rect(
                cx - _BTN_W // 2,
                btn_area_top + i * (_BTN_H + _BTN_SPACING),
                _BTN_W,
                _BTN_H,
            )
            self.buttons.append((rect, label, action, enabled))

        # Load-game slot selection state
        self._view: str = "main"  # "main", "load_slots", or "settings"
        self._slots: List[Optional[Dict[str, Any]]] = []
        self._slot_rects: List[pygame.Rect] = []
        self._back_rect: pygame.Rect = pygame.Rect(0, 0, 0, 0)
        self._load_panel_rect: pygame.Rect = pygame.Rect(0, 0, 0, 0)
        self._thumb_cache: dict = {}
        self._preview_cache: dict = {}
        self._hover_slot: Optional[int] = None
        self._hover_start: int = 0
        self._thumb_rects: dict = {}

        # Settings view state — current in-flight edits before Save is clicked
        self._settings_pending: Dict[str, Any] = {}
        self._settings_panel_rect: pygame.Rect = pygame.Rect(0, 0, 0, 0)
        self._settings_toggle_rect: pygame.Rect = pygame.Rect(0, 0, 0, 0)
        self._settings_res_btn_rect: pygame.Rect = pygame.Rect(0, 0, 0, 0)
        self._settings_res_open: bool = False
        self._settings_save_rect: pygame.Rect = pygame.Rect(0, 0, 0, 0)
        self._settings_back_rect: pygame.Rect = pygame.Rect(0, 0, 0, 0)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> Tuple[str, Optional[Dict[str, Any]]]:
        """Block until the user selects an option.

        Returns:
            A ``(action, save_data)`` tuple.  ``save_data`` is ``None`` for
            every action except ``"load_game"`` with a valid save slot selected.
        """
        while True:
            mouse_pos = pygame.mouse.get_pos()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return ("exit", None)

                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if self._view == "main":
                        for rect, _label, action, enabled in self.buttons:
                            if enabled and rect.collidepoint(mouse_pos):
                                if action == "load_game":
                                    self._slots = get_save_slots()
                                    self._build_slot_rects()
                                    self._view = "load_slots"
                                elif action == "settings":
                                    self._settings_pending = settings_store.get_all()
                                    self._settings_res_open = False
                                    self._build_settings_rects()
                                    self._view = "settings"
                                else:
                                    return (action, None)

                    elif self._view == "load_slots":
                        if self._back_rect.collidepoint(mouse_pos):
                            self._view = "main"
                            continue
                        for i, rect in enumerate(self._slot_rects):
                            if rect.collidepoint(mouse_pos) and self._slots[i] is not None:
                                try:
                                    data = _sm_load_game(i + 1)
                                    return ("load_game", data)
                                except Exception:
                                    pass  # Slot corrupted — stay on screen

                    elif self._view == "settings":
                        self._handle_settings_click(mouse_pos)

            if self._view == "main":
                self._draw(mouse_pos)
            elif self._view == "load_slots":
                self._draw_load_slots(mouse_pos)
            else:
                self._draw_settings(mouse_pos)
            pygame.display.flip()
            self.clock.tick(60)

    # ------------------------------------------------------------------
    # Load-slots helpers
    # ------------------------------------------------------------------

    def _build_slot_rects(self) -> None:
        # Panel geometry — wide enough to display all save info on one line
        panel_w = 760
        panel_margin = 24
        slot_w = panel_w - 2 * panel_margin
        slot_h = 90
        slot_spacing = 12
        top_pad = 22
        title_h = 54       # approximate rendered height of title_font at 52pt
        title_gap = 10
        divider_gap = 16
        back_h = 46
        back_gap = 22
        bottom_pad = 24
        panel_h = (
            top_pad + title_h + title_gap + 1 + divider_gap
            + 3 * slot_h + 2 * slot_spacing
            + back_gap + back_h + bottom_pad
        )

        cx = _TOTAL_WIDTH // 2
        cy = SCREEN_HEIGHT // 2
        self._load_panel_rect = pygame.Rect(
            cx - panel_w // 2, cy - panel_h // 2, panel_w, panel_h
        )

        slots_top = (
            self._load_panel_rect.top
            + top_pad + title_h + title_gap + 1 + divider_gap
        )
        self._slot_rects = []
        for i in range(3):
            self._slot_rects.append(
                pygame.Rect(
                    self._load_panel_rect.left + panel_margin,
                    slots_top + i * (slot_h + slot_spacing),
                    slot_w,
                    slot_h,
                )
            )

        back_y = self._slot_rects[-1].bottom + back_gap
        self._back_rect = pygame.Rect(cx - 100, back_y, 200, back_h)

    def _draw_load_slots(self, mouse_pos: Tuple[int, int]) -> None:
        self.screen.fill(BEIGE)

        # Panel background and border (matches main menu style)
        pygame.draw.rect(self.screen, SANDY_BROWN, self._load_panel_rect, border_radius=6)
        pygame.draw.rect(self.screen, DARK_BROWN, self._load_panel_rect, 3, border_radius=6)

        # Title
        title_surf = self.title_font.render("Load Game", True, DARK_BROWN)
        title_rect = title_surf.get_rect(
            centerx=self._load_panel_rect.centerx,
            top=self._load_panel_rect.top + 22,
        )
        self.screen.blit(title_surf, title_rect)

        # Divider
        divider_y = title_rect.bottom + 10
        pygame.draw.line(
            self.screen, DARK_BROWN,
            (self._load_panel_rect.left + 30, divider_y),
            (self._load_panel_rect.right - 30, divider_y),
            1,
        )

        # Slots
        for i, rect in enumerate(self._slot_rects):
            slot_info = self._slots[i]
            hovered = slot_info is not None and rect.collidepoint(mouse_pos)

            if not slot_info:
                bg, border = LIGHT_GRAY, GRAY
            elif hovered:
                bg, border = PALE_BROWN, DARK_BROWN
            else:
                bg, border = TAN, DARK_BROWN

            pygame.draw.rect(self.screen, bg, rect, border_radius=4)
            pygame.draw.rect(self.screen, border, rect, 2, border_radius=4)

            # Thumbnail (right side of slot)
            _THUMB_W, _THUMB_H = 105, 64
            thumb_surf = None
            thumb_path = slot_info.get("thumbnail_path") if slot_info else None
            if thumb_path and os.path.exists(thumb_path):
                if i not in self._thumb_cache:
                    try:
                        raw = pygame.image.load(thumb_path).convert()
                        self._thumb_cache[i] = pygame.transform.smoothscale(raw, (_THUMB_W, _THUMB_H))
                    except Exception:
                        self._thumb_cache[i] = None
                thumb_surf = self._thumb_cache.get(i)
            if thumb_surf is not None:
                thumb_x = rect.right - _THUMB_W - 6
                thumb_y = rect.centery - _THUMB_H // 2
                self._thumb_rects[i] = pygame.Rect(thumb_x, thumb_y, _THUMB_W, _THUMB_H)
                self.screen.blit(thumb_surf, (thumb_x, thumb_y))
                pygame.draw.rect(self.screen, DARK_BROWN,
                                 pygame.Rect(thumb_x, thumb_y, _THUMB_W, _THUMB_H), 1)
            else:
                self._thumb_rects.pop(i, None)

            label_color = DARK_BROWN if slot_info else DARK_GRAY
            label_str = (slot_info.get("save_name") or f"Slot {i + 1}") if slot_info else f"Slot {i + 1}"
            label_surf = self.button_font.render(label_str, True, label_color)
            self.screen.blit(label_surf, (rect.left + 14, rect.top + 8))

            text_right = (rect.right - _THUMB_W - 14) if thumb_surf is not None else rect.right
            max_w = text_right - rect.left - 14

            def _blit_row(text: str, color: tuple, y: int) -> None:
                surf = self.subtitle_font.render(text, True, color)
                if surf.get_width() > max_w:
                    clip = pygame.Surface((max_w, surf.get_height()), pygame.SRCALPHA)
                    clip.blit(surf, (0, 0))
                    surf = clip
                self.screen.blit(surf, (rect.left + 14, y))

            if slot_info:
                try:
                    gd = datetime.datetime.fromisoformat(slot_info["game_date"])
                    game_date_str = gd.strftime("%d %b %Y  %H:%M")
                except Exception:
                    game_date_str = slot_info["game_date"]
                try:
                    sd = datetime.datetime.fromisoformat(slot_info["saved_at"])
                    saved_str = sd.strftime("%Y-%m-%d %H:%M")
                except Exception:
                    saved_str = slot_info["saved_at"]
                ps = slot_info.get("playtime_seconds", 0.0)
                h, m = int(ps) // 3600, (int(ps) % 3600) // 60
                row2 = (
                    f"{game_date_str}"
                    f"   |   {slot_info.get('wealth', slot_info['money']):.1f} G wealth"
                    f"   |   {slot_info['money']:.1f} G cash"
                )
                row3 = f"{h:02d}h {m:02d}m played   |   Saved {saved_str}"
                _blit_row(row2, DARK_BROWN, rect.top + 34)
                _blit_row(row3, DARK_BROWN, rect.top + 58)
            else:
                _blit_row("Empty", DARK_GRAY, rect.top + 34)

        # Back button
        hovered = self._back_rect.collidepoint(mouse_pos)
        pygame.draw.rect(self.screen, PALE_BROWN if hovered else TAN, self._back_rect, border_radius=4)
        pygame.draw.rect(self.screen, DARK_BROWN, self._back_rect, 2, border_radius=4)
        back_surf = self.button_font.render("Back", True, DARK_BROWN)
        self.screen.blit(back_surf, back_surf.get_rect(center=self._back_rect.center))

        # Hover preview — show full-res thumbnail after 0.5 s of hovering
        hovering = None
        for idx, thumb_rect in self._thumb_rects.items():
            if thumb_rect.collidepoint(mouse_pos):
                if self._hover_slot != idx:
                    self._hover_slot = idx
                    self._hover_start = pygame.time.get_ticks()
                hovering = idx
                break
        if hovering is None:
            self._hover_slot = None
        if self._hover_slot is not None and pygame.time.get_ticks() - self._hover_start >= 500:
            slot_info = self._slots[self._hover_slot]
            thumb_path = slot_info.get("thumbnail_path") if slot_info else None
            if thumb_path and os.path.exists(thumb_path):
                if self._hover_slot not in self._preview_cache:
                    try:
                        self._preview_cache[self._hover_slot] = pygame.image.load(thumb_path).convert()
                    except Exception:
                        self._preview_cache[self._hover_slot] = None
                preview = self._preview_cache.get(self._hover_slot)
                if preview is not None:
                    pw, ph = preview.get_size()
                    px = self.screen.get_width() // 2 - pw // 2
                    py = self.screen.get_height() // 2 - ph // 2
                    pad = 6
                    shadow = pygame.Surface((pw + pad * 2, ph + pad * 2), pygame.SRCALPHA)
                    shadow.fill((0, 0, 0, 180))
                    self.screen.blit(shadow, (px - pad, py - pad))
                    self.screen.blit(preview, (px, py))
                    pygame.draw.rect(self.screen, DARK_BROWN, pygame.Rect(px, py, pw, ph), 2)

        if self.cursor_img and pygame.mouse.get_focused():
            self.screen.blit(self.cursor_img, pygame.mouse.get_pos())

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _draw(self, mouse_pos: Tuple[int, int]) -> None:
        self.screen.fill(BEIGE)

        # Panel background and border
        pygame.draw.rect(self.screen, SANDY_BROWN, self.panel_rect, border_radius=6)
        pygame.draw.rect(self.screen, DARK_BROWN, self.panel_rect, 3, border_radius=6)

        # --- Icon ---
        cursor_y = self.panel_rect.top + 24
        if self.icon_surf:
            icon_rect = self.icon_surf.get_rect(
                centerx=self.panel_rect.centerx, top=cursor_y
            )
            self.screen.blit(self.icon_surf, icon_rect)
            cursor_y = icon_rect.bottom + 14

        # --- Title ---
        title_surf = self.title_font.render("Merchant's Rise", True, DARK_BROWN)
        title_rect = title_surf.get_rect(
            centerx=self.panel_rect.centerx, top=cursor_y
        )
        self.screen.blit(title_surf, title_rect)
        cursor_y = title_rect.bottom + 6

        # --- Subtitle ---
        sub_surf = self.subtitle_font.render(
            "A Medieval Trading Simulation", True, PALE_BROWN
        )
        sub_rect = sub_surf.get_rect(
            centerx=self.panel_rect.centerx, top=cursor_y
        )
        self.screen.blit(sub_surf, sub_rect)
        cursor_y = sub_rect.bottom + 16

        # --- Divider ---
        pygame.draw.line(
            self.screen, DARK_BROWN,
            (self.panel_rect.left + 30, cursor_y),
            (self.panel_rect.right - 30, cursor_y),
            1,
        )

        # --- Buttons ---
        for rect, label, action, enabled in self.buttons:
            is_hovered = enabled and rect.collidepoint(mouse_pos)

            if not enabled:
                bg = LIGHT_GRAY
                text_color = DARK_GRAY
                border_color = DARK_GRAY
            elif is_hovered:
                bg = PALE_BROWN
                text_color = WHITE
                border_color = DARK_BROWN
            else:
                bg = TAN
                text_color = DARK_BROWN
                border_color = DARK_BROWN

            pygame.draw.rect(self.screen, bg, rect, border_radius=4)
            pygame.draw.rect(self.screen, border_color, rect, 2, border_radius=4)

            text_surf = self.button_font.render(label, True, text_color)
            self.screen.blit(text_surf, text_surf.get_rect(center=rect.center))

        if self.cursor_img and pygame.mouse.get_focused():
            self.screen.blit(self.cursor_img, pygame.mouse.get_pos())

    # ------------------------------------------------------------------
    # Settings view helpers
    # ------------------------------------------------------------------

    def _build_settings_rects(self) -> None:
        panel_w = 480
        panel_h = 330
        cx = _TOTAL_WIDTH // 2
        cy = SCREEN_HEIGHT // 2
        self._settings_panel_rect = pygame.Rect(
            cx - panel_w // 2, cy - panel_h // 2, panel_w, panel_h
        )

        # Row 1 — Debug overlay toggle (below title + divider)
        row1_y = self._settings_panel_rect.top + 110
        toggle_w, toggle_h = 52, 28
        self._settings_toggle_rect = pygame.Rect(
            self._settings_panel_rect.right - 40 - toggle_w,
            row1_y,
            toggle_w,
            toggle_h,
        )

        # Row 2 — Resolution dropdown button
        row2_y = row1_y + 52
        btn_w, btn_h = 160, 30
        self._settings_res_btn_rect = pygame.Rect(
            self._settings_panel_rect.right - 40 - btn_w,
            row2_y,
            btn_w,
            btn_h,
        )

        # Save / Discard buttons at the bottom
        s_btn_w, s_btn_h = 140, 42
        gap = 24
        total_btn_w = 2 * s_btn_w + gap
        btn_y = self._settings_panel_rect.bottom - s_btn_h - 24
        self._settings_save_rect = pygame.Rect(
            cx - total_btn_w // 2, btn_y, s_btn_w, s_btn_h
        )
        self._settings_back_rect = pygame.Rect(
            cx - total_btn_w // 2 + s_btn_w + gap, btn_y, s_btn_w, s_btn_h
        )

    def _res_option_rects(self) -> List[pygame.Rect]:
        """Return one rect per resolution preset, stacked below the dropdown button."""
        from ..config.settings_store import RESOLUTION_PRESETS
        item_h = 30
        rects = []
        for i in range(len(RESOLUTION_PRESETS)):
            rects.append(pygame.Rect(
                self._settings_res_btn_rect.x,
                self._settings_res_btn_rect.bottom + i * item_h,
                self._settings_res_btn_rect.width,
                item_h,
            ))
        return rects

    def _handle_settings_click(self, pos: Tuple[int, int]) -> None:
        from ..config.settings_store import RESOLUTION_PRESETS

        # ── Dropdown is open — consume the click ──────────────────────
        if self._settings_res_open:
            for i, opt_rect in enumerate(self._res_option_rects()):
                if opt_rect.collidepoint(pos):
                    self._settings_pending["resolution"] = RESOLUTION_PRESETS[i]
                    break
            self._settings_res_open = False
            return

        # ── Normal row interactions ───────────────────────────────────
        if self._settings_toggle_rect.collidepoint(pos):
            self._settings_pending["show_map_debug"] = not self._settings_pending.get("show_map_debug", True)
        elif self._settings_res_btn_rect.collidepoint(pos):
            self._settings_res_open = True
        elif self._settings_save_rect.collidepoint(pos):
            settings_store.save_all(self._settings_pending)
            self._settings_res_open = False
            self._view = "main"
        elif self._settings_back_rect.collidepoint(pos):
            self._settings_res_open = False
            self._view = "main"

    def _draw_settings(self, mouse_pos: Tuple[int, int]) -> None:
        from ..config.settings_store import RESOLUTION_PRESETS
        self.screen.fill(BEIGE)

        # Panel
        pygame.draw.rect(self.screen, SANDY_BROWN, self._settings_panel_rect, border_radius=6)
        pygame.draw.rect(self.screen, DARK_BROWN, self._settings_panel_rect, 3, border_radius=6)

        # Title
        title_surf = self.title_font.render("Settings", True, DARK_BROWN)
        title_rect = title_surf.get_rect(
            centerx=self._settings_panel_rect.centerx,
            top=self._settings_panel_rect.top + 22,
        )
        self.screen.blit(title_surf, title_rect)

        # Divider
        divider_y = title_rect.bottom + 10
        pygame.draw.line(
            self.screen, DARK_BROWN,
            (self._settings_panel_rect.left + 30, divider_y),
            (self._settings_panel_rect.right - 30, divider_y),
            1,
        )

        # ── Row 1: Debug overlay toggle ──────────────────────────────
        row1_y = self._settings_toggle_rect.centery
        label_surf = self.button_font.render("Debug Overlay", True, DARK_BROWN)
        self.screen.blit(
            label_surf,
            label_surf.get_rect(midleft=(self._settings_panel_rect.left + 30, row1_y)),
        )

        enabled = bool(self._settings_pending.get("show_map_debug", True))
        pill_color = DARK_GREEN if enabled else DARK_GRAY
        pygame.draw.rect(self.screen, pill_color, self._settings_toggle_rect, border_radius=14)
        pygame.draw.rect(self.screen, DARK_BROWN, self._settings_toggle_rect, 2, border_radius=14)

        knob_r = self._settings_toggle_rect.height // 2 - 3
        knob_x = (
            self._settings_toggle_rect.right - knob_r - 5
            if enabled
            else self._settings_toggle_rect.left + knob_r + 5
        )
        pygame.draw.circle(self.screen, WHITE, (knob_x, self._settings_toggle_rect.centery), knob_r)

        state_label = self.subtitle_font.render("On" if enabled else "Off", True, DARK_BROWN)
        self.screen.blit(
            state_label,
            state_label.get_rect(midleft=(self._settings_toggle_rect.right + 10, row1_y)),
        )

        # ── Row 2: Resolution dropdown ───────────────────────────────
        row2_y = self._settings_res_btn_rect.centery
        res_heading = self.button_font.render("Window Size", True, DARK_BROWN)
        self.screen.blit(
            res_heading,
            res_heading.get_rect(midleft=(self._settings_panel_rect.left + 30, row2_y)),
        )

        cur_res = self._settings_pending.get("resolution", RESOLUTION_PRESETS[0])

        # Dropdown closed button
        btn_hovered = (not self._settings_res_open
                       and self._settings_res_btn_rect.collidepoint(mouse_pos))
        pygame.draw.rect(
            self.screen,
            PALE_BROWN if btn_hovered else TAN,
            self._settings_res_btn_rect,
            border_radius=4,
        )
        pygame.draw.rect(self.screen, DARK_BROWN, self._settings_res_btn_rect, 2, border_radius=4)

        # Current value
        pad = 8
        val_surf = self.subtitle_font.render(cur_res, True, DARK_BROWN)
        self.screen.blit(
            val_surf,
            val_surf.get_rect(midleft=(self._settings_res_btn_rect.left + pad, row2_y)),
        )

        # Filled triangle indicator (down when closed, up when open)
        tri_cx = self._settings_res_btn_rect.right - pad - 5
        tri_cy = row2_y
        tri_hw, tri_hh = 5, 4  # half-width, half-height
        if self._settings_res_open:
            tri_pts = [
                (tri_cx - tri_hw, tri_cy + tri_hh),
                (tri_cx + tri_hw, tri_cy + tri_hh),
                (tri_cx,          tri_cy - tri_hh),
            ]
        else:
            tri_pts = [
                (tri_cx - tri_hw, tri_cy - tri_hh),
                (tri_cx + tri_hw, tri_cy - tri_hh),
                (tri_cx,          tri_cy + tri_hh),
            ]
        pygame.draw.polygon(self.screen, DARK_BROWN, tri_pts)

        # Note below the dropdown row
        note_surf = self.subtitle_font.render("(takes effect after restart)", True, DARK_GRAY)
        self.screen.blit(
            note_surf,
            note_surf.get_rect(
                midleft=(self._settings_panel_rect.left + 30,
                         self._settings_res_btn_rect.bottom + 14),
            ),
        )

        # ── Save / Discard buttons ────────────────────────────────────
        for rect, label in (
            (self._settings_save_rect, "Save"),
            (self._settings_back_rect, "Discard"),
        ):
            hovered = rect.collidepoint(mouse_pos)
            bg = PALE_BROWN if hovered else TAN
            text_col = WHITE if hovered else DARK_BROWN
            pygame.draw.rect(self.screen, bg, rect, border_radius=4)
            pygame.draw.rect(self.screen, DARK_BROWN, rect, 2, border_radius=4)
            btn_surf = self.button_font.render(label, True, text_col)
            self.screen.blit(btn_surf, btn_surf.get_rect(center=rect.center))

        # ── Dropdown list (drawn last so it floats above everything) ──
        if self._settings_res_open:
            opt_rects = self._res_option_rects()
            # Background behind the full list
            list_rect = pygame.Rect(
                opt_rects[0].x,
                opt_rects[0].y,
                opt_rects[0].width,
                sum(r.height for r in opt_rects),
            )
            # Border drawn FIRST so fill can never cover it
            pygame.draw.rect(self.screen, DARK_BROWN, list_rect, 2)
            # Fill only the interior (inset by the 2 px border on every side)
            pygame.draw.rect(self.screen, SANDY_BROWN, list_rect.inflate(-4, -4))

            for i, (opt_rect, preset) in enumerate(zip(opt_rects, RESOLUTION_PRESETS)):
                row_hovered = opt_rect.collidepoint(mouse_pos)
                if row_hovered or preset == cur_res:
                    fill_color = PALE_BROWN if row_hovered else TAN
                    # Inset 2 px from left/right border; also from top/bottom border on
                    # the first and last rows so the outer border stays visible.
                    ix = opt_rect.x + 2
                    iy = opt_rect.y + (2 if i == 0 else 0)
                    iw = opt_rect.width - 4
                    ih = opt_rect.height - (2 if i == 0 else 0) - (2 if i == len(RESOLUTION_PRESETS) - 1 else 0)
                    pygame.draw.rect(self.screen, fill_color, pygame.Rect(ix, iy, iw, ih))
                opt_surf = self.subtitle_font.render(preset, True, DARK_BROWN)
                self.screen.blit(
                    opt_surf,
                    opt_surf.get_rect(midleft=(opt_rect.left + 10, opt_rect.centery)),
                )
                if i < len(RESOLUTION_PRESETS) - 1:
                    pygame.draw.line(
                        self.screen, DARK_BROWN,
                        (opt_rect.left + 2, opt_rect.bottom),
                        (opt_rect.right - 3, opt_rect.bottom),
                    )

        if self.cursor_img and pygame.mouse.get_focused():
            self.screen.blit(self.cursor_img, pygame.mouse.get_pos())
