"""Meals for the poor: goods given to the church, opened from its house menu ("Donate Goods").

One card per feast in CHURCH_FEASTS: a banner with its name, a framed cell per
good it takes with how many the player has (red where they fall short), and a
button giving them, whose tooltip tells their worth at today's prices. The
church books and rewards the gift (Church.donate_feast); this window only shows
and asks.
"""

import pygame
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple
from .loan_dialog import _BaseDialog, _close_dialog
from ...config.colors import BLACK, DARK_BROWN, DARK_GREEN, DARK_RED, GRAY
from ...config.constants import CHURCH_FEASTS

if TYPE_CHECKING:
    from ...game_state import GameState
    from ...models.institutions.church import Church

ICON_SIZE = 40
_icons: Dict[str, Optional[pygame.Surface]] = {}

INTRO = [
    "Give goods for a meal for the poor, and the church will feed",
    "the beggars of the town and the country round about.",
    "The goods must be in your stock.",
]

CARD_FILL = (250, 238, 205)
BANNER_FILL = (196, 160, 104)
CELL_FILL = (255, 248, 228)
CELL_SHORT_FILL = (246, 222, 210)   # a cell whose good falls short
BUTTON_FILL = (200, 170, 110)
BUTTON_IDLE_FILL = (190, 180, 165)  # not enough goods: greyed, still clickable to say what is missing
TOOLTIP_FILL = (255, 250, 235)


class FeastMenu(_BaseDialog):
    W = 640
    MARGIN = 26        # between the panel's edge and the cards
    CARD_GAP = 14
    BANNER_H = 30
    CELL_W, CELL_H = 134, 58
    CELL_GAP = 10
    CARD_H = BANNER_H + 14 + CELL_H + 14 + _BaseDialog.BTN_H + 14

    def __init__(self, screen: pygame.Surface, game_state: 'GameState', church: 'Church') -> None:
        intro_h = len(INTRO) * 24 + 14
        height = (self.HDR + self.PAD + intro_h
                  + len(CHURCH_FEASTS) * (self.CARD_H + self.CARD_GAP) - self.CARD_GAP + self.MARGIN)
        super().__init__(screen, game_state, self.W, height)
        self.church = church
        self.house = church  # closes the menu when the player walks off (map_view)
        top = self.panel.top + self.HDR + self.PAD + intro_h
        self.cards: List[pygame.Rect] = [
            pygame.Rect(self.panel.left + self.MARGIN, top + i * (self.CARD_H + self.CARD_GAP),
                        self.W - 2 * self.MARGIN, self.CARD_H)
            for i in range(len(CHURCH_FEASTS))
        ]
        self.buttons: List[pygame.Rect] = [
            pygame.Rect(card.centerx - 100, card.bottom - self.BTN_H - 14, 200, self.BTN_H)
            for card in self.cards
        ]

    # -- input -----------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            _close_dialog(self.game_state)

    def handle_click(self, pos: Tuple[int, int]) -> bool:
        if self.close_rect.collidepoint(pos) or not self.panel.collidepoint(pos):
            _close_dialog(self.game_state)
            return True
        for index, button in enumerate(self.buttons):
            if button.collidepoint(pos):
                if self.church.donate_feast(self.game_state, index):
                    _close_dialog(self.game_state)
                return True
        return True

    # -- drawing ---------------------------------------------------------------

    def _icon(self, good_name: str) -> Optional[pygame.Surface]:
        if good_name not in _icons:
            images = self.game_state.game.images
            picture = images.get('goods_icon', {}).get(good_name)
            if picture is None:
                picture = images['goods_30'].get(good_name)
            if picture is None:
                _icons[good_name] = None
            else:
                scale = ICON_SIZE / max(picture.get_size())
                size = (max(1, round(picture.get_width() * scale)), max(1, round(picture.get_height() * scale)))
                _icons[good_name] = pygame.transform.smoothscale(picture, size).convert_alpha()
        return _icons[good_name]

    def _draw_cell(self, surf: pygame.Surface, rect: pygame.Rect, good_name: str, needed: int, have: int) -> None:
        enough = have >= needed
        pygame.draw.rect(surf, CELL_FILL if enough else CELL_SHORT_FILL, rect, border_radius=6)
        pygame.draw.rect(surf, DARK_BROWN, rect, 1, border_radius=6)
        icon = self._icon(good_name)
        if icon is not None:
            surf.blit(icon, icon.get_rect(center=(rect.left + 8 + ICON_SIZE // 2, rect.centery)))
        text_x = rect.left + 16 + ICON_SIZE
        self._text(surf, str(needed), text_x, rect.top + 6, DARK_GREEN if enough else DARK_RED)
        self._text(surf, f"have {have}", text_x, rect.top + 29, GRAY)

    def _draw_tooltip(self, surf: pygame.Surface, text: str, anchor: pygame.Rect) -> None:
        label = self.body_font.render(text, True, BLACK)
        box = label.get_rect().inflate(16, 10)
        box.midleft = (anchor.right + 10, anchor.centery)
        pygame.draw.rect(surf, TOOLTIP_FILL, box, border_radius=4)
        pygame.draw.rect(surf, DARK_BROWN, box, 1, border_radius=4)
        surf.blit(label, label.get_rect(center=box.center))

    def draw(self, alpha_scale: float = 1.0) -> None:
        if alpha_scale <= 0:
            return

        use_temp = alpha_scale < 1.0
        if use_temp:
            surf = pygame.Surface((self.panel.width, self.panel.height), pygame.SRCALPHA)
            off = (-self.panel.left, -self.panel.top)
        else:
            surf = self.screen
            off = (0, 0)

        self._draw_panel(surf, off)
        self._draw_close_btn(surf, off)
        self._draw_title(surf, off, "Meals for the Poor")

        game = self.game_state.game
        depot = game.depot
        mouse_pos = pygame.mouse.get_pos() if not use_temp else (-1, -1)
        p = self.panel.move(*off)

        y = p.top + self.HDR + self.PAD
        for line in INTRO:
            y = self._text(surf, line, p.centerx, y, BLACK, center=True) + 2

        hovered = None
        for (name, needed), card, button in zip(CHURCH_FEASTS, self.cards, self.buttons):
            card = card.move(*off)
            pygame.draw.rect(surf, CARD_FILL, card, border_radius=8)
            banner = pygame.Rect(card.left, card.top, card.width, self.BANNER_H)
            pygame.draw.rect(surf, BANNER_FILL, banner, border_top_left_radius=8, border_top_right_radius=8)
            pygame.draw.line(surf, DARK_BROWN, banner.bottomleft, (banner.right - 1, banner.bottom), 1)
            pygame.draw.rect(surf, DARK_BROWN, card, 2, border_radius=8)
            label = self.body_font.render(name, True, BLACK)
            surf.blit(label, label.get_rect(center=banner.center))

            row_w = len(needed) * self.CELL_W + (len(needed) - 1) * self.CELL_GAP
            x = card.centerx - row_w // 2
            for good_name, quantity in needed.items():
                cell = pygame.Rect(x, banner.bottom + 14, self.CELL_W, self.CELL_H)
                self._draw_cell(surf, cell, good_name, quantity, depot.good_stock.get(good_name, 0))
                x += self.CELL_W + self.CELL_GAP

            ready = not depot.missing_goods(needed)
            local_button = button.move(*off)
            self._draw_btn(surf, local_button, "Donate goods", mouse_pos,
                           color=BUTTON_FILL if ready else BUTTON_IDLE_FILL)
            if button.collidepoint(mouse_pos):
                hovered = (needed, local_button)

        # Last, so the cards above do not cover it
        if hovered is not None:
            needed, local_button = hovered
            prices = {good.name: good.get_price() for good in game.goods}
            worth = sum(quantity * prices.get(good_name, 0.0) for good_name, quantity in needed.items())
            self._draw_tooltip(surf, f"Worth {worth:,.0f}g at today's prices", local_button)

        if use_temp:
            surf.set_alpha(int(255 * alpha_scale))
            self.screen.blit(surf, self.panel)
