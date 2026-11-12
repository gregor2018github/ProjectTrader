"""The trade desk's numbers (src/models/trade_offer.py): what an order comes to, its limits, why it is refused."""

from types import SimpleNamespace

import pytest

from src.models.trade_offer import MAX_QUANTITY, buy_offer, fifo_cost, market_block, max_buy, price_after, sell_offer


# WHAT AN ORDER COMES TO

def test_buy_offer_is_what_the_purchase_costs(depot, wood, game_state):
    offer = buy_offer(wood, 10, depot, game_state)

    assert offer.blocked is None
    assert offer.total == pytest.approx(102)        # 10 at 10g, and the fee of 2 %
    assert offer.fee == pytest.approx(2)
    assert offer.each == pytest.approx(10.2)
    money = depot.money
    assert depot.buy(wood, 10, game_state)
    assert money - depot.money == pytest.approx(offer.total)


def test_sell_offer_is_what_the_sale_brings_and_earns(depot, wood, game_state):
    depot.buy(wood, 10, game_state)
    wood.price = 12.0

    offer = sell_offer(wood, 10, depot, game_state)

    assert offer.blocked is None
    assert offer.total == pytest.approx(120 * 0.98)
    assert offer.profit == pytest.approx(120 * 0.98 - 100)
    assert offer.limit == 10
    money = depot.money
    assert depot.sell(wood, 10, game_state)
    assert depot.money - money == pytest.approx(offer.total)


def test_a_sale_below_what_the_goods_cost_is_a_loss(depot, wood, game_state):
    depot.buy(wood, 10, game_state)
    assert sell_offer(wood, 10, depot, game_state).profit == pytest.approx(-2)     # only the fee


def test_fifo_cost_takes_the_oldest_purchases_first(depot, wood, game_state):
    depot.buy(wood, 5, game_state)
    wood.price = 20.0
    depot.buy(wood, 5, game_state)

    assert fifo_cost(depot, "Wood", 5) == pytest.approx(50)
    assert fifo_cost(depot, "Wood", 7) == pytest.approx(50 + 40)


def test_a_big_order_moves_the_price_against_the_trader(depot, make_good, game_state):
    iron = make_good("Iron", price=10, market_quantity=10)

    assert price_after(iron, 5, buying=True) > iron.price
    assert price_after(iron, 20, buying=False) < iron.price
    assert buy_offer(iron, 5, depot, game_state).each > 10 * 1.02


def test_a_small_order_in_a_deep_market_leaves_the_price(wood):
    assert price_after(wood, 10, buying=True) == pytest.approx(wood.price)


# THE MOST THAT COULD BE TRADED

def test_max_buy_is_what_the_purse_pays(depot, wood):
    depot.money = 51        # five at 10.2, the fee included
    assert max_buy(wood, depot) == 5


def test_max_buy_is_what_the_storage_takes(depot, wood):
    assert max_buy(wood, depot) == depot.room_for("Wood") == 100


def test_max_buy_is_what_the_market_holds(depot, make_good):
    assert max_buy(make_good("Iron", price=1, market_quantity=7), depot) == 7


def test_max_buy_stops_where_the_slippage_makes_it_too_dear(depot, make_good):
    iron = make_good("Iron", price=10, market_quantity=40)
    depot.money = 250
    most = max_buy(iron, depot)

    assert 0 < most < 40
    assert iron.quote(most, buying=True) * 1.02 <= 250 < iron.quote(most + 1, buying=True) * 1.02


def test_no_order_names_more_than_the_most(depot, make_good):
    depot.starting_slots = [{"good": None, "qty": 0, "reserved": None} for _ in range(100)]
    cheap = make_good("Wood", price=0.01, market_quantity=100_000)
    assert max_buy(cheap, depot) == MAX_QUANTITY


# WHY AN ORDER IS REFUSED

def test_nothing_is_traded_away_from_a_market_square(depot, wood, game_state):
    game_state.game = SimpleNamespace(player=SimpleNamespace(in_market_area=False))
    assert market_block("Wood", depot, game_state) == "Trade at a market square"
    assert buy_offer(wood, 1, depot, game_state).blocked == "Trade at a market square"


@pytest.mark.parametrize("setup, reason", [
    (lambda d, gs: setattr(gs, "sold_here", {"Stone"}), "Not sold at this market"),
    (lambda d, gs: gs.closed.add("Wood"), "Booth closed"),
    (lambda d, gs: setattr(gs, "time_level", 1), "Game paused"),
    (lambda d, gs: d.trading_licenses.clear(), "No licence"),
])
def test_what_stops_both_sides(depot, wood, game_state, setup, reason):
    depot.buy(wood, 5, game_state)
    setup(depot, game_state)

    assert buy_offer(wood, 1, depot, game_state).blocked == reason
    assert sell_offer(wood, 1, depot, game_state).blocked == reason


@pytest.mark.parametrize("setup, quantity, reason", [
    (lambda d: None, 0, "Enter a quantity"),
    (lambda d: setattr(d, "money", 5), 1, "Not enough money"),
    (lambda d: None, 101, "Room for only 100"),
])
def test_what_stops_a_purchase(depot, wood, game_state, setup, quantity, reason):
    setup(depot)
    assert buy_offer(wood, quantity, depot, game_state).blocked == reason


def test_a_purchase_the_market_cannot_fill(depot, make_good, game_state):
    iron = make_good("Iron", market_quantity=3)
    assert buy_offer(iron, 4, depot, game_state).blocked == "The market has only 3"


def test_what_stops_a_sale(depot, wood, game_state):
    assert sell_offer(wood, 1, depot, game_state).blocked == "None in stock"
    depot.buy(wood, 5, game_state)
    assert sell_offer(wood, 0, depot, game_state).blocked == "Enter a quantity"
    assert sell_offer(wood, 6, depot, game_state).blocked == "You hold only 5"
    assert sell_offer(wood, 5, depot, game_state).blocked is None


@pytest.mark.parametrize("quantity", [4, 5])
def test_an_offer_refused_is_a_trade_refused(depot, wood, game_state, quantity):
    """The desk greys a button exactly when the depot would refuse the order."""
    depot.money = 50        # four at 10.2 and not five
    offer = buy_offer(wood, quantity, depot, game_state)
    assert (offer.blocked is None) == depot.buy(wood, quantity, game_state) == (quantity == 4)
