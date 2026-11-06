"""A good's day in the town's market: who wanted it and where it came from.

The market view shows it when a good's box is hovered (``chart_view``): a
panel with yesterday's demand against supply, each a bar, what they were made
of, and the line that reconciles them. Demand is what the households' whole
baskets asked for plus what the workshops planned to use; supply is what the
town's workshops made plus what merchants brought in, and what the merchants
took out of town is shown beside it. They differ by what the market's stock
gave or took, what buyers went without (dear or sold out) and the player's
trades, which is exactly how the stock moves:

    demand − went without = supply − sent out − added to stock + you sold − you bought

The numbers are the simulation's (``GoodState.yesterday``, through
``Good.flows_yesterday``); this module only adds them up and draws them.
"""
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

import pygame

from ..config.colors import BLACK, BEIGE, DARK_BROWN, DARK_RED, WHITE
from ..config.constants import FONTS_PATH

if TYPE_CHECKING:
    from ..sim.state import GoodFlows

BAR_WIDTH = 150                 # the longer of the two bars, in pixels
BAR_HEIGHT = 10
PAD = 8                         # inside the panel's border
ROW_GAP = 3
ABOVE_POINTER = 32              # how far above the pointer the panel ends when it opens upwards (clear of the hovered box)
DEMAND_COLOR = (112, 78, 46)    # umber ink
SUPPLY_COLOR = (196, 158, 92)   # ochre
TRACK_EDGE = (150, 120, 80)
DETAIL_COLOR = (90, 70, 50)
RECONCILE_GAP = 4               # above the reconciling line
NONE_BELOW = 0.005              # less than this is nothing (float dust), shown as 0


@dataclass(frozen=True)
class DailyFlows:
    """One good's day in the market, added up for the market view."""
    townsfolk: float            # households' whole baskets (what they wanted, before the price talked them out of some)
    workshops: float            # inputs the workshops planned to use
    made: float                 # made in town and sold into the market
    imported: float             # brought in by merchants
    exported: float             # taken out by merchants
    got: float = 0.0            # what households and workshops bought
    player_bought: float = 0.0
    player_sold: float = 0.0

    @property
    def demand(self) -> float:
        return self.townsfolk + self.workshops

    @property
    def supply(self) -> float:
        return self.made + self.imported

    @property
    def went_without(self) -> float:
        """What households and workshops wanted and did not get (too dear, or sold out)."""
        return max(0.0, self.demand - self.got)

    @property
    def added_to_stock(self) -> float:
        """How the market's stock moved (taken from it when negative)."""
        return self.supply + self.player_sold - self.exported - self.got - self.player_bought


def daily_flows(flows: "GoodFlows") -> DailyFlows:
    """Yesterday's flows of a good, as the market view adds them up."""
    return DailyFlows(townsfolk=flows.wanted, workshops=flows.input_wanted, made=flows.produced,
                      imported=flows.imported, exported=flows.exported, got=flows.bought + flows.input_bought,
                      player_bought=flows.player_bought, player_sold=flows.player_sold)


def amount(value: float) -> str:
    """A day's units: whole units, '<1' for a little, '0' for none."""
    if value < NONE_BELOW:
        return "0"
    if value < 1:
        return "<1"
    return f"{int(value + 0.5):,}"      # halves up (round() would make 6.5 a 6)


def bar_lengths(flows: DailyFlows, width: int = BAR_WIDTH) -> Tuple[int, int]:
    """The demand and supply bars' lengths: the larger fills *width*, the other in proportion (0 when both are 0)."""
    top = max(flows.demand, flows.supply)
    if top <= 0:
        return 0, 0
    return round(width * flows.demand / top), round(width * flows.supply / top)


def detail_lines(flows: DailyFlows) -> Tuple[str, str]:
    """The small print under the bars: what the demand and the supply were made of."""
    demand = f"townsfolk {amount(flows.townsfolk)}, workshops {amount(flows.workshops)}"
    supply = f"made here {amount(flows.made)}, imported {amount(flows.imported)}"
    if flows.exported >= NONE_BELOW:
        supply += f"; sent out {amount(flows.exported)}"
    return demand, supply


def reconcile_line(flows: DailyFlows) -> str:
    """What makes demand and supply differ: the stock taken or added, what went without, the player's trades."""
    parts = []
    stock = flows.added_to_stock
    if stock <= -NONE_BELOW:
        parts.append(f"taken from stock {amount(-stock)}")
    elif stock >= NONE_BELOW:
        parts.append(f"added to stock {amount(stock)}")
    if flows.went_without >= NONE_BELOW:
        parts.append(f"went without {amount(flows.went_without)}")
    if flows.player_bought >= NONE_BELOW:
        parts.append(f"you bought {amount(flows.player_bought)}")
    if flows.player_sold >= NONE_BELOW:
        parts.append(f"you sold {amount(flows.player_sold)}")
    return ", ".join(parts).capitalize() if parts else "Stock unchanged"


_fonts: Dict[int, pygame.font.Font] = {}


def _small_font(size: int = 18) -> pygame.font.Font:
    if size not in _fonts:
        try:
            _fonts[size] = pygame.font.Font(os.path.join(FONTS_PATH, "RomanAntique.ttf"), size)
        except (OSError, pygame.error):
            _fonts[size] = pygame.font.SysFont("arial", size - 4)
    return _fonts[size]


def draw_flows_tooltip(screen: pygame.Surface, font: pygame.font.Font, name: str, flows: DailyFlows,
                       pos: Tuple[int, int], safe_right: int, safe_bottom: int,
                       warning: Optional[str] = None) -> pygame.Rect:
    """The hovered good's panel beside the pointer: its name, a warning if any, and yesterday's demand and supply.

    Flips to the left of the pointer when it would run past *safe_right*, and
    opens above the pointer when it would run past *safe_bottom*. Returns the
    panel's rect.
    """
    small = _small_font()
    rows: List[Tuple[pygame.Surface, int]] = [(font.render(name, True, BLACK), 0)]
    if warning:
        rows.append((font.render(warning, True, DARK_RED), 0))
    rows.append((small.render("Yesterday in the market", True, DETAIL_COLOR), 4))
    demand_len, supply_len = bar_lengths(flows)
    label_w = max(small.size("Demand")[0], small.size("Supply")[0]) + 8
    number_w = max(small.size(amount(flows.demand))[0], small.size(amount(flows.supply))[0]) + 8
    bar_row_w = label_w + number_w + BAR_WIDTH
    demand_detail, supply_detail = detail_lines(flows)
    details = [small.render(demand_detail, True, DETAIL_COLOR), small.render(supply_detail, True, DETAIL_COLOR)]
    reconcile = small.render(reconcile_line(flows), True, DARK_BROWN)
    line_h = small.size("Hg")[1]        # rendered height: this font's get_height() reports less than it draws

    width = max([s.get_width() for s, _ in rows] + [bar_row_w] + [d.get_width() for d in details]
                + [reconcile.get_width()])
    height = (sum(s.get_height() + gap + ROW_GAP for s, gap in rows)
              + 4 * (line_h + ROW_GAP) + RECONCILE_GAP + line_h + ROW_GAP)
    panel = pygame.Rect(pos[0] + 35, pos[1] + 10, width + 2 * PAD, height + 2 * PAD - ROW_GAP)
    if panel.right > safe_right:
        panel.right = pos[0] - 15
    if panel.bottom > safe_bottom:      # no room below the pointer (the goods bar is at the bottom): open above it
        panel.bottom = pos[1] - ABOVE_POINTER
    panel.top = max(0, panel.top)

    pygame.draw.rect(screen, WHITE, panel)
    pygame.draw.rect(screen, DARK_BROWN, panel, 1)
    x, y = panel.left + PAD, panel.top + PAD
    for surface, gap in rows:
        y += gap
        screen.blit(surface, (x, y))
        y += surface.get_height() + ROW_GAP
    for label, value, length, color, detail in (("Demand", flows.demand, demand_len, DEMAND_COLOR, details[0]),
                                                ("Supply", flows.supply, supply_len, SUPPLY_COLOR, details[1])):
        screen.blit(small.render(label, True, DARK_BROWN), (x, y))
        number = small.render(amount(value), True, DARK_BROWN)
        screen.blit(number, (x + label_w + number_w - 8 - number.get_width(), y))
        track = pygame.Rect(x + label_w + number_w, y + (line_h - BAR_HEIGHT) // 2, BAR_WIDTH, BAR_HEIGHT)
        pygame.draw.rect(screen, BEIGE, track)
        if length:
            pygame.draw.rect(screen, color, (track.x, track.y, length, BAR_HEIGHT))
        pygame.draw.rect(screen, TRACK_EDGE, track, 1)
        y += line_h + ROW_GAP
        screen.blit(detail, (x + 10, y))
        y += line_h + ROW_GAP
    screen.blit(reconcile, (x, y + RECONCILE_GAP))
    return panel
