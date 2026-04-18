import math
import pygame
import datetime
from typing import TYPE_CHECKING, Optional, List
from ...config.colors import *

if TYPE_CHECKING:
    from ...models.depot import Depot
    from ...game_state import GameState
    from ...models.population import PopulationManager
    from ...models.good import Good

def draw_depot_chart(screen: pygame.Surface, rect: pygame.Rect, font: pygame.font.Font, depot: 'Depot', game_state: 'GameState', population_manager: Optional['PopulationManager'] = None, goods: Optional[List['Good']] = None) -> None:
    """Draws the depot chart view with wealth, money, stock, house, population and happiness statistics.

    Args:
        screen: The pygame surface to draw on.
        rect: The area where the chart should be drawn.
        font: Font for labels and text.
        depot: The player's depot model containing history data.
        game_state: Current game state.
        population_manager: Optional population manager for population/happiness charts.
    """
    # 1. Draw Background
    pygame.draw.rect(screen, BEIGE, rect)
    pygame.draw.rect(screen, DARK_BROWN, rect, 2)

    # 2. Define Layout Areas
    # Chart Area: Top part, buttons at bottom
    button_height = 40
    button_margin = 10

    chart_rect = pygame.Rect(
        rect.x + 20,
        rect.y + 20,
        rect.width - 40,
        rect.height - button_height - 30
    )

    buttons_area_y = rect.bottom - button_height - 15

    # Draw chart background
    pygame.draw.rect(screen, SANDY_BROWN, chart_rect)
    pygame.draw.rect(screen, DARK_BROWN, chart_rect, 2)

    # 3. Get Data based on active selection
    active_chart = game_state.depot_active_chart
    data_points = []
    color = BLACK
    label = active_chart

    if active_chart == "Wealth":
        data_points = depot.wealth
        color = DARK_GREEN
    elif active_chart == "Money":
        data_points = depot.money_history
        color = MATTE_BROWN
    elif active_chart == "Stock":
        data_points = depot.total_stock
        color = DARK_BLUE
    elif active_chart == "Houses":
        data_points = depot.house_history
        color = DARK_RED
    elif active_chart == "Population" and population_manager is not None:
        data_points = population_manager.total_population_history
        color = STEELE_BLUE
    elif active_chart == "Happiness" and population_manager is not None:
        data_points = population_manager.average_happiness_history
        color = DARK_ORANGE

    # 4. Draw Chart
    if active_chart == "Population" and population_manager is not None:
        _draw_population_stacked_bars(screen, chart_rect, font, population_manager, game_state.date)
    elif active_chart == "Stock" and goods is not None:
        _draw_stock_stacked_bars(screen, chart_rect, font, depot, goods, game_state.date)
    elif active_chart == "Expenses":
        _draw_expenses_stacked_bars(screen, chart_rect, font, depot, game_state.date)
    elif len(data_points) > 1:
        # Determine scaling
        max_points = chart_rect.width
        visible_data = data_points[-int(max_points):]

        if not visible_data:
            visible_data = [0]

        # For Money chart, also fetch aligned loan history
        visible_loan_data = []
        if active_chart == "Money" and len(depot.loan_history) > 1:
            raw_loans = depot.loan_history[-int(max_points):]
            # Align to same length as visible_data
            if len(raw_loans) >= len(visible_data):
                visible_loan_data = raw_loans[-len(visible_data):]
            else:
                visible_loan_data = [0.0] * (len(visible_data) - len(raw_loans)) + list(raw_loans)

        has_loans = bool(visible_loan_data) and any(v > 0 for v in visible_loan_data)

        min_val = min(visible_data)
        max_val = max(visible_data)
        if has_loans:
            max_val = max(max_val, max(visible_loan_data))

        # Add some padding to Y-axis
        range_val = max_val - min_val
        if range_val == 0:
            range_val = 1 if max_val == 0 else max_val * 0.1

        y_min_scale = min_val - (range_val * 0.1)
        y_max_scale = max_val + (range_val * 0.1)

        if y_min_scale < 0 and min_val >= 0: y_min_scale = 0 # Don't go below 0 for positive data

        y_range = y_max_scale - y_min_scale

        # Calculate points
        points = []
        margin = 2  # Padding to stay clearly inside the chart border
        inner_width = chart_rect.width - (margin * 2)
        inner_height = chart_rect.height - (margin * 2)
        point_width = inner_width / max(1, len(visible_data) - 1)

        for i, val in enumerate(visible_data):
            x = chart_rect.left + margin + (i * point_width)
            # Y is inverted (top is 0)
            if y_range != 0:
                normalized_val = (val - y_min_scale) / y_range
                y = (chart_rect.bottom - margin) - (normalized_val * inner_height)
            else:
                y = chart_rect.bottom - margin - (0.5 * inner_height)
            points.append((x, y))

        # Draw lines
        loan_points = []
        if len(points) > 1:
            mouse_pos_early = pygame.mouse.get_pos()
            is_hovering = chart_rect.collidepoint(mouse_pos_early) and active_chart in ("Wealth", "Money", "Happiness")
            line_width = 3 if is_hovering else 2
            pygame.draw.lines(screen, color, False, points, line_width)

            # Draw loan line for Money chart
            if has_loans:
                loan_color = DARK_RED
                for i, val in enumerate(visible_loan_data):
                    x = chart_rect.left + margin + (i * point_width)
                    if y_range != 0:
                        normalized_val = (val - y_min_scale) / y_range
                        y = (chart_rect.bottom - margin) - (normalized_val * inner_height)
                    else:
                        y = chart_rect.bottom - margin - (0.5 * inner_height)
                    loan_points.append((x, y))
                if len(loan_points) > 1:
                    pygame.draw.lines(screen, loan_color, False, loan_points, line_width)

        # Draw horizontal orientation lines
        step = _nice_grid_step(y_range)

        # Draw lines at step increments
        # Start at the first multiple of step >= y_min_scale
        start_line = (int(y_min_scale // step) + 1) * step
        current_line = start_line

        while current_line < y_max_scale:
            # Calculate Y position
            normalized_y = (current_line - y_min_scale) / y_range
            line_y = chart_rect.bottom - margin - (normalized_y * inner_height)

            # Draw line - fix right side reaching 2 pixels too much
            pygame.draw.line(screen, CHART_BROWN, (chart_rect.left, line_y), (chart_rect.right - 2, line_y), 1)

            # Draw label
            line_label = font.render(f"{int(current_line):,}", True, CHART_BROWN)
            screen.blit(line_label, (chart_rect.left + 5, line_y - 12))

            current_line += step

        _draw_bar_stat_box(screen, font, chart_rect, max_val, min_val)

        # Draw Title
        title_surf = font.render(f"{label} History", True, DARK_BROWN)
        title_rect = title_surf.get_rect(midtop=(chart_rect.centerx, chart_rect.top + 8))
        screen.blit(title_surf, title_rect)
        underline_y = title_rect.bottom + 2
        pygame.draw.line(screen, DARK_BROWN, (title_rect.left, underline_y), (title_rect.right, underline_y), 1)

        # Legend for Money chart when loans are visible
        if has_loans:
            legend_items = [(color, "Cash"), (DARK_RED, "Loans")]
            lx, ly = chart_rect.left + 6, chart_rect.top + 6
            seg_len = 18
            for leg_color, leg_label in legend_items:
                pygame.draw.line(screen, leg_color, (lx, ly + 5), (lx + seg_len, ly + 5), 2)
                lbl = font.render(leg_label, True, DARK_BROWN)
                screen.blit(lbl, (lx + seg_len + 4, ly))
                ly += lbl.get_height() + 3

        # Line chart hover tooltips
        mouse_pos = pygame.mouse.get_pos()
        if chart_rect.collidepoint(mouse_pos) and active_chart in ("Wealth", "Money", "Happiness"):
            rel_x = mouse_pos[0] - (chart_rect.left + margin)
            vis_idx = max(0, min(len(visible_data) - 1, round(rel_x / point_width) if point_width else 0))
            start_idx = len(data_points) - len(visible_data)
            actual_idx = start_idx + vis_idx
            entries_ago = len(data_points) - 1 - actual_idx

            # Draw vertical line at the hovered data point
            vx = int(points[vis_idx][0])
            pygame.draw.line(screen, CHART_BROWN, (vx, chart_rect.top + 1), (vx, chart_rect.bottom - 2), 1)
            # Draw dot on main line
            dot_pos = (int(points[vis_idx][0]), int(points[vis_idx][1]))
            pygame.draw.circle(screen, color, dot_pos, 4)
            pygame.draw.circle(screen, DARK_BROWN, dot_pos, 4, 1)
            # Draw dot on loan line if visible
            if has_loans and vis_idx < len(loan_points):
                loan_dot = (int(loan_points[vis_idx][0]), int(loan_points[vis_idx][1]))
                pygame.draw.circle(screen, DARK_RED, loan_dot, 4)
                pygame.draw.circle(screen, DARK_BROWN, loan_dot, 4, 1)

            if active_chart == "Wealth":
                bar_date = (game_state.date - datetime.timedelta(days=entries_ago)).strftime("%d.%m.%Y")
                total_w = depot.wealth[actual_idx] if actual_idx < len(depot.wealth) else 0
                money   = depot.money_history[actual_idx] if actual_idx < len(depot.money_history) else 0
                goods_v = total_w - money
                prop_v  = depot.property_value_history[actual_idx] if actual_idx < len(depot.property_value_history) else 0
                loan_v  = depot.loan_history[actual_idx] if actual_idx < len(depot.loan_history) else 0
                lines = [
                    ("Date:",         bar_date),
                    ("Total Wealth:", f"{total_w:,.0f}"),
                    ("Money:",        f"{money:,.0f}"),
                    ("Goods:",        f"{goods_v:,.0f}"),
                    ("Property:",     f"{prop_v:,.0f}"),
                    ("Loan:",         f"{loan_v:,.0f}"),
                ]
                _draw_wealth_tooltip(screen, font, mouse_pos, chart_rect, lines)

            elif active_chart == "Money":
                bar_date = (game_state.date - datetime.timedelta(days=entries_ago)).strftime("%d.%m.%Y")
                cash   = depot.money_history[actual_idx] if actual_idx < len(depot.money_history) else 0
                loan_v = depot.loan_history[actual_idx] if actual_idx < len(depot.loan_history) else 0
                lines = [
                    ("Date:",  bar_date),
                    ("Cash:",  f"{cash:,.0f}"),
                    ("Loans:", f"{loan_v:,.0f}"),
                ]
                _draw_wealth_tooltip(screen, font, mouse_pos, chart_rect, lines)

            elif active_chart == "Happiness" and population_manager is not None:
                bar_date = (game_state.date - datetime.timedelta(hours=entries_ago)).strftime("%d.%m.%Y %H:00")
                h_hist = population_manager.happiness_history
                total_h = population_manager.average_happiness_history[actual_idx] if actual_idx < len(population_manager.average_happiness_history) else 0
                poor_h  = h_hist["Poor"][actual_idx]   if "Poor"          in h_hist and actual_idx < len(h_hist["Poor"])          else 0
                comm_h  = h_hist["Commons"][actual_idx] if "Commons"       in h_hist and actual_idx < len(h_hist["Commons"])       else 0
                mid_h   = h_hist["Middling Sort"][actual_idx] if "Middling Sort" in h_hist and actual_idx < len(h_hist["Middling Sort"]) else 0
                nob_h   = h_hist["Nobility"][actual_idx] if "Nobility"     in h_hist and actual_idx < len(h_hist["Nobility"])      else 0
                lines = [
                    ("Date:",           bar_date),
                    ("Happiness Total:", f"{total_h:.1f}"),
                    ("Poor:",           f"{poor_h:.1f}"),
                    ("Common:",         f"{comm_h:.1f}"),
                    ("Middling Sort:",   f"{mid_h:.1f}"),
                    ("Nobility:",        f"{nob_h:.1f}"),
                ]
                _draw_wealth_tooltip(screen, font, mouse_pos, chart_rect, lines)

    else:
        # Not enough data
        text = font.render("Not enough data yet", True, DARK_BROWN)
        text_rect = text.get_rect(center=chart_rect.center)
        screen.blit(text, text_rect)

    # 5. Draw Buttons
    button_labels = ["Wealth", "Money", "Stock", "Expenses", "Houses"]
    if population_manager is not None:
        button_labels += ["Population", "Happiness"]

    btn_width = (chart_rect.width - (button_margin * (len(button_labels) - 1))) / len(button_labels)

    current_x = chart_rect.left

    for label in button_labels:
        btn_rect = pygame.Rect(current_x, buttons_area_y, btn_width, button_height)

        # Store rect in game_state for click handling
        game_state.depot_chart_buttons[label] = btn_rect

        # Determine stats
        is_active = (label == active_chart)
        is_hovered = btn_rect.collidepoint(pygame.mouse.get_pos())

        # Colors
        if is_active:
            bg_color = PALE_BROWN
            border_color = BLACK
            text_color = BLACK
        elif is_hovered:
            bg_color = WHEAT
            border_color = DARK_BROWN
            text_color = DARK_BROWN
        else:
            bg_color = TAN
            border_color = DARK_BROWN
            text_color = DARK_BROWN

        # Draw button
        pygame.draw.rect(screen, bg_color, btn_rect)
        pygame.draw.rect(screen, border_color, btn_rect, 2)

        # Text
        text_surf = font.render(label, True, text_color)
        text_rect = text_surf.get_rect(center=btn_rect.center)
        screen.blit(text_surf, text_rect)

        current_x += btn_width + button_margin


def _draw_population_stacked_bars(
    screen: pygame.Surface,
    chart_rect: pygame.Rect,
    font: pygame.font.Font,
    population_manager: 'PopulationManager',
    current_date: datetime.datetime,
) -> None:
    """Draw a stacked bar chart of per-group population history."""
    GROUPS = ["Poor", "Commons", "Middling Sort", "Nobility"]
    GROUP_COLORS = {
        "Poor":          POP_COLOR_POOR,
        "Commons":       POP_COLOR_COMMONS,
        "Middling Sort": POP_COLOR_MIDDLING_SORT,
        "Nobility":      POP_COLOR_NOBILITY,
    }

    history = population_manager.population_history
    valid_groups = [g for g in GROUPS if g in history and len(history[g]) > 0]
    min_len = min(len(history[g]) for g in valid_groups) if valid_groups else 0

    if min_len < 1:
        text = font.render("Not enough data yet", True, DARK_BROWN)
        screen.blit(text, text.get_rect(center=chart_rect.center))
        return

    margin = 4
    bar_w = 12
    bar_gap = 2
    max_bars = (chart_rect.width - margin * 2) // (bar_w + bar_gap)
    start_idx = max(0, min_len - max_bars)

    max_total = max(
        sum(history[g][i] for g in valid_groups)
        for i in range(start_idx, min_len)
    )
    min_total = min(
        sum(history[g][i] for g in valid_groups)
        for i in range(start_idx, min_len)
    )
    if max_total == 0:
        max_total = 1
    y_max_scale = max_total * 1.1
    inner_h = chart_rect.height - margin * 2
    bar_bottom = chart_rect.bottom - margin

    _draw_bar_chart_grid(screen, font, chart_rect, bar_bottom, inner_h, y_max_scale)

    mouse_pos = pygame.mouse.get_pos()
    hover_info = None      # (group_name, val, bar_total, data_idx)
    hover_seg_rect = None  # rect of the hovered segment for outline
    hover_bar_info = None  # (total_px_h, bar_total) for horizontal line

    for bar_idx, data_idx in enumerate(range(start_idx, min_len)):
        bar_x = chart_rect.left + margin + bar_idx * (bar_w + bar_gap)
        cumulative_h = 0
        bar_total = sum(history[g][data_idx] for g in valid_groups)
        bar_is_hovered = False

        for group in GROUPS:
            if group not in valid_groups:
                continue
            val = history[group][data_idx]
            seg_h = round(val / y_max_scale * inner_h)
            if seg_h < 1 and val > 0:
                seg_h = 1
            seg_rect = pygame.Rect(bar_x, bar_bottom - cumulative_h - seg_h, bar_w, seg_h)
            pygame.draw.rect(screen, GROUP_COLORS[group], seg_rect)
            if seg_rect.collidepoint(mouse_pos):
                bar_is_hovered = True
                if hover_info is None:
                    hover_info = (group, val, bar_total, data_idx)
                    hover_seg_rect = seg_rect
            cumulative_h += seg_h

        if bar_is_hovered and hover_bar_info is None:
            total_px_h = round(bar_total / y_max_scale * inner_h)
            hover_bar_info = (total_px_h, bar_total)

    # Hover effects: segment outline + horizontal total line with value
    if hover_seg_rect:
        pygame.draw.rect(screen, WHITE, hover_seg_rect.inflate(2, 2), 2)
    if hover_bar_info:
        hb_total_px, hb_total = hover_bar_info
        line_y = bar_bottom - hb_total_px
        pygame.draw.line(screen, DARK_BROWN, (chart_rect.left, line_y), (chart_rect.right - 2, line_y), 1)
        val_surf = font.render(f"{hb_total:,}", True, DARK_BROWN)
        screen.blit(val_surf, (chart_rect.right - val_surf.get_width() - 4, line_y - val_surf.get_height() - 1))

    _draw_bar_stat_box(screen, font, chart_rect, max_total, min_total)

    # Title
    title_surf = font.render("Population History", True, DARK_BROWN)
    title_rect = title_surf.get_rect(midtop=(chart_rect.centerx, chart_rect.top + 8))
    screen.blit(title_surf, title_rect)
    pygame.draw.line(screen, DARK_BROWN, (title_rect.left, title_rect.bottom + 2), (title_rect.right, title_rect.bottom + 2), 1)

    if hover_info:
        group_name, val, bar_total, data_idx = hover_info
        days_ago = min_len - 1 - data_idx
        bar_date = (current_date - datetime.timedelta(days=days_ago)).strftime("%d.%m.%Y")
        pct = val / bar_total * 100 if bar_total else 0
        _draw_stacked_bar_tooltip(screen, font, mouse_pos, chart_rect,
                                  bar_date, "Group", group_name, val, pct, bar_total)


def _draw_stock_stacked_bars(
    screen: pygame.Surface,
    chart_rect: pygame.Rect,
    font: pygame.font.Font,
    depot: 'Depot',
    goods: List['Good'],
    current_date: datetime.datetime,
) -> None:
    """Draw a stacked bar chart of per-good stock history."""
    history = depot.stock_history
    valid_goods = [g for g in goods if g.name in history and len(history[g.name]) > 0]

    min_len = min(len(history[g.name]) for g in valid_goods) if valid_goods else 0

    if min_len < 1:
        text = font.render("Not enough data yet", True, DARK_BROWN)
        screen.blit(text, text.get_rect(center=chart_rect.center))
        return

    margin = 4
    bar_w = 12
    bar_gap = 2
    max_bars = (chart_rect.width - margin * 2) // (bar_w + bar_gap)
    start_idx = max(0, min_len - max_bars)

    max_total = max(
        sum(history[g.name][i] for g in valid_goods)
        for i in range(start_idx, min_len)
    )
    min_total = min(
        sum(history[g.name][i] for g in valid_goods)
        for i in range(start_idx, min_len)
    )
    if max_total == 0:
        max_total = 1
    y_max_scale = max_total * 1.1
    inner_h = chart_rect.height - margin * 2
    bar_bottom = chart_rect.bottom - margin

    _draw_bar_chart_grid(screen, font, chart_rect, bar_bottom, inner_h, y_max_scale)

    mouse_pos = pygame.mouse.get_pos()
    hover_info = None      # (good_name, val, bar_total, data_idx)
    hover_seg_rect = None  # rect of the hovered segment for outline
    hover_bar_info = None  # (total_px_h, bar_total) for horizontal line

    for bar_idx, data_idx in enumerate(range(start_idx, min_len)):
        bar_x = chart_rect.left + margin + bar_idx * (bar_w + bar_gap)
        cumulative_h = 0
        bar_total = sum(history[g.name][data_idx] for g in valid_goods)
        bar_is_hovered = False

        for good in valid_goods:
            val = history[good.name][data_idx]
            if val == 0:
                continue
            seg_h = round(val / y_max_scale * inner_h)
            if seg_h < 1:
                seg_h = 1
            seg_rect = pygame.Rect(bar_x, bar_bottom - cumulative_h - seg_h, bar_w, seg_h)
            pygame.draw.rect(screen, good.color, seg_rect)
            if seg_rect.collidepoint(mouse_pos):
                bar_is_hovered = True
                if hover_info is None:
                    hover_info = (good.name, val, bar_total, data_idx)
                    hover_seg_rect = seg_rect
            cumulative_h += seg_h

        if bar_is_hovered and hover_bar_info is None:
            total_px_h = round(bar_total / y_max_scale * inner_h)
            hover_bar_info = (total_px_h, bar_total)

    # Hover effects: segment outline + horizontal total line with value
    if hover_seg_rect:
        pygame.draw.rect(screen, WHITE, hover_seg_rect.inflate(2, 2), 2)
    if hover_bar_info:
        hb_total_px, hb_total = hover_bar_info
        line_y = bar_bottom - hb_total_px
        pygame.draw.line(screen, DARK_BROWN, (chart_rect.left, line_y), (chart_rect.right - 2, line_y), 1)
        val_surf = font.render(f"{hb_total:,}", True, DARK_BROWN)
        screen.blit(val_surf, (chart_rect.right - val_surf.get_width() - 4, line_y - val_surf.get_height() - 1))

    _draw_bar_stat_box(screen, font, chart_rect, max_total, min_total)

    # Title
    title_surf = font.render("Stock History", True, DARK_BROWN)
    title_rect = title_surf.get_rect(midtop=(chart_rect.centerx, chart_rect.top + 8))
    screen.blit(title_surf, title_rect)
    pygame.draw.line(screen, DARK_BROWN, (title_rect.left, title_rect.bottom + 2), (title_rect.right, title_rect.bottom + 2), 1)

    if hover_info:
        good_name, val, bar_total, data_idx = hover_info
        days_ago = min_len - 1 - data_idx
        bar_date = (current_date - datetime.timedelta(days=days_ago)).strftime("%d.%m.%Y")
        pct = val / bar_total * 100 if bar_total else 0
        _draw_stacked_bar_tooltip(screen, font, mouse_pos, chart_rect,
                                  bar_date, "Good", good_name, val, pct, bar_total)


def _draw_expenses_stacked_bars(
    screen: pygame.Surface,
    chart_rect: pygame.Rect,
    font: pygame.font.Font,
    depot: 'Depot',
    current_date: datetime.datetime,
) -> None:
    """Draw a stacked bar chart of daily expenses broken down by category."""
    # Category list: (display_name, history_list, color)
    # Good Cost is computed per-day from the totals.
    categories = [
        ("Cost of Living",     depot.cost_of_living_expenditure_history,  MATTE_BROWN),
        ("Good Cost",          None,                                      DARK_GREEN),
        ("Transaction Cost",   depot.transaction_expenditure_history,     STEELE_BLUE),
        ("Licenses",           depot.license_expenditure_history,         GOLD),
        ("Donations",          depot.donation_expenditure_history,        DARK_ORANGE),
        ("Loan Interest",      depot.loan_expenditure_history,            DARK_RED),
        ("Overdraft Penalty",  depot.overdraft_expenditure_history,       POP_COLOR_NOBILITY),
        ("Miscellaneous",      depot.miscellaneous_expenditure_history,   GRAY),
    ]

    total_hist = depot.expenditure_history
    total_len = len(total_hist)

    if total_len < 1:
        text = font.render("Not enough data yet", True, DARK_BROWN)
        screen.blit(text, text.get_rect(center=chart_rect.center))
        return

    # Align every subcategory history to the tail of expenditure_history.
    # Shorter histories (e.g. older saves missing miscellaneous) are padded
    # with leading zeros so the last entry still represents "today".
    def _align_to_tail(hist: list, n: int) -> list:
        if hist is None:
            return [0.0] * n
        if len(hist) >= n:
            return list(hist[-n:])
        return [0.0] * (n - len(hist)) + list(hist)

    min_len = total_len
    per_day: dict = {}
    for name, hist, _ in categories:
        per_day[name] = _align_to_tail(hist, total_len)
    for i in range(total_len):
        subtracted = sum(per_day[name][i] for name, hist, _ in categories if hist is not None)
        per_day["Good Cost"][i] = max(0.0, total_hist[i] - subtracted)

    margin = 4
    bar_w = 12
    bar_gap = 2
    max_bars = (chart_rect.width - margin * 2) // (bar_w + bar_gap)
    start_idx = max(0, min_len - max_bars)

    max_total = max(
        sum(per_day[name][i] for name, _, _ in categories)
        for i in range(start_idx, min_len)
    )
    min_total = min(
        sum(per_day[name][i] for name, _, _ in categories)
        for i in range(start_idx, min_len)
    )
    if max_total == 0:
        max_total = 1
    y_max_scale = max_total * 1.1
    bar_bottom = chart_rect.bottom - margin

    # Pre-compute legend + Max/Min layout so bars never overlap the header band.
    legend_items = [(name, color) for name, _, color in categories]
    rendered_labels = [font.render(name, True, DARK_BROWN) for name, _ in legend_items]
    leg_cols = 4
    leg_rows = (len(legend_items) + leg_cols - 1) // leg_cols
    swatch = 10
    lbl_h = rendered_labels[0].get_height()
    leg_row_gap = 2
    leg_col_gap = 10
    leg_pad_x, leg_pad_y = 6, 4

    # Per-column widths so narrow labels don't waste space
    col_widths = []
    for c in range(leg_cols):
        indices = [c + r * leg_cols for r in range(leg_rows) if c + r * leg_cols < len(rendered_labels)]
        col_widths.append(swatch + 4 + max(rendered_labels[i].get_width() for i in indices))

    # Max/Min column appended on the right of the legend box
    stat_lines = [("Max:", f"{max_total:,.0f}"), ("Min:", f"{min_total:,.0f}")]
    stat_rendered = [(font.render(lbl, True, CHART_BROWN), font.render(val, True, DARK_BROWN))
                     for lbl, val in stat_lines]
    stat_lbl_w = max(s.get_width() for s, _ in stat_rendered)
    stat_val_w = max(s.get_width() for _, s in stat_rendered)
    stat_col_w = stat_lbl_w + 4 + stat_val_w
    stat_sep = 10  # gap between category columns and stat column

    legend_w = leg_pad_x * 2 + sum(col_widths) + (leg_cols - 1) * leg_col_gap + stat_sep + stat_col_w
    legend_h = leg_pad_y * 2 + leg_rows * lbl_h + (leg_rows - 1) * leg_row_gap

    # Reserve vertical space at the top for title + legend so bars stay below.
    title_band_h = font.get_height() + 12  # title + underline spacing
    inner_top = chart_rect.top + margin + title_band_h + legend_h + 6
    inner_h = max(20, bar_bottom - inner_top)

    _draw_bar_chart_grid(screen, font, chart_rect, bar_bottom, inner_h, y_max_scale)

    mouse_pos = pygame.mouse.get_pos()
    hover_info = None
    hover_seg_rect = None
    hover_bar_info = None

    for bar_idx, data_idx in enumerate(range(start_idx, min_len)):
        bar_x = chart_rect.left + margin + bar_idx * (bar_w + bar_gap)
        cumulative_h = 0
        bar_total = sum(per_day[name][data_idx] for name, _, _ in categories)
        bar_is_hovered = False

        for name, _, color in categories:
            val = per_day[name][data_idx]
            if val <= 0:
                continue
            seg_h = round(val / y_max_scale * inner_h)
            if seg_h < 1:
                seg_h = 1
            seg_rect = pygame.Rect(bar_x, bar_bottom - cumulative_h - seg_h, bar_w, seg_h)
            pygame.draw.rect(screen, color, seg_rect)
            if seg_rect.collidepoint(mouse_pos):
                bar_is_hovered = True
                if hover_info is None:
                    hover_info = (name, val, bar_total, data_idx)
                    hover_seg_rect = seg_rect
            cumulative_h += seg_h

        if bar_is_hovered and hover_bar_info is None:
            total_px_h = round(bar_total / y_max_scale * inner_h)
            hover_bar_info = (total_px_h, bar_total)

    if hover_seg_rect:
        pygame.draw.rect(screen, WHITE, hover_seg_rect.inflate(2, 2), 2)
    if hover_bar_info:
        hb_total_px, hb_total = hover_bar_info
        line_y = bar_bottom - hb_total_px
        pygame.draw.line(screen, DARK_BROWN, (chart_rect.left, line_y), (chart_rect.right - 2, line_y), 1)
        val_surf = font.render(f"{hb_total:,.0f}", True, DARK_BROWN)
        screen.blit(val_surf, (chart_rect.right - val_surf.get_width() - 4, line_y - val_surf.get_height() - 1))

    title_surf = font.render("Expenses History", True, DARK_BROWN)
    title_rect = title_surf.get_rect(midtop=(chart_rect.centerx, chart_rect.top + 8))
    screen.blit(title_surf, title_rect)
    pygame.draw.line(screen, DARK_BROWN, (title_rect.left, title_rect.bottom + 2), (title_rect.right, title_rect.bottom + 2), 1)

    # Legend + Max/Min in a single panel below the title, centered horizontally.
    legend_x = chart_rect.centerx - legend_w // 2
    legend_y = title_rect.bottom + 6
    legend_rect = pygame.Rect(legend_x, legend_y, legend_w, legend_h)
    pygame.draw.rect(screen, SANDY_BROWN, legend_rect)
    pygame.draw.rect(screen, CHART_BROWN, legend_rect, 1)

    # Pre-compute x offset per column from cumulative column widths
    col_offsets = []
    acc = 0
    for w in col_widths:
        col_offsets.append(acc)
        acc += w + leg_col_gap

    # Category swatches (left portion)
    for idx, ((name, color), lbl_surf) in enumerate(zip(legend_items, rendered_labels)):
        r = idx // leg_cols
        c = idx % leg_cols
        cx = legend_x + leg_pad_x + col_offsets[c]
        cy = legend_y + leg_pad_y + r * (lbl_h + leg_row_gap)
        sw_rect = pygame.Rect(cx, cy + (lbl_h - swatch) // 2, swatch, swatch)
        pygame.draw.rect(screen, color, sw_rect)
        pygame.draw.rect(screen, DARK_BROWN, sw_rect, 1)
        screen.blit(lbl_surf, (cx + swatch + 4, cy))

    # Vertical divider before Max/Min column
    div_x = legend_x + leg_pad_x + sum(col_widths) + (leg_cols - 1) * leg_col_gap + stat_sep // 2
    pygame.draw.line(screen, CHART_BROWN, (div_x, legend_y + 3), (div_x, legend_y + legend_h - 3), 1)

    # Max/Min values (right column, vertically centred in the legend box)
    stat_x = div_x + stat_sep // 2 + 2
    total_stat_h = len(stat_rendered) * lbl_h + (len(stat_rendered) - 1) * leg_row_gap
    stat_y = legend_y + (legend_h - total_stat_h) // 2
    for lbl_surf, val_surf in stat_rendered:
        screen.blit(lbl_surf, (stat_x, stat_y))
        screen.blit(val_surf, (stat_x + stat_lbl_w + 4, stat_y))
        stat_y += lbl_h + leg_row_gap

    if hover_info:
        cat_name, val, bar_total, data_idx = hover_info
        days_ago = min_len - 1 - data_idx
        bar_date = (current_date - datetime.timedelta(days=days_ago)).strftime("%d.%m.%Y")
        pct = val / bar_total * 100 if bar_total else 0
        _draw_stacked_bar_tooltip(screen, font, mouse_pos, chart_rect,
                                  bar_date, "Category", cat_name, int(round(val)), pct, int(round(bar_total)))


def _draw_bar_chart_grid(
    screen: pygame.Surface,
    font: pygame.font.Font,
    chart_rect: pygame.Rect,
    bar_bottom: int,
    inner_h: int,
    y_max_scale: float,
) -> None:
    """Draw horizontal grid lines behind a stacked bar chart."""
    step = _nice_grid_step(y_max_scale)

    current_line = step
    while current_line < y_max_scale:
        line_y = bar_bottom - round(current_line / y_max_scale * inner_h)
        pygame.draw.line(screen, CHART_BROWN, (chart_rect.left, line_y), (chart_rect.right - 2, line_y), 1)
        label = font.render(f"{int(current_line):,}", True, CHART_BROWN)
        screen.blit(label, (chart_rect.left + 5, line_y - 12))
        current_line += step


def _draw_bar_stat_box(
    screen: pygame.Surface,
    font: pygame.font.Font,
    chart_rect: pygame.Rect,
    max_val: float,
    min_val: float,
) -> None:
    """Draw a small Max/Min info box in the top-right of the chart."""
    lines = [
        ("Max:", f"{max_val:,.0f}"),
        ("Min:", f"{min_val:,.0f}"),
    ]
    padding_x, padding_y, line_spacing, col_gap = 5, 4, 2, 6
    rendered = [(font.render(lbl, True, CHART_BROWN), font.render(val, True, DARK_BROWN))
                for lbl, val in lines]
    label_w = max(s.get_width() for s, _ in rendered)
    value_w = max(s.get_width() for _, s in rendered)
    line_h = rendered[0][0].get_height()
    box_w = padding_x * 2 + label_w + col_gap + value_w
    box_h = padding_y * 2 + len(lines) * line_h + (len(lines) - 1) * line_spacing
    box_x = chart_rect.right - box_w - 4
    box_y = chart_rect.top + 4
    box_rect = pygame.Rect(box_x, box_y, box_w, box_h)
    pygame.draw.rect(screen, SANDY_BROWN, box_rect)
    pygame.draw.rect(screen, CHART_BROWN, box_rect, 1)
    for i, (lbl_surf, val_surf) in enumerate(rendered):
        y = box_y + padding_y + i * (line_h + line_spacing)
        screen.blit(lbl_surf, (box_x + padding_x, y))
        screen.blit(val_surf, (box_x + padding_x + label_w + col_gap, y))


def _nice_grid_step(value_range: float, target_lines: int = 5) -> int:
    """Return a round step size that produces roughly target_lines grid lines."""
    if value_range <= 0:
        return 1
    raw = value_range / target_lines
    magnitude = 10 ** math.floor(math.log10(raw))
    residual = raw / magnitude
    if residual < 1.5:
        nice = 1
    elif residual < 3.5:
        nice = 2
    elif residual < 7.5:
        nice = 5
    else:
        nice = 10
    return max(1, int(round(nice * magnitude)))


def _draw_stacked_bar_tooltip(
    screen: pygame.Surface,
    font: pygame.font.Font,
    mouse_pos: tuple,
    chart_rect: pygame.Rect,
    bar_date: str,
    type_label: str,
    entry_name: str,
    val: int,
    pct: float,
    bar_total: int,
) -> None:
    """Render a 4-line tooltip for a stacked bar segment."""
    lines = [
        ("Date:",            bar_date),
        (f"{type_label}:",   entry_name),
        ("Amount:",          f"{val:,} ({pct:.1f}%)"),
        ("Total:",           f"{bar_total:,}"),
    ]

    padding_x = 8
    padding_y = 5
    line_spacing = 2
    col_gap = 8

    rendered = [(font.render(lbl, True, DARK_BROWN), font.render(val, True, BLACK))
                for lbl, val in lines]
    label_w = max(s.get_width() for s, _ in rendered)
    value_w = max(s.get_width() for _, s in rendered)
    line_h = rendered[0][0].get_height()

    tp_w = padding_x * 2 + label_w + col_gap + value_w
    tp_h = padding_y * 2 + len(lines) * line_h + (len(lines) - 1) * line_spacing

    tp_x = min(mouse_pos[0] + 12, chart_rect.right - tp_w - 2)
    tp_y = max(mouse_pos[1] - tp_h - 6, chart_rect.top + 2)
    tp_rect = pygame.Rect(tp_x, tp_y, tp_w, tp_h)

    pygame.draw.rect(screen, WHITE, tp_rect)
    pygame.draw.rect(screen, DARK_BROWN, tp_rect, 1)

    for i, (lbl_surf, val_surf) in enumerate(rendered):
        y = tp_y + padding_y + i * (line_h + line_spacing)
        screen.blit(lbl_surf, (tp_x + padding_x, y))
        screen.blit(val_surf, (tp_x + padding_x + label_w + col_gap, y))


def _draw_wealth_tooltip(
    screen: pygame.Surface,
    font: pygame.font.Font,
    mouse_pos: tuple,
    chart_rect: pygame.Rect,
    lines: list,
) -> None:
    """Render a multi-line tooltip for the wealth line chart."""
    padding_x = 8
    padding_y = 5
    line_spacing = 2
    col_gap = 8

    rendered = [(font.render(lbl, True, DARK_BROWN), font.render(val, True, BLACK))
                for lbl, val in lines]
    label_w = max(s.get_width() for s, _ in rendered)
    value_w = max(s.get_width() for _, s in rendered)
    line_h = rendered[0][0].get_height()

    tp_w = padding_x * 2 + label_w + col_gap + value_w
    tp_h = padding_y * 2 + len(lines) * line_h + (len(lines) - 1) * line_spacing

    tp_x = min(mouse_pos[0] + 12, chart_rect.right - tp_w - 2)
    tp_y = max(mouse_pos[1] - tp_h - 6, chart_rect.top + 2)
    tp_rect = pygame.Rect(tp_x, tp_y, tp_w, tp_h)

    pygame.draw.rect(screen, WHITE, tp_rect)
    pygame.draw.rect(screen, DARK_BROWN, tp_rect, 1)

    for i, (lbl_surf, val_surf) in enumerate(rendered):
        y = tp_y + padding_y + i * (line_h + line_spacing)
        screen.blit(lbl_surf, (tp_x + padding_x, y))
        screen.blit(val_surf, (tp_x + padding_x + label_w + col_gap, y))
