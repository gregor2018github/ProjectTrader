"""The health report: every check on hand-written rows, the tradability measure, and a real run end to end."""
import math

import pytest

from src.config.constants import HUNGER_THRESHOLD, MARKET_VOLUME_FACTOR_MAX, MARKET_VOLUME_FACTOR_MIN
from src.sim import TownSpec, health, sweep
from src.sim.run import load_definitions, write_run


# -- rows as the runner writes them (strings), with only the columns a check reads -----

def stamp(day: int) -> dict:
    return {"day": str(day), "year": "1500", "season": "Spring", "day_of_season": str(day % 7 + 1)}


def good_row(day: int, price: float = 10.0, stock: float = 1000.0, target: float = 1000.0, good: str = "Wood",
             outside: float = None, imported: float = 0.0, least_share: float = 1.0) -> dict:
    return {**stamp(day), "good": good, "price": repr(price), "reference": repr(price),
            "outside_price": repr(price if outside is None else outside), "stock": repr(stock),
            "target_stock": repr(target), "imported": repr(imported), "least_share": repr(least_share)}


def class_row(day: int, cls: str = "Poor", basic: float = 1.0, comfort: float = 0.9, luxury: float = 0.5,
              happiness: float = 70.0, purse: float = 100.0, count: float = 50.0) -> dict:
    return {**stamp(day), "class": cls, "fulfilment_basic": repr(basic), "fulfilment_comfort": repr(comfort),
            "fulfilment_luxury": repr(luxury), "happiness": repr(happiness), "purse": repr(purse), "count": repr(count)}


def workshop_row(day: int, ws: str = "farm", cash: float = 100.0, done: float = 1.0, capacity: float = 2.0) -> dict:
    return {**stamp(day), "workshop": ws, "cash": repr(cash), "done_yesterday": repr(done), "capacity": repr(capacity)}


def town_row(day: int, money: float = 1000.0, citizens: float = 500.0, balance: float = 0.0) -> dict:
    return {**stamp(day), "money_supply": repr(money), "citizens": repr(citizens), "market_balance": repr(balance)}


def finding(name: str, data: health.RunData) -> health.Finding:
    return next(c.run(data) for c in health.CHECKS if c.name == name)


def days(n: int, make, changes: dict = None):
    """*n* days of one kind of row, day by day, with *changes* ({day: keyword arguments}) applied to those days."""
    return [make(d, **(changes or {}).get(d, {})) for d in range(n)]


# -- the registry -------------------------------------------------------------------

def test_every_check_of_the_design_is_registered_once_and_in_order():
    names = [c.name for c in health.CHECKS]
    assert names == ["market balance", "bad numbers", "price at clamp", "price far from outside", "hunger",
                     "poorly supplied", "money supply", "population", "population trend", "happiness",
                     "workshop cash", "dead workshop", "structural shortage", "comfort band", "luxury band",
                     "goods run short"]
    assert all(c.severity in (health.FAIL, health.WARN) for c in health.CHECKS)


def test_a_finding_that_misses_has_its_checks_severity_as_status():
    assert health.Finding("x", health.WARN, False, 1, "").status == health.WARN
    assert health.Finding("x", health.FAIL, True, 0, "").status == health.OK


# -- streaks --------------------------------------------------------------------------

def test_the_longest_streak_is_the_longest_run_of_consecutive_rows():
    rows = [{"day": str(d), "v": v} for d, v in enumerate("xx.xxx.x")]
    s = health.longest_streak(rows, lambda r: r["v"] == "x")
    assert s.length == 3 and s.first["day"] == "3" and s.last["day"] == "5"
    assert health.longest_streak(rows, lambda r: False).length == 0


# -- the checks -------------------------------------------------------------------------

def test_the_market_balance_is_measured_against_the_money_supply():
    rows = [{"money_supply": "1000.0", "market_balance": "1e-12"}, {"money_supply": "0.5", "market_balance": "0.0"}]
    assert health.market_balance(rows) == pytest.approx(1e-15)
    data = health.RunData(town=[town_row(0, balance=1e-3)])
    assert finding("market balance", data).status == health.FAIL


def test_bad_numbers_are_nans_infinities_and_negative_stocks_purses_and_counts():
    clean = health.RunData(goods=[good_row(0)], population=[class_row(0)], workshops=[workshop_row(0, cash=-5.0)],
                           town=[town_row(0)])
    assert finding("bad numbers", clean).ok                  # a workshop may run into debt: its own check
    assert health.bad_numbers(health.RunData(goods=[good_row(0, stock=-1.0)]))
    assert health.bad_numbers(health.RunData(population=[class_row(0, purse=-0.5)]))
    assert not health.bad_numbers(health.RunData(goods=[good_row(0, stock=-1e-12)]))    # float dust
    nan = health.RunData(town=[{**town_row(0), "money_supply": "nan"}], workshops=[{**workshop_row(0), "cash": "inf"}])
    f = finding("bad numbers", nan)
    assert f.status == health.FAIL and f.value == 2


def test_a_price_at_its_clamp_for_more_than_two_weeks_fails(monkeypatch):
    monkeypatch.setattr(health, "CLAMP_DAYS", 14)
    empty = {d: {"stock": 0.0} for d in range(5, 20)}                       # 15 days with nothing on the market
    f = finding("price at clamp", health.RunData(goods=days(30, good_row, empty)))
    assert f.status == health.FAIL and f.value == 15 and "scarcity ceiling" in f.text
    assert health.volume_factor_of(good_row(0, stock=0.0)) == MARKET_VOLUME_FACTOR_MAX
    glut = {d: {"stock": 1e9} for d in range(5, 19)}                         # 14 days of glut: just allowed
    f = finding("price at clamp", health.RunData(goods=days(30, good_row, glut)))
    assert f.ok and f.value == 14 and "glut floor" in f.text
    assert health.volume_factor_of(good_row(0, stock=1e9)) == MARKET_VOLUME_FACTOR_MIN


def test_a_price_far_from_outside_for_too_long_is_a_warning(monkeypatch):
    monkeypatch.setattr(health, "FAR_DAYS", 28)
    dear = {d: {"price": 21.0, "outside": 10.0} for d in range(29)}
    f = finding("price far from outside", health.RunData(goods=days(40, good_row, dear)))
    assert f.status == health.WARN and f.value == 29
    cheap_but_in_band = {d: {"price": 5.0, "outside": 10.0} for d in range(40)}
    assert finding("price far from outside", health.RunData(goods=days(40, good_row, cheap_but_in_band))).ok


def test_hunger_is_a_week_running_under_the_threshold(monkeypatch):
    monkeypatch.setattr(health, "HUNGER_DAYS", 7)
    under = HUNGER_THRESHOLD - 0.01
    seven = {d: {"basic": under} for d in range(3, 10)}
    assert finding("hunger", health.RunData(population=days(20, class_row, seven))).ok
    eight = {d: {"basic": under} for d in range(3, 11)}
    f = finding("hunger", health.RunData(population=days(20, class_row, eight)))
    assert f.status == health.FAIL and f.value == 8 and f.text.startswith("Poor")


def test_the_towns_own_row_is_not_a_class():
    rows = days(20, class_row) + [{**class_row(d, basic=0.0), "class": "All"} for d in range(20)]
    assert finding("hunger", health.RunData(population=rows)).ok


def test_a_class_poorly_supplied_on_average_is_a_warning(monkeypatch):
    monkeypatch.setattr(health, "SUPPLIED_MIN", 0.9)
    rows = [class_row(d, basic=0.85) for d in range(10)] + [class_row(d, "Nobility") for d in range(10)]
    f = finding("poorly supplied", health.RunData(population=rows))
    assert f.status == health.WARN and f.value == pytest.approx(0.85) and "Poor" in f.text


def test_the_money_supply_must_stay_near_its_median_in_the_last_years(monkeypatch):
    monkeypatch.setattr(health, "RECENT_YEARS", 1)                          # the last 28 days
    steady = days(100, town_row)
    assert finding("money supply", health.RunData(town=steady)).ok
    late_boom = days(100, town_row, {d: {"money": 3500.0} for d in range(90, 100)})
    f = finding("money supply", health.RunData(town=late_boom))
    assert f.status == health.FAIL and f.value == pytest.approx(3.5)
    early_boom = days(100, town_row, {d: {"money": 9000.0} for d in range(0, 10)})
    assert finding("money supply", health.RunData(town=early_boom)).ok        # before the last years


def test_the_population_must_stay_in_its_band_of_the_first_day():
    grown = days(50, town_row, {d: {"citizens": 650.0} for d in range(30, 50)})
    f = finding("population", health.RunData(town=grown, meta={"town": {"house_capacities": [300, 400]}}))
    assert f.status == health.FAIL and f.value == pytest.approx(1.3) and "650 of 700 places" in f.text
    shrunk = days(50, town_row, {40: {"citizens": 240.0}})
    assert finding("population", health.RunData(town=shrunk)).value == pytest.approx(500 / 240)


def test_the_population_trend_is_a_least_squares_slope_per_year(monkeypatch):
    monkeypatch.setattr(health, "RECENT_YEARS", 2)
    assert health.trend_per_year([100.0] * 56) == 0.0
    rising = [100.0 + 0.1 * d for d in range(56)]                           # 2.8 a year on a mean of 102.75
    assert health.trend_per_year(rising) == pytest.approx(2.8 / 102.75)
    f = finding("population trend", health.RunData(town=[town_row(d, citizens=c) for d, c in enumerate(rising)]))
    assert f.status == health.FAIL and "+2.7" in f.text
    falling = [town_row(d, citizens=500.0 - 0.01 * d) for d in range(56)]
    assert finding("population trend", health.RunData(town=falling)).ok


def test_a_class_unhappy_or_too_happy_on_average_is_a_warning():
    rows = days(10, class_row, {d: {"happiness": 40.0} for d in range(10)}) + \
        [class_row(d, "Nobility", happiness=95.0) for d in range(10)] + [class_row(d, "Commons") for d in range(10)]
    f = finding("happiness", health.RunData(population=rows))
    assert f.status == health.WARN and f.value == 2 and "Poor 40.0 (!)" in f.text and "Commons 70.0," not in f.text


def test_a_workshop_in_debt_for_two_seasons_fails(monkeypatch):
    monkeypatch.setattr(health, "NEGATIVE_CASH_DAYS", 56)
    debt = {d: {"cash": -1.0} for d in range(10, 67)}
    f = finding("workshop cash", health.RunData(workshops=days(80, workshop_row, debt)))
    assert f.status == health.FAIL and f.value == 57 and f.text.startswith("farm")
    assert finding("workshop cash", health.RunData(workshops=days(80, workshop_row))).ok


def test_a_workshop_idle_for_over_a_year_is_dead(monkeypatch):
    monkeypatch.setattr(health, "DEAD_DAYS", 28)
    idle = {d: {"done": 0.001} for d in range(29)}                         # under 1 % of its capacity of 2
    rows = days(40, workshop_row, idle) + [workshop_row(d, "mill") for d in range(40)]
    f = finding("dead workshop", health.RunData(workshops=rows))
    assert f.status == health.WARN and f.value == 29 and "farm" in f.text
    slow_but_working = {d: {"done": 0.05} for d in range(40)}
    assert finding("dead workshop", health.RunData(workshops=days(40, workshop_row, slow_but_working))).ok


def test_a_good_imported_at_its_limit_on_most_days_is_a_structural_shortage(monkeypatch):
    monkeypatch.setattr(health, "AT_LIMIT_SHARE", 0.95)
    meta = {"definitions": {"goods": [{"name": "Wood", "import_limit": 30}, {"name": "Iron", "import_limit": 0}]}}
    wood = days(10, good_row, {d: {"imported": 29.0} for d in range(6)})   # 29 >= 0.95 × 30 on 6 of 10 days
    iron = [good_row(d, good="Iron", imported=50.0) for d in range(10)]      # no limit: never short by it
    data = health.RunData(goods=wood + iron, meta=meta)
    assert health.at_limit_shares(data) == {"Wood": 0.6}
    f = finding("structural shortage", data)
    assert f.status == health.WARN and f.value == 0.6 and "Wood 60%" in f.text


def test_the_calibration_bands_name_the_classes_outside():
    rows = [class_row(d, comfort=0.99, luxury=0.5) for d in range(5)] + \
        [class_row(d, "Nobility", comfort=0.9, luxury=0.2) for d in range(5)]
    comfort = finding("comfort band", health.RunData(population=rows))
    luxury = finding("luxury band", health.RunData(population=rows))
    assert comfort.status == health.WARN and "Poor 0.99 (!)" in comfort.text and comfort.value == 1
    assert luxury.status == health.WARN and "Nobility 0.20 (!)" in luxury.text


def test_a_short_day_is_one_some_class_bought_under_90_percent_of_its_basket(monkeypatch):
    monkeypatch.setattr(health, "SHORT_BELOW", 0.90)
    rows = [{"good": "Wood", "least_share": s} for s in ("1.0", "0.95", "0.9", "0.89")]
    assert health.short_days(rows) == {"Wood": 0.25}


def test_the_town_should_run_short_of_a_few_goods(monkeypatch):
    monkeypatch.setattr(health, "SHORT_GOODS_MIN", 2)
    one = [good_row(d, least_share=0.5) for d in range(10)] + [good_row(d, good="Iron") for d in range(10)]
    assert finding("goods run short", health.RunData(goods=one)).status == health.WARN
    two = one + [good_row(d, good="Salt", least_share=0.5) for d in range(10)]
    assert finding("goods run short", health.RunData(goods=two)).ok


# -- tradability ------------------------------------------------------------------------------

def test_a_round_trip_in_a_calm_market_costs_two_fees():
    assert health.round_trip_cost(good_row(0, 10.0), units=20, fee=2.0) == pytest.approx(4.0)


def test_a_round_trip_in_a_thin_market_costs_its_slippage_too():
    assert health.round_trip_cost(good_row(0, 10.0, stock=100.0, target=100.0), units=20, fee=2.0) > 4.0


def test_tradability_measures_the_window_range_against_the_price():
    flat = [good_row(d, 10.0) for d in range(40)]
    swing = [good_row(d, 10.0 if d % 2 else 12.0, good="Wine") for d in range(40)]
    result = {t.good: t for t in health.tradability(flat + swing, window=30, lot_value=200.0, fee=2.0)}
    assert result["Wood"].median_range == 0.0 and result["Wood"].share_worth_it == 0.0
    assert result["Wood"].days == 11
    assert 2.0 / 12.0 <= result["Wine"].median_range <= 2.0 / 10.0            # a 2g range on 10g or 12g
    assert result["Wine"].share_worth_it == 1.0                                 # 2g × 17 or 20 units > 2 × 4g


def test_a_lot_is_whole_units_worth_its_value_and_at_least_one():
    assert health.lot_units(10.0, value=100.0) == 10
    assert health.lot_units(3.0, value=100.0) == 33
    assert health.lot_units(400.0, value=100.0) == 1


# -- a real run, end to end (the game's definitions on a small town, no map) ----------------

TOWN = TownSpec([6, 8, 4, 12, 5, 7, 9, 3, 10])
DEFINITIONS, SCENARIO = load_definitions()


@pytest.fixture(scope="module")
def two_runs(tmp_path_factory):
    out = str(tmp_path_factory.mktemp("sweep"))
    return out, [sweep.run_seed(seed, 0.5, out, DEFINITIONS, TOWN, SCENARIO, reuse=False) for seed in (1, 2)]


def test_every_check_runs_on_a_real_run_and_its_books_are_sound(two_runs):
    out, results = two_runs
    for r in results:
        assert [f.check for f in r.findings] == [c.name for c in health.CHECKS]
        by_name = {f.check: f for f in r.findings}
        assert by_name["market balance"].ok and by_name["bad numbers"].ok
        assert all(math.isfinite(f.value) for f in r.findings)
        assert len(r.tradability) == len(DEFINITIONS.goods)
    assert health.report(sweep.seed_dir(out, 1), show_tradability=False) in (0, 1)


def test_reusing_a_run_checks_it_again_without_simulating(two_runs):
    out, results = two_runs
    again = sweep.run_seed(1, 0.5, out, DEFINITIONS, TOWN, SCENARIO, reuse=True)
    assert again.seconds == 0.0
    assert [f.text for f in again.findings] == [f.text for f in results[0].findings]


def test_the_sweeps_table_counts_every_seed_once_per_check(two_runs, tmp_path):
    _, results = two_runs
    rows = sweep.tally(results)
    assert len(rows) == len(health.CHECKS)
    assert all(sum(r.counts.values()) == 2 for r in rows)
    text = sweep.summary(results, 0.5, markdown=True)
    assert text.startswith("# Health over 2 seeds x 0.5 years (seeds 1-2)")
    assert "| market balance |" in text and "## Per seed" in text and "## Tradability" in text
    path = tmp_path / "summary.csv"
    sweep.write_csv(str(path), results)
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1 + 2 * len(health.CHECKS)


def test_the_worst_seed_is_one_that_missed():
    check = next(c for c in health.CHECKS if c.name == "hunger")
    findings = {1: health.Finding("hunger", health.FAIL, True, 7, ""),
                2: health.Finding("hunger", health.FAIL, False, 8, "")}
    results = [sweep.SeedResult(s, [findings[s] if c is check else health.Finding(c.name, c.severity, True, 0, "")
                                    for c in health.CHECKS], [], 0.0) for s in (1, 2)]
    row = next(r for r in sweep.tally(results) if r.check is check)
    assert row.worst_seed == 2 and row.counts == {health.OK: 1, health.WARN: 0, health.FAIL: 1}
