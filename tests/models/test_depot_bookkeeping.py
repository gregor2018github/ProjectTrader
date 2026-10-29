"""Bookings outside the market (living costs, donations, labour, loans), the daily
roll-over into the histories, and the breakdowns and statistics read from them."""

import datetime

import pytest

from src.config.constants import ALMS_CATEGORY
from tests.fakes import fake_warehouse


def next_day(depot):
    """What the main loop does to the depot at midnight."""
    depot.update_income_and_expenditures()
    depot.update_stock_history()
    depot.update_total_stock()


# BOOKINGS

def test_cost_of_living_is_charged_even_into_debt(depot):
    depot.money = 3
    depot.book_cost_of_living(5)
    assert depot.money == -2
    assert depot.cost_of_living_expenditures == 5
    assert depot.expenditures == 5


@pytest.mark.parametrize("category", ["Church Donations", "Town Donations", ALMS_CATEGORY])
def test_donation_is_booked_under_its_category(depot, category):
    assert depot.book_donation(7, category)
    assert depot.money == 10_000 - 7
    assert depot.donations[category] == 7
    assert depot.donation_expenditures == 7
    assert depot.stats.donations_total == 7


def test_donation_refused_without_the_money(depot):
    depot.money = 6
    assert not depot.book_donation(7)
    assert depot.money == 6
    assert depot.donation_expenditures == 0


def test_a_new_donation_category_gets_a_history_as_long_as_the_others(depot):
    next_day(depot)
    next_day(depot)
    depot.book_donation(4, "Guild Donations")
    assert depot.donation_history["Guild Donations"] == [0.0, 0.0, 0.0]

    next_day(depot)
    assert depot.donation_history["Guild Donations"] == [0.0, 0.0, 0.0, 4]


def test_labor_income_pays_without_a_fee(depot):
    next_day(depot)
    depot.book_labor_income(15, "Woodhacking")

    assert depot.money == 10_015
    assert depot.income == 15
    assert depot.labor_income == {"Woodhacking": 15}
    assert depot.labor_income_history["Woodhacking"] == [0.0, 0.0]


def test_miscellaneous_refused_without_the_money(depot):
    assert depot.book_miscellaneous(3)
    depot.money = 2
    assert not depot.book_miscellaneous(3)
    assert depot.miscellaneous_expenditures == 3


def test_overdraft_penalty_is_counted(depot):
    depot.book_overdraft_penalty(4)
    assert depot.money == 10_000 - 4
    assert depot.overdraft_expenditures == 4
    assert depot.stats.overdraft_count == 1


# LOANS

def take_loan(depot, amount=1000):
    depot.take_loan(amount, daily_principal=50, daily_interest=5, settlement_principal=0,
                    duration_days=20, start_date="1 March 1450")


def test_loan_credits_its_principal(depot):
    take_loan(depot)
    assert depot.money == 11_000
    assert depot.active_loans[0]["remaining_principal"] == 1000
    assert depot.stats.loans_taken == 1


def test_repaying_a_loan_early(depot, game_state):
    take_loan(depot)
    depot.active_loans[0]["remaining_principal"] = 600

    assert depot.repay_loan(0, game_state)

    assert depot.money == 11_000 - 600
    assert depot.active_loans == []
    assert game_state.events[-1][0] == "LOAN"


def test_repaying_refused_without_the_money_or_the_loan(depot, game_state):
    take_loan(depot)
    depot.money = 999

    assert not depot.repay_loan(0, game_state)
    assert not depot.repay_loan(1, game_state)
    assert not depot.repay_loan(-1, game_state)

    assert depot.money == 999
    assert len(depot.active_loans) == 1
    assert game_state.warnings == ["Not enough money to repay loan."]


# THE DAILY ROLL-OVER

def test_roll_over_moves_the_day_into_history_and_starts_afresh(depot, wood, game_state):
    depot.buy(wood, 10, game_state)
    depot.book_cost_of_living(5)
    depot.book_donation(7)

    next_day(depot)

    assert depot.expenditure_history == [0.0, 114]
    assert depot.transaction_expenditure_history == [0.0, 2]
    assert depot.cost_of_living_expenditure_history == [0.0, 5]
    assert depot.donation_history["Church Donations"] == [0.0, 7]
    assert depot.stock_history["Wood"] == [0, 10]
    assert depot.total_stock == [0, 10]
    assert (depot.expenditures, depot.transaction_expenditures, depot.donation_expenditures) == (0, 0, 0)
    assert depot.donations["Church Donations"] == 0


def test_wealth_is_money_and_goods_and_buildings_less_loans(depot, wood, game_state):
    depot.buy(wood, 10, game_state)                 # 102 for 10 Wood worth 10 each
    depot.buy_warehouse(fake_warehouse(buy_price=500), game_state)
    take_loan(depot, 1000)

    wealth = depot.update_wealth([wood])

    assert depot.money == 10_000 - 102 - 500 + 1000
    assert wealth == depot.money + 100 + 500 - 1000
    assert depot.wealth[-1] == wealth
    assert depot.property_value_history[-1] == 500
    assert depot.loan_history[-1] == 1000


# BREAKDOWNS

@pytest.fixture
def two_days(depot, wood, game_state):
    """Day one: 10 Wood bought (100 + 2 fee), 5 living costs, 15 from woodhacking.
    Day two, still open: 7 to the church, 3 into a well, 5 from fishing."""
    depot.buy(wood, 10, game_state)
    depot.book_cost_of_living(5)
    depot.book_labor_income(15, "Woodhacking")
    next_day(depot)
    depot.book_donation(7)
    depot.book_miscellaneous(3)
    depot.book_labor_income(5, "Fishing")
    return depot


def test_expense_breakdown_of_today(two_days):
    today = two_days.get_expense_breakdown(1)

    assert today["total"] == 10
    assert today["donations"]["Church Donations"] == 7
    assert today["miscellaneous"]["total"] == 3
    assert today["trading_expenses"]["total"] == 0
    assert today["cost_of_living"]["total"] == 0


@pytest.mark.parametrize("period", [2, 30, None])
def test_expense_breakdown_over_both_days(two_days, period):
    both = two_days.get_expense_breakdown(period)

    assert both["total"] == 117
    assert both["trading_expenses"] == {"total": 102, "Transaction Cost": 2, "Good Cost": 100}
    assert both["cost_of_living"]["total"] == 5
    assert both["donations"]["total"] == 7


def test_income_breakdown(two_days):
    today = two_days.get_income_breakdown(1)
    assert today["total"] == 5
    assert today["labor_income"] == {"total": 5, "Woodhacking": 0, "Fishing": 5}

    both = two_days.get_income_breakdown(None)
    assert both["total"] == 20
    assert both["labor_income"]["Woodhacking"] == 15
    assert both["sold_goods"]["total"] == 0


def test_sales_count_as_market_income(depot, wood, game_state):
    depot.buy(wood, 10, game_state)
    depot.sell(wood, 10, game_state)
    assert depot.get_income_breakdown(1)["sold_goods"] == {"total": 100, "Market": 100}


def test_donation_stats(two_days):
    assert two_days.get_donation_stats(None)["total"] == 7
    assert two_days.get_donation_stats(1)["by_category"]["Church Donations"] == 7


# TRADE CYCLE STATISTICS

def test_trade_cycle_stats_look_back_over_a_period(depot, wood, game_state):
    depot.buy(wood, 20, game_state)
    wood.set_price(15)
    depot.sell(wood, 10, game_state)                # +5 a unit
    game_state.date += datetime.timedelta(days=10)
    wood.set_price(5)
    depot.sell(wood, 10, game_state)                # -5 a unit

    recent = depot.get_trade_cycle_stats(game_state.date, datetime.timedelta(days=3))
    assert (recent["total_cycles"], recent["successful_cycles"], recent["total_profit"]) == (1, 0, -50)

    every = depot.get_trade_cycle_stats(game_state.date, None)
    assert every["total_cycles"] == 2
    assert every["success_rate"] == 50
    assert every["total_profit"] == 0
    assert every["best_goods"] == [("Wood", 0)]


def test_no_trades_no_success_rate(depot, game_state):
    assert depot.get_trade_cycle_stats(game_state.date, None)["success_rate"] == 0


# OLD SAVES

def test_goods_added_after_a_save_get_empty_records(depot):
    next_day(depot)
    next_day(depot)
    depot.good_stock["Wood"] = 4

    depot.add_missing_goods(["Wood", "Silk"])

    assert depot.good_stock["Wood"] == 4
    assert depot.good_stock["Silk"] == 0
    assert depot.stock_history["Silk"] == [0, 0, 0]
    assert depot.purchase_history["Silk"] == []
    assert depot.trade_cycles["by_good"]["Silk"]["total"] == 0
