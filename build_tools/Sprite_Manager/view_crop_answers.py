"""The model's answers for one stage sprite of a crop, and taking one into the game.

Left the sheet as it was last sent and the ways to more answers, in the
middle the answers for this stage and variant, right the chosen one cut out
and scaled beside the sprite it was drawn from (and the one it would
replace), standing on one ground line, as it would be saved. Accepting saves
it as <crop>_<stage>_<n>.png in the crop's folder, over one there may be,
and goes back to the crop.
"""

from pathlib import Path

import pygame

import gemini_client
import pose_review
import win_clipboard
from answers import AnswerError, ask_open_file, clipboard_answer, measure, store_web_answer
from crop_sheets import CropDetail
from images import fitted, is_blank, make_thumb, trim
from theme import (
    CARD_BG, DONE_COLOR, ERROR_COLOR, PANEL_GAP, RESULT_CARD_SIZE, RESULT_THUMB_SIZE, STATUS_COLORS, TEXT_DIM,
)
from view import View
from view_review import CAPTION_ON_CHECKER
from widgets import Button, Card, CardGrid, Checker, draw_panel, fit_text

SHEET_SHARE = 0.26
RESULT_SHARE = 0.38
BUTTON_H = 40
BUTTON_GAP = 10
LABEL_H = 24


class CropAnswersView(View):
    def __init__(self, app, crop_view, sheet, entry=None):
        """
        Args:
            crop_view: The view_crop.CropView to go back to.
            sheet: The crop_sheets.CropSheet the answers are for.
            entry: The answer to show first.
        """
        super().__init__(app)
        self.crop_view = crop_view
        self.crop = app.npc
        self.store = app.store
        self.sheet = sheet
        self.grid = CardGrid()
        self.entry = None
        self.detail = None
        self.checker = Checker()
        self.paste_button = Button('Paste answer', h=BUTTON_H)
        self.open_button = Button('Open image', h=BUTTON_H)
        self.send_button = Button('Send to Gemini again', h=BUTTON_H)
        self.web_button = Button('Send in browser again', h=BUTTON_H)
        self.button_rows = ((self.paste_button, self.open_button), (self.send_button,), (self.web_button,))
        self.reject_button = Button('Not good enough', w=190)
        self.accept_button = Button('Accept', w=150)
        self.actions = ((self.paste_button, self.paste_answer),
                        (self.open_button, self.open_answer),
                        (self.send_button, self.send),
                        (self.web_button, self.send_web),
                        (self.reject_button, self.reject),
                        (self.accept_button, self.accept))
        self.wanted = entry

    @property
    def target(self):
        return self.crop.sprite_path(self.sheet.stage.key, self.sheet.variant)

    # --- state ------------------------------------------------------------

    def refresh(self):
        self.build_answer_cards()
        if self.wanted is not None:
            self.choose(self.wanted)
            self.wanted = None
        elif self.entry not in self.store.entries:
            entries = self.store.pending(self.sheet.pose) or self.store.for_pose(self.sheet.pose)
            self.choose(entries[-1] if entries else None)

    def build_answer_cards(self):
        cards = []
        order = {pose_review.PENDING: 0, pose_review.REJECTED: 1, pose_review.ACCEPTED: 2}
        for entry in sorted(self.store.for_pose(self.sheet.pose), key=lambda e: (order.get(e.status, 3), e.created)):
            path = self.crop.out_dir / entry.image
            try:
                thumb = make_thumb(path, RESULT_THUMB_SIZE, trimmed=False)
            except (pygame.error, OSError):
                continue
            measure(path, entry, self.store)
            cards.append(Card(entry, entry.model, thumb, entry.status,
                              note_color=STATUS_COLORS.get(entry.status, TEXT_DIM),
                              extra=[(entry.short_warning(), DONE_COLOR)], size=RESULT_CARD_SIZE))
        self.grid.cards = cards

    def choose(self, entry):
        self.entry, self.detail = entry, None
        if entry is None:
            return
        try:
            self.detail = CropDetail(self.crop, entry)
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
        entry = store_web_answer(self.crop, self.store, self.sheet, source, kind)
        self.build_answer_cards()
        self.choose(entry)
        if self.detail and not self.detail.error:
            self.app.set_status('Answer in - Accept (Enter) if it is right')

    def send(self):
        self.app.send([self.sheet])

    def send_web(self):
        crop, store, sheet = self.crop, self.store, self.sheet
        self.app.send_web(sheet, f'{crop.title} {sheet.pose}', lambda path: self.take_downloaded(crop, store, path))

    def take_downloaded(self, crop, store, path):
        entry = store_web_answer(crop, store, self.sheet, path)
        if self.app.view is self:
            self.build_answer_cards()
            self.choose(entry)

    def accept(self):
        """Save the chosen answer as the stage sprite, over the one there may be, and go back to the crop."""
        if not (self.detail and self.detail.result):
            return
        path = self.target
        replaced = path.is_file()
        try:
            pygame.image.save(trim(self.detail.result.output), str(path))
        except (pygame.error, OSError) as exc:
            self.app.set_status(f'Could not save: {exc}', error=True)
            return
        for entry in self.store.for_pose(self.sheet.pose):
            if entry.status == pose_review.ACCEPTED and entry is not self.entry:
                entry.status = pose_review.REJECTED   # replaced: no longer the one in the game
        self.store.set_status(self.entry, pose_review.ACCEPTED)
        self.back()
        self.app.set_status(f'{"Replaced" if replaced else "Saved"} {path.name}')
        self.app.toast.show(f'{self.sheet.stage.title} {self.sheet.variant} saved')

    def reject(self):
        if not self.entry:
            return
        back = self.entry.status != pose_review.PENDING
        self.store.set_status(self.entry, pose_review.PENDING if back else pose_review.REJECTED)
        self.build_answer_cards()
        self.app.set_status(f'{self.entry.image} is now {self.entry.status}')

    # --- view -------------------------------------------------------------

    def header(self):
        return (f'Answers for {self.crop.title}: {self.sheet.stage.title}, variant {self.sheet.variant}',
                'Ctrl+V or drop a file = answer, Enter = accept into the game, Del = not good enough, '
                'click white gaps in the result to see through them.')

    def footer(self):
        app = self.app
        return ((app.back_button, app.folder_button),
                (app.settings_button, self.reject_button, self.accept_button))

    def update_footer(self):
        self.accept_button.enabled = bool(self.detail and self.detail.result)
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
        fonts = self.app.fonts
        draw_panel(screen, fonts, sheet_rect, 'Sheet as sent')
        inner = sheet_rect.inflate(-20, -20)
        half = (inner.w - BUTTON_GAP) // 2
        y = inner.bottom - len(self.button_rows) * (BUTTON_H + BUTTON_GAP) + BUTTON_GAP
        for row in self.button_rows:
            if len(row) == 1:
                row[0].rect = pygame.Rect(inner.x, y, inner.w, BUTTON_H)
            else:
                row[0].rect = pygame.Rect(inner.x, y, half, BUTTON_H)
                row[1].rect = pygame.Rect(inner.right - half, y, half, BUTTON_H)
            y += BUTTON_H + BUTTON_GAP
        image_area = pygame.Rect(inner.x, inner.y, inner.w, self.paste_button.rect.y - BUTTON_GAP - inner.y)
        screen.blit(fitted(self.sheet.surface, image_area.size, CARD_BG), image_area)
        self.paste_button.enabled = win_clipboard.AVAILABLE
        self.send_button.enabled = not self.app.busy() and not gemini_client.SDK_ERROR
        self.send_button.label = 'Sending ...' if self.app.busy() else 'Send to Gemini again'
        self.web_button.enabled = not self.app.web_queue_busy()
        for row in self.button_rows:
            for button in row:
                button.draw(screen, fonts.font, mouse)

        screen.blit(fonts.small.render('Answers', True, TEXT_DIM), (answers_rect.x + 4, answers_rect.y - 20))
        if not self.grid.cards:
            text = fonts.small.render('None yet', True, TEXT_DIM)
            screen.blit(text, text.get_rect(midtop=(answers_rect.centerx, answers_rect.y + 20)))
        self.grid.layout(answers_rect)
        self.grid.draw(screen, fonts, mouse, selected_key=self.entry)

        draw_panel(screen, fonts, result_rect, 'Drawn from, the new one and the one now, same scale  (click white gaps)')
        self.draw_result(screen, result_rect.inflate(-20, -20))

    def draw_result(self, screen, area):
        """Reference, new sprite and the sprite it replaces side by side on one ground line, at one scale."""
        small = self.app.fonts.small
        self.checker.draw(screen, area)
        detail = self.detail
        if not detail:
            return
        detail.preview = None
        if not detail.result:
            text = small.render(fit_text(small, detail.error, area.w - 20), True, ERROR_COLOR)
            screen.blit(text, text.get_rect(center=area.center))
            return
        current = self.crop.sprite(self.sheet.stage.key, self.sheet.variant)
        shown = [('drawn from', detail.reference), ('new', detail.result.output)]
        if not is_blank(current):
            shown.append(('now in the game', trim(current)))
        gap = max(8, detail.reference.get_width() // 5)
        total_w = sum(s.get_width() for _, s in shown) + gap * (len(shown) - 1)
        total_h = max(s.get_height() for _, s in shown)
        factor = min((area.w - 20) / total_w, (area.h - 50 - LABEL_H) / total_h, 6)
        if factor >= 1:
            factor = int(factor)   # whole pixels, so the pixel art stays crisp
        baseline = area.bottom - 40
        x = area.centerx - int(total_w * factor) // 2
        scale = pygame.transform.scale if factor >= 1 else pygame.transform.smoothscale
        for label, surface in shown:
            size = (max(1, int(surface.get_width() * factor)), max(1, int(surface.get_height() * factor)))
            rect = pygame.Rect((x, baseline - size[1]), size)
            screen.blit(scale(surface, size), rect)
            text = small.render(label, True, CAPTION_ON_CHECKER)
            screen.blit(text, text.get_rect(midbottom=(rect.centerx, rect.y - 4)))
            if label == 'new':
                pygame.draw.rect(screen, TEXT_DIM, rect, 1)
                detail.preview = (rect, factor)
            x += size[0] + int(gap * factor)
        output = detail.result.output
        caption = small.render(f'{output.get_width()} x {output.get_height()} px, scale {detail.result.scale:.2f} '
                               f'-> {self.target.name}', True, CAPTION_ON_CHECKER)
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

    def scroll_by(self, steps):
        self.grid.scroll_by(steps)

    def back(self):
        self.app.show(self.crop_view)
        return True
