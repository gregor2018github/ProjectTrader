"""The depot's charts, the left half of the depot's full view: a counting-house sheet with the
chart's title on its tablet, a tab per chart, four headline figures, and the plot on a paler leaf.

What a chart shows is worked out in ``depot_chart_data.py`` (no pygame); this draws it:
- the plot, with its scale on the left, the calendar under it (days, or seasons and years) and
  the depot list's time frame shaded at its right end, so both halves speak of the same days;
- stacked areas for a level (net worth as coin, goods and property under its own line), stacked
  bars for what came and went each day, bars up and down round nought for profit, lines for
  the town's contentment; today's column is "so far", its bar drawn paler;
- a legend whose names hide or show their series on a click and bring it forward on hover;
- the range (the last season, year, or all of it) at the plot's top right;
- the column under the pointer marked, and a parchment note with all of that day's figures.

The plot is drawn into a layer kept until the figures, the size or what is in focus change; only
the hover is drawn every frame. What can be clicked is filed in ``game_state.depot_chart_buttons``
as ``"chart:<name>"``, ``"range:<name>"`` or ``"series:<name>"`` and handled by ``handle_click``.
"""

import math
from typing import TYPE_CHECKING, Dict, List, Optional, Sequence, Tuple

import pygame

from . import ledger_style as style
from .depot_chart_data import (
    AREA, BARS, CHART_GROUPS, CHARTS, DEFAULT_RANGE, GAIN, LINES, LOSS, RANGES, SEASON, SIGNED, TAB_LABELS,
    TITLES, ChartData, Series, amount, build_chart, compact, nice_step, signed,
)
from ...sim.calendar import price_tick_number

if TYPE_CHECKING:
    from ...game_state import GameState
    from ...models.depot import Depot
    from ...models.good import Good
    from ...models.population import PopulationManager

Colour = Tuple[int, int, int]

# Where things go on the sheet, from its top left
MARGIN = 52                     # clear of the frame's band
TABS_TOP, TAB_H, TAB_GAP, GROUP_GAP = 100, 34, 5, 16
FIGURES_TOP, FIGURE_H, FIGURE_GAP = TABS_TOP + TAB_H + 12, 66, 10
LEAF_TOP = FIGURES_TOP + FIGURE_H + 12
# Inside the plot's leaf
HEADER_H, GUTTER, RIGHT_PAD, TICKS_H = 34, 58, 18, 26
CHIP_H, CHIP_GAP = 24, 6
RANGE_TAB = (64, 24)

UNIT_WORDS = {"coins": "Coins", "units": "Units in store", "people": "Townsfolk", "points": "Contentment, out of 100"}
COLUMN_WORDS = {"day": "day by day", "hour": "hour by hour", "season": "season by season"}
HINT = "click a name to hide or show it"

_cache: Dict[str, object] = {"data_key": None, "data": None, "layer_key": None, "layer": None}


# ----------------------------------------------------------------------
# The view
# ----------------------------------------------------------------------

def draw_depot_chart(screen: pygame.Surface, rect: pygame.Rect, font: pygame.font.Font, depot: 'Depot',
                     game_state: 'GameState', population_manager: Optional['PopulationManager'] = None,
                     goods: Optional[List['Good']] = None, framed: bool = True) -> None:
    """Draw the depot's charts into *rect* and file what can be clicked. Not *framed*, they go
    on a sheet already drawn (the depot's whole view, ``draw_depot_sheet``), the chart's title
    then heading its plot instead of a tablet of its own."""
    active = game_state.depot_active_chart if game_state.depot_active_chart in CHARTS else CHARTS[0]
    buttons = game_state.depot_chart_buttons
    mouse = pygame.mouse.get_pos()
    hover_ok = _hover_allowed(game_state)

    if framed:
        screen.blit(style.sheet(rect.size, TITLES[active]), rect)
    _draw_tabs(screen, rect, active, buttons, mouse if hover_ok else None, population_manager is not None)

    leaf = pygame.Rect(rect.left + MARGIN, rect.top + LEAF_TOP, rect.width - 2 * MARGIN,
                       rect.height - LEAF_TOP - MARGIN)
    chart = _chart(active, depot, goods or [], population_manager, game_state, leaf.width - GUTTER - RIGHT_PAD)
    _draw_figures(screen, rect, chart)

    chips = _layout_legend(chart, leaf)
    focus = None
    if hover_ok:
        focus = next((name for name, chip in chips if chip.collidepoint(mouse)), None)
    plot = _plot_rect(leaf, chips)
    screen.blit(_layer(chart, leaf, plot, focus), leaf)

    _draw_header(screen, leaf, chart, game_state, buttons, mouse if hover_ok else None,
                 None if framed else TITLES[active])
    _draw_legend(screen, chart, chips, buttons, focus, leaf.right - 12)
    if hover_ok and plot.collidepoint(mouse) and chart.count:
        _draw_hover(screen, chart, plot, mouse, rect, focus)


def handle_click(game_state: 'GameState', pos: Tuple[int, int]) -> bool:
    """A click on a chart's tab, a range or a name in the legend; True if it was one."""
    for key, rect in list(game_state.depot_chart_buttons.items()):
        if not rect.collidepoint(pos):
            continue
        kind, _, value = key.partition(":")
        if kind == "chart":
            game_state.depot_active_chart = value
        elif kind == "range":
            game_state.depot_chart_range = value
        elif kind == "series":
            hidden = game_state.depot_chart_hidden.setdefault(game_state.depot_active_chart, set())
            hidden.symmetric_difference_update({value})
        else:
            continue
        return True
    return False


def _hover_allowed(game_state: 'GameState') -> bool:
    """No hover while something lies over the view."""
    return not (getattr(game_state, "info_window", None) or getattr(game_state, "dialogue", None)
                or getattr(game_state, "contract_acquisition", None))


# ----------------------------------------------------------------------
# The chart's figures, kept while nothing they come from changes
# ----------------------------------------------------------------------

def _chart(active: str, depot: 'Depot', goods: Sequence['Good'], population, game_state: 'GameState',
           plot_width: int) -> ChartData:
    range_name = getattr(game_state, "depot_chart_range", DEFAULT_RANGE)
    if range_name not in RANGES:
        range_name = DEFAULT_RANGE
    hidden = frozenset(getattr(game_state, "depot_chart_hidden", {}).get(active, ()))
    key = (active, range_name, hidden, plot_width, game_state.depot_time_frame,
           price_tick_number(game_state.date), round(depot.money, 2), sum(depot.good_stock.values()),
           len(depot.wealth), round(depot.income, 2), round(depot.expenditures, 2), len(depot.trades),
           depot.get_property_count(),
           len(population.average_happiness_history) if population is not None else 0,
           len(population.total_population_history) if population is not None else 0)
    if _cache["data_key"] != key:
        _cache["data"] = build_chart(active, depot, goods, population, game_state.date, range_name, hidden,
                                     plot_width, game_state.depot_time_frame)
        _cache["data_key"] = key
    return _cache["data"]


# ----------------------------------------------------------------------
# The tabs and the figures
# ----------------------------------------------------------------------

def _draw_tabs(screen: pygame.Surface, rect: pygame.Rect, active: str, buttons: Dict[str, pygame.Rect],
               mouse: Optional[Tuple[int, int]], town: bool) -> None:
    groups = [g for g in CHART_GROUPS if town or not set(g) & {"Population", "Happiness"}]
    count = sum(len(g) for g in groups)
    width = rect.width - 2 * MARGIN
    tab_w = (width - (count - len(groups)) * TAB_GAP - (len(groups) - 1) * GROUP_GAP) / count
    x = rect.left + MARGIN
    for g, group in enumerate(groups):
        if g:
            sep = x - GROUP_GAP / 2 - TAB_GAP / 2      # a brass lozenge between the groups
            cy = rect.top + TABS_TOP + TAB_H // 2
            points = [(sep, cy - 6), (sep + 4, cy), (sep, cy + 6), (sep - 4, cy)]
            pygame.draw.polygon(screen, style.BRASS, points)
            pygame.draw.polygon(screen, style.BRASS_DARK, points, 1)
        for name in group:
            tab_rect = pygame.Rect(round(x), rect.top + TABS_TOP, round(tab_w), TAB_H)
            hovered = mouse is not None and tab_rect.collidepoint(mouse)
            style.tab(screen, tab_rect, TAB_LABELS.get(name, name), name == active, hovered)
            buttons[f"chart:{name}"] = tab_rect
            x += tab_w + TAB_GAP
        x += GROUP_GAP - TAB_GAP


def _draw_figures(screen: pygame.Surface, rect: pygame.Rect, chart: ChartData) -> None:
    """Four leaves of headline figures over the plot."""
    figures = chart.figures[:4]
    width = (rect.width - 2 * MARGIN - 3 * FIGURE_GAP) / 4
    label_font, value_font, note_font = style.font(16), style.title_font(28), style.font(15)
    for i in range(4):
        box = pygame.Rect(round(rect.left + MARGIN + i * (width + FIGURE_GAP)), rect.top + FIGURES_TOP,
                          round(width), FIGURE_H)
        style.leaf(screen, box, lit=i < len(figures))
        if i >= len(figures):
            continue
        fig = figures[i]
        screen.blit(_fitted(label_font, fig.label.upper(), box.width - 24, style.FAINT_INK), (box.left + 12, box.top + 6))
        ink = style.GAIN_INK if fig.tone > 0 else style.LOSS_INK if fig.tone < 0 else style.INK
        value = _fitted(value_font, fig.value, box.width - 24, ink)
        screen.blit(value, (box.left + 12, box.top + 22))
        if fig.note:
            note = _fitted(note_font, fig.note, box.width - 24, style.FAINT_INK)
            screen.blit(note, note.get_rect(bottomright=(box.right - 10, box.bottom - 5)))


def _fitted(face: pygame.font.Font, text: str, width: int, colour: Colour) -> pygame.Surface:
    """*text* rendered, cut short with an ellipsis if wider than *width*."""
    if face.size(text)[0] > width:
        while text and face.size(text + "...")[0] > width:
            text = text[:-1]
        text = text.rstrip() + "..."
    return face.render(text, True, colour)


# ----------------------------------------------------------------------
# The plot's leaf: its header, its legend, the plot itself
# ----------------------------------------------------------------------

def _layout_legend(chart: ChartData, leaf: pygame.Rect) -> List[Tuple[str, pygame.Rect]]:
    """The legend's chips, flowed in rows from the leaf's bottom left; a chart of one series has none."""
    series = [s for s in chart.all_series() if not s.fixed or len(chart.all_series()) > 1]
    if len(series) < 2:
        return []
    face = style.font(17)
    rows: List[List[Tuple[str, int]]] = [[]]
    width_left = leaf.width - 24
    used = 0
    for s in series:
        w = 12 + 7 + face.size(s.name)[0] + 16
        if rows[-1] and used + w > width_left:
            rows.append([])
            used = 0
        rows[-1].append((s.name, w))
        used += w + CHIP_GAP
    chips = []
    top = leaf.bottom - 10 - len(rows) * CHIP_H - (len(rows) - 1) * 4
    for r, row in enumerate(rows):
        x = leaf.left + 12
        for name, w in row:
            chips.append((name, pygame.Rect(x, top + r * (CHIP_H + 4), w, CHIP_H)))
            x += w + CHIP_GAP
    return chips


def _plot_rect(leaf: pygame.Rect, chips: List[Tuple[str, pygame.Rect]]) -> pygame.Rect:
    bottom = (min(chip.top for _, chip in chips) - 8 if chips else leaf.bottom - 12) - TICKS_H
    top = leaf.top + HEADER_H + 14
    return pygame.Rect(leaf.left + GUTTER, top, leaf.width - GUTTER - RIGHT_PAD, bottom - top)


def _draw_header(screen: pygame.Surface, leaf: pygame.Rect, chart: ChartData, game_state: 'GameState',
                 buttons: Dict[str, pygame.Rect], mouse: Optional[Tuple[int, int]],
                 title: Optional[str] = None) -> None:
    """The chart's *title*, if it has no tablet of its own, what the plot counts in and by, and
    the range switches at the right."""
    words = f"{UNIT_WORDS[chart.unit]}, {COLUMN_WORDS[chart.column]}"
    if chart.column == SEASON and chart.name != "Happiness":
        words += " (too many days to show singly)"
    x = leaf.left + 14
    if title:
        head = style.title_font(24).render(title, True, style.INK)
        screen.blit(head, (x, leaf.top + HEADER_H // 2 + 3 - head.get_height() // 2))
        x += head.get_width() + 10
        cy = leaf.top + 22                                   # a small brass lozenge between title and words
        points = [(x + 4, cy - 5), (x + 8, cy), (x + 4, cy + 5), (x, cy)]
        pygame.draw.polygon(screen, style.BRASS, points)
        pygame.draw.polygon(screen, style.BRASS_DARK, points, 1)
        x += 18
    screen.blit(style.font(17).render(words, True, style.FAINT_INK), (x, leaf.top + 12))
    current = getattr(game_state, "depot_chart_range", DEFAULT_RANGE)
    x = leaf.right - 12 - len(RANGES) * RANGE_TAB[0] - (len(RANGES) - 1) * 4
    for name in RANGES:
        tab = pygame.Rect(x, leaf.top + 9, *RANGE_TAB)
        style.small_tab(screen, tab, name, name == current, mouse is not None and tab.collidepoint(mouse))
        buttons[f"range:{name}"] = tab
        x += RANGE_TAB[0] + 4
    pygame.draw.line(screen, style.RULE, (leaf.left + 12, leaf.top + HEADER_H + 4),
                     (leaf.right - 12, leaf.top + HEADER_H + 4), 1)


def _draw_legend(screen: pygame.Surface, chart: ChartData, chips: List[Tuple[str, pygame.Rect]],
                 buttons: Dict[str, pygame.Rect], focus: Optional[str], leaf_right: int) -> None:
    by_name = {s.name: s for s in chart.all_series()}
    face = style.font(17)
    for name, chip in chips:
        s = by_name[name]
        lit = not s.hidden
        if name == focus:
            pygame.draw.rect(screen, (250, 240, 212), chip, border_radius=4)
            pygame.draw.rect(screen, style.BRASS, chip, 1, border_radius=4)
        sw = pygame.Rect(chip.left + 8, chip.centery - 6, 12, 12)
        if s in chart.lines and chart.kind != LINES or s.dashed:
            colour = s.colour if lit else style.RULE
            _dashed(screen, colour, [(sw.left, sw.centery), (sw.right, sw.centery)], 3, 4, 2) if s.dashed else \
                pygame.draw.line(screen, colour, (sw.left, sw.centery), (sw.right, sw.centery), 3)
        elif lit:
            pygame.draw.rect(screen, s.colour, sw, border_radius=2)
            pygame.draw.rect(screen, style.blend(s.colour, style.INK, 0.5), sw, 1, border_radius=2)
        else:
            pygame.draw.rect(screen, style.FAINT_INK, sw, 1, border_radius=2)
        text = face.render(name, True, style.INK if lit else style.FAINT_INK)
        screen.blit(text, (sw.right + 7, chip.centery - text.get_height() // 2))
        if not lit:                                             # struck out
            y = chip.centery + 1
            pygame.draw.line(screen, style.FAINT_INK, (sw.right + 5, y), (sw.right + 9 + text.get_width(), y), 1)
        if not s.fixed:
            buttons[f"series:{name}"] = chip
    if any(not by_name[name].fixed for name, _ in chips):     # how the legend works, where it fits
        row_top = max(chip.top for _, chip in chips)
        right = max(chip.right for _, chip in chips if chip.top == row_top)
        hint = style.font(15).render(HINT, True, style.blend(style.FAINT_INK, style.PAPER, 0.3))
        if right + 16 + hint.get_width() < leaf_right:
            screen.blit(hint, (right + 16, row_top + (CHIP_H - hint.get_height()) // 2))


# ----------------------------------------------------------------------
# The plot, drawn into a layer of the leaf's size
# ----------------------------------------------------------------------

class _Geometry:
    """Where a column and a value lie in the plot."""

    def __init__(self, chart: ChartData, plot: pygame.Rect):
        self.chart, self.plot = chart, plot
        self.n = max(1, chart.count)
        self.bars = chart.kind in (BARS, SIGNED)
        lo, hi = chart.scale()
        if chart.fixed_scale:
            self.step = 20.0
        else:
            self.step = nice_step(hi - lo)
            lo = math.floor(lo / self.step) * self.step
            hi = math.ceil(hi * 1.04 / self.step) * self.step if hi > 0 else 0.0
            if hi - lo < 1e-9:
                hi = lo + self.step
        self.lo, self.hi = lo, hi

    def y(self, value: float) -> float:
        return self.plot.bottom - (value - self.lo) / (self.hi - self.lo) * self.plot.height

    @property
    def pitch(self) -> float:
        """A column's width (bars), or the distance between two points (lines)."""
        if self.bars:
            return self.plot.width / self.n
        return self.plot.width / max(1, self.n - 1)

    def x(self, i: int) -> float:
        """A bar's middle, or a point on a line (the first at the left edge, the last at the right)."""
        if self.bars:
            return self.plot.left + (i + 0.5) * self.pitch
        if self.n == 1:
            return self.plot.centerx
        return self.plot.left + i * self.pitch

    def column_at(self, x: int) -> int:
        if self.bars:
            i = int((x - self.plot.left) // self.pitch)
        else:
            i = round((x - self.plot.left) / self.pitch) if self.n > 1 else 0
        return max(0, min(self.n - 1, i))


def _layer(chart: ChartData, leaf: pygame.Rect, plot: pygame.Rect, focus: Optional[str]) -> pygame.Surface:
    key = (_cache["data_key"], leaf.size, plot.topleft, plot.size, focus, id(chart))
    if _cache["layer_key"] == key:
        return _cache["layer"]
    surf = pygame.Surface(leaf.size, pygame.SRCALPHA)
    style.leaf(surf, surf.get_rect())
    local = plot.move(-leaf.left, -leaf.top)
    if not chart.count:
        text = style.title_font(24).render(chart.empty_text, True, style.FAINT_INK)
        surf.blit(text, text.get_rect(center=local.center))
    else:
        geo = _Geometry(chart, local)
        _draw_period(surf, chart, geo)
        _draw_grid(surf, chart, geo)
        if chart.kind == AREA:
            _draw_areas(surf, chart, geo, focus)
        elif chart.kind == BARS:
            _draw_bars(surf, chart, geo, focus)
        elif chart.kind == SIGNED:
            _draw_signed(surf, chart, geo)
        _draw_lines(surf, chart, geo, focus)
        _draw_ticks(surf, chart, geo)
    _cache["layer_key"], _cache["layer"] = key, surf
    return surf


def _draw_period(surf: pygame.Surface, chart: ChartData, geo: _Geometry) -> None:
    """The depot list's time frame, shaded at the plot's right end and named."""
    k = chart.period_columns
    if not k or k >= chart.count:
        return
    first = chart.count - k
    left = geo.plot.left + first * geo.pitch if geo.bars else geo.x(first) - geo.pitch / 2
    band = pygame.Rect(round(left), geo.plot.top, geo.plot.right - round(left), geo.plot.height)
    shade = pygame.Surface(band.size, pygame.SRCALPHA)
    shade.fill((*style.BRASS, 34))
    surf.blit(shade, band)
    pygame.draw.line(surf, style.blend(style.BRASS, style.PAPER, 0.3), band.topleft, band.bottomleft, 1)
    label = style.font(15).render(chart.period_name, True, style.BRASS_DARK)
    if label.get_width() + 8 < band.width:
        surf.blit(label, (band.left + 5, band.top + 3))


def _draw_grid(surf: pygame.Surface, chart: ChartData, geo: _Geometry) -> None:
    face = style.font(16)
    value = geo.lo
    while value <= geo.hi + 1e-9:
        y = round(geo.y(value))
        zero = abs(value) < 1e-9 and geo.lo < 0
        pygame.draw.line(surf, style.FAINT_INK if zero else style.RULE, (geo.plot.left, y), (geo.plot.right, y), 1)
        label = face.render(compact(value), True, style.FAINT_INK)
        surf.blit(label, label.get_rect(midright=(geo.plot.left - 8, y)))
        value += geo.step
    if geo.lo >= 0:                                             # the baseline, a shade darker than the grid
        pygame.draw.line(surf, style.FAINT_INK, geo.plot.bottomleft, geo.plot.bottomright, 1)


def _draw_ticks(surf: pygame.Surface, chart: ChartData, geo: _Geometry) -> None:
    """The calendar under the plot; a year's beginning ruled through it."""
    face = style.font(16)
    last_right = -10 ** 6
    for i, label, year in chart.ticks:
        x = round(geo.plot.left + i * geo.pitch) if geo.bars else round(geo.x(i))
        if year and x > geo.plot.left + 1:
            _dashed(surf, style.blend(style.BRASS_DARK, style.PAPER, 0.35),
                    [(x, geo.plot.top), (x, geo.plot.bottom)], 1, 5, 4)
        pygame.draw.line(surf, style.FAINT_INK, (x, geo.plot.bottom), (x, geo.plot.bottom + 5), 1)
        text = face.render(label, True, style.INK if year else style.FAINT_INK)
        centre = x + (geo.pitch / 2 if geo.bars and len(chart.ticks) == chart.count else 0)
        box = text.get_rect(midtop=(round(centre), geo.plot.bottom + 6))
        box.left = max(box.left, geo.plot.left - 4)
        box.right = min(box.right, geo.plot.right + 14)
        if box.left > last_right + 8:
            surf.blit(text, box)
            last_right = box.right


def _colour(s: Series, focus: Optional[str]) -> Colour:
    return s.colour if focus is None or focus == s.name else style.faded(s.colour)


def _draw_areas(surf: pygame.Surface, chart: ChartData, geo: _Geometry, focus: Optional[str]) -> None:
    """The layers stacked, each a translucent band with its upper edge inked."""
    xs = [geo.x(i) for i in range(chart.count)] if chart.count > 1 else [geo.plot.left, geo.plot.right]
    base = [0.0] * chart.count
    fills = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
    edges = []
    for s in chart.visible_layers():
        top = [b + v for b, v in zip(base, s.values)]
        upper = [(x, geo.y(v)) for x, v in zip(xs, _widened(top, chart.count))]
        lower = [(x, geo.y(v)) for x, v in zip(xs, _widened(base, chart.count))]
        alpha = 120 if focus in (None, s.name) else 40
        pygame.draw.polygon(fills, (*s.colour, alpha), upper + lower[::-1])
        edges.append((_colour(s, focus), upper))
        base = top
    surf.blit(fills, (0, 0))
    for colour, points in edges:
        _polyline(surf, colour, points, 2)


def _widened(values: List[float], count: int) -> List[float]:
    return values if count > 1 else values * 2


def _draw_bars(surf: pygame.Surface, chart: ChartData, geo: _Geometry, focus: Optional[str]) -> None:
    """Each column's layers stacked, a hair of paper between them; today's bar paler, being unfinished."""
    width, offset = _bar_width(geo)
    for i in range(chart.count):
        left = round(geo.plot.left + i * geo.pitch + offset)
        bottom = geo.y(0)
        so_far = chart.partial and i == chart.count - 1
        layers = [s for s in chart.visible_layers() if s.values[i] > 0]
        for n, s in enumerate(layers):
            top = geo.y(sum(t.values[i] for t in layers[:n + 1]))
            rect = pygame.Rect(left, round(top), width, max(1, round(bottom) - round(top)))
            if n and rect.height > 3 and width > 3:                # the hair of paper under it
                rect.height -= 1
            colour = _colour(s, focus)
            radius = min(3, width // 3) if n == len(layers) - 1 else 0
            pygame.draw.rect(surf, style.faded(colour, 0.5) if so_far else colour, rect,
                             border_top_left_radius=radius, border_top_right_radius=radius)
            if so_far:
                pygame.draw.rect(surf, colour, rect, 1, border_top_left_radius=radius, border_top_right_radius=radius)
            bottom = top


def _bar_width(geo: _Geometry) -> Tuple[int, float]:
    gap = min(6.0, max(1.0, geo.pitch * 0.28))
    width = max(1, int(geo.pitch - gap))
    return width, (geo.pitch - width) / 2


def _draw_signed(surf: pygame.Surface, chart: ChartData, geo: _Geometry) -> None:
    """A gain up from nought in green, a loss down from it in red."""
    width, offset = _bar_width(geo)
    zero = round(geo.y(0))
    values = chart.layers[0].values
    for i, value in enumerate(values):
        y = round(geo.y(value))
        left = round(geo.plot.left + i * geo.pitch + offset)
        colour = GAIN if value >= 0 else LOSS
        rect = pygame.Rect(left, min(y, zero), width, max(1, abs(zero - y)))
        radius = min(3, width // 3)
        corners = dict(border_top_left_radius=radius, border_top_right_radius=radius) if value >= 0 else \
            dict(border_bottom_left_radius=radius, border_bottom_right_radius=radius)
        if chart.partial and i == len(values) - 1:
            pygame.draw.rect(surf, style.faded(colour, 0.5), rect, **corners)
            pygame.draw.rect(surf, colour, rect, 1, **corners)
        else:
            pygame.draw.rect(surf, colour, rect, **corners)


def _draw_lines(surf: pygame.Surface, chart: ChartData, geo: _Geometry, focus: Optional[str]) -> None:
    """The lines over the layers (a total, loans, an average) or, for happiness, the chart itself;
    the one in focus last, on top."""
    lines = chart.visible_lines()
    lines.sort(key=lambda s: (s.name == focus, s.thick))
    for s in lines:
        xs = [geo.x(i) for i in range(chart.count)] if chart.count > 1 else [geo.plot.left, geo.plot.right]
        points = [(x, geo.y(v)) for x, v in zip(xs, _widened(s.values, chart.count))]
        colour = _colour(s, focus)
        width = 3 if s.thick or s.name == focus else 2
        if s.dashed:
            _dashed(surf, colour, points, 2, 9, 6)
        else:
            _polyline(surf, colour, points, width)


def _polyline(surface: pygame.Surface, colour: Colour, points: Sequence[Tuple[float, float]], width: int) -> None:
    """A line of any width with smoothed edges and round joints."""
    if len(points) < 2:
        return
    if width <= 1:
        pygame.draw.aalines(surface, colour, False, points)
        return
    half = (width - 1) / 2
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        length = math.hypot(x1 - x0, y1 - y0)
        if length == 0:
            continue
        nx, ny = -(y1 - y0) / length * half, (x1 - x0) / length * half
        a, b, c, d = (x0 + nx, y0 + ny), (x1 + nx, y1 + ny), (x1 - nx, y1 - ny), (x0 - nx, y0 - ny)
        pygame.draw.polygon(surface, colour, (a, b, c, d))
        pygame.draw.aaline(surface, colour, a, b)
        pygame.draw.aaline(surface, colour, d, c)
    if half >= 1:
        for x, y in points[1:-1]:
            pygame.draw.circle(surface, colour, (round(x), round(y)), round(half))


def _dashed(surface: pygame.Surface, colour: Colour, points: Sequence[Tuple[float, float]], width: int,
            dash: float, gap: float) -> None:
    """A dashed line along *points*, the dashes running on round the bends."""
    on, left = True, dash
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        length = math.hypot(x1 - x0, y1 - y0)
        done = 0.0
        while done < length - 1e-9:
            step = min(left, length - done)
            if on:
                a = (x0 + (x1 - x0) * done / length, y0 + (y1 - y0) * done / length)
                b = (x0 + (x1 - x0) * (done + step) / length, y0 + (y1 - y0) * (done + step) / length)
                pygame.draw.line(surface, colour, a, b, width)
            done += step
            left -= step
            if left <= 1e-9:
                on = not on
                left = dash if on else gap


# ----------------------------------------------------------------------
# The column under the pointer
# ----------------------------------------------------------------------

def _draw_hover(screen: pygame.Surface, chart: ChartData, plot: pygame.Rect, mouse: Tuple[int, int],
                bounds: pygame.Rect, focus: Optional[str]) -> None:
    geo = _Geometry(chart, plot)
    i = geo.column_at(mouse[0])
    x = geo.x(i)
    if geo.bars:
        band = pygame.Rect(round(plot.left + i * geo.pitch), plot.top, max(2, round(geo.pitch)), plot.height)
        shade = pygame.Surface(band.size, pygame.SRCALPHA)
        shade.fill((*style.BRASS, 60))
        screen.blit(shade, band)
    else:
        pygame.draw.line(screen, style.BRASS_DARK, (round(x), plot.top), (round(x), plot.bottom), 1)
        dots = []
        if chart.kind == AREA:
            base = 0.0
            for s in chart.visible_layers():
                base += s.values[i]
                dots.append((s.colour, base))
        dots += [(s.colour, s.values[i]) for s in chart.visible_lines()]
        for colour, value in dots:
            centre = (round(x), round(geo.y(value)))
            pygame.draw.circle(screen, style.PAPER, centre, 6)
            pygame.draw.circle(screen, colour, centre, 4)

    rows, colours = [], {}
    line_names = {s.name for s in chart.lines}
    for colour, name, value in chart.tooltip(i):
        if chart.kind == SIGNED and name == "Profit":
            colour = GAIN if value >= 0 else LOSS
            colours[len(rows)] = style.GAIN_INK if value > 0 else style.LOSS_INK if value < 0 else style.INK
            text = signed(value)
        else:
            text = amount(value, chart.unit)
        if colour is None:
            kind = "total"
        elif name in line_names and chart.kind != LINES:
            kind = "line"
        elif name == focus:
            kind = "focus"
        else:
            kind = "line" if chart.kind == LINES else ""
        rows.append((colour, name, text, kind))
    if chart.extra and i < len(chart.extra):
        rows += [(None, label, value, "faint") for label, value in chart.extra[i]]
    style.note(screen, (round(x), mouse[1]), chart.headings[i], rows, bounds.inflate(-2 * MARGIN + 20, -60),
               colours)
