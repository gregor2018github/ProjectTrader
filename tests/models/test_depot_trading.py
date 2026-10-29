"""Depot.buy() and Depot.sell(): money, stock, the market, FIFO profit, and every reason a trade is refused."""

import pytest


def snapshot(depot, good):
    """What a refused trade must leave as it was."""
    return (depot.money, dict(depot.good_stock), good.market_quantity,
            [dict(s) for s in depot.starting_slots], len(depot.trades))


# BUYING

def test_buy_moves_money_goods_and_market(depot, wood, game_state):
    assert depot.buy(wood, 10, game_state)

    assert depot.money == 10_000 - 100 - 2
    assert depot.good_stock["Wood"] == 10
    assert wood.market_quantity == 990
    assert depot.expenditures == 102
    assert depot.transaction_expenditures == 2
    assert depot.purchase_history["Wood"] == [
        {"timestamp": game_state.date, "price": 10.0, "quantity": 10, "total_cost": 100.0}
    ]
    assert depot.trades[-1]["type"] == "purchase"
    assert depot.stats.goods_bought == 1
    assert depot.stats.money_spent_goods == 100
    assert game_state.events[-1][0] == "TRADE"
    assert game_state.money_feedback == [("spent", 100)]
    assert game_state.warnings == []


def test_buy_with_exactly_enough_money(depot, wood, game_state):
    depot.money = 102
    assert depot.buy(wood, 10, game_state)
    assert depot.money == 0


def test_big_order_pays_more_per_unit_as_the_market_empties(depot, make_good, game_state):
    iron = make_good("Iron", price=10, market_quantity=10)
    quoted = iron.quote(5, buying=True)
    assert quoted > 5 * iron.price

    assert depot.buy(iron, 5, game_state)
    assert depot.money == pytest.approx(10_000 - quoted - 2)
    assert depot.purchase_history["Iron"][0]["price"] == pytest.approx(quoted / 5)


@pytest.mark.parametrize("setup, quantity, warning", [
    (lambda d, g, gs: None, 0, None),
    (lambda d, g, gs: setattr(gs, "sold_here", {"Stone"}), 1, "Wood is not traded at this market."),
    (lambda d, g, gs: gs.closed.add("Wood"), 1, "The Wood booth is closed."),
    (lambda d, g, gs: d.trading_licenses.pop("Wood"), 1, "No trading license for Wood."),
    (lambda d, g, gs: setattr(g, "market_quantity", 5), 6, "Market cannot fulfill the order."),
    (lambda d, g, gs: setattr(d, "money", 101), 10, "Not enough money."),
], ids=["nothing", "not-sold-here", "booth-closed", "no-license", "market-short", "no-money"])
def test_refused_purchase_changes_nothing(depot, wood, game_state, setup, quantity, warning):
    setup(depot, wood, game_state)
    before = snapshot(depot, wood)

    assert not depot.buy(wood, quantity, game_state)

    assert snapshot(depot, wood) == before
    assert game_state.warnings == ([warning] if warning else [])
    assert game_state.money_feedback == []


def test_buy_refused_when_storage_is_full(depot, wood, stone, game_state):
    assert depot.buy(wood, 100, game_state)
    assert not depot.buy(stone, 1, game_state)
    assert game_state.warnings == ["Not enough storage capacity."]


def test_buy_refused_when_free_units_are_in_slots_of_another_good(depot, wood, stone, game_state):
    # 81 Wood takes all five slots (20+20+20+20+1): 19 units are free, but only for Wood
    assert depot.buy(wood, 81, game_state)
    assert not depot.buy(stone, 1, game_state)
    assert "each slot holds one good only" in game_state.warnings[0]
    assert depot.buy(wood, 19, game_state)


# SELLING

def test_sell_moves_money_goods_and_market(depot, wood, game_state):
    depot.buy(wood, 10, game_state)
    money = depot.money

    assert depot.sell(wood, 4, game_state)

    assert depot.money == money + 40 - 2
    assert depot.good_stock["Wood"] == 6
    assert wood.market_quantity == 994
    assert depot.income == 40
    assert depot.trades[-1]["type"] == "sale"
    assert depot.stats.goods_sold == 1
    assert game_state.money_feedback[-1] == ("received", 40)


def test_buying_and_selling_back_costs_only_the_fees(depot, make_good, game_state):
    # Even where each unit moves the price, the volumes cancel out
    iron = make_good("Iron", price=10, market_quantity=10)
    depot.buy(iron, 5, game_state)
    depot.sell(iron, 5, game_state)

    assert depot.money == pytest.approx(10_000 - 4)
    assert iron.market_quantity == 10


def test_sell_matches_purchases_first_in_first_out(depot, wood, game_state):
    depot.buy(wood, 10, game_state)    # at 10
    wood.set_price(20)
    depot.buy(wood, 10, game_state)    # at 20
    wood.set_price(30)

    assert depot.sell(wood, 15, game_state)

    # 10 from the first lot (+20 each), 5 from the second (+10 each)
    cycles = depot.trade_cycle_records
    assert [(c["quantity"], c["buy_price"], c["profit"]) for c in cycles] == [(10, 10, 200), (5, 20, 50)]
    assert depot.trade_cycles["total"] == 2
    assert depot.trade_cycles["successful"] == 2
    assert depot.trade_cycles["total_profit"] == 250
    assert depot.trade_cycles["by_good"]["Wood"]["best_profit"] == 20
    assert depot.trade_cycles["by_good"]["Wood"]["worst_profit"] == 10
    # What is left is 5 of the second lot
    assert depot.purchase_history["Wood"] == [
        {"timestamp": game_state.date, "price": 20.0, "quantity": 5, "total_cost": 100.0}
    ]
    assert depot.avg_buy_price("Wood") == 20


def test_sell_at_a_loss_is_a_cycle_but_not_a_successful_one(depot, wood, game_state):
    depot.buy(wood, 10, game_state)
    wood.set_price(4)
    depot.sell(wood, 10, game_state)

    assert depot.trade_cycles["total"] == 1
    assert depot.trade_cycles["successful"] == 0
    assert depot.trade_cycles["total_profit"] == -60
    assert depot.avg_buy_price("Wood") is None


def test_sell_refused_with_too_little_stock(depot, wood, game_state):
    depot.buy(wood, 3, game_state)
    before = snapshot(depot, wood)

    assert not depot.sell(wood, 4, game_state)

    assert snapshot(depot, wood) == before
    assert game_state.warnings == ["Not enough Wood in stock."]


def test_sell_refused_when_the_fee_cannot_be_paid(depot, make_good, game_state):
    cheap = make_good("Wood", price=0.5)
    depot.money = 2.5
    depot.buy(cheap, 1, game_state)    # 0.5 + 2 fee: nothing left
    before = snapshot(depot, cheap)

    # 0.5 revenue does not cover the 2 fee, and there is no money to make up for it
    assert not depot.sell(cheap, 1, game_state)

    assert snapshot(depot, cheap) == before
    assert game_state.warnings == ["Not enough money to cover transaction costs."]


def test_sell_refused_without_license(depot, wood, game_state):
    depot.buy(wood, 5, game_state)
    del depot.trading_licenses["Wood"]

    assert not depot.sell(wood, 5, game_state)
    assert depot.good_stock["Wood"] == 5
