"""The storage settings: the priority list purchases follow, the goods a
warehouse accepts, and slots reserved for one good."""

from src.models.depot import START
from tests.fakes import fake_warehouse
from tests.models.conftest import SLOT_SIZE

SHED, BARN = 101, 102


def contents(slots):
    return [(s["good"], s["qty"]) for s in slots]


def own_two_warehouses(depot, game_state):
    """A shed of 2 slots of 30 bought before a barn of 2 slots of 30."""
    for tmx_id in (SHED, BARN):
        assert depot.buy_warehouse(fake_warehouse(tmx_id=tmx_id, slots=2, slot_size=30), game_state)


def fill_starting_storage(depot, stone, game_state):
    assert depot.buy(stone, 5 * SLOT_SIZE, game_state)


# THE PRIORITY LIST

def test_the_priority_list_starts_with_the_starting_storage_and_warehouses_as_bought(depot, game_state):
    own_two_warehouses(depot, game_state)
    assert depot.storage_priority() == [START, SHED, BARN]


def test_purchases_follow_the_priority_list(depot, wood, game_state):
    own_two_warehouses(depot, game_state)
    depot.move_in_priority(BARN, -2)
    assert depot.storage_priority() == [BARN, START, SHED]

    depot.buy(wood, 70, game_state)

    assert contents(depot.warehouse_slots(BARN)) == [("Wood", 30), ("Wood", 30)]
    assert contents(depot.starting_slots)[0] == ("Wood", 10)
    assert contents(depot.warehouse_slots(SHED)) == [(None, 0), (None, 0)]


def test_sales_take_from_the_end_of_the_priority_list(depot, wood, game_state):
    own_two_warehouses(depot, game_state)
    depot.move_in_priority(BARN, -2)
    depot.buy(wood, 70, game_state)

    depot.sell(wood, 10, game_state)

    assert contents(depot.starting_slots)[0] == (None, 0)
    assert contents(depot.warehouse_slots(BARN)) == [("Wood", 30), ("Wood", 30)]


def test_moving_past_either_end_stays_at_the_end(depot, game_state):
    own_two_warehouses(depot, game_state)
    depot.move_in_priority(START, -1)
    depot.move_in_priority(BARN, 5)
    assert depot.storage_priority() == [START, SHED, BARN]


def test_a_saved_list_missing_or_repeating_storages_is_mended(depot, game_state):
    own_two_warehouses(depot, game_state)
    depot.storage_order = [BARN, BARN, 999]
    assert depot.storage_priority() == [BARN, START, SHED]


# WAREHOUSE FILTERS

def test_a_warehouse_takes_only_the_goods_it_accepts(depot, wood, stone, make_good, game_state):
    own_two_warehouses(depot, game_state)
    fill_starting_storage(depot, stone, game_state)
    depot.set_accepted_goods(SHED, ["Iron"])

    depot.buy(wood, 20, game_state)
    depot.buy(make_good("Iron"), 20, game_state)

    assert contents(depot.warehouse_slots(SHED)) == [("Iron", 20), (None, 0)]
    assert contents(depot.warehouse_slots(BARN)) == [("Wood", 20), (None, 0)]


def test_a_filter_does_not_throw_out_what_is_already_stored(depot, wood, stone, game_state):
    own_two_warehouses(depot, game_state)
    fill_starting_storage(depot, stone, game_state)
    depot.buy(wood, 20, game_state)
    depot.set_accepted_goods(SHED, [])

    assert contents(depot.warehouse_slots(SHED)) == [("Wood", 20), (None, 0)]
    depot.buy(wood, 5, game_state)
    assert contents(depot.warehouse_slots(SHED)) == [("Wood", 20), (None, 0)]
    assert contents(depot.warehouse_slots(BARN)) == [("Wood", 5), (None, 0)]


def test_accepting_all_goods_again(depot, wood, stone, game_state):
    own_two_warehouses(depot, game_state)
    fill_starting_storage(depot, stone, game_state)
    depot.set_accepted_goods(SHED, [])
    depot.set_accepted_goods(SHED, None)

    depot.buy(wood, 20, game_state)
    assert contents(depot.warehouse_slots(SHED))[0] == ("Wood", 20)


# SLOT RESERVATIONS

def test_a_reserved_slot_takes_only_its_good(depot, wood, stone, make_good, game_state):
    own_two_warehouses(depot, game_state)
    fill_starting_storage(depot, stone, game_state)
    depot.set_slot_reservation(SHED, 0, "Iron")

    depot.buy(wood, 20, game_state)
    depot.buy(make_good("Iron"), 10, game_state)

    assert contents(depot.warehouse_slots(SHED)) == [("Iron", 10), ("Wood", 20)]
    assert depot.warehouse_slots(SHED)[0]["reserved"] == "Iron"


def test_a_reservation_lets_its_good_in_where_the_warehouse_filter_would_not(depot, stone, make_good, game_state):
    own_two_warehouses(depot, game_state)
    fill_starting_storage(depot, stone, game_state)
    depot.set_accepted_goods(SHED, [])
    depot.set_slot_reservation(SHED, 1, "Iron")

    depot.buy(make_good("Iron"), 10, game_state)
    assert contents(depot.warehouse_slots(SHED)) == [(None, 0), ("Iron", 10)]


def test_a_reservation_is_lifted_with_none(depot, game_state):
    own_two_warehouses(depot, game_state)
    depot.set_slot_reservation(SHED, 0, "Iron")
    depot.set_slot_reservation(SHED, 0, None)
    assert "reserved" not in depot.warehouse_slots(SHED)[0]


# REFUSALS

def test_room_for_leaves_out_what_filters_keep_for_other_goods(depot, stone, game_state):
    own_two_warehouses(depot, game_state)
    fill_starting_storage(depot, stone, game_state)
    depot.set_accepted_goods(SHED, ["Iron"])
    depot.set_slot_reservation(BARN, 0, "Iron")

    assert depot.room_for("Wood") == 30
    assert depot.room_for("Wood", filtered=False) == 4 * 30
    assert depot.room_in_warehouse(SHED, "Wood") == 0
    assert depot.room_in_warehouse(SHED, "Wood", filtered=False) == 60


def test_a_purchase_only_the_filters_stop_is_refused_saying_so(depot, wood, stone, game_state):
    own_two_warehouses(depot, game_state)
    fill_starting_storage(depot, stone, game_state)
    depot.set_accepted_goods(SHED, [])
    depot.set_accepted_goods(BARN, [])
    money = depot.money

    assert not depot.buy(wood, 10, game_state)

    assert depot.money == money
    assert depot.good_stock["Wood"] == 0
    assert "reserved for other goods" in game_state.warnings[-1]


def test_storing_from_the_hands_follows_the_filters(depot, wood, stone, game_state):
    own_two_warehouses(depot, game_state)
    fill_starting_storage(depot, stone, game_state)
    depot.buy(wood, 1, game_state)
    assert depot.carry_from_warehouse(SHED, 0, 1) == 1
    depot.set_accepted_goods(SHED, [])

    assert depot.store_in_warehouse(SHED, 0, 1) == 0
    assert depot.pack_total() == 1


# LOADING

def test_settle_mends_the_priority_list_of_an_older_save(depot, game_state):
    own_two_warehouses(depot, game_state)
    depot.storage_order = []
    depot.settle_storage({})
    assert depot.storage_order == [START, SHED, BARN]
