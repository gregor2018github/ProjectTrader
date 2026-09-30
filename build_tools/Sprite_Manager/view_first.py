"""Screen 2 for a new person: making the front standing sprite everything else starts from.

Left the split image and the description it is sent with, in the middle the
answers, right the chosen answer as it would be saved, beside the player.
"""

from pathlib import Path

import pygame

import gemini_client
import pose_review
import win_clipboard
from answers import AnswerError, clipboard_answer, store_web_answer
from create_new_NPC import ask_open_file
from create_new_pose import (
    CARD_BG, DONE_COLOR, ERROR_COLOR, PANEL_GAP, RESULT_CARD_SIZE, RESULT_THUMB_SIZE, ROOT,
    STATUS_COLORS, TEXT, TEXT_DIM, Button, Card, Detail, fit_text, make_thumb, measure,
)
from gimp import FileWatcher
from images import fitted
from new_figure import FIRST_POSE, open_in_editor, write_first_sheet
from view import View
from view_review import draw_result
from widgets import CardGrid, Checker, draw_panel

SHEET_SHARE = 0.32       # of the body, for the split image and its buttons
RESULT_SHARE = 0.34      # of the body, for the chosen answer
BUTTON_H = 40
BUTTON_GAP = 10
LINE_H = 19


class FirstSpriteView(View):
    def __init__(self, app):
        super().__init__(app)
        self.figure = app.npc
        self.store = app.store
        self.sheet = None
        self.description = None
        self.grid = CardGrid()
        self.entry = None             # the answer chosen
        self.detail = None            # ... cut out and scaled like the player
        self.checker = Checker()
        self.watcher = FileWatcher()  # description.txt, edited outside

        self.edit_button = Button('Edit description', h=BUTTON_H)
        self.copy_image_button = Button('Copy image', h=BUTTON_H)
        self.copy_prompt_button = Button('Copy prompt', h=BUTTON_H)
        self.paste_button = Button('Paste answer', h=BUTTON_H)
        self.open_button = Button('Open image', h=BUTTON_H)
        self.send_button = Button('Send to Gemini', h=BUTTON_H)
        self.button_rows = ((self.edit_button,),
                            (self.copy_image_button, self.copy_prompt_button),
                            (self.paste_button, self.open_button),
                            (self.send_button,))
        self.reject_button = Button('Not good enough', w=190)
        self.accept_button = Button('Accept', w=150)
        self.actions = ((self.edit_button, self.edit_description),
                        (self.copy_image_button, self.copy_image),
                        (self.copy_prompt_button, self.copy_prompt),
                        (self.paste_button, self.paste_answer),
                        (self.open_button, self.open_answer),
                        (self.send_button, self.send),
                        (self.reject_button, self.reject),
                        (self.accept_button, self.accept))

    # --- state ------------------------------------------------------------

    def refresh(self):
        """Split image and prompt from the files on disk, and the answers."""
        try:
            self.sheet, self.description = write_first_sheet(self.figure)
        except (pygame.error, OSError) as exc:
            self.sheet = self.description = None
            self.app.set_status(f'Cannot build the split image: {exc}', error=True)
        self.build_answer_cards()
        if self.entry not in self.store.entries:
            pending = self.store.pending()
            self.choose(pending[-1] if pending else None)
        self.watcher.reset()

    def build_answer_cards(self):
        cards = []
        for entry in self.store.sorted_entries():
            path = self.figure.out_dir / entry.image
            try:
                thumb = make_thumb(path, RESULT_THUMB_SIZE, trim=False)
            except (pygame.error, OSError):
                continue
            measure(path, entry, self.store)
            cards.append(Card(entry, entry.model, thumb, entry.status,
                              note_color=STATUS_COLORS.get(entry.status, TEXT_DIM),
                              extra=[(entry.short_warning(), DONE_COLOR)], size=RESULT_CARD_SIZE))
        self.grid.cards = cards

    def choose(self, entry):
        """Show an answer as it would be saved."""
        self.entry, self.detail = entry, None
        if entry is None:
            return
        app = self.app
        try:
            self.detail = Detail(self.figure, entry, *app.player_references(), layout='1x2')
        except Exception as exc:  # a deleted or unreadable file
            app.set_status(f'Cannot open {entry.image}: {exc}', error=True)
            return
        if self.detail.error:
            app.set_status(self.detail.error, error=True)

    def unfinished(self):
        """Why the prompt cannot go out yet, or ''."""
        if not self.description:
            return 'no description'
        missing = self.description.unfinished()
        return f'Write {missing} in description.txt first ("Edit description")' if missing else ''

    def ready_sheet(self):
        """The split image, rebuilt from the files; None (with the reason shown) if the prompt is not ready."""
        self.refresh()
        reason = self.unfinished()
        if reason:
            self.app.set_status(reason, error=True)
            return None
        return self.sheet

    # --- actions ----------------------------------------------------------

    def edit_description(self):
        try:
            open_in_editor(self.figure.ensure_description())
        except OSError as exc:
            self.app.set_status(str(exc), error=True)
            return
        self.app.set_status('Save description.txt and the prompt follows it')

    def copy_image(self):
        sheet = self.ready_sheet()
        if not sheet:
            return
        try:
            win_clipboard.copy_image(sheet.surface)
        except win_clipboard.ClipboardError as exc:
            self.app.set_status(str(exc), error=True)
            return
        self.app.set_status('Split image copied - paste it into Gemini, then the prompt')
        self.app.toast.show('Split image copied')

    def copy_prompt(self):
        sheet = self.ready_sheet()
        if not sheet:
            return
        try:
            win_clipboard.copy_text(sheet.prompt)
        except win_clipboard.ClipboardError as exc:
            self.app.set_status(str(exc), error=True)
            return
        self.app.set_status('Prompt copied')
        self.app.toast.show('Prompt copied')

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
        entry = store_web_answer(self.figure, self.store, self.sheet, source, kind)
        self.build_answer_cards()
        self.choose(entry)
        if self.detail and not self.detail.error:
            self.app.set_status('Answer in - Accept (Enter) if it is right')

    def send(self):
        sheet = self.ready_sheet()
        if sheet:
            self.app.send([sheet])

    def accept(self):
        """Save the answer as the person's front standing sprite and go on to his other sprites."""
        if not (self.detail and self.detail.result):
            return
        try:
            path = pose_review.save_sprite(self.detail.result, self.figure, FIRST_POSE)
        except (pygame.error, OSError) as exc:
            self.app.set_status(f'Could not save: {exc}', error=True)
            return
        self.store.set_status(self.entry, pose_review.ACCEPTED)
        self.app.first_sprite_saved(self.figure.folder)
        self.app.set_status(f'Saved {path.relative_to(ROOT)} - now the other directions')

    def reject(self):
        """Mark the answer as not good enough, or put it back to pending."""
        if not self.entry:
            return
        back = self.entry.status != pose_review.PENDING
        self.store.set_status(self.entry, pose_review.PENDING if back else pose_review.REJECTED)
        self.build_answer_cards()
        self.app.set_status(f'{self.entry.image} is now {self.entry.status}')

    def tick(self):
        """Follow description.txt while it is edited."""
        if self.watcher.changed([self.figure.description_path]):
            self.refresh()
            self.app.set_status('Description updated')

    # --- view -------------------------------------------------------------

    def header(self):
        return (f'2. First sprite for "{self.figure.name}"',
                'Describe them, then Ctrl+C / Ctrl+Shift+C for the web view or Send to Gemini. '
                'Ctrl+V or drop a file = answer, Enter = accept, Del = not good enough.')

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
        """(sheet, answers, result) panels."""
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

        draw_panel(screen, fonts, result_rect, 'The player and the new sprite, same scale  (click white gaps)')
        area = result_rect.inflate(-20, -20)
        if self.detail:
            draw_result(screen, fonts, self.detail, area, self.checker,
                        self.figure.sprite_path(FIRST_POSE).name)
        else:
            self.checker.draw(screen, area)

    def draw_sheet_panel(self, screen, rect, mouse):
        """Split image, the description it goes with, and the buttons."""
        fonts = self.app.fonts
        draw_panel(screen, fonts, rect, 'Split image and description')
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

        lines = self.description_lines(inner.w)
        text_h = len(lines) * LINE_H
        image_area = pygame.Rect(inner.x, inner.y, inner.w,
                                 self.edit_button.rect.y - BUTTON_GAP - text_h - BUTTON_GAP - inner.y)
        if self.sheet and image_area.h > 40:
            screen.blit(fitted(self.sheet.surface, image_area.size, CARD_BG), image_area)
        y = image_area.bottom + BUTTON_GAP
        for text, color in lines:
            screen.blit(fonts.small.render(text, True, color), (inner.x, y))
            y += LINE_H

        ready = bool(self.sheet) and not self.unfinished()
        for button in (self.copy_image_button, self.copy_prompt_button):
            button.enabled = ready and win_clipboard.AVAILABLE
        self.paste_button.enabled = bool(self.sheet) and win_clipboard.AVAILABLE
        self.open_button.enabled = bool(self.sheet)
        self.send_button.enabled = ready and not self.app.busy() and not gemini_client.SDK_ERROR
        self.send_button.label = 'Sending ...' if self.app.busy() else 'Send to Gemini'
        for row in self.button_rows:
            for button in row:
                button.draw(screen, fonts.font, mouse)

    def description_lines(self, width):
        """(text, colour) lines summing up description.txt."""
        small = self.app.fonts.small
        d = self.description
        if not d:
            return []
        lines = [(f'Who: {d.who}', TEXT)] + [(f'- {line}', TEXT) for line in d.looks]
        if d.colours:
            lines.append((f'Colours: {d.colours}', TEXT))
        reason = self.unfinished()
        if reason:
            lines.append((reason, ERROR_COLOR))
        return [(fit_text(small, text, width), color) for text, color in lines]

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
        if event.key == pygame.K_c and ctrl:
            if event.mod & pygame.KMOD_SHIFT:
                self.copy_prompt()
            else:
                self.copy_image()
        elif event.key == pygame.K_v and ctrl:
            self.paste_answer()
        elif event.key == pygame.K_o and ctrl:
            self.open_answer()
        elif event.key == pygame.K_e:
            self.edit_description()
        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.accept()
        elif event.key == pygame.K_DELETE:
            self.reject()

    def scroll_by(self, steps):
        self.grid.scroll_by(steps)

    def back(self):
        self.app.close_npc()
        return True
