"""One animal: its frames, the chosen one beside the sheep's pose, its walk and grazing playing, and the sheet.

Left the frames, all facing left: standing, the walk and the grazing, with
how far each is, and under them what the animal looks like, which goes into
its prompts. In the middle the chosen frame beside the sheep's frame of the
same pose (the pose it is drawn in) and the animal standing, at one scale on
one ground line; under them the walk and the grazing played as the game
plays them, with whatever frames there are. Right the chosen frame's sheet
as it is sent (animal_sheets.py), with the ways to an answer as for the walk
frames of the humans. Until the animal has its standing sprite, that is the
only frame that can be made. Its answers open in view_animal_answers.py.
"""

from pathlib import Path

import pygame

import gemini_client
import pose_review
import win_clipboard
from animal_sheets import animal_sheet, can_draw
from animals import POSES, STATIC, base_animal, poses_of
from answers import AnswerError, ask_open_file, clipboard_answer, store_web_answer
from gimp import ENV_GIMP, FileWatcher, find_gimp, open_in_gimp
from images import fitted, is_blank, trim
from theme import BG, CARD_BG, CARD_HOVER, CARD_SELECTED, ERROR_COLOR, PANEL_GAP, STATUS_COLORS, TEXT, TEXT_DIM
from view import View
from view_animal_answers import AnimalAnswersView
from widgets import Button, Checker, TextField, draw_panel, fit_text

FRAME_PANEL_W = 320
FRAME_ROW = 32
SHEET_PANEL_MIN_W = 320
SHEET_PANEL_SHARE = 0.3
BUTTON_H = 40
BUTTON_GAP = 10
FIELD_H = 34
PLAY_SHARE = 0.42            # of the middle, for the animations
WALK_FRAME_S = 0.18          # how long the game shows a walk frame (Animator's interval, slowed for the sheep)
EAT_FRAME_S = (0.55, 0.22)   # the game's grazing frames, sheep.EAT_FRAME_DURATIONS
CHECKER_TEXT = (40, 40, 40)
DONE = STATUS_COLORS[pose_review.ACCEPTED]
WAITING = STATUS_COLORS[pose_review.PENDING]


class AnimalView(View):
    def __init__(self, app, pose=None):
        super().__init__(app)
        self.animal = app.npc
        self.store = app.store
        self.base = base_animal()
        self.pose = pose or self.first_open_pose()
        self.sheet = None             # the chosen frame's AnimalSheet, or None
        self.sheet_error = ''         # why there is none
        self.sheet_cache = None       # (size, image) of the sheet as last drawn
        self.compare_cache = None     # (size, [(label, image or None)]) of the comparison, as last made
        self.play_cache = {}          # {(group, size): [(image, seconds)]}
        self.frame_rows = []          # [(rect, pose)] as last drawn
        self.checker = Checker()
        self.gimp = find_gimp()
        self.watcher = FileWatcher()

        self.description_field = TextField(self.animal.description, placeholder='what it looks like', h=FIELD_H)
        self.answers_button = Button('Answers', w=150)
        self.copy_image_button = Button('Copy image', h=BUTTON_H)
        self.copy_prompt_button = Button('Copy prompt', h=BUTTON_H)
        self.paste_button = Button('Paste answer', h=BUTTON_H)
        self.open_button = Button('Open image', h=BUTTON_H)
        self.send_button = Button('Send to Gemini', h=BUTTON_H)
        self.web_button = Button('Send in browser', h=BUTTON_H)
        self.gimp_button = Button('Edit in GIMP', h=BUTTON_H)
        self.web_missing_button = Button('Send missing in browser', h=BUTTON_H)
        self.missing_button = Button('Send missing', w=220)
        self.sheet_button_rows = ((self.copy_image_button, self.copy_prompt_button),
                                  (self.paste_button, self.open_button),
                                  (self.send_button, self.web_button),
                                  (self.gimp_button,),
                                  (self.web_missing_button,))
        self.actions = ((self.answers_button, self.open_answers),
                        (self.missing_button, self.send_missing),
                        (self.copy_image_button, self.copy_image),
                        (self.copy_prompt_button, self.copy_prompt),
                        (self.paste_button, self.paste_answer),
                        (self.open_button, self.open_answer),
                        (self.send_button, self.send_current),
                        (self.web_button, self.send_web),
                        (self.gimp_button, self.edit_in_gimp),
                        (self.web_missing_button, self.send_missing_web))

    # --- state ------------------------------------------------------------

    def first_open_pose(self):
        """Where work is: the first frame not drawn that can be, else the standing one."""
        for pose in POSES:
            if not self.animal.has(pose.key) and can_draw(self.animal, pose)[0]:
                return pose
        return STATIC

    def refresh(self):
        self.base = base_animal()
        self.build_sheet()
        self.compare_cache = None
        self.play_cache = {}
        self.watcher.reset()

    def build_sheet(self):
        self.sheet, self.sheet_error, self.sheet_cache = None, '', None
        possible, why = can_draw(self.animal, self.pose)
        if not possible:
            self.sheet_error = why
            return
        try:
            self.sheet = animal_sheet(self.animal, self.pose)
        except (pygame.error, OSError) as exc:
            self.sheet_error = str(exc)

    def select(self, pose):
        self.commit_fields()
        self.pose = pose
        self.refresh()

    def written_sheet(self, pose=None):
        """A frame's sheet written to disk, ready to send; None (with the reason shown) if it cannot be."""
        pose = pose or self.pose
        possible, why = can_draw(self.animal, pose)
        if not possible:
            self.app.set_status(f'{pose.title}: {why}', error=True)
            return None
        try:
            return animal_sheet(self.animal, pose, write=True)
        except (pygame.error, OSError) as exc:
            self.app.set_status(f'Cannot write the sheet of {pose.title}: {exc}', error=True)
            return None

    def note(self, pose):
        """(text, colour) beside a frame in the list."""
        if self.animal.has(pose.key):
            return 'done', DONE
        note = self.store.pose_note(pose.key)
        if note == 'rejected':
            return note, ERROR_COLOR
        if note:
            return note, WAITING
        possible, _ = can_draw(self.animal, pose)
        return ('not drawn', TEXT_DIM) if possible else ('later', TEXT_DIM)

    def missing_poses(self):
        """The frames not drawn yet that can be: what "Send missing" sends."""
        return [p for p in POSES if not self.animal.has(p.key) and can_draw(self.animal, p)[0]]

    def missing_sheets(self):
        sheets = [self.written_sheet(p) for p in self.missing_poses()]
        return [s for s in sheets if s]

    def commit_fields(self):
        """Take what was typed; True if it changed."""
        self.description_field.focus(False)
        text = self.description_field.text.strip()
        if text == self.animal.description:
            return False
        self.animal.description = text
        self.animal.save()
        return True

    # --- the web view and the API -------------------------------------------

    def copy_image(self):
        sheet = self.written_sheet()
        if not sheet:
            return
        try:
            win_clipboard.copy_image(sheet.surface)
        except win_clipboard.ClipboardError as exc:
            self.app.set_status(str(exc), error=True)
            return
        self.app.set_status(f'Sheet of {sheet.name} copied - paste it into Gemini, then the prompt')
        self.app.toast.show('Sheet copied')

    def copy_prompt(self):
        sheet = self.written_sheet()
        if not sheet:
            return
        try:
            win_clipboard.copy_text(sheet.prompt)
        except win_clipboard.ClipboardError as exc:
            self.app.set_status(str(exc), error=True)
            return
        self.app.set_status(f'Prompt of {sheet.name} copied')
        self.app.toast.show('Prompt copied')

    def send_web(self):
        sheet = self.written_sheet()
        if sheet:
            animal, store = self.animal, self.store
            self.app.send_web(sheet, f'{animal.title} {sheet.name}',
                              lambda path: self.take_downloaded(animal, store, sheet, path))

    def take_downloaded(self, animal, store, sheet, path):
        """Book the browser's answer; open it if this animal is still on screen."""
        entry = store_web_answer(animal, store, sheet, path)
        if self.app.view is self:
            self.open_answers(sheet, entry)

    def send_missing_web(self):
        """Send every frame not drawn yet to the browser, one after another; or stop that."""
        app = self.app
        if app.web_queue_busy():
            app.stop_web_queue()
            return
        animal, store = self.animal, self.store
        app.send_web_queue([(sheet, f'{animal.title} {sheet.name}',
                             lambda path, sheet=sheet: store_web_answer(animal, store, sheet, path))
                            for sheet in self.missing_sheets()])

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
        """Store an answer from the web view for the chosen frame and open it.

        Raises:
            AnswerError: If the source is not an image.
        """
        sheet = self.written_sheet()
        if sheet:
            entry = store_web_answer(self.animal, self.store, sheet, source, kind)
            self.open_answers(sheet, entry)

    def send_current(self):
        sheet = self.written_sheet()
        if sheet:
            self.app.send([sheet])

    def send_missing(self):
        self.app.send(self.missing_sheets())

    def open_answers(self, sheet=None, entry=None):
        """The answers of the chosen frame (or of `sheet`'s), `entry` first."""
        if sheet is None:
            if not self.store.for_pose(self.pose.key):
                return
            sheet = self.sheet or self.written_sheet()
            if sheet is None:
                return
        if entry or self.store.for_pose(sheet.pose):
            self.commit_fields()
            self.app.show(AnimalAnswersView(self.app, self, sheet, entry))

    # --- editing by hand ----------------------------------------------------

    def edit_in_gimp(self):
        path = self.animal.sprite_path(self.pose.key)
        if not path.is_file():
            return
        if not self.gimp:
            self.app.set_status(f'GIMP not found - set {ENV_GIMP} to its gimp.exe', error=True)
            return
        try:
            open_in_gimp(self.gimp, path)
        except OSError as exc:
            self.app.set_status(f'Could not start GIMP: {exc}', error=True)
            return
        self.app.set_status(f'{path.name} opened in GIMP - File > Overwrite {path.name} to save it back '
                            '(the right-hand mirror image is not updated)')
        self.app.toast.show('Opening in GIMP')

    def tick(self):
        """Refresh when a frame was changed outside the tool, e.g. in GIMP."""
        changed = self.watcher.changed([self.animal.sprite_path(p.key) for p in POSES])
        if changed:
            self.refresh()
            self.app.set_status(f'Updated from disk: {", ".join(p.name for p in changed)}')

    # --- header and footer --------------------------------------------------

    def header(self):
        return (f'{self.animal.title}: frames, facing left',
                'Up/Down = frame. Ctrl+W = send in browser, Ctrl+Shift+W = send missing in browser, Ctrl+C = copy '
                'sheet, Ctrl+Shift+C = copy prompt, Ctrl+V or drop a file = answer, R = answers, G = edit in GIMP.')

    def footer(self):
        app = self.app
        return ((app.back_button, app.folder_button, self.answers_button), (app.settings_button, self.missing_button))

    def update_footer(self):
        app = self.app
        answers = self.store.for_pose(self.pose.key)
        waiting = sum(e.status == pose_review.PENDING for e in answers)
        self.answers_button.label = f'Answers ({waiting})' if waiting else 'Answers'
        self.answers_button.enabled = bool(answers)
        missing = len(self.missing_poses()) * app.settings.tries
        self.missing_button.label = 'Sending ...' if app.busy() else f'Send missing ({missing})'
        self.missing_button.enabled = bool(missing) and not app.busy() and not gemini_client.SDK_ERROR

    # --- drawing ------------------------------------------------------------

    def areas(self):
        """(frames, comparison, animations, sheet) panels."""
        body = self.app.body()
        sheet_w = max(SHEET_PANEL_MIN_W, int(body.w * SHEET_PANEL_SHARE))
        frames = pygame.Rect(body.x, body.y, FRAME_PANEL_W, body.h)
        sheet = pygame.Rect(body.right - sheet_w, body.y, sheet_w, body.h)
        middle = pygame.Rect(frames.right + PANEL_GAP, body.y, sheet.x - frames.right - 2 * PANEL_GAP, body.h)
        play_h = int(middle.h * PLAY_SHARE)
        play = pygame.Rect(middle.x, middle.bottom - play_h, middle.w, play_h)
        compare = pygame.Rect(middle.x, middle.y, middle.w, play.y - 28 - middle.y)
        return frames, compare, play, sheet

    def draw(self, screen, mouse):
        frames, compare, play, sheet = self.areas()
        self.draw_frames(screen, frames, mouse)
        self.draw_compare(screen, compare)
        self.draw_play(screen, play)
        self.draw_sheet(screen, sheet, mouse)

    def draw_frames(self, screen, rect, mouse):
        fonts = self.app.fonts
        small = fonts.small
        draw_panel(screen, fonts, rect, 'Frames, facing left')
        inner = rect.inflate(-16, -16)
        y = inner.y
        self.frame_rows = []
        for pose in POSES:
            if pose.number == 1:
                y += 8   # a little gap before each group
            row = pygame.Rect(inner.x, y, inner.w, FRAME_ROW - 4)
            y += FRAME_ROW
            color = CARD_SELECTED if pose == self.pose else CARD_HOVER if row.collidepoint(mouse) else BG
            pygame.draw.rect(screen, color, row, border_radius=5)
            label = small.render(pose.title, True, TEXT)
            screen.blit(label, label.get_rect(midleft=(row.x + 10, row.centery)))
            note, note_color = self.note(pose)
            text = small.render(note, True, note_color)
            screen.blit(text, text.get_rect(midright=(row.right - 10, row.centery)))
            self.frame_rows.append((row, pose))
        y += 16
        screen.blit(small.render('What it looks like (for the prompts)', True, TEXT_DIM), (inner.x, y))
        self.description_field.rect = pygame.Rect(inner.x, y + 20, inner.w, FIELD_H)
        self.description_field.draw(screen, small, mouse)
        y = self.description_field.rect.bottom + 16
        lines = ('Every frame is saved facing left and, mirrored,',
                 'facing right, which the game plays walking right.')
        if self.animal.is_base:
            lines += ('', 'The sheep\'s frames are the poses every',
                      'other animal\'s frames are drawn in.')
        for line in lines:
            screen.blit(small.render(fit_text(small, line, inner.w), True, TEXT_DIM), (inner.x, y))
            y += 20

    def compared(self, size):
        """[(label, image or None)]: the sheep's pose, the animal standing and the chosen frame, at one scale."""
        if self.compare_cache and self.compare_cache[0] == size:
            return self.compare_cache[1]
        animal, pose = self.animal, self.pose
        shown = []
        if self.base and not animal.is_base and pose != STATIC:
            shown.append(('the sheep\'s pose', self.base.sprite(pose.key)))
        if pose != STATIC:
            shown.append(('standing', animal.sprite(STATIC.key)))
        shown.append((pose.title.lower(), animal.sprite(pose.key)))
        shown = [(label, None if is_blank(s) else trim(s)) for label, s in shown]
        drawn = [s for _, s in shown if s]
        column = size[0] / len(shown)
        factor = min([(column - 20) / s.get_width() for s in drawn] +
                     [(size[1] - 60) / s.get_height() for s in drawn], default=1)
        items = []
        for label, sprite in shown:
            image = None
            if sprite:
                image = pygame.transform.smoothscale(
                    sprite, (max(1, round(sprite.get_width() * factor)), max(1, round(sprite.get_height() * factor))))
            items.append((label, image))
        self.compare_cache = (size, items)
        return items

    def draw_compare(self, screen, rect):
        small = self.app.fonts.small
        screen.blit(small.render(f'{self.pose.title}: the pose it is drawn in, and the frame', True, TEXT_DIM),
                    (rect.x + 4, rect.y - 20))
        self.checker.draw(screen, rect)
        items = self.compared(rect.size)
        column = rect.w / len(items)
        ground = rect.bottom - 30
        for index, (label, image) in enumerate(items):
            centre = int(rect.x + column * (index + 0.5))
            if image:
                screen.blit(image, image.get_rect(midbottom=(centre, ground)))
            else:
                text = small.render('not drawn', True, CHECKER_TEXT)
                screen.blit(text, text.get_rect(midbottom=(centre, ground)))
            text = small.render(label, True, CHECKER_TEXT)
            screen.blit(text, text.get_rect(midtop=(centre, ground + 6)))

    def animation(self, group, size):
        """[(image, seconds)] of the walk or the grazing as the game plays it, the frames there are."""
        key = (group, size)
        if key not in self.play_cache:
            durations = [EAT_FRAME_S[(p.number - 1) % len(EAT_FRAME_S)] if group == 'eat' else WALK_FRAME_S
                         for p in poses_of(group)]
            sprites = [(self.animal.sprite(p.key), d) for p, d in zip(poses_of(group), durations)]
            sprites = [(s, d) for s, d in sprites if not is_blank(s)]
            frames = []
            if sprites:
                # Whole canvases at one scale, as the game scales them: the frames keep their places
                w, h = sprites[0][0].get_size()
                factor = min((size[0] - 20) / w, (size[1] - 40) / h)
                for sprite, seconds in sprites:
                    frames.append((pygame.transform.smoothscale(
                        sprite, (max(1, round(sprite.get_width() * factor)),
                                 max(1, round(sprite.get_height() * factor)))), seconds))
            self.play_cache[key] = frames
        return self.play_cache[key]

    def draw_play(self, screen, rect):
        small = self.app.fonts.small
        screen.blit(small.render('As the game plays them', True, TEXT_DIM), (rect.x + 4, rect.y - 20))
        half = (rect.w - PANEL_GAP) // 2
        now = pygame.time.get_ticks() / 1000
        for index, (group, title) in enumerate((('move', 'Walk'), ('eat', 'Grazing'))):
            box = pygame.Rect(rect.x + index * (half + PANEL_GAP), rect.y, half, rect.h)
            self.checker.draw(screen, box)
            frames = self.animation(group, (box.w, box.h))
            if frames:
                total = sum(seconds for _, seconds in frames)
                t = now % total
                for image, seconds in frames:
                    if t < seconds:
                        break
                    t -= seconds
                screen.blit(image, image.get_rect(midbottom=(box.centerx, box.bottom - 30)))
                caption = f'{title}: {len(frames)} of {len(poses_of(group))} frames'
            else:
                caption = f'{title}: no frames yet'
            text = small.render(caption, True, CHECKER_TEXT)
            screen.blit(text, text.get_rect(midbottom=(box.centerx, box.bottom - 6)))

    def draw_sheet(self, screen, rect, mouse):
        app = self.app
        fonts = app.fonts
        sheet = self.sheet
        draw_panel(screen, fonts, rect, f'Sheet for {self.pose.title}' if sheet else f'No sheet for {self.pose.title}')
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
            if self.sheet_cache is None or self.sheet_cache[0] != area.size:
                self.sheet_cache = (area.size, fitted(sheet.surface, area.size, CARD_BG))
            screen.blit(self.sheet_cache[1], area)
        else:
            text = fonts.small.render(fit_text(fonts.small, f'Not yet: {self.sheet_error}', area.w), True, TEXT_DIM)
            screen.blit(text, text.get_rect(midtop=(area.centerx, area.y + 20)))

        ready = sheet is not None
        for button in (self.copy_image_button, self.copy_prompt_button, self.paste_button):
            button.enabled = ready and win_clipboard.AVAILABLE
        self.open_button.enabled = ready
        self.web_button.enabled = ready and not app.web_queue_busy()
        if app.web_queue_busy():
            self.web_missing_button.label = f'Stop browser queue ({app.web_queue_left()} left)'
            self.web_missing_button.enabled = bool(app.web_queue)
        else:
            missing = len(self.missing_poses())
            self.web_missing_button.label = f'Send missing in browser ({missing})'
            self.web_missing_button.enabled = bool(missing)
        self.send_button.enabled = ready and not app.busy() and not gemini_client.SDK_ERROR
        tries = app.settings.tries
        self.send_button.label = 'Sending ...' if app.busy() else (
            f'Send to Gemini ({tries}x)' if tries > 1 else 'Send to Gemini')
        path = self.animal.sprite_path(self.pose.key)
        self.gimp_button.enabled = bool(self.gimp and path.is_file())
        self.gimp_button.label = 'Edit in GIMP' if self.gimp else 'Edit in GIMP (GIMP not found)'
        for row in rows:
            for button in row:
                button.draw(screen, fonts.font, mouse)

    # --- input --------------------------------------------------------------

    def click(self, pos):
        field = self.description_field
        if field.rect.collidepoint(pos):
            field.focus(True)
            return
        if field.focused and self.commit_fields():
            self.refresh()
        field.focus(False)
        for button, action in self.actions:
            if button.hit(pos):
                action()
                return
        for row, pose in self.frame_rows:
            if row.collidepoint(pos):
                self.select(pose)
                return

    def captures_keys(self):
        return self.description_field.focused

    def text_input(self, text):
        if self.description_field.focused:
            self.description_field.type(text)

    def key(self, event):
        field = self.description_field
        if field.focused:
            if field.key(event) == 'done' and self.commit_fields():
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
            self.select(POSES[(POSES.index(self.pose) + step) % len(POSES)])
        elif event.key == pygame.K_r:
            self.open_answers()
        elif event.key == pygame.K_g:
            self.edit_in_gimp()

    def back(self):
        self.commit_fields()
        self.app.close_animal()
        return True
