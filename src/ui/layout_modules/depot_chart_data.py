"""What the depot's charts show, worked out without pygame: each chart's columns, series, axis
marks, headline figures and the lines of its tooltip.

The depot keeps its books as a snapshot taken at every midnight (``Depot.update_wealth``,
``update_income_and_expenditures``...), so a history's last entry is how yesterday closed and its
first one how the game opened. Every series here is dated backwards from today, and today itself
is added from the live figures (``ChartData.partial``: "so far"). Days before the calendar's
first one (the town's presimulated days, the opening snapshot) are left out.

A chart covers a range (``RANGES``: the last season, the last year, or everything). When it has
more days than its plot has room for as columns (``max_columns``), they are summed (a flow) or
closed up (a level) into seasons; happiness, kept by the hour, is averaged into days first.

``build_chart(name, ...)`` returns a ``ChartData``; ``depot_view_chart.py`` draws it.
"""

import datetime
import math
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from ...sim.calendar import (
    DAYS_PER_SEASON, DAYS_PER_YEAR, EPOCH, PERIOD_DAYS, SEASON_ABBREVIATIONS, SEASONS, day_number, format_date,
    game_date, season_number,
)

Colour = Tuple[int, int, int]

# The charts, in the order of their tabs, grouped: the player's purse, their books, the town
CHART_GROUPS: Tuple[Tuple[str, ...], ...] = (
    ("Wealth", "Money", "Stock", "Houses"),
    ("Income", "Expenses", "Profit"),
    ("Population", "Happiness"),
)
CHARTS: Tuple[str, ...] = tuple(name for group in CHART_GROUPS for name in group)
TAB_LABELS: Dict[str, str] = {"Houses": "Property", "Population": "Townsfolk"}

TITLES: Dict[str, str] = {
    "Wealth": "Net Worth",
    "Money": "Coin in Hand",
    "Stock": "Goods in Store",
    "Houses": "Property",
    "Income": "Income by Source",
    "Expenses": "Expenses by Kind",
    "Profit": "Profit and Loss",
    "Population": "The Townsfolk",
    "Happiness": "The Town's Contentment",
}

# How far back a chart looks (None: since the game began)
RANGES: Dict[str, Optional[int]] = {"Season": DAYS_PER_SEASON, "Year": DAYS_PER_YEAR, "All": None}
DEFAULT_RANGE = "All"

# Inks for what has no colour of its own, always given out in this order and each kept to its
# entity; checked for colour-blind readers against the parchment: azurite, ochre, murex,
# malachite, vermilion, verdigris, olive, madder
INKS: Tuple[Colour, ...] = (
    (43, 95, 176), (176, 122, 18), (123, 63, 158), (46, 128, 80),
    (192, 69, 42), (14, 134, 160), (110, 138, 30), (176, 58, 128),
)
AZURITE, OCHRE, MUREX, MALACHITE, VERMILION, VERDIGRIS, OLIVE, MADDER = INKS
INK = (44, 32, 22)                      # a total's line, in the ink the page is written in
GAIN, LOSS = (46, 118, 66), (164, 52, 40)
CLASS_COLOURS: Dict[str, Colour] = {
    "Poor": (180, 60, 60), "Commons": (128, 120, 108), "Middling Sort": (70, 130, 190), "Nobility": (110, 60, 160),
}

# The kinds of chart
AREA = "area"                           # stacked areas of a level (wealth, population)
LINES = "lines"                         # lines, none stacked (happiness)
BARS = "bars"                           # stacked bars of how much there was each day
SIGNED = "signed"                       # bars up for a gain, down for a loss

DAY, HOUR, SEASON = "day", "hour", "season"     # what one column is
BAR_PITCH = 6                           # the fewest pixels a column of bars may have
POINT_PITCH = 2                         # and a point on a line or an area


@dataclass
class Series:
    """One thing a chart shows: stacked as a layer, or drawn over the layers as a line."""
    name: str
    colour: Colour
    values: List[float]
    dashed: bool = False
    thick: bool = False
    hidden: bool = False                # switched off in the legend
    fixed: bool = False                 # cannot be switched off (a total)


@dataclass
class Figure:
    """A headline figure over the plot: what it is, its value, and a word under it (``tone`` +1 a
    gain, -1 a loss, 0 neither)."""
    label: str
    value: str
    note: str = ""
    tone: int = 0


@dataclass
class ChartData:
    name: str
    title: str
    kind: str
    unit: str                                       # "coins", "units", "people" or "points"
    column: str = DAY                               # DAY, HOUR or SEASON
    dates: List[datetime.date] = field(default_factory=list)
    headings: List[str] = field(default_factory=list)       # each column's tooltip heading
    layers: List[Series] = field(default_factory=list)
    lines: List[Series] = field(default_factory=list)
    partial: bool = False                           # the last column is today, so far
    figures: List[Figure] = field(default_factory=list)
    ticks: List[Tuple[int, str, bool]] = field(default_factory=list)   # (column, label, a year begins)
    extra: List[List[Tuple[str, str]]] = field(default_factory=list)   # more tooltip lines per column
    fixed_scale: Optional[Tuple[float, float]] = None
    period_columns: int = 0                         # how many last columns the list's period covers
    period_name: str = ""
    total_label: str = "Total"
    empty_text: str = "Nothing written in the books yet"

    @property
    def count(self) -> int:
        return len(self.dates)

    def visible_layers(self) -> List[Series]:
        return [s for s in self.layers if not s.hidden]

    def visible_lines(self) -> List[Series]:
        return [s for s in self.lines if not s.hidden]

    def all_series(self) -> List[Series]:
        return self.layers + self.lines

    def stack_total(self, i: int) -> float:
        return sum(s.values[i] for s in self.visible_layers())

    def scale(self) -> Tuple[float, float]:
        """The lowest and highest value the plot must hold (always taking in nought)."""
        if self.fixed_scale:
            return self.fixed_scale
        lo = hi = 0.0
        if self.kind in (AREA, BARS):
            hi = max((self.stack_total(i) for i in range(self.count)), default=0.0)
        else:
            for s in self.visible_layers():
                hi, lo = max(hi, max(s.values, default=0.0)), min(lo, min(s.values, default=0.0))
        for s in self.visible_lines():
            hi, lo = max(hi, max(s.values, default=0.0)), min(lo, min(s.values, default=0.0))
        if hi - lo < 1e-9:
            hi = lo + 1.0
        return lo, hi

    def tooltip(self, i: int) -> List[Tuple[Optional[Colour], str, float]]:
        """The column's values, each with the colour of its mark (None for the total)."""
        rows = [(s.colour, s.name, s.values[i]) for s in self.all_series()
                if not s.hidden and not (self.kind == BARS and abs(s.values[i]) < 1e-9)]
        # A sum of the layers, unless the chart draws its own total (net worth)
        if self.kind in (AREA, BARS) and len(self.visible_layers()) > 1 and not any(s.fixed for s in self.lines):
            rows.append((None, self.total_label, self.stack_total(i)))
        return rows


# ----------------------------------------------------------------------
# Numbers as the page writes them
# ----------------------------------------------------------------------

def amount(value: float, unit: str = "coins") -> str:
    """A figure for a tooltip or a headline: coins to two places while small, whole otherwise."""
    if unit == "points":
        return f"{value:.1f}"
    if unit != "coins" or abs(value) >= 100:
        return f"{value:,.0f}"
    return f"{value:,.2f}"


def signed(value: float, unit: str = "coins") -> str:
    """A change, with its sign: +12.50, -3, and nought plain."""
    text = amount(value, unit)
    if text.lstrip("-").strip("0.,") == "":
        return text.lstrip("-")
    return text if value < 0 else "+" + text


def compact(value: float) -> str:
    """An axis label: 950, 1.2k, 34k, 1.5m."""
    size = abs(value)
    if size >= 1_000_000:
        text = f"{value / 1_000_000:.1f}m"
    elif size >= 10_000:
        text = f"{value / 1000:.0f}k"
    elif size >= 1000:
        text = f"{value / 1000:.1f}k"
    elif size >= 10 or value == int(value):
        text = f"{value:.0f}"
    else:
        text = f"{value:.1f}"
    return text.replace(".0k", "k").replace(".0m", "m")


def nice_step(span: float, lines: int = 5) -> float:
    """A round step (1, 2 or 5 times a power of ten) giving about *lines* grid lines over *span*."""
    if span <= 0:
        return 1.0
    raw = span / lines
    magnitude = 10 ** math.floor(math.log10(raw))
    for nice in (1, 2, 5):
        if raw <= nice * magnitude * 1.25:
            return nice * magnitude
    return 10 * magnitude


# ----------------------------------------------------------------------
# Lining the histories up with the calendar
# ----------------------------------------------------------------------

def _dates_back(n: int, last: datetime.date) -> List[datetime.date]:
    """*n* days running up to *last*."""
    return [last - datetime.timedelta(days=n - 1 - k) for k in range(n)]


def _aligned(history: Optional[Sequence[float]], n: int, pad_first: bool = False) -> List[float]:
    """A history cut or padded at its front to *n* entries, so its last one stays the newest; padded
    with noughts, or with its first value (a level an older save began keeping later)."""
    history = list(history or [])
    if len(history) >= n:
        return history[len(history) - n:]
    pad = history[0] if pad_first and history else 0.0
    return [pad] * (n - len(history)) + history


@dataclass
class _Daily:
    """A chart's days before it is cut to its range and made into columns."""
    dates: List[datetime.date]
    layers: List[Series]
    lines: List[Series] = field(default_factory=list)
    flow: bool = False                              # summed into seasons, rather than closed up
    partial: bool = True
    extra: List[List[Tuple[str, str]]] = field(default_factory=list)

    def clip(self, first: datetime.date) -> None:
        """Leave out the days before *first*."""
        start = next((i for i, d in enumerate(self.dates) if d >= first), len(self.dates))
        self.dates = self.dates[start:]
        for s in self.layers + self.lines:
            s.values = s.values[start:]
        self.extra = self.extra[start:]


def _snapshots(now: datetime.datetime, histories: Sequence[Sequence[float]],
               live: Sequence[float]) -> Tuple[List[datetime.date], List[List[float]]]:
    """Midnight snapshots, lined up to the first history (the last being how yesterday closed),
    with today's live values after them."""
    n = len(histories[0])
    dates = _dates_back(n, now.date() - datetime.timedelta(days=1)) + [now.date()]
    return dates, [_aligned(h, n, pad_first=True) + [v] for h, v in zip(histories, live)]


# ----------------------------------------------------------------------
# Building a chart
# ----------------------------------------------------------------------

def build_chart(name: str, depot: Any, goods: Sequence[Any], population: Any, now: datetime.datetime,
                range_name: str = DEFAULT_RANGE, hidden: Sequence[str] = (), plot_width: int = 700,
                list_period: Optional[str] = None) -> ChartData:
    """Chart *name* as it stands at *now*, over *range_name*, with the series named in *hidden*
    switched off, fitted to a plot *plot_width* pixels wide (a bar wants ``BAR_PITCH`` of them, a
    point on a line ``POINT_PITCH``). *list_period* is the depot list's time frame, whose last days
    a daily chart marks."""
    if name not in CHARTS:
        name = CHARTS[0]
    chart = ChartData(name=name, title=TITLES[name], kind=_KINDS[name], unit=_UNITS[name])
    max_columns = max(2, plot_width // (BAR_PITCH if chart.kind in (BARS, SIGNED) else POINT_PITCH))
    if name in ("Population", "Happiness") and population is None:
        chart.empty_text = "No word from the town hall"
        return chart
    if name == "Happiness":
        _happiness(chart, population, now, range_name, hidden, max_columns, list_period)
        return chart

    daily = _BUILDERS[name](depot, goods, population, now)
    daily.clip(datetime.date.fromordinal(max(EPOCH.toordinal(), _range_start(now, range_name))))
    if not daily.dates:
        return chart
    if name == "Profit":
        _running_total(daily)
    # Only what was there in the range earns a place in the legend
    kept = [s for s in daily.layers if any(abs(v) > 1e-9 for v in s.values)]
    daily.layers = kept or daily.layers[:1]
    for s in daily.layers + daily.lines:
        s.hidden = s.name in hidden and not s.fixed

    chart.layers, chart.lines, chart.partial = daily.layers, daily.lines, daily.partial
    if len(daily.dates) > max_columns:
        _by_season(chart, daily.dates, daily.flow)
    else:
        chart.dates = daily.dates
        chart.headings = [_heading(d, now.date(), daily.partial) for d in daily.dates]
        chart.extra = daily.extra
        chart.ticks = _day_ticks(daily.dates)
        _mark_period(chart, list_period, now.date())
    if name == "Profit" and chart.count > 1:
        values = chart.layers[0].values
        chart.lines = [Series("Average", INK, [sum(values) / len(values)] * len(values), dashed=True, fixed=True)]
    chart.figures = _FIGURES[name](chart, depot, goods)
    return chart


def _range_start(now: datetime.datetime, range_name: str) -> int:
    days = RANGES.get(range_name)
    if days is None:
        return 0
    return (now.date() - datetime.timedelta(days=days - 1)).toordinal()


def _heading(day: datetime.date, today: datetime.date, partial: bool) -> str:
    return format_date(day) + (", so far" if partial and day == today else "")


def _day_ticks(dates: List[datetime.date]) -> List[Tuple[int, str, bool]]:
    """Every day on a short chart; where each season begins on a longer one, a year by its number."""
    ticks = []
    for i, day in enumerate(dates):
        d = game_date(day)
        year = d.day == 1 and d.season == 0
        if len(dates) <= DAYS_PER_SEASON + 3:
            ticks.append((i, f"{d.day} {SEASON_ABBREVIATIONS[d.season]}", year))
        elif d.day == 1:
            ticks.append((i, str(d.year) if year else SEASONS[d.season], year))
    return ticks


def _by_season(chart: ChartData, dates: List[datetime.date], flow: bool) -> None:
    """The days summed (a flow) or closed up (a level) into seasons."""
    groups: List[List[int]] = []
    last = None
    for i, day in enumerate(dates):
        if season_number(day) != last:
            groups.append([])
            last = season_number(day)
        groups[-1].append(i)
    for s in chart.all_series():
        s.values = [sum(s.values[i] for i in g) if flow else s.values[g[-1]] for g in groups]
    chart.column = SEASON
    chart.dates = [dates[g[0]] for g in groups]
    chart.extra = []
    chart.headings, chart.ticks = [], []
    many = len(groups) > 16
    for n, g in enumerate(groups):
        d = game_date(dates[g[0]])
        so_far = ", so far" if chart.partial and n == len(groups) - 1 else ""
        chart.headings.append(f"{SEASONS[d.season]} {d.year}{so_far}")
        if d.season == 0:
            chart.ticks.append((n, str(d.year), True))
        elif not many:
            chart.ticks.append((n, SEASON_ABBREVIATIONS[d.season], False))


def _mark_period(chart: ChartData, list_period: Optional[str], today: datetime.date) -> None:
    """How many of the last columns the depot list's time frame adds up over."""
    days = PERIOD_DAYS.get(list_period) if list_period else None
    if not days or not chart.dates or chart.dates[-1] != today:
        return
    first = today - datetime.timedelta(days=days - 1)
    chart.period_columns = sum(1 for d in chart.dates if d >= first)
    chart.period_name = list_period


# ----------------------------------------------------------------------
# Each chart's days
# ----------------------------------------------------------------------

def _goods_value(depot: Any, goods: Sequence[Any]) -> float:
    return sum(depot.good_stock.get(g.name, 0) * g.price for g in goods)


def _net_worth(depot: Any, goods: Sequence[Any]) -> float:
    return depot.money + _goods_value(depot, goods) + depot.get_property_value() - depot.outstanding_loans()


def _wealth_columns(depot, goods, now) -> Tuple[List[datetime.date], List[List[float]]]:
    """Net worth, coin, goods' worth, property and loans, every midnight and now."""
    dates, (net, money, prop, loans) = _snapshots(
        now, (depot.wealth, depot.money_history, depot.property_value_history, depot.loan_history),
        (_net_worth(depot, goods), depot.money, depot.get_property_value(), depot.outstanding_loans()))
    held = [max(0.0, w - m - p + l) for w, m, p, l in zip(net, money, prop, loans)]
    return dates, [net, money, held, prop, loans]


def _wealth(depot, goods, population, now) -> _Daily:
    dates, (net, money, held, prop, loans) = _wealth_columns(depot, goods, now)
    lines = [Series("Net worth", INK, net, thick=True, fixed=True)]
    if any(v > 0 for v in loans):
        lines.append(Series("Loans", VERMILION, loans, dashed=True))
    return _Daily(dates, [Series("Coin", OCHRE, money), Series("Goods", MALACHITE, held),
                          Series("Property", MUREX, prop)], lines)


def _money(depot, goods, population, now) -> _Daily:
    dates, (money, loans) = _snapshots(now, (depot.money_history, depot.loan_history),
                                       (depot.money, depot.outstanding_loans()))
    lines = [Series("Loans", VERMILION, loans, dashed=True)] if any(v > 0 for v in loans) else []
    return _Daily(dates, [Series("Coin", OCHRE, money)], lines)


def _houses(depot, goods, population, now) -> _Daily:
    dates, (value, count, room) = _snapshots(
        now, (depot.property_value_history, depot.house_history, depot.storage_capacity_history),
        (depot.get_property_value(), depot.get_property_count(), depot.storage_capacity))
    extra = [[("Buildings", f"{c:,.0f}"), ("Storage", f"{r:,.0f} units")] for c, r in zip(count, room)]
    return _Daily(dates, [Series("Property value", MUREX, value)], extra=extra)


def _stock(depot, goods, population, now) -> _Daily:
    held = [g for g in goods if g.name in depot.stock_history]
    n = max((len(depot.stock_history[g.name]) for g in held), default=1)
    histories = [_aligned(depot.stock_history[g.name], n) for g in held] or [[0] * n]
    dates, columns = _snapshots(now, histories, [depot.good_stock.get(g.name, 0) for g in held] or [0])
    layers = [Series(g.name, tuple(g.color), [float(v) for v in values]) for g, values in zip(held, columns)]
    return _Daily(dates, layers)


def _flows(now: datetime.datetime, total: Sequence[float],
           parts: List[Tuple[str, Colour, Sequence[float], float]], live_total: float,
           rest: str, rest_colour: Colour) -> _Daily:
    """A day's flow split into parts (each a history and today's figure so far), what the parts do
    not account for going to *rest*. A flow history's first entry is the opening's nought."""
    n = len(total)
    dates = _dates_back(n - 1, now.date() - datetime.timedelta(days=1)) + [now.date()]
    totals = list(total[1:]) + [live_total]
    layers = [Series(name, colour, _aligned(history, n)[1:] + [live]) for name, colour, history, live in parts]
    rest_values = [max(0.0, t - sum(s.values[i] for s in layers)) for i, t in enumerate(totals)]
    return _Daily(dates, [Series(rest, rest_colour, rest_values)] + layers, flow=True)


# The expenses' kinds: (name, ink, the depot's histories, its counters for today)
_EXPENSE_PARTS = (
    ("Cost of living", AZURITE, ("cost_of_living_expenditure_history",), ("cost_of_living_expenditures",)),
    ("Market fees", VERDIGRIS, ("transaction_expenditure_history",), ("transaction_expenditures",)),
    ("Licences", MUREX, ("license_expenditure_history",), ("license_expenditures",)),
    ("Donations", OCHRE, ("donation_expenditure_history",), ("donation_expenditures",)),
    ("Loans", VERMILION, ("loan_expenditure_history", "overdraft_expenditure_history"),
     ("loan_expenditures", "overdraft_expenditures")),
    ("Property", MADDER, ("property_expenditure_history",), ("property_expenditures",)),
    ("Miscellaneous", OLIVE, ("miscellaneous_expenditure_history",), ("miscellaneous_expenditures",)),
)


def _expenses(depot, goods, population, now) -> _Daily:
    n = len(depot.expenditure_history)
    parts = []
    for name, colour, histories, counters in _EXPENSE_PARTS:
        summed = [sum(values) for values in zip(*(_aligned(getattr(depot, h, None), n) for h in histories))]
        parts.append((name, colour, summed, sum(getattr(depot, c, 0.0) or 0.0 for c in counters)))
    return _flows(now, depot.expenditure_history, parts, depot.expenditures, "Goods bought", MALACHITE)


def _income(depot, goods, population, now) -> _Daily:
    inks = [ink for ink in INKS if ink != MALACHITE]           # malachite is the goods sold's
    parts = [(name, inks[i % len(inks)], depot.labor_income_history[name], depot.labor_income.get(name, 0.0))
             for i, name in enumerate(sorted(depot.labor_income_history))]
    return _flows(now, depot.income_history, parts, depot.income, "Goods sold", MALACHITE)


def _profit(depot, goods, population, now) -> _Daily:
    """How much better each day closed than the one before, and what that came from."""
    dates, (net, money, held, prop, loans) = _wealth_columns(depot, goods, now)
    diff = lambda values, k: values[k] - values[k - 1]
    extra = [[("Coin", signed(diff(money, k))), ("Goods' worth", signed(diff(held, k))),
              ("Property", signed(diff(prop, k))), ("Loans", signed(-diff(loans, k)))]
             for k in range(1, len(net))]
    for rows in extra:                                         # only what moved
        rows[:] = [row for row in rows if row[1] not in ("0.00", "0")]
    values = [diff(net, k) for k in range(1, len(net))]
    return _Daily(dates[1:], [Series("Profit", GAIN, values, fixed=True)], flow=True, extra=extra)


def _running_total(daily: _Daily) -> None:
    running = 0.0
    for value, rows in zip(daily.layers[0].values, daily.extra):
        running += value
        rows.append(("Running total", signed(running)))


def _population(depot, goods, population, now) -> _Daily:
    """Each class's head count, recorded at every midnight, the last today's."""
    history = population.population_history
    names = [c for c in CLASS_COLOURS if c in history] + [c for c in history if c not in CLASS_COLOURS]
    n = max((len(history[c]) for c in names), default=0)
    layers = [Series(c, CLASS_COLOURS.get(c, INKS[i % len(INKS)]), [float(v) for v in _aligned(history[c], n)])
              for i, c in enumerate(names)]
    return _Daily(_dates_back(n, now.date()), layers, partial=False)


def _happiness(chart: ChartData, population: Any, now: datetime.datetime, range_name: str,
               hidden: Sequence[str], max_columns: int, list_period: Optional[str]) -> None:
    """The town's and each class's happiness by the hour, or a day's average when the hours do not
    fit, or a season's close when the days do not."""
    chart.fixed_scale = (0.0, 100.0)
    histories = [("Town", INK, population.average_happiness_history)] + [
        (c, CLASS_COLOURS.get(c, INKS[i % len(INKS)]), h) for i, (c, h) in enumerate(population.happiness_history.items())]
    n = len(histories[0][2])
    stamp = now.replace(minute=0, second=0, microsecond=0)
    moments = [stamp - datetime.timedelta(hours=n - 1 - k) for k in range(n)]
    first_day = max(EPOCH.toordinal(), _range_start(now, range_name))
    first = next((k for k, m in enumerate(moments) if m.date().toordinal() >= first_day), n)
    moments = moments[first:]
    if not moments:
        return
    chart.lines = [Series(name, colour, _aligned(h, n)[first:], thick=name == "Town", fixed=name == "Town")
                   for name, colour, h in histories]
    for s in chart.lines:
        s.hidden = s.name in hidden and not s.fixed
    if len(moments) <= max_columns:
        chart.column = HOUR
        chart.dates = [m.date() for m in moments]
        chart.headings = [f"{format_date(m)}  {m.hour:02d}:00" for m in moments]
        chart.ticks = [(k, f"{game_date(m).day} {SEASON_ABBREVIATIONS[game_date(m).season]}", False)
                       for k, m in enumerate(moments) if m.hour == 0]
        _mark_period(chart, list_period, now.date())
    else:
        by_day: Dict[datetime.date, List[int]] = {}
        for k, m in enumerate(moments):
            by_day.setdefault(m.date(), []).append(k)
        days = sorted(by_day)
        for s in chart.lines:
            s.values = [sum(s.values[k] for k in by_day[d]) / len(by_day[d]) for d in days]
        if len(days) > max_columns:
            _by_season(chart, days, flow=False)
        else:
            chart.dates = days
            chart.headings = [format_date(d) + (", the day's average" if d != now.date() else ", so far") for d in days]
            chart.ticks = _day_ticks(days)
            _mark_period(chart, list_period, now.date())
    chart.figures = _happiness_figures(chart)


# ----------------------------------------------------------------------
# The headline figures over the plot
# ----------------------------------------------------------------------

def _change(first: float, last: float, unit: str) -> Figure:
    diff = last - first
    note = f"{diff / first * 100:+.1f}%" if first > 0 and unit != "points" else ("points" if unit == "points" else "")
    return Figure("Change", signed(diff, unit), note, (diff > 1e-9) - (diff < -1e-9))


def _span(chart: ChartData) -> str:
    """The range shown, in words, for a figure's note."""
    if chart.column == SEASON:
        return f"over {chart.count} seasons"
    days = (chart.dates[-1] - chart.dates[0]).days + 1
    return f"over {days} day{'s' if days != 1 else ''}"


def _when(chart: ChartData, i: int) -> str:
    return chart.headings[i].replace(", so far", " (today)") if i < len(chart.headings) else ""


def _extremes(values: List[float], chart: ChartData, unit: str) -> List[Figure]:
    hi = max(range(len(values)), key=lambda i: values[i])
    lo = min(range(len(values)), key=lambda i: values[i])
    return [Figure("Highest", amount(values[hi], unit), _when(chart, hi)),
            Figure("Lowest", amount(values[lo], unit), _when(chart, lo))]


def _wealth_figures(chart: ChartData, depot, goods) -> List[Figure]:
    net = chart.lines[0].values
    return [Figure("Net worth", amount(net[-1]), "now"), _change(net[0], net[-1], "coins")] + _extremes(net, chart, "coins")


def _money_figures(chart: ChartData, depot, goods) -> List[Figure]:
    coin = chart.layers[0].values
    loans = depot.outstanding_loans()
    return [Figure("Coin in hand", amount(coin[-1]), "now"), _change(coin[0], coin[-1], "coins"),
            Figure("Loans owed", amount(loans), "outstanding" if loans else "none", -1 if loans else 0),
            _extremes(coin, chart, "coins")[1]]


def _houses_figures(chart: ChartData, depot, goods) -> List[Figure]:
    value = chart.layers[0].values
    return [Figure("Buildings", f"{depot.get_property_count():,}", "owned"),
            Figure("Property value", amount(value[-1]), "as bought"),
            Figure("Storage", f"{depot.storage_capacity:,}", "units of room"),
            _change(value[0], value[-1], "coins")]


def _stock_figures(chart: ChartData, depot, goods) -> List[Figure]:
    held = {g.name: depot.good_stock.get(g.name, 0) for g in goods}
    total = sum(held.values())
    capacity = depot.total_capacity()
    most = max(held, key=held.get) if total else None
    return [Figure("In store", f"{total:,}", f"of {capacity:,} units" if capacity else "units"),
            Figure("Worth", amount(_goods_value(depot, goods)), "at today's prices"),
            Figure("Most held", most or "-", f"{held[most]:,} units" if most else "nothing stored"),
            Figure("Kinds of goods", f"{sum(1 for v in held.values() if v)}", "in store")]


def _flow_figures(word: str, tone: int) -> Callable:
    def figures(chart: ChartData, depot, goods) -> List[Figure]:
        totals = [chart.stack_total(i) for i in range(chart.count)]
        whole = sum(totals)
        best = max(range(len(totals)), key=lambda i: totals[i])
        shares = sorted(((sum(s.values), s.name) for s in chart.visible_layers()), reverse=True)
        main = shares[0] if shares and shares[0][0] > 0 else None
        return [Figure(f"{word} in all", amount(whole), _span(chart), tone if whole else 0),
                Figure(f"Per {chart.column}", amount(whole / max(1, len(totals))), "on average"),
                Figure(f"Most in a {chart.column}", amount(totals[best]), _when(chart, best) if totals[best] else ""),
                Figure("Mostly", main[1] if main else "-", f"{main[0] / whole * 100:.0f}% of it" if main else "nothing yet")]
    return figures


def _profit_figures(chart: ChartData, depot, goods) -> List[Figure]:
    values = chart.layers[0].values
    whole = sum(values)
    best = max(range(len(values)), key=lambda i: values[i])
    worst = min(range(len(values)), key=lambda i: values[i])
    return [Figure("Profit in all", signed(whole), _span(chart), (whole > 0) - (whole < 0)),
            Figure(f"Good {chart.column}s", f"{sum(1 for v in values if v > 0)} of {len(values)}", "closed with a gain"),
            Figure(f"Best {chart.column}", signed(values[best]), _when(chart, best), 1 if values[best] > 0 else 0),
            Figure(f"Worst {chart.column}", signed(values[worst]), _when(chart, worst), -1 if values[worst] < 0 else 0)]


def _population_figures(chart: ChartData, depot, goods) -> List[Figure]:
    totals = [sum(s.values[i] for s in chart.layers) for i in range(chart.count)]
    largest = max(chart.layers, key=lambda s: s.values[-1])
    share = largest.values[-1] / totals[-1] * 100 if totals[-1] else 0
    return [Figure("Townsfolk", f"{totals[-1]:,.0f}", "living in town"), _change(totals[0], totals[-1], "people"),
            Figure("Largest class", largest.name, f"{share:.0f}% of the town"), _extremes(totals, chart, "people")[0]]


def _happiness_figures(chart: ChartData) -> List[Figure]:
    if not chart.count:
        return []
    town = chart.lines[0].values
    figures = [Figure("Town", f"{town[-1]:.1f}", "out of 100"), _change(town[0], town[-1], "points")]
    classes = chart.lines[1:]
    if classes:
        happy = max(classes, key=lambda s: s.values[-1])
        sad = min(classes, key=lambda s: s.values[-1])
        figures.append(Figure("Happiest", happy.name, f"{happy.values[-1]:.1f}", 1))
        figures.append(Figure("Least content", sad.name, f"{sad.values[-1]:.1f}", -1 if sad.values[-1] < 50 else 0))
    return figures


_BUILDERS = {
    "Wealth": _wealth, "Money": _money, "Stock": _stock, "Houses": _houses, "Income": _income,
    "Expenses": _expenses, "Profit": _profit, "Population": _population,
}
_KINDS = {
    "Wealth": AREA, "Money": AREA, "Stock": BARS, "Houses": AREA, "Income": BARS, "Expenses": BARS,
    "Profit": SIGNED, "Population": AREA, "Happiness": LINES,
}
_UNITS = {
    "Wealth": "coins", "Money": "coins", "Stock": "units", "Houses": "coins", "Income": "coins",
    "Expenses": "coins", "Profit": "coins", "Population": "people", "Happiness": "points",
}
_FIGURES = {
    "Wealth": _wealth_figures, "Money": _money_figures, "Stock": _stock_figures, "Houses": _houses_figures,
    "Income": _flow_figures("Earned", 1), "Expenses": _flow_figures("Spent", -1), "Profit": _profit_figures,
    "Population": _population_figures,
}
