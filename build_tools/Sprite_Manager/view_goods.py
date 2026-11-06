"""Menu sprites: every good's pictures for the game's menus, and which are still missing.

On the left, one row per good of goods.json, in its order: its name and licence, and a cell per kind
of picture (goods.py): the picture if there is one, PLACEHOLDER (the 30px stand-ins of the goods added
in P1.3), MISSING, or a dash where the good needs none (only a licence's head has a signed licence).
Over it, how far each kind is. On the right, the chosen good: every picture large, with its file,
size and where the game shows it, and what is left to make.

Click a row (or Up / Down) to choose a good, M shows only the goods with something missing, O opens
assets/pictures. "GIMP" beside a picture opens it in GIMP (read again once saved back), and "Remake from painting"
(P) makes the cut-out, 30px icon and licence picture again from the painting, e.g. after fixing it there. "Make its picture" (Enter) sketches the chosen good beside three other goods for the model
(view_good_design.py, goods_sheets.py); accepting an answer writes its painting, cut-out, 30px icon
and its licence picture (the good toned sepia).
"""

import os
import sys

import pygame

from goods import (KINDS, MISSING, NOT_NEEDED, OK, PICTURES_DIR, PLACEHOLDER, find_goods, tally)
from goods_sheets import GOODS_PICTURES, GoodSubject, remake_from_painting
from images import pixel_fit, smooth_fit
from pose_review import ReviewStore
from theme import BAR_BG, CARD_BG, CARD_HOVER, CARD_SELECTED, DONE_COLOR, ERROR_COLOR, PANEL_GAP, TEXT, \
    TEXT_DIM, THUMB_BG
from view import View
from widgets import Button, checkerboard, draw_panel, fit_text, progress_color, wrap_text

ROW_H = 62
CELL_W = 92
NAME_W = 150
THUMB = 52
SUMMARY_H = 72
DETAIL_MIN_W = 320
SCROLL_STEP = ROW_H
STATUS_TEXT = {MISSING: ('missing', ERROR_COLOR), PLACEHOLDER: ('placeholder', DONE_COLOR),
               NOT_NEEDED: ('-', TEXT_DIM)}


def load_picture(path):
    """The picture at `path` for showing, or None if it cannot be read."""
    try:
        image = pygame.image.load(str(path))
    except (pygame.error, OSError):
        return None
    return image.convert_alpha() if image.get_alpha() is not None or image.get_colorkey() else image.convert()


def fit(image, size):
    """Small pixel icons blown up crisply, big paintings scaled smoothly."""
    if image.get_width() <= 64 and image.get_height() <= 64:
        return pixel_fit(image, size)
    return smooth_fit(image, size)


class GoodsView(View):
    def __init__(self, app):
        super().__init__(app)
        self.switch_buttons = app.switch_buttons('menu')
        self.only_missing = False
        self.missing_button = Button('Only missing (M)', w=160)
        self.make_button = Button('Make its picture (Enter)', w=240, h=40)
        self.waiting = {}        # {good name: answers waiting for review}
        self.remake_button = Button('Remake from painting (P)', w=290, h=40)
        self.gimp_buttons = []   # [(Button, path)] beside the chosen good's pictures, as last drawn
        self.goods = []
        self.totals = {}
        self.statuses = {}       # {good name: {kind key: status}}
        self.images = {}         # {(good name, kind key): Surface}, the pictures as read
        self.thumbs = {}         # {(good name, kind key): Surface}, fitted into a cell
        self.chosen = None
        self.scroll = 0
        self.table = pygame.Rect(0, 0, 0, 0)
        self.rows = []           # [(Rect, good)] as last drawn

    def refresh(self):
        self.goods = find_goods()
        self.totals = tally(self.goods)
        self.statuses = {g.name: {k.key: g.status(k.key) for k in KINDS} for g in self.goods}
        self.images.clear()
        self.thumbs.clear()
        for good in self.goods:
            for kind in KINDS:
                if self.statuses[good.name][kind.key] in (OK, PLACEHOLDER):
                    image = load_picture(good.path(kind.key))
                    if image is not None:
                        self.images[good.name, kind.key] = image
                        self.thumbs[good.name, kind.key] = fit(image, (THUMB, THUMB))
        self.waiting = {g.name: len(ReviewStore(GoodSubject(g).out_dir).pending()) for g in self.goods}
        names = [g.name for g in self.goods]
        if self.chosen not in names:
            self.chosen = next((g.name for g in self.goods if self.open_work(g)), names[0] if names else None)

    def open_work(self, good):
        """The kinds of picture `good` still lacks (or has only a placeholder of), counted ones only."""
        return [k for k in KINDS if k.counted and self.statuses[good.name][k.key] in (MISSING, PLACEHOLDER)]

    def shown(self):
        return [g for g in self.goods if not self.only_missing or self.open_work(g)]

    def header(self):
        return ('Menu sprites',
                "Every good's pictures for the game's menus, and what is still missing. "
                'Click a good (or Up / Down); M = only the missing, O = open the folder, Tab = next area.')

    def footer(self):
        return ((self.app.home_button,) + tuple(self.switch_buttons),
                (self.missing_button,))

    def update_footer(self):
        self.missing_button.label = 'Show all (M)' if self.only_missing else 'Only missing (M)'

    # --- drawing ----------------------------------------------------------

    def draw(self, screen, mouse):
        body = self.app.body()
        table_w = NAME_W + CELL_W * len(KINDS) + 16
        if body.w - table_w - PANEL_GAP < DETAIL_MIN_W:
            table_w = max(NAME_W + CELL_W * 3, body.w - DETAIL_MIN_W - PANEL_GAP)
        self.draw_summary(screen, pygame.Rect(body.x, body.y, body.w, SUMMARY_H))
        top = body.y + SUMMARY_H + PANEL_GAP + 6
        self.table = pygame.Rect(body.x, top, table_w, body.bottom - top)
        self.draw_table(screen, self.table, mouse)
        detail = pygame.Rect(self.table.right + PANEL_GAP, top, body.right - self.table.right - PANEL_GAP,
                             body.bottom - top)
        if detail.w >= 200:
            self.draw_detail(screen, detail)

    def draw_summary(self, screen, rect):
        """How far each kind of picture is over all goods, one block each."""
        fonts = self.app.fonts
        draw_panel(screen, fonts, rect, f'{len(self.goods)} goods in goods.json')
        part = rect.w // len(KINDS)
        for index, kind in enumerate(KINDS):
            done, needed, placeholders = self.totals.get(kind.key, (0, 0, 0))
            cell = pygame.Rect(rect.x + part * index + 14, rect.y + 8, part - 28, rect.h - 16)
            share = done / needed if needed else 1
            color = progress_color(share) if kind.counted else TEXT_DIM
            title = fonts.small.render(kind.title, True, TEXT)
            screen.blit(title, cell.topleft)
            count = fonts.font.render(f'{done} / {needed}', True, color)
            screen.blit(count, count.get_rect(topright=cell.topright))
            bar = pygame.Rect(cell.x, cell.y + 28, cell.w, 6)
            pygame.draw.rect(screen, BAR_BG, bar, border_radius=3)
            if round(bar.w * share):
                pygame.draw.rect(screen, color, (bar.x, bar.y, round(bar.w * share), bar.h), border_radius=3)
            note = (f'{placeholders} placeholders' if placeholders else
                    'made by the game' if not kind.counted else
                    f'{needed - done} missing' if needed > done else 'all there')
            text = fonts.small.render(note, True, DONE_COLOR if placeholders else TEXT_DIM)
            screen.blit(text, (cell.x, bar.bottom + 2))
            if index:
                pygame.draw.line(screen, BAR_BG, (rect.x + part * index, rect.y + 10),
                                 (rect.x + part * index, rect.bottom - 10), 2)

    def draw_table(self, screen, rect, mouse):
        fonts = self.app.fonts
        small = fonts.small
        goods = self.shown()
        draw_panel(screen, fonts, rect, f'{len(goods)} goods' + (' with something missing' if self.only_missing else ''))
        head_h = 26
        for index, kind in enumerate(KINDS):
            x = rect.x + NAME_W + index * CELL_W
            text = small.render(fit_text(small, kind.title, CELL_W - 6), True, TEXT_DIM)
            screen.blit(text, text.get_rect(midtop=(x + CELL_W // 2, rect.y + 5)))
        body = pygame.Rect(rect.x, rect.y + head_h, rect.w, rect.h - head_h - 4)
        self.scroll = max(0, min(self.scroll, len(goods) * ROW_H - body.h))
        self.rows = []
        clip = screen.get_clip()
        screen.set_clip(body)
        for row, good in enumerate(goods):
            line = pygame.Rect(rect.x + 4, body.y + row * ROW_H - self.scroll, rect.w - 8, ROW_H - 4)
            if line.bottom < body.y or line.y > body.bottom:
                continue
            self.rows.append((line, good))
            color = (CARD_SELECTED if good.name == self.chosen else
                     CARD_HOVER if line.collidepoint(mouse) and body.collidepoint(mouse) else None)
            if color:
                pygame.draw.rect(screen, color, line, border_radius=6)
            name = small.render(fit_text(small, good.name, NAME_W - 14), True, TEXT)
            screen.blit(name, (line.x + 8, line.y + 10))
            waiting = self.waiting.get(good.name, 0)
            sub = (f'{waiting} to review' if waiting else
                   'own licence' if good.is_head else f'under {good.licence}')
            text = small.render(fit_text(small, sub, NAME_W - 14), True, DONE_COLOR if waiting else TEXT_DIM)
            screen.blit(text, (line.x + 8, line.y + 30))
            for index, kind in enumerate(KINDS):
                cell = pygame.Rect(rect.x + NAME_W + index * CELL_W, line.y, CELL_W, line.h)
                self.draw_cell(screen, cell, good, kind)
        screen.set_clip(clip)

    def draw_cell(self, screen, cell, good, kind):
        small = self.app.fonts.small
        status = self.statuses[good.name][kind.key]
        thumb = self.thumbs.get((good.name, kind.key))
        tile = pygame.Rect(0, 0, THUMB + 4, THUMB + 4)
        tile.center = cell.center
        if thumb is not None:
            pygame.draw.rect(screen, THUMB_BG, tile, border_radius=4)
            screen.blit(thumb, thumb.get_rect(center=tile.center))
            if status == PLACEHOLDER:
                pygame.draw.rect(screen, DONE_COLOR, tile, 2, border_radius=4)
                label = small.render('placeholder', True, BAR_BG)
                back = label.get_rect(midbottom=(tile.centerx, tile.bottom + 2)).inflate(6, -2)
                pygame.draw.rect(screen, DONE_COLOR, back, border_radius=3)
                screen.blit(label, label.get_rect(center=back.center))
            return
        text, color = STATUS_TEXT.get(status, ('unreadable', ERROR_COLOR))
        if status == MISSING and not kind.counted:
            color = TEXT_DIM
        if status != NOT_NEEDED:
            pygame.draw.rect(screen, color, tile, 1, border_radius=4)
        label = small.render(text, True, color)
        screen.blit(label, label.get_rect(center=tile.center))

    def draw_detail(self, screen, rect):
        """The chosen good: each picture large with its file, size and use, and what is left to make."""
        fonts = self.app.fonts
        small = fonts.small
        good = next((g for g in self.goods if g.name == self.chosen), None)
        draw_panel(screen, fonts, rect, good.name if good else '')
        if good is None:
            return
        clip = screen.get_clip()
        screen.set_clip(rect)
        inner = rect.inflate(-28, -24)
        title = fonts.title.render(good.name, True, TEXT)
        screen.blit(title, inner.topleft)
        if good.color:
            swatch = pygame.Rect(inner.right - 26, inner.y + 8, 26, 26)
            pygame.draw.rect(screen, good.color, swatch, border_radius=4)
            name = small.render(good.color_name, True, TEXT_DIM)
            screen.blit(name, name.get_rect(midright=(swatch.x - 8, swatch.centery)))
        y = inner.y + title.get_height()
        work = self.open_work(good)
        if work:
            todo = 'Still to make: ' + ', '.join(
                k.title.lower() + (' (now a placeholder)' if self.statuses[good.name][k.key] == PLACEHOLDER
                                   else '') for k in work)
            color = ERROR_COLOR
        else:
            todo, color = 'Every picture it needs is there.', progress_color(1)
        for line in wrap_text(small, todo, inner.w, 3):
            screen.blit(small.render(line, True, color), (inner.x, y))
            y += 18
        y += 10

        # At the foot the way to make its picture; the kinds share the height left above it, each a picture
        # and its title, file and as much of its use as fits
        self.make_button.rect.bottomleft = inner.bottomleft
        waiting = self.waiting.get(good.name, 0)
        self.make_button.label = (f'Its picture: {waiting} to review (Enter)' if waiting else
                                  'Make its picture (Enter)' if work else 'Redo its picture (Enter)')
        mouse = pygame.mouse.get_pos()
        self.make_button.draw(screen, fonts.font, mouse)
        self.remake_button.rect.bottomleft = (self.make_button.rect.right + 12, inner.bottom)
        self.remake_button.rect.w = min(290, inner.right - self.remake_button.rect.x)
        self.remake_button.enabled = self.statuses[good.name]['painting'] == OK
        self.remake_button.draw(screen, small, mouse)
        bottom = self.make_button.rect.y - 12
        self.gimp_buttons = []
        row_h = max(48, min(150, (bottom - y) // len(KINDS) - 8))
        size = max(40, min(row_h, inner.w - 220))
        for kind in KINDS:
            status = self.statuses[good.name][kind.key]
            box = pygame.Rect(inner.x, y, size, size)
            image = self.images.get((good.name, kind.key))
            if image is not None:
                screen.blit(checkerboard(box.size), box)
                picture = fit(image, box.size)
                screen.blit(picture, picture.get_rect(center=box.center))
                if status == PLACEHOLDER:
                    pygame.draw.rect(screen, DONE_COLOR, box, 2)
            else:
                pygame.draw.rect(screen, BAR_BG, box, border_radius=4)
                text, color = STATUS_TEXT.get(status, ('unreadable', ERROR_COLOR))
                label = small.render(text, True, color if kind.counted or status != MISSING else TEXT_DIM)
                screen.blit(label, label.get_rect(center=box.center))
            x = box.right + 14
            width = inner.right - x
            heading = fonts.font.render(kind.title, True, TEXT)
            screen.blit(heading, (x, y))
            path = good.path(kind.key)
            if image is not None and kind.counted:
                gimp = Button('GIMP', h=22, w=56)
                gimp.rect.midleft = (x + heading.get_width() + 12, y + heading.get_height() // 2)
                gimp.draw(screen, small, mouse)
                self.gimp_buttons.append((gimp, path))
            if status == NOT_NEEDED:
                facts = f'none: traded under the {good.licence} licence'
            elif image is not None:
                facts = f'{path.relative_to(PICTURES_DIR).as_posix()}, {image.get_width()} x {image.get_height()}'
                if status == PLACEHOLDER:
                    facts += ', a placeholder'
            else:
                facts = f'{path.relative_to(PICTURES_DIR).as_posix()} missing, should be {kind.size}'
            ty = y + 24
            screen.blit(small.render(fit_text(small, facts, width), True,
                                     ERROR_COLOR if status == MISSING and kind.counted else TEXT_DIM), (x, ty))
            ty += 18
            lines = (row_h - 42) // 18
            if lines > 0:
                for line in wrap_text(small, kind.use, width, lines):
                    screen.blit(small.render(line, True, TEXT_DIM), (x, ty))
                    ty += 18
            y += row_h + 8
        screen.set_clip(clip)

    # --- input ------------------------------------------------------------

    def click(self, pos):
        for button in self.switch_buttons:
            if button.hit(pos):
                self.app.switch_to(button.screen)
                return
        if self.missing_button.hit(pos):
            self.toggle_missing()
        elif self.make_button.hit(pos):
            self.make()
        elif self.remake_button.hit(pos):
            self.remake()
        elif any(button.hit(pos) for button, _ in self.gimp_buttons):
            path = next(path for button, path in self.gimp_buttons if button.hit(pos))
            self.app.edit_in_gimp(GOODS_PICTURES, path)
        elif self.table.collidepoint(pos):
            for line, good in self.rows:
                if line.collidepoint(pos):
                    self.chosen = good.name
                    return

    def make(self):
        """Sketch the chosen good's picture for the model."""
        good = next((g for g in self.goods if g.name == self.chosen), None)
        if good is not None:
            self.app.open_good(self, good)

    def remake(self):
        """The chosen good's cut-out, 30px icon and licence picture made again from its painting, e.g. after
        fixing it in GIMP."""
        good = next((g for g in self.goods if g.name == self.chosen), None)
        if good is None or self.statuses[good.name]['painting'] != OK:
            return
        try:
            written = remake_from_painting(GoodSubject(good))
        except (pygame.error, OSError, ValueError) as exc:
            self.app.set_status(f'Cannot cut {good.name} out of its painting: {exc}', error=True)
            return
        self.refresh()
        self.app.set_status(f'Made {", ".join(written)} from the painting; the old ones are in replaced/')
        self.app.toast.show(f'{good.name}: made again from the painting')

    def toggle_missing(self):
        self.only_missing = not self.only_missing
        self.scroll = 0
        shown = self.shown()
        if shown and self.chosen not in [g.name for g in shown]:
            self.chosen = shown[0].name

    def open_pictures(self):
        if sys.platform == 'win32':
            os.startfile(PICTURES_DIR)
        else:
            self.app.set_status(str(PICTURES_DIR))

    def step(self, by):
        shown = self.shown()
        names = [g.name for g in shown]
        if not names:
            return
        index = names.index(self.chosen) + by if self.chosen in names else 0
        index = max(0, min(len(names) - 1, index))
        self.chosen = names[index]
        visible = self.table.h - 30
        if index * ROW_H < self.scroll:
            self.scroll = index * ROW_H
        elif (index + 1) * ROW_H > self.scroll + visible:
            self.scroll = (index + 1) * ROW_H - visible

    def key(self, event):
        if event.key == pygame.K_TAB:
            self.app.switch_to_next()
        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.make()
        elif event.key == pygame.K_p:
            self.remake()
        elif event.key == pygame.K_m:
            self.toggle_missing()
        elif event.key == pygame.K_o:
            self.open_pictures()
        elif event.key == pygame.K_DOWN:
            self.step(1)
        elif event.key == pygame.K_UP:
            self.step(-1)

    def scroll_by(self, steps):
        self.scroll = max(0, self.scroll - steps * SCROLL_STEP)

    def back(self):
        self.app.go_home()
        return True
