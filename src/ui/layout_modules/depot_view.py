"""The depot's accounts: a counting-house sheet with the figures of the chosen time frame.

At the top a tab for each time frame (``PERIOD_DAYS``: Daily, Seasonal, Yearly, Total) and the
days it covers. On the left a ledger of the period's figures, each row's value set right at the
end of a dotted leader, gains in green and losses in red; a row marked with a lozenge opens its
details on the right (``DepotViewDetail``), and when the depot's charts are shown beside it, turns
them to the matching chart too (``ROW_CHARTS``). The last trade is written out in a line, and the
goods that paid best and worst have their pictures.

What can be clicked is filed each frame in ``game_state.depot_buttons`` (``"frame:<name>"``) and
``game_state.depot_plus_rects`` (a row's detail key), and handled by ``handle_click``; the wheel
scrolls the ledger while the pointer is over ``game_state.depot_scroll_rect``.
"""

import datetime
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

import pygame

from . import ledger_style as style
from ...sim.calendar import EPOCH, PERIOD_DAYS, format_date

if TYPE_CHECKING:
    from ...game_state import GameState
    from ...models.depot import Depot

MARGIN = 52
TABS_TOP, TAB_H, TAB_W, TAB_GAP = 100, 34, 112, 8
CONTENT_TOP = 176
ROW_H, HEADING_H, SECTION_GAP = 26, 38, 10
COLUMN_GAP = 14

# A row whose details can be opened, and the chart it turns the depot's charts to
ROW_CHARTS: Dict[str, Optional[str]] = {
    "Current Wealth": "Wealth", "Wealth Start": "Wealth", "Income": "Income", "Expenses": "Expenses",
    "Profit": "Profit", "Total Stock": "Stock", "Buy Actions": None, "Sell Actions": None, "Total Actions": None,
}
ROW_LABELS = {"Wealth Start": "Wealth at Start", "Total Stock": "Stock in Store"}

Row = Tuple[str, str, int]          # (label, value, tone: +1 a gain, -1 a loss, 0 neither)


def draw_depot_view(screen: pygame.Surface, font: pygame.font.Font, depot: 'Depot', game_state: 'GameState',
                    rect: pygame.Rect, framed: bool = True) -> None:
    """Draw the depot's accounts into *rect* and file what can be clicked; not *framed*, on a
    sheet already drawn (the depot's whole view, ``draw_depot_sheet``)."""
    mouse = pygame.mouse.get_pos()
    hover_ok = not (getattr(game_state, "info_window", None) or getattr(game_state, "dialogue", None))
    if framed:
        screen.blit(style.sheet(rect.size, "Accounts"), rect)
    _draw_frames(screen, rect, game_state, mouse if hover_ok else None)

    inner_w = rect.width - 2 * MARGIN
    list_w = (inner_w - COLUMN_GAP) // 2
    list_rect = pygame.Rect(rect.left + MARGIN, rect.top + CONTENT_TOP, list_w, rect.height - CONTENT_TOP - MARGIN)
    panel_rect = pygame.Rect(list_rect.right + COLUMN_GAP, list_rect.top, inner_w - list_w - COLUMN_GAP, list_rect.height)

    if game_state.detail_panel is None:
        from .depot_view_detail import DepotViewDetail
        game_state.detail_panel = DepotViewDetail(rect, game_state)
        game_state.detail_panel.show_for_statistic("Current Wealth")
    game_state.detail_panel.rect = panel_rect

    sections = _sections(depot, game_state)
    _draw_ledger(screen, list_rect, sections, depot, game_state, mouse if hover_ok else None)

    if game_state.detail_panel.visible:
        game_state.detail_panel.draw(screen, font)
    else:
        style.leaf(screen, panel_rect, lit=False)
        hint = style.font(17).render("Choose a marked row to see its details", True, style.FAINT_INK)
        screen.blit(hint, hint.get_rect(center=panel_rect.center))


def handle_click(game_state: 'GameState', pos: Tuple[int, int]) -> bool:
    """A click on a time frame's tab or a ledger row with details; True if it was one."""
    for key, rect in list(game_state.depot_buttons.items()):
        if rect.collidepoint(pos) and key.startswith("frame:"):
            game_state.depot_time_frame = key.partition(":")[2]
            if game_state.detail_panel is not None:
                game_state.detail_panel.update_statistics(force=True)
            return True
    for label, rect in list(game_state.depot_plus_rects.items()):
        if not rect.collidepoint(pos):
            continue
        panel = game_state.detail_panel
        if panel is not None:
            if panel.visible and panel.current_statistic == label:
                panel.visible = False
            else:
                panel.show_for_statistic(label)
                if ROW_CHARTS.get(label):
                    game_state.depot_active_chart = ROW_CHARTS[label]
        return True
    return False


# ----------------------------------------------------------------------
# The time frames
# ----------------------------------------------------------------------

def _draw_frames(screen: pygame.Surface, rect: pygame.Rect, game_state: 'GameState',
                 mouse: Optional[Tuple[int, int]]) -> None:
    frames = game_state.depot_time_frames
    total_w = len(frames) * TAB_W + (len(frames) - 1) * TAB_GAP
    x = rect.centerx - total_w // 2
    for name in frames:
        tab = pygame.Rect(x, rect.top + TABS_TOP, TAB_W, TAB_H)
        style.tab(screen, tab, name, name == game_state.depot_time_frame,
                  mouse is not None and tab.collidepoint(mouse))
        game_state.depot_buttons[f"frame:{name}"] = tab
        x += TAB_W + TAB_GAP
    days = PERIOD_DAYS.get(game_state.depot_time_frame)
    start = EPOCH if days is None else (game_state.date - datetime.timedelta(days=days - 1)).date()
    start = max(start, EPOCH)
    words = format_date(game_state.date) if days == 1 else f"{format_date(start)}  to  {format_date(game_state.date)}"
    text = style.font(18).render(words, True, style.FAINT_INK)
    centre = (rect.centerx, rect.top + TABS_TOP + TAB_H + 18)
    screen.blit(text, text.get_rect(center=centre))
    half = text.get_width() // 2 + 26
    for sign in (-1, 1):
        x0 = centre[0] + sign * half
        pygame.draw.line(screen, style.BRASS, (x0, centre[1]), (x0 + sign * 60, centre[1]), 1)


# ----------------------------------------------------------------------
# The period's figures
# ----------------------------------------------------------------------

def _sections(depot: 'Depot', game_state: 'GameState') -> List[Tuple[str, List[Row]]]:
    """The ledger's sections and rows for the time frame chosen."""
    goods = game_state.game.goods
    period_days = PERIOD_DAYS.get(game_state.depot_time_frame)
    outstanding_loans = depot.outstanding_loans()
    current_wealth = (depot.money + sum(depot.good_stock.get(g.name, 0) * g.price for g in goods)
                      + depot.get_property_value() - outstanding_loans)
    if period_days is not None and len(depot.wealth) >= period_days:
        start_wealth = depot.wealth[-period_days]
    else:
        start_wealth = depot.wealth[0]
    change = current_wealth - start_wealth

    if period_days is not None:
        back = period_days - 1
        income = (sum(depot.income_history[-back:]) if back > 0 else 0) + depot.income
        expense = (sum(depot.expenditure_history[-back:]) if back > 0 else 0) + depot.expenditures
        since = game_state.date - datetime.timedelta(days=period_days)
        trades = [t for t in depot.trades if t["timestamp"] >= since]
        cycles = depot.get_trade_cycle_stats(game_state.date, datetime.timedelta(days=period_days))
    else:
        income = sum(depot.income_history) + depot.income
        expense = sum(depot.expenditure_history) + depot.expenditures
        trades = depot.trades
        cycles = depot.get_trade_cycle_stats(game_state.date, None)

    tone = lambda v: (v > 0.005) - (v < -0.005)
    margin = change / start_wealth * 100 if start_wealth > 0 else 0.0
    sections = [
        ("Wealth", [
            ("Current Wealth", f"{current_wealth:,.2f}", 0),
            ("Wealth Start", f"{start_wealth:,.2f}", 0),
            ("Outstanding Loans", f"{outstanding_loans:,.2f}", -1 if outstanding_loans > 0 else 0),
            ("Income", f"{income:,.2f}", 0),
            ("Expenses", f"{expense:,.2f}", 0),
            ("Profit", f"{'+' if change > 0.005 else ''}{change:,.2f}", tone(change)),
            ("Profit Margin", f"{margin:+.1f}%" if abs(margin) >= 0.05 else "0.0%", tone(margin)),
            ("Total Stock", f"{sum(depot.good_stock.values()):,} / {depot.total_capacity():,}", 0),
        ]),
        ("Trading", [
            ("Buy Actions", f"{sum(1 for t in trades if t['type'] == 'purchase'):,}", 0),
            ("Sell Actions", f"{sum(1 for t in trades if t['type'] == 'sale'):,}", 0),
            ("Total Actions", f"{len(trades):,}", 0),
        ]),
        ("Trade Cycles", [
            ("Completed Trades", f"{cycles['total_cycles']:,}", 0),
            ("Successful Trades", f"{cycles['successful_cycles']:,}", 0),
            ("Success Rate", f"{cycles['success_rate']:.1f}%", 0),
            ("Total Trade Profit", f"{cycles['total_profit']:+,.2f}" if cycles['total_profit'] else "0.00",
             tone(cycles['total_profit'])),
        ]),
    ]
    best = [(name, p) for name, p in cycles["best_goods"][:3] if p > 0]
    worst = [(name, p) for name, p in reversed(cycles["worst_goods"][-3:]) if p < 0]
    if best or worst:
        sections.append(("Goods, Profit per Unit",
                         [(f"@{name}", f"{p:+,.2f}", 1) for name, p in best] +
                         [(f"@{name}", f"{p:+,.2f}", -1) for name, p in worst]))
    return sections


# ----------------------------------------------------------------------
# The ledger, scrolled
# ----------------------------------------------------------------------

def _draw_ledger(screen: pygame.Surface, list_rect: pygame.Rect, sections: List[Tuple[str, List[Row]]],
                 depot: 'Depot', game_state: 'GameState', mouse: Optional[Tuple[int, int]]) -> None:
    style.leaf(screen, list_rect)
    view = list_rect.inflate(-16, -16)
    game_state.depot_scroll_rect = list_rect
    last_trade = depot.trades[-1] if depot.trades else None
    height = sum(HEADING_H + len(rows) * ROW_H + SECTION_GAP for _, rows in sections)
    height += (HEADING_H + 2 * ROW_H + SECTION_GAP) if last_trade else 0
    content = pygame.Surface((view.width, max(height, 1)), pygame.SRCALPHA)

    max_offset = max(0, height - view.height)
    offset = max(0, min(game_state.depot_scroll_offset, max_offset))
    game_state.depot_scroll_offset = offset
    local_mouse = (mouse[0] - view.left, mouse[1] - view.top + offset) if mouse and view.collidepoint(mouse) else None

    panel = game_state.detail_panel
    selected = panel.current_statistic if panel is not None and panel.visible else None
    icons = game_state.game.images.get('goods_30', {}) if hasattr(game_state.game, 'images') else {}
    row_font, value_font, head_font = style.font(19), style.font(19), style.title_font(24)
    rows_clickable: Dict[str, pygame.Rect] = {}

    y = 0
    sections_drawn = list(sections)
    if last_trade:
        sections_drawn.insert(1, ("Last Trade", []))
    for title, rows in sections_drawn:
        head = head_font.render(title, True, style.INK)
        content.blit(head, (6, y + 4))
        pygame.draw.line(content, style.BRASS, (6, y + HEADING_H - 6), (view.width - 6, y + HEADING_H - 6), 1)
        pygame.draw.line(content, style.blend(style.BRASS, style.PAPER, 0.5), (6, y + HEADING_H - 4),
                         (view.width - 6, y + HEADING_H - 4), 1)
        y += HEADING_H
        if title == "Last Trade":
            _draw_last_trade(content, y, view.width, last_trade, icons)
            y += 2 * ROW_H + SECTION_GAP
            continue
        for label, value, tone in rows:
            row = pygame.Rect(0, y, view.width, ROW_H)
            key = label if label in ROW_CHARTS else None
            hovered = key is not None and local_mouse is not None and row.collidepoint(local_mouse)
            if key == selected or hovered:
                wash = pygame.Surface(row.size, pygame.SRCALPHA)
                wash.fill((*style.BRASS, 70 if key == selected else 36))
                content.blit(wash, row)
                if key == selected:
                    pygame.draw.rect(content, style.BRASS_DARK, (0, y + 3, 3, ROW_H - 6))
            x = 10
            if key is not None:                                   # a lozenge: its details can be opened
                cx, cy = x + 5, y + ROW_H // 2
                points = [(cx, cy - 6), (cx + 5, cy), (cx, cy + 6), (cx - 5, cy)]
                pygame.draw.polygon(content, style.BRASS if key == selected else (240, 226, 190), points)
                pygame.draw.polygon(content, style.BRASS_DARK, points, 1)
                rows_clickable[key] = row
            x += 18
            name = label
            if label.startswith("@"):                              # a good, with its picture
                name = label[1:]
                if name in icons:
                    icon = pygame.transform.smoothscale(icons[name], (22, 22))
                    content.blit(icon, (x - 16, y + 2))
                    x += 10
            text = row_font.render(ROW_LABELS.get(name, name), True, style.INK)
            ink = style.GAIN_INK if tone > 0 else style.LOSS_INK if tone < 0 else style.INK
            val = value_font.render(value, True, ink)
            ty = y + (ROW_H - text.get_height()) // 2
            content.blit(text, (x, ty))
            content.blit(val, (view.width - 8 - val.get_width(), ty))
            style.leader(content, x + text.get_width() + 8, view.width - 14 - val.get_width(), y + ROW_H - 8)
            y += ROW_H
        y += SECTION_GAP

    clip = screen.get_clip()
    screen.set_clip(view)
    screen.blit(content, view.topleft, area=pygame.Rect(0, offset, view.width, view.height))
    screen.set_clip(clip)

    game_state.depot_plus_rects = {}
    for key, row in rows_clickable.items():
        on_screen = row.move(view.left, view.top - offset).clip(view)
        if on_screen.height > ROW_H // 2:
            game_state.depot_plus_rects[key] = on_screen

    if max_offset:                                                # a brass scrollbar in the leaf's margin
        track = pygame.Rect(list_rect.right - 7, view.top, 4, view.height)
        pygame.draw.rect(screen, style.RULE, track, border_radius=2)
        thumb_h = max(24, view.height * view.height // height)
        thumb_y = view.top + (view.height - thumb_h) * offset // max_offset
        pygame.draw.rect(screen, style.BRASS_DARK, (track.left, thumb_y, 4, thumb_h), border_radius=2)


def _draw_last_trade(surf: pygame.Surface, y: int, width: int, trade: dict, icons: dict) -> None:
    """The last trade in two lines: what, how many and at what, then what it came to and when."""
    sold = trade["type"] != "purchase"
    icon = icons.get(trade["good"])
    x = 10
    if icon is not None:
        surf.blit(pygame.transform.smoothscale(icon, (34, 34)), (x, y + 8))
        x += 44
    verb = "Sold" if sold else "Bought"
    first = style.font(19).render(f"{verb} {trade['quantity']:,} {trade['good']} at {trade['price']:,.2f}",
                                  True, style.INK)
    surf.blit(first, (x, y + 2))
    when = trade.get("timestamp")
    second = style.font(17).render(format_date(when) if when else "", True, style.FAINT_INK)
    surf.blit(second, (x, y + ROW_H + 2))
    total = style.font(19).render(f"{'+' if sold else '-'}{trade['total']:,.2f}", True,
                                  style.GAIN_INK if sold else style.LOSS_INK)
    surf.blit(total, (width - 8 - total.get_width(), y + ROW_H + 2))
