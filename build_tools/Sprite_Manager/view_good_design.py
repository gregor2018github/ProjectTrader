"""Sketching a good's picture for the menus before it goes to the model.

The sketch screen of the plants, buildings and crops (view_sprite_design.SketchView) with the good's
2x2 sheet (goods_sheets.GoodSketch): three other goods for the style, picked at random, and bottom right
the red frame to sketch the new good in. Right, above the colour, what the good is (its description.txt,
which goes into the prompt; "Edit description" opens it) and the three goods shown ("Other goods" picks
three others). Answers open in view_good_answers.py; Back returns to the menu sprites.
"""

import os
import sys

import pygame

import pose_review
from goods_sheets import POSE
from images import fitted
from theme import CARD_BG, TEXT, TEXT_DIM
from view_good_answers import GoodAnswersView
from view_sprite_design import SketchView
from widgets import Button, fit_text, wrap_text

TILE = 72
TILE_GAP = 10
SMALL_BUTTON_H = 32


class GoodDesignView(SketchView):
    def __init__(self, app, goods_view, sketch):
        """
        Args:
            goods_view: The view_goods.GoodsView to go back to.
            sketch: The goods_sheets.GoodSketch to work on.
        """
        super().__init__(app, sketch)
        self.goods_view = goods_view
        self.subject = app.npc
        self.thumbs = {}
        self.description_button = Button('Edit description (E)', h=SMALL_BUTTON_H, w=180)
        self.reroll_button = Button('Other goods (R)', h=SMALL_BUTTON_H, w=150)
        self.answers_button = Button('Answers', w=150)
        self.actions += [(self.description_button, self.edit_description),
                         (self.reroll_button, self.reroll),
                         (self.answers_button, self.open_answers)]

    @property
    def sketch(self):
        return self.job

    # --- actions ----------------------------------------------------------

    def edit_description(self):
        try:
            path = self.subject.ensure_description()
        except OSError as exc:
            self.app.set_status(f'Cannot write the description: {exc}', error=True)
            return
        if sys.platform == 'win32':
            os.startfile(path)
        self.app.set_status(f'Editing {path} - the prompt follows the file as it is saved')

    def reroll(self):
        self.sketch.pick_references()
        self.changed()
        self.app.set_status('Now shown: ' + ', '.join(g.name for g in self.sketch.references))

    def open_answers(self):
        if not self.app.store.for_pose(POSE):
            return
        try:
            sheet = self.sketch.sheet()
        except (pygame.error, OSError) as exc:
            self.app.set_status(f'Cannot write the split image: {exc}', error=True)
            return
        self.app.show(GoodAnswersView(self.app, self, sheet))

    # --- what SketchView asks ---------------------------------------------

    def unfinished(self):
        if self.sketch.unreadable:
            return 'Cannot cut out ' + ', '.join(self.sketch.unreadable) + ' - try other goods (R)'
        return '' if self.sketch.has_sketch() else 'Sketch the good in the red frame first'

    def sheet_title(self):
        return 'Split image - three goods for the style, sketch the new one in the red frame'

    def controls_title(self):
        return 'The good'

    def web_label(self):
        return f'{self.subject.title} painting'

    def show_answer(self, sheet, entry):
        self.app.show(GoodAnswersView(self.app, self, sheet, entry))

    # --- view -------------------------------------------------------------

    def header(self):
        return (f'Sketch {self.subject.title} for the menus',
                'Sketch the good bottom right in flat colours (B brush, L line, F fill, left paints, right rubs out, '
                'Alt+click takes a colour, Ctrl+Z undo), then send it (Ctrl+W in the browser). Ctrl+V = answer.')

    def footer(self):
        app = self.app
        return (app.back_button, app.folder_button), (app.settings_button, self.answers_button)

    def update_footer(self):
        answers = self.app.store.for_pose(POSE)
        waiting = sum(e.status == pose_review.PENDING for e in answers)
        self.answers_button.label = f'Answers ({waiting} new)' if waiting else f'Answers ({len(answers)})'
        self.answers_button.enabled = bool(answers)

    def draw_choices(self, screen, x, y, w, mouse):
        """What the good is, and the goods shown for the style."""
        fonts = self.app.fonts
        small = fonts.small
        for line in wrap_text(small, self.subject.description(), w, 3):
            screen.blit(small.render(line, True, TEXT), (x, y))
            y += 18
        y += 6
        self.description_button.rect.topleft = (x, y)
        self.description_button.draw(screen, small, mouse)
        y += SMALL_BUTTON_H + 16

        screen.blit(small.render('Shown for the style', True, TEXT_DIM), (x, y))
        y += 22
        for index, good in enumerate(self.sketch.references):
            rect = pygame.Rect(x + index * (TILE + TILE_GAP), y, TILE, TILE)
            screen.blit(self.thumb(good), rect)
            label = small.render(fit_text(small, good.name, TILE + TILE_GAP), True, TEXT_DIM)
            screen.blit(label, label.get_rect(midtop=(rect.centerx, rect.bottom + 2)))
        y += TILE + 24
        self.reroll_button.rect.topleft = (x, y)
        self.reroll_button.enabled = len(self.sketch.references) > 0
        self.reroll_button.draw(screen, small, mouse)
        return y + SMALL_BUTTON_H + 16

    def thumb(self, good):
        if good.name not in self.thumbs:
            try:
                image = pygame.image.load(str(good.path('icon'))).convert_alpha()
            except (pygame.error, OSError):
                image = pygame.Surface((1, 1), pygame.SRCALPHA)
            self.thumbs[good.name] = fitted(image, (TILE, TILE), CARD_BG)
        return self.thumbs[good.name]

    # --- input ------------------------------------------------------------

    def key(self, event):
        if event.key == pygame.K_e and not event.mod & pygame.KMOD_CTRL:
            self.edit_description()
        elif event.key == pygame.K_r and not event.mod & pygame.KMOD_CTRL:
            self.reroll()
        elif event.key == pygame.K_TAB:
            self.open_answers()
        else:
            super().key(event)

    def back(self):
        self.app.close_good(self.goods_view)
        return True
