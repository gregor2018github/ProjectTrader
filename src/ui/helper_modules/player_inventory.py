"""The player's own inventory: what they carry by hand.

Opened with I, or from the menu of a click on the player's figure. Goods
are only put into the hands and taken out of them at a warehouse the
player owns (warehouse_inventory), so this window just shows them.
"""

import pygame
from typing import Any, Dict, List, Tuple, TYPE_CHECKING

from ...config.constants import PACK_SLOT_SIZE
from .inventory_window import FIRST_SECTION_Y, InventoryWindow, SlotSection

if TYPE_CHECKING:
    from ...game_state import GameState


PACK = "pack"


def open_player_inventory(game_state: 'GameState') -> None:
    game_state.info_window = PlayerInventory(game_state.screen, game_state)
    game_state.active_house_menu = None


class PlayerInventory(InventoryWindow):
    """A centred overlay showing the goods the player carries."""

    def __init__(self, screen: pygame.Surface, game_state: 'GameState') -> None:
        super().__init__(screen, game_state)
        self._shown = False
        self._place_panel([
            SlotSection(PACK, len(self.depot.pack_slots), PACK_SLOT_SIZE, FIRST_SECTION_Y,
                        "Carried by hand", "Carrying"),
        ])

    def _titles(self) -> Tuple[str, str]:
        player = getattr(self.game_state.game, "player", None)
        return "Inventory", getattr(player, "name", "") or "What you carry"

    def _read_slots(self) -> Dict[str, List[Dict[str, Any]]]:
        return {PACK: [dict(slot) for slot in self.depot.pack_slots]}

    def _footer(self, slots: Dict[str, List[Dict[str, Any]]]) -> str:
        return f"Value carried:  {self._worth(slots[PACK]):,.0f}g"

    def _slot_tooltip(self, section: SlotSection, slot: Dict[str, Any]) -> str:
        if slot["good"] is None:
            return "Free hand  ·  fill it at a warehouse you own"
        return f"{slot['good']}  ·  worth {self._price(slot['good']) * slot['qty']:,.0f}g"

    def handle_event(self, event: pygame.event.Event) -> None:
        # I closes it again, as it opened it; the press that opened it is
        # handed on to it too, before it was ever drawn, and is not meant for it
        if event.type == pygame.KEYDOWN and event.key == pygame.K_i:
            if self._shown:
                self._close()
        else:
            super().handle_event(event)

    def draw(self, alpha_scale: float = 1.0) -> None:
        self._shown = True
        super().draw(alpha_scale)
