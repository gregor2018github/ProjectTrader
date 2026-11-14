"""The dialog choosing the model figure: whose finished walk the top row of a "Model figure" sheet shows."""

import pygame

from images import fitted, is_blank, load_frame, trim
from theme import DIALOG_PAD, DONE_COLOR, TEXT, TEXT_DIM, window_size
from widgets import Button, Card, CardGrid, draw_dialog_box

PICK_CARD_SIZE = (130, 190)
PICK_THUMB_SIZE = (110, 130)
PICK_MAX_SIZE = (1100, 780)


class ModelPicker:
    """Pick one of the figures with walk frames as the model for the sheets' top row."""

    def __init__(self, figures, npc, direction, count, chosen, fonts, on_pick):
        """
        Args:
            figures: Every WalkNpc of the tool.
            npc: The WalkNpc the sheets are for; it cannot be its own model.
            direction: The Direction shown, to tell which models have its frames.
            count: Frames in that direction's cycle.
            chosen: Folder name of the model chosen now.
            fonts: widgets.Fonts.
            on_pick: Called with the WalkNpc clicked.
        """
        self.fonts = fonts
        self.on_pick = on_pick
        self.direction = direction
        self.grid = CardGrid(centred=False)
        self.cancel_button = Button('Cancel', w=120)
        self.chosen = chosen

        cards = []
        for figure in figures:
            if figure.folder == npc.folder or direction.motion not in figure.motions:
                continue
            done = figure.done(direction, count)
            if not done:
                continue
            sprite = load_frame(figure.sprite_path(npc.base_for(direction)))
            if is_blank(sprite):
                continue
            complete = done == count
            note = f'{done}/{count} {direction.label.lower()}' + ('' if complete else ' - the rest on the grid')
            cards.append(Card(figure, figure.label, fitted(trim(sprite), PICK_THUMB_SIZE), note,
                              note_color=DONE_COLOR if complete else TEXT_DIM, size=PICK_CARD_SIZE))
        # The complete ones first, each group by name
        cards.sort(key=lambda c: (c.key.done(direction, count) != count, c.label.lower()))
        self.grid.cards = cards

    def rect(self):
        width, height = window_size()
        size = (min(PICK_MAX_SIZE[0], width - 40), min(PICK_MAX_SIZE[1], height - 40))
        return pygame.Rect(((width - size[0]) // 2, (height - size[1]) // 2), size)

    def scroll_by(self, steps):
        self.grid.scroll_by(steps)

    def draw(self, screen, mouse):
        font, small, title = self.fonts
        rect = self.rect()
        draw_dialog_box(screen, rect)

        x, y, width = rect.x + DIALOG_PAD, rect.y + DIALOG_PAD, rect.w - 2 * DIALOG_PAD
        screen.blit(title.render('Model figure for the top row', True, TEXT), (x, y))
        y += 48
        self.cancel_button.rect.bottomright = (rect.right - DIALOG_PAD, rect.bottom - DIALOG_PAD)
        area = pygame.Rect(x, y, width, self.cancel_button.rect.y - 16 - y)
        if not self.grid.cards:
            text = font.render(f'Nobody else has frames of the {self.direction.title} yet.', True, TEXT_DIM)
            screen.blit(text, text.get_rect(center=area.center))
        self.grid.layout(area)
        chosen = next((c.key for c in self.grid.cards if c.key.name == self.chosen), None)
        self.grid.draw(screen, self.fonts, mouse, selected_key=chosen)

        hint = 'Its standing sprite and frames go above; the grey mannequin stays in the red frame.'
        screen.blit(small.render(hint, True, TEXT_DIM),
                    (x, self.cancel_button.rect.centery - small.get_linesize() // 2))
        self.cancel_button.draw(screen, font, mouse)

    def click(self, pos):
        """Handles one click; returns 'close' when the dialog is done."""
        if self.cancel_button.hit(pos) or not self.rect().collidepoint(pos):
            return 'close'
        card = self.grid.card_at(pos)
        if card:
            self.on_pick(card.key)
            return 'close'
        return None
