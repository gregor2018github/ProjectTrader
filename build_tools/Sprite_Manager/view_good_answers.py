"""The model's answers for a good's picture, and taking one into the game.

The crops' answers screen (view_crop_answers.CropAnswersView) for a good: left the sheet as sent, in the
middle the answers, right the good cut out of the chosen answer as the game would show it - the painting,
the cut-out and the 30px icon, each with the one it replaces under it. Accepting writes all three
(goods_sheets.save_pictures, which keeps the old ones) and goes back to the menu sprites.
"""

import pygame

import pose_review

from goods_sheets import GoodDetail, pictures_of, save_pictures
from images import pixel_fit, smooth_fit
from theme import ERROR_COLOR, TEXT_DIM
from view_crop_answers import CropAnswersView
from view_review import CAPTION_ON_CHECKER
from widgets import fit_text

SMALL_ZOOM = 3             # the 30px icon is shown this many times bigger, pixel for pixel
SMALL_SIZE_SHOWN = 30 * SMALL_ZOOM
SHOWN = (('painting', 'painting'), ('icon', 'cut-out'), ('small', f'30px x{SMALL_ZOOM}'))


class GoodAnswersView(CropAnswersView):
    def __init__(self, app, design_view, sheet, entry=None):
        """
        Args:
            design_view: The view_good_design.GoodDesignView to go back to.
            sheet: The goods_sheets.GoodSheet the answers are for.
            entry: The answer to show first.
        """
        super().__init__(app, design_view, sheet, entry)
        self.design_view = design_view
        self.subject = app.npc
        self._current = None

    def make_detail(self, entry):
        return GoodDetail(self.subject, entry)

    def current_pictures(self):
        """{kind: Surface} of the good's pictures in the game now (placeholders too)."""
        if self._current is None:
            self._current = {}
            for kind, _ in SHOWN:
                try:
                    self._current[kind] = pygame.image.load(str(self.subject.good.path(kind))).convert_alpha()
                except (pygame.error, OSError):
                    pass
        return self._current

    def save_output(self, output):
        written = save_pictures(self.subject, output)
        return 'Saved ' + ', '.join(written)

    def accept(self):
        """Write the good's pictures from the chosen answer and go back to the menu sprites."""
        if not (self.detail and self.detail.result):
            return
        entry = self.entry
        super().accept()
        if entry.status == pose_review.ACCEPTED:   # saved; else the error stays on screen
            self.app.close_good(self.design_view.goods_view)

    def back(self):
        self.app.show(self.design_view)
        return True

    def result_title(self):
        return 'What accepting writes, over what the game has now  (click white gaps in the cut-out)'

    def header(self):
        return (f'Answers for {self.subject.title}',
                'Ctrl+V or drop a file = answer, Enter = accept into the game (painting, cut-out and 30px icon), '
                'Del = not good enough, click white gaps in the cut-out to see through them.')

    def draw_result(self, screen, area):
        """The new pictures in a row, the ones they replace under them."""
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
        new = pictures_of(detail.result.output)
        now = self.current_pictures()
        gap = 14
        column = (area.w - 2 * gap - (len(SHOWN) - 1) * gap) // len(SHOWN)
        row_h = (area.h - 4 * 24) // 2
        size = max(30, min(column, row_h))
        for index, (kind, label) in enumerate(SHOWN):
            x = area.x + gap + index * (column + gap)
            for row, (title, pictures) in enumerate((('new', new), ('now', now))):
                y = area.y + 24 + row * (size + 48)
                caption = small.render(f'{title}: {label}', True, CAPTION_ON_CHECKER)
                screen.blit(caption, (x, y - 20))
                picture = pictures.get(kind)
                box = pygame.Rect(x, y, size, size)
                if picture is None:
                    text = small.render('none', True, TEXT_DIM)
                    screen.blit(text, text.get_rect(center=box.center))
                    continue
                if kind == 'small':
                    shown = pixel_fit(picture, (min(size, SMALL_SIZE_SHOWN), min(size, SMALL_SIZE_SHOWN)))
                else:
                    shown = smooth_fit(picture, box.size)
                rect = shown.get_rect(center=box.center)
                screen.blit(shown, rect)
                if row == 0 and kind == 'icon':
                    pygame.draw.rect(screen, TEXT_DIM, rect, 1)
                    detail.preview = (rect, rect.w / detail.result.output.get_width())
        caption = small.render(f'{detail.result.output.get_width()} x {detail.result.output.get_height()} px '
                               f'cut out of the answer', True, CAPTION_ON_CHECKER)
        screen.blit(caption, caption.get_rect(midbottom=(area.centerx, area.bottom - 10)))
