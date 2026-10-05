"""Screen 2 of the plants and buildings: designing a new sprite before it goes to the model.

Left the split image as it will be sent: the example, and the red frame to
sketch the new sprite's shape in with the mouse, in as many colours as it
takes. With the brush the left button paints and the right rubs out, and
Shift+click goes on from where the last stroke ended in a straight line;
the line tool draws one straight line per drag (Shift keeps it to steps of
15 degrees); with the fill the left button floods a patch of one colour
(or of bare paper) and the right rubs that patch out. Alt+click takes up a
colour from the sketch. Under it the tool, brush size, undo and the ways to the model, as
for the humans: copy image and prompt for the web view, paste or open its
answer, or send to the API. Right the kind (the example's, to begin with),
an optional subcategory that goes into the prompt, and the colour in hand,
from the wheel or from the colours used last (keys 1 to 0).

Everything is saved in the job's folder as it changes, so a job can be left
and picked up again from the overview.
"""

import math
from pathlib import Path

import pygame

import gemini_client
import win_clipboard
from answers import AnswerError, ask_open_file, clipboard_answer, store_web_answer
from colour_wheel import ColourWheel
from sprite_job import colour_name, hex_colour, load_recent_colours, remember_colour
from theme import CARD_BG, DIALOG_BG, DIALOG_LINE, PANEL_GAP, TEXT, TEXT_DIM
from view import View
from widgets import Button, TextField, draw_chips, draw_panel, fit_text

PROPOSALS_PAD = 10       # inside the box of proposals under the subcategory field

CONTROLS_SHARE = 0.3     # of the body, for kind, subcategory and colour
CONTROLS_MIN_W = 330
BUTTON_H = 40
BUTTON_GAP = 10
# Brush radius, as a share of the cell
BRUSHES = (('XXS', 0.002), ('XS', 0.004), ('S', 0.007), ('M', 0.012), ('L', 0.025), ('XL', 0.05))
TOOLS = (('brush', 'Brush'), ('line', 'Line'), ('fill', 'Fill'))
SIZED_TOOLS = ('brush', 'line')
LINE_SNAP = 15              # degrees, the steps a line keeps to while Shift is held
SWATCH_H = 44
RECENT_SIZE = 30            # the quick picks of the colours used last
RECENT_GAP = 6
BRUSH_RING = (60, 60, 60)   # where the brush would paint, over the white cell
CURSOR_SWATCH = 12          # the colour in hand, beside the mouse over the cell


class DesignView(View):
    def __init__(self, app):
        super().__init__(app)
        self.job = app.npc
        self.wheel = ColourWheel(self.job.colour)
        self.field = TextField(self.job.subcategory, placeholder='e.g. oak, rosebush (optional)')
        self.tool = 'brush'
        self.brush = 'S'
        self.tool_chips = []
        self.brush_chips = []
        self.recent = load_recent_colours(self.job.domain)
        self.recent_chips = []        # [(rect, colour)]
        self.kind_chips = []
        self.proposal_chips = []      # [(rect, text)] while the subcategory field is typed in
        self.proposals_rect = None
        self.stroke = None             # (last point, colour or None to rub out) while the mouse paints
        self.line = None               # (start, end, colour) while a straight line is dragged
        self.last_point = None         # where the last stroke or line ended, for Shift+click
        self.display = None            # the sheet with the sketch, scaled into the panel
        self.display_rect = None
        self.dirty = True

        self.undo_button = Button('Undo', h=32, w=80)
        self.clear_button = Button('Clear', h=32, w=80)
        self.copy_image_button = Button('Copy image', h=BUTTON_H)
        self.copy_prompt_button = Button('Copy prompt', h=BUTTON_H)
        self.paste_button = Button('Paste answer', h=BUTTON_H)
        self.open_button = Button('Open image', h=BUTTON_H)
        self.send_button = Button('Send to Gemini', h=BUTTON_H)
        self.web_button = Button('Send in browser', h=BUTTON_H)
        self.send_buttons = (self.web_button, self.copy_image_button, self.copy_prompt_button, self.paste_button,
                             self.open_button, self.send_button)
        self.answers_button = Button('Answers', w=150)
        self.discard_button = Button('Discard', w=110)
        self.discard_armed = False
        self.actions = ((self.undo_button, self.undo),
                        (self.clear_button, self.clear),
                        (self.copy_image_button, self.copy_image),
                        (self.copy_prompt_button, self.copy_prompt),
                        (self.web_button, self.send_web),
                        (self.paste_button, self.paste_answer),
                        (self.open_button, self.open_answer),
                        (self.send_button, self.send),
                        (self.answers_button, self.app.open_answers),
                        (self.discard_button, self.discard))

    # --- state ------------------------------------------------------------

    def refresh(self):
        """Answers came in or files changed: only the answer count follows; the design is the job's."""
        self.dirty = True

    def changed(self):
        """The design changed: show it and keep it."""
        self.dirty = True
        try:
            self.job.save()
        except (pygame.error, OSError) as exc:
            self.app.set_status(f'Cannot save the job: {exc}', error=True)

    def unfinished(self):
        return '' if self.job.has_sketch() else f'Sketch the new {self.job.domain.noun} in the red frame first'

    def ready_sheet(self):
        """The split image written to disk as it is now; None (with the reason shown) if not ready."""
        reason = self.unfinished()
        if reason:
            self.app.set_status(reason, error=True)
            return None
        try:
            return self.job.write_sheet()
        except (pygame.error, OSError) as exc:
            self.app.set_status(f'Cannot write the split image: {exc}', error=True)
            return None

    # --- actions ----------------------------------------------------------

    def undo(self):
        if self.job.undo():
            self.changed()

    def clear(self):
        self.job.clear()
        self.last_point = None
        self.changed()

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

    def send_web(self):
        sheet = self.ready_sheet()
        if sheet:
            self.app.send_web(sheet, f'new {self.job.domain.noun}')

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
        sheet = self.ready_sheet()
        if not sheet:
            return
        entry = store_web_answer(self.job, self.app.store, sheet, source, kind)
        self.app.open_answers(entry)

    def send(self):
        sheet = self.ready_sheet()
        if sheet:
            self.app.send([sheet])

    def discard(self):
        """Delete the job and its answers; asks once more first."""
        if not self.discard_armed:
            self.discard_armed = True
            self.app.set_status(f'Click "Sure?" to delete this new {self.job.domain.noun} and all its answers',
                                error=True)
            return
        self.job.discard()
        self.app.close_job()
        self.app.set_status(f'Discarded {self.job.name}')

    # --- view -------------------------------------------------------------

    def header(self):
        return (f'2. New {self.job.domain.noun} from {self.job.example_label}',
                'Sketch the shape in the red frame (B brush, L line, F fill, left paints, right rubs out, '
                'Shift+click straight on, Alt+click takes a colour, 1-0 recent colours, Ctrl+Z undo), '
                'pick the type, then send it (Ctrl+W in the browser). Ctrl+V or drop a file = answer.')

    def footer(self):
        app = self.app
        return ((app.back_button, app.folder_button, self.discard_button),
                (app.settings_button, self.answers_button))

    def update_footer(self):
        count = len(self.app.store.entries)
        waiting = len(self.app.store.pending())
        self.answers_button.label = f'Answers ({waiting} new)' if waiting else f'Answers ({count})'
        self.answers_button.enabled = bool(count)
        self.discard_button.label = 'Sure?' if self.discard_armed else 'Discard'

    def areas(self):
        """(sheet panel, controls panel)."""
        body = self.app.body()
        controls_w = max(CONTROLS_MIN_W, int(body.w * CONTROLS_SHARE))
        controls = pygame.Rect(body.right - controls_w, body.y, controls_w, body.h)
        sheet = pygame.Rect(body.x, body.y, controls.x - PANEL_GAP - body.x, body.h)
        return sheet, controls

    def draw(self, screen, mouse):
        sheet_rect, controls_rect = self.areas()
        self.draw_sheet_panel(screen, sheet_rect, mouse)
        self.draw_controls(screen, controls_rect, mouse)

    def draw_sheet_panel(self, screen, rect, mouse):
        fonts = self.app.fonts
        draw_panel(screen, fonts, rect, f'Split image - sketch the new {self.job.domain.noun} in the red frame')
        inner = rect.inflate(-20, -20)

        # From the bottom: the ways to the model, then the brush row
        y = inner.bottom - BUTTON_H
        width = (inner.w - (len(self.send_buttons) - 1) * BUTTON_GAP) // len(self.send_buttons)
        for index, button in enumerate(self.send_buttons):
            button.rect = pygame.Rect(inner.x + index * (width + BUTTON_GAP), y, width, BUTTON_H)
        tools_y = y - BUTTON_GAP - 32
        tool_names = dict(TOOLS)
        self.tool_chips, _ = draw_chips(screen, fonts.small, list(tool_names), tool_names.get, self.tool,
                                        inner.x, tools_y, inner.w // 2, mouse)
        x = self.tool_chips[-1][0].right + 24
        label = fonts.small.render('Size', True, TEXT_DIM)
        screen.blit(label, (x, tools_y + 7))
        x += label.get_width() + 12
        self.brush_chips, _ = draw_chips(screen, fonts.small, [b for b, _ in BRUSHES], str,
                                         self.brush if self.tool in SIZED_TOOLS else None,
                                         x, tools_y, inner.w // 2, mouse)
        self.clear_button.rect.topright = (inner.right, tools_y)
        self.undo_button.rect.topright = (self.clear_button.rect.x - BUTTON_GAP, tools_y)

        area = pygame.Rect(inner.x, inner.y, inner.w, tools_y - BUTTON_GAP - inner.y)
        self.draw_sheet(screen, area, mouse)

        ready = not self.unfinished()
        for button in (self.copy_image_button, self.copy_prompt_button):
            button.enabled = ready and win_clipboard.AVAILABLE
        self.paste_button.enabled = ready and win_clipboard.AVAILABLE
        self.open_button.enabled = self.web_button.enabled = ready
        self.send_button.enabled = ready and not self.app.busy() and not gemini_client.SDK_ERROR
        self.send_button.label = 'Sending ...' if self.app.busy() else 'Send to Gemini'
        self.undo_button.enabled = bool(self.job.undo_stack)
        self.clear_button.enabled = self.job.has_sketch()
        for button in self.send_buttons + (self.undo_button, self.clear_button):
            button.draw(screen, fonts.font, mouse)

    def draw_sheet(self, screen, area, mouse):
        """The split image with the sketch, as big as it fits; remembers where for the mouse."""
        if area.w < 40 or area.h < 40:
            return
        job = self.job
        if self.dirty or self.display is None or not self.display_rect or \
                not area.contains(self.display_rect) or self.display_rect.size != self._fit(area):
            sheet = job.build_sheet(with_sketch=False)
            sheet.blit(job.sketch_surface(), job.cells()[1])
            self.display = pygame.transform.smoothscale(sheet, self._fit(area))
            self.dirty = False
        self.display_rect = self.display.get_rect(center=area.center)
        screen.blit(self.display, self.display_rect)

        # The line being dragged, or the one Shift+click would draw
        right = self.right_cell_on_screen()
        factor = self.display_rect.w / job.build_sheet_size()[0]
        if self.line:
            start, end, colour = self.line
            self.draw_line_preview(screen, start, end, colour, factor)
        elif (self.tool == 'brush' and self.last_point and not self.stroke and right.collidepoint(mouse)
              and pygame.key.get_mods() & pygame.KMOD_SHIFT):
            pygame.draw.line(screen, BRUSH_RING, self.to_screen(self.last_point), mouse)

        # The tool, where it would paint, and the colour in hand beside it
        if right.collidepoint(mouse):
            if self.tool in SIZED_TOOLS:
                pygame.draw.circle(screen, BRUSH_RING, mouse, max(2, int(self.radius() * factor)), 1)
            else:
                mx, my = mouse
                pygame.draw.line(screen, BRUSH_RING, (mx - 7, my), (mx + 7, my))
                pygame.draw.line(screen, BRUSH_RING, (mx, my - 7), (mx, my + 7))
            swatch = pygame.Rect(mouse[0] + 10, mouse[1] + 10, CURSOR_SWATCH, CURSOR_SWATCH)
            pygame.draw.rect(screen, self.wheel.colour, swatch)
            pygame.draw.rect(screen, BRUSH_RING, swatch, 1)

    def draw_line_preview(self, screen, start, end, colour, factor):
        """A straight line as it will be painted; one that rubs out shows as white with a thin core."""
        a, b = self.to_screen(start), self.to_screen(end)
        radius = max(1, round(self.radius() * factor))
        paint = colour if colour is not None else (255, 255, 255)
        screen.set_clip(self.right_cell_on_screen())
        pygame.draw.line(screen, paint, a, b, 2 * radius)
        for point in (a, b):
            pygame.draw.circle(screen, paint, point, radius)
        if colour is None:
            pygame.draw.line(screen, BRUSH_RING, a, b)
        screen.set_clip(None)

    def _fit(self, area):
        w, h = self.job.build_sheet_size()
        factor = min(area.w / w, area.h / h)
        return max(1, int(w * factor)), max(1, int(h * factor))

    def right_cell_on_screen(self):
        if not self.display_rect:
            return pygame.Rect(0, 0, 0, 0)
        factor = self.display_rect.w / self.job.build_sheet_size()[0]
        cell = self.job.cells()[1]
        return pygame.Rect(self.display_rect.x + cell.x * factor, self.display_rect.y + cell.y * factor,
                           cell.w * factor, cell.h * factor)

    def to_cell(self, pos):
        """A screen point in right-cell coordinates."""
        right = self.right_cell_on_screen()
        factor = right.w / self.job.cell_size[0]
        return (pos[0] - right.x) / factor, (pos[1] - right.y) / factor

    def to_screen(self, point):
        """A right-cell point on the screen."""
        right = self.right_cell_on_screen()
        factor = right.w / self.job.cell_size[0]
        return round(right.x + point[0] * factor), round(right.y + point[1] * factor)

    def radius(self):
        share = dict(BRUSHES)[self.brush]
        return max(1, round(min(self.job.cell_size) * share))

    def draw_controls(self, screen, rect, mouse):
        fonts = self.app.fonts
        draw_panel(screen, fonts, rect, f'The new {self.job.domain.noun}')
        inner = rect.inflate(-28, -28)
        x, y, w = inner.x, inner.y, inner.w

        screen.blit(fonts.small.render('Type', True, TEXT_DIM), (x, y))
        y += 22
        domain = self.job.domain
        self.kind_chips, y = draw_chips(screen, fonts.small, [k.key for k in domain.kinds],
                                        lambda key: domain.kinds_by_key[key].title, self.job.kind, x, y, w, mouse)
        y += 16
        screen.blit(fonts.small.render('Subcategory, goes into the prompt', True, TEXT_DIM), (x, y))
        y += 22
        self.field.rect = pygame.Rect(x, y, w, 36)
        self.field.draw(screen, fonts.font, mouse)
        y += 36 + 16

        screen.blit(fonts.small.render('Colour in hand', True, TEXT_DIM), (x, y))
        y += 22
        recent_y = inner.bottom - RECENT_SIZE
        self.draw_recent(screen, x, recent_y, w, mouse)
        recent_label = recent_y - 22
        screen.blit(fonts.small.render('Used last (keys 1 to 0)', True, TEXT_DIM), (x, recent_label))
        swatch = pygame.Rect(x, recent_label - 12 - SWATCH_H, w, SWATCH_H)
        self.wheel.layout(pygame.Rect(x, y, w, swatch.y - 12 - y))
        self.wheel.draw(screen)
        colour = self.wheel.colour
        pygame.draw.rect(screen, colour, (swatch.x, swatch.y, SWATCH_H, SWATCH_H), border_radius=6)
        pygame.draw.rect(screen, CARD_BG, (swatch.x, swatch.y, SWATCH_H, SWATCH_H), 1, border_radius=6)
        text = fit_text(fonts.font, f'{colour_name(colour)}  {hex_colour(colour)}', w - SWATCH_H - 12)
        label = fonts.font.render(text, True, TEXT)
        screen.blit(label, label.get_rect(midleft=(swatch.x + SWATCH_H + 12, swatch.centery)))
        self.draw_proposals(screen, self.field.rect, inner, mouse)

    def draw_recent(self, screen, x, y, w, mouse):
        """The colours used last as a row of swatches, as many as fit."""
        self.recent_chips = []
        fits = max(1, (w + RECENT_GAP) // (RECENT_SIZE + RECENT_GAP))
        for index, colour in enumerate(self.recent[:fits]):
            rect = pygame.Rect(x + index * (RECENT_SIZE + RECENT_GAP), y, RECENT_SIZE, RECENT_SIZE)
            pygame.draw.rect(screen, colour, rect, border_radius=4)
            if colour == self.wheel.colour:
                line, width = TEXT, 2
            elif rect.collidepoint(mouse):
                line, width = TEXT_DIM, 2
            else:
                line, width = DIALOG_LINE, 1
            pygame.draw.rect(screen, line, rect, width, border_radius=4)
            self.recent_chips.append((rect, colour))
        if not self.recent:
            screen.blit(self.app.fonts.small.render('none yet', True, TEXT_DIM), (x, y + 6))

    def proposals(self):
        """The subcategories proposed for the kind, narrowed down to what is typed."""
        typed = self.field.text.strip().lower()
        return [s for s in self.job.domain.suggestions.get(self.job.kind, ())
                if typed in s.lower() and s.lower() != typed]

    def draw_proposals(self, screen, field, inner, mouse):
        """Below the subcategory field while it is typed in: the proposals as chips, over the wheel."""
        self.proposal_chips, self.proposals_rect = [], None
        proposals = self.proposals() if self.field.focused else []
        if not proposals:
            return
        small = self.app.fonts.small
        x, w = inner.x + PROPOSALS_PAD, inner.w - 2 * PROPOSALS_PAD
        top = field.bottom + 6
        kind = self.job.domain.kinds_by_key[self.job.kind]
        title = small.render(f'Proposals for {kind.title.lower()}', True, TEXT_DIM)
        # Lay the chips out once off screen to know how tall the box must be
        scratch = pygame.Surface((1, 1))
        _, bottom = draw_chips(scratch, small, proposals, str, None, x, 0, w, (-1, -1))
        box = pygame.Rect(inner.x, top, inner.w, bottom + title.get_height() + 3 * PROPOSALS_PAD)
        pygame.draw.rect(screen, DIALOG_BG, box, border_radius=8)
        pygame.draw.rect(screen, DIALOG_LINE, box, 2, border_radius=8)
        screen.blit(title, (x, top + PROPOSALS_PAD))
        chips_y = top + 2 * PROPOSALS_PAD + title.get_height()
        self.proposal_chips, _ = draw_chips(screen, small, proposals, str, None, x, chips_y, w, mouse)
        self.proposals_rect = box

    # --- input ------------------------------------------------------------

    def click(self, pos):
        if not self.discard_button.rect.collidepoint(pos):
            self.discard_armed = False
        if self.proposals_rect and self.proposals_rect.collidepoint(pos):
            for chip, value in self.proposal_chips:
                if chip.collidepoint(pos):
                    self.field.text = value
                    self.field.focus(False)
                    self.take_subcategory()
            return
        self.field.focus(self.field.rect.collidepoint(pos))
        if not self.field.focused:
            self.take_subcategory()
        for button, action in self.actions:
            if button.hit(pos):
                action()
                return
        for chip, value in self.tool_chips:
            if chip.collidepoint(pos):
                self.tool = value
                return
        for chip, value in self.brush_chips:
            if chip.collidepoint(pos):
                self.brush = value
                if self.tool not in SIZED_TOOLS:
                    self.tool = 'brush'
                return
        for chip, colour in self.recent_chips:
            if chip.collidepoint(pos):
                self.pick_colour(colour)
                return
        for chip, value in self.kind_chips:
            if chip.collidepoint(pos):
                self.job.kind = value
                self.changed()
                return
        if self.wheel.press(pos):
            self.take_colour()
            return
        if pygame.key.get_mods() & pygame.KMOD_ALT:
            self.take_up_colour(pos)
            return
        self.use_tool(pos, self.wheel.colour)

    def right_click(self, pos):
        self.use_tool(pos, None)

    def use_tool(self, pos, colour):
        """Paint or fill at a screen point in `colour`; None rubs out."""
        if not self.right_cell_on_screen().collidepoint(pos):
            return
        point = self.to_cell(pos)
        if self.tool == 'line':
            self.line = (point, point, colour)   # painted when the mouse lets go
            return
        self.job.begin_stroke()
        if self.tool == 'fill':
            if self.job.fill(point, colour):
                self.used(colour)
                self.changed()
            else:
                self.job.undo_stack.pop()
            return
        # Shift+click goes on from where the last stroke ended, in a straight line
        start = self.last_point if self.last_point and pygame.key.get_mods() & pygame.KMOD_SHIFT else point
        self.stroke = (point, colour)
        self.job.paint(start, point, self.radius(), colour)
        self.dirty = True

    def line_end(self, start, pos):
        """Where a dragged line ends: at the mouse, or with Shift in the nearest step of LINE_SNAP degrees."""
        end = self.to_cell(pos)
        if not pygame.key.get_mods() & pygame.KMOD_SHIFT:
            return end
        dx, dy = end[0] - start[0], end[1] - start[1]
        step = math.radians(LINE_SNAP)
        angle = round(math.atan2(dy, dx) / step) * step
        length = math.hypot(dx, dy)
        return start[0] + math.cos(angle) * length, start[1] + math.sin(angle) * length

    def take_up_colour(self, pos):
        """Alt+click: the colour under the mouse becomes the one in hand."""
        if not self.right_cell_on_screen().collidepoint(pos):
            return
        colour = self.job.colour_at(self.to_cell(pos))
        if colour is None:
            self.app.set_status('No colour there to take up')
            return
        self.pick_colour(colour)

    def pick_colour(self, colour):
        self.wheel.colour = colour
        self.take_colour()

    def used(self, colour):
        """A colour went onto the sketch: it heads the colours used last."""
        if colour is not None:
            remember_colour(self.job.domain, self.recent, colour)

    def mouse_motion(self, pos, buttons):
        if self.wheel.dragging:
            self.wheel.drag(pos)
            self.take_colour(save=False)
        elif self.line:
            start, _, colour = self.line
            self.line = (start, self.line_end(start, pos), colour)
        elif self.stroke:
            last, colour = self.stroke
            point = self.to_cell(pos)
            self.job.paint(last, point, self.radius(), colour)
            self.stroke = (point, colour)
            self.dirty = True

    def mouse_up(self, pos, button):
        if self.wheel.release():
            self.take_colour()
        if self.line:
            start, _, colour = self.line
            end = self.line_end(start, pos)
            self.line = None
            self.job.begin_stroke()
            self.job.paint(start, end, self.radius(), colour)
            self.last_point = end
            self.used(colour)
            self.changed()
        if self.stroke:
            self.last_point, colour = self.stroke
            self.stroke = None
            self.used(colour)
            self.changed()

    def take_colour(self, save=True):
        self.job.colour = self.wheel.colour
        self.dirty = True
        if save:
            self.changed()

    def take_subcategory(self):
        text = self.field.text.strip()
        if text != self.job.subcategory:
            self.job.subcategory = text
            self.changed()

    def captures_keys(self):
        return self.field.focused

    def text_input(self, text):
        self.field.type(text)

    def key(self, event):
        if self.field.focused:
            if self.field.key(event) == 'done':
                self.take_subcategory()
            return
        ctrl = event.mod & pygame.KMOD_CTRL
        number = '1234567890'.find(event.unicode) if event.unicode and not ctrl else -1
        if number >= 0:
            if number < len(self.recent_chips):
                self.pick_colour(self.recent_chips[number][1])
        elif event.key == pygame.K_b and not ctrl:
            self.tool = 'brush'
        elif event.key == pygame.K_l and not ctrl:
            self.tool = 'line'
        elif event.key == pygame.K_f and not ctrl:
            self.tool = 'fill'
        elif event.key == pygame.K_z and ctrl:
            self.undo()
        elif event.key == pygame.K_c and ctrl:
            if event.mod & pygame.KMOD_SHIFT:
                self.copy_prompt()
            else:
                self.copy_image()
        elif event.key == pygame.K_w and ctrl:
            self.send_web()
        elif event.key == pygame.K_v and ctrl:
            self.paste_answer()
        elif event.key == pygame.K_o and ctrl:
            self.open_answer()
        elif event.key == pygame.K_TAB and self.app.store.entries:
            self.app.open_answers()

    def back(self):
        self.field.focus(False)
        self.take_subcategory()
        self.app.close_job()
        return True
