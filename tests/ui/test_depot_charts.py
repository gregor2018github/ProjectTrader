"""The depot's charts: what each one shows (``depot_chart_data``: the days lined up with the
calendar, today so far, the range, seasons when the days do not fit, the legend, the headline
figures) and the view (``depot_view_chart``, ``depot_view``: drawn without fault, and its tabs,
ranges, legend and rows doing what they say)."""

import datetime
from types import SimpleNamespace

import pygame
import pytest

from src.game_state import GameState
from src.models.depot import Depot
from src.sim.calendar import EPOCH
from src.ui.layout_modules import depot_chart_data as data
from src.ui.layout_modules import depot_view, depot_view_chart, ledger_style
from src.ui.layout_modules.depot_chart_data import CHARTS, SEASON, build_chart, compact, nice_step, signed
from tests.models.conftest import GOODS, make_good, pinned_storage  # noqa: F401

DAYS = 10                                           # today is the calendar's 11th day
NOW = datetime.datetime.combine(EPOCH, datetime.time(14, 0)) + datetime.timedelta(days=DAYS)
WIDE = 800                                          # a plot wide enough for every day as a column


class FakeDepot(SimpleNamespace):
    """Books of DAYS midnights after the opening: net worth 100 at the opening and 10 more every
    day, all of it coin; an income of 10 coins a day, 2 of them from fishing from the 5th day on."""

    def __init__(self):
        n = DAYS + 1                                # the opening and a snapshot every midnight
        wealth = [100.0 + 10 * k for k in range(n)]
        super().__init__(
            wealth=wealth, money_history=list(wealth), property_value_history=[0.0] * n, loan_history=[0.0] * n,
            money=215.0, good_stock={"Wood": 0}, stock_history={"Wood": [0] * n}, storage_capacity=100,
            house_history=[0] * n, storage_capacity_history=[100] * n,
            income_history=[0.0] + [10.0] * DAYS, income=7.0,
            labor_income_history={"Fishing": [0.0] * 5 + [2.0] * (n - 5)}, labor_income={"Fishing": 3.0},
            expenditure_history=[0.0] + [4.0] * DAYS, expenditures=1.0,
            cost_of_living_expenditure_history=[0.0] + [1.0] * DAYS, cost_of_living_expenditures=1.0,
            loan_expenditure_history=[0.0] + [0.5] * DAYS, loan_expenditures=0.0,
            overdraft_expenditure_history=[0.0] + [0.5] * DAYS, overdraft_expenditures=0.0,
            donation_expenditure_history=[0.0] * n, donation_expenditures=0.0,
        )

    def outstanding_loans(self):
        return 0.0

    def get_property_value(self):
        return 0.0

    def get_property_count(self):
        return 0

    def total_capacity(self):
        return 100


GOODS_SHOWN = [SimpleNamespace(name="Wood", price=2.0, color=(120, 80, 40))]


def chart(name, **kwargs):
    kwargs.setdefault("plot_width", WIDE)
    return build_chart(name, FakeDepot(), GOODS_SHOWN, None, NOW, **kwargs)


# THE DAYS, LINED UP WITH THE CALENDAR

class TestDays:
    def test_a_level_runs_from_the_first_day_to_today(self):
        wealth = chart("Wealth")
        # the opening snapshot is dated the day before the calendar's first, and left out
        assert wealth.count == DAYS + 1
        assert wealth.dates[0] == EPOCH and wealth.dates[-1] == NOW.date()

    def test_the_last_snapshot_is_yesterday_and_today_is_live(self):
        net = chart("Wealth").lines[0].values
        assert net[-2] == 200.0                     # how yesterday closed
        assert net[-1] == 215.0                     # what the purse holds now

    def test_today_is_so_far(self):
        wealth = chart("Wealth")
        assert wealth.partial
        assert wealth.headings[-1].endswith(", so far")
        assert not wealth.headings[-2].endswith(", so far")

    def test_a_flow_has_no_column_for_the_opening(self):
        income = chart("Income")
        assert income.count == DAYS + 1             # the ten days in the books, and today
        assert income.dates[0] == EPOCH

    def test_the_range_keeps_the_last_days(self):
        season = chart("Wealth", range_name="Season")
        assert season.count == 7
        assert season.dates[0] == NOW.date() - datetime.timedelta(days=6)


# WHAT EACH CHART SHOWS

class TestFlows:
    def test_what_the_parts_do_not_account_for_is_goods_sold(self):
        income = chart("Income")
        by_name = {s.name: s.values for s in income.layers}
        assert by_name["Fishing"][-1] == 3.0 and by_name["Goods sold"][-1] == 4.0     # today, so far
        assert by_name["Fishing"][0] == 0.0 and by_name["Goods sold"][0] == 10.0
        assert [income.stack_total(i) for i in range(income.count)] == [10.0] * DAYS + [7.0]

    def test_loan_interest_and_overdraft_are_one_kind_of_expense(self):
        loans = {s.name: s.values for s in chart("Expenses").layers}["Loans"]
        assert loans[0] == 1.0

    def test_only_what_there_was_is_in_the_legend(self):
        names = [s.name for s in chart("Expenses").layers]
        assert "Donations" not in names and "Licences" not in names
        assert "Cost of living" in names

    def test_profit_is_how_much_better_each_day_closed(self):
        profit = chart("Profit")
        assert profit.layers[0].values == [10.0] * DAYS + [15.0]
        assert profit.extra[-1][-1] == ("Running total", "+115")      # whole coins from 100 up
        assert profit.lines[0].name == "Average"
        assert profit.lines[0].values[0] == pytest.approx(115.0 / 11)

    def test_the_running_total_starts_with_the_range(self):
        profit = chart("Profit", range_name="Season")
        assert profit.extra[0][-1] == ("Running total", "+10.00")


class TestColumns:
    def test_days_that_do_not_fit_are_summed_into_seasons(self):
        income = chart("Income", plot_width=2 * data.BAR_PITCH)
        assert income.column == SEASON
        # days 1 to 7 are the first season, days 8 to 10 and today the second
        assert [income.stack_total(i) for i in range(income.count)] == [70.0, 37.0]
        assert income.headings[-1].endswith(", so far")

    def test_a_level_closes_a_season_with_its_last_day(self):
        wealth = chart("Wealth", plot_width=2 * data.POINT_PITCH)
        assert wealth.column == SEASON
        assert wealth.lines[0].values == [170.0, 215.0]       # how the 7th day closed, and now

    def test_the_lists_period_is_marked(self):
        assert chart("Wealth", list_period="Seasonal").period_columns == 7
        assert chart("Wealth", list_period="Total").period_columns == 0


class TestLegend:
    def test_a_hidden_layer_leaves_the_stack_and_the_scale(self):
        shown = chart("Income")
        hidden = chart("Income", hidden=("Goods sold",))
        assert hidden.stack_total(0) == 0.0 and shown.stack_total(0) == 10.0
        assert hidden.scale()[1] < shown.scale()[1]

    def test_a_total_cannot_be_hidden(self):
        assert not chart("Wealth", hidden=("Net worth",)).lines[0].hidden


class TestFigures:
    def test_profits_figures(self):
        figures = {f.label: f for f in chart("Profit").figures}
        assert figures["Profit in all"].value == "+115" and figures["Profit in all"].tone == 1
        assert figures["Good days"].value == "11 of 11"

    def test_net_worths_change(self):
        change = {f.label: f for f in chart("Wealth").figures}["Change"]
        # from how the first day shown closed (the opening is not shown) to now
        assert change.value == "+105" and change.note == "+95.5%"


class TestHappiness:
    @staticmethod
    def town(hours):
        return SimpleNamespace(average_happiness_history=[50.0 + k % 24 for k in range(hours)],
                               happiness_history={"Poor": [40.0] * hours})

    def test_hours_when_they_fit(self):
        happy = build_chart("Happiness", None, [], self.town(48), NOW, plot_width=400)
        assert happy.column == data.HOUR and happy.count == 48
        assert happy.lines[0].values[-1] == 50.0 + 47 % 24

    def test_a_days_average_when_they_do_not(self):
        happy = build_chart("Happiness", None, [], self.town(72), NOW, plot_width=40)
        assert happy.column == data.DAY
        # each whole day runs through the hours 0 to 23 once, from 50 to 73
        assert happy.lines[0].values[1] == pytest.approx(61.5)

    def test_no_town_hall_no_chart(self):
        assert build_chart("Population", FakeDepot(), [], None, NOW).count == 0


class TestNumbers:
    @pytest.mark.parametrize("value, text", [(950, "950"), (1200, "1.2k"), (1000, "1k"), (34_000, "34k"),
                                             (1_500_000, "1.5m"), (2.5, "2.5"), (-200, "-200")])
    def test_compact(self, value, text):
        assert compact(value) == text

    @pytest.mark.parametrize("value, text", [(12.5, "+12.50"), (-3, "-3.00"), (0.001, "0.00"), (-0.001, "0.00"),
                                             (1234, "+1,234")])
    def test_signed(self, value, text):
        assert signed(value) == text

    @pytest.mark.parametrize("span, step", [(100, 20), (1228, 200), (7, 2), (0.9, 0.2)])
    def test_nice_step(self, span, step):
        assert nice_step(span) == pytest.approx(step)


# THE VIEW

@pytest.fixture
def screen():
    pygame.init()
    return pygame.display.set_mode((1920, 1080))


@pytest.fixture
def goods(make_good):  # noqa: F811
    return [make_good(name) for name in ("Wood", "Stone")]


@pytest.fixture
def real_depot(goods):
    """A real Depot with three days in its books, a trade and a fishing day among them."""
    depot = Depot(money=1000, fee_rate=0.02, storage_capacity=100, goods=GOODS)
    for day in range(3):
        depot.money += 25
        depot.income += 25
        depot.book_labor_income(5, "Fishing")
        depot.update_income_and_expenditures()
        depot.update_wealth(goods)
        depot.update_total_stock()
        depot.update_stock_history()
    return depot


@pytest.fixture
def state(real_depot, goods):
    state = GameState()
    state.date = NOW
    state.small_font = pygame.font.Font(None, 19)
    state.game = SimpleNamespace(goods=goods, depot=real_depot, images={})
    return state


def town(days=12):
    return SimpleNamespace(population_history={"Poor": [10] * days, "Commons": [20] * days},
                           total_population_history=[30] * days,
                           average_happiness_history=[80.0] * (days * 24),
                           happiness_history={"Poor": [70.0] * (days * 24), "Commons": [85.0] * (days * 24)})


class TestChartView:
    @pytest.mark.parametrize("name", CHARTS)
    def test_every_chart_draws_from_a_real_depot(self, screen, state, real_depot, goods, name):
        state.depot_active_chart = name
        rect = pygame.Rect(0, 60, 905, 960)
        depot_view_chart.draw_depot_chart(screen, rect, None, real_depot, state, town(), goods)
        assert f"chart:{name}" in state.depot_chart_buttons
        assert {f"range:{r}" for r in data.RANGES} <= set(state.depot_chart_buttons)

    def test_a_new_depot_draws_its_empty_books(self, screen, state, goods):
        depot = Depot(money=1000, fee_rate=0.02, storage_capacity=100, goods=GOODS)
        for name in CHARTS:
            state.depot_active_chart = name
            depot_view_chart.draw_depot_chart(screen, pygame.Rect(0, 60, 905, 960), None, depot, state, town(1), goods)

    def test_a_tab_turns_to_its_chart(self, screen, state, real_depot, goods):
        depot_view_chart.draw_depot_chart(screen, pygame.Rect(0, 60, 905, 960), None, real_depot, state, town(), goods)
        assert depot_view_chart.handle_click(state, state.depot_chart_buttons["chart:Profit"].center)
        assert state.depot_active_chart == "Profit"
        assert depot_view_chart.handle_click(state, state.depot_chart_buttons["range:Season"].center)
        assert state.depot_chart_range == "Season"
        assert not depot_view_chart.handle_click(state, (5, 5))

    def test_a_name_in_the_legend_hides_and_shows_its_series(self, screen, state, real_depot, goods):
        state.depot_active_chart = "Population"
        depot_view_chart.draw_depot_chart(screen, pygame.Rect(0, 60, 905, 960), None, real_depot, state, town(), goods)
        chip = state.depot_chart_buttons["series:Poor"].center
        depot_view_chart.handle_click(state, chip)
        assert state.depot_chart_hidden["Population"] == {"Poor"}
        depot_view_chart.handle_click(state, chip)
        assert state.depot_chart_hidden["Population"] == set()

    def test_a_total_has_no_switch(self, screen, state, real_depot, goods):
        state.depot_active_chart = "Wealth"
        depot_view_chart.draw_depot_chart(screen, pygame.Rect(0, 60, 905, 960), None, real_depot, state, town(), goods)
        assert "series:Net worth" not in state.depot_chart_buttons
        assert "series:Coin" in state.depot_chart_buttons


class TestAccounts:
    def test_a_time_frame_tab_chooses_the_frame(self, screen, state, real_depot):
        depot_view.draw_depot_view(screen, None, real_depot, state, pygame.Rect(905, 60, 905, 960))
        assert set(state.depot_buttons) == {f"frame:{f}" for f in state.depot_time_frames}
        assert depot_view.handle_click(state, state.depot_buttons["frame:Yearly"].center)
        assert state.depot_time_frame == "Yearly"

    def test_a_row_opens_its_details_and_turns_the_chart(self, screen, state, real_depot):
        depot_view.draw_depot_view(screen, None, real_depot, state, pygame.Rect(905, 60, 905, 960))
        assert state.detail_panel.current_statistic == "Current Wealth"
        depot_view.handle_click(state, state.depot_plus_rects["Expenses"].center)
        assert state.detail_panel.current_statistic == "Expenses" and state.detail_panel.visible
        assert state.depot_active_chart == "Expenses"
        depot_view.handle_click(state, state.depot_plus_rects["Expenses"].center)
        assert not state.detail_panel.visible

    def test_the_wheel_scrolls_only_over_the_ledger(self, screen, state, real_depot):
        rect = pygame.Rect(905, 60, 905, 960)
        depot_view.draw_depot_view(screen, None, real_depot, state, rect)
        assert state.depot_scroll_rect is not None and rect.contains(state.depot_scroll_rect)


class TestBothSides:
    """The depot over both sides: one sheet, one title, the charts and the accounts either side of a rule."""

    def test_the_halves_meet_at_the_middle_with_room_to_spare(self, screen):
        whole = pygame.Rect(0, 60, 1810, 960)
        left, right = ledger_style.draw_depot_sheet(screen, whole)
        assert left.left == whole.left and right.right == whole.right
        content_gap = (right.left + depot_view.MARGIN) - (left.right - depot_view_chart.MARGIN)
        assert content_gap == 2 * ledger_style.SEAM
        assert left.right - depot_view_chart.MARGIN < whole.centerx < right.left + depot_view.MARGIN

    def test_both_halves_draw_on_the_one_sheet(self, screen, state, real_depot, goods):
        left, right = ledger_style.draw_depot_sheet(screen, pygame.Rect(0, 60, 1810, 960))
        depot_view_chart.draw_depot_chart(screen, left, None, real_depot, state, town(), goods, framed=False)
        depot_view.draw_depot_view(screen, None, real_depot, state, right, framed=False)
        assert all(left.contains(r) for r in state.depot_chart_buttons.values())
        assert all(right.contains(r) for r in state.depot_buttons.values())
