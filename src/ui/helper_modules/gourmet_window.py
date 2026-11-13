"""The Gourmet Collection, opened at the guildhall: every tavern dish, those tasted and those not.

A page each for the plates, the bowls and the drinks (`Dish.type`), on the sheet the
guild's records are drawn on (`records_window.py`). Every dish is a card: its picture,
its name and how often it was eaten; clicking a tasted one shows its picture large
(the tavern's `DishServedWindow`, which comes back here). A dish not tasted yet is greyed
out with a question mark for its name, and of its picture only its outline is shown, a
flat grey shape (`silhouette`), so a plate is a plate and a cup a cup, but what is on it
cannot be told. Hovering a card tells more: what it is, where it is served and what it
does for the player (models/meal_effects.py); of a dish not tasted only where it is
served. The dishes go from the plain tavern's to the fine one's, by course and price
within each.

The pictures have a painted wall and table behind the dish, no see-through background,
so the outline is found from the picture: the colours along its edges are the
background's, everything reached from the edges through such colours is background, and
the rest is the dish (`dish_mask`). The dish's own outline is thickened before the
background is let in and thinned after (`SILHOUETTE_CLOSE_PX`), so it does not leak in
where food is coloured like the table, and thin bits (crumbs by a bowl) are trimmed off
(`SILHOUETTE_TRIM_PX`). It is worked out at twice the size, its edge rounded off and
made soft (`SILHOUETTE_ROUND`, `SILHOUETTE_FEATHER`).

What a dish has been eaten comes from `Statistics.dishes_tried`, by `dish_key`. The
pictures are large, so their small copies (`thumbnail`) are made a few at a time while
the window is drawn (`THUMB_BUDGET_S` a frame) and kept for the next time; until then a
card shows a plain dish's outline.
"""

import os
import time
from typing import Dict, List, Optional, Sequence, Tuple, TYPE_CHECKING

import pygame

from .loan_dialog import _BaseDialog
from .tavern_menu_window import DishServedWindow, dish_picture
from .records_window import RecordsWindow, _FAINT_INK, _leaf, _picture_frame
from ..layout_modules.effect_circles import line_pitch
from ...config.colors import GOLD
from ...config.constants import FONTS_PATH
from ...models import meal_effects
from ...models.minigames.tutorial_sheet import BRASS, BRASS_DARK, INK, draw_tab, framed_sheet, inked, plaque
from ...models.minigames.woodhacking import draw_divider
from ...models.tavern_menu import COURSES, DISH_TYPES, TAVERN_CLASSES, Dish, all_dishes, dish_key, dish_picture_path

if TYPE_CHECKING:
    from ...game_state import GameState

UNKNOWN_NAME = "?"
#: The pages, a dish's type each, and their names on the tabs
PAGE_NAMES: Dict[str, str] = {"plate": "Plates", "bowl": "Bowls", "drink": "Drinks"}
#: Where each class of dish is served, as the cards say it
SERVED_AT: Dict[str, str] = {"low": "a plain tavern", "middle": "a good inn", "high": "a fine tavern"}
#: How long making the pictures' small copies may take a frame
THUMB_BUDGET_S = 0.012
#: The outline of a dish not tasted yet: its colour, the background it stands on
SILHOUETTE = (128, 118, 104)
SILHOUETTE_GROUND = (198, 190, 174)
#: Finding the dish in its picture: how near a background colour a pixel must be (each channel),
#: how far the dish's own outline is thickened while the background is let in, and how thin
#: a bit sticking out is trimmed off; and the share of the largest shape a lone bit must have
SILHOUETTE_TOLERANCE = 20
SILHOUETTE_CLOSE_PX = 3
SILHOUETTE_TRIM_PX = 2
SILHOUETTE_KEEP_SHARE = 0.03
#: Smoothing the outline: how much its ragged edge is rounded off, and how soft its edge is
#: (each the times a picture is made smaller to blur it; more is smoother)
SILHOUETTE_ROUND = 4
SILHOUETTE_FEATHER = 6
_PLATE_EMPTY = (226, 214, 188)   # a card's picture still being made, or a dish with none

_thumbs: Dict[Tuple[str, bool], Optional[pygame.Surface]] = {}   # (path, tasted) -> its small copy


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


def _grow(mask: pygame.mask.Mask, radius: int) -> pygame.mask.Mask:
    """The mask with every set pixel spread to a disc of `radius` round it."""
    grown = pygame.mask.Mask(mask.get_size())
    for dx in range(-radius, radius + 1):
        for dy in range(-radius, radius + 1):
            if dx * dx + dy * dy <= radius * radius:
                grown.draw(mask, (dx, dy))
    return grown


def _shrink(mask: pygame.mask.Mask, radius: int) -> pygame.mask.Mask:
    """The mask with `radius` taken off its every edge."""
    outside = mask.copy()
    outside.invert()
    shrunk = _grow(outside, radius)
    shrunk.invert()
    return shrunk


def dish_mask(picture: pygame.Surface) -> pygame.mask.Mask:
    """Where the dish is in its picture, as a solid shape (see the module)."""
    w, h = picture.get_size()
    edge = ([picture.get_at((x, y))[:3] for x in range(0, w, 3) for y in (0, 1, h - 2, h - 1)]
            + [picture.get_at((x, y))[:3] for y in range(0, h, 3) for x in (0, 1, w - 2, w - 1)])
    palette: List[Tuple[int, int, int]] = []
    for colour in edge:
        if all(sum(abs(a - b) for a, b in zip(colour, known)) > 18 for known in palette):
            palette.append(colour)
    tolerance = (SILHOUETTE_TOLERANCE, SILHOUETTE_TOLERANCE, SILHOUETTE_TOLERANCE, 255)
    like_background = pygame.mask.Mask((w, h))
    for colour in palette:
        like_background.draw(pygame.mask.from_threshold(picture, colour, tolerance), (0, 0))
    dish = like_background.copy()
    dish.invert()
    # The background is what the edges reach past the thickened dish; all else is the dish, holes filled
    open_ground = _grow(dish, SILHOUETTE_CLOSE_PX)
    open_ground.invert()
    background = pygame.mask.Mask((w, h))
    for part in open_ground.connected_components():
        if any(r.left == 0 or r.top == 0 or r.right == w or r.bottom == h for r in part.get_bounding_rects()):
            background.draw(part, (0, 0))
    background = _grow(background, SILHOUETTE_CLOSE_PX)   # the thickening taken off again
    shape = background.copy()
    shape.invert()
    # Thin bits trimmed off, and lone bits far smaller than the dish dropped
    shape = _grow(_shrink(shape, SILHOUETTE_TRIM_PX), SILHOUETTE_TRIM_PX)
    parts = shape.connected_components()
    kept = pygame.mask.Mask((w, h))
    if parts:
        largest = max(part.count() for part in parts)
        for part in parts:
            if part.count() >= SILHOUETTE_KEEP_SHARE * largest:
                kept.draw(part, (0, 0))
    return kept


def silhouette(picture: pygame.Surface, size: Tuple[int, int]) -> pygame.Surface:
    """The dish's outline as a flat grey shape, `size` large, with smooth edges.

    The shape is found at twice the size (`dish_mask`), whose edge is ragged; it is rounded
    off by blurring it (made `SILHOUETTE_ROUND` times smaller and large again at four times
    the size) and cutting it back to a sharp shape there, and then given a soft edge
    (blurred again, `SILHOUETTE_FEATHER`, and kept soft as it comes down to `size`).
    """
    w, h = size
    double = pygame.transform.smoothscale(picture, (w * 2, h * 2))
    shape = dish_mask(double).to_surface(setcolor=(255, 255, 255, 255), unsetcolor=(0, 0, 0, 255))
    blurred = pygame.transform.smoothscale(
        pygame.transform.smoothscale(shape, (max(1, w * 2 // SILHOUETTE_ROUND), max(1, h * 2 // SILHOUETTE_ROUND))),
        (w * 4, h * 4))
    rounded = pygame.mask.from_threshold(blurred, (255, 255, 255), (128, 128, 128, 255))
    sharp = rounded.to_surface(setcolor=(255, 255, 255, 255), unsetcolor=(255, 255, 255, 0))
    soft = pygame.transform.smoothscale(
        pygame.transform.smoothscale(sharp, (max(1, w * 4 // SILHOUETTE_FEATHER), max(1, h * 4 // SILHOUETTE_FEATHER))),
        size)
    soft.fill(SILHOUETTE, special_flags=pygame.BLEND_RGB_MIN)   # white to the grey, the soft edge kept
    return soft


def thumbnail(dish: Dish, tasted: bool, size: Tuple[int, int]) -> Optional[pygame.Surface]:
    """The dish's picture made small to fit `size`, or only its outline if not tasted; None if it has none."""
    path = dish_picture_path(dish)
    key = (path, tasted)
    if key not in _thumbs:
        picture = None
        if os.path.exists(path):
            try:
                big = pygame.image.load(path)
                scale = min(size[0] / big.get_width(), size[1] / big.get_height())
                fitted = (max(1, round(big.get_width() * scale)), max(1, round(big.get_height() * scale)))
                if tasted:
                    picture = pygame.transform.smoothscale(big, fitted)
                else:
                    picture = silhouette(big.convert() if pygame.display.get_surface() else big, fitted)
                if pygame.display.get_surface() is not None:
                    picture = picture.convert_alpha()
            except pygame.error as error:
                print(f"Warning: could not read the picture of {dish.name!r}: {error}")
                picture = None
        _thumbs[key] = picture
    return _thumbs[key]


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
    COLUMNS = 11
    CARD_W, CARD_H = 140, 172
    GAP = 10
    MARGIN = 44
    TITLE_Y, DIVIDER_Y = 46, 80
    TAB_TOP = 94
    TAB_W, TAB_H = 200, 38
    BODY_TOP = 146
    PLAQUES_H = 46
    ROWS = 4                     # enough for the plates, the longest page
    BODY_H = PLAQUES_H + ROWS * CARD_H + (ROWS - 1) * GAP
    W = COLUMNS * CARD_W + (COLUMNS - 1) * GAP + 2 * MARGIN
    H = BODY_TOP + BODY_H + MARGIN
    PICTURE_W, PICTURE_H = 124, 88
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
        self._waiting: Dict[str, List[int]] = {}     # the cards of a page whose pictures are still to come
        self.close_rect = pygame.Rect(0, 0, 30, 30)
        self.close_rect.center = (self.panel.right - 19, self.panel.top + 19)
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

    def handle_click(self, pos: Tuple[int, int]) -> bool:
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
        """Show a tasted dish's picture large; a click there comes back here. False if it cannot be."""
        if not self.tasted(dish):
            return False
        picture = dish_picture(dish)
        if picture is None:
            return False
        self.game_state.info_window = DishServedWindow(self.screen, self.game_state, self, dish, picture,
                                                       back_hint="Click to go back to the collection.")
        return True

    # -- the pages, drawn once ----------------------------------------------

    def _build_page(self, kind: str) -> pygame.Surface:
        sheet = framed_sheet((self.W, self.H))
        whole = sheet.get_rect()
        title = inked("Gourmet Collection", self.sheet_title_font, GOLD)
        sheet.blit(title, title.get_rect(center=(whole.centerx, self.TITLE_Y)))
        draw_divider(sheet, (whole.centerx, self.DIVIDER_Y), 210)

        stats = self._stats
        every = [d for dishes in self.pages.values() for d in dishes]
        page = self.pages[kind]
        body = self._local(self.body)
        tasted_all = sum(times_eaten(stats, d) > 0 for d in every)
        meals = sum(times_eaten(stats, d) for d in every)
        for dx, text in ((-420, f"Dishes tasted: {tasted_all} of {len(every)}"),
                         (0, f"{PAGE_NAMES[kind]} tasted: {sum(times_eaten(stats, d) > 0 for d in page)} of {len(page)}"),
                         (420, f"Meals eaten out: {meals:,}")):
            plaque(sheet, self.body_font, text, (body.centerx + dx, body.top + 16))
        for index, dish in enumerate(page):
            self._draw_card(sheet, index, dish)
        self._waiting[kind] = [i for i, dish in enumerate(page)
                               if (dish_picture_path(dish), self.tasted(dish)) not in _thumbs]
        return sheet

    def _draw_card(self, sheet: pygame.Surface, index: int, dish: Dish) -> None:
        tasted = self.tasted(dish)
        card = self._local(self.card_rect(index))
        _leaf(sheet, card, tasted)
        picture = self._local(self.picture_rect(self.card_rect(index)))
        _picture_frame(sheet, picture, tasted)
        sheet.fill(_PLATE_EMPTY if tasted else SILHOUETTE_GROUND, picture)
        known = (dish_picture_path(dish), tasted) in _thumbs
        thumb = _thumbs.get((dish_picture_path(dish), tasted)) if known else None
        if thumb is not None:
            sheet.blit(thumb, thumb.get_rect(center=picture.center))
        else:
            # Still being made, or no picture: the outline of a dish of its type
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
        pygame.draw.line(sheet, BRASS if tasted else (168, 150, 120),
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

    def _make_pictures(self) -> None:
        """Make the small copies of the shown page's pictures still to come, while time allows this frame."""
        waiting = self._waiting.get(self.page)
        if not waiting:
            return
        sheet = self._sheets[self.page]
        page = self.pages[self.page]
        started = time.perf_counter()
        while waiting and time.perf_counter() - started < THUMB_BUDGET_S:
            index = waiting.pop(0)
            thumbnail(page[index], self.tasted(page[index]), (self.PICTURE_W, self.PICTURE_H))
            self._draw_card(sheet, index, page[index])

    # -- what changes from frame to frame -----------------------------------

    def _draw_tabs(self, surf: pygame.Surface, off: Tuple[int, int], mouse: Tuple[int, int]) -> None:
        for kind, rect in self.tab_rects.items():
            page = self.pages[kind]
            label = f"{PAGE_NAMES[kind]}  {sum(self.tasted(d) for d in page)}/{len(page)}"
            draw_tab(surf, rect.move(*off), label, self.body_font, kind == self.page, False, rect.collidepoint(mouse))

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
        pygame.draw.rect(surf, BRASS_DARK, box, 2, border_radius=4)
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
        self._make_pictures()
        surf.blit(self._sheets[self.page], self.panel.move(*off))

        mouse = pygame.mouse.get_pos()
        self._draw_tabs(surf, off, mouse)
        RecordsWindow._draw_close(self, surf, off, mouse)
        dish = self.hovered_dish(mouse) if not use_temp else None
        if dish is not None:
            index = self.pages[self.page].index(dish)
            glow = pygame.Surface(self.card_rect(index).size, pygame.SRCALPHA)
            glow.fill((*GOLD, 50))
            surf.blit(glow, self.card_rect(index).move(*off))
            self._draw_tooltip(surf, dish, mouse, off)

        if use_temp:
            surf.set_alpha(int(255 * alpha_scale))
            self.screen.blit(surf, self.panel.topleft)
