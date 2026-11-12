import pygame
import datetime
from typing import List, Dict, Any, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from ...models.good import Good
    from ...models.depot import Depot
    from ...game_state import GameState

from ...config.colors import *
from ...config.constants import SCREEN_WIDTH, SCREEN_HEIGHT, SIDEBAR_WIDTH
from ...sim.calendar import format_long

# Goods in the top bar: those pinned (right-click in the market view) and those the player
# holds, in goods.json order, one column of (upper, lower) per slot; only
# TOP_BAR_VISIBLE_COLUMNS fit at once, the arrows scroll through the rest.
TOP_BAR_VISIBLE_COLUMNS = 6
TOP_BAR_COLUMN_SPACING = 160
TOP_BAR_DATE_SEPARATOR_X = 466      # The money and the date are left of it, the goods right of it
# The goods end here, the warehouses and the total stock are right of it
TOP_BAR_STOCK_SEPARATOR_X = TOP_BAR_DATE_SEPARATOR_X + TOP_BAR_VISIBLE_COLUMNS * TOP_BAR_COLUMN_SPACING + 44


def top_bar_goods(game_state: "GameState") -> List[str]:
    """The goods the top bar shows: held or pinned, in goods.json order."""
    game = getattr(game_state, "game", None)
    if game is None or not hasattr(game, "goods"):
        return []
    held = game.depot.good_stock if hasattr(game, "depot") else {}
    pinned = set(getattr(game_state, "pinned_goods", []))
    return [g.name for g in game.goods if held.get(g.name, 0) > 0 or g.name in pinned]


def top_bar_columns(game_state: "GameState") -> List[Tuple[str, Optional[str]]]:
    """The top bar's goods two to a column."""
    names = top_bar_goods(game_state)
    return [(names[i], names[i + 1] if i + 1 < len(names) else None) for i in range(0, len(names), 2)]


def _get_town_for_stats(game_state: "GameState") -> Optional[Any]:
    """Get the town instance used for statistics display."""
    if not hasattr(game_state, 'game') or game_state.game is None:
        return None

    if not hasattr(game_state.game, 'game_map') or game_state.game.game_map is None:
        return None

    houses = getattr(game_state.game.game_map.tmx_map, 'houses', [])
    for house in houses:
        if hasattr(house, 'population_groups') and hasattr(house, 'max_citizens'):
            return house
    return None


def _draw_town_statistics_panel(
    screen: pygame.Surface,
    main_font: pygame.font.Font,
    game_state: "GameState"
) -> Optional[pygame.Rect]:
    """Draw bottom-bar replacement with core town population statistics."""
    town = _get_town_for_stats(game_state)
    if town is None:
        return None

    # Use small font for tooltip to match right-panel tooltips
    small_font = getattr(game_state, "small_font", main_font)

    mouse_pos = pygame.mouse.get_pos()
    menu_is_open = (
        (hasattr(game_state, 'game') and hasattr(game_state.game, 'menu') and game_state.game.menu.is_open)
        or bool(getattr(game_state, 'info_window', None))
    )

    current_population = int(getattr(town, 'citizens', 0))
    maximum_population = int(getattr(town, 'max_citizens', 0))
    happiness = float(getattr(town, 'happiness', 80))
    population_groups = getattr(town, 'population_groups', {})

    panel_padding_x = 20
    panel_y = SCREEN_HEIGHT - 53
    panel_h = 44
    icon_size = panel_h - 10  # 34px

    pop_icon = None
    if hasattr(game_state, 'game') and hasattr(game_state.game, 'images'):
        pop_icon = game_state.game.images.get('pictogram_population')

    count_surf = main_font.render(str(current_population), True, BLACK)
    gap = 6
    content_w = (icon_size + gap if pop_icon else 0) + count_surf.get_width()
    panel_w = content_w + 20  # 10px padding each side
    panel_rect = pygame.Rect(panel_padding_x, panel_y, panel_w, panel_h)

    is_hovered = panel_rect.collidepoint(mouse_pos) and not menu_is_open

    if is_hovered:
        pygame.draw.rect(screen, PALE_BROWN, panel_rect, border_radius=4)

    draw_x = panel_rect.x + 10
    if pop_icon:
        icon_rect = pop_icon.get_rect(midleft=(draw_x, panel_rect.centery))
        screen.blit(pop_icon, icon_rect)
        draw_x = icon_rect.right + gap
    text_rect = count_surf.get_rect(midleft=(draw_x, panel_rect.centery))
    screen.blit(count_surf, text_rect)

    tooltip_text = None
    tooltip_pos = None
    if is_hovered:
        tooltip_text = [
            ("Current:", f"{current_population} Souls"),
            ("Housing Capacity:", f"{maximum_population} Souls"),
            ("Housing Fillgrade:", f"{current_population / maximum_population * 100:.1f} %" if maximum_population else "N/A"),
            ("Happiness:", f"{happiness:.0f} %"),
            ("Poor:", f"{int(population_groups.get('Poor', 0))} Souls"),
            ("Commons:", f"{int(population_groups.get('Commons', 0))} Souls"),
            ("Middling Sort:", f"{int(population_groups.get('Middling Sort', 0))} Souls"),
            ("Nobility:", f"{int(population_groups.get('Nobility', 0))} Souls")
        ]
        tooltip_pos = mouse_pos

    if tooltip_text and tooltip_pos:
        # Pre-render surfaces to calculate dimensions using the smaller font
        line_data = []
        max_label_w = 0
        max_value_w = 0
        line_height = 0
        line_spacing = 6 # Vertical distance between lines
        
        for label, val in tooltip_text:
            label_surf = small_font.render(label, True, BLACK)
            val_surf = small_font.render(val, True, BLACK)
            line_data.append((label, label_surf, val_surf))
            max_label_w = max(max_label_w, label_surf.get_width())
            max_value_w = max(max_value_w, val_surf.get_width())
            line_height = max(line_height, label_surf.get_height())

        padding = 12
        column_gap = 40 # space between columns
        stripe_height = 10 # Extra height for the separator stripe
        
        tooltip_width = max_label_w + max_value_w + column_gap + (padding * 2)
        tooltip_height = (len(tooltip_text) * (line_height + line_spacing)) + (padding * 2) + stripe_height

        tooltip_rect = pygame.Rect(
            tooltip_pos[0] + 14,
            tooltip_pos[1] - tooltip_height - 8,
            tooltip_width,
            tooltip_height
        )

        if tooltip_rect.right > SCREEN_WIDTH:
            tooltip_rect.right = SCREEN_WIDTH - 8
        if tooltip_rect.left < 8:
            tooltip_rect.left = 8
        if tooltip_rect.top < 64:
            tooltip_rect.top = 64

        pygame.draw.rect(screen, WHITE, tooltip_rect)
        pygame.draw.rect(screen, DARK_BROWN, tooltip_rect, 1)

        line_y = tooltip_rect.top + padding
        for label, label_surf, val_surf in line_data:
            # Draw label left-aligned
            screen.blit(label_surf, (tooltip_rect.left + padding, line_y))
            # Draw value right-aligned within its column
            val_x = tooltip_rect.right - padding - val_surf.get_width()
            screen.blit(val_surf, (val_x, line_y))
            
            line_y += line_height + line_spacing

            # Draw a brown stripe under "Happiness"
            if label == "Happiness:":
                stripe_y = line_y - (line_spacing // 2) + 2
                pygame.draw.line(screen, DARK_BROWN, 
                                (tooltip_rect.left + padding, stripe_y), 
                                (tooltip_rect.right - padding, stripe_y), 2)
                line_y += 8 # Add space after the stripe

    return panel_rect

def draw_layout(
    screen: pygame.Surface,
    goods: List["Good"],
    main_depot: "Depot",
    main_font: pygame.font.Font,
    date: datetime.datetime,
    input_fields: Dict[str, str],
    mouse_clicked_on: Optional[str],
    images: Dict[str, Any],
    game_state: "GameState"
) -> Dict[str, pygame.Rect]:
    """Builds layout parts - background, top bar, middle section, and bottom bar.
    
    Each section is drawn by a dedicated helper function. Only right bar is drawn separately.
    """

    top_bar_buttons = _draw_top_bar(screen, main_depot, goods, main_font, date, images, game_state)
    buttons = _draw_bottom_bar(screen, goods, main_font, input_fields, mouse_clicked_on, game_state)
    buttons.update(top_bar_buttons)
    return buttons

def _draw_top_bar(
    screen: pygame.Surface,
    main_depot: "Depot",
    goods: List["Good"],
    main_font: pygame.font.Font,
    date: datetime.datetime,
    images: Dict[str, Any],
    game_state: "GameState"
) -> Dict[str, pygame.Rect]:
    """Draws the top bar with money, date, goods inventory, warehouses, and stock.

    Only TOP_BAR_VISIBLE_COLUMNS columns of goods fit; the rest are reached with the
    arrows either side of them, which scroll one column at a time. Returns the
    rects of the arrows that can be clicked.
    """

    money_50 = images['money_50']
    goods_images_30 = images['goods_30']
    stock_30 = images['stock_30']
    warehouses_30 = images['warehouses_30']

    top_bar = pygame.Rect(0, 0, SCREEN_WIDTH, 60)
    pygame.draw.rect(screen, LIGHT_GRAY, top_bar)
    pygame.draw.rect(screen, DARK_GRAY, top_bar, 2)

    # Money display with glow effect if active
    money_color = game_state.money_effect_color if hasattr(game_state, "money_effect_color") and game_state.money_effect_color else BLACK
    money_text = main_font.render(f"Money: {round(main_depot.money, 2)}", True, money_color)
    screen.blit(money_text, (70, 10))
    screen.blit(money_50, (10, 5))

    # Date display
    date_text = main_font.render(f"{format_long(date)} | {date.hour} o'clock", True, DARK_BROWN)
    screen.blit(date_text, (70, 35))

    # Separator bar
    pygame.draw.line(screen, DARK_GRAY, (TOP_BAR_DATE_SEPARATOR_X, 5), (TOP_BAR_DATE_SEPARATOR_X, 55), 2)

    # Goods inventory display
    start_x = TOP_BAR_DATE_SEPARATOR_X + 62
    spacing = TOP_BAR_COLUMN_SPACING
    mouse_pos = pygame.mouse.get_pos()

    # Build a name->Good lookup for price queries
    good_lookup = {g.name: g for g in goods}

    # Collect (good_name, slot_rect) for hover detection; draw after so tooltip is on top
    good_slots: List[tuple] = []

    offset = clamp_top_bar_offset(game_state)
    columns = top_bar_columns(game_state)
    visible_columns = columns[offset:offset + TOP_BAR_VISIBLE_COLUMNS]
    for i, column in enumerate(visible_columns):
        text_x = start_x + (i * spacing)
        for row, good_name in enumerate(column):
            if good_name is None:
                continue
            row_y = row * 29
            text = main_font.render(f"{good_name}: {round(main_depot.good_stock.get(good_name, 0), 2)}", True, BLACK)
            screen.blit(text, (text_x, row_y + 10 - row * 4))
            icon = goods_images_30.get(good_name)
            if icon:
                screen.blit(icon, (text_x - 35, row_y))
            slot_rect = pygame.Rect(text_x - 35, row_y, 35 + text.get_width(), 30 + row)
            good_slots.append((good_name, slot_rect))

    buttons = _draw_top_bar_arrows(screen, game_state, offset, mouse_pos)

    # Separator bar
    sep_x = TOP_BAR_STOCK_SEPARATOR_X
    pygame.draw.line(screen, DARK_GRAY, (sep_x, 5), (sep_x, 55), 2)

    # Warehouses counter
    screen.blit(warehouses_30, (sep_x + 20, 5))
    warehouses_text = main_font.render(f"Warehouses: {main_depot.warehouse_count}", True, BLACK)
    screen.blit(warehouses_text, (sep_x + 55, 10))

    # Merchant rank, right-aligned beside the warehouses; red while it is slipping
    rank_rect = _draw_top_bar_rank(screen, main_font, game_state, mouse_pos)
    if rank_rect:
        buttons['merchant_rank'] = rank_rect

    # Total Stock counter
    screen.blit(stock_30, (sep_x + 20, 30))
    total_stock = sum(main_depot.good_stock.values())
    stock_text = main_font.render(f"Total Stock: {total_stock} / {main_depot.total_capacity()}", True, BLACK)
    screen.blit(stock_text, (sep_x + 55, 35))
    total_stock_rect = pygame.Rect(sep_x + 20, 29, 30 + stock_text.get_width(), 31)

    # Draw hover tooltip last so it renders above all other top-bar elements
    small_font = getattr(game_state, 'small_font', main_font)
    if total_stock_rect.collidepoint(mouse_pos) and total_stock > 0:
        _draw_top_bar_total_tooltip(screen, main_font, small_font, main_depot, good_lookup, date, mouse_pos)
    else:
        for good_name, slot_rect in good_slots:
            if slot_rect.collidepoint(mouse_pos):
                _draw_top_bar_good_tooltip(screen, main_font, small_font, main_depot, good_lookup, good_name, date, mouse_pos)
                break

    return buttons


def _draw_top_bar_rank(screen: pygame.Surface, main_font: pygame.font.Font,
                       game_state: "GameState", mouse_pos: tuple) -> Optional[pygame.Rect]:
    """Draw the rank title at the right end of the top bar's first row; returns its clickable rect."""
    merchant_rank = getattr(getattr(game_state, 'game', None), 'merchant_rank', None)
    if merchant_rank is None:
        return None
    slipping = merchant_rank.grace_since is not None
    text = main_font.render(merchant_rank.rank.name, True, DARK_RED if slipping else DARK_BROWN)
    rect = text.get_rect(topright=(SCREEN_WIDTH - 12, 10)).inflate(8, 4)
    if rect.collidepoint(mouse_pos) and not getattr(game_state, 'info_window', None):
        hover = pygame.Surface(rect.size, pygame.SRCALPHA)
        hover.fill((0, 0, 0, 30))
        screen.blit(hover, rect)
    screen.blit(text, text.get_rect(center=rect.center))
    return rect


def clamp_top_bar_offset(game_state: "GameState") -> int:
    """Keep the top bar's scroll offset within the columns there are, and return it."""
    max_offset = max(0, len(top_bar_columns(game_state)) - TOP_BAR_VISIBLE_COLUMNS)
    offset = min(max(getattr(game_state, 'top_bar_goods_offset', 0), 0), max_offset)
    game_state.top_bar_goods_offset = offset
    return offset


def scroll_top_bar(game_state: "GameState", step: int) -> None:
    """Move the top bar's goods one or more columns to the left (-) or right (+)."""
    game_state.top_bar_goods_offset = getattr(game_state, 'top_bar_goods_offset', 0) + step
    clamp_top_bar_offset(game_state)


def _draw_top_bar_arrows(
    screen: pygame.Surface,
    game_state: "GameState",
    offset: int,
    mouse_pos: tuple,
) -> Dict[str, pygame.Rect]:
    """Draw the goods' scroll arrows; returns the rects of those that lead somewhere."""
    column_count = len(top_bar_columns(game_state))
    if column_count <= TOP_BAR_VISIBLE_COLUMNS:
        return {}

    max_offset = column_count - TOP_BAR_VISIBLE_COLUMNS
    menu_is_open = (
        (hasattr(game_state, 'game') and hasattr(game_state.game, 'menu') and game_state.game.menu.is_open)
        or bool(getattr(game_state, 'info_window', None))
    )
    arrows = [
        ('top_bar_left', pygame.Rect(TOP_BAR_DATE_SEPARATOR_X + 6, 8, 18, 44), -1, offset > 0),
        ('top_bar_right', pygame.Rect(TOP_BAR_STOCK_SEPARATOR_X - 22, 8, 18, 44), 1, offset < max_offset),
    ]
    buttons = {}
    for key, rect, direction, enabled in arrows:
        hovered = enabled and not menu_is_open and rect.collidepoint(mouse_pos)
        if hovered:
            pygame.draw.rect(screen, PALE_BROWN, rect, border_radius=4)
        color = (WHITE if hovered else DARK_BROWN) if enabled else GRAY
        tip_x = rect.centerx + direction * 5
        back_x = rect.centerx - direction * 5
        points = [(back_x, rect.centery - 12), (tip_x, rect.centery), (back_x, rect.centery + 12)]
        pygame.draw.lines(screen, color, False, points, 3)
        if enabled:
            buttons[key] = rect
    return buttons

def _draw_top_bar_total_tooltip(
    screen: pygame.Surface,
    main_font: pygame.font.Font,
    small_font: pygame.font.Font,
    depot: "Depot",
    good_lookup: Dict[str, Any],
    date: datetime.datetime,
    mouse_pos: tuple,
) -> None:
    """Draw an aggregated tooltip for the Total Stock indicator."""
    all_good_names = list(depot.good_stock.keys())

    total_market_value = 0.0
    total_purchase_value = 0.0
    for good_name in all_good_names:
        qty = depot.good_stock.get(good_name, 0)
        if qty > 0:
            good = good_lookup.get(good_name)
            total_market_value += (good.get_price() if good else 0.0) * qty
            avg = depot.avg_buy_price(good_name)
            total_purchase_value += (avg * qty) if avg is not None else 0.0

    total_pl = total_market_value - total_purchase_value
    pl_color = DARK_GREEN if total_pl >= 0 else DARK_RED
    pl_sign = "+" if total_pl >= 0 else ""

    stocked_names = [n for n in all_good_names if depot.good_stock.get(n, 0) > 0]
    licenses_held = sum(1 for n in stocked_names if depot.has_license(n, date))
    license_text = f"{licenses_held}/{len(stocked_names)}"
    license_color = DARK_GREEN if licenses_held == len(stocked_names) else DARK_RED

    rows = [
        ("Market Value:", f"{total_market_value:.2f}", DARK_BROWN),
        ("Purchase Value:", f"{total_purchase_value:.2f}", DARK_BROWN),
        ("P/L:", f"{pl_sign}{total_pl:.2f}", pl_color),
        ("Licenses:", license_text, license_color),
    ]

    row_spacing = 3
    col_gap = 12
    pad_x, pad_y = 8, 6

    label_surfs = [main_font.render(label, True, DARK_BROWN) for label, _, _ in rows]
    license_idx = len(rows) - 1
    value_surfs = [
        small_font.render(val, True, color) if i == license_idx else main_font.render(val, True, color)
        for i, (_, val, color) in enumerate(rows)
    ]
    stable_value_surfs = [
        small_font.render("".join('9' if c.isdigit() else c for c in val), True, DARK_BROWN) if i == license_idx
        else main_font.render("".join('9' if c.isdigit() else c for c in val), True, DARK_BROWN)
        for i, (_, val, _) in enumerate(rows)
    ]

    label_col_w = max(s.get_width() for s in label_surfs)
    value_col_w = max(s.get_width() for s in stable_value_surfs)
    line_h = label_surfs[0].get_height()
    total_w = label_col_w + col_gap + value_col_w
    total_h = len(rows) * line_h + (len(rows) - 1) * row_spacing

    tip_x = mouse_pos[0] + 34
    tip_y = mouse_pos[1] + 38
    bg_rect = pygame.Rect(tip_x - pad_x, tip_y - pad_y, total_w + pad_x * 2, total_h + pad_y * 2)

    if bg_rect.right > SCREEN_WIDTH:
        bg_rect.right = SCREEN_WIDTH - 4

    pygame.draw.rect(screen, WHITE, bg_rect)
    pygame.draw.rect(screen, DARK_BROWN, bg_rect, 1)

    y = bg_rect.top + pad_y
    value_x = bg_rect.left + pad_x + label_col_w + col_gap
    for label_surf, value_surf in zip(label_surfs, value_surfs):
        screen.blit(label_surf, (bg_rect.left + pad_x, y))
        v_offset = (line_h - value_surf.get_height()) // 2
        screen.blit(value_surf, (value_x, y + v_offset))
        y += line_h + row_spacing


def _draw_top_bar_good_tooltip(
    screen: pygame.Surface,
    main_font: pygame.font.Font,
    small_font: pygame.font.Font,
    depot: "Depot",
    good_lookup: Dict[str, Any],
    good_name: str,
    date: datetime.datetime,
    mouse_pos: tuple,
) -> None:
    """Draw a detailed tooltip for a good in the top bar inventory row."""
    qty = depot.good_stock.get(good_name, 0)
    good = good_lookup.get(good_name)
    current_price = good.get_price() if good else 0.0

    market_value = current_price * qty
    avg = depot.avg_buy_price(good_name) if qty > 0 else None
    purchase_value = avg * qty if avg is not None else 0.0
    pl = market_value - purchase_value

    has_license = depot.has_license(good_name, date)
    license_value_text = "YES" if has_license else "NO"
    license_color = DARK_GREEN if has_license else DARK_RED
    pl_color = DARK_GREEN if pl >= 0 else DARK_RED
    pl_sign = "+" if pl >= 0 else ""

    # Two-column layout: (label, value_text, value_color)
    rows = []
    if qty > 0:
        rows += [
            ("Market Value:", f"{market_value:.2f}", DARK_BROWN),
            ("Purchase Value:", f"{purchase_value:.2f}", DARK_BROWN),
            ("P/L:", f"{pl_sign}{pl:.2f}", pl_color),
        ]
    rows.append(("License:", license_value_text, license_color))

    row_spacing = 3
    col_gap = 12
    pad_x, pad_y = 8, 6

    label_surfs = [main_font.render(label, True, DARK_BROWN) for label, _, _ in rows]
    # License row uses small_font; all others use main_font
    license_idx = len(rows) - 1
    value_surfs = [
        small_font.render(val, True, color) if i == license_idx else main_font.render(val, True, color)
        for i, (_, val, color) in enumerate(rows)
    ]
    stable_value_surfs = [
        small_font.render("".join('9' if c.isdigit() else c for c in val), True, DARK_BROWN) if i == license_idx
        else main_font.render("".join('9' if c.isdigit() else c for c in val), True, DARK_BROWN)
        for i, (_, val, _) in enumerate(rows)
    ]

    label_col_w = max(s.get_width() for s in label_surfs)
    value_col_w = max(s.get_width() for s in stable_value_surfs)
    line_h = label_surfs[0].get_height()
    total_w = label_col_w + col_gap + value_col_w
    total_h = len(rows) * line_h + (len(rows) - 1) * row_spacing

    tip_x = mouse_pos[0] + 34
    tip_y = mouse_pos[1] + 38
    bg_rect = pygame.Rect(tip_x - pad_x, tip_y - pad_y, total_w + pad_x * 2, total_h + pad_y * 2)

    if bg_rect.right > SCREEN_WIDTH:
        bg_rect.right = SCREEN_WIDTH - 4

    pygame.draw.rect(screen, WHITE, bg_rect)
    pygame.draw.rect(screen, DARK_BROWN, bg_rect, 1)

    y = bg_rect.top + pad_y
    value_x = bg_rect.left + pad_x + label_col_w + col_gap
    for label_surf, value_surf in zip(label_surfs, value_surfs):
        screen.blit(label_surf, (bg_rect.left + pad_x, y))
        # vertically center the value within the row height
        v_offset = (line_h - value_surf.get_height()) // 2
        screen.blit(value_surf, (value_x, y + v_offset))
        y += line_h + row_spacing


def _draw_bottom_bar(
    screen: pygame.Surface,
    goods: List["Good"],
    main_font: pygame.font.Font,
    input_fields: Dict[str, str],
    mouse_clicked_on: Optional[str],
    game_state: "GameState"
) -> Dict[str, pygame.Rect]:
    """Draws the bottom bar with the town's population.

    Trading is done on the market view's trade desk (layout_modules/trade_desk.py).
    Time controls and sound controls are drawn separately in their own modules.
    """
    bottom_bar = pygame.Rect(0, SCREEN_HEIGHT-60, SCREEN_WIDTH, 60)
    pygame.draw.rect(screen, LIGHT_GRAY, bottom_bar)
    pygame.draw.rect(screen, DARK_GRAY, bottom_bar, 2)

    buttons = {}
    town_rect = _draw_town_statistics_panel(screen, main_font, game_state)
    if town_rect:
        buttons['town_population'] = town_rect
    _draw_tiredness_panel(screen, game_state, (town_rect.right if town_rect else 0) + 30)
    return buttons


TIREDNESS_BAR_SIZE = (150, 16)


def _draw_tiredness_panel(screen: pygame.Surface, game_state: "GameState", left: int) -> None:
    """The player's tiredness as a bar beside the population, with a tooltip saying what it is."""
    from ..helper_modules.rest_window import draw_tiredness_bar
    from ...models.rest import FULL_REST_HOURS, HOURS_TO_EXHAUSTION
    game = getattr(game_state, 'game', None)
    player = getattr(game, 'player', None)
    if player is None:
        return
    font = getattr(game_state, "small_font", None) or game_state.font
    label = font.render("Tiredness", True, BLACK)
    centre_y = SCREEN_HEIGHT - 30
    screen.blit(label, label.get_rect(midleft=(left, centre_y)))
    bar = pygame.Rect(0, 0, *TIREDNESS_BAR_SIZE)
    bar.midleft = (left + label.get_width() + 10, centre_y)
    draw_tiredness_bar(screen, bar, player.tiredness)
    area = pygame.Rect(left, centre_y - 20, bar.right - left, 40)
    mouse_pos = pygame.mouse.get_pos()
    if not area.collidepoint(mouse_pos) or getattr(game_state, 'info_window', None):
        return
    intro = getattr(game, 'intro', None)
    where = ("Rest at Uncle Gared's shop to recover." if intro is not None and intro.stage == "done"
             else "Find a roof to rest under.")
    lines = [f"Tiredness: {player.tiredness * 100:.0f} %",
             f"Worn out after {HOURS_TO_EXHAUSTION:.0f} hours up; {FULL_REST_HOURS:.0f} hours of rest clear it.",
             where]
    surfs = [font.render(line, True, BLACK) for line in lines]
    pad = 10
    tip = pygame.Rect(0, 0, max(s.get_width() for s in surfs) + 2 * pad,
                      sum(s.get_height() + 4 for s in surfs) + 2 * pad - 4)
    tip.bottomleft = (mouse_pos[0] + 14, mouse_pos[1] - 8)
    tip.right = min(tip.right, SCREEN_WIDTH - 8)
    pygame.draw.rect(screen, WHITE, tip)
    pygame.draw.rect(screen, DARK_BROWN, tip, 1)
    y = tip.top + pad
    for surf in surfs:
        screen.blit(surf, (tip.left + pad, y))
        y += surf.get_height() + 4

def draw_right_bar(screen: pygame.Surface, images: Dict[str, Any], buttons: Dict[str, pygame.Rect], main_font: pygame.font.Font, game_state: "GameState") -> None:
    """Draws the right sidebar for menu options with pictogram buttons and sub-buttons.
    
    The menu button is drawn separately in the menu module.
    
    Args:
        screen: The pygame surface to draw on.
        images: Dictionary of pre-loaded pictogram images.
        buttons: Dictionary to store the clickable button rects.
        main_font: Font for tooltip rendering.
        game_state: The current game state object.
    """
    right_bar = pygame.Rect(SCREEN_WIDTH, 0, SIDEBAR_WIDTH, SCREEN_HEIGHT)
    pygame.draw.rect(screen, LIGHT_GRAY, right_bar)
    pygame.draw.rect(screen, DARK_GRAY, right_bar, 1)

    # Get mouse position for hover effects
    mouse_pos = pygame.mouse.get_pos()
    
    # Check if menu is open - if so, disable all hover effects on other buttons
    menu_is_open = (
        (hasattr(game_state, 'game') and hasattr(game_state.game, 'menu') and game_state.game.menu.is_open)
        or bool(getattr(game_state, 'info_window', None))
    )
    
    tooltips = []

    # Draw pictograms for side menu
    pictogram_names = ["map", "market", "depot", "politics", "trade_routes", "building", "ledger"]
    label_map = {
        "map": "Explore",
        "market": "Market",
        "depot": "Depot",
        "politics": "Politics",
        "trade_routes": "Trade Routes",
        "building": "Town Map",
        "ledger": "Ledger",
    }

    start_y = 75    # the higher the number the lower the first button
    spacing = -15   # the higher the number (also pos), the further apart the buttons
    
    # Buttons that open a modal instead of switching layout modules — no sub-buttons
    modal_buttons = {"ledger"}

    for i, name in enumerate(pictogram_names):
        img_key = f"pictogram_{name}"
        rect = pygame.Rect(SCREEN_WIDTH + 5, start_y + i * (100 + spacing), 100, 100)
        visible_rect = pygame.Rect(rect.x, rect.y, 100, 50)

        if img_key in images:
            img = images[img_key]

            if name not in modal_buttons:
                # Sub-buttons logic
                sub_btn_y = rect.bottom - 100 + 45
                sub_btn_width = 47
                sub_btn_height = 20

                # Left button "picto_<name>_left"
                left_btn_rect = pygame.Rect(rect.left+2, sub_btn_y, sub_btn_width, sub_btn_height)
                is_left_hovered = left_btn_rect.collidepoint(mouse_pos) and not menu_is_open
                color_left = PALE_BROWN if is_left_hovered else TAN
                pygame.draw.rect(screen, color_left, left_btn_rect)
                pygame.draw.rect(screen, DARK_BROWN, left_btn_rect, 1) # 1px border
                buttons[f"picto_{name}_left"] = left_btn_rect
                if is_left_hovered:
                    tooltips.append(("Open left", mouse_pos))

                # Right button "picto_<name>_right"
                right_btn_rect = pygame.Rect(rect.right-2 - sub_btn_width, sub_btn_y, sub_btn_width, sub_btn_height)
                is_right_hovered = right_btn_rect.collidepoint(mouse_pos) and not menu_is_open
                color_right = PALE_BROWN if is_right_hovered else TAN
                pygame.draw.rect(screen, color_right, right_btn_rect)
                pygame.draw.rect(screen, DARK_BROWN, right_btn_rect, 1) # 1px border
                buttons[f"picto_{name}_right"] = right_btn_rect
                if is_right_hovered:
                    tooltips.append(("Open right", mouse_pos))
            else:
                is_left_hovered = False
                is_right_hovered = False

            # Draw main pictogram image after left and right buttons so it overlaps the buttons by 2 pixels
            screen.blit(img, rect)
            buttons[f"pictogram_{name}"] = visible_rect

            # Main pictogram hover effect
            is_pictogram_hovered = visible_rect.collidepoint(mouse_pos) and not is_left_hovered and not is_right_hovered and not menu_is_open
            if is_pictogram_hovered:
                # redraw pictogram a bit darker to indicate hover
                overlay = pygame.Surface((visible_rect.width, visible_rect.height), pygame.SRCALPHA)
                overlay.fill((0, 0, 0, 50))  # black overlay
                screen.blit(overlay, visible_rect.topleft)
                # add tooltip
                tooltips.append((label_map[name], mouse_pos))

        elif name in modal_buttons:
            # Fallback tile for modal buttons with no image asset yet
            pygame.draw.rect(screen, TAN, visible_rect)
            pygame.draw.rect(screen, DARK_BROWN, visible_rect, 2)
            lbl = main_font.render(label_map[name], True, DARK_BROWN)
            screen.blit(lbl, lbl.get_rect(center=visible_rect.center))
            buttons[f"pictogram_{name}"] = visible_rect
            if visible_rect.collidepoint(mouse_pos) and not menu_is_open:
                overlay = pygame.Surface(visible_rect.size, pygame.SRCALPHA)
                overlay.fill((0, 0, 0, 40))
                screen.blit(overlay, visible_rect.topleft)
                tooltips.append((label_map[name], mouse_pos))

    # Render tooltips last to ensure they are on top of everything
    for text, pos in tooltips:
        tooltip_surf = main_font.render(text, True, BLACK)
        # Position tooltip to the left of the side bar
        tooltip_rect = tooltip_surf.get_rect(topright=(pos[0] - 20, pos[1] + 10))
        
        # Ensure tooltip stays on screen
        if tooltip_rect.left < 0:
            tooltip_rect.left = 10
            
        pygame.draw.rect(screen, WHITE, tooltip_rect.inflate(10, 6))
        pygame.draw.rect(screen, DARK_BROWN, tooltip_rect.inflate(10, 6), 1)
        screen.blit(tooltip_surf, tooltip_rect)
