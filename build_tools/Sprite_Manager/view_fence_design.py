"""Sketching one piece of a fence or wall before it goes to the model.

The sketch screen of the plants and buildings (view_sprite_design.SketchView)
with the piece's sheet (fence_sheets.FenceSketch): the reference above the
sketch for a horizontal piece, beside it for a vertical one, both on their
tile rasters at one scale. The raster, the run's foot line and the blue rings
where the posts stand are only help and are not sent; the brush keeps to the
piece's raster. "Draft" (D) paints a first sketch from the raster and the
material, which a piece gets by itself the first time it is opened.

Right, above the colour, what the piece is drawn from, in up to three groups,
each with its own prompt: another length of this style, this style turned
(the first vertical piece from a horizontal one, say), or another style's
piece or one of the old walls, for the look only. The sketch stays the same
whichever is chosen. Answers open in view_fence_answers.py; Back returns to
the style.
"""

import pygame

import pose_review
from fence_sheets import FenceSketch, choose_reference
from fences import MODE_TITLES, OTHER_STYLE, SAME_RUN, TURNED, find_styles, reference_options
from images import fitted
from theme import CARD_BG, DONE_COLOR, TEXT, TEXT_DIM
from view_fence_answers import FenceAnswersView
from view_sprite_design import SketchView
from widgets import Button, fit_text

TILE_W, TILE_H = 92, 56     # a reference's thumbnail
TILE_GAP = 8
TILE_LABEL_H = 18
GROUP_GAP = 12
HOVER_LINE = (150, 150, 150)
DRAWN_FROM_HINTS = {
    SAME_RUN: 'the same fence, only longer or shorter',
    TURNED: 'the same fence, running the other way',
    OTHER_STYLE: 'only its style and scale count',
}


class FenceDesignView(SketchView):
    def __init__(self, app, fence_view, sketch):
        """
        Args:
            fence_view: The view_fence.FenceView to go back to.
            sketch: The fence_sheets.FenceSketch to work on.
        """
        super().__init__(app, sketch)
        self.fence_view = fence_view
        self.style = app.npc
        self.styles = find_styles()
        self.tiles = []           # [(rect, Reference)] as last drawn
        self.thumbs = {}          # {reference key: thumbnail}
        self.answers_button = Button('Answers', w=150)
        self.draft_button = Button('Draft', h=32, w=80)
        self.actions += [(self.answers_button, self.open_answers),
                         (self.draft_button, self.draft)]

    @property
    def sketch(self):
        return self.job

    # --- state ------------------------------------------------------------

    def options(self):
        return reference_options(self.sketch.piece, self.styles)

    def choose(self, reference):
        """Draw the piece from another reference; the sketch stays."""
        piece = self.sketch.piece
        try:
            choose_reference(piece, reference)
            self.sketch.save()
            self.job = FenceSketch(piece, reference)
        except (pygame.error, OSError) as exc:
            self.app.set_status(f'Cannot draw from that piece: {exc}', error=True)
            return
        self.stroke = self.line = self.last_point = None
        self.dirty = True
        self.app.set_status(f'{piece.title} now {self.job.mode_label()}')

    def draft(self):
        self.sketch.draft()
        self.last_point = None
        self.changed()
        self.app.set_status('Drafted from the raster - Ctrl+Z takes it back')

    def unfinished(self):
        return '' if self.sketch.has_sketch() else 'Sketch the piece on its raster first (D drafts one)'

    def sheet_title(self):
        return 'Split image - sketch the piece on its raster (raster, foot line and post rings are not sent)'

    def controls_title(self):
        return 'Drawn from'

    def web_label(self):
        return self.sketch.piece.name

    def show_answer(self, sheet, entry):
        self.app.show(FenceAnswersView(self.app, self.fence_view, sheet, entry))

    def open_answers(self):
        if not self.app.store.for_pose(self.sketch.pose):
            return
        try:
            sheet = self.sketch.sheet()
        except (pygame.error, OSError) as exc:
            self.app.set_status(f'Cannot write the split image: {exc}', error=True)
            return
        self.app.show(FenceAnswersView(self.app, self.fence_view, sheet))

    # --- view -------------------------------------------------------------

    def header(self):
        sketch = self.sketch
        return (f'Sketch {sketch.piece.name} - {sketch.mode_label()}',
                'Sketch the piece on its raster, the posts on the blue rings (D drafts one, B brush, L line, '
                'F fill, left paints, right rubs out, Alt+click takes a colour, Ctrl+Z undo), pick what it is '
                'drawn from, then send it (Ctrl+W in the browser). Ctrl+V = answer.')

    def footer(self):
        app = self.app
        return (app.back_button, app.folder_button), (app.settings_button, self.answers_button)

    def update_footer(self):
        answers = self.app.store.for_pose(self.sketch.pose)
        waiting = sum(e.status == pose_review.PENDING for e in answers)
        self.answers_button.label = f'Answers ({waiting} new)' if waiting else f'Answers ({len(answers)})'
        self.answers_button.enabled = bool(answers)

    def draw_sheet_panel(self, screen, rect, mouse):
        super().draw_sheet_panel(screen, rect, mouse)
        # Draft goes left of Undo, in the tools' row
        self.draft_button.rect.topright = (self.undo_button.rect.x - 10, self.undo_button.rect.y)
        self.draft_button.draw(screen, self.app.fonts.font, mouse)

    def draw_choices(self, screen, x, y, w, mouse):
        """The pieces it can be drawn from, by mode, the chosen one framed."""
        small = self.app.fonts.small
        self.tiles = []
        chosen = self.sketch.reference.key
        per_row = max(1, (w + TILE_GAP) // (TILE_W + TILE_GAP))
        for mode, refs in self.options().items():
            screen.blit(small.render(fit_text(small, MODE_TITLES[mode], w), True, TEXT), (x, y))
            y += 20
            screen.blit(small.render(fit_text(small, DRAWN_FROM_HINTS[mode], w), True, TEXT_DIM), (x, y))
            y += 22
            for index, reference in enumerate(refs):
                row, column = divmod(index, per_row)
                rect = pygame.Rect(x + column * (TILE_W + TILE_GAP),
                                   y + row * (TILE_H + TILE_LABEL_H + TILE_GAP), TILE_W, TILE_H)
                screen.blit(self.thumb(reference), rect)
                if reference.key == chosen:
                    pygame.draw.rect(screen, DONE_COLOR, rect.inflate(4, 4), 3, border_radius=3)
                elif rect.collidepoint(mouse):
                    pygame.draw.rect(screen, HOVER_LINE, rect.inflate(2, 2), 2, border_radius=3)
                name = reference.label() if mode != OTHER_STYLE or reference.old else \
                    f'{reference.style_title} {reference.piece.key}'
                label = small.render(fit_text(small, name, TILE_W + TILE_GAP), True, TEXT_DIM)
                screen.blit(label, label.get_rect(midtop=(rect.centerx, rect.bottom + 2)))
                self.tiles.append((rect, reference))
            rows = (len(refs) + per_row - 1) // per_row
            y += rows * (TILE_H + TILE_LABEL_H + TILE_GAP) + GROUP_GAP
        return y + 4

    def thumb(self, reference):
        if reference.key not in self.thumbs:
            try:
                sprite = reference.load()
                sprite = sprite.subsurface(sprite.get_bounding_rect()).copy()
            except (pygame.error, OSError, ValueError):
                sprite = pygame.Surface((1, 1), pygame.SRCALPHA)
            self.thumbs[reference.key] = fitted(sprite, (TILE_W, TILE_H), CARD_BG)
        return self.thumbs[reference.key]

    # --- input ------------------------------------------------------------

    def click(self, pos):
        for rect, reference in self.tiles:
            if rect.collidepoint(pos):
                if reference.key != self.sketch.reference.key:
                    self.choose(reference)
                return
        super().click(pos)

    def key(self, event):
        ctrl = event.mod & pygame.KMOD_CTRL
        if event.key == pygame.K_TAB:
            self.open_answers()
        elif event.key == pygame.K_d and not ctrl:
            self.draft()
        else:
            super().key(event)

    def back(self):
        self.app.show(self.fence_view)
        return True
