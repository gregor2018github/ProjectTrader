"""The starting storage as the uncle's shop shows it: its slots, its filter and
reservations, and carrying goods out of it and back, all by the key START."""

from types import SimpleNamespace

from src.models.depot import START
from src.models.intro import DONE, FIND_SHOP, SHOP_HOUSE, is_found_shop
from tests.fakes import fake_warehouse
from tests.models.conftest import PACK_SLOTS, SLOT_SIZE, STARTING_STORAGE_SLOTS

SHED = 101


def contents(slots):
    return [(s["good"], s["qty"]) for s in slots]


def test_the_shop_is_the_players_storage_only_once_the_uncle_is_found():
    shop, other = SimpleNamespace(name=SHOP_HOUSE), SimpleNamespace(name="House_1")
    assert is_found_shop(shop, SimpleNamespace(stage=DONE))
    assert not is_found_shop(shop, SimpleNamespace(stage=FIND_SHOP))
    assert not is_found_shop(other, SimpleNamespace(stage=DONE))
    assert not is_found_shop(shop, None)


def test_the_starting_storage_shows_its_slots(depot, wood, game_state):
    assert depot.buy(wood, 3, game_state)
    slots = depot.warehouse_slots(START)
    assert len(slots) == STARTING_STORAGE_SLOTS
    assert contents(slots)[0] == ("Wood", 3)
    slots[0]["qty"] = 99  # a copy
    assert depot.starting_slots[0]["qty"] == 3


def test_goods_are_carried_out_of_the_starting_storage_and_back(depot, wood, game_state):
    assert depot.buy(wood, 3, game_state)
    assert depot.carry_from_warehouse(START, 0, 3) == 3
    assert sum(s["qty"] for s in depot.pack_slots if s["good"] == "Wood") == 3
    assert depot.starting_slots[0]["good"] is None
    pack_index = next(i for i, s in enumerate(depot.pack_slots) if s["good"] == "Wood")
    assert depot.store_in_warehouse(START, pack_index, 1) == 1
    assert contents(depot.starting_slots)[0] == ("Wood", 1)
    assert depot.good_stock["Wood"] == 3


def test_the_starting_storage_can_accept_only_some_goods(depot, wood, stone, game_state):
    assert depot.buy_warehouse(fake_warehouse(tmx_id=SHED, slots=2, slot_size=30), game_state)
    depot.set_accepted_goods(START, ["Stone"])
    assert depot.storage_accepts(START) == ["Stone"]
    assert depot.buy(wood, 5, game_state)
    assert all(s["good"] is None for s in depot.starting_slots)
    assert contents(depot.warehouse_slots(SHED))[0] == ("Wood", 5)
    assert depot.buy(stone, 5, game_state)
    assert contents(depot.starting_slots)[0] == ("Stone", 5)
    depot.set_accepted_goods(START, None)
    assert depot.storage_accepts(START) is None


def test_a_starting_slot_can_be_kept_for_one_good(depot, wood, stone, game_state):
    depot.set_slot_reservation(START, 0, "Stone")
    assert depot.buy(wood, SLOT_SIZE, game_state)
    assert contents(depot.starting_slots)[:2] == [(None, 0), ("Wood", SLOT_SIZE)]
    assert depot.warehouse_slots(START)[0]["reserved"] == "Stone"
    depot.set_slot_reservation(START, 0, None)
    assert "reserved" not in depot.starting_slots[0]


def test_the_pack_cannot_take_more_than_it_holds(depot, wood, game_state):
    assert depot.buy(wood, PACK_SLOTS + 5, game_state)
    assert depot.carry_from_warehouse(START, 0, SLOT_SIZE) == min(SLOT_SIZE, PACK_SLOTS)
