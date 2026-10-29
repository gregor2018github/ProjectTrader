"""Inventory of an owned warehouse, and what the player carries by hand.

Opened from the house menu of a warehouse the player owns: the building's
storage slots over the player's hands (see inventory_window). Clicking a
slot moves as much of its goods across as fits, a right-click one.
"""

import pygame
from typing import Any, Dict, List, Tuple, TYPE_CHECKING

from ...config.constants import PACK_SLOT_SIZE
from .inventory_window import FIRST_SECTION_Y, InventoryWindow, SlotSection

if TYPE_CHECKING:
    from ...game_state import GameState
    from ...models.institutions.warehouse import Warehouse


# The two sections of the window
WAREHOUSE, PACK = "warehouse", "pack"


def open_warehouse_inventory(game_state: 'GameState', warehouse: 'Warehouse') -> None:
    game_state.info_window = WarehouseInventory(game_state.screen, game_state, warehouse)
    game_state.active_house_menu = warehouse  # walking away closes it, as with the house menu


class WarehouseInventory(InventoryWindow):
    """A centred overlay showing one warehouse's slots and the player's hands."""

    def __init__(self, screen: pygame.Surface, game_state: 'GameState',
                 warehouse: 'Warehouse') -> None:
        super().__init__(screen, game_state)
        self.house = warehouse  # map_view closes the window once the player walks off

        entry = self.depot.warehouse_entry(warehouse.tmx_id) or {}
        slot_count = len(entry.get("slots", [])) or warehouse.buy_slots
        slot_size = entry.get("slot_size", warehouse.buy_slot_size)
        warehouse_section = SlotSection(WAREHOUSE, slot_count, slot_size, FIRST_SECTION_Y,
                                        "Slots in use", "Stored")
        pack_section = SlotSection(PACK, len(self.depot.pack_slots), PACK_SLOT_SIZE,
                                   warehouse_section.bottom + 34, "Carried by hand", "Carrying")
        self._place_panel([warehouse_section, pack_section])

    def _titles(self) -> Tuple[str, str]:
        name = self.house.display_name or (self.house.name or "Warehouse").split('_')[0]
        return name, "Warehouse Inventory"

    def _read_slots(self) -> Dict[str, List[Dict[str, Any]]]:
        return {
            WAREHOUSE: self.depot.warehouse_slots(self.house.tmx_id),
            PACK: [dict(slot) for slot in self.depot.pack_slots],
        }

    def _footer(self, slots: Dict[str, List[Dict[str, Any]]]) -> str:
        return f"Value in this warehouse:  {self._worth(slots[WAREHOUSE]):,.0f}g"

    def _slot_tooltip(self, section: SlotSection, slot: Dict[str, Any]) -> str:
        good_name, qty = slot["good"], slot["qty"]
        if good_name is None:
            if section.by_hand:
                return "Free hand  ·  carries one unit of a good"
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
    # Moving goods
    # ------------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> None:
        super().handle_event(event)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
            self._transfer(event.pos, one=True)

    def handle_click(self, pos: Tuple[int, int]) -> bool:
        if self.close_rect.collidepoint(pos) or not self.panel_rect.collidepoint(pos):
            return super().handle_click(pos)
        self._transfer(pos, one=False)
        return True

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
                moved = self.depot.carry_from_warehouse(self.house.tmx_id, index, wanted)
                where = "your hands"
            else:
                moved = self.depot.store_in_warehouse(self.house.tmx_id, index, wanted)
                where = "this warehouse"
            if moved == 0:
                self.game_state.show_warning(f"There is no room for {good_name} in {where}.")
            return
