"""One crop: its growth stages, the variants of the chosen stage, and the sheet to draw one on.

Left the stages from the ploughed field to the ripe crop, with how many of
each stage's variants are done; under them adding a stage after the chosen
one or taking it out (never below crops.MIN_STAGES, never the first or the
last), the number of variants, and the chosen stage's title, description and
height, which go into its prompt, and the crop's own description, which the
prompt of a crop's very first sprite needs. In the middle the chosen stage's
variants, and under them the growth of the chosen variant, every stage side
by side at one scale, so a stage out of step shows. Right the chosen
variant's sheet (crop_sheets.py) with the ways to an answer, as for the walk
frames; its answers open in view_crop_answers.py.
"""

from pathlib import Path

import pygame

import gemini_client
import pose_review
import win_clipboard
from answers import AnswerError, ask_open_file, clipboard_answer, store_web_answer
from crop_sheets import write_sheet
from crops import MAX_VARIANTS, find_crops
from gimp import ENV_GIMP, FileWatcher, find_gimp, open_in_gimp
from images import fitted, is_blank, trim
from sheets import SHEET_ERRORS
from theme import (
    BG, CARD_BG, CARD_HOVER, CARD_SELECTED, DONE_COLOR, ERROR_COLOR, PANEL_GAP, STATUS_COLORS, TEXT, TEXT_DIM,
)
from view import View
from view_crop_answers import CropAnswersView
from widgets import PANEL_TITLE, Button, Card, CardGrid, Checker, TextField, draw_panel, fit_text

STAGE_PANEL_W = 320
STAGE_ROW = 32
SHEET_PANEL_MIN_W = 320
SHEET_PANEL_SHARE = 0.3
CARD_SIZE = (172, 296)
THUMB_SIZE = (150, 232)
BUTTON_H = 40
SMALL_BUTTON_W = 40
BUTTON_GAP = 10
FIELD_H = 34
STRIP_SHARE = 0.38           # of the middle panel, for the growth of the chosen variant
STRIP_MIN_H = 120
HEIGHT_STEP = 0.05           # a stage's height, per click
HEIGHT_LIMITS = (0.02, 1.0)
SOIL = (120, 84, 52)         # the ploughed field, in the growth strip
FURROW = (92, 62, 38)
CHECKER_TEXT = (40, 40, 40)
DONE = STATUS_COLORS[pose_review.ACCEPTED]
WAITING = STATUS_COLORS[pose_review.PENDING]


class CropView(View):
    def __init__(self, app, stage_index=None, variant=1):
        super().__init__(app)
        self.crop = app.npc
        self.store = app.store
        self.others = find_crops()
        self.sheets = {}              # {variant: CropSheet or None} of the chosen stage
        self.grid = CardGrid()
        self.stage_rows = []          # [(rect, index)] as last drawn
        self.strip = None             # (size, [(title, image or None, bare)]) of the growth strip, as last made
        self.strip_checker = Checker()
        self.gimp = find_gimp()
        self.watcher = FileWatcher()

        self.title_field = TextField(h=FIELD_H)
        self.description_field = TextField(placeholder='what the plant looks like at this stage', h=FIELD_H)
        self.crop_field = TextField(self.crop.description, placeholder='what it looks like ripe', h=FIELD_H)
        self.fields = (self.title_field, self.description_field, self.crop_field)
        self.field_stage = None       # the Stage the title and description fields were filled from

        self.add_stage_button = Button('Add stage after', h=BUTTON_H)
        self.remove_stage_button = Button('Remove stage', h=BUTTON_H)
        self.fewer_button = Button('-', w=SMALL_BUTTON_W, h=FIELD_H)
        self.more_button = Button('+', w=SMALL_BUTTON_W, h=FIELD_H)
        self.lower_button = Button('-', w=SMALL_BUTTON_W, h=FIELD_H)
        self.taller_button = Button('+', w=SMALL_BUTTON_W, h=FIELD_H)
        self.answers_button = Button('Answers', w=150)
        self.missing_button = Button('Send missing', w=220)
        self.copy_image_button = Button('Copy image', h=BUTTON_H)
        self.copy_prompt_button = Button('Copy prompt', h=BUTTON_H)
        self.paste_button = Button('Paste answer', h=BUTTON_H)
        self.open_button = Button('Open image', h=BUTTON_H)
        self.send_button = Button('Send to Gemini', h=BUTTON_H)
        self.web_button = Button('Send in browser', h=BUTTON_H)
        self.gimp_button = Button('Edit in GIMP', h=BUTTON_H)
        self.web_missing_button = Button('Send missing in browser', h=BUTTON_H)
        self.sheet_button_rows = ((self.copy_image_button, self.copy_prompt_button),
                                  (self.paste_button, self.open_button),
                                  (self.send_button, self.web_button),
                                  (self.gimp_button,),
                                  (self.web_missing_button,))
        self.actions = ((self.add_stage_button, self.add_stage),
                        (self.remove_stage_button, self.remove_stage),
                        (self.fewer_button, lambda: self.set_variants(self.crop.variants - 1)),
                        (self.more_button, lambda: self.set_variants(self.crop.variants + 1)),
                        (self.lower_button, lambda: self.change_height(-HEIGHT_STEP)),
                        (self.taller_button, lambda: self.change_height(HEIGHT_STEP)),
                        (self.answers_button, self.open_answers),
                        (self.missing_button, self.send_missing),
                        (self.copy_image_button, self.copy_image),
                        (self.copy_prompt_button, self.copy_prompt),
                        (self.paste_button, self.paste_answer),
                        (self.open_button, self.open_answer),
                        (self.send_button, self.send_current),
                        (self.web_button, self.send_web),
                        (self.gimp_button, self.edit_in_gimp),
                        (self.web_missing_button, self.send_missing_web))
        self.stage_index = self.first_open_stage() if stage_index is None else stage_index
        self.variant = variant
        self.select_stage(min(self.stage_index, len(self.crop.stages) - 1), variant)

    # --- state ------------------------------------------------------------

    def stage(self):
        return self.crop.stages[self.stage_index]

    def first_open_stage(self):
        """Where work is: the latest stage with a variant missing (the ripe one first, the rest are drawn
        from it), else the ripe one."""
        stages = self.crop.stages
        for index in range(len(stages) - 1, 0, -1):
            if self.crop.done(stages[index]) < self.crop.variants:
                return index
        return len(stages) - 1

    def current_sheet(self):
        return self.sheets.get(self.variant)

    def current_path(self):
        stage = self.stage()
        return None if stage.bare else self.crop.sprite_path(stage.key, self.variant)

    def pose(self):
        return self.crop.pose(self.stage().key, self.variant)

    def select_stage(self, index, variant=None):
        self.commit_fields()
        self.stage_index = index
        if variant is not None:
            self.variant = max(1, min(variant, self.crop.variants))
        stage = self.field_stage = self.stage()
        self.title_field.text = stage.title
        self.description_field.text = stage.description
        self.grid.scroll = 0
        self.refresh()

    def select_variant(self, variant):
        self.variant = variant
        self.strip = None

    def build_sheets(self):
        """The chosen stage's sheets, from the sprites on disk as they are now."""
        self.sheets = {}
        if self.stage().bare:
            return
        for variant in range(1, self.crop.variants + 1):
            try:
                self.sheets[variant] = write_sheet(self.crop, self.stage_index, variant, self.others)
            except SHEET_ERRORS as exc:
                self.sheets[variant] = None
                self.app.set_status(f'Cannot build the sheet of {self.crop.pose(self.stage().key, variant)}: {exc}',
                                    error=True)

    def refresh(self):
        """Sheets, cards and the growth strip, after sprites or answers changed."""
        self.others = find_crops()
        self.build_sheets()
        self.build_cards()
        self.strip = None
        self.watcher.reset()

    def note(self, variant):
        """(text, colour) of a variant's state."""
        stage = self.stage()
        if self.crop.has(stage.key, variant):
            return 'done', DONE
        note = self.store.pose_note(self.crop.pose(stage.key, variant))
        if note == 'rejected':
            return note, ERROR_COLOR
        if note:
            return note, WAITING
        if self.sheets.get(variant) is None:
            return 'nothing to draw it from', ERROR_COLOR
        return 'not drawn', TEXT_DIM

    def build_cards(self):
        cards = []
        stage = self.stage()
        if not stage.bare:
            for variant in range(1, self.crop.variants + 1):
                sprite = self.crop.sprite(stage.key, variant)
                sheet = self.sheets.get(variant)
                if sheet:
                    surface = sheet.surface if is_blank(sprite) else sheet.with_result(sprite)
                    thumb = fitted(surface, THUMB_SIZE)
                elif not is_blank(sprite):
                    thumb = fitted(trim(sprite), THUMB_SIZE)
                else:
                    thumb = fitted(pygame.Surface((1, 1), pygame.SRCALPHA), THUMB_SIZE)
                note, color = self.note(variant)
                cards.append(Card(variant, f'Variant {variant}', thumb, note, note_color=color, size=CARD_SIZE))
        self.grid.cards = cards

    def stage_note(self, stage):
        """(text, colour) beside a stage in the list."""
        if stage.bare:
            return 'ground tiles', TEXT_DIM
        done = self.crop.done(stage)
        waiting = sum(e.pose.rsplit('_', 1)[0] == stage.key for e in self.store.pending())
        note, color = f'{done}/{self.crop.variants}', DONE if done == self.crop.variants else TEXT_DIM
        if waiting:
            note, color = f'{note}  +{waiting}', WAITING
        return note, color

    def missing_sheets(self):
        stage = self.stage()
        return [s for v, s in self.sheets.items() if s and not self.crop.has(stage.key, v)]

    # --- changing the crop ------------------------------------------------

    def commit_fields(self):
        """Take what was typed into the fields; True if anything changed."""
        for field in self.fields:
            field.focus(False)
        changed = False
        stage = self.field_stage if self.field_stage in self.crop.stages else None
        title = self.title_field.text.strip()
        if stage and title and title != stage.title:
            stage.title, changed = title, True
        description = self.description_field.text.strip()
        if stage and description != stage.description:
            stage.description, changed = description, True
        about = self.crop_field.text.strip()
        if about != self.crop.description:
            self.crop.description, changed = about, True
        if changed:
            self.crop.save()
        return changed

    def add_stage(self):
        self.commit_fields()
        if self.crop.can_add_stage_after(self.stage_index):
            index = self.crop.add_stage_after(self.stage_index)
            self.select_stage(index)
            self.app.set_status(f'New stage at {self.stage().height:.0%} of the ripe height - give it a title '
                                'and a description')
            self.title_field.focus(True)

    def remove_stage(self):
        self.commit_fields()
        if not self.crop.can_remove_stage(self.stage_index):
            return
        title = self.stage().title
        moved = self.crop.remove_stage(self.stage_index)
        self.select_stage(min(self.stage_index, len(self.crop.stages) - 1))
        kept = f', its {moved} sprite(s) moved to {self.crop.out_dir.name}/removed' if moved else ''
        self.app.set_status(f'Stage "{title}" taken out{kept}')

    def set_variants(self, count):
        self.commit_fields()
        if not 1 <= count <= MAX_VARIANTS:
            return
        moved = self.crop.set_variants(count)
        self.select_stage(self.stage_index, self.variant)
        kept = f' - {moved} sprite(s) moved to {self.crop.out_dir.name}/removed' if moved else ''
        self.app.set_status(f'{count} variants per stage{kept}')

    def change_height(self, step):
        stage = self.stage()
        if stage.bare or stage is self.crop.ripe:
            return
        stage.height = round(min(HEIGHT_LIMITS[1], max(HEIGHT_LIMITS[0], stage.height + step)), 2)
        self.crop.save()
        self.refresh()

    # --- the web view and the API -------------------------------------------

    def copy_image(self):
        sheet = self.current_sheet()
        if not sheet:
            return
        try:
            win_clipboard.copy_image(sheet.surface)
        except win_clipboard.ClipboardError as exc:
            self.app.set_status(str(exc), error=True)
            return
        self.app.set_status(f'Sheet of {sheet.pose} copied - paste it into Gemini, then the prompt')
        self.app.toast.show('Sheet copied')

    def copy_prompt(self):
        sheet = self.current_sheet()
        if not sheet:
            return
        try:
            win_clipboard.copy_text(sheet.prompt)
        except win_clipboard.ClipboardError as exc:
            self.app.set_status(str(exc), error=True)
            return
        self.app.set_status(f'Prompt of {sheet.pose} copied')
        self.app.toast.show('Prompt copied')

    def send_web(self):
        sheet = self.current_sheet()
        if sheet:
            crop, store = self.crop, self.store
            self.app.send_web(sheet, f'{crop.title} {sheet.pose}',
                              lambda path: self.take_downloaded(crop, store, sheet, path))

    def take_downloaded(self, crop, store, sheet, path):
        """Book the browser's answer; open it if this crop is still on screen."""
        entry = store_web_answer(crop, store, sheet, path)
        if self.app.view is self:
            self.build_cards()
            self.open_answers(sheet, entry)

    def send_missing_web(self):
        """Send every variant of the stage not drawn yet to the browser, one after another; or stop that."""
        app = self.app
        if app.web_queue_busy():
            app.stop_web_queue()
            return
        crop, store = self.crop, self.store
        app.send_web_queue([(sheet, f'{crop.title} {sheet.pose}',
                             lambda path, sheet=sheet: self.take_queued(crop, store, sheet, path))
                            for sheet in self.missing_sheets()])

    def take_queued(self, crop, store, sheet, path):
        store_web_answer(crop, store, sheet, path)
        if self.app.view is self:
            self.build_cards()

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
        """Store an answer from the web view for the chosen variant and open it.

        Raises:
            AnswerError: If the source is not an image.
        """
        sheet = self.current_sheet()
        if sheet:
            entry = store_web_answer(self.crop, self.store, sheet, source, kind)
            self.open_answers(sheet, entry)

    def send_current(self):
        sheet = self.current_sheet()
        if sheet:
            self.app.send([sheet])

    def send_missing(self):
        self.app.send(self.missing_sheets())

    def open_answers(self, sheet=None, entry=None):
        """The answers of the chosen variant (or of `sheet`'s), `entry` first."""
        sheet = sheet or self.current_sheet()
        if sheet is None or not (entry or self.store.for_pose(sheet.pose)):
            return
        self.app.show(CropAnswersView(self.app, self, sheet, entry))

    # --- editing by hand ----------------------------------------------------

    def edit_in_gimp(self):
        path = self.current_path()
        if not (path and path.is_file()):
            return
        if not self.gimp:
            self.app.set_status(f'GIMP not found - set {ENV_GIMP} to its gimp.exe', error=True)
            return
        try:
            open_in_gimp(self.gimp, path)
        except OSError as exc:
            self.app.set_status(f'Could not start GIMP: {exc}', error=True)
            return
        self.app.set_status(f'{path.name} opened in GIMP - File > Overwrite {path.name} to save it back')
        self.app.toast.show('Opening in GIMP')

    def tick(self):
        """Refresh when a sprite of the stage was changed outside the tool, e.g. in GIMP."""
        stage = self.stage()
        if stage.bare:
            return
        changed = self.watcher.changed([self.crop.sprite_path(stage.key, v) for v in range(1, self.crop.variants + 1)])
        if changed:
            self.refresh()
            self.app.set_status(f'Updated from disk: {", ".join(p.name for p in changed)}')

    # --- header and footer --------------------------------------------------

    def header(self):
        return (f'{self.crop.title}: growth stages',
                'Up/Down = stage, Left/Right = variant. Ctrl+W = send in browser, Ctrl+Shift+W = send missing in '
                'browser, Ctrl+C = copy sheet, Ctrl+Shift+C = copy prompt, Ctrl+V or drop a file = answer, '
                'R = answers, G = edit in GIMP, S = settings.')

    def footer(self):
        app = self.app
        return ((app.back_button, app.folder_button, self.answers_button), (app.settings_button, self.missing_button))

    def update_footer(self):
        app = self.app
        sheet = self.current_sheet()
        answers = self.store.for_pose(sheet.pose) if sheet else []
        waiting = sum(e.status == pose_review.PENDING for e in answers)
        self.answers_button.label = f'Answers ({waiting})' if waiting else 'Answers'
        self.answers_button.enabled = bool(answers)
        missing = len(self.missing_sheets()) * app.settings.tries
        self.missing_button.label = 'Sending ...' if app.busy() else f'Send missing ({missing})'
        self.missing_button.enabled = bool(missing) and not app.busy() and not gemini_client.SDK_ERROR

    # --- drawing ------------------------------------------------------------

    def areas(self):
        """(stages, cards, strip, sheet) panels."""
        body = self.app.body()
        sheet_w = max(SHEET_PANEL_MIN_W, int(body.w * SHEET_PANEL_SHARE))
        stages = pygame.Rect(body.x, body.y, STAGE_PANEL_W, body.h)
        sheet = pygame.Rect(body.right - sheet_w, body.y, sheet_w, body.h)
        middle = pygame.Rect(stages.right + PANEL_GAP, body.y, sheet.x - stages.right - 2 * PANEL_GAP, body.h)
        strip_h = max(STRIP_MIN_H, int(middle.h * STRIP_SHARE))
        strip = pygame.Rect(middle.x, middle.bottom - strip_h, middle.w, strip_h)
        cards = pygame.Rect(middle.x, middle.y, middle.w, strip.y - PANEL_TITLE - PANEL_GAP - middle.y)
        return stages, cards, strip, sheet

    def draw(self, screen, mouse):
        stages, cards, strip, sheet = self.areas()
        self.draw_stages(screen, stages, mouse)
        small = self.app.fonts.small
        stage = self.stage()
        if stage.bare:
            caption = f'{stage.title}: the bare field is ground tiles, it has no sprites'
        else:
            caption = f'{stage.title}: {self.crop.done(stage)} of {self.crop.variants} variants drawn'
        screen.blit(small.render(fit_text(small, caption, cards.w), True, TEXT_DIM), (cards.x + 4, cards.y - 20))
        self.grid.layout(cards)
        self.grid.draw(screen, self.app.fonts, mouse, selected_key=self.variant)
        self.draw_strip(screen, strip)
        self.draw_sheet(screen, sheet, mouse)

    def draw_stages(self, screen, rect, mouse):
        fonts = self.app.fonts
        small = fonts.small
        draw_panel(screen, fonts, rect, 'Stages, from sowing to harvest')
        inner = rect.inflate(-16, -16)
        y = inner.y
        self.stage_rows = []
        for index, stage in enumerate(self.crop.stages):
            row = pygame.Rect(inner.x, y, inner.w, STAGE_ROW - 4)
            y += STAGE_ROW
            color = CARD_SELECTED if index == self.stage_index else CARD_HOVER if row.collidepoint(mouse) else BG
            pygame.draw.rect(screen, color, row, border_radius=5)
            label = small.render(fit_text(small, f'{index}. {stage.title}', row.w - 90), True, TEXT)
            screen.blit(label, label.get_rect(midleft=(row.x + 10, row.centery)))
            note, note_color = self.stage_note(stage)
            text = small.render(note, True, note_color)
            screen.blit(text, text.get_rect(midright=(row.right - 10, row.centery)))
            self.stage_rows.append((row, index))

        y += 4
        half = (inner.w - BUTTON_GAP) // 2
        self.add_stage_button.rect = pygame.Rect(inner.x, y, half, BUTTON_H)
        self.remove_stage_button.rect = pygame.Rect(inner.right - half, y, half, BUTTON_H)
        self.add_stage_button.enabled = self.crop.can_add_stage_after(self.stage_index)
        self.remove_stage_button.enabled = self.crop.can_remove_stage(self.stage_index)
        y += BUTTON_H + BUTTON_GAP
        self.fewer_button.enabled = self.crop.variants > 1
        self.more_button.enabled = self.crop.variants < MAX_VARIANTS
        y = self.draw_stepper(screen, inner, y, f'Variants per stage: {self.crop.variants}',
                              self.fewer_button, self.more_button, mouse)

        stage = self.stage()
        y += 8
        y = self.draw_field(screen, inner, y, 'Stage title', self.title_field, mouse)
        y = self.draw_field(screen, inner, y, 'What it looks like (for the prompt)', self.description_field, mouse)
        fixed = stage.bare or stage is self.crop.ripe
        height = 'fixed' if fixed else f'{stage.height:.0%} of the ripe plant'
        self.lower_button.enabled = not fixed and stage.height > HEIGHT_LIMITS[0]
        self.taller_button.enabled = not fixed and stage.height < HEIGHT_LIMITS[1]
        y = self.draw_stepper(screen, inner, y, f'Height: {height}', self.lower_button, self.taller_button, mouse)
        y += 8
        self.draw_field(screen, inner, y, 'The crop, ripe (for a first sprite)', self.crop_field, mouse)
        for button in (self.add_stage_button, self.remove_stage_button):
            button.draw(screen, fonts.font, mouse)

    def draw_field(self, screen, inner, y, caption, field, mouse):
        small = self.app.fonts.small
        screen.blit(small.render(caption, True, TEXT_DIM), (inner.x, y))
        field.rect = pygame.Rect(inner.x, y + 20, inner.w, FIELD_H)
        field.draw(screen, small, mouse)
        return field.rect.bottom + BUTTON_GAP

    def draw_stepper(self, screen, inner, y, label, minus, plus, mouse):
        """A label with - and + buttons at its right; returns the y under it."""
        small = self.app.fonts.small
        plus.rect.topright = (inner.right, y)
        minus.rect.topright = (plus.rect.x - 6, y)
        text = small.render(fit_text(small, label, minus.rect.x - inner.x - 8), True, TEXT)
        screen.blit(text, text.get_rect(midleft=(inner.x, minus.rect.centery)))
        for button in (minus, plus):
            button.draw(screen, self.app.fonts.font, mouse)
        return y + FIELD_H + BUTTON_GAP

    def growth(self, size):
        """[(title, image or None, bare)] of the chosen variant's stages, at one scale to fit `size`."""
        if self.strip and self.strip[0] == size:
            return self.strip[1]
        stages = self.crop.stages
        sprites = [None if s.bare else self.crop.sprite(s.key, self.variant) for s in stages]
        sprites = [None if is_blank(s) else trim(s) for s in sprites]
        column = size[0] / len(stages)
        drawn = [s for s in sprites if s]
        factor = min([(column - 12) / s.get_width() for s in drawn] +
                     [(size[1] - 50) / s.get_height() for s in drawn], default=1)
        items = []
        for stage, sprite in zip(stages, sprites):
            image = None
            if sprite:
                image = pygame.transform.smoothscale(
                    sprite, (max(1, round(sprite.get_width() * factor)), max(1, round(sprite.get_height() * factor))))
            items.append((stage.title, image, stage.bare))
        self.strip = (size, items)
        return items

    def draw_strip(self, screen, rect):
        """The chosen variant from the ploughed field to the ripe crop, side by side on one ground line."""
        small = self.app.fonts.small
        screen.blit(small.render(f'Variant {self.variant} growing, every stage at one scale', True, TEXT_DIM),
                    (rect.x + 4, rect.y - 20))
        self.strip_checker.draw(screen, rect)
        items = self.growth(rect.size)
        column = rect.w / len(items)
        ground = rect.bottom - 30
        for index, (title, image, bare) in enumerate(items):
            centre = int(rect.x + column * (index + 0.5))
            if index == self.stage_index:
                pygame.draw.rect(screen, DONE_COLOR, (int(rect.x + column * index) + 2, rect.y + 2,
                                                      int(column) - 4, rect.h - 4), 2, border_radius=4)
            if bare:
                soil = pygame.Rect(0, 0, int(column * 0.8), 10)
                soil.midbottom = (centre, ground)
                pygame.draw.rect(screen, SOIL, soil, border_radius=3)
                for x in range(soil.x + 4, soil.right - 2, 8):
                    pygame.draw.line(screen, FURROW, (x, soil.y + 2), (x + 3, soil.bottom - 2), 2)
            elif image:
                screen.blit(image, image.get_rect(midbottom=(centre, ground)))
            else:
                text = small.render('not drawn', True, CHECKER_TEXT)
                screen.blit(text, text.get_rect(midbottom=(centre, ground)))
            label = small.render(fit_text(small, title, int(column) - 6), True, CHECKER_TEXT)
            screen.blit(label, label.get_rect(midtop=(centre, ground + 6)))

    def draw_sheet(self, screen, rect, mouse):
        app = self.app
        fonts = app.fonts
        sheet = self.current_sheet()
        stage = self.stage()
        if sheet:
            ref = sheet.reference
            source = (f'{ref.stage.title} {ref.variant}' if ref.crop.name == self.crop.name
                      else f'{ref.crop.title} (another crop)')
            title = f'Sheet for {sheet.pose}  -  drawn from {source}'
        elif stage.bare:
            title = 'No sheet: the ploughed field has no sprites'
        else:
            title = 'No sheet: nothing to draw it from yet'
        draw_panel(screen, fonts, rect, title)
        inner = rect.inflate(-20, -20)
        half = (inner.w - BUTTON_GAP) // 2
        rows = self.sheet_button_rows
        y = inner.bottom - len(rows) * (BUTTON_H + BUTTON_GAP) + BUTTON_GAP
        for row in rows:
            if len(row) == 1:
                row[0].rect = pygame.Rect(inner.x, y, inner.w, BUTTON_H)
            else:
                row[0].rect = pygame.Rect(inner.x, y, half, BUTTON_H)
                row[1].rect = pygame.Rect(inner.right - half, y, half, BUTTON_H)
            y += BUTTON_H + BUTTON_GAP
        area = pygame.Rect(inner.x, inner.y, inner.w, rows[0][0].rect.y - BUTTON_GAP - inner.y)
        if sheet:
            screen.blit(fitted(sheet.surface, area.size, CARD_BG), area)
        elif not stage.bare:
            lines = ('Every stage sprite is drawn from another sprite:',
                     'this crop\'s, or another crop\'s ripe one.',
                     'Add a crop with a ripe sprite first.')
            for index, line in enumerate(lines):
                text = fonts.small.render(fit_text(fonts.small, line, area.w), True, TEXT_DIM)
                screen.blit(text, text.get_rect(midtop=(area.centerx, area.y + 20 + 20 * index)))

        ready = bool(sheet)
        for button in (self.copy_image_button, self.copy_prompt_button, self.paste_button):
            button.enabled = ready and win_clipboard.AVAILABLE
        self.open_button.enabled = ready
        self.web_button.enabled = ready and not app.web_queue_busy()
        if app.web_queue_busy():
            self.web_missing_button.label = f'Stop browser queue ({app.web_queue_left()} left)'
            self.web_missing_button.enabled = bool(app.web_queue)
        else:
            missing = len(self.missing_sheets())
            self.web_missing_button.label = f'Send missing in browser ({missing})'
            self.web_missing_button.enabled = bool(missing)
        self.send_button.enabled = ready and not app.busy() and not gemini_client.SDK_ERROR
        tries = app.settings.tries
        self.send_button.label = 'Sending ...' if app.busy() else (
            f'Send to Gemini ({tries}x)' if tries > 1 else 'Send to Gemini')
        path = self.current_path()
        self.gimp_button.enabled = bool(self.gimp and path and path.is_file())
        self.gimp_button.label = 'Edit in GIMP' if self.gimp else 'Edit in GIMP (GIMP not found)'
        for row in rows:
            for button in row:
                button.draw(screen, fonts.font, mouse)

    # --- input --------------------------------------------------------------

    def click(self, pos):
        target = next((f for f in self.fields if f.rect.collidepoint(pos)), None)
        if target and target.focused:
            return
        if any(f.focused for f in self.fields) and self.commit_fields():
            self.refresh()
        if target:
            target.focus(True)
            return
        for button, action in self.actions:
            if button.hit(pos):
                action()
                return
        for row, index in self.stage_rows:
            if row.collidepoint(pos):
                self.select_stage(index)
                return
        card = self.grid.card_at(pos)
        if card:
            self.select_variant(card.key)

    def captures_keys(self):
        return any(f.focused for f in self.fields)

    def text_input(self, text):
        for field in self.fields:
            if field.focused:
                field.type(text)

    def key(self, event):
        focused = next((f for f in self.fields if f.focused), None)
        if focused:
            if focused.key(event) == 'done':
                if self.commit_fields():
                    self.refresh()
            return
        ctrl = event.mod & pygame.KMOD_CTRL
        shift = event.mod & pygame.KMOD_SHIFT
        if event.key == pygame.K_c and ctrl:
            self.copy_prompt() if shift else self.copy_image()
        elif event.key == pygame.K_w and ctrl:
            self.send_missing_web() if shift else self.send_web()
        elif event.key == pygame.K_v and ctrl:
            self.paste_answer()
        elif event.key == pygame.K_o and ctrl:
            self.open_answer()
        elif event.key in (pygame.K_UP, pygame.K_DOWN):
            step = 1 if event.key == pygame.K_DOWN else -1
            self.select_stage((self.stage_index + step) % len(self.crop.stages))
        elif event.key in (pygame.K_LEFT, pygame.K_RIGHT) and self.grid.cards:
            step = 1 if event.key == pygame.K_RIGHT else -1
            self.select_variant((self.variant - 1 + step) % self.crop.variants + 1)
        elif event.key == pygame.K_r:
            self.open_answers()
        elif event.key == pygame.K_g:
            self.edit_in_gimp()

    def scroll_by(self, steps):
        self.grid.scroll_by(steps)

    def back(self):
        self.commit_fields()
        self.app.close_crop()
        return True
