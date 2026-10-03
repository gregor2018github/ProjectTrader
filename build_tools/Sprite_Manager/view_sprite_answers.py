"""Screen 3 of the plants and buildings: the model's answers for a new sprite, and taking one into the game.

Left the split image as it was last sent and the ways to more answers, in
the middle the answers, right the chosen one cut out and scaled beside the
example, as it would be saved. Accepting saves it as a single sprite, puts
it into its sprite collection for Tiled and catalogs it (sprite_library.add_sprite()).
More than one answer of a job can be accepted, as variants.
"""

from pathlib import Path

import pygame

import gemini_client
import pose_review
import win_clipboard
from answers import AnswerError, ask_open_file, clipboard_answer, measure, store_web_answer
from images import fitted, make_thumb
from sprite_extraction import SpriteDetail
from sprite_job import colour_name
from sprite_library import MAP_SPRITES, Catalog, add_sprite, next_free_file
from theme import (
    CARD_BG, DONE_COLOR, ERROR_COLOR, PANEL_GAP, RESULT_CARD_SIZE, RESULT_THUMB_SIZE, STATUS_COLORS,
    TEXT, TEXT_DIM,
)
from view import View
from view_review import CAPTION_ON_CHECKER
from widgets import Button, Card, CardGrid, Checker, draw_panel, fit_text

SHEET_SHARE = 0.26
RESULT_SHARE = 0.36
BUTTON_H = 40
BUTTON_GAP = 10
LINE_H = 19


class AnswersView(View):
    def __init__(self, app, entry=None):
        super().__init__(app)
        self.job = app.npc
        self.store = app.store
        self.grid = CardGrid()
        self.entry = None
        self.detail = None
        self.checker = Checker()
        self.sheet = None
        self.paste_button = Button('Paste answer', h=BUTTON_H)
        self.open_button = Button('Open image', h=BUTTON_H)
        self.send_button = Button('Send again', h=BUTTON_H)
        self.design_button = Button('Change the design', h=BUTTON_H)
        self.gimp_button = Button('Edit in GIMP', h=BUTTON_H)
        self.button_rows = ((self.paste_button, self.open_button), (self.send_button,),
                            (self.design_button, self.gimp_button))
        self.reject_button = Button('Not good enough', w=190)
        self.accept_button = Button('Accept', w=150)
        self.actions = ((self.paste_button, self.paste_answer),
                        (self.open_button, self.open_answer),
                        (self.send_button, self.send),
                        (self.design_button, self.back),
                        (self.gimp_button, self.edit_in_gimp),
                        (self.reject_button, self.reject),
                        (self.accept_button, self.accept))
        self.wanted = entry   # the answer to show first

    # --- state ------------------------------------------------------------

    def refresh(self):
        try:
            self.sheet = self.job.write_sheet() if self.job.has_sketch() else None
        except (pygame.error, OSError) as exc:
            self.sheet = None
            self.app.set_status(f'Cannot write the split image: {exc}', error=True)
        self.build_answer_cards()
        if self.wanted is not None:
            self.choose(self.wanted)
            self.wanted = None
        elif self.entry not in self.store.entries:
            pending = self.store.pending()
            entries = pending or self.store.sorted_entries()
            self.choose(entries[-1] if entries else None)

    def build_answer_cards(self):
        cards = []
        for entry in self.store.sorted_entries():
            path = self.job.out_dir / entry.image
            try:
                thumb = make_thumb(path, RESULT_THUMB_SIZE, trimmed=False)
            except (pygame.error, OSError):
                continue
            measure(path, entry, self.store)
            saved = self.job.accepted.get(entry.image)
            note = f'{entry.status}: {Path(saved).name}' if saved else entry.status
            cards.append(Card(entry, entry.model, thumb, note,
                              note_color=STATUS_COLORS.get(entry.status, TEXT_DIM),
                              extra=[(entry.short_warning(), DONE_COLOR)], size=RESULT_CARD_SIZE))
        self.grid.cards = cards

    def choose(self, entry):
        self.entry, self.detail = entry, None
        if entry is None:
            return
        try:
            self.detail = SpriteDetail(self.job, entry)
        except Exception as exc:  # a deleted or unreadable file
            self.app.set_status(f'Cannot open {entry.image}: {exc}', error=True)
            return
        if self.detail.error:
            self.app.set_status(self.detail.error, error=True)

    # --- actions ----------------------------------------------------------

    def paste_answer(self):
        try:
            self.import_answer(*clipboard_answer())
        except AnswerError as exc:
            self.app.set_status(str(exc), error=True)

    def open_answer(self):
        path = ask_open_file()
        if path:
            self.drop_file(Path(path))

    def drop_file(self, path):
        try:
            self.import_answer(path)
        except AnswerError as exc:
            self.app.set_status(str(exc), error=True)

    def import_answer(self, source, kind=''):
        if not self.sheet:
            return
        entry = store_web_answer(self.job, self.store, self.sheet, source, kind)
        self.build_answer_cards()
        self.choose(entry)
        if self.detail and not self.detail.error:
            self.app.set_status('Answer in - Accept (Enter) if it is right')

    def send(self):
        if self.sheet:
            self.app.send([self.sheet])

    def accept(self):
        """Save the chosen answer as a new sprite, single and in its collection."""
        if not (self.detail and self.detail.result):
            return
        saved = self.job.accepted.get(self.entry.image)
        if saved:
            self.app.set_status(f'This answer is in the game already, as {Path(saved).name}', error=True)
            return
        domain = self.job.domain
        kind = domain.kinds_by_key[self.job.kind]
        try:
            added = add_sprite(domain, self.detail.result.output, kind, self.job.subcategory,
                               self.app.catalog(domain))
        except (pygame.error, OSError, ValueError) as exc:
            self.app.set_status(f'Could not save: {exc}', error=True)
            return
        self.job.accepted[self.entry.image] = Catalog.file_key(added.path)
        self.job.save()
        self.store.set_status(self.entry, pose_review.ACCEPTED)
        self.app.reload_library(domain)
        self.build_answer_cards()
        self.app.set_status(added.summary())
        self.app.toast.show(f'Added {added.path.name}')

    def saved_path(self):
        """The sprite the chosen answer became, if it was accepted."""
        saved = self.entry and self.job.accepted.get(self.entry.image)
        return MAP_SPRITES / saved if saved else None

    def edit_in_gimp(self):
        """Open the sprite the chosen answer became in GIMP."""
        path = self.saved_path()
        if path and path.is_file():
            self.app.edit_in_gimp(self.job.domain, path)

    def reject(self):
        if not self.entry:
            return
        back = self.entry.status != pose_review.PENDING
        self.store.set_status(self.entry, pose_review.PENDING if back else pose_review.REJECTED)
        self.build_answer_cards()
        self.app.set_status(f'{self.entry.image} is now {self.entry.status}')

    # --- view -------------------------------------------------------------

    def header(self):
        return (f'3. Answers for the new {self.job.label}',
                'Ctrl+V or drop a file = answer, Enter = accept into the game, Del = not good enough, '
                'click white gaps in the result to see through them.')

    def footer(self):
        app = self.app
        return ((app.back_button, app.folder_button),
                (app.settings_button, self.reject_button, self.accept_button))

    def update_footer(self):
        self.accept_button.enabled = bool(self.detail and self.detail.result) and \
            self.entry.image not in self.job.accepted
        self.reject_button.enabled = bool(self.entry)
        self.reject_button.label = ('Back to pending' if self.entry and self.entry.status != pose_review.PENDING
                                    else 'Not good enough')

    def areas(self):
        body = self.app.body()
        sheet_w, result_w = int(body.w * SHEET_SHARE), int(body.w * RESULT_SHARE)
        sheet = pygame.Rect(body.x, body.y, sheet_w, body.h)
        result = pygame.Rect(body.right - result_w, body.y, result_w, body.h)
        answers = pygame.Rect(sheet.right + PANEL_GAP, body.y, result.x - sheet.right - 2 * PANEL_GAP, body.h)
        return sheet, answers, result

    def draw(self, screen, mouse):
        sheet_rect, answers_rect, result_rect = self.areas()
        self.draw_sheet_panel(screen, sheet_rect, mouse)

        fonts = self.app.fonts
        screen.blit(fonts.small.render('Answers', True, TEXT_DIM), (answers_rect.x + 4, answers_rect.y - 20))
        if not self.grid.cards:
            text = fonts.small.render('None yet', True, TEXT_DIM)
            screen.blit(text, text.get_rect(midtop=(answers_rect.centerx, answers_rect.y + 20)))
        self.grid.layout(answers_rect)
        self.grid.draw(screen, fonts, mouse, selected_key=self.entry)

        draw_panel(screen, fonts, result_rect,
                   f'The example and the new {self.job.domain.noun}, same scale  (click white gaps)')
        self.draw_result(screen, result_rect.inflate(-20, -20))

    def draw_sheet_panel(self, screen, rect, mouse):
        fonts = self.app.fonts
        draw_panel(screen, fonts, rect, 'Split image as sent')
        inner = rect.inflate(-20, -20)
        half = (inner.w - BUTTON_GAP) // 2
        y = inner.bottom - len(self.button_rows) * (BUTTON_H + BUTTON_GAP) + BUTTON_GAP
        for row in self.button_rows:
            if len(row) == 1:
                row[0].rect = pygame.Rect(inner.x, y, inner.w, BUTTON_H)
            else:
                row[0].rect = pygame.Rect(inner.x, y, half, BUTTON_H)
                row[1].rect = pygame.Rect(inner.right - half, y, half, BUTTON_H)
            y += BUTTON_H + BUTTON_GAP

        job = self.job
        lines = [f'Type: {job.domain.kinds_by_key[job.kind].title}',
                 f'Subcategory: {job.subcategory or "-"}',
                 f'Colour: {colour_name(job.colour)}',
                 f'From: {job.example_label}']
        lines += [f'Saved: {Path(p).name}' for p in job.accepted.values()]
        text_bottom = self.paste_button.rect.y - BUTTON_GAP
        text_top = text_bottom - len(lines) * LINE_H
        image_area = pygame.Rect(inner.x, inner.y, inner.w, text_top - BUTTON_GAP - inner.y)
        if self.sheet and image_area.h > 40:
            screen.blit(fitted(self.sheet.surface, image_area.size, CARD_BG), image_area)
        y = text_top
        for line in lines:
            screen.blit(fonts.small.render(fit_text(fonts.small, line, inner.w), True, TEXT), (inner.x, y))
            y += LINE_H

        self.paste_button.enabled = bool(self.sheet) and win_clipboard.AVAILABLE
        self.open_button.enabled = bool(self.sheet)
        self.send_button.enabled = bool(self.sheet) and not self.app.busy() and not gemini_client.SDK_ERROR
        self.send_button.label = 'Sending ...' if self.app.busy() else 'Send to Gemini again'
        self.gimp_button.enabled = bool(self.saved_path())
        for row in self.button_rows:
            for button in row:
                button.draw(screen, fonts.font, mouse)

    def draw_result(self, screen, area):
        """The example and the new sprite side by side on one ground line, at one scale."""
        fonts = self.app.fonts
        self.checker.draw(screen, area)
        detail = self.detail
        if not detail:
            return
        detail.preview = None
        if not detail.result:
            text = fonts.small.render(fit_text(fonts.small, detail.error, area.w - 20), True, ERROR_COLOR)
            screen.blit(text, text.get_rect(center=area.center))
            return
        example, output = self.job.example, detail.result.output
        gap = max(8, example.get_width() // 4)
        total = (example.get_width() + gap + output.get_width(), max(example.get_height(), output.get_height()))
        factor = min((area.w - 20) / total[0], (area.h - 50) / total[1], 6)
        # Whole pixels when blown up, so the pixel art stays crisp
        if factor >= 1:
            factor = int(factor)
        baseline = area.bottom - 40
        x = area.centerx - int(total[0] * factor) // 2
        shown = []
        for surface in (example, output):
            size = (max(1, int(surface.get_width() * factor)), max(1, int(surface.get_height() * factor)))
            scale = pygame.transform.scale if factor >= 1 else pygame.transform.smoothscale
            image = scale(surface, size)
            pos = (x, baseline - size[1])
            screen.blit(image, pos)
            shown.append(pygame.Rect(pos, size))
            x += size[0] + int(gap * factor)
        pygame.draw.rect(screen, TEXT_DIM, shown[1], 1)
        detail.preview = (shown[1], factor)

        target = next_free_file(self.job.domain.kinds_by_key[self.job.kind]).name
        saved = self.job.accepted.get(self.entry.image)
        name = f'saved as {Path(saved).name}' if saved else f'-> {target}'
        caption = fonts.small.render(
            f'{output.get_width()} x {output.get_height()} px, scale {detail.result.scale:.2f} {name}',
            True, CAPTION_ON_CHECKER)
        screen.blit(caption, caption.get_rect(midbottom=(area.centerx, area.bottom - 10)))

    # --- input ------------------------------------------------------------

    def click(self, pos):
        for button, action in self.actions:
            if button.hit(pos):
                action()
                return
        card = self.grid.card_at(pos)
        if card:
            self.choose(card.key)
        elif self.detail:
            self.detail.toggle_hole(pos)

    def key(self, event):
        ctrl = event.mod & pygame.KMOD_CTRL
        if event.key == pygame.K_v and ctrl:
            self.paste_answer()
        elif event.key == pygame.K_o and ctrl:
            self.open_answer()
        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.accept()
        elif event.key == pygame.K_DELETE:
            self.reject()
        elif event.key == pygame.K_TAB:
            self.back()
        elif event.key == pygame.K_g:
            self.edit_in_gimp()

    def scroll_by(self, steps):
        self.grid.scroll_by(steps)

    def back(self):
        self.app.open_design()
        return True
