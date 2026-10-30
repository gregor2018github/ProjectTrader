"""What the inventory windows share: sections of goods slots on a dimmed overlay.

A window is one or more sections of slots (a warehouse's, the player's
hands), each with a heading line, a fill bar for all its slots and the slots
themselves: big ones with the good's picture, name, amount and a fill bar of
their own (green once full), or, for slots of a single unit (by hand), small
ones with only the picture.

Everything but the hover effects is drawn once into a cached panel, which is
only redrawn when what it shows changes, so an open window costs about as
much per frame as two blits.
"""

import os
import pygame
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from ...config.colors import (
    BEIGE, DARK_BROWN, DARK_GRAY, LIGHT_GRAY, WHEAT, WHITE,
    MUTED_GREEN, MUTED_ORANGE, MUTED_RED, SANDY_BROWN,
)
from ...config.constants import FONTS_PATH, SCREEN_HEIGHT, SCREEN_WIDTH, SIDEBAR_WIDTH
from ..ui_utils import draw_9slice, draw_mouse_tooltip

if TYPE_CHECKING:
    from ...game_state import GameState


COLS = 5
BOX_W = 104                  # a slot's box, with the good's picture, name and amount
BOX_H = 116
BAR_W = 12                   # the slot's fill bar, right of its box
BAR_GAP = 6
CELL_W = BOX_W + BAR_GAP + BAR_W
COL_GAP = 16
ROW_GAP = 16
TOTAL_BAR_H = 18             # a section's fill bar for all its slots, over them
NEARLY_FULL = 0.75           # fill share from which a section's bar turns orange
ICON_SIZE = 56
HAND_BOX = 60                # a slot of a single unit (the hands'): only the good's picture, no fill bar
HAND_GAP = 8
HAND_ICON_SIZE = 44
SIDE_PAD = 36
PANEL_W = COLS * CELL_W + (COLS - 1) * COL_GAP + 2 * SIDE_PAD
SUBTITLE_Y = 62
RULE_Y = 96
FIRST_SECTION_Y = 110        # where the first section's heading line goes
EMPTY_SLOT = (230, 225, 210)  # the faded placeholder of the license overview
DIM_ALPHA = 120              # how dark the game behind the window gets

# Good pictures by name and size, scaled once per session from the game's
# cut-out goods_icon images (or the 30px icons where a good has none)
_icons: Dict[Tuple[str, int], Optional[pygame.Surface]] = {}


FILTER_BUTTON = 20           # a slot's reservation button, in its top-left corner


def draw_funnel(surf: pygame.Surface, rect: pygame.Rect, color: Tuple[int, int, int]) -> None:
    """A small funnel, the sign of a filter, filling rect."""
    x, y, w, h = rect
    pygame.draw.polygon(surf, color, [
        (x + w * 0.15, y + h * 0.2), (x + w * 0.85, y + h * 0.2),
        (x + w * 0.58, y + h * 0.52), (x + w * 0.58, y + h * 0.82),
        (x + w * 0.42, y + h * 0.72), (x + w * 0.42, y + h * 0.52),
    ])


class SlotSection:
    """One block of slots on a window: its heading line, total bar and slot rects.

    Slots of a single unit (by hand) are drawn small, side by side in one
    row, without a fill bar of their own. A section with reservations has a
    small funnel button in each slot's corner to reserve it for one good.
    """

    def __init__(self, kind: str, slot_count: int, slot_size: int, top: int,
                 label: str, amount_label: str, reservations: bool = False) -> None:
        """
        Args:
            kind: Which section this is, as the window names it.
            slot_count: How many slots it has.
            slot_size: Units of one good a slot holds.
            top: Its heading line's top, in panel coordinates.
            label: The heading's left text ("Slots in use" gets the count added).
            amount_label: The heading's right text, before the units held.
            reservations: Whether its slots can be reserved for one good.
        """
        self.kind = kind
        self.reservations = reservations
        self.slot_count = slot_count
        self.slot_size = slot_size
        self.label = label
        self.amount_label = amount_label
        self.by_hand = slot_size == 1
        self.cols = max(1, slot_count) if self.by_hand else COLS
        self.box_w, self.box_h = (HAND_BOX, HAND_BOX) if self.by_hand else (BOX_W, BOX_H)
        self.cell_w = HAND_BOX if self.by_hand else CELL_W
        self.col_gap = HAND_GAP if self.by_hand else COL_GAP
        self.heading_y = top
        self.bar_y = top + 30
        self.grid_y = top + 68
        rows = max(1, -(-slot_count // self.cols))
        self.bottom = self.grid_y + rows * self.box_h + (rows - 1) * ROW_GAP
        self.slot_rects: List[Tuple[pygame.Rect, pygame.Rect]] = []
        self.bar_rect = pygame.Rect(0, 0, 0, 0)

    def place(self, panel: pygame.Rect) -> None:
        """Lay the slots out on the panel, now that it has its place on screen."""
        # Slot boxes and their fill bars in screen space, row by row; a short
        # last row (or fewer slots than columns) is centred
        slot_count, cols = self.slot_count, self.cols
        self.slot_rects = []
        for i in range(slot_count):
            row, col = divmod(i, cols)
            in_row = min(cols, slot_count - row * cols)
            row_w = in_row * self.cell_w + (in_row - 1) * self.col_gap
            x = panel.x + (panel.width - row_w) // 2 + col * (self.cell_w + self.col_gap)
            y = panel.y + self.grid_y + row * (self.box_h + ROW_GAP)
            box = pygame.Rect(x, y, self.box_w, self.box_h)
            if self.by_hand:
                bar = pygame.Rect(box.right, y, 0, 0)
            else:
                bar = pygame.Rect(box.right + BAR_GAP, y, BAR_W, BOX_H)
            self.slot_rects.append((box, bar))

        # The section's fill bar spans its first row of slots, bars included (panel coordinates)
        first_row = self.slot_rects[:cols]
        if first_row:
            left, right = first_row[0][0].left - panel.x, first_row[-1][1].right - panel.x
        else:
            left, right = SIDE_PAD, panel.width - SIDE_PAD
        self.bar_rect = pygame.Rect(left, self.bar_y, right - left, TOTAL_BAR_H)

    def filter_button(self, index: int) -> pygame.Rect:
        """The reservation button of a slot, in screen space."""
        box = self.slot_rects[index][0]
        return pygame.Rect(box.x + 4, box.y + 4, FILTER_BUTTON, FILTER_BUTTON)

    def filter_button_at(self, pos: Tuple[int, int]) -> Optional[int]:
        if not self.reservations:
            return None
        for i in range(len(self.slot_rects)):
            if self.filter_button(i).collidepoint(pos):
                return i
        return None

    def slot_at(self, pos: Tuple[int, int]) -> Optional[int]:
        for i, (box, bar) in enumerate(self.slot_rects):
            if box.collidepoint(pos) or (bar.width and bar.collidepoint(pos)):
                return i
        return None


class InventoryWindow:
    """A centred overlay of slot sections under a title, with a footer line.

    Subclasses build their sections and call _place_panel(), and say what the
    slots hold (_read_slots), what the footer reads (_footer) and what a
    hovered slot's tooltip says (_slot_tooltip). They may add to the panel
    (_draw_extra, with _extra_key telling when it changes) and draw over it
    every frame (_draw_overlay).
    """

    def __init__(self, screen: pygame.Surface, game_state: 'GameState') -> None:
        self.screen = screen
        self.game_state = game_state

        try:
            self.title_font = pygame.font.Font(os.path.join(FONTS_PATH, "Medici Text.ttf"), 36)
            self.heading_font = pygame.font.Font(os.path.join(FONTS_PATH, "Augusta.ttf"), 24)
            self.body_font = pygame.font.Font(os.path.join(FONTS_PATH, "Augusta.ttf"), 18)
            self.small_font = pygame.font.Font(os.path.join(FONTS_PATH, "Augusta.ttf"), 16)
        except Exception:
            self.title_font = pygame.font.SysFont("arial", 30)
            self.heading_font = pygame.font.SysFont("arial", 20)
            self.body_font = pygame.font.SysFont("arial", 15)
            self.small_font = pygame.font.SysFont("arial", 13)

        game = game_state.game
        self.depot = game.depot
        self.goods_by_name = {good.name: good for good in game.goods}
        self.sections: Dict[str, SlotSection] = {}
        self.rules_y: List[int] = []  # thin lines between sections, in panel coordinates

        self._panel: Optional[pygame.Surface] = None
        self._panel_key: Optional[tuple] = None
        self._slots: Dict[str, List[Dict[str, Any]]] = {}
        self._tooltip: Optional[Tuple[str, int, str]] = None  # (section, slot index, text) of the last hover

    def _place_panel(self, sections: List[SlotSection]) -> None:
        """Size and centre the panel round the sections, a thin rule between each, and a footer line."""
        self.rules_y = [section.bottom + 20 for section in sections[:-1]]
        self.footer_rule_y = sections[-1].bottom + 18
        self.footer_y = self.footer_rule_y + 12
        panel_h = self.footer_y + 44

        total_w = SCREEN_WIDTH + SIDEBAR_WIDTH
        self.panel_rect = pygame.Rect(
            (total_w - PANEL_W) // 2, (SCREEN_HEIGHT - panel_h) // 2, PANEL_W, panel_h
        )
        self.sections = {section.kind: section for section in sections}
        for section in sections:
            section.place(self.panel_rect)
        cb_size = 28
        self.close_rect = pygame.Rect(
            self.panel_rect.right - cb_size - 8, self.panel_rect.top + 8, cb_size, cb_size
        )

        # Made once: the dimming over the game, and the hover shade of a slot
        self._dim = pygame.Surface((total_w, SCREEN_HEIGHT)).convert()
        self._dim.fill((0, 0, 0))
        self._slot_shades: Dict[Tuple[int, int], pygame.Surface] = {}
        for section in sections:
            size = (section.box_w, section.box_h)
            if size not in self._slot_shades:
                self._slot_shades[size] = pygame.Surface(size, pygame.SRCALPHA)
                self._slot_shades[size].fill((0, 0, 0, 30))

    # ------------------------------------------------------------------
    # For subclasses
    # ------------------------------------------------------------------

    def _titles(self) -> Tuple[str, str]:
        """The window's title and subtitle."""
        raise NotImplementedError

    def _read_slots(self) -> Dict[str, List[Dict[str, Any]]]:
        """Copies of every section's slots, by section kind."""
        raise NotImplementedError

    def _footer(self, slots: Dict[str, List[Dict[str, Any]]]) -> str:
        """The footer line's text."""
        raise NotImplementedError

    def _slot_tooltip(self, section: SlotSection, slot: Dict[str, Any]) -> str:
        """The tooltip of a hovered slot."""
        raise NotImplementedError

    def _extra_key(self) -> tuple:
        """What else the panel shows, beyond the slots and footer, so it is redrawn when that changes."""
        return ()

    def _draw_extra(self, surf: pygame.Surface) -> None:
        """Draw more onto the panel, under the title (panel coordinates)."""

    def _draw_overlay(self, mouse_pos: Tuple[int, int]) -> bool:
        """Draw over the panel this frame (screen coordinates); True keeps the slots' hover effects off."""
        return False

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    def _price(self, good_name: str) -> float:
        good = self.goods_by_name.get(good_name)
        return good.get_price() if good else 0.0

    def _worth(self, slots: List[Dict[str, Any]]) -> float:
        return sum(self._price(s["good"]) * s["qty"] for s in slots if s["good"])

    def _icon(self, good_name: str, icon_size: int = ICON_SIZE) -> Optional[pygame.Surface]:
        key = (good_name, icon_size)
        if key not in _icons:
            images = self.game_state.game.images
            large = images.get('goods_icon', {}).get(good_name)
            if large is not None:
                scale = icon_size / max(large.get_size())
                size = (max(1, round(large.get_width() * scale)), max(1, round(large.get_height() * scale)))
                _icons[key] = pygame.transform.smoothscale(large, size).convert_alpha()
            else:
                small = images['goods_30'].get(good_name)
                _icons[key] = (
                    pygame.transform.smoothscale(small, (icon_size, icon_size)) if small else None
                )
        return _icons[key]

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self._close()

    def handle_click(self, pos: Tuple[int, int]) -> bool:
        if self.close_rect.collidepoint(pos) or not self.panel_rect.collidepoint(pos):
            self._close()
        return True

    def _close(self) -> None:
        gs = self.game_state
        gs.menu_fade_window = self
        gs.menu_fade_timer = gs.menu_fade_duration
        gs.info_window = None
        gs.active_house_menu = None

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def draw(self, alpha_scale: float = 1.0) -> None:
        if alpha_scale <= 0:
            return

        # Redraw the panel only when something on it changed
        slots = self._read_slots()
        footer = self._footer(slots)
        key = tuple(tuple((s["good"], s["qty"], s.get("reserved")) for s in slots[kind]) for kind in self.sections)
        key += (footer, self._extra_key())
        if key != self._panel_key:
            self._slots = slots
            self._panel = self._render_panel(slots, footer)
            self._panel_key = key
            self._tooltip = None

        self._dim.set_alpha(int(DIM_ALPHA * alpha_scale))
        self.screen.blit(self._dim, (0, 0))
        self._panel.set_alpha(None if alpha_scale >= 1.0 else int(255 * alpha_scale))
        self.screen.blit(self._panel, self.panel_rect.topleft)
        if alpha_scale < 1.0:
            return  # fading out: no hover effects

        mouse_pos = pygame.mouse.get_pos()
        if self._draw_overlay(mouse_pos):
            return
        if self.close_rect.collidepoint(mouse_pos):
            self._draw_close_button(self.screen, self.close_rect, hovered=True)
            return

        for kind, section in self.sections.items():
            index = section.slot_at(mouse_pos)
            if index is None:
                continue
            box = section.slot_rects[index][0]
            self.screen.blit(self._slot_shades[box.size], box.topleft)
            if self._tooltip is None or self._tooltip[:2] != (kind, index):
                self._tooltip = (kind, index, self._slot_tooltip(section, self._slots[kind][index]))
            draw_mouse_tooltip(self.screen, self.body_font, self._tooltip[2], mouse_pos)
            break

    def _render_panel(self, slots: Dict[str, List[Dict[str, Any]]], footer: str) -> pygame.Surface:
        """Everything on the window that does not follow the mouse."""
        w, h = self.panel_rect.size
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        game = self.game_state.game
        if hasattr(game, 'pic_info_window'):
            draw_9slice(surf, game.pic_info_window, pygame.Rect(0, 0, w, h))
        else:
            surf.fill((*SANDY_BROWN, 255))
            pygame.draw.rect(surf, DARK_BROWN, pygame.Rect(0, 0, w, h), 4)

        title_text, subtitle_text = self._titles()
        title = self.title_font.render(title_text, True, DARK_BROWN)
        surf.blit(title, title.get_rect(centerx=w // 2, top=16))
        subtitle = self.heading_font.render(subtitle_text, True, DARK_GRAY)
        surf.blit(subtitle, subtitle.get_rect(centerx=w // 2, top=SUBTITLE_Y))
        pygame.draw.line(surf, DARK_BROWN, (30, RULE_Y), (w - 30, RULE_Y), 2)
        self._draw_close_button(surf, self.close_rect.move(-self.panel_rect.x, -self.panel_rect.y), hovered=False)
        self._draw_extra(surf)

        for kind, section in self.sections.items():
            self._draw_section(surf, section, slots[kind])
        for rule_y in self.rules_y:
            pygame.draw.line(surf, DARK_BROWN, (30, rule_y), (w - 30, rule_y), 1)

        pygame.draw.line(surf, DARK_BROWN, (30, self.footer_rule_y), (w - 30, self.footer_rule_y), 1)
        footer_surf = self.body_font.render(footer, True, DARK_BROWN)
        surf.blit(footer_surf, (SIDE_PAD, self.footer_y))

        return surf.convert_alpha()

    def _draw_section(self, surf: pygame.Surface, section: SlotSection, slots: List[Dict[str, Any]]) -> None:
        """A section's heading line ('in use' count and units), its total bar and its slots."""
        w = self.panel_rect.width
        used = [s for s in slots if s["good"] is not None]
        stored = sum(s["qty"] for s in used)
        capacity = len(slots) * section.slot_size

        heading = section.label if section.by_hand else f"{section.label}:  {len(used)} / {len(slots)}"
        heading_surf = self.body_font.render(heading, True, DARK_BROWN)
        surf.blit(heading_surf, (SIDE_PAD, section.heading_y))
        unit = "goods" if section.by_hand else "units"
        amount_surf = self.body_font.render(
            f"{section.amount_label}:  {stored} / {capacity} {unit}", True, DARK_BROWN)
        surf.blit(amount_surf, amount_surf.get_rect(right=w - SIDE_PAD, top=section.heading_y))

        bar = section.bar_rect
        pygame.draw.rect(surf, WHEAT, bar)
        share = min(1.0, stored / capacity) if capacity else 0.0
        if share > 0:
            color = MUTED_RED if share >= 1.0 else MUTED_ORANGE if share >= NEARLY_FULL else MUTED_GREEN
            pygame.draw.rect(surf, color, pygame.Rect(bar.x, bar.y, max(2, round(bar.width * share)), bar.height))
        pygame.draw.rect(surf, DARK_BROWN, bar, 2)

        for (box, slot_bar), slot in zip(section.slot_rects, slots):
            box = box.move(-self.panel_rect.x, -self.panel_rect.y)
            if section.by_hand:
                self._draw_hand_slot(surf, box, slot)
            else:
                self._draw_slot(surf, box, slot_bar.move(-self.panel_rect.x, -self.panel_rect.y),
                                slot, section.slot_size, section.reservations)

    @staticmethod
    def _draw_close_button(surf: pygame.Surface, rect: pygame.Rect, hovered: bool) -> None:
        pygame.draw.rect(surf, (180, 60, 60) if hovered else DARK_BROWN, rect)
        m = 5
        pygame.draw.line(surf, WHITE, (rect.left + m, rect.top + m), (rect.right - m, rect.bottom - m), 2)
        pygame.draw.line(surf, WHITE, (rect.left + m, rect.bottom - m), (rect.right - m, rect.top + m), 2)

    def _draw_slot(self, surf: pygame.Surface, box: pygame.Rect, bar: pygame.Rect,
                   slot: Dict[str, Any], slot_size: int, reservations: bool = False) -> None:
        good_name, qty = slot["good"], slot["qty"]
        reserved = slot.get("reserved")

        # Fill bar, filling from the bottom: green once the slot is full
        pygame.draw.rect(surf, WHEAT, bar)
        if good_name is not None and qty > 0:
            share = min(1.0, qty / slot_size) if slot_size else 1.0
            fill_h = max(2, round(bar.height * share))
            color = MUTED_GREEN if share >= 1.0 else MUTED_ORANGE
            pygame.draw.rect(surf, color, pygame.Rect(bar.x, bar.bottom - fill_h, bar.width, fill_h))
        pygame.draw.rect(surf, DARK_BROWN if good_name else LIGHT_GRAY, bar, 2 if good_name else 1)

        if good_name is None:
            pygame.draw.rect(surf, EMPTY_SLOT, box)
            pygame.draw.rect(surf, LIGHT_GRAY, box, 1)
            if reserved is None:
                empty = self.small_font.render("Empty", True, LIGHT_GRAY)
                surf.blit(empty, empty.get_rect(center=box.center))
            else:
                # An empty reserved slot shows what it is kept for, faintly
                icon = self._icon(reserved)
                if icon:
                    faint = icon.copy()
                    faint.set_alpha(80)
                    surf.blit(faint, faint.get_rect(center=(box.centerx, box.top + 8 + ICON_SIZE // 2)))
                label = self.small_font.render(f"for {reserved}", True, DARK_GRAY)
                surf.blit(label, label.get_rect(centerx=box.centerx, bottom=box.bottom - 14))
        else:
            pygame.draw.rect(surf, BEIGE, box)
            pygame.draw.rect(surf, DARK_BROWN, box, 2)
            icon = self._icon(good_name)
            if icon:
                surf.blit(icon, icon.get_rect(center=(box.centerx, box.top + 8 + ICON_SIZE // 2)))
            name = self.small_font.render(good_name, True, DARK_BROWN)
            surf.blit(name, name.get_rect(centerx=box.centerx, bottom=box.bottom - 24))
            amount = self.small_font.render(f"{qty} / {slot_size}", True, DARK_GRAY)
            surf.blit(amount, amount.get_rect(centerx=box.centerx, bottom=box.bottom - 6))

        if reservations:
            # The reservation button: a filled funnel when the slot is reserved
            button = pygame.Rect(box.x + 4, box.y + 4, FILTER_BUTTON, FILTER_BUTTON)
            if reserved is not None:
                pygame.draw.rect(surf, DARK_BROWN, button, border_radius=3)
                draw_funnel(surf, button, WHITE)
            else:
                draw_funnel(surf, button, LIGHT_GRAY if good_name is None else (190, 175, 150))

    def _draw_hand_slot(self, surf: pygame.Surface, box: pygame.Rect, slot: Dict[str, Any]) -> None:
        """A small slot of one unit: just the good's picture, its name is in the tooltip."""
        if slot["good"] is None:
            pygame.draw.rect(surf, EMPTY_SLOT, box)
            pygame.draw.rect(surf, LIGHT_GRAY, box, 1)
            return
        pygame.draw.rect(surf, BEIGE, box)
        pygame.draw.rect(surf, DARK_BROWN, box, 2)
        icon = self._icon(slot["good"], HAND_ICON_SIZE)
        if icon:
            surf.blit(icon, icon.get_rect(center=box.center))
