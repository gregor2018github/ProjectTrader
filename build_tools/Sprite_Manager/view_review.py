"""Screens 3 and 4: every answer of an NPC, and one answer judged on its own."""

import pygame

import gemini_client
import pose_review
from create_new_pose import (
    CARD_BG, DONE_COLOR, ERROR_COLOR, PANEL_GAP, RESULT_CARD_SIZE, RESULT_THUMB_SIZE, ROOT,
    STATUS_COLORS, TEXT_DIM, Button, Card, Detail, make_thumb, measure,
)
from images import fitted
from npc import DEFAULT_BASE
from sheets import SHEET_ERRORS, reference_shapes, write_sheets, write_standing_sheet
from view import View
from widgets import CardGrid, Checker, draw_panel


class ReviewView(View):
    """Every answer of the NPC, pending ones first."""

    def __init__(self, app):
        super().__init__(app)
        self.grid = CardGrid()  # filled by refresh(), when the app shows the view

    def refresh(self):
        app = self.app
        cards = []
        for entry in app.store.sorted_entries():
            path = app.npc.out_dir / entry.image
            try:
                thumb = make_thumb(path, RESULT_THUMB_SIZE, trim=False)
            except (pygame.error, OSError):
                continue
            measure(path, entry, app.store)
            cards.append(Card(
                entry, entry.pose, thumb, entry.status,
                note_color=STATUS_COLORS.get(entry.status, TEXT_DIM),
                extra=[(entry.delivered() or 'size unknown', TEXT_DIM),
                       (entry.asked_for(), TEXT_DIM),
                       (entry.short_warning(), DONE_COLOR)],
                size=RESULT_CARD_SIZE))
        self.grid.cards = cards

    def header(self):
        waiting = len(self.app.store.pending())
        return (f'3. Answers for "{self.app.npc.name}"  -  {waiting} waiting',
                'Click an answer to judge it. Accepted ones are already in the game.')

    def footer(self):
        app = self.app
        return (app.back_button, app.folder_button), (app.settings_button,)

    def draw(self, screen, mouse):
        self.grid.layout(self.app.card_area())
        self.grid.draw(screen, self.app.fonts, mouse)

    def click(self, pos):
        card = self.grid.card_at(pos)
        if card:
            self.app.open_detail(card.key, self)

    def scroll_by(self, steps):
        self.grid.scroll_by(steps)

    def back(self):
        self.app.show(self.app.frames)
        return True


class DetailView(View):
    """One answer next to the frame it would become: accept it, or not."""

    def __init__(self, app, entry, return_to):
        """
        Raises:
            ValueError: If the entry is not a frame of one of the figure's motions.
            Exception: If its image cannot be read.
        """
        super().__init__(app)
        direction, frame = app.npc.parse_pose(entry.pose)
        if direction is None:
            raise ValueError(f'{entry.pose} is not a walk or run frame')
        # A standing sprite is made from the front one, a frame from its direction's base.
        self.base = DEFAULT_BASE if frame == 0 else app.npc.base_for(direction)
        poses, shapes = reference_shapes(app.npc, entry.pose, self.base)
        self.detail = Detail(app.npc, entry, poses, shapes)
        self.return_to = return_to
        self.checker = Checker()
        self.reject_button = Button('Not good enough', w=190)
        self.regenerate_button = Button('Regenerate', w=150)
        self.accept_button = Button('Accept', w=150)

    @property
    def entry(self):
        return self.detail.entry

    def opening_status(self):
        """(text, is_error) to greet the answer with."""
        if self.detail.error:
            return self.detail.error, True
        if self.entry.warning:
            return self.entry.warning, False
        return f'{self.entry.pose}, {self.entry.status}', False

    # --- actions ----------------------------------------------------------

    def close(self):
        self.app.show(self.return_to)

    def accept(self):
        """Save the frame into the game and mark the answer accepted."""
        app, detail = self.app, self.detail
        if not detail.result:
            return
        try:
            path = pose_review.save_sprite(detail.result, app.npc, self.entry.pose)
        except (pygame.error, OSError) as exc:
            app.set_status(f'Could not save: {exc}', error=True)
            return
        app.store.set_status(self.entry, pose_review.ACCEPTED)
        self.close()
        app.set_status(f'Saved {path.relative_to(ROOT)}')

    def reject(self):
        """Mark the answer as not good enough, or put it back to pending."""
        entry = self.entry
        back = entry.status != pose_review.PENDING
        self.app.store.set_status(entry, pose_review.PENDING if back else pose_review.REJECTED)
        self.app.set_status(f'{entry.image} is now {entry.status}')

    def regenerate(self):
        """Ask the API for another answer to the same frame, from a fresh sheet."""
        direction, frame = self.app.npc.parse_pose(self.entry.pose)
        if self.app.busy() or direction is None:
            return
        try:
            if frame == 0:
                self.app.send([write_standing_sheet(self.app.npc, direction)])
            else:
                self.app.send(write_sheets(self.app.npc, direction, [frame]))
        except SHEET_ERRORS as exc:
            self.app.set_status(f'Cannot rebuild the sheet: {exc}', error=True)

    # --- view -------------------------------------------------------------

    def header(self):
        entry = self.entry
        got = f'got {entry.delivered()}' if entry.delivered() else 'size unknown'
        return (f'{entry.pose}  -  {entry.image}',
                f'from {entry.asked_for()}  -  {got}  -  Enter = accept, Del = not good enough')

    def footer(self):
        app = self.app
        return ((app.back_button, app.folder_button),
                (self.reject_button, self.regenerate_button, self.accept_button))

    def update_footer(self):
        self.accept_button.enabled = bool(self.detail.result)
        self.reject_button.label = ('Back to pending' if self.entry.status != pose_review.PENDING
                                    else 'Not good enough')
        self.regenerate_button.enabled = not self.app.busy() and not gemini_client.SDK_ERROR

    def draw(self, screen, mouse):
        detail, fonts, npc = self.detail, self.app.fonts, self.app.npc
        body = self.app.body()
        image_rect = pygame.Rect(body.x, body.y, int((body.w - PANEL_GAP) * 0.55), body.h)
        preview_rect = pygame.Rect(image_rect.right + PANEL_GAP, body.y,
                                   body.right - image_rect.right - PANEL_GAP, body.h)

        returned = f'{detail.image.get_width()} x {detail.image.get_height()} px'
        tokens = self.entry.token_detail()
        draw_panel(screen, fonts, image_rect,
                   f'The answer  -  {returned}' + (f'  -  {tokens}' if tokens else ''))
        area = image_rect.inflate(-20, -20)
        screen.blit(fitted(detail.image, area.size, CARD_BG), area)

        draw_panel(screen, fonts, preview_rect,
                   f'{npc.prefix}_{self.base} and the new frame, same scale  (click white gaps)')
        area = preview_rect.inflate(-20, -20)
        self.checker.draw(screen, area)
        detail.preview = None
        if not detail.result:
            text = fonts.small.render(detail.error, True, ERROR_COLOR)
            screen.blit(text, text.get_rect(center=area.center))
            return

        reference, output = detail.result.player, detail.result.output
        gap = 20
        total = (reference.get_width() + output.get_width() + gap,
                 max(reference.get_height(), output.get_height()))
        factor = min((area.w - 20) / total[0], (area.h - 50) / total[1], 1.5)
        rw, rh = int(reference.get_width() * factor), int(reference.get_height() * factor)
        ow, oh = int(output.get_width() * factor), int(output.get_height() * factor)
        baseline = area.bottom - 40
        start_x = area.centerx - int(total[0] * factor) // 2
        # Both canvases stand on the reference's baseline.
        reference_bottom = detail.result.player_offset[1] + reference.get_height()
        output_pos = (start_x + rw + int(gap * factor), baseline - int(reference_bottom * factor))
        screen.blit(pygame.transform.smoothscale(reference, (rw, rh)), (start_x, baseline - rh))
        screen.blit(pygame.transform.smoothscale(output, (ow, oh)), output_pos)
        pygame.draw.rect(screen, TEXT_DIM, (*output_pos, ow, oh), 1)
        detail.preview = (pygame.Rect(output_pos, (ow, oh)), factor)

        caption = fonts.small.render(
            f'{output.get_width()} x {output.get_height()} px, scale {detail.result.scale:.2f} '
            f'-> {npc.sprite_path(self.entry.pose).name}', True, (40, 40, 40))
        screen.blit(caption, caption.get_rect(midbottom=(area.centerx, area.bottom - 10)))

    def click(self, pos):
        if self.accept_button.hit(pos):
            self.accept()
        elif self.reject_button.hit(pos):
            self.reject()
        elif self.regenerate_button.hit(pos):
            self.regenerate()
        else:
            self.detail.toggle_hole(pos)

    def key(self, event):
        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.accept()
        elif event.key == pygame.K_DELETE:
            self.reject()

    def back(self):
        self.close()
        return True
