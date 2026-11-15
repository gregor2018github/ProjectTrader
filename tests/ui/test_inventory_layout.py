"""The warehouse window's slots: at most MAX_SLOT_ROWS rows, more columns and a wider window instead."""
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame  # noqa: E402
import pytest  # noqa: E402

from src.config.constants import PACK_SLOTS, SCREEN_HEIGHT, SCREEN_WIDTH, SIDEBAR_WIDTH  # noqa: E402
from src.ui.helper_modules.inventory_window import COLS, PANEL_W, SlotSection  # noqa: E402
from src.ui.helper_modules.warehouse_inventory import MAX_SLOT_ROWS, SETTINGS_RULE_Y  # noqa: E402


def sections(slots):
    warehouse = SlotSection("warehouse", slots, 50, SETTINGS_RULE_Y + 14, "Slots in use", "Stored",
                            reservations=True, max_rows=MAX_SLOT_ROWS)
    pack = SlotSection("pack", PACK_SLOTS, 1, warehouse.bottom + 34, "Carried by hand", "Carrying")
    return warehouse, pack


@pytest.mark.parametrize("slots", [3, 10, 20])
def test_up_to_twenty_slots_keep_five_columns_and_the_old_width(slots):
    warehouse, pack = sections(slots)
    assert warehouse.cols == COLS
    assert max(PANEL_W, warehouse.width, pack.width) == PANEL_W


@pytest.mark.parametrize("slots", [24, 30, 32, 40])
def test_more_slots_take_more_columns_not_more_rows(slots):
    warehouse, _ = sections(slots)
    rows = -(-slots // warehouse.cols)
    assert rows <= MAX_SLOT_ROWS
    assert warehouse.cols > COLS


@pytest.mark.parametrize("slots", [20, 32, 40])
def test_the_window_fits_the_screen(slots):
    warehouse, pack = sections(slots)
    height = pack.bottom + 18 + 12 + 44   # as InventoryWindow._place_panel adds the footer
    width = max(PANEL_W, warehouse.width, pack.width)
    assert height <= SCREEN_HEIGHT
    assert width <= SCREEN_WIDTH + SIDEBAR_WIDTH


def test_slots_are_placed_inside_the_widened_panel():
    pygame.init()
    warehouse, _ = sections(32)
    width = max(PANEL_W, warehouse.width)
    panel = pygame.Rect(0, 0, width, 1000)
    warehouse.place(panel)
    for box, bar in warehouse.slot_rects:
        assert panel.contains(box) and panel.contains(bar)
    assert len({box.y for box, _ in warehouse.slot_rects}) == MAX_SLOT_ROWS
