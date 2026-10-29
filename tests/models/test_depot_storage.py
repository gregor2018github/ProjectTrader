"""The depot's storage slots: where bought goods go, where sold goods come from,
warehouses, the player's pack, and repacking after a load (settle_storage)."""

from tests.fakes import fake_warehouse
from tests.models.conftest import PACK_SLOTS, PACK_SLOT_SIZE, SLOT_SIZE, STARTING_STORAGE_SLOTS

WAREHOUSE_ID = 101


def contents(slots):
    return [(s["good"], s["qty"]) for s in slots]


def held(depot):
    """Units of each good lying in any slot, pack included."""
    totals = {}
    for slots, _ in depot._storages() + [(depot.pack_slots, PACK_SLOT_SIZE)]:
        for slot in slots:
            if slot["good"] is not None:
                totals[slot["good"]] = totals.get(slot["good"], 0) + slot["qty"]
    return totals


def stocked(depot):
    return {g: q for g, q in depot.good_stock.items() if q > 0}


def own_warehouse(depot, game_state, **kwargs):
    warehouse = fake_warehouse(tmx_id=WAREHOUSE_ID, **kwargs)
    assert depot.buy_warehouse(warehouse, game_state)
    return warehouse


# FILLING AND EMPTYING SLOTS

def test_a_fresh_depot_has_empty_starting_slots_and_pack(depot):
    assert contents(depot.starting_slots) == [(None, 0)] * STARTING_STORAGE_SLOTS
    assert contents(depot.pack_slots) == [(None, 0)] * PACK_SLOTS
    assert depot.total_capacity() == SLOT_SIZE * STARTING_STORAGE_SLOTS + PACK_SLOTS * PACK_SLOT_SIZE


def test_purchase_fills_slots_in_order(depot, wood, game_state):
    depot.buy(wood, 45, game_state)
    assert contents(depot.starting_slots) == [("Wood", 20), ("Wood", 20), ("Wood", 5), (None, 0), (None, 0)]


def test_purchase_tops_up_its_own_slot_before_taking_an_empty_one(depot, wood, stone, game_state):
    depot.buy(wood, 5, game_state)
    depot.buy(stone, 10, game_state)
    depot.buy(wood, 10, game_state)

    assert contents(depot.starting_slots) == [("Wood", 15), ("Stone", 10), (None, 0), (None, 0), (None, 0)]
    assert depot.room_for("Wood") == 5 + 3 * SLOT_SIZE
    assert depot.room_for("Stone") == 10 + 3 * SLOT_SIZE
    assert depot.room_for("Iron") == 3 * SLOT_SIZE


def test_sale_empties_the_least_filled_slot_first(depot, wood, game_state):
    depot.buy(wood, 45, game_state)
    depot.sell(wood, 3, game_state)
    assert contents(depot.starting_slots)[:3] == [("Wood", 20), ("Wood", 20), ("Wood", 2)]


def test_emptied_slot_is_free_for_another_good(depot, wood, stone, game_state):
    depot.buy(wood, 100, game_state)
    depot.sell(wood, 20, game_state)
    assert depot.buy(stone, 20, game_state)
    assert held(depot) == {"Wood": 80, "Stone": 20}


# WAREHOUSES

def test_buying_a_warehouse_adds_its_slots(depot, game_state):
    warehouse = own_warehouse(depot, game_state, buy_price=500, slots=3, slot_size=30)

    assert warehouse.is_owned
    assert depot.money == 10_000 - 500
    assert depot.property_expenditures == 500
    assert depot.storage_capacity == SLOT_SIZE * STARTING_STORAGE_SLOTS + 90
    assert depot.warehouse_count == 2
    assert contents(depot.warehouse_slots(WAREHOUSE_ID)) == [(None, 0)] * 3
    assert depot.get_property_value() == 500
    assert depot.stats.properties_bought == 1
    assert game_state.events[-1][0] == "PROPERTY"


def test_warehouse_refused_without_the_money(depot, game_state):
    depot.money = 499
    warehouse = fake_warehouse(buy_price=500)

    assert not depot.buy_warehouse(warehouse, game_state)

    assert not warehouse.is_owned
    assert depot.money == 499
    assert depot.properties["warehouses"] == []


def test_warehouse_slots_returns_copies(depot, game_state):
    own_warehouse(depot, game_state)
    depot.warehouse_slots(WAREHOUSE_ID)[0]["qty"] = 99
    assert depot.warehouse_slots(WAREHOUSE_ID)[0]["qty"] == 0
    assert depot.warehouse_slots(999) == []


def test_purchases_fill_the_starting_storage_before_warehouses(depot, wood, game_state):
    own_warehouse(depot, game_state, slots=3, slot_size=30)
    depot.buy(wood, 110, game_state)

    assert contents(depot.starting_slots) == [("Wood", 20)] * 5
    assert contents(depot.warehouse_slots(WAREHOUSE_ID)) == [("Wood", 10), (None, 0), (None, 0)]


def test_sales_empty_the_newest_warehouse_first(depot, wood, game_state):
    own_warehouse(depot, game_state, slots=3, slot_size=30)
    depot.buy(wood, 110, game_state)
    depot.sell(wood, 15, game_state)

    assert contents(depot.warehouse_slots(WAREHOUSE_ID)) == [(None, 0)] * 3
    assert sorted(s["qty"] for s in depot.starting_slots) == [15, 20, 20, 20, 20]


# THE PACK

def stock_warehouse_with_wood(depot, wood, stone, game_state, quantity=30):
    """A warehouse holding Wood in its first slot (the starting storage being full of Stone)."""
    own_warehouse(depot, game_state, slots=3, slot_size=30)
    depot.buy(stone, 100, game_state)
    depot.buy(wood, quantity, game_state)
    assert depot.warehouse_slots(WAREHOUSE_ID)[0] == {"good": "Wood", "qty": quantity}


def test_carrying_moves_goods_into_the_pack_without_changing_stock(depot, wood, stone, game_state):
    stock_warehouse_with_wood(depot, wood, stone, game_state)

    assert depot.carry_from_warehouse(WAREHOUSE_ID, 0, 4) == 4

    assert depot.pack_total() == 4
    assert depot.warehouse_slots(WAREHOUSE_ID)[0]["qty"] == 26
    assert depot.good_stock["Wood"] == 30
    assert held(depot) == stocked(depot)


def test_the_pack_takes_no_more_than_it_has_room_for(depot, wood, stone, game_state):
    stock_warehouse_with_wood(depot, wood, stone, game_state)

    assert depot.carry_from_warehouse(WAREHOUSE_ID, 0, 25) == PACK_SLOTS * PACK_SLOT_SIZE
    assert depot.carry_from_warehouse(WAREHOUSE_ID, 0, 1) == 0
    assert held(depot) == stocked(depot)


def test_storing_puts_pack_goods_back(depot, wood, stone, game_state):
    stock_warehouse_with_wood(depot, wood, stone, game_state)
    depot.carry_from_warehouse(WAREHOUSE_ID, 0, 3)
    pack_index = next(i for i, s in enumerate(depot.pack_slots) if s["good"] == "Wood")

    assert depot.store_in_warehouse(WAREHOUSE_ID, pack_index, 1) == 1

    assert depot.pack_total() == 2
    assert depot.warehouse_slots(WAREHOUSE_ID)[0]["qty"] == 28
    assert held(depot) == stocked(depot)


def test_moves_with_nothing_to_move_do_nothing(depot, wood, stone, game_state):
    stock_warehouse_with_wood(depot, wood, stone, game_state)

    assert depot.carry_from_warehouse(999, 0, 1) == 0          # not an owned warehouse
    assert depot.carry_from_warehouse(WAREHOUSE_ID, 7, 1) == 0  # no such slot
    assert depot.carry_from_warehouse(WAREHOUSE_ID, 1, 1) == 0  # empty slot
    assert depot.carry_from_warehouse(WAREHOUSE_ID, 0, 0) == 0
    assert depot.store_in_warehouse(WAREHOUSE_ID, 0, 1) == 0    # empty pack
    assert depot.pack_total() == 0


def test_purchases_never_go_into_the_pack(depot, wood, stone, game_state):
    stock_warehouse_with_wood(depot, wood, stone, game_state)
    depot.carry_from_warehouse(WAREHOUSE_ID, 0, 2)

    depot.buy(wood, 5, game_state)

    assert depot.pack_total() == 2
    assert contents(depot.warehouse_slots(WAREHOUSE_ID)) == [("Wood", 30), ("Wood", 3), (None, 0)]


def test_sales_take_from_the_pack_last(depot, wood, stone, game_state):
    stock_warehouse_with_wood(depot, wood, stone, game_state)
    depot.carry_from_warehouse(WAREHOUSE_ID, 0, 4)    # 26 left in the warehouse

    depot.sell(wood, 26, game_state)
    assert depot.pack_total() == 4

    depot.sell(wood, 1, game_state)
    assert depot.pack_total() == 3
    assert held(depot) == stocked(depot)


# SETTLING AFTER A LOAD

def test_settle_leaves_slots_that_agree_alone(depot, wood, stone, game_state):
    depot.buy(wood, 5, game_state)
    depot.buy(stone, 30, game_state)
    depot.buy(wood, 10, game_state)
    before = contents(depot.starting_slots)

    depot.settle_storage({})

    assert contents(depot.starting_slots) == before


def test_settle_packs_a_save_without_slots_largest_stock_first(depot):
    depot.good_stock.update({"Wood": 30, "Stone": 50})

    depot.settle_storage({})

    assert contents(depot.starting_slots) == [
        ("Stone", 20), ("Stone", 20), ("Stone", 10), ("Wood", 20), ("Wood", 10),
    ]


def test_settle_puts_overflow_in_extra_slots_which_go_once_emptied(depot, wood, game_state):
    depot.good_stock["Wood"] = 130

    depot.settle_storage({})

    assert len(depot.starting_slots) == STARTING_STORAGE_SLOTS + 2
    assert held(depot) == {"Wood": 130}

    depot.sell(wood, 30, game_state)    # the 10 in the last extra slot, then one full slot
    assert len(depot.starting_slots) == STARTING_STORAGE_SLOTS + 1
    assert held(depot) == {"Wood": 100}


def test_settle_gives_an_old_warehouse_its_slots(depot):
    depot.properties["warehouses"] += [
        {"tmx_id": 7, "buy_price": 300, "buy_storage": 60, "stock": {"Wood": 5}},
        {"tmx_id": 8, "buy_price": 300, "buy_storage": 60},
    ]

    depot.settle_storage({7: (2, 30)})

    old_with_layout, old_without = depot.properties["warehouses"]
    assert contents(old_with_layout["slots"]) == [(None, 0)] * 2
    assert old_with_layout["slot_size"] == 30
    assert "stock" not in old_with_layout
    # Not on the map any more: its storage in starting-size slots
    assert len(old_without["slots"]) == 60 // SLOT_SIZE
    assert old_without["slot_size"] == SLOT_SIZE


def test_settle_trims_a_pack_carrying_more_than_the_stock(depot):
    depot.good_stock["Wood"] = 2
    for slot in depot.pack_slots[:3]:
        slot.update(good="Wood", qty=1)

    depot.settle_storage({})

    assert depot.pack_total() == 2
    assert held(depot) == {"Wood": 2}
