"""Screen 2: the walk (or run) frames of one figure, direction by direction.

Left the directions and the walk as the game plays it, in the middle the
frames of the chosen direction, right the chosen frame's sheet with the
buttons that get an answer for it. Above a frame's sheet, Free / Locked
chooses whether the figure's own head is put into the red frame (H).
"""

import time
from pathlib import Path

import pygame

import gemini_client
import pose_review
import win_clipboard
from answers import AnswerError, ask_open_file, clipboard_answer, store_web_answer
from chibi import ghost_path
from even_colours import NUMPY_ERROR, even_out
from export_dialog import GIF, ExportDialog
from frame_picker import FramePicker
from gif_export import PIL_ERROR, gif_bytes
from gimp import ENV_GIMP, FileWatcher, find_gimp, open_in_gimp
from images import fitted, is_blank, load_frame, pixel_fit, save_copy, smooth_fit, trim
from sheets import SHEET_ERRORS, can_make_standing, lock_head_possible, write_sheets, write_standing_sheet
from theme import (
    BG, CARD_BG, CARD_HOVER, CARD_SELECTED, DONE_COLOR, ERROR_COLOR, PANEL_GAP, STATUS_COLORS, TEXT,
    TEXT_DIM,
)
from view import View
from video_export import AV_ERROR, write_video
from walk import find_direction, is_optional, partner_of, standing_pose
from widgets import PANEL_TITLE, Button, Card, CardGrid, Checker, Comparison, draw_chips, draw_panel, fit_text

# Layout
DIR_PANEL_W = 230
DIR_ROW = 34
SHEET_PANEL_MIN_W = 320
SHEET_PANEL_SHARE = 0.3
FRAME_CARD_SIZE = (172, 296)
FRAME_THUMB_SIZE = (150, 232)
BUTTON_H = 40
BUTTON_GAP = 10
PREVIEW_FRAME_MS = 140
PREVIEW_MIN_H = 60
PREVIEW_MAX_ZOOM = 2.0
COMPARE_SHARE = 0.36     # share of the sheet panel the comparison takes, when shown
HEAD_CHOICES = ((False, 'Free'), (True, 'Locked'))   # the head in the red frame: the model's, or the figure's own

COLOUR_BACKUPS = 'colour_backups'   # under the output folder: frames as they were before evening out

STANDING = 'standing'    # the key of the standing sprite's card, beside the frames' indices
CHECKER_TEXT = (40, 40, 40)   # readable on the light checkerboard


class FramesView(View):
    def __init__(self, app, direction):
        super().__init__(app)
        self.npc = app.npc
        self.store = app.store
        self.direction = direction
        self.sheets = []
        self.standing_sheet = None    # the sheet for the standing sprite, where one can be made
        self.current = 0              # index into self.sheets, or STANDING
        self.grid = CardGrid()
        self.preview = []             # the direction's walk as the game plays it
        self.preview_note = ''
        self.comparison = None        # accepted frame vs. goal, when there is one
        self.dir_rows = []            # [(rect, direction)] as last drawn
        self.motion_chips = []        # [(rect, motion)] as last drawn, for the player
        self.head_chips = []          # [(rect, locked)] as last drawn, above a frame's sheet
        self.preview_checker = Checker()
        self.standing_checker = Checker()
        self.gimp = find_gimp()
        self.watcher = FileWatcher()
        self.colour_undo = None       # (direction, [(frame, backup, mtime)]) of the last evening out

        # Footer
        self.review_button = Button('Review', w=140)
        self.mirror_all_button = Button('Mirror missing', w=290)
        self.redo_first_button = Button('Redo first sprite', w=180)
        self.missing_button = Button('Send missing', w=220)
        # Sheet panel, in rows of two
        self.copy_image_button = Button('Copy image', h=BUTTON_H)
        self.copy_prompt_button = Button('Copy prompt', h=BUTTON_H)
        self.paste_button = Button('Paste answer', h=BUTTON_H)
        self.open_button = Button('Open image', h=BUTTON_H)
        self.send_button = Button('Send to Gemini', h=BUTTON_H)
        self.from_frame_button = Button('From other frame', h=BUTTON_H)
        self.gimp_button = Button('Edit in GIMP', h=BUTTON_H)
        # Under the animation in the directions panel
        self.export_button = Button('Export...', h=BUTTON_H)
        self.colours_button = Button('Even out colours', h=BUTTON_H)
        self.sheet_button_rows = ((self.copy_image_button, self.copy_prompt_button),
                                  (self.paste_button, self.open_button),
                                  (self.send_button, self.from_frame_button),
                                  (self.gimp_button,))
        self.actions = ((self.review_button, app.open_review),
                        (self.missing_button, self.send_missing),
                        (self.mirror_all_button, self.mirror_missing),
                        (self.redo_first_button, app.redo_first_sprite),
                        (self.colours_button, self.even_out_or_undo),
                        (self.from_frame_button, self.open_picker),
                        (self.gimp_button, self.edit_in_gimp),
                        (self.copy_image_button, self.copy_image),
                        (self.copy_prompt_button, self.copy_prompt),
                        (self.paste_button, self.paste_answer),
                        (self.open_button, self.open_answer),
                        (self.send_button, self.send_current),
                        (self.export_button, self.open_export))
        self.select_direction(direction)

    # --- state ------------------------------------------------------------

    def current_sheet(self):
        """The chosen card's sheet; None without one (no sheets, or the front standing sprite)."""
        if self.current == STANDING:
            return self.standing_sheet
        return self.sheets[self.current] if self.sheets else None

    def standing_path(self):
        """The direction's standing sprite, drawn or not; None for a diagonal."""
        pose = standing_pose(self.direction)
        return self.npc.sprite_path(pose) if pose else None

    def current_path(self):
        """Where the chosen frame or standing sprite is saved in the game, done or not."""
        if self.current == STANDING:
            return self.standing_path()
        sheet = self.current_sheet()
        return self.npc.sprite_path(sheet.pose) if sheet else None

    def watched_paths(self):
        """The files the view shows: the frames and the standing sprite."""
        paths = [self.npc.sprite_path(s.pose) for s in self.sheets]
        return paths + [self.standing_path()] if self.standing_path() else paths

    def partner(self):
        """The direction whose frames are this one's mirror image, or None."""
        return partner_of(self.direction)

    def count(self):
        return self.app.counts[self.direction]

    def directions(self):
        """The directions of the motion shown."""
        return self.npc.directions(self.direction.motion)

    def select_motion(self, motion):
        """Show the same direction of another motion, keeping the chosen frame."""
        if motion != self.direction.motion:
            self.select_direction(find_direction(motion, self.direction.key), self.current)

    def next_motion(self):
        motions = self.npc.motions
        self.select_motion(motions[(motions.index(self.direction.motion) + 1) % len(motions)])

    def select_direction(self, direction, current=0):
        """Rebuild the direction's sheets from the base files and show them.

        Args:
            direction: The Direction.
            current: The card to choose: a frame's index, or STANDING.
        """
        self.direction = direction
        self.app.last_direction = direction
        try:
            self.sheets = write_sheets(self.npc, direction, lock_head=self.app.settings.lock_head)
        except SHEET_ERRORS as exc:
            self.sheets = []
            self.app.set_status(f'Cannot build the {direction.title} sheets: {exc}', error=True)
        self.standing_sheet = None
        if can_make_standing(direction):
            try:
                self.standing_sheet = write_standing_sheet(self.npc, direction)
            except SHEET_ERRORS as exc:
                self.app.set_status(f'Cannot build the standing sheet: {exc}', error=True)
        if current == STANDING and standing_pose(direction):
            self.current = STANDING
        else:
            index = current if isinstance(current, int) else 0
            self.current = min(index, max(0, len(self.sheets) - 1))
        self.grid.scroll = 0
        self.app.place_footer()  # the mirror button comes and goes with the direction
        self.refresh()
        if self.sheets and self.sheets[0].auto_ghost and not self.app.status_error:
            self.app.set_status(f'Ghost made on the fly - draw {ghost_path(direction).name} '
                                'for a cleaner one')

    def select_frame(self, key):
        """Choose a card: a frame's index, or STANDING."""
        self.current = key
        if not self.rebuild_current():
            self.build_comparison()  # the front standing sprite: nothing to rebuild

    def rebuild_current(self):
        """Rebuild the chosen card's sheet, so it matches the base files on disk."""
        sheet = self.current_sheet()
        if not sheet:
            return None
        try:
            if sheet.standing:
                fresh = self.standing_sheet = write_standing_sheet(self.npc, sheet.direction)
            else:
                fresh = self.sheets[self.current] = write_sheets(self.npc, sheet.direction, [sheet.frame],
                                                                 self.app.settings.lock_head)[0]
        except SHEET_ERRORS as exc:
            self.app.set_status(f'Cannot rebuild the sheet: {exc}', error=True)
            return sheet
        self.build_frame_cards()
        return fresh

    def can_lock_head(self):
        """Whether the chosen card's sheet can have the figure's head locked into it."""
        sheet = self.current_sheet()
        return bool(sheet) and not sheet.standing and lock_head_possible(self.npc, self.direction)

    def set_head_lock(self, locked):
        """Free or lock the head in every walk and run sheet, and rebuild this direction's."""
        app = self.app
        if locked == app.settings.lock_head:
            return
        app.settings = app.settings.with_values(lock_head=locked)
        app.settings.save()
        self.select_direction(self.direction, self.current)
        app.set_status('Head locked: the sheets carry the figure\'s own head' if locked else
                       'Head free: the model draws the head over the ghost')

    def refresh(self):
        """Cards, comparison and preview, after answers or frames on disk changed."""
        self.build_frame_cards()
        self.preview, self.preview_note = self.npc.game_frames(self.direction, self.count())
        # What was just read is up to date; only later edits are news.
        self.watcher.reset()

    def frame_note(self, pose):
        """(text, colour) of a frame's state."""
        if self.npc.has(pose):
            return 'done', STATUS_COLORS[pose_review.ACCEPTED]
        note = self.store.pose_note(pose)
        if note == 'rejected':
            return note, ERROR_COLOR
        return note, STATUS_COLORS[pose_review.PENDING]

    def standing_card(self):
        """The card of the direction's standing sprite, or None for a diagonal.

        It shows the sprite once there is one, until then the sheet to make it from.
        """
        path = self.standing_path()
        if not path:
            return None
        sprite = load_frame(path)
        if self.standing_sheet:
            thumb = self.sheet_thumb(self.standing_sheet, sprite)
        elif not is_blank(sprite):
            thumb = fitted(trim(sprite), FRAME_THUMB_SIZE)  # the front one: the reference itself
        else:
            thumb = fitted(pygame.Surface((1, 1), pygame.SRCALPHA), FRAME_THUMB_SIZE)
        note, color = self.frame_note(standing_pose(self.direction))
        if not note:
            note, color = 'not drawn', TEXT_DIM
        return Card(STANDING, f'Standing  ({standing_pose(self.direction)})', thumb,
                    note, note_color=color, size=FRAME_CARD_SIZE)

    @staticmethod
    def sheet_thumb(sheet, sprite):
        """A card's picture: the sheet, with the accepted sprite in place of the ghost once there is one."""
        surface = sheet.surface if is_blank(sprite) else sheet.with_result(sprite)
        return fitted(surface, FRAME_THUMB_SIZE)

    def build_frame_cards(self):
        standing = self.standing_card()
        cards = [standing] if standing else []
        for index, sheet in enumerate(self.sheets):
            note, color = self.frame_note(sheet.pose)
            sprite = load_frame(self.npc.sprite_path(sheet.pose))
            cards.append(Card(
                index, f'Frame {sheet.frame}  ({sheet.pose})', self.sheet_thumb(sheet, sprite),
                note, note_color=color, size=FRAME_CARD_SIZE))
        self.grid.cards = cards
        self.build_comparison()

    def build_comparison(self):
        """The accepted frame next to its goal, if the chosen frame is done."""
        sheet = self.current_sheet()
        sprite = load_frame(self.current_path()) if sheet else None
        self.comparison = None if is_blank(sprite) else Comparison(sheet.ghost, sprite)

    def missing_sheets(self):
        return [s for s in self.sheets if not self.npc.has(s.pose)]

    def mirrorable_missing(self):
        """Frames this direction lacks and its partner has."""
        return [s.frame for s in self.missing_sheets()
                if self.npc.mirror_source(self.direction, s.frame)]

    # --- the web view: clipboard, files -----------------------------------

    def copy_image(self):
        sheet = self.rebuild_current()
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
        sheet = self.rebuild_current()
        if not sheet:
            return
        try:
            win_clipboard.copy_text(sheet.prompt)
        except win_clipboard.ClipboardError as exc:
            self.app.set_status(str(exc), error=True)
            return
        self.app.set_status(f'Prompt of {sheet.pose} copied')
        self.app.toast.show('Prompt copied')

    def paste_answer(self):
        """Take the image on the clipboard as the answer for the chosen frame."""
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
        """Store an answer from the web view and open it for review.

        Raises:
            AnswerError: If the source is not an image.
        """
        sheet = self.current_sheet()
        if not sheet:
            return
        entry = store_web_answer(self.npc, self.store, sheet, source, kind)
        self.build_frame_cards()
        self.app.open_detail(entry, self)

    # --- the API ----------------------------------------------------------

    def send_current(self):
        sheet = self.rebuild_current()
        if sheet:
            self.app.send([sheet])

    def send_missing(self):
        self.select_direction(self.direction, self.current)
        self.app.send(self.missing_sheets())

    # --- frames from frames -----------------------------------------------

    def save_frame(self, source, target, mirror):
        """Save one frame as another, flipped if asked; False if that failed."""
        try:
            save_copy(source, target, mirror)
        except (pygame.error, OSError) as exc:
            self.app.set_status(f'Could not copy {source.name}: {exc}', error=True)
            return False
        return True

    def mirror_missing(self):
        """Save the partner's frames, flipped, for every frame this direction lacks."""
        written = 0
        for frame in self.mirrorable_missing():
            source = self.npc.mirror_source(self.direction, frame)
            if not self.save_frame(source, self.npc.frame_path(self.direction, frame), mirror=True):
                break
            written += 1
        self.refresh()
        if written:
            partner = self.partner().label.lower()
            self.app.set_status(f'Mirrored {written} frame(s) from {partner}')
            self.app.toast.show(f'{written} frame(s) mirrored from {partner}')

    def open_picker(self):
        """Choose another frame of the NPC to make the chosen one from."""
        sheet = self.current_sheet()
        if sheet:
            self.app.dialog = FramePicker(self.npc, sheet, self.app.counts, self.app.fonts,
                                          self.copy_frame)

    def copy_frame(self, source, source_label, mirror):
        """Save another of the NPC's frames as the chosen one."""
        sheet, target = self.current_sheet(), self.current_path()
        replaced = target.is_file()
        if not self.save_frame(source, target, mirror):
            return
        self.refresh()
        how = 'mirrored' if mirror else 'copied'
        verb = 'Replaced' if replaced else 'Saved'
        self.app.set_status(f'{verb} {target.name}, {how} from {source_label}')
        self.app.toast.show(f'{sheet.name} {how} from {source_label}')

    # --- colours -----------------------------------------------------------

    def colour_reference(self):
        """The sprite the direction's frames are evened out against: its standing sprite, else the front one."""
        return self.npc.sprite_path(self.npc.base_for(self.direction))

    def done_frame_paths(self):
        return [p for p in (self.npc.sprite_path(s.pose) for s in self.sheets) if p.is_file()]

    def can_undo_colours(self):
        """True while the last evening out was of this direction and its frames are as it left them."""
        if not self.colour_undo or self.colour_undo[0] != self.direction:
            return False
        return all(path.is_file() and path.stat().st_mtime == mtime and backup.is_file()
                   for path, backup, mtime in self.colour_undo[1])

    def even_out_or_undo(self):
        if self.can_undo_colours():
            self.undo_colours()
        else:
            self.even_out_colours()

    def even_out_colours(self):
        """Pull the colours of the direction's frames onto its standing sprite, so the walk does not flicker."""
        frames, reference = self.done_frame_paths(), self.colour_reference()
        if not frames or not reference.is_file():
            return
        stamp = time.strftime('%Y%m%d_%H%M%S')
        backup_dir = self.npc.out_dir / COLOUR_BACKUPS / f'{self.direction.motion.key}_{self.direction.key}_{stamp}'
        try:
            changes = even_out(reference, frames, backup_dir)
        except (RuntimeError, ValueError, pygame.error, OSError) as exc:
            self.app.set_status(f'Cannot even out the colours: {exc}', error=True)
            return
        self.colour_undo = (self.direction, [(c.path, backup_dir / c.path.name, c.path.stat().st_mtime)
                                             for c in changes])
        self.refresh()
        mean = sum(c.mean for c in changes) / len(changes)
        worst = max(changes, key=lambda c: c.mean)
        self.app.set_status(f'Evened out {len(changes)} frame(s) against {reference.name}: mean change '
                            f'{mean:.1f}, most {worst.path.name} ({worst.mean:.1f}) - click again to undo')
        self.app.toast.show(f'Colours of {len(changes)} frame(s) evened out')

    def undo_colours(self):
        """Put the frames back as they were before the last evening out."""
        _, saved = self.colour_undo
        for path, backup, _ in saved:
            if not self.save_frame(backup, path, mirror=False):
                return
        self.colour_undo = None
        self.refresh()
        self.app.set_status(f'Colours of {len(saved)} frame(s) put back')
        self.app.toast.show('Colours put back')

    # --- sharing ----------------------------------------------------------

    def export_path(self, suffix):
        """Where the direction's animation is exported: <prefix>_<direction>_<motion><suffix>."""
        return self.npc.out_dir / f'{self.npc.prefix}_{self.direction.key}_{self.direction.motion.key}{suffix}'

    def open_export(self):
        """Ask whether to export the animation as GIF or as video."""
        if self.preview:
            self.app.dialog = ExportDialog(self.app.fonts, self.export, PIL_ERROR, AV_ERROR)

    def export(self, choice):
        """Save the animation as the game plays it as a GIF or an MP4 and put the file on the clipboard."""
        kind = 'GIF' if choice == GIF else 'video'
        path = self.export_path('.gif' if choice == GIF else '.mp4').resolve()
        gif = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            if choice == GIF:
                gif = gif_bytes(self.preview)
                path.write_bytes(gif)
            else:
                write_video(self.preview, path)
        except Exception as exc:  # noqa: BLE001 - Pillow and PyAV raise their own errors
            self.app.set_status(f'Cannot make the {kind}: {exc}', error=True)
            return
        try:
            win_clipboard.copy_file(path, gif)
        except (OSError, win_clipboard.ClipboardError) as exc:
            self.app.set_status(f'{path.name} saved, but cannot copy it: {exc}', error=True)
            return
        self.app.set_status(f'{path.name} saved and copied - paste it wherever it should go')
        self.app.toast.show(f'{kind} copied')

    # --- editing by hand --------------------------------------------------

    def edit_in_gimp(self):
        """Open the chosen frame in GIMP; tick() picks up the saved result."""
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
        """Refresh when a frame was changed outside the tool, e.g. in GIMP."""
        changed = self.watcher.changed(self.watched_paths())
        if changed:
            self.refresh()
            self.app.set_status(f'Updated from disk: {", ".join(p.name for p in changed)}')

    # --- layout -----------------------------------------------------------

    def areas(self):
        """(directions, cards, sheet) panels."""
        body = self.app.body()
        sheet_w = max(SHEET_PANEL_MIN_W, int(body.w * SHEET_PANEL_SHARE))
        dirs = pygame.Rect(body.x, body.y, DIR_PANEL_W, body.h)
        sheet = pygame.Rect(body.right - sheet_w, body.y, sheet_w, body.h)
        cards = pygame.Rect(dirs.right + PANEL_GAP, body.y,
                            sheet.x - dirs.right - 2 * PANEL_GAP, body.h)
        return dirs, cards, sheet

    def place_sheet_buttons(self, sheet_rect):
        """Put the buttons along the foot of the sheet panel; returns the room left above them."""
        inner = sheet_rect.inflate(-20, -20)
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
        top_of_buttons = rows[0][0].rect.y
        return pygame.Rect(inner.x, inner.y, inner.w, top_of_buttons - BUTTON_GAP - inner.y)

    # --- header and footer ------------------------------------------------

    def header(self):
        motions = ' / '.join(m.label for m in self.npc.motions)
        switch = f'Tab = {motions.lower()}. ' if len(self.npc.motions) > 1 else ''
        return (f'2. {motions} frames for "{self.npc.name}"',
                f'{switch}Up/Down = direction, Left/Right = frame. Ctrl+C = copy sheet, Ctrl+Shift+C = '
                'copy prompt, Ctrl+V or drop a file = answer from the web view, H = lock head, E = even out colours, '
                'S = settings.')

    def footer(self):
        app = self.app
        mirror = (self.mirror_all_button,) if self.partner() else ()
        redo = () if self.npc.is_player else (self.redo_first_button,)
        return ((app.back_button, app.folder_button, self.review_button) + mirror,
                redo + (app.settings_button, self.missing_button))

    def update_footer(self):
        app = self.app
        waiting = len(self.store.pending())
        self.review_button.label = f'Review ({waiting})' if waiting else 'Review'
        self.review_button.enabled = bool(self.store.entries)
        partner = self.partner()
        if partner:
            mirrorable = len(self.mirrorable_missing())
            self.mirror_all_button.enabled = bool(mirrorable)
            self.mirror_all_button.label = f'Mirror missing from {partner.label.lower()} ({mirrorable})'
        missing = len(self.missing_sheets()) * app.settings.tries
        self.missing_button.label = 'Sending ...' if app.busy() else f'Send missing ({missing})'
        self.missing_button.enabled = bool(missing) and not app.busy() and not gemini_client.SDK_ERROR

    # --- drawing ----------------------------------------------------------

    def draw(self, screen, mouse):
        dirs, cards, sheet = self.areas()
        self.draw_directions(screen, dirs, mouse)
        screen.blit(self.app.fonts.small.render(
            f'Frames of the {self.direction.title}  -  rebuilt from the base files on every click',
            True, TEXT_DIM), (cards.x + 4, cards.y - 20))
        self.grid.layout(cards)
        self.grid.draw(screen, self.app.fonts, mouse, selected_key=self.current)
        self.draw_sheet(screen, sheet, mouse)

    def direction_note(self, direction):
        """(text, colour) beside a direction: frames done, answers waiting."""
        count = self.app.counts[direction]
        done = self.npc.done(direction, count)
        waiting = sum(self.npc.parse_pose(e.pose)[0] == direction for e in self.store.pending())
        if done:
            note, color = f'{done}/{count}', STATUS_COLORS[pose_review.ACCEPTED]
        elif is_optional(direction):
            note, color = 'optional', TEXT_DIM
        else:
            note, color = f'0/{count}', TEXT_DIM
        if waiting:
            note, color = f'{note}  +{waiting}', DONE_COLOR
        return note, color

    def draw_directions(self, screen, rect, mouse):
        small = self.app.fonts.small
        draw_panel(screen, self.app.fonts, rect, 'Direction')
        self.dir_rows = []
        y = rect.y + 8
        self.motion_chips = []
        if len(self.npc.motions) > 1:
            self.motion_chips, bottom = draw_chips(
                screen, small, self.npc.motions, lambda m: m.label, self.direction.motion,
                rect.x + 8, y, rect.w - 16, mouse)
            y = bottom + 8
        for direction in self.directions():
            row = pygame.Rect(rect.x + 8, y, rect.w - 16, DIR_ROW - 4)
            y += DIR_ROW
            if direction == self.direction:
                color = CARD_SELECTED
            elif row.collidepoint(mouse):
                color = CARD_HOVER
            else:
                color = BG
            pygame.draw.rect(screen, color, row, border_radius=5)
            label = small.render(direction.label, True, TEXT)
            screen.blit(label, label.get_rect(midleft=(row.x + 10, row.centery)))
            note, note_color = self.direction_note(direction)
            text = small.render(note, True, note_color)
            screen.blit(text, text.get_rect(midright=(row.right - 10, row.centery)))
            self.dir_rows.append((row, direction))

        box = pygame.Rect(rect.x + 8, y + PANEL_TITLE, rect.w - 16,
                          rect.bottom - 8 - y - PANEL_TITLE - 2 * (BUTTON_H + BUTTON_GAP))
        self.export_button.enabled = self.colours_button.enabled = False
        if box.h >= PREVIEW_MIN_H:
            self.draw_preview(screen, box)
            self.draw_export_button(screen, box, mouse)
            self.draw_colours_button(screen, box, mouse)

    def draw_preview(self, screen, box):
        """The frames the NPC already has, playing in a loop."""
        small = self.app.fonts.small
        title = small.render(fit_text(small, f'In the game: {self.preview_note}', box.w), True, TEXT_DIM)
        screen.blit(title, (box.x, box.y - 20))
        self.preview_checker.draw(screen, box)
        if self.preview:
            frame = self.preview[pygame.time.get_ticks() // PREVIEW_FRAME_MS % len(self.preview)]
            image = smooth_fit(frame, (box.w - 20, box.h - 20), PREVIEW_MAX_ZOOM)
            screen.blit(image, image.get_rect(midbottom=(box.centerx, box.bottom - 10)))

    def draw_export_button(self, screen, box, mouse):
        """'Export...' under the animation."""
        self.export_button.rect = pygame.Rect(box.x, box.bottom + BUTTON_GAP, box.w, BUTTON_H)
        self.export_button.enabled = (bool(self.preview) and win_clipboard.AVAILABLE
                                      and not (PIL_ERROR and AV_ERROR))
        self.export_button.draw(screen, self.app.fonts.font, mouse)

    def draw_colours_button(self, screen, box, mouse):
        """'Even out colours' under 'Export...', or its undo right after."""
        self.colours_button.rect = self.export_button.rect.move(0, BUTTON_H + BUTTON_GAP)
        if self.can_undo_colours():
            self.colours_button.label, self.colours_button.enabled = 'Undo even out', True
        else:
            self.colours_button.label = 'Even out (needs numpy)' if NUMPY_ERROR else 'Even out colours'
            self.colours_button.enabled = (not NUMPY_ERROR and bool(self.done_frame_paths())
                                           and self.colour_reference().is_file())
        self.colours_button.draw(screen, self.app.fonts.font, mouse)

    def draw_sheet(self, screen, rect, mouse):
        app = self.app
        sheet = self.current_sheet()
        if sheet:
            title = f'Sheet for {sheet.pose}'
        elif self.current == STANDING:
            title = f'Standing sprite {self.standing_path().name}  -  the reference for the others'
        else:
            title = 'Sheet'
        draw_panel(screen, app.fonts, rect, title)
        area = self.place_sheet_buttons(rect)
        if sheet and not sheet.standing:
            area = self.draw_head_choice(screen, area, mouse)
        if not sheet and self.current == STANDING:
            self.draw_standing(screen, area)
        elif sheet and self.comparison:
            compare_h = int(area.h * COMPARE_SHARE)
            compare_area = pygame.Rect(area.x, area.bottom - compare_h, area.w, compare_h)
            area.h = compare_area.y - area.y - BUTTON_GAP
            self.comparison.draw(screen, app.fonts, compare_area)
        if sheet:
            screen.blit(fitted(sheet.surface, area.size, CARD_BG), area)

        ready = bool(sheet)
        for button in (self.copy_image_button, self.copy_prompt_button, self.paste_button):
            button.enabled = ready and win_clipboard.AVAILABLE
        self.open_button.enabled = ready
        self.from_frame_button.enabled = ready
        self.send_button.enabled = ready and not app.busy() and not gemini_client.SDK_ERROR
        tries = app.settings.tries
        self.send_button.label = 'Sending ...' if app.busy() else (
            f'Send to Gemini ({tries}x)' if tries > 1 else 'Send to Gemini')
        path = self.current_path()
        self.gimp_button.enabled = bool(self.gimp and path and path.is_file())
        self.gimp_button.label = 'Edit in GIMP' if self.gimp else 'Edit in GIMP (GIMP not found)'
        for row in self.sheet_button_rows:
            for button in row:
                button.draw(screen, app.fonts.font, mouse)

    def draw_head_choice(self, screen, area, mouse):
        """Head: Free / Locked at the top of the sheet area; returns the room left under it."""
        small = self.app.fonts.small
        label = small.render('Head:', True, TEXT_DIM)
        screen.blit(label, (area.x, area.y + 4))
        x = area.x + label.get_width() + 10
        self.head_chips = []
        if self.can_lock_head():
            self.head_chips, bottom = draw_chips(screen, small, [locked for locked, _ in HEAD_CHOICES],
                                                 dict(HEAD_CHOICES).get, self.app.settings.lock_head,
                                                 x, area.y, area.right - x, mouse)
        else:
            note = small.render(fit_text(small, 'free - only for up, down, left, right with their standing '
                                         'sprite', area.right - x), True, TEXT_DIM)
            screen.blit(note, (x, area.y + 4))
            bottom = area.y + note.get_height() + 8
        top = bottom + BUTTON_GAP
        return pygame.Rect(area.x, top, area.w, area.bottom - top)

    def draw_standing(self, screen, area):
        """The direction's standing sprite, large, on a checkerboard."""
        self.standing_checker.draw(screen, area)
        sprite = load_frame(self.standing_path())
        if is_blank(sprite):
            small = self.app.fonts.small
            text = small.render('Not drawn yet', True, CHECKER_TEXT)
            screen.blit(text, text.get_rect(center=area.center))
            return
        image = pixel_fit(trim(sprite), (area.w - 20, area.h - 20))
        screen.blit(image, image.get_rect(midbottom=(area.centerx, area.bottom - 10)))

    # --- input ------------------------------------------------------------

    def click(self, pos):
        for button, action in self.actions:
            if button is self.mirror_all_button and not self.partner():
                continue  # not shown in this direction
            if button is self.redo_first_button and self.npc.is_player:
                continue  # the player is the reference everyone is drawn against
            if button.hit(pos):
                action()
                return
        for chip, motion in self.motion_chips:
            if chip.collidepoint(pos):
                self.select_motion(motion)
                return
        for chip, locked in self.head_chips:
            if chip.collidepoint(pos):
                self.set_head_lock(locked)
                return
        for row, direction in self.dir_rows:
            if row.collidepoint(pos):
                self.select_direction(direction)
                return
        card = self.grid.card_at(pos)
        if card:
            self.select_frame(card.key)

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
        elif event.key in (pygame.K_LEFT, pygame.K_RIGHT) and self.grid.cards:
            step = 1 if event.key == pygame.K_RIGHT else -1
            keys = [card.key for card in self.grid.cards]
            index = keys.index(self.current) if self.current in keys else 0
            self.select_frame(keys[(index + step) % len(keys)])
        elif event.key in (pygame.K_UP, pygame.K_DOWN):
            step = 1 if event.key == pygame.K_DOWN else -1
            directions = self.directions()
            index = directions.index(self.direction)
            self.select_direction(directions[(index + step) % len(directions)])
        elif event.key == pygame.K_TAB and len(self.npc.motions) > 1:
            self.next_motion()
        elif event.key == pygame.K_r and self.store.entries:
            self.app.open_review()
        elif event.key == pygame.K_m:
            self.open_picker()
        elif event.key == pygame.K_g:
            self.edit_in_gimp()
        elif event.key == pygame.K_e:
            self.even_out_or_undo()
        elif event.key == pygame.K_h and self.can_lock_head():
            self.set_head_lock(not self.app.settings.lock_head)
        elif event.key == pygame.K_f and not self.npc.is_player:
            self.app.redo_first_sprite()

    def scroll_by(self, steps):
        self.grid.scroll_by(steps)

    def back(self):
        self.app.close_npc()
        return True
