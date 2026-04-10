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
    elif len(data_points) > 1:
        # Determine scaling
        # We show a maximum of X points, similar to market chart, or adjust to fit
        # For now, let's limit to the last N points that fit (e.g., width of chart)
        max_points = chart_rect.width
        visible_data = data_points[-int(max_points):]

        if not visible_data:
            visible_data = [0]

        min_val = min(visible_data)
        max_val = max(visible_data)

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
        if len(points) > 1:
            mouse_pos_early = pygame.mouse.get_pos()
            is_hovering = chart_rect.collidepoint(mouse_pos_early) and active_chart in ("Wealth", "Money", "Happiness")
            line_width = 3 if is_hovering else 2
            pygame.draw.lines(screen, color, False, points, line_width)

        # Draw horizontal orientation lines
        # Determine a nice step size based on max value
        if max_val < 10:
            step = 2
        elif max_val < 50:
            step = 10
        elif max_val < 200:
            step = 50
        elif max_val < 1000:
            step = 100
        elif max_val < 5000:
            step = 500
        else:
            step = 1000

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

        # Draw min/max labels
        max_label = font.render(f"{max_val:,.1f}", True, DARK_BROWN)
        min_label = font.render(f"{min_val:,.1f}", True, DARK_BROWN)

        screen.blit(max_label, (chart_rect.left + 5, chart_rect.top + 5))
        screen.blit(min_label, (chart_rect.left + 5, chart_rect.bottom - 25))

        # Draw Title
        title_surf = font.render(f"{label} History", True, DARK_BROWN)
        title_rect = title_surf.get_rect(midtop=(chart_rect.centerx, chart_rect.top + 8))
        screen.blit(title_surf, title_rect)
        underline_y = title_rect.bottom + 2
        pygame.draw.line(screen, DARK_BROWN, (title_rect.left, underline_y), (title_rect.right, underline_y), 1)

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
            # Draw dot at intersection
            dot_pos = (int(points[vis_idx][0]), int(points[vis_idx][1]))
            pygame.draw.circle(screen, color, dot_pos, 4)
            pygame.draw.circle(screen, DARK_BROWN, dot_pos, 4, 1)

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
    button_labels = ["Wealth", "Money", "Stock", "Houses"]
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
    if max_total == 0:
        max_total = 1
    y_max_scale = max_total * 1.1
    inner_h = chart_rect.height - margin * 2

    mouse_pos = pygame.mouse.get_pos()
    hover_info = None  # (group_name, val, bar_total, data_idx)

    for bar_idx, data_idx in enumerate(range(start_idx, min_len)):
        bar_x = chart_rect.left + margin + bar_idx * (bar_w + bar_gap)
        bar_bottom = chart_rect.bottom - margin
        cumulative_h = 0
        bar_total = sum(history[g][data_idx] for g in valid_groups)

        for group in GROUPS:
            if group not in valid_groups:
                continue
            val = history[group][data_idx]
            seg_h = round(val / y_max_scale * inner_h)
            if seg_h < 1 and val > 0:
                seg_h = 1
            seg_rect = pygame.Rect(bar_x, bar_bottom - cumulative_h - seg_h, bar_w, seg_h)
            pygame.draw.rect(screen, GROUP_COLORS[group], seg_rect)
            if hover_info is None and seg_rect.collidepoint(mouse_pos):
                hover_info = (group, val, bar_total, data_idx)
            cumulative_h += seg_h

    # Y-axis scale label
    max_label = font.render(f"{max_total:,}", True, DARK_BROWN)
    screen.blit(max_label, (chart_rect.left + 5, chart_rect.top + 5))

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
    if max_total == 0:
        max_total = 1
    y_max_scale = max_total * 1.1
    inner_h = chart_rect.height - margin * 2

    mouse_pos = pygame.mouse.get_pos()
    hover_info = None  # (good_name, val, bar_total, data_idx)

    for bar_idx, data_idx in enumerate(range(start_idx, min_len)):
        bar_x = chart_rect.left + margin + bar_idx * (bar_w + bar_gap)
        bar_bottom = chart_rect.bottom - margin
        cumulative_h = 0
        bar_total = sum(history[g.name][data_idx] for g in valid_goods)

        for good in valid_goods:
            val = history[good.name][data_idx]
            if val == 0:
                continue
            seg_h = round(val / y_max_scale * inner_h)
            if seg_h < 1:
                seg_h = 1
            seg_rect = pygame.Rect(bar_x, bar_bottom - cumulative_h - seg_h, bar_w, seg_h)
            pygame.draw.rect(screen, good.color, seg_rect)
            if hover_info is None and seg_rect.collidepoint(mouse_pos):
                hover_info = (good.name, val, bar_total, data_idx)
            cumulative_h += seg_h

    # Y-axis max label
    max_label = font.render(f"{max_total:,}", True, DARK_BROWN)
    screen.blit(max_label, (chart_rect.left + 5, chart_rect.top + 5))

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
