"""The town council's window, opened at the town hall ("Town Council").

A sheet in the style of the guild's records, with three pages:

- **Offices**: the pyramid of seats, the head of the council on top, each a card with its
  holder's arms, what it pays and when it is voted on again. The card chosen is set out
  below, with the button to put one's name down for it (or to lay down one's own).
- **Notables**: the town's notables and how each likes the player; the one chosen at the
  right, with the gifts that can be sent, the amends that can be made and, before a vote
  the player is in, the purse and the delay.
- **Election**: the vote the player is in: the candidates, how each voter leans, and the
  council's minutes of its last sessions.

Everything is the model's (`models/council.py`); the window only shows it and passes the
clicks on. It is drawn afresh each frame over a sheet made once, since favour and money
change under it.
"""

import os
from typing import Any, Callable, Dict, List, Optional, Tuple, TYPE_CHECKING

import pygame

from .loan_dialog import _BaseDialog, _close_dialog
from .records_window import _leaf
from ..heraldry import PLAYER_ARMS, draw_arms
from ..transaction_feedback import on_money_spent
from ...config.colors import GOLD
from ...config.constants import FONTS_PATH, PURSES_PER_ELECTION
from ...models.council import (
    Council, FAVOUR_MAX, Office, Outcome, PLAYER, favour_word, session_moment,
)
from ...models.minigames.tutorial_sheet import (
    BRASS, BRASS_DARK, BRASS_LIGHT, INK, RUBRIC, draw_button, draw_tab, framed_sheet, inked, plaque,
)
from ...models.minigames.woodhacking import draw_divider
from ...sim.calendar import format_date, format_long

if TYPE_CHECKING:
    from ...game_state import GameState

PAGE_OFFICES, PAGE_NOTABLES, PAGE_ELECTION = "Offices", "Notables", "Election"
PAGES = (PAGE_OFFICES, PAGE_NOTABLES, PAGE_ELECTION)
GIFT_SIZES = (0.5, 1.0, 3.0)        # the coin gifts offered, in the notable's means

FAINT_INK = (120, 104, 84)
GOOD_INK = (40, 104, 52)
_TRACK = (120, 104, 84, 70)
_DISABLED = ((206, 190, 156), (160, 138, 100), (140, 120, 90))   # a button that cannot be pressed: fill, edge, ink


def open_council_window(game_state: 'GameState', house: Any = None) -> None:
    game_state.info_window = CouncilWindow(game_state.screen, game_state)
    if house is not None:
        game_state.active_house_menu = house


def wrap(text: str, font: pygame.font.Font, width: int) -> List[str]:
    """The text broken into lines no wider than *width*."""
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if line and font.size(trial)[0] > width:
            lines.append(line)
            line = word
        else:
            line = trial
    if line:
        lines.append(line)
    return lines


def arms_of(council: Council, who: Optional[str]) -> Optional[Dict[str, Any]]:
    if who is None:
        return None
    return PLAYER_ARMS if who == PLAYER else council.notables[who].arms


def draw_favour_bar(surf: pygame.Surface, rect: pygame.Rect, value: float) -> None:
    """Favour from its middle: green to the right for liking, red to the left for dislike."""
    track = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.rect(track, _TRACK, track.get_rect(), border_radius=3)
    surf.blit(track, rect)
    half = rect.width / 2
    length = round(half * min(1.0, abs(value) / FAVOUR_MAX))
    if length > 0:
        if value > 0:
            pygame.draw.rect(surf, GOOD_INK, (rect.centerx, rect.top, length, rect.height), border_radius=2)
        else:
            pygame.draw.rect(surf, RUBRIC, (rect.centerx - length, rect.top, length, rect.height), border_radius=2)
    pygame.draw.rect(surf, BRASS_DARK, rect, 1, border_radius=3)
    pygame.draw.line(surf, INK, (rect.centerx, rect.top - 2), (rect.centerx, rect.bottom + 1), 1)


class CouncilWindow(_BaseDialog):
    W, H = 1240, 804
    MARGIN = 44
    FRAME_INSET = 13
    TITLE_Y, DIVIDER_Y = 46, 80
    TAB_TOP, TAB_W, TAB_H, TAB_GAP = 94, 210, 38, 10
    PLAQUE_Y = 153
    BODY_TOP = 178
    MESSAGE_H = 50
    BODY_W = W - 2 * MARGIN
    BODY_H = H - BODY_TOP - MESSAGE_H

    CARD_W, CARD_H, CARD_GAP, ROW_STEP = 270, 122, 14, 136
    DETAIL_TOP = 3 * ROW_STEP
    BUTTON_W, BUTTON_H = 236, 42

    LIST_W = 548
    LIST_HEAD, LIST_ROW = 46, 40
    ELECTION_W = 690
    VOTER_ROW = 38

    def __init__(self, screen: pygame.Surface, game_state: 'GameState') -> None:
        super().__init__(screen, game_state, self.W, self.H)
        self.council: Council = game_state.game.council
        self.sheet_title_font = self._font("Medici Text.ttf", 46)
        self.name_font = self._font("Medici Text.ttf", 26)
        self.small_font = self._font("Augusta.ttf", 17)
        self.tight_font = self._font("Medici Text.ttf", 21)     # an office's name too long for its card
        self.page = PAGE_ELECTION if self.council.candidacy else PAGE_OFFICES
        own = self.council.player_office
        self.office_key: str = own.key if own else next(iter(self.council.offices))
        self.notable_key: str = next(iter(self.council.notables))
        self.message: Optional[Outcome] = None
        self._sheet: Optional[pygame.Surface] = None
        self._hot: Dict[str, Tuple[pygame.Rect, Callable[[], None]]] = {}   # what can be clicked, on the sheet
        self.close_local = pygame.Rect(0, 0, 30, 30)
        self.close_local.center = (self.W - 19, 19)
        tabs_w = len(PAGES) * self.TAB_W + (len(PAGES) - 1) * self.TAB_GAP
        left = (self.W - tabs_w) // 2
        self.tab_rects = {page: pygame.Rect(left + i * (self.TAB_W + self.TAB_GAP), self.TAB_TOP, self.TAB_W, self.TAB_H)
                          for i, page in enumerate(PAGES)}
        self.body = pygame.Rect(self.MARGIN, self.BODY_TOP, self.BODY_W, self.BODY_H)

    @staticmethod
    def _font(name: str, size: int) -> pygame.font.Font:
        try:
            return pygame.font.Font(os.path.join(FONTS_PATH, name), size)
        except Exception:
            return pygame.font.SysFont("arial", size - 4)

    @property
    def _date(self):
        return self.game_state.date

    @property
    def _depot(self):
        return self.game_state.game.depot

    # -- input -------------------------------------------------------------

    def button_rect(self, key: str) -> Optional[pygame.Rect]:
        """Where something clickable was drawn last, on the screen (None if it was not)."""
        entry = self._hot.get(key)
        return entry[0].move(self.panel.topleft) if entry else None

    def handle_click(self, pos: Tuple[int, int]) -> bool:
        local = (pos[0] - self.panel.left, pos[1] - self.panel.top)
        if self.close_local.collidepoint(local) or not self.panel.collidepoint(pos):
            _close_dialog(self.game_state)
            return True
        for page, rect in self.tab_rects.items():
            if rect.collidepoint(local):
                self.page = page
                return True
        for rect, action in list(self._hot.values()):
            if rect.collidepoint(local):
                action()
                return True
        return True

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            _close_dialog(self.game_state)

    def _do(self, action: Callable[[], Outcome]) -> None:
        """Do something that may cost money, keep what came of it to show, and let the coins fall."""
        before = self._depot.money
        self.message = action()
        spent = before - self._depot.money
        if spent > 0 and hasattr(self.game_state, "coin_popups"):
            on_money_spent(self.game_state, spent)

    def _choose_office(self, key: str) -> None:
        self.office_key = key

    def _choose_notable(self, key: str) -> None:
        self.notable_key = key

    def show_notable(self, key: str) -> None:
        self.notable_key = key
        self.page = PAGE_NOTABLES

    # -- small things drawn ------------------------------------------------

    def _put(self, surf: pygame.Surface, text: str, pos: Tuple[int, int], font: Optional[pygame.font.Font] = None,
             colour=INK, anchor: str = "topleft") -> pygame.Rect:
        label = (font or self.body_font).render(text, True, colour)
        rect = label.get_rect(**{anchor: pos})
        surf.blit(label, rect)
        return rect

    def _button(self, surf: pygame.Surface, key: str, rect: pygame.Rect, label: str, action: Callable[[], None],
                enabled: bool, mouse: Tuple[int, int]) -> None:
        if enabled:
            draw_button(surf, rect, label, self.body_font, rect.collidepoint(mouse))
            self._hot[key] = (rect, action)
            return
        fill, edge, ink = _DISABLED
        pygame.draw.rect(surf, fill, rect, border_radius=4)
        pygame.draw.rect(surf, edge, rect, 2, border_radius=4)
        text = self.body_font.render(label, True, ink)
        surf.blit(text, text.get_rect(center=rect.center))

    def _heading(self, surf: pygame.Surface, rect: pygame.Rect, text: str) -> None:
        self._put(surf, text, (rect.centerx, rect.top + 22), self.name_font, anchor="center")
        draw_divider(surf, (rect.centerx, rect.top + self.LIST_HEAD - 4), 110)

    @staticmethod
    def _mark(surf: pygame.Surface, centre: Tuple[int, int], met: bool) -> None:
        x, y = centre
        if met:
            pygame.draw.lines(surf, GOOD_INK, False, [(x - 7, y), (x - 2, y + 6), (x + 8, y - 7)], 3)
        else:
            pygame.draw.line(surf, RUBRIC, (x - 6, y - 6), (x + 6, y + 6), 3)
            pygame.draw.line(surf, RUBRIC, (x - 6, y + 6), (x + 6, y - 6), 3)

    @staticmethod
    def _pips(surf: pygame.Surface, centre: Tuple[int, int], count: int) -> None:
        """An office's tier as gold lozenges in a row (the blackletter's numerals read badly)."""
        x = centre[0] - (count - 1) * 8
        for i in range(count):
            cx = x + i * 16
            points = [(cx, centre[1] - 7), (cx + 6, centre[1]), (cx, centre[1] + 7), (cx - 6, centre[1])]
            pygame.draw.polygon(surf, GOLD, points)
            pygame.draw.polygon(surf, BRASS_DARK, points, 1)

    def _holder_line(self, who: Optional[str]) -> str:
        return "Empty" if who is None else self.council.name_of(who)

    # -- the offices -------------------------------------------------------

    def card_rect(self, office_key: str) -> pygame.Rect:
        """Where an office's card lies on the sheet: its tier's row, the highest on top, centred."""
        council = self.council
        office = council.offices[office_key]
        row = [o.key for o in council.offices.values() if o.tier == office.tier]
        width = len(row) * self.CARD_W + (len(row) - 1) * self.CARD_GAP
        left = self.body.centerx - width // 2 + row.index(office_key) * (self.CARD_W + self.CARD_GAP)
        return pygame.Rect(left, self.body.top + (council.top_tier - office.tier) * self.ROW_STEP,
                           self.CARD_W, self.CARD_H)

    def _draw_card(self, surf: pygame.Surface, office: Office, mouse: Tuple[int, int]) -> None:
        council = self.council
        rect = self.card_rect(office.key)
        seat = council.seats[office.key]
        mine = seat.holder == PLAYER
        standing = council.candidacy is not None and council.candidacy.office == office.key
        _leaf(surf, rect)
        if mine:
            glow = pygame.Surface(rect.size, pygame.SRCALPHA)
            glow.fill((*GOLD, 70))
            surf.blit(glow, rect)
        if office.key == self.office_key:
            pygame.draw.rect(surf, RUBRIC, rect, 3, border_radius=4)
        elif rect.collidepoint(mouse):
            pygame.draw.rect(surf, GOLD, rect, 2, border_radius=4)

        arms = arms_of(council, seat.holder)
        shield = pygame.Rect(rect.left + 14, rect.top + 16, 50, 60)
        if arms:
            draw_arms(surf, shield, arms)
        else:
            pygame.draw.rect(surf, FAINT_INK, shield, 1, border_radius=3)
        self._pips(surf, (shield.centerx, shield.bottom + 18), office.tier)

        x = shield.right + 14
        title = self.name_font if self.name_font.size(office.name)[0] <= rect.right - x - 8 else self.tight_font
        self._put(surf, office.name, (x, rect.top + 26), title, anchor="midleft")
        self._put(surf, self._holder_line(seat.holder), (x, rect.top + 42), colour=RUBRIC if mine else INK)
        privileges = office.privileges()
        self._put(surf, privileges[0], (x, rect.top + 68), self.small_font, FAINT_INK)
        if standing:
            plaque(surf, self.small_font, "Your name is down", (x + 78, rect.top + 102))
        elif len(privileges) > 1:
            self._put(surf, privileges[1], (x, rect.top + 90), self.small_font, FAINT_INK)
        self._hot[f"office:{office.key}"] = (rect, lambda key=office.key: self._choose_office(key))

    def _draw_office_detail(self, surf: pygame.Surface, mouse: Tuple[int, int]) -> None:
        council = self.council
        office = council.offices[self.office_key]
        seat = council.seats[office.key]
        rect = pygame.Rect(self.body.left, self.body.top + self.DETAIL_TOP, self.BODY_W, self.BODY_H - self.DETAIL_TOP)
        _leaf(surf, rect)
        x = rect.left + 20
        self._put(surf, office.name, (x, rect.top + 12), self.name_font)
        self._put(surf, office.duty, (x, rect.top + 48))
        y = rect.top + 78
        for line in wrap("   ·   ".join(office.privileges()), self.small_font, 640):
            self._put(surf, line, (x, y), self.small_font, GOOD_INK)
            y += 22
        held = (f"Held by {self._holder_line(seat.holder)}; voted on again at the session of "
                f"{format_date(session_moment(council.term_ends(office.key)))}")
        self._put(surf, held, (x, rect.bottom - 34), self.small_font, FAINT_INK)

        # What it asks, at the right
        column = rect.right - 430
        pygame.draw.line(surf, BRASS, (column - 22, rect.top + 14), (column - 22, rect.bottom - 14), 1)
        ranked = council.has_rank(office)
        self._mark(surf, (column + 8, rect.top + 26), ranked)
        self._put(surf, f"Asks for the rank of {council.rank_needed(office)}", (column + 26, rect.top + 14))
        stepped = office.tier <= council.tier_of(PLAYER) + 1
        self._mark(surf, (column + 8, rect.top + 54), stepped)
        self._put(surf, "No more than one tier above your own", (column + 26, rect.top + 42))
        voters = len(council.electorate(office.key, [seat.holder] if seat.holder else []))
        self._put(surf, f"Voted on by {voters} of the council   ·   Fee {council.filing_fee(office):,.0f} coins",
                  (column + 26, rect.top + 70), self.small_font, FAINT_INK)

        button = pygame.Rect(rect.right - self.BUTTON_W - 18, rect.bottom - self.BUTTON_H - 14, self.BUTTON_W, self.BUTTON_H)
        candidacy = council.candidacy
        if seat.holder == PLAYER:
            self._button(surf, "resign", button, "Lay down the office", lambda: self._do(council.resign), True, mouse)
        elif candidacy is not None and candidacy.office == office.key:
            self._button(surf, "withdraw", button, "Withdraw your name", lambda: self._do(council.withdraw), True, mouse)
        else:
            allowed = council.can_stand(office.key)
            self._button(surf, "stand", button, "Stand for election",
                         lambda key=office.key: self._stand(key), allowed.ok, mouse)
            if not allowed.ok:
                room = button.left - 14 - (column - 22 + 12)     # between the rule and the button
                lines = wrap(allowed.text, self.small_font, max(room, 40))
                top = button.centery - len(lines) * 11
                for i, line in enumerate(lines):
                    self._put(surf, line, (button.left - 14, top + i * 22 + 11), self.small_font, RUBRIC, "midright")

    def _stand(self, office_key: str) -> None:
        self._do(lambda: self.council.stand(office_key, self._date))
        if self.message and self.message.ok:
            self.page = PAGE_ELECTION

    def _draw_offices(self, surf: pygame.Surface, mouse: Tuple[int, int]) -> None:
        for tier in range(self.council.top_tier, 1, -1):       # a rule between the tiers
            y = self.body.top + (self.council.top_tier - tier) * self.ROW_STEP + self.CARD_H + 7
            draw_divider(surf, (self.body.centerx, y), 300)
        for office in self.council.offices.values():
            self._draw_card(surf, office, mouse)
        self._draw_office_detail(surf, mouse)

    # -- the notables ------------------------------------------------------

    def _role(self, key: str) -> str:
        office = self.council.office_of(key)
        return office.name if office else self.council.notables[key].trade.capitalize()

    def notable_row_rect(self, index: int) -> pygame.Rect:
        return pygame.Rect(self.body.left + 8, self.body.top + self.LIST_HEAD + index * self.LIST_ROW,
                           self.LIST_W - 16, self.LIST_ROW)

    def _draw_notable_list(self, surf: pygame.Surface, mouse: Tuple[int, int]) -> None:
        council = self.council
        rect = pygame.Rect(self.body.topleft, (self.LIST_W, self.BODY_H))
        _leaf(surf, rect)
        self._heading(surf, rect, "The notables of the town")
        for index, (key, notable) in enumerate(council.notables.items()):
            row = self.notable_row_rect(index)
            if key == self.notable_key or row.collidepoint(mouse):
                band = pygame.Surface(row.size, pygame.SRCALPHA)
                band.fill((*GOLD, 90 if key == self.notable_key else 40))
                surf.blit(band, row)
            draw_arms(surf, pygame.Rect(row.left + 8, row.top + 4, 27, 32), notable.arms)
            self._put(surf, notable.name, (row.left + 46, row.centery), colour=RUBRIC if notable.grudge > 0 else INK,
                      anchor="midleft")
            bar = pygame.Rect(row.right - 124, row.centery - 5, 112, 10)
            draw_favour_bar(surf, bar, council.effective_favour(key))
            self._put(surf, self._role(key), (bar.left - 12, row.centery), self.small_font, FAINT_INK, "midright")
            self._hot[f"notable:{key}"] = (row, lambda key=key: self._choose_notable(key))

        button = pygame.Rect(rect.left + 18, rect.bottom - self.BUTTON_H - 16, self.BUTTON_W + 40, self.BUTTON_H)
        given = council.banquet_given(self._date)
        cost = council.banquet_cost()
        self._button(surf, "banquet", button, f"Host a banquet · {cost:,.0f} coins",
                     lambda: self._do(lambda: council.host_banquet(self._date)),
                     not given and self._depot.money >= cost and cost > 0, mouse)
        words = "Given this season" if given else "Once a season, for all the notables"
        self._put(surf, words, (button.right + 14, button.centery), self.small_font, FAINT_INK, "midleft")

    def _draw_notable(self, surf: pygame.Surface, mouse: Tuple[int, int]) -> None:
        council = self.council
        key = self.notable_key
        notable = council.notables[key]
        rect = pygame.Rect(self.body.left + self.LIST_W + 14, self.body.top, self.BODY_W - self.LIST_W - 14, self.BODY_H)
        _leaf(surf, rect)
        left = rect.left + 24
        draw_arms(surf, pygame.Rect(left, rect.top + 22, 84, 100), notable.arms)
        x = left + 104
        self._put(surf, notable.name, (x, rect.top + 20), self.name_font)
        office = council.office_of(key)
        role = f"{office.name}, {notable.trade}" if office else f"{notable.trade.capitalize()}, without a seat"
        self._put(surf, role, (x, rect.top + 54))
        fond = self._put(surf, f"Fond of {notable.likes}", (x, rect.top + 82), colour=FAINT_INK)
        icons = getattr(self.game_state.game, "images", {}).get("goods_30", {})
        if notable.likes in icons:
            surf.blit(icons[notable.likes], icons[notable.likes].get_rect(midleft=(fond.right + 8, fond.centery)))

        favour = council.effective_favour(key)
        y = rect.top + 146
        self._put(surf, "Favour", (left, y))
        bar = pygame.Rect(left + 84, y + 6, 240, 12)
        draw_favour_bar(surf, bar, favour)
        self._put(surf, favour_word(favour), (bar.right + 16, y), colour=GOOD_INK if favour >= 12 else RUBRIC if favour < -12 else INK)
        if notable.grudge > 0:
            words = "At feud with you" if council.in_feud(key) else "Still bears you a grudge"
            self._put(surf, words, (left, y + 28), colour=RUBRIC)
        pygame.draw.line(surf, BRASS, (left, rect.top + 208), (rect.right - 24, rect.top + 208), 1)

        # Gifts
        y = rect.top + 220
        self._put(surf, "A gift of coin", (left, y))
        means = council.means(key)
        for i, size in enumerate(GIFT_SIZES):
            amount = max(5, round(means * size / 5) * 5)
            button = pygame.Rect(left + i * 180, y + 30, 168, self.BUTTON_H)
            self._button(surf, f"gift:{i}", button, f"{amount:,} coins",
                         lambda amount=amount: self._do(lambda: council.gift_money(key, amount)),
                         self._depot.money >= amount, mouse)
            self._put(surf, f"Favour +{council.gift_gain(key, amount):.0f}", (button.centerx, button.bottom + 12),
                      self.small_font, FAINT_INK, "center")

        y = rect.top + 322
        lot = council.liked_lot(key)
        have = self._depot.good_stock.get(notable.likes, 0)
        button = pygame.Rect(left, y, 258, self.BUTTON_H)
        self._button(surf, "goods", button, f"Send {lot} {notable.likes}",
                     lambda: self._do(lambda: council.gift_goods(key, lot)), have >= lot, mouse)
        self._put(surf, f"Worth half as much again  ·  you have {have}",
                  (button.right + 14, button.centery), self.small_font, FAINT_INK, "midleft")

        y = rect.top + 376
        if notable.grudge > 0:
            cost = council.amends_cost(key)
            button = pygame.Rect(left, y, 258, self.BUTTON_H)
            self._button(surf, "amends", button, f"Make amends · {cost:,.0f} coins",
                         lambda: self._do(lambda: council.make_amends(key)), self._depot.money >= cost, mouse)
            self._put(surf, "Ends the feud at once", (button.right + 14, button.centery), self.small_font, FAINT_INK,
                      "midleft")

        # Before the vote
        y = rect.top + 434
        pygame.draw.line(surf, BRASS, (left, y - 8), (rect.right - 24, y - 8), 1)
        self._put(surf, "Before the vote", (left, y))
        candidacy = council.candidacy
        if candidacy is None:
            self._put(surf, "Put your name down for a seat, and more can be arranged.", (left, y + 34), self.small_font,
                      FAINT_INK)
            return
        if not council.is_voter(key):
            self._put(surf, "Has no vote in your election.", (left, y + 34), self.small_font, FAINT_INK)
            return
        purse = pygame.Rect(left, y + 30, 258, self.BUTTON_H)
        delay = pygame.Rect(purse.right + 14, y + 30, 258, self.BUTTON_H)
        if key in candidacy.purses:
            taken = candidacy.purses[key]
            self._put(surf, "Has taken your purse" if taken else "Refused your purse", purse.center,
                      colour=GOOD_INK if taken else RUBRIC, anchor="center")
        else:
            self._button(surf, "purse", purse, f"Offer a purse · {council.purse_cost(key):,.0f}",
                         lambda: self._do(lambda: council.offer_purse(key)), council.can_offer_purse(key).ok, mouse)
        if candidacy.delayed == key:
            self._put(surf, "Will be met on the road", delay.center, colour=GOOD_INK, anchor="center")
        else:
            self._button(surf, "delay", delay, f"Have delayed · {council.delay_cost(key):,.0f}",
                         lambda: self._do(lambda: council.arrange_delay(key)), council.can_arrange_delay(key).ok, mouse)
        left_over = PURSES_PER_ELECTION - len(candidacy.purses)
        self._put(surf, f"A purse may be refused, and talked of; {left_over} more may be offered.",
                  (left, purse.bottom + 10), self.small_font, FAINT_INK)
        self._put(surf, "A delay may fail, and be traced back to you.", (left, purse.bottom + 31), self.small_font,
                  FAINT_INK)

    # -- the election ------------------------------------------------------

    def voter_row_rect(self, index: int) -> pygame.Rect:
        return pygame.Rect(self.body.left + 10, self.body.top + 172 + index * self.VOTER_ROW,
                           self.ELECTION_W - 20, self.VOTER_ROW)

    def _draw_contest(self, surf: pygame.Surface, mouse: Tuple[int, int]) -> None:
        council = self.council
        candidacy = council.candidacy
        rect = pygame.Rect(self.body.topleft, (self.ELECTION_W, self.BODY_H))
        _leaf(surf, rect)
        left = rect.left + 22
        if candidacy is None:
            self._heading(surf, rect, "No vote of yours is called")
            own = council.player_office
            lines = ["Choose a seat on the page of the offices and put your name down for it.",
                     "The council sits once a season; whoever would be voted on must have",
                     "their name down before that day begins. Use the days until then:",
                     "those who vote go by how well they like each candidate."]
            if own is not None:
                ends = format_long(session_moment(council.term_ends(own.key)))
                lines += ["", f"Your seat as {own.name} is voted on again on {ends}."]
            y = rect.top + self.LIST_HEAD + 14
            for line in lines:
                self._put(surf, line, (left, y))
                y += 28
            return

        office = council.offices[candidacy.office]
        title = f"Your seat as {office.name} is voted on" if candidacy.defending else f"You stand for {office.name}"
        self._put(surf, title, (left, rect.top + 12), self.name_font)
        self._put(surf, f"The council sits on {format_long(session_moment(candidacy.session))}, at "
                        f"{session_moment(candidacy.session).hour} o'clock", (left, rect.top + 46), colour=FAINT_INK)
        holder = council.seats[office.key].holder
        x = left
        for candidate in candidacy.candidates:
            draw_arms(surf, pygame.Rect(x, rect.top + 82, 40, 48), arms_of(council, candidate))
            self._put(surf, council.name_of(candidate), (x + 50, rect.top + 84),
                      colour=RUBRIC if candidate == PLAYER else INK)
            self._put(surf, "holds the seat" if candidate == holder else "stands for it", (x + 50, rect.top + 108),
                      self.small_font, FAINT_INK)
            x += 218
        if len(candidacy.candidates) == 1:
            self._put(surf, "Nobody stands against you so far.", (x + 10, rect.top + 96), colour=GOOD_INK)
        pygame.draw.line(surf, BRASS, (left, rect.top + 146), (rect.right - 22, rect.top + 146), 1)
        self._put(surf, "Those who vote", (left, rect.top + 150), self.small_font, FAINT_INK)

        voters = council.electorate(office.key, candidacy.candidates)
        for index, voter in enumerate(voters):
            row = self.voter_row_rect(index)
            if row.collidepoint(mouse):
                band = pygame.Surface(row.size, pygame.SRCALPHA)
                band.fill((*GOLD, 40))
                surf.blit(band, row)
            draw_arms(surf, pygame.Rect(row.left + 10, row.top + 4, 25, 30), council.notables[voter].arms)
            name = self._put(surf, council.name_of(voter), (row.left + 46, row.centery), anchor="midleft")
            notes = [self._role(voter)]
            if voter in candidacy.purses:
                notes.append("took your purse" if candidacy.purses[voter] else "refused your purse")
            if candidacy.delayed == voter:
                notes.append("to be delayed")
            self._put(surf, ", ".join(notes), (name.right + 12, row.centery + 1), self.small_font, FAINT_INK, "midleft")
            whom, _margin = council.leaning(voter)
            if whom == PLAYER:
                words, colour = "Leans to you", GOOD_INK
            elif whom is None:
                words, colour = "Undecided", INK
            else:
                words, colour = f"Leans to {council.name_of(whom).split()[0]}", RUBRIC
            self._put(surf, words, (row.right - 12, row.centery), colour=colour, anchor="midright")
            self._hot[f"voter:{voter}"] = (row, lambda voter=voter: self.show_notable(voter))

        mine, undecided, against = council.forecast()
        plaque(surf, self.body_font, f"For you {mine}     Undecided {undecided}     Against {against}",
               (rect.left + 220, rect.bottom - 62))
        self._put(surf, "The most votes take the seat; a tie leaves it with its holder. Click a voter to court them.",
                  (left, rect.bottom - 34), self.small_font, FAINT_INK)
        if not candidacy.defending:
            button = pygame.Rect(rect.right - self.BUTTON_W - 18, rect.bottom - self.BUTTON_H - 44, self.BUTTON_W,
                                 self.BUTTON_H)
            self._button(surf, "withdraw", button, "Withdraw your name", lambda: self._do(council.withdraw), True, mouse)

    def _draw_minutes(self, surf: pygame.Surface) -> None:
        rect = pygame.Rect(self.body.left + self.ELECTION_W + 14, self.body.top, self.BODY_W - self.ELECTION_W - 14,
                           self.BODY_H)
        _leaf(surf, rect)
        self._heading(surf, rect, "The council's minutes")
        y = rect.top + self.LIST_HEAD + 10
        if not self.council.minutes:
            self._put(surf, "Nothing has been decided yet.", (rect.left + 20, y), self.small_font, FAINT_INK)
            return
        for entry in reversed(self.council.minutes):
            lines = wrap(entry, self.small_font, rect.width - 52)
            if y + len(lines) * 21 > rect.bottom - 14:
                break
            surf.fill(BRASS_DARK, (rect.left + 20, y + 8, 5, 5))
            for line in lines:
                self._put(surf, line, (rect.left + 34, y), self.small_font)
                y += 21
            y += 9

    # -- the sheet ---------------------------------------------------------

    def _build_sheet(self) -> pygame.Surface:
        sheet = framed_sheet((self.W, self.H))
        title = inked("The Town Council", self.sheet_title_font, GOLD)
        sheet.blit(title, title.get_rect(center=(self.W // 2, self.TITLE_Y)))
        draw_divider(sheet, (self.W // 2, self.DIVIDER_Y), 190)
        return sheet

    def _draw_plaques(self, surf: pygame.Surface) -> None:
        council = self.council
        office = council.player_office
        sits = format_long(council.next_session(self._date))
        for dx, text in ((-370, f"The council sits: {sits}"),
                         (0, f"Your office: {office.name if office else 'none'}"),
                         (330, f"Your purse: {self._depot.money:,.0f} coins")):
            plaque(surf, self.small_font, text, (self.W // 2 + dx, self.PLAQUE_Y))

    def _draw_close(self, surf: pygame.Surface, mouse: Tuple[int, int]) -> None:
        rect = self.close_local
        pygame.draw.rect(surf, (168, 52, 44) if rect.collidepoint(mouse) else RUBRIC, rect, border_radius=3)
        pygame.draw.rect(surf, GOLD, rect, 2, border_radius=3)
        inset = 9
        for start, end in (((rect.left + inset, rect.top + inset), (rect.right - inset - 1, rect.bottom - inset - 1)),
                           ((rect.left + inset, rect.bottom - inset - 1), (rect.right - inset - 1, rect.top + inset))):
            pygame.draw.line(surf, BRASS_LIGHT, start, end, 3)

    def draw(self, alpha_scale: float = 1.0) -> None:
        if alpha_scale <= 0:
            return
        if self._sheet is None:
            self._sheet = self._build_sheet()
        surf = self._sheet.copy()
        position = pygame.mouse.get_pos()
        mouse = (position[0] - self.panel.left, position[1] - self.panel.top)
        self._hot = {}

        for page, rect in self.tab_rects.items():
            draw_tab(surf, rect, page, self.body_font, page == self.page, False, rect.collidepoint(mouse))
        self._draw_plaques(surf)
        if self.page == PAGE_OFFICES:
            self._draw_offices(surf, mouse)
        elif self.page == PAGE_NOTABLES:
            self._draw_notable_list(surf, mouse)
            self._draw_notable(surf, mouse)
        else:
            self._draw_contest(surf, mouse)
            self._draw_minutes(surf)
        if self.message is not None:
            self._put(surf, self.message.text, (self.W // 2, self.H - self.MESSAGE_H // 2 - 4),
                      colour=GOOD_INK if self.message.ok else RUBRIC, anchor="center")
        self._draw_close(surf, mouse)

        if alpha_scale < 1.0:
            surf.set_alpha(int(255 * alpha_scale))
        else:
            shadow = pygame.Surface(self.panel.size, pygame.SRCALPHA)
            shadow.fill((0, 0, 0, 90))
            self.screen.blit(shadow, self.panel.move(6, 8))
        self.screen.blit(surf, self.panel.topleft)
