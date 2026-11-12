"""The trade desk: the market view's column of order cards, beside the price chart.

Every good shown in the chart (three at the most) has a card where its line
ends: its price and how it moved in a day, what the market holds, what the
player holds of it and what that is worth, a quantity, and a Buy and a Sell
button that say what the order comes to before it is placed. Under each button
stands the price per unit with the fee and the most that could be traded, a
click on which takes it as the quantity. The card's last line says why an
order cannot be placed, or, with the pointer on a button, what it does to the
price and what a sale earns.

The cards are in the order the goods were put in the chart, so F1/F2, F3/F4
and F5/F6 keep meaning the first, second and third card. The numbers come from
``src/models/trade_offer.py``; this module lays the cards out, draws them and
hands their hitboxes to ``GameState.trade_buttons`` for the mouse handler.
"""
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import pygame

from ...config.colors import (BLACK, BUTTON_TEXT, BUY_BUTTON, BUY_BUTTON_BORDER, BUY_BUTTON_HOVER, DARK_BROWN,
                              DARK_GRAY, DARK_GREEN, DARK_RED, GRAY, LIGHT_GRAY, PALE_BROWN, PARCHMENT,
                              SELL_BUTTON, SELL_BUTTON_BORDER, SELL_BUTTON_HOVER, TAN, WHITE)
from ...config.constants import PRICE_TICKS_PER_DAY
from ...models.trade_offer import MAX_QUANTITY, Offer, buy_offer, market_block, sell_offer

if TYPE_CHECKING:
    from ...game_state import GameState
    from ...models.depot import Depot
    from ...models.good import Good

DESK_WIDTH = 300                # the column's width, taken from the chart's right
CARD_HEIGHT = 274
CARD_GAP = 8
SECTIONS = ("one", "two", "three")                      # the cards, as the input fields name them
HOTKEYS = (("F1", "F2"), ("F3", "F4"), ("F5", "F6"))    # each card's Buy and Sell key
DETAIL_COLOR = (110, 86, 58)    # the small print
RULE_COLOR = (200, 178, 132)    # the lines between a card's parts
FIELD_COLOR = (250, 244, 224)
DISABLED_TEXT = (128, 128, 128)
LICENCE_WARN_DAYS = 2           # a licence ending within this many days is mentioned on its card


@dataclass
class Card:
    """One card's place on the desk and the hitboxes on it."""
    section: str
    hotkeys: Tuple[str, str]
    rect: pygame.Rect
    good: Optional["Good"] = None
    parts: Dict[str, pygame.Rect] = field(default_factory=dict)


@dataclass
class Preview:
    """What the chart shows for the button under the pointer: where the order leaves the price."""
    good: "Good"
    price_after: float
    buying: bool


def layout_cards(desk: pygame.Rect, goods: List[Optional["Good"]]) -> List[Card]:
    """The desk's three cards from the top, each with its good (None for a free place) and its hitboxes."""
    cards = []
    for i, section in enumerate(SECTIONS):
        rect = pygame.Rect(desk.x + 6, desk.y + CARD_GAP + i * (CARD_HEIGHT + CARD_GAP), desk.width - 12, CARD_HEIGHT)
        good = goods[i] if i < len(goods) else None
        card = Card(section, HOTKEYS[i], rect, good)
        if good is not None:
            card.parts = _card_parts(rect)
        cards.append(card)
    return cards


def _card_parts(card: pygame.Rect) -> Dict[str, pygame.Rect]:
    """The hitboxes on a card: the quantity row, the two buttons and the two limits under them."""
    left, width = card.x + 14, card.width - 24
    parts: Dict[str, pygame.Rect] = {}
    row_y, gap = card.y + 112, 6
    widths = [("half", 38), ("minus", 32), ("quantity", width - 2 * 38 - 2 * 32 - 4 * gap), ("plus", 32), ("double", 38)]
    x = left
    for key, part_width in widths:
        parts[key] = pygame.Rect(x, row_y, part_width, 32)
        x += part_width + gap
    button_y, button_w = row_y + 40, (width - 8) // 2
    parts["buy"] = pygame.Rect(left, button_y, button_w, 50)
    parts["sell"] = pygame.Rect(left + button_w + 8, button_y, button_w, 50)
    parts["maxbuy"] = pygame.Rect(left, button_y + 72, button_w, 20)
    parts["maxsell"] = pygame.Rect(left + button_w + 8, button_y + 72, button_w, 20)
    return parts


def hovered_good(cards: List[Card], mouse_pos: Tuple[int, int]) -> Optional["Good"]:
    """The good whose card the pointer is on."""
    for card in cards:
        if card.good is not None and card.rect.collidepoint(mouse_pos):
            return card.good
    return None


def quantity_of(game_state: "GameState", section: str) -> int:
    """The quantity typed on a card; nothing typed is 0."""
    text = game_state.input_fields.get(f"quantity_{section}", "")
    return min(int(text), MAX_QUANTITY) if text.isdigit() else 0


_offer_cache: Dict[str, Tuple[tuple, Tuple[Offer, Offer]]] = {}


def offers(good: "Good", quantity: int, depot: "Depot", game_state: "GameState") -> Tuple[Offer, Offer]:
    """The card's buy and sell offers, worked out anew only when something they hang on has changed."""
    name = good.name
    key = (quantity, good.state.stock, good.get_price(), depot.money, depot.good_stock.get(name, 0),
           depot.room_for(name), market_block(name, depot, game_state))
    cached = _offer_cache.get(name)
    if cached is None or cached[0] != key:
        cached = (key, (buy_offer(good, quantity, depot, game_state), sell_offer(good, quantity, depot, game_state)))
        _offer_cache[name] = cached
    return cached[1]


def day_change(good: "Good") -> Optional[float]:
    """How far the price has moved in a day, as a share of what it was; None while the chart is younger."""
    history = good.price_history_hourly
    if len(history) <= PRICE_TICKS_PER_DAY or history[-PRICE_TICKS_PER_DAY - 1] <= 0:
        return None
    return good.get_price() / history[-PRICE_TICKS_PER_DAY - 1] - 1.0


def coins(value: float) -> str:
    return f"{value:,.2f}"


def draw_desk(screen: pygame.Surface, cards: List[Card], depot: "Depot", game_state: "GameState",
              font: pygame.font.Font, icons: Dict[str, pygame.Surface], line_ends: Dict[str, Tuple[float, float]],
              suppress_hover: bool = False) -> Optional[Preview]:
    """Draw the cards and the leaders from each good's line to its card; file the hitboxes in the game state.

    Args:
        line_ends: Where each charted good's line ends in the chart, by name.
        suppress_hover: Something is open over the view; nothing reacts to the pointer.

    Returns:
        What the chart should show for the Buy or Sell button under the pointer, if it is on one.
    """
    small = getattr(game_state, "small_font", None) or font
    mouse_pos = pygame.mouse.get_pos()
    preview = None
    for card in cards:
        if card.good is None:
            _draw_free_place(screen, card, small)
            continue
        end = line_ends.get(card.good.name)
        if end is not None:
            _draw_leader(screen, end, card, card.good.color, 10 + 7 * cards.index(card))
        buy, sell = offers(card.good, quantity_of(game_state, card.section), depot, game_state)
        hover = None if suppress_hover else next((key for key, rect in card.parts.items()
                                                  if rect.collidepoint(mouse_pos)), None)
        _draw_card(screen, card, buy, sell, depot, game_state, font, small, icons, hover)
        for key, rect in card.parts.items():
            game_state.trade_buttons[f"{key}_{card.section}"] = rect
        game_state.trade_cards.append((card.rect, card.section))
        game_state.trade_limits[card.section] = (buy.limit, sell.limit)
        if hover == "buy" and buy.blocked is None:
            preview = Preview(card.good, buy.price_after, True)
        elif hover == "sell" and sell.blocked is None:
            preview = Preview(card.good, sell.price_after, False)
    return preview


def _draw_leader(screen: pygame.Surface, end: Tuple[float, float], card: Card, color: Tuple[int, int, int],
                 run: int) -> None:
    """The good's line running on from where it ends in the chart to its card: *run* pixels on, then up or down to it."""
    x, y = end
    target = (card.rect.left, card.rect.y + 28)
    pygame.draw.lines(screen, color, False, [(x, y), (x + run, y), (x + run, target[1]), target])
    pygame.draw.circle(screen, color, (int(x), int(y)), 4)


def _draw_free_place(screen: pygame.Surface, card: Card, small: pygame.font.Font) -> None:
    """A place on the desk no good has taken yet."""
    pygame.draw.rect(screen, RULE_COLOR, card.rect, 1, border_radius=6)
    for i, line in enumerate(("Pick a good below", "to chart and trade it")):
        text = small.render(line, True, DETAIL_COLOR)
        screen.blit(text, text.get_rect(center=(card.rect.centerx, card.rect.centery - 11 + i * 22)))


def _blit_right(screen: pygame.Surface, surface: pygame.Surface, right: int, y: int) -> None:
    screen.blit(surface, (right - surface.get_width(), y))


def _draw_card(screen: pygame.Surface, card: Card, buy: Offer, sell: Offer, depot: "Depot",
               game_state: "GameState", font: pygame.font.Font, small: pygame.font.Font,
               icons: Dict[str, pygame.Surface], hover: Optional[str]) -> None:
    good, rect, parts = card.good, card.rect, card.parts
    left, right = rect.x + 14, rect.right - 10

    pygame.draw.rect(screen, PARCHMENT, rect, border_radius=6)
    pygame.draw.rect(screen, good.color, (rect.x, rect.y, 7, rect.height),
                     border_top_left_radius=6, border_bottom_left_radius=6)
    pygame.draw.rect(screen, DARK_BROWN, rect, 3 if good.hovered else 1, border_radius=6)

    # The good, its price, how it moved in a day and what the market holds
    icon = icons.get(good.name)
    if icon:
        screen.blit(icon, (left, rect.y + 8))
    screen.blit(font.render(good.name, True, BLACK), (left + 38, rect.y + 6))
    _blit_right(screen, font.render(f"{good.get_price():.2f}", True, BLACK), right, rect.y + 6)
    change = day_change(good)
    if change is not None:
        rising = change >= 0
        color = DARK_GREEN if rising else DARK_RED
        tip_y, base_y = (rect.y + 37, rect.y + 46) if rising else (rect.y + 46, rect.y + 37)
        pygame.draw.polygon(screen, color, [(left + 43, tip_y), (left + 38, base_y), (left + 48, base_y)])
        screen.blit(small.render(f"{abs(change) * 100:.1f}% in a day", True, color), (left + 54, rect.y + 32))
    _blit_right(screen, small.render(f"{good.market_quantity:,} at market", True, DETAIL_COLOR), right, rect.y + 32)
    pygame.draw.line(screen, RULE_COLOR, (left, rect.y + 57), (right, rect.y + 57))

    # What the player holds of it
    held = depot.good_stock.get(good.name, 0)
    average = depot.avg_buy_price(good.name) if held > 0 else None
    if held > 0:
        worth = good.get_price() * held
        screen.blit(small.render(f"You hold {held:,}", True, DARK_BROWN), (left, rect.y + 63))
        screen.blit(small.render(f"Worth {coins(worth)}", True, DARK_BROWN), (left, rect.y + 83))
        if average is not None:
            gain = worth - average * held
            _blit_right(screen, small.render(f"bought at {average:.2f}", True, DETAIL_COLOR), right, rect.y + 63)
            _blit_right(screen, small.render(f"{'+' if gain >= 0 else ''}{coins(gain)}", True,
                                             DARK_GREEN if gain >= 0 else DARK_RED), right, rect.y + 83)
    else:
        screen.blit(small.render("None in stock", True, DETAIL_COLOR), (left, rect.y + 73))
    pygame.draw.line(screen, RULE_COLOR, (left, rect.y + 105), (right, rect.y + 105))

    # The quantity and its steps
    for key, label in (("half", "/2"), ("minus", "-"), ("plus", "+"), ("double", "x2")):
        hot = hover == key
        pygame.draw.rect(screen, PALE_BROWN if hot else TAN, parts[key], border_radius=4)
        pygame.draw.rect(screen, DARK_BROWN, parts[key], 1, border_radius=4)
        ink = WHITE if hot else DARK_BROWN
        if key in ("minus", "plus"):
            cx, cy = parts[key].center
            pygame.draw.line(screen, ink, (cx - 6, cy), (cx + 6, cy), 2)
            if key == "plus":
                pygame.draw.line(screen, ink, (cx, cy - 6), (cx, cy + 6), 2)
        else:
            text = small.render(label, True, ink)
            screen.blit(text, text.get_rect(center=parts[key].center))
    _draw_quantity_field(screen, parts["quantity"], card.section, game_state, font, hover == "quantity")

    # Buy and sell, each with what it comes to
    for key, offer, hotkey, colors in (
            ("buy", buy, card.hotkeys[0], (BUY_BUTTON, BUY_BUTTON_HOVER, BUY_BUTTON_BORDER)),
            ("sell", sell, card.hotkeys[1], (SELL_BUTTON, SELL_BUTTON_HOVER, SELL_BUTTON_BORDER))):
        button, off = parts[key], offer.blocked is not None
        fill = LIGHT_GRAY if off else colors[1] if hover == key else colors[0]
        pygame.draw.rect(screen, fill, button, border_radius=5)
        pygame.draw.rect(screen, GRAY if off else colors[2], button, 2, border_radius=5)
        ink = DISABLED_TEXT if off else BUTTON_TEXT
        label = font.render("Buy" if key == "buy" else "Sell", True, ink)
        screen.blit(label, label.get_rect(midtop=(button.centerx, button.y + 3)))
        screen.blit(small.render(hotkey, True, ink), (button.x + 6, button.y + 4))
        if offer.quantity > 0:
            total = small.render(("-" if key == "buy" else "+") + coins(offer.total), True, ink)
            screen.blit(total, total.get_rect(midbottom=(button.centerx, button.bottom - 4)))
        if game_state.button_click_effects.get(f"{key}_{card.section}", 0):
            pressed = pygame.Surface(button.size, pygame.SRCALPHA)
            pygame.draw.rect(pressed, (0, 0, 0, 100), pressed.get_rect(), border_radius=5)
            screen.blit(pressed, button)

        # Under it: the price per unit with the fee, and the most that could be traded
        if offer.quantity > 0:
            each_color = DETAIL_COLOR
            if key == "sell" and offer.profit is not None:
                each_color = DARK_GREEN if offer.profit >= 0 else DARK_RED
            each = small.render(f"{offer.each:.2f} each", True, each_color)
            screen.blit(each, each.get_rect(midtop=(button.centerx, button.bottom + 3)))
        link_key = "maxbuy" if key == "buy" else "maxsell"
        link_hot = hover == link_key and offer.limit > 0
        link = small.render(f"{'Max' if key == 'buy' else 'All'} {offer.limit:,}", True,
                            BLACK if link_hot else DARK_BROWN if offer.limit > 0 else DISABLED_TEXT)
        link_rect = link.get_rect(center=parts[link_key].center)
        screen.blit(link, link_rect)
        if link_hot:
            pygame.draw.line(screen, BLACK, (link_rect.left, link_rect.bottom - 1), (link_rect.right, link_rect.bottom - 1))

    text, color = status_line(good, buy, sell, hover, depot, game_state)
    if text:
        status = small.render(text, True, color)
        screen.blit(status, status.get_rect(center=(rect.centerx + 3, rect.bottom - 14)))


def _draw_quantity_field(screen: pygame.Surface, rect: pygame.Rect, section: str, game_state: "GameState",
                         font: pygame.font.Font, hovered: bool) -> None:
    """The card's quantity: a text field, typed into once clicked."""
    name = f"quantity_{section}"
    focused = game_state.mouse_clicked_on == name
    text = game_state.input_fields.get(name, "")
    pygame.draw.rect(screen, WHITE if focused or hovered else FIELD_COLOR, rect, border_radius=4)
    pygame.draw.rect(screen, DARK_BROWN, rect, 2 if focused else 1, border_radius=4)
    surface = font.render(text, True, BLACK)
    text_rect = surface.get_rect(center=rect.center)
    if focused and game_state.input_text_selected and text:
        marked = pygame.Surface((text_rect.width + 6, rect.height - 8), pygame.SRCALPHA)
        marked.fill((0, 0, 0, 70))
        screen.blit(marked, (text_rect.x - 3, rect.y + 4))
    screen.blit(surface, text_rect)
    if focused and not game_state.input_text_selected and game_state.cursor_visible:
        cursor_x = text_rect.x + font.size(text[:game_state.cursor_position])[0] + 1
        pygame.draw.line(screen, BLACK, (cursor_x, rect.y + 6), (cursor_x, rect.bottom - 6), 2)


def status_line(good: "Good", buy: Offer, sell: Offer, hover: Optional[str], depot: "Depot",
                game_state: "GameState") -> Tuple[str, Tuple[int, int, int]]:
    """The card's last line: why an order cannot be placed, what the hovered one does, or a licence running out."""
    if hover == "buy":
        if buy.blocked:
            return buy.blocked, DARK_RED
        return f"Price rises to {buy.price_after:.2f}", DARK_BROWN
    if hover == "sell":
        if sell.blocked:
            return sell.blocked, DARK_RED
        profit = ""
        if sell.profit is not None:
            profit = f"{'Profit' if sell.profit >= 0 else 'Loss'} {coins(abs(sell.profit))}, "
        return f"{profit}price falls to {sell.price_after:.2f}", DARK_GREEN if (sell.profit or 0) >= 0 else DARK_RED
    blocked = market_block(good.name, depot, game_state)
    if blocked:
        return blocked, DARK_RED
    expiry = depot.trading_licenses.get(depot.license_name(good.name))
    if expiry is not None:
        days = (expiry - game_state.date).days
        if days <= LICENCE_WARN_DAYS:
            return ("Licence ends today" if days < 1 else f"Licence ends in {days} day{'s' if days > 1 else ''}"), DARK_RED
    return "", DARK_BROWN
