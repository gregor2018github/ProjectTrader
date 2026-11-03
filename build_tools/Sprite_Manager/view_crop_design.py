"""Sketching one stage sprite of a crop before it goes to the model.

The sketch screen of the plants and buildings (view_sprite_design.SketchView)
with the crop's sheet (crop_sheets.CropSketch): left the reference and the
red frame to sketch the plant in, with the dashed lines of the ground and of
the height the stage grows to, which are only help and are not sent. Right,
above the colour, what the sprite is drawn from, in up to three groups, each
with its own prompt: another stage of this crop to grow it from (the ripe
plant for a smaller one, say), another variant of this stage to make a
variation of, or, for a crop with no sprite yet, another crop's ripe sprite
for the style. Each reference keeps a sketch of its own. Answers open in
view_crop_answers.py; Back returns to the crop.
"""

import pygame

import pose_review
from crop_sheets import (
    GROW, MODE_TITLES, OTHER_CROP, VARIATION, choose_reference, crop_sketch, reference_options,
)
from images import fitted, trim
from theme import CARD_BG, DONE_COLOR, TEXT, TEXT_DIM
from view_crop_answers import CropAnswersView
from view_sprite_design import SketchView
from widgets import Button, fit_text

TILE = 64                 # a reference's thumbnail
TILE_GAP = 8
TILE_LABEL_H = 18
GROUP_GAP = 12
HOVER_LINE = (150, 150, 150)
DRAWN_FROM_HINTS = {
    GROW: 'the same crop at this stage, grown as far as it is',
    VARIATION: 'another clump just as far grown, a neighbour in the field',
    OTHER_CROP: 'only the style and scale come from it',
}


class CropDesignView(SketchView):
    def __init__(self, app, crop_view, sketch):
        """
        Args:
            crop_view: The view_crop.CropView to go back to.
            sketch: The crop_sheets.CropSketch to work on.
        """
        super().__init__(app, sketch)
        self.crop_view = crop_view
        self.crop = app.npc
        self.tiles = []           # [(rect, Reference)] as last drawn
        self.thumbs = {}          # {reference path: thumbnail}
        self.answers_button = Button('Answers', w=150)
        self.actions.append((self.answers_button, self.open_answers))

    @property
    def sketch(self):
        return self.job

    # --- state ------------------------------------------------------------

    def options(self):
        sketch = self.sketch
        return reference_options(self.crop, sketch.stage_index, sketch.variant, self.crop_view.others)

    def choose(self, reference):
        """Draw the sprite from another reference; its own sketch comes up."""
        sketch = self.sketch
        try:
            choose_reference(self.crop, sketch.pose, reference)
            self.job = crop_sketch(self.crop, sketch.stage_index, sketch.variant, reference=reference)
        except (pygame.error, OSError) as exc:
            self.app.set_status(f'Cannot draw from that sprite: {exc}', error=True)
            return
        self.stroke = self.line = self.last_point = None
        self.dirty = True
        self.app.set_status(f'{sketch.stage.title} {sketch.variant} now {self.job.mode_label()}')

    def unfinished(self):
        return '' if self.sketch.has_sketch() else 'Sketch the plant in the red frame first'

    def sheet_title(self):
        return 'Split image - sketch the plant in the red frame (the dashed lines are not sent)'

    def controls_title(self):
        return 'Drawn from'

    def web_label(self):
        return f'{self.crop.title} {self.sketch.pose}'

    def show_answer(self, sheet, entry):
        self.app.show(CropAnswersView(self.app, self.crop_view, sheet, entry))

    def open_answers(self):
        if not self.app.store.for_pose(self.sketch.pose):
            return
        try:
            sheet = self.sketch.sheet()
        except (pygame.error, OSError) as exc:
            self.app.set_status(f'Cannot write the split image: {exc}', error=True)
            return
        self.app.show(CropAnswersView(self.app, self.crop_view, sheet))

    # --- view -------------------------------------------------------------

    def header(self):
        sketch = self.sketch
        return (f'Sketch {self.crop.title}: {sketch.stage.title}, variant {sketch.variant} - {sketch.mode_label()}',
                'Sketch the plant up to the red line, standing on the grey one (B brush, L line, F fill, left paints, '
                'right rubs out, Shift+click straight on, Alt+click takes a colour, 1-0 recent colours, Ctrl+Z '
                'undo), pick what it is drawn from, then send it (Ctrl+W in the browser). Ctrl+V = answer.')

    def footer(self):
        app = self.app
        return (app.back_button, app.folder_button), (app.settings_button, self.answers_button)

    def update_footer(self):
        answers = self.app.store.for_pose(self.sketch.pose)
        waiting = sum(e.status == pose_review.PENDING for e in answers)
        self.answers_button.label = f'Answers ({waiting} new)' if waiting else f'Answers ({len(answers)})'
        self.answers_button.enabled = bool(answers)

    def draw_choices(self, screen, x, y, w, mouse):
        """The sprites it can be drawn from, by mode, the chosen one framed."""
        small = self.app.fonts.small
        self.tiles = []
        chosen = self.sketch.reference.path
        per_row = max(1, (w + TILE_GAP) // (TILE + TILE_GAP))
        for mode, refs in self.options().items():
            title = small.render(fit_text(small, MODE_TITLES[mode], w), True, TEXT)
            screen.blit(title, (x, y))
            y += 20
            hint = small.render(fit_text(small, DRAWN_FROM_HINTS[mode], w), True, TEXT_DIM)
            screen.blit(hint, (x, y))
            y += 22
            for index, reference in enumerate(refs):
                row, column = divmod(index, per_row)
                rect = pygame.Rect(x + column * (TILE + TILE_GAP), y + row * (TILE + TILE_LABEL_H + TILE_GAP),
                                   TILE, TILE)
                screen.blit(self.thumb(reference), rect)
                if reference.path == chosen:
                    pygame.draw.rect(screen, DONE_COLOR, rect.inflate(4, 4), 3, border_radius=3)
                elif rect.collidepoint(mouse):
                    pygame.draw.rect(screen, HOVER_LINE, rect.inflate(2, 2), 2, border_radius=3)
                name = (reference.crop.title if mode == OTHER_CROP else reference.stage.title)
                label = small.render(fit_text(small, f'{name} {reference.variant}', TILE + TILE_GAP), True, TEXT_DIM)
                screen.blit(label, label.get_rect(midtop=(rect.centerx, rect.bottom + 2)))
                self.tiles.append((rect, reference))
            rows = (len(refs) + per_row - 1) // per_row
            y += rows * (TILE + TILE_LABEL_H + TILE_GAP) + GROUP_GAP
        return y + 4

    def thumb(self, reference):
        path = reference.path
        if path not in self.thumbs:
            try:
                sprite = trim(pygame.image.load(str(path)).convert_alpha())
            except (pygame.error, OSError):
                sprite = pygame.Surface((1, 1), pygame.SRCALPHA)
            self.thumbs[path] = fitted(sprite, (TILE, TILE), CARD_BG)
        return self.thumbs[path]

    # --- input ------------------------------------------------------------

    def click(self, pos):
        for rect, reference in self.tiles:
            if rect.collidepoint(pos):
                if reference.path != self.sketch.reference.path:
                    self.choose(reference)
                return
        super().click(pos)

    def key(self, event):
        if event.key == pygame.K_TAB:
            self.open_answers()
        else:
            super().key(event)

    def back(self):
        self.app.show(self.crop_view)
        return True
