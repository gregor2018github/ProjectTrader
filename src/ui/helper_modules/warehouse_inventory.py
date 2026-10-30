"""Inventory of an owned warehouse, and what the player carries by hand.

Opened from the house menu of a warehouse the player owns: the building's
storage slots over the player's hands (see inventory_window). Clicking a
slot moves as much of its goods across as fits, a right-click one.

Over the slots are the warehouse's settings: its place in the priority list
purchases follow (moved earlier or later), and the goods it accepts (picked
in a GoodsPicker). The funnel in a slot's corner reserves it for one good.
"""

import pygame
from typing import Any, Dict, List, Optional, Set, Tuple, TYPE_CHECKING

from ...config.colors import BEIGE, DARK_BROWN, DARK_GRAY, LIGHT_GRAY, SANDY_BROWN
from ...config.constants import PACK_SLOT_SIZE
from ...models.depot import START
from ..ui_utils import draw_mouse_tooltip
from .goods_picker import GoodsPicker
from .inventory_window import FIRST_SECTION_Y, SIDE_PAD, InventoryWindow, SlotSection, draw_funnel

if TYPE_CHECKING:
    from ...game_state import GameState
    from ...models.institutions.warehouse import Warehouse


# The two sections of the window
WAREHOUSE, PACK = "warehouse", "pack"

# The settings strip, over the warehouse's slots (panel coordinates)
PRIORITY_Y = FIRST_SECTION_Y
ACCEPTS_Y = PRIORITY_Y + 36
SETTINGS_RULE_Y = ACCEPTS_Y + 40
SETTINGS_BUTTON_H = 28
ARROW_BUTTON_W = 34
CHOOSE_BUTTON_W = 150
STARTING_STORAGE_NAME = "Starting storage"


def open_warehouse_inventory(game_state: 'GameState', warehouse: 'Warehouse') -> None:
    game_state.info_window = WarehouseInventory(game_state.screen, game_state, warehouse)
    game_state.active_house_menu = warehouse  # walking away closes it, as with the house menu


class WarehouseInventory(InventoryWindow):
    """A centred overlay showing one warehouse's settings and slots, and the player's hands."""

    def __init__(self, screen: pygame.Surface, game_state: 'GameState',
                 warehouse: 'Warehouse') -> None:
        super().__init__(screen, game_state)
        self.house = warehouse  # map_view closes the window once the player walks off
        self.goods = list(self.depot.good_stock)
        self.picker: Optional[GoodsPicker] = None

        # Names of the storages in the priority list
        from ...models.institutions.warehouse import Warehouse as WarehouseHouse
        self.storage_names: Dict[Any, str] = {START: STARTING_STORAGE_NAME}
        for house in game_state.game.game_map.tmx_map.houses:
            if isinstance(house, WarehouseHouse):
                self.storage_names[house.tmx_id] = house.display_name or (house.name or "Warehouse").split('_')[0]

        entry = self.depot.warehouse_entry(warehouse.tmx_id) or {}
        slot_count = len(entry.get("slots", [])) or warehouse.buy_slots
        slot_size = entry.get("slot_size", warehouse.buy_slot_size)
        warehouse_section = SlotSection(WAREHOUSE, slot_count, slot_size, SETTINGS_RULE_Y + 14,
                                        "Slots in use", "Stored", reservations=True)
        pack_section = SlotSection(PACK, len(self.depot.pack_slots), PACK_SLOT_SIZE,
                                   warehouse_section.bottom + 34, "Carried by hand", "Carrying")
        self._place_panel([warehouse_section, pack_section])

        # The settings' buttons, in screen space
        right = self.panel_rect.right - SIDE_PAD
        self.later_button = pygame.Rect(right - ARROW_BUTTON_W, self.panel_rect.y + PRIORITY_Y - 4,
                                        ARROW_BUTTON_W, SETTINGS_BUTTON_H)
        self.earlier_button = self.later_button.move(-ARROW_BUTTON_W - 6, 0)
        self.choose_button = pygame.Rect(right - CHOOSE_BUTTON_W, self.panel_rect.y + ACCEPTS_Y - 4,
                                         CHOOSE_BUTTON_W, SETTINGS_BUTTON_H)

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    def _accepts(self) -> Optional[List[str]]:
        entry = self.depot.warehouse_entry(self.house.tmx_id) or {}
        return entry.get("accepts")

    def _titles(self) -> Tuple[str, str]:
        return self.storage_names.get(self.house.tmx_id, "Warehouse"), "Warehouse Inventory"

    def _read_slots(self) -> Dict[str, List[Dict[str, Any]]]:
        return {
            WAREHOUSE: self.depot.warehouse_slots(self.house.tmx_id),
            PACK: [dict(slot) for slot in self.depot.pack_slots],
        }

    def _footer(self, slots: Dict[str, List[Dict[str, Any]]]) -> str:
        return f"Value in this warehouse:  {self._worth(slots[WAREHOUSE]):,.0f}g"

    def _extra_key(self) -> tuple:
        accepts = self._accepts()
        return tuple(self.depot.storage_priority()), None if accepts is None else tuple(accepts)

    def _slot_tooltip(self, section: SlotSection, slot: Dict[str, Any]) -> str:
        good_name, qty = slot["good"], slot["qty"]
        reserved = slot.get("reserved")
        if good_name is None:
            if section.by_hand:
                return "Free hand  ·  carries one unit of a good"
            if reserved is not None:
                return f"Empty slot kept for {reserved}  ·  holds up to {section.slot_size}"
            return f"Empty slot  ·  holds up to {section.slot_size} of one good"
        worth = f"worth {self._price(good_name) * qty:,.0f}g"
        if section.by_hand:
            return f"{good_name}  ·  {worth}  ·  click: store"
        if section.kind == WAREHOUSE:
            action = "click: carry what you can, right-click: carry one"
        else:
            action = "click: store, right-click: store one"
        return f"{qty} of {section.slot_size} {good_name}  ·  {worth}  ·  {action}"

    # ------------------------------------------------------------------
    # The settings strip
    # ------------------------------------------------------------------

    def _draw_extra(self, surf: pygame.Surface) -> None:
        w = self.panel_rect.width
        off = (-self.panel_rect.x, -self.panel_rect.y)
        order = self.depot.storage_priority()
        place = order.index(self.house.tmx_id) if self.house.tmx_id in order else -1

        # Priority: the whole list, this warehouse picked out, and the buttons moving it
        label = self.body_font.render("Priority:", True, DARK_BROWN)
        surf.blit(label, (SIDE_PAD, PRIORITY_Y))
        x = SIDE_PAD + label.get_width() + 14
        limit = self.earlier_button.move(*off).left - 12
        for i, key in enumerate(order):
            if i:
                arrow = self.small_font.render(" › ", True, DARK_GRAY)
                surf.blit(arrow, (x, PRIORITY_Y + 2))
                x += arrow.get_width()
            name = f"{i + 1}. {self.storage_names.get(key, 'Warehouse')}"
            text = (self.body_font if i == place else self.small_font).render(
                name, True, DARK_BROWN if i == place else DARK_GRAY)
            if x + text.get_width() > limit:
                more = self.small_font.render("…", True, DARK_GRAY)
                surf.blit(more, (x, PRIORITY_Y + 2))
                break
            surf.blit(text, (x, PRIORITY_Y + (0 if i == place else 2)))
            if i == place:
                pygame.draw.line(surf, DARK_BROWN, (x, PRIORITY_Y + text.get_height()),
                                 (x + text.get_width(), PRIORITY_Y + text.get_height()), 1)
            x += text.get_width()
        self._draw_arrow_button(surf, self.earlier_button.move(*off), left=True, enabled=place > 0)
        self._draw_arrow_button(surf, self.later_button.move(*off), left=False,
                                enabled=0 <= place < len(order) - 1)

        # Accepts: which goods may be put here
        accepts = self._accepts()
        label = self.body_font.render("Accepts:", True, DARK_BROWN)
        surf.blit(label, (SIDE_PAD, ACCEPTS_Y))
        if accepts is None:
            summary = "All goods"
        elif not accepts:
            summary = "No goods (reserved slots only)"
        else:
            summary = ", ".join(accepts)
        text = self.body_font.render(summary, True, DARK_GRAY)
        room = self.choose_button.move(*off).left - 12 - (SIDE_PAD + label.get_width() + 14)
        if text.get_width() > room:
            text = self.body_font.render(f"{len(accepts)} goods: {', '.join(accepts)}", True, DARK_GRAY)
            text = text.subsurface((0, 0, max(1, room - 14), text.get_height())).copy()
            surf.blit(self.body_font.render("…", True, DARK_GRAY),
                      (SIDE_PAD + label.get_width() + 14 + text.get_width(), ACCEPTS_Y))
        surf.blit(text, (SIDE_PAD + label.get_width() + 14, ACCEPTS_Y))
        button = self.choose_button.move(*off)
        pygame.draw.rect(surf, SANDY_BROWN, button)
        pygame.draw.rect(surf, DARK_BROWN, button, 2)
        draw_funnel(surf, pygame.Rect(button.x + 8, button.y + 4, 20, 20), DARK_BROWN)
        caption = self.small_font.render("Choose goods", True, DARK_BROWN)
        surf.blit(caption, caption.get_rect(midleft=(button.x + 32, button.centery)))

        pygame.draw.line(surf, DARK_BROWN, (30, SETTINGS_RULE_Y), (w - 30, SETTINGS_RULE_Y), 1)

    @staticmethod
    def _draw_arrow_button(surf: pygame.Surface, rect: pygame.Rect, left: bool, enabled: bool) -> None:
        pygame.draw.rect(surf, SANDY_BROWN if enabled else BEIGE, rect)
        pygame.draw.rect(surf, DARK_BROWN if enabled else LIGHT_GRAY, rect, 2)
        cx, cy, d = rect.centerx, rect.centery, 6
        points = [(cx + d // 2, cy - d), (cx + d // 2, cy + d), (cx - d, cy)] if left else \
            [(cx - d // 2, cy - d), (cx - d // 2, cy + d), (cx + d, cy)]
        pygame.draw.polygon(surf, DARK_BROWN if enabled else LIGHT_GRAY, points)

    def _draw_overlay(self, mouse_pos: Tuple[int, int]) -> bool:
        if self.picker is not None:
            self.picker.draw(self.screen, mouse_pos)
            return True
        tips = (
            (self.earlier_button, "Purchases come here sooner, before the storage above it"),
            (self.later_button, "Purchases come here later, after the storage below it"),
            (self.choose_button, "Choose which goods purchases may put here"),
        )
        for rect, tip in tips:
            if rect.collidepoint(mouse_pos):
                shade = pygame.Surface(rect.size, pygame.SRCALPHA)
                shade.fill((0, 0, 0, 30))
                self.screen.blit(shade, rect.topleft)
                draw_mouse_tooltip(self.screen, self.body_font, tip, mouse_pos)
                return True
        section = self.sections[WAREHOUSE]
        index = section.filter_button_at(mouse_pos)
        if index is not None:
            reserved = self._slots[WAREHOUSE][index].get("reserved")  # read by draw() just before
            tip = f"Kept for {reserved}: click to change" if reserved else "Keep this slot for one good"
            draw_mouse_tooltip(self.screen, self.body_font, tip, mouse_pos)
            return True
        return False

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> None:
        if self.picker is not None:
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.picker = None
            return
        super().handle_event(event)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
            self._transfer(event.pos, one=True)

    def handle_click(self, pos: Tuple[int, int]) -> bool:
        if self.picker is not None:
            self.picker.handle_click(pos)
            if self.picker.closed:
                self.picker = None
            return True
        if self.close_rect.collidepoint(pos) or not self.panel_rect.collidepoint(pos):
            return super().handle_click(pos)
        if self.earlier_button.collidepoint(pos):
            self.depot.move_in_priority(self.house.tmx_id, -1)
        elif self.later_button.collidepoint(pos):
            self.depot.move_in_priority(self.house.tmx_id, 1)
        elif self.choose_button.collidepoint(pos):
            self._open_accepts_picker()
        elif (index := self.sections[WAREHOUSE].filter_button_at(pos)) is not None:
            self._open_reservation_picker(index)
        else:
            self._transfer(pos, one=False)
        return True

    def _open_accepts_picker(self) -> None:
        accepts = self._accepts()
        chosen: Set[str] = set(self.goods) if accepts is None else set(accepts)

        def changed(goods: Optional[Set[str]]) -> None:
            self.depot.set_accepted_goods(self.house.tmx_id, goods)

        self.picker = GoodsPicker(self, "Goods this warehouse accepts", self.goods, self.choose_button,
                                  chosen=chosen, on_change=changed)

    def _open_reservation_picker(self, index: int) -> None:
        slot = self.depot.warehouse_slots(self.house.tmx_id)[index]

        def picked(good: Optional[str]) -> None:
            self.depot.set_slot_reservation(self.house.tmx_id, index, good)

        anchor = self.sections[WAREHOUSE].slot_rects[index][0]
        self.picker = GoodsPicker(self, "Keep this slot for", self.goods, anchor,
                                  current=slot.get("reserved"), on_pick=picked)

    def _transfer(self, pos: Tuple[int, int], one: bool) -> None:
        """Move a clicked slot's goods to the other section: as many as fit, or one."""
        for kind, section in self.sections.items():
            index = section.slot_at(pos)
            if index is None:
                continue
            slot = (self.depot.warehouse_slots(self.house.tmx_id) if kind == WAREHOUSE
                    else self.depot.pack_slots)[index]
            if slot["good"] is None:
                return
            good_name, wanted = slot["good"], 1 if one else slot["qty"]
            if kind == WAREHOUSE:
                if self.depot.carry_from_warehouse(self.house.tmx_id, index, wanted) == 0:
                    self.game_state.show_warning(f"Your hands are full: there is no room for {good_name}.")
            elif self.depot.store_in_warehouse(self.house.tmx_id, index, wanted) == 0:
                if self.depot.room_in_warehouse(self.house.tmx_id, good_name, filtered=False) > 0:
                    self.game_state.show_warning(
                        f"No room for {good_name} here: this warehouse's free slots are reserved for other goods.")
                else:
                    self.game_state.show_warning(f"There is no room for {good_name} in this warehouse.")
            return
