"""Goods given to the player (Depot.receive_goods): into the pack first, where a
purchase would go when the pack is full, all of them or none, and booked as bought
for nothing."""

from tests.models.conftest import PACK_SLOTS, SLOT_SIZE, STARTING_STORAGE_SLOTS


def contents(slots):
    return [(s["good"], s["qty"]) for s in slots]


def pack_held(depot, good):
    return sum(s["qty"] for s in depot.pack_slots if s["good"] == good)


def test_a_gift_goes_into_the_pack_and_costs_nothing(depot, game_state):
    money = depot.money
    assert depot.receive_goods("Wood", 3, game_state.date)
    assert pack_held(depot, "Wood") == 3
    assert all(s["good"] is None for s in depot.starting_slots)
    assert depot.good_stock["Wood"] == 3 and depot.money == money
    assert depot.purchase_history["Wood"][-1]["price"] == 0.0
    assert depot.stats.goods_bought == 0


def test_what_the_pack_cannot_hold_goes_where_a_purchase_would(depot, game_state):
    assert depot.receive_goods("Wood", PACK_SLOTS + 2, game_state.date)
    assert pack_held(depot, "Wood") == PACK_SLOTS
    assert contents(depot.starting_slots)[0] == ("Wood", 2)
    assert depot.good_stock["Wood"] == PACK_SLOTS + 2


def test_with_the_storage_full_the_pack_still_takes_it(depot, stone, game_state):
    assert depot.buy(stone, SLOT_SIZE * STARTING_STORAGE_SLOTS, game_state)
    assert depot.room_to_receive("Wood") == PACK_SLOTS
    assert depot.receive_goods("Wood", 3, game_state.date)
    assert pack_held(depot, "Wood") == 3
    assert depot.good_stock["Wood"] == 3


def test_without_room_for_all_of_it_nothing_is_taken(depot, stone, game_state):
    assert depot.buy(stone, SLOT_SIZE * STARTING_STORAGE_SLOTS, game_state)
    assert not depot.receive_goods("Wood", PACK_SLOTS + 1, game_state.date)
    assert depot.good_stock["Wood"] == 0 and depot.pack_total() == 0


def test_selling_a_gift_is_all_profit(depot, wood, game_state):
    depot.receive_goods("Wood", 3, game_state.date)
    assert depot.sell(wood, 3, game_state)
    assert depot.good_stock["Wood"] == 0 and depot.purchase_history["Wood"] == []
