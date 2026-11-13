"""The model's answers for one piece of a fence or wall, and taking one into the game.

The crops' answers screen (view_crop_answers.py) with a fence piece: on the
right the piece cut out of the answer onto its raster, with the tiles and the
blue rings where its posts must stand, under it the piece twice end to end
(the join two pieces make) and the piece in the game now. Arrow keys nudge the
cut by a game pixel, should its posts not sit on the rings; a click on a white
gap shows it again or makes it see-through. Accepting saves it as
<style>_<h|v><n>.png in the style's folder, over one there may be, and goes
back to the style with its Tiled properties in the status line.
"""

import pygame

from fence_sheets import FOOT_COLOR, POST_COLOR, FenceDetail
from fences import HORIZONTAL, TILE
from theme import ERROR_COLOR
from view_crop_answers import CropAnswersView
from view_review import CAPTION_ON_CHECKER
from widgets import fit_text

GRID_LINE = (200, 200, 210)
GAP = 14
MAX_ZOOM = 8
NUDGES = {pygame.K_LEFT: (-1, 0), pygame.K_RIGHT: (1, 0), pygame.K_UP: (0, -1), pygame.K_DOWN: (0, 1)}


class FenceAnswersView(CropAnswersView):
    def __init__(self, app, fence_view, sheet, entry=None):
        """
        Args:
            fence_view: The view_fence.FenceView to go back to.
            sheet: The fence_sheets.FenceSheet the answers are for.
            entry: The answer to show first.
        """
        super().__init__(app, fence_view, sheet, entry)
        self.fence_view = fence_view
        self.piece = sheet.piece

    @property
    def target(self):
        return self.piece.path

    def make_detail(self, entry):
        return FenceDetail(self.crop, entry)

    def current_sprite(self):
        return self.piece.sprite() if self.piece.exists() else None

    def save_output(self, output):
        replaced = self.piece.save(output)
        return f'{"Replaced" if replaced else "Saved"} {self.piece.path.name}. {self.piece.tiled_hint()}'

    def result_title(self):
        return 'On its raster, twice end to end, and the one now  (arrows nudge, click white gaps)'

    def header(self):
        return (f'Answers for {self.piece.name}',
                'Ctrl+V or drop a file = answer, Enter = accept into the game, Del = not good enough, arrows = '
                'nudge the cut by a game pixel, click white gaps in the result to see through them.')

    def back(self):
        self.app.show(self.fence_view)
        return True

    # --- the result -------------------------------------------------------

    def draw_result(self, screen, area):
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
        output = detail.result.output
        raster = self.piece.raster
        w, h = output.get_size()
        across = raster.orientation == HORIZONTAL
        joined = self.joined(output)
        current = self.current_sprite()
        # Laid out: the piece on its raster; beside it (vertical) or under it (horizontal) the pair and the old one
        shown = [('new', output), ('twice, end to end', joined)] + ([('now in the game', current)] if current else [])
        if across:
            total_w = max(s.get_width() for _, s in shown)
            total_h = sum(s.get_height() for _, s in shown) + GAP * (len(shown) - 1)
        else:
            total_w = sum(s.get_width() for _, s in shown) + GAP * (len(shown) - 1)
            total_h = max(s.get_height() for _, s in shown)
        label_room = 22 * len(shown)
        factor = min((area.w - 20) / total_w, (area.h - 40 - label_room) / total_h, MAX_ZOOM)
        factor = int(factor) if factor >= 1 else factor
        scale = pygame.transform.scale if factor >= 1 else pygame.transform.smoothscale
        x, y = area.x + 10, area.y + 26
        for label, surface in shown:
            size = (max(1, int(surface.get_width() * factor)), max(1, int(surface.get_height() * factor)))
            rect = pygame.Rect((x, y), size)
            screen.blit(scale(surface, size), rect)
            text = small.render(label, True, CAPTION_ON_CHECKER)
            screen.blit(text, text.get_rect(bottomleft=(rect.x, rect.y - 2)))
            if label == 'new':
                self.draw_raster(screen, rect, factor)
                detail.preview = (rect, factor)
            if across:
                y += size[1] + GAP + 22
            else:
                x += size[0] + GAP
        nudge = detail.result.nudge
        moved = f', moved {nudge[0]:+d}, {nudge[1]:+d} px' if any(nudge) else ''
        caption = small.render(f'{w} x {h} px{moved} -> {self.piece.path.name}', True, CAPTION_ON_CHECKER)
        screen.blit(caption, caption.get_rect(midbottom=(area.centerx, area.bottom - 10)))

    def draw_raster(self, screen, rect, factor):
        raster = self.piece.raster
        unit = TILE * factor
        tiles_w, tiles_h = raster.size
        for x in range(tiles_w + 1):
            pygame.draw.line(screen, GRID_LINE, (rect.x + x * unit, rect.y), (rect.x + x * unit, rect.bottom))
        for y in range(tiles_h + 1):
            pygame.draw.line(screen, GRID_LINE, (rect.x, rect.y + y * unit), (rect.right, rect.y + y * unit))

        def at(point):
            return round(rect.x + point[0] * unit), round(rect.y + point[1] * unit)

        pygame.draw.line(screen, FOOT_COLOR, at(raster.start), at(raster.end()), 1)
        for post in raster.posts():
            pygame.draw.circle(screen, POST_COLOR, at(post), max(3, round(unit / 10)), 2)

    def joined(self, output):
        """The piece twice, the second starting where the first ends, as two would lie on the map."""
        raster = self.piece.raster
        step = raster.length * TILE
        w, h = output.get_size()
        if raster.orientation == HORIZONTAL:
            canvas = pygame.Surface((w + step, h), pygame.SRCALPHA)
            canvas.blit(output, (0, 0))
            canvas.blit(output, (step, 0))
        else:
            canvas = pygame.Surface((w, h + step), pygame.SRCALPHA)
            canvas.blit(output, (0, 0))
            canvas.blit(output, (0, step))     # the nearer one, lower in the picture, in front
        return canvas

    # --- input ------------------------------------------------------------

    def key(self, event):
        if event.key in NUDGES and self.detail and self.detail.result:
            self.detail.move(*NUDGES[event.key])
            if self.detail.error:
                self.app.set_status(self.detail.error, error=True)
                self.detail.error = ''
        else:
            super().key(event)
