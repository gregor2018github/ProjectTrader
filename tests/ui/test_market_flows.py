"""The market view's demand and supply panel: what it adds up, how it rounds, where it opens."""
import pygame
import pytest

from src.sim.state import GoodFlows
from src.ui import market_flows as mf
from src.ui.market_flows import DailyFlows


@pytest.fixture(scope="module", autouse=True)
def fonts():
    pygame.font.init()
    yield


def test_demand_is_the_towns_baskets_and_the_workshops_inputs_and_supply_what_was_made_and_imported():
    flows = mf.daily_flows(GoodFlows(wanted=44.0, bought=40.0, input_wanted=17.0, input_bought=15.0,
                                     produced=38.0, imported=30.0, exported=5.0))
    assert (flows.townsfolk, flows.workshops, flows.made, flows.imported, flows.exported) == (44.0, 17.0, 38.0, 30.0, 5.0)
    assert flows.demand == 61.0 and flows.supply == 68.0


def test_amounts_are_whole_units_a_little_is_under_one_and_none_is_zero():
    assert mf.amount(1234.4) == "1,234"
    assert mf.amount(9.6) == "10"
    assert mf.amount(1.0) == "1"
    assert mf.amount(0.4) == "<1"
    assert mf.amount(0.001) == "0"


def test_the_larger_bar_fills_the_width_and_the_other_follows():
    assert mf.bar_lengths(DailyFlows(40.0, 20.0, 30.0, 0.0, 0.0), width=150) == (150, 75)
    assert mf.bar_lengths(DailyFlows(0.0, 0.0, 0.0, 0.0, 0.0), width=150) == (0, 0)


def test_what_was_sent_out_shows_only_when_something_was():
    demand, supply = mf.detail_lines(DailyFlows(44.0, 17.0, 38.0, 30.0, 0.0))
    assert demand == "townsfolk 44, workshops 17" and supply == "made here 38, imported 30"
    assert mf.detail_lines(DailyFlows(1.0, 0.0, 9.0, 0.0, 6.5))[1] == "made here 9, imported 0; sent out 7"


def test_the_reconciling_line_names_the_stock_taken_and_what_went_without():
    short = DailyFlows(townsfolk=50.0, workshops=10.0, made=30.0, imported=20.0, exported=0.0, got=55.0)
    assert short.went_without == 5.0 and short.added_to_stock == -5.0
    assert mf.reconcile_line(short) == "Taken from stock 5, went without 5"
    glut = DailyFlows(townsfolk=20.0, workshops=0.0, made=40.0, imported=0.0, exported=5.0, got=20.0)
    assert mf.reconcile_line(glut) == "Added to stock 15"
    even = DailyFlows(townsfolk=20.0, workshops=0.0, made=20.0, imported=0.0, exported=0.0, got=20.0)
    assert mf.reconcile_line(even) == "Stock unchanged"
    player = DailyFlows(townsfolk=20.0, workshops=0.0, made=20.0, imported=0.0, exported=0.0, got=20.0,
                        player_bought=8.0, player_sold=0.3)
    assert mf.reconcile_line(player) == "Taken from stock 8, you bought 8, you sold <1"


def test_demand_and_supply_reconcile_exactly_with_how_the_stock_moved():
    flows = mf.daily_flows(GoodFlows(wanted=44.0, bought=40.0, input_wanted=17.0, input_bought=15.0,
                                     produced=38.0, imported=30.0, exported=5.0, player_bought=2.0, player_sold=1.0))
    # in: made 38 + imported 30 + the player's 1; out: bought 40 + 15, sent out 5, the player 2
    assert flows.added_to_stock == pytest.approx(38 + 30 + 1 - 40 - 15 - 5 - 2)
    assert flows.demand - flows.went_without == pytest.approx(
        flows.supply - flows.exported - flows.added_to_stock + flows.player_sold - flows.player_bought)


def test_the_panel_opens_above_the_pointer_when_the_goods_bar_leaves_no_room_below():
    screen = pygame.Surface((1760, 1064))
    font = pygame.font.Font(None, 24)
    flows = DailyFlows(44.0, 17.0, 38.0, 30.0, 0.0)
    low = mf.draw_flows_tooltip(screen, font, "Wood", flows, (100, 960), safe_right=1650, safe_bottom=1004)
    assert low.bottom == 960 - mf.ABOVE_POINTER and low.left == 135
    high = mf.draw_flows_tooltip(screen, font, "Wood", flows, (100, 200), safe_right=1650, safe_bottom=1004)
    assert high.top == 210
    right = mf.draw_flows_tooltip(screen, font, "Wood", flows, (1600, 200), safe_right=1650, safe_bottom=1004)
    assert right.right == 1585


def test_the_panel_draws_its_two_bars_in_their_colours():
    screen = pygame.Surface((800, 600))
    screen.fill((0, 0, 0))
    panel = mf.draw_flows_tooltip(screen, pygame.font.Font(None, 24), "Wine", DailyFlows(35.0, 0.0, 0.0, 11.0, 0.0),
                                  (10, 10), safe_right=800, safe_bottom=600, warning="No License")
    colours = {tuple(screen.get_at((x, y)))[:3] for x in range(panel.left, panel.right)
               for y in range(panel.top, panel.bottom)}
    assert mf.DEMAND_COLOR in colours and mf.SUPPLY_COLOR in colours
