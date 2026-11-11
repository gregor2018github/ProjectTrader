"""Food: every tavern dish's picture, by type, and which are still missing.

Over everything, one block per type of dish (food.py: plates, bowls, drinks): how many of its dishes
have a picture, and the example the others of the type are to be drawn after, or that it has none yet.
On the left, the dishes of dishes.csv by type, a heading per type: the picture if there is one, the
name, class, course and price. On the right, the chosen dish: its picture large with its file, its
description, and the example its picture is drawn after.

Click a row (or Up / Down) to choose a dish; clicking a type's block over the list (or T) shows only that
type, clicking it again all of them; M shows only the dishes without a picture, O opens assets/pictures. "GIMP" beside a picture opens it in GIMP.
"""

import os
import sys

import pygame

from food import CLASS_TITLES, FOOD_PICTURES, PICTURES_DIR, TYPE_TITLES, TYPES, example_of, find_dishes, tally
from images import smooth_fit
from theme import BAR_BG, CARD_HOVER, CARD_SELECTED, DONE_COLOR, ERROR_COLOR, PANEL_GAP, TEXT, TEXT_DIM, THUMB_BG
from view import View
from widgets import Button, draw_panel, fit_text, progress_color, wrap_text

ROW_H = 58
HEAD_H = 34              # a type's heading in the list
THUMB = 50
SUMMARY_H = 96
TABLE_W = 470
DETAIL_MIN_W = 320
EXAMPLE_THUMB = 64       # the example's picture in the summary


def load_picture(path):
    """The picture at `path` for showing, or None if it cannot be read."""
    try:
        return pygame.image.load(str(path)).convert_alpha()
    except (pygame.error, OSError):
        return None


class FoodView(View):
    def __init__(self, app):
        super().__init__(app)
        self.switch_buttons = app.switch_buttons('food')
        self.only_missing = False
        self.type_filter = None   # None: every type, else a type key
        self.missing_button = Button('Only missing (M)', w=170)
        self.gimp_button = Button('GIMP', h=24, w=60)
        self.gimp_button.enabled = False
        self.dishes = []
        self.totals = {}
        self.examples = {}        # {type key: Dish or None}
        self.images = {}          # {dish name: Surface}, the pictures as read
        self.thumbs = {}          # {(dish name, size): Surface}
        self.chosen = None
        self.scroll = 0
        self.table = pygame.Rect(0, 0, 0, 0)
        self.rows = []            # [(Rect, dish)] as last drawn
        self.type_blocks = []     # [(Rect, type key)] of the summary, as last drawn

    def refresh(self):
        self.dishes = find_dishes()
        self.totals = tally(self.dishes)
        self.examples = {key: example_of(key, self.dishes) for key, _, _ in TYPES}
        self.images.clear()
        self.thumbs.clear()
        for dish in self.dishes:
            if dish.has_picture():
                image = load_picture(dish.picture)
                if image is not None:
                    self.images[dish.name] = image
        names = [d.name for d in self.dishes]
        if self.chosen not in names:
            self.chosen = names[0] if names else None

    def thumb(self, dish, size):
        image = self.images.get(dish.name)
        if image is None:
            return None
        if (dish.name, size) not in self.thumbs:
            self.thumbs[dish.name, size] = smooth_fit(image, (size, size))
        return self.thumbs[dish.name, size]

    def shown(self):
        return [d for d in self.dishes
                if (self.type_filter is None or d.type == self.type_filter)
                and (not self.only_missing or d.name not in self.images)]

    def chosen_dish(self):
        return next((d for d in self.dishes if d.name == self.chosen), None)

    def header(self):
        return ('Food',
                "The tavern dishes' pictures by type. Click a dish (or Up / Down), a type's block (or T) for only "
                'that type; M = only the missing, O = open the folder, Tab = next area.')

    def footer(self):
        return ((self.app.home_button,) + tuple(self.switch_buttons),
                (self.missing_button,))

    def update_footer(self):
        self.missing_button.label = 'Show all (M)' if self.only_missing else 'Only missing (M)'

    # --- drawing ----------------------------------------------------------

    def draw(self, screen, mouse):
        body = self.app.body()
        self.draw_summary(screen, pygame.Rect(body.x, body.y, body.w, SUMMARY_H))
        top = body.y + SUMMARY_H + PANEL_GAP + 6
        table_w = min(TABLE_W, max(260, body.w - DETAIL_MIN_W - PANEL_GAP))
        self.table = pygame.Rect(body.x, top, table_w, body.bottom - top)
        self.draw_table(screen, self.table, mouse)
        detail = pygame.Rect(self.table.right + PANEL_GAP, top, body.right - self.table.right - PANEL_GAP,
                             body.bottom - top)
        if detail.w >= 200:
            self.draw_detail(screen, detail, mouse)

    def draw_summary(self, screen, rect):
        """Per type: how many of its dishes have a picture, and its example."""
        fonts = self.app.fonts
        draw_panel(screen, fonts, rect, f'{len(self.dishes)} dishes in dishes.csv'
                   + (f', showing only the {TYPE_TITLES[self.type_filter].lower()}' if self.type_filter else ''))
        part = rect.w // len(TYPES)
        mouse = pygame.mouse.get_pos()
        self.type_blocks = []
        for index, (key, title, _served) in enumerate(TYPES):
            block = pygame.Rect(rect.x + part * index + 4, rect.y + 4, part - 8, rect.h - 8)
            self.type_blocks.append((block, key))
            if key == self.type_filter or block.collidepoint(mouse):
                pygame.draw.rect(screen, CARD_SELECTED if key == self.type_filter else CARD_HOVER, block,
                                 border_radius=8)
            cell = pygame.Rect(rect.x + part * index + 14, rect.y + 10, part - 28, rect.h - 20)
            done, needed = self.totals.get(key, (0, 0))
            example = self.examples.get(key)
            picture = self.thumb(example, EXAMPLE_THUMB) if example else None
            text_x = cell.x
            if picture is not None:
                tile = pygame.Rect(cell.x, cell.y, EXAMPLE_THUMB, EXAMPLE_THUMB)
                pygame.draw.rect(screen, THUMB_BG, tile, border_radius=4)
                screen.blit(picture, picture.get_rect(center=tile.center))
                text_x = tile.right + 10
            width = cell.right - text_x
            share = done / needed if needed else 1
            heading = fonts.font.render(title, True, TEXT)
            screen.blit(heading, (text_x, cell.y))
            count = fonts.font.render(f'{done} / {needed}', True, progress_color(share))
            screen.blit(count, count.get_rect(topright=(cell.right, cell.y)))
            bar = pygame.Rect(text_x, cell.y + 30, width, 6)
            pygame.draw.rect(screen, BAR_BG, bar, border_radius=3)
            if round(bar.w * share):
                pygame.draw.rect(screen, progress_color(share), (bar.x, bar.y, round(bar.w * share), bar.h),
                                 border_radius=3)
            note, color = ((f'example: {example.name}', TEXT_DIM) if example else
                           ('no example yet', ERROR_COLOR))
            screen.blit(fonts.small.render(fit_text(fonts.small, note, width), True, color), (text_x, bar.bottom + 6))
            if index:
                pygame.draw.line(screen, BAR_BG, (rect.x + part * index, rect.y + 10),
                                 (rect.x + part * index, rect.bottom - 10), 2)

    def table_lines(self):
        """[(kind, item, height)] of the list: ('head', type key) over each type's ('dish', Dish)."""
        lines = []
        shown = self.shown()
        for key, _title, _served in TYPES:
            dishes = [d for d in shown if d.type == key]
            if dishes:
                lines.append(('head', key, HEAD_H))
                lines += [('dish', dish, ROW_H) for dish in dishes]
        return lines

    def draw_table(self, screen, rect, mouse):
        fonts = self.app.fonts
        small = fonts.small
        shown = self.shown()
        draw_panel(screen, fonts, rect, f'{len(shown)} dishes' + (' without a picture' if self.only_missing else ''))
        body = pygame.Rect(rect.x, rect.y + 8, rect.w, rect.h - 12)
        lines = self.table_lines()
        self.scroll = max(0, min(self.scroll, sum(h for _, _, h in lines) - body.h))
        self.rows = []
        clip = screen.get_clip()
        screen.set_clip(body)
        y = body.y - self.scroll
        for kind, item, height in lines:
            line = pygame.Rect(rect.x + 4, y, rect.w - 8, height - 4)
            y += height
            if line.bottom < body.y or line.y > body.bottom:
                continue
            if kind == 'head':
                done, needed = self.totals[item]
                text = fonts.font.render(f'{TYPE_TITLES[item]}', True, TEXT)
                screen.blit(text, (line.x + 8, line.y + 6))
                count = small.render(f'{done} of {needed} with a picture', True, TEXT_DIM)
                screen.blit(count, count.get_rect(bottomright=(line.right - 8, line.bottom - 6)))
                pygame.draw.line(screen, BAR_BG, (line.x, line.bottom), (line.right, line.bottom), 2)
                continue
            dish = item
            self.rows.append((line, dish))
            color = (CARD_SELECTED if dish.name == self.chosen else
                     CARD_HOVER if line.collidepoint(mouse) and body.collidepoint(mouse) else None)
            if color:
                pygame.draw.rect(screen, color, line, border_radius=6)
            tile = pygame.Rect(line.x + 6, 0, THUMB, THUMB)
            tile.centery = line.centery
            thumb = self.thumb(dish, THUMB - 4)
            if thumb is not None:
                pygame.draw.rect(screen, THUMB_BG, tile, border_radius=4)
                screen.blit(thumb, thumb.get_rect(center=tile.center))
            else:
                pygame.draw.rect(screen, ERROR_COLOR, tile, 1, border_radius=4)
                label = small.render('missing', True, ERROR_COLOR)
                screen.blit(label, label.get_rect(center=tile.center))
            x = tile.right + 12
            price = small.render(f'{dish.price:.2f}', True, TEXT_DIM)
            screen.blit(price, price.get_rect(topright=(line.right - 8, line.y + 8)))
            name = small.render(fit_text(small, dish.name, line.right - x - price.get_width() - 20), True, TEXT)
            screen.blit(name, (x, line.y + 8))
            sub = f'{CLASS_TITLES.get(dish.tavern_class, dish.tavern_class)} tavern, {dish.course}' + \
                  (', meat' if dish.meat else '')
            screen.blit(small.render(fit_text(small, sub, line.right - x - 8), True, TEXT_DIM), (x, line.y + 28))
        screen.set_clip(clip)

    def draw_detail(self, screen, rect, mouse):
        """The chosen dish: its picture large, its facts, and the example of its type."""
        fonts = self.app.fonts
        small = fonts.small
        dish = self.chosen_dish()
        draw_panel(screen, fonts, rect, dish.name if dish else '')
        self.gimp_button.enabled = False
        if dish is None:
            return
        clip = screen.get_clip()
        screen.set_clip(rect)
        inner = rect.inflate(-28, -24)
        title = fonts.title.render(fit_text(fonts.title, dish.name, inner.w), True, TEXT)
        screen.blit(title, inner.topleft)
        y = inner.y + title.get_height()
        served = dict((key, served) for key, _, served in TYPES)[dish.type]
        facts = (f'{CLASS_TITLES.get(dish.tavern_class, dish.tavern_class)} tavern, {dish.course}, served {served}, '
                 f'{"with" if dish.meat else "no"} meat, {dish.price:.2f} coins')
        for line in wrap_text(small, facts, inner.w, 2) + wrap_text(small, dish.description, inner.w, 3):
            screen.blit(small.render(line, True, TEXT_DIM), (inner.x, y))
            y += 18
        y += 10

        example = self.examples.get(dish.type)
        example_h = 0 if example is None or example is dish else min(170, inner.h // 4)
        note_h = 60
        box = pygame.Rect(inner.x, y, inner.w, max(60, inner.bottom - y - example_h - note_h))
        image = self.images.get(dish.name)
        relative = dish.picture.relative_to(PICTURES_DIR).as_posix()
        if image is not None:
            picture = smooth_fit(image, box.size, max_factor=1)
            frame = picture.get_rect(midtop=box.midtop)
            screen.blit(picture, frame)
            line = small.render(f'{relative}, {image.get_width()} x {image.get_height()}', True, TEXT_DIM)
            screen.blit(line, (inner.x, frame.bottom + 8))
            self.gimp_button.rect.midleft = (inner.x + line.get_width() + 14, frame.bottom + 8 + line.get_height() // 2)
            self.gimp_button.enabled = True
            self.gimp_button.draw(screen, small, mouse)
            y = frame.bottom + 8 + note_h // 2
        else:
            empty = pygame.Rect(box.x, box.y, box.w, min(box.h, 200))
            pygame.draw.rect(screen, BAR_BG, empty, border_radius=6)
            label = fonts.font.render('No picture yet', True, ERROR_COLOR)
            screen.blit(label, label.get_rect(center=empty.center))
            screen.blit(small.render(f'{relative} missing', True, ERROR_COLOR), (inner.x, empty.bottom + 8))
            y = empty.bottom + 8 + note_h // 2

        if example is dish:
            text = f'This is the example the other {TYPE_TITLES[dish.type].lower()} are drawn after.'
            screen.blit(small.render(fit_text(small, text, inner.w), True, DONE_COLOR), (inner.x, y))
        elif example is None:
            text = (f'No example for the {TYPE_TITLES[dish.type].lower()} yet: their pictures are drawn after one '
                    f'of their own, which is still to be handed in.')
            for line in wrap_text(small, text, inner.w, 2):
                screen.blit(small.render(line, True, ERROR_COLOR), (inner.x, y))
                y += 18
        else:
            screen.blit(small.render(f'Drawn after the example of the {TYPE_TITLES[dish.type].lower()}: {example.name}',
                                     True, TEXT), (inner.x, y))
            y += 24
            picture = smooth_fit(self.images[example.name], (inner.w, max(20, inner.bottom - y)))
            screen.blit(picture, (inner.x, y))
        screen.set_clip(clip)

    # --- input ------------------------------------------------------------

    def click(self, pos):
        for button in self.switch_buttons:
            if button.hit(pos):
                self.app.switch_to(button.screen)
                return
        if self.missing_button.hit(pos):
            self.toggle_missing()
        elif any(block.collidepoint(pos) for block, _ in self.type_blocks):
            key = next(key for block, key in self.type_blocks if block.collidepoint(pos))
            self.type_filter = None if self.type_filter == key else key
            self.keep_chosen_shown()
        elif self.gimp_button.hit(pos):
            dish = self.chosen_dish()
            if dish is not None:
                self.app.edit_in_gimp(FOOD_PICTURES, dish.picture)
        elif self.table.collidepoint(pos):
            for line, dish in self.rows:
                if line.collidepoint(pos):
                    self.chosen = dish.name
                    return

    def keep_chosen_shown(self):
        shown = self.shown()
        self.scroll = 0
        if shown and self.chosen not in [d.name for d in shown]:
            self.chosen = shown[0].name

    def toggle_missing(self):
        self.only_missing = not self.only_missing
        self.keep_chosen_shown()

    def next_type(self):
        keys = [None] + [key for key, _, _ in TYPES]
        self.type_filter = keys[(keys.index(self.type_filter) + 1) % len(keys)]
        self.keep_chosen_shown()

    def open_pictures(self):
        if sys.platform == 'win32':
            os.startfile(PICTURES_DIR)
        else:
            self.app.set_status(str(PICTURES_DIR))

    def step(self, by):
        names = [d.name for d in self.shown()]
        if not names:
            return
        index = names.index(self.chosen) + by if self.chosen in names else 0
        self.chosen = names[max(0, min(len(names) - 1, index))]
        # Keep the chosen row in view
        top = 0
        for kind, item, height in self.table_lines():
            if kind == 'dish' and item.name == self.chosen:
                break
            top += height
        visible = self.table.h - 12
        if top < self.scroll:
            self.scroll = top
        elif top + ROW_H > self.scroll + visible:
            self.scroll = top + ROW_H - visible

    def key(self, event):
        if event.key == pygame.K_TAB:
            self.app.switch_to_next()
        elif event.key == pygame.K_m:
            self.toggle_missing()
        elif event.key == pygame.K_t:
            self.next_type()
        elif event.key == pygame.K_o:
            self.open_pictures()
        elif event.key == pygame.K_DOWN:
            self.step(1)
        elif event.key == pygame.K_UP:
            self.step(-1)

    def scroll_by(self, steps):
        self.scroll = max(0, self.scroll - steps * ROW_H)

    def back(self):
        self.app.go_home()
        return True
