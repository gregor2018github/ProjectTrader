"""The Gourmet Collection, opened at the guildhall: every tavern dish, those tasted and those not.

A page each for the plates, the bowls and the drinks (`Dish.type`), on the sheet the
guild's records are drawn on (`records_window.py`), in a table's colours of its own
(`GOURMET_PAGE`): saffron and honey gold on cream, umber for what is dark, a linen's
weave in the frame's band, and the pictures in their gold frames. Every dish is a card: its picture,
its name and how often it was eaten; clicking a tasted one shows its picture large over
the collection (the tavern's `DishServedWindow`, kept in `enlarged`, the collection dimmed
behind it), and a click or Escape puts it away again. A dish not tasted yet is greyed
out with a question mark for its name, and of its picture only its outline is shown, a
flat grey shape, so a plate is a plate and a cup a cup, but what is on it cannot be told. Hovering a card tells more: what it is, where it is served and what it
does for the player (models/meal_effects.py); of a dish not tasted only where it is
served. The dishes go from the plain tavern's to the fine one's, by course and price
within each.

What a dish has been eaten comes from `Statistics.dishes_tried`, by `dish_key`. The
small pictures and the silhouettes are files made ahead (`ui/dish_previews.py`), loaded
as a page is first shown; a dish without one shows a drawn outline of a plate, bowl or
cup.
"""

import os
from typing import Dict, List, Optional, Sequence, Tuple, TYPE_CHECKING

import pygame

from .loan_dialog import _BaseDialog
from .tavern_menu_window import DishServedWindow, dish_picture
from .charter_style import BlockColours
from .records_window import (
    PageTheme, RecordsWindow, _FAINT_INK, _FAINT_RULE, _leaf, _picture_frame, _plaque, _tab, _title,
)
from ..dish_previews import PREVIEW_SIZE, load_preview
from ..layout_modules.effect_circles import line_pitch
from ...config.constants import FONTS_PATH
from ...models import meal_effects
from ...models.minigames.tutorial_sheet import (
    BRASS, BRASS_DARK, BRASS_LIGHT, INK, WEAVE, SheetTheme, framed_sheet, title_tablet,
)
from ...models.tavern_menu import COURSES, DISH_TYPES, TAVERN_CLASSES, Dish, all_dishes, dish_key, dish_picture_path

if TYPE_CHECKING:
    from ...game_state import GameState

UNKNOWN_NAME = "?"
#: The pages, a dish's type each, and their names on the tabs
PAGE_NAMES: Dict[str, str] = {"plate": "Plates", "bowl": "Bowls", "drink": "Drinks"}
#: Where each class of dish is served, as the cards say it
SERVED_AT: Dict[str, str] = {"low": "a plain tavern", "middle": "a good inn", "high": "a fine tavern"}
_PLATE_EMPTY = (226, 214, 188)       # behind a tasted dish's picture
SILHOUETTE_GROUND = (198, 190, 174)  # behind an untasted one's outline

# Saffron and honey on cream, umber for the dark: a laid table. The pictures keep their brass
# frames (``accent``), what was red elsewhere is umber or a burnt sienna here.
_UMBER, _UMBER_DEEP, _OLD_GOLD, _SAFFRON = (104, 72, 38), (76, 50, 24), (150, 110, 40), (204, 152, 52)
_SIENNA, _CREAM = (146, 78, 38), (246, 234, 204)
GOURMET_PAGE = PageTheme(
    sheet=SheetTheme(edge_dark=_OLD_GOLD, edge_light=(226, 188, 96), rule=(150, 110, 40),
                     band_wash=(232, 204, 132, 90), strands=(_SAFFRON, _UMBER), bead_dark=_UMBER,
                     bead_light=_CREAM,
                     block=BlockColours(edge=_UMBER_DEEP, rule=_OLD_GOLD, ornament=(214, 170, 82), boss=_SIENNA),
                     texture=WEAVE, texture_colour=(150, 110, 40, 46)),
    title=((246, 214, 128), (150, 96, 26)), accent=BRASS, accent_dark=BRASS_DARK, accent_light=BRASS_LIGHT,
    leaf_fill=(255, 250, 232, 130),
    tab_current=(_UMBER, (226, 188, 96), _CREAM), tab_other=((228, 204, 146), (240, 220, 170), _OLD_GOLD, INK),
    seal=(_SIENNA, _UMBER_DEEP, _CREAM), laurel=(_SAFFRON, _UMBER, _SIENNA), glow=(240, 196, 96))


def open_gourmet_window(game_state: 'GameState') -> None:
    game_state.info_window = GourmetWindow(game_state.screen, game_state)


def dishes_of(dish_type: str, dishes: Optional[Sequence[Dish]] = None) -> List[Dish]:
    """The dishes of a type in the order the page shows them: by tavern class, course, price, name."""
    course_order = {course: i for i, (course, _heading) in enumerate(COURSES)}
    chosen = [d for d in (all_dishes() if dishes is None else dishes) if d.type == dish_type]
    return sorted(chosen, key=lambda d: (TAVERN_CLASSES.index(d.tavern_class), course_order.get(d.course, 99),
                                         d.price, d.name))


def times_eaten(stats, dish: Dish) -> int:
    return stats.dishes_tried.get(dish_key(dish), 0)


def eaten_text(times: int) -> str:
    if times == 0:
        return "Not yet tasted"
    return "Eaten once" if times == 1 else f"Eaten {times} times"


def _wrap(text: str, font: pygame.font.Font, width: int) -> List[str]:
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


class GourmetWindow(_BaseDialog):
    theme = GOURMET_PAGE         # read by the records' close button too
    COLUMNS = 11
    CARD_W, CARD_H = 140, 172
    GAP = 10
    MARGIN = 44
    TITLE_Y = 49                 # on its tablet, which stands over the frame's band
    TAB_TOP = 100
    TAB_W, TAB_H = 200, 38
    BODY_TOP = 152
    PLAQUES_H = 46
    ROWS = 4                     # enough for the plates, the longest page
    BODY_H = PLAQUES_H + ROWS * CARD_H + (ROWS - 1) * GAP
    W = COLUMNS * CARD_W + (COLUMNS - 1) * GAP + 2 * MARGIN
    H = BODY_TOP + BODY_H + MARGIN
    PICTURE_W, PICTURE_H = PREVIEW_SIZE
    TOOLTIP_W, TOOLTIP_PAD = 340, 12

    def __init__(self, screen: pygame.Surface, game_state: 'GameState',
                 dishes: Optional[Sequence[Dish]] = None) -> None:
        super().__init__(screen, game_state, self.W, self.H)
        self.sheet_title_font = RecordsWindow._medici(46, 36)
        self.name_font = self._font("RomanAntique.ttf", 17)
        self.unknown_font = RecordsWindow._medici(40, 32)
        self.small_font = self._font("RomanAntique.ttf", 15)
        self.tip_title_font = RecordsWindow._medici(24, 22)
        self.pages: Dict[str, List[Dish]] = {kind: dishes_of(kind, dishes) for kind in DISH_TYPES}
        self.page = DISH_TYPES[0]
        self._sheets: Dict[str, pygame.Surface] = {}
        self.enlarged: Optional[DishServedWindow] = None   # a dish's picture shown large over the collection
        self._dim: Optional[pygame.Surface] = None
        self.close_rect = pygame.Rect(0, 0, 30, 30)
        self.close_rect.center = (self.panel.right - 64, self.panel.top + 60)   # below the frame's band
        tabs_w = len(DISH_TYPES) * self.TAB_W + (len(DISH_TYPES) - 1) * self.GAP
        left = self.panel.centerx - tabs_w // 2
        self.tab_rects = {kind: pygame.Rect(left + i * (self.TAB_W + self.GAP), self.panel.top + self.TAB_TOP,
                                            self.TAB_W, self.TAB_H)
                          for i, kind in enumerate(DISH_TYPES)}
        self.body = pygame.Rect(self.panel.left + self.MARGIN, self.panel.top + self.BODY_TOP,
                                self.W - 2 * self.MARGIN, self.BODY_H)

    @staticmethod
    def _font(name: str, size: int) -> pygame.font.Font:
        try:
            return pygame.font.Font(os.path.join(FONTS_PATH, name), size)
        except Exception:
            return pygame.font.SysFont("georgia", size)

    @property
    def _stats(self):
        return self.game_state.game.depot.stats

    def tasted(self, dish: Dish) -> bool:
        return times_eaten(self._stats, dish) > 0

    # -- where things are ---------------------------------------------------

    def card_rect(self, index: int) -> pygame.Rect:
        """Where a card of the page lies on the screen."""
        row, column = divmod(index, self.COLUMNS)
        return pygame.Rect(self.body.left + column * (self.CARD_W + self.GAP),
                           self.body.top + self.PLAQUES_H + row * (self.CARD_H + self.GAP),
                           self.CARD_W, self.CARD_H)

    def picture_rect(self, card: pygame.Rect) -> pygame.Rect:
        return pygame.Rect(card.centerx - self.PICTURE_W // 2, card.top + 10, self.PICTURE_W, self.PICTURE_H)

    def hovered_dish(self, pos: Tuple[int, int]) -> Optional[Dish]:
        for index, dish in enumerate(self.pages[self.page]):
            if self.card_rect(index).collidepoint(pos):
                return dish
        return None

    def _local(self, rect: pygame.Rect) -> pygame.Rect:
        return rect.move(-self.panel.left, -self.panel.top)

    # -- input --------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> None:
        if self.enlarged is not None and event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.enlarged = None

    def handle_click(self, pos: Tuple[int, int]) -> bool:
        if self.enlarged is not None:
            self.enlarged = None              # any click puts the large picture away, the collection stays
            return True
        for kind, rect in self.tab_rects.items():
            if rect.collidepoint(pos):
                self.page = kind
                return True
        dish = self.hovered_dish(pos)
        if dish is not None:
            self.enlarge(dish)
            return True
        return super().handle_click(pos)

    def enlarge(self, dish: Dish) -> bool:
        """Show a tasted dish's picture large over the collection. False if it cannot be."""
        if not self.tasted(dish):
            return False
        picture = dish_picture(dish)
        if picture is None:
            return False
        self.enlarged = DishServedWindow(self.screen, self.game_state, self, dish, picture,
                                         back_hint="Click to go back to the collection.")
        return True

    # -- the pages, drawn once ----------------------------------------------

    def _build_page(self, kind: str) -> pygame.Surface:
        theme = self.theme
        sheet = framed_sheet((self.W, self.H), corner_blocks=True, theme=theme.sheet)
        whole = sheet.get_rect()
        title = _title("Gourmet Collection", self.sheet_title_font, theme)
        title_tablet(sheet, title, whole.centerx, theme.sheet, self.TITLE_Y)   # over the band, clear of its waves

        stats = self._stats
        every = [d for dishes in self.pages.values() for d in dishes]
        page = self.pages[kind]
        body = self._local(self.body)
        tasted_all = sum(times_eaten(stats, d) > 0 for d in every)
        meals = sum(times_eaten(stats, d) for d in every)
        for dx, text in ((-420, f"Dishes tasted: {tasted_all} of {len(every)}"),
                         (0, f"{PAGE_NAMES[kind]} tasted: {sum(times_eaten(stats, d) > 0 for d in page)} of {len(page)}"),
                         (420, f"Meals eaten out: {meals:,}")):
            _plaque(sheet, self.body_font, text, (body.centerx + dx, body.top + 16), theme)
        for index, dish in enumerate(page):
            self._draw_card(sheet, index, dish)
        return sheet

    def _draw_card(self, sheet: pygame.Surface, index: int, dish: Dish) -> None:
        tasted = self.tasted(dish)
        card = self._local(self.card_rect(index))
        _leaf(sheet, card, tasted, self.theme)
        picture = self._local(self.picture_rect(self.card_rect(index)))
        _picture_frame(sheet, picture, tasted, self.theme)
        sheet.fill(_PLATE_EMPTY if tasted else SILHOUETTE_GROUND, picture)
        preview = load_preview(dish_key(dish), tasted)
        if preview is not None:
            sheet.blit(preview, preview.get_rect(center=picture.center))
        else:
            # No picture made: the outline of a dish of its type
            self._outline(sheet, picture, dish.type, tasted)

        y = picture.bottom + 10
        if tasted:
            for line in _wrap(dish.name, self.name_font, card.width - 14)[:2]:
                text = self.name_font.render(line, True, INK)
                sheet.blit(text, text.get_rect(midtop=(card.centerx, y)))
                y += line_pitch(self.name_font) - 4   # the font's own line size is wrong
        else:
            mark = self.unknown_font.render(UNKNOWN_NAME, True, _FAINT_INK)
            sheet.blit(mark, mark.get_rect(midtop=(card.centerx, y - 6)))
        pygame.draw.line(sheet, BRASS if tasted else _FAINT_RULE,
                         (card.left + 14, card.bottom - 26), (card.right - 14, card.bottom - 26), 1)
        count = self.small_font.render(eaten_text(times_eaten(self._stats, dish)), True, INK if tasted else _FAINT_INK)
        sheet.blit(count, count.get_rect(midbottom=(card.centerx, card.bottom - 7)))

    @staticmethod
    def _outline(sheet: pygame.Surface, picture: pygame.Rect, dish_type: str, tasted: bool) -> None:
        """A plain plate, bowl or cup drawn in ink, where its picture is still to come or there is none."""
        ink = BRASS_DARK if tasted else _FAINT_INK
        cx, cy = picture.center
        if dish_type == "plate":
            pygame.draw.ellipse(sheet, ink, pygame.Rect(cx - 44, cy - 18, 88, 36), 2)
            pygame.draw.ellipse(sheet, ink, pygame.Rect(cx - 28, cy - 10, 56, 20), 1)
        elif dish_type == "bowl":
            pygame.draw.ellipse(sheet, ink, pygame.Rect(cx - 36, cy - 18, 72, 16), 2)
            pygame.draw.arc(sheet, ink, pygame.Rect(cx - 36, cy - 40, 72, 64), 3.3, 6.12, 2)
            pygame.draw.line(sheet, ink, (cx - 12, cy + 24), (cx + 12, cy + 24), 2)
        else:
            pygame.draw.lines(sheet, ink, False, [(cx - 18, cy - 26), (cx - 14, cy + 24), (cx + 14, cy + 24),
                                                  (cx + 18, cy - 26)], 2)
            pygame.draw.arc(sheet, ink, pygame.Rect(cx + 10, cy - 14, 22, 26), -1.6, 1.6, 2)

    # -- what changes from frame to frame -----------------------------------

    def _draw_tabs(self, surf: pygame.Surface, off: Tuple[int, int], mouse: Tuple[int, int]) -> None:
        for kind, rect in self.tab_rects.items():
            page = self.pages[kind]
            label = f"{PAGE_NAMES[kind]}  {sum(self.tasted(d) for d in page)}/{len(page)}"
            _tab(surf, rect.move(*off), label, self.body_font, kind == self.page, rect.collidepoint(mouse), self.theme, 0)

    def tooltip_lines(self, dish: Dish) -> List[Tuple[str, Tuple[int, int, int]]]:
        """What hovering a card tells: all of it for a dish tasted, only where it is served otherwise."""
        served = f"Served at {SERVED_AT.get(dish.tavern_class, 'a tavern')}"
        if not self.tasted(dish):
            return [("Not yet tasted", _FAINT_INK), (served, INK)]
        effect = meal_effects.describe(meal_effects.effect_kind(dish), meal_effects.effect_strength(dish.price))
        hours = meal_effects.describe_hours(meal_effects.meal_hours(dish))
        return ([(line, (90, 70, 50)) for line in _wrap(dish.description, self.small_font,
                                                         self.TOOLTIP_W - 2 * self.TOOLTIP_PAD)]
                + [(f"{served}, {dish.price:.2f} coins", INK),
                   (f"{effect}, {hours}", (40, 96, 40)),
                   (eaten_text(times_eaten(self._stats, dish)), INK)]
                + ([("Click to see it larger", _FAINT_INK)] if os.path.exists(dish_picture_path(dish)) else []))

    def _draw_tooltip(self, surf: pygame.Surface, dish: Dish, mouse: Tuple[int, int], off: Tuple[int, int]) -> None:
        title = self.tip_title_font.render(dish.name if self.tasted(dish) else UNKNOWN_NAME, True, INK)
        lines = [self.small_font.render(text, True, colour) for text, colour in self.tooltip_lines(dish)]
        pitch = line_pitch(self.small_font)
        box = pygame.Rect(0, 0, self.TOOLTIP_W, 2 * self.TOOLTIP_PAD + title.get_height() + 6 + pitch * len(lines))
        box.topleft = (mouse[0] + 18, mouse[1] + 18)
        panel = self.panel.inflate(-12, -12)
        if box.right > panel.right:
            box.right = mouse[0] - 12
        if box.bottom > panel.bottom:
            box.bottom = mouse[1] - 12
        box = box.move(*off)
        pygame.draw.rect(surf, (250, 242, 220), box, border_radius=4)
        pygame.draw.rect(surf, _UMBER, box, 2, border_radius=4)
        pygame.draw.rect(surf, BRASS, box.inflate(-6, -6), 1, border_radius=3)
        y = box.top + self.TOOLTIP_PAD
        surf.blit(title, (box.left + self.TOOLTIP_PAD, y))
        y += title.get_height() + 6
        for line in lines:
            surf.blit(line, (box.left + self.TOOLTIP_PAD, y))
            y += pitch

    def draw(self, alpha_scale: float = 1.0) -> None:
        if alpha_scale <= 0:
            return
        use_temp = alpha_scale < 1.0
        if use_temp:
            surf = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
            off = (-self.panel.left, -self.panel.top)
        else:
            surf = self.screen
            off = (0, 0)
            shadow = pygame.Surface(self.panel.size, pygame.SRCALPHA)
            shadow.fill((0, 0, 0, 90))
            surf.blit(shadow, self.panel.move(6, 8))

        if self.page not in self._sheets:
            self._sheets[self.page] = self._build_page(self.page)
        surf.blit(self._sheets[self.page], self.panel.move(*off))

        mouse = pygame.mouse.get_pos()
        self._draw_tabs(surf, off, mouse)
        RecordsWindow._draw_close(self, surf, off, mouse)
        dish = self.hovered_dish(mouse) if not use_temp and self.enlarged is None else None
        if dish is not None:
            index = self.pages[self.page].index(dish)
            glow = pygame.Surface(self.card_rect(index).size, pygame.SRCALPHA)
            glow.fill((*self.theme.glow, 50))
            surf.blit(glow, self.card_rect(index).move(*off))
            self._draw_tooltip(surf, dish, mouse, off)

        if use_temp:
            surf.set_alpha(int(255 * alpha_scale))
            self.screen.blit(surf, self.panel.topleft)
        elif self.enlarged is not None:
            # The collection dimmed behind the dish's picture
            if self._dim is None or self._dim.get_size() != self.screen.get_size():
                self._dim = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
                self._dim.fill((0, 0, 0, 110))
            self.screen.blit(self._dim, (0, 0))
            self.enlarged.draw()
