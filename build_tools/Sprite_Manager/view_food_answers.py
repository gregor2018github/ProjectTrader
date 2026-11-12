"""The model's answers for a dish's picture, and taking one into the game.

The crops' answers screen (view_crop_answers.CropAnswersView) for a dish: left the example as sent, with
the ways to more answers, in the middle the answers, right the chosen answer as it would be saved (fitted
to the example's proportions and size) between the example and the picture it would replace. Accepting
writes assets/pictures/dish_<key>.png (food_sheets.save_picture, which keeps an old one) and goes back to
the food.
"""

import pygame

from food_sheets import DishDetail, save_picture
from images import smooth_fit
from theme import ERROR_COLOR, TEXT_DIM
from view_crop_answers import CropAnswersView
from view_review import CAPTION_ON_CHECKER
from widgets import fit_text


class DishAnswersView(CropAnswersView):
    def __init__(self, app, food_view, sheet, entry=None):
        """
        Args:
            food_view: The view_food.FoodView to go back to.
            sheet: The food_sheets.DishSheet the answers are for.
            entry: The answer to show first.
        """
        super().__init__(app, food_view, sheet, entry)
        self.food_view = food_view
        self.subject = app.npc
        self._current = None

    @property
    def target(self):
        return self.subject.target

    def make_detail(self, entry):
        return DishDetail(self.subject, entry, self.sheet.surface)

    def current_sprite(self):
        """The dish's picture in the game now, or None."""
        if self._current is None and self.target.is_file():
            try:
                self._current = pygame.image.load(str(self.target)).convert()
            except (pygame.error, OSError):
                pass
        return self._current

    def save_output(self, output):
        return save_picture(self.subject, output)

    def result_title(self):
        return 'The example, the new picture as it would be saved, and the one now'

    def header(self):
        return (f'Answers for {self.subject.title}',
                f'Drawn after {self.sheet.example.name}. Ctrl+V or drop a file = answer, Enter = accept into the '
                f'game, Del = not good enough.')

    def draw_result(self, screen, area):
        """Example, new picture and the one now in a column, each as big as fits."""
        small = self.app.fonts.small
        self.checker.draw(screen, area)
        detail = self.detail
        if not detail:
            return
        if not detail.result:
            text = small.render(fit_text(small, detail.error, area.w - 20), True, ERROR_COLOR)
            screen.blit(text, text.get_rect(center=area.center))
            return
        shown = [(f'example: {self.sheet.example.name}', self.sheet.surface), ('new', detail.result.output)]
        current = self.current_sprite()
        if current is not None:
            shown.append(('now in the game', current))
        gap = 26
        height = (area.h - 30 - len(shown) * gap) // len(shown)
        y = area.y + gap
        for label, surface in shown:
            picture = smooth_fit(surface, (area.w - 20, height))
            rect = picture.get_rect(midtop=(area.centerx, y))
            text = small.render(label, True, CAPTION_ON_CHECKER)
            screen.blit(text, text.get_rect(midbottom=(rect.centerx, rect.y - 3)))
            screen.blit(picture, rect)
            if label == 'new':
                pygame.draw.rect(screen, TEXT_DIM, rect.inflate(2, 2), 1)
            y += height + gap
        output = detail.result.output
        caption = small.render(f'{output.get_width()} x {output.get_height()} px -> {self.target.name}', True,
                               CAPTION_ON_CHECKER)
        screen.blit(caption, caption.get_rect(midbottom=(area.centerx, area.bottom - 6)))

    def back(self):
        self.app.close_dish(self.food_view)
        return True
