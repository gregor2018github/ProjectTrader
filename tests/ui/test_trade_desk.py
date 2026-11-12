"""The market view's trade desk: its cards' layout, quantities and orders, and the chart choosing its goods."""

import pygame
import pytest

from src.game_state import GameState
from src.handlers.mouse_handler import _step_trade_quantity, _toggle_chart_good, trade_card_order
from src.models.trade_offer import MAX_QUANTITY
from src.ui.layout_modules import trade_desk
from tests.models.conftest import depot, game_state, make_good, pinned_storage  # noqa: F401


@pytest.fixture
def goods(make_good):  # noqa: F811
    goods = [make_good(name) for name in ("Wood", "Stone", "Iron", "Wool")]
    for i, good in enumerate(goods):
        good.index = i
        good.show_in_charts = i < 2
    return goods


@pytest.fixture
def state(goods):
    """A real GameState with Wood and Stone in the chart, each with a quantity of 5."""
    state = GameState()
    state.available_goods = [g.name for g in goods]
    state.good_quantities = {g.name: "5" for g in goods}
    state.chart_selection_order = ["Wood", "Stone"]
    state.sync_quicktrade_fields()
    return state


# THE CARDS FOLLOW THE CHART

def test_the_cards_are_the_charted_goods_in_the_order_chosen(state, goods):
    assert state.trade_goods() == ["Wood", "Stone"]
    assert state.input_fields["good_one"] == "Wood" and state.input_fields["quantity_one"] == "5"
    assert state.input_fields["good_three"] == ""

    _toggle_chart_good(goods[3], goods, state)

    assert state.trade_goods() == ["Wood", "Stone", "Wool"]
    assert state.input_fields["good_three"] == "Wool"


def test_taking_a_good_out_of_the_chart_takes_its_card(state, goods):
    _toggle_chart_good(goods[0], goods, state)
    assert state.trade_goods() == ["Stone"]
    assert state.input_fields["good_one"] == "Stone" and state.input_fields["good_two"] == ""


def test_a_market_square_remembers_the_goods_charted_there(state, goods):
    state.market_area = "Market_Area"
    _toggle_chart_good(goods[2], goods, state)
    assert state.quicktrade_slots["Market_Area"] == ["Wood", "Stone", "Iron"]


def test_away_from_the_markets_the_chart_changes_no_square(state, goods):
    before = {area: list(slots) for area, slots in state.quicktrade_slots.items()}
    _toggle_chart_good(goods[2], goods, state)
    assert state.quicktrade_slots == before


def test_choosing_a_good_ends_typing_a_quantity(state, goods):
    state.mouse_clicked_on = "quantity_one"
    _toggle_chart_good(goods[2], goods, state)
    assert state.mouse_clicked_on == "none"


# THE LAYOUT

def test_three_cards_fit_the_desk_without_overlapping(goods):
    desk = pygame.Rect(1510, 60, trade_desk.DESK_WIDTH, 885)
    cards = trade_desk.layout_cards(desk, goods[:2])

    assert [card.section for card in cards] == ["one", "two", "three"]
    assert [card.good for card in cards] == [goods[0], goods[1], None]
    assert all(desk.contains(card.rect) for card in cards)
    assert cards[0].rect.bottom < cards[1].rect.top < cards[1].rect.bottom < cards[2].rect.top
    assert cards[2].parts == {}


def test_a_cards_parts_are_on_it_and_apart(goods):
    card = trade_desk.layout_cards(pygame.Rect(0, 0, trade_desk.DESK_WIDTH, 885), goods[:1])[0]
    parts = list(card.parts.values())

    assert set(card.parts) == {"half", "minus", "quantity", "plus", "double", "buy", "sell", "maxbuy", "maxsell"}
    assert all(card.rect.contains(part) for part in parts)
    assert not any(a.colliderect(b) for i, a in enumerate(parts) for b in parts[i + 1:])


def test_the_pointer_on_a_card_names_its_good(goods):
    cards = trade_desk.layout_cards(pygame.Rect(0, 0, trade_desk.DESK_WIDTH, 885), goods[:2])
    assert trade_desk.hovered_good(cards, cards[1].rect.center) is goods[1]
    assert trade_desk.hovered_good(cards, cards[2].rect.center) is None


# THE QUANTITY

@pytest.mark.parametrize("part, expected", [
    ("plus", "6"), ("minus", "4"), ("double", "10"), ("half", "2"), ("maxbuy", "40"), ("maxsell", "7"),
])
def test_the_steps_change_the_quantity(state, part, expected):
    state.trade_limits = {"one": (40, 7)}
    _step_trade_quantity(part, "one", "Wood", state)
    assert state.input_fields["quantity_one"] == expected
    assert state.good_quantities["Wood"] == expected


def test_the_quantity_stays_between_one_and_the_most(state):
    state.set_trade_quantity("Wood", 0)
    assert state.good_quantities["Wood"] == "1"
    state.set_trade_quantity("Wood", 5000)
    assert state.good_quantities["Wood"] == str(MAX_QUANTITY)


def test_a_limit_of_nothing_is_not_taken_as_the_quantity(state):
    state.trade_limits = {"one": (0, 0)}
    _step_trade_quantity("maxbuy", "one", "Wood", state)
    _step_trade_quantity("maxsell", "one", "Wood", state)
    assert state.input_fields["quantity_one"] == "5"


def test_nothing_typed_counts_as_no_quantity(state):
    state.input_fields["quantity_one"] = ""
    assert trade_desk.quantity_of(state, "one") == 0
    assert trade_desk.quantity_of(state, "two") == 5


# THE ORDER

class _Game:
    """What trade_card_order asks of the game: where the player stands."""
    def __init__(self, in_market_area=True):
        self.player = type("Player", (), {"in_market_area": in_market_area, "market_area": None})()


@pytest.fixture
def trading(state, monkeypatch, depot):  # noqa: F811
    """The real GameState made to trade like the fake one: every booth open, warnings kept, no coin popups."""
    from src.models import depot as depot_module
    state.warnings = []
    monkeypatch.setattr(state, "show_warning", state.warnings.append)
    monkeypatch.setattr(state, "is_good_tradable", lambda name: True)
    monkeypatch.setattr(state, "is_good_sold_here", lambda name: True)
    monkeypatch.setattr(depot_module, "on_money_spent", lambda gs, amount=0.0: None)
    monkeypatch.setattr(depot_module, "on_money_received", lambda gs, amount=0.0: None)
    state.game = _Game()
    for name in depot.good_stock:
        depot.add_license(name, 12, state.date)
    return state


def test_a_cards_button_buys_and_sells_its_quantity(trading, goods, depot):  # noqa: F811
    assert trade_card_order("buy", "one", trading, goods, depot)
    assert depot.good_stock["Wood"] == 5
    assert trading.button_click_effects["buy_one"] > 0

    assert trade_card_order("sell", "one", trading, goods, depot)
    assert depot.good_stock["Wood"] == 0


def test_no_order_while_paused_or_away_from_the_markets(trading, goods, depot):  # noqa: F811
    trading.time_level = 1
    assert not trade_card_order("buy", "one", trading, goods, depot)
    trading.time_level = 3
    trading.game = _Game(in_market_area=False)
    assert not trade_card_order("buy", "one", trading, goods, depot)
    assert depot.good_stock["Wood"] == 0 and trading.warnings == []


def test_an_order_the_depot_refuses_says_why(trading, goods, depot):  # noqa: F811
    depot.money = 1
    assert not trade_card_order("buy", "one", trading, goods, depot)
    assert trading.warnings == ["Not enough money."]


def test_a_click_on_a_greyed_button_stays_quiet(trading, goods, depot):  # noqa: F811
    depot.money = 1
    assert not trade_card_order("buy", "one", trading, goods, depot, quiet=True)
    assert trading.warnings == []


def test_a_card_without_a_good_or_a_quantity_orders_nothing(trading, goods, depot):  # noqa: F811
    assert not trade_card_order("buy", "three", trading, goods, depot)
    trading.input_fields["quantity_one"] = ""
    assert not trade_card_order("buy", "one", trading, goods, depot)


# WHAT A CARD SAYS

def test_the_days_change_needs_a_days_chart(goods):
    wood = goods[0]
    assert trade_desk.day_change(wood) is None
    wood.price_history_hourly[:] = [8.0] * 60
    assert trade_desk.day_change(wood) == pytest.approx(0.25)


def test_the_last_line_says_why_or_what_the_order_does(trading, goods, depot):  # noqa: F811
    wood = goods[0]
    buy, sell = trade_desk.offers(wood, 5, depot, trading)
    assert trade_desk.status_line(wood, buy, sell, None, depot, trading)[0] == ""
    assert trade_desk.status_line(wood, buy, sell, "buy", depot, trading)[0] == "Price rises to 10.00"
    assert trade_desk.status_line(wood, buy, sell, "sell", depot, trading)[0] == "None in stock"

    depot.buy(wood, 5, trading)
    wood.price = 12.0
    buy, sell = trade_desk.offers(wood, 5, depot, trading)
    assert trade_desk.status_line(wood, buy, sell, "sell", depot, trading)[0] == "Profit 8.80, price falls to 12.00"

    trading.time_level = 1
    assert trade_desk.status_line(wood, buy, sell, None, depot, trading)[0] == "Game paused"

