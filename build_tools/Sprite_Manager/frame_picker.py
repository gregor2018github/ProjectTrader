"""The dialog that makes a frame or standing sprite out of another one the NPC already has."""

import pygame

from create_new_pose import (
    DIALOG_PAD, DONE_COLOR, TEXT, TEXT_DIM, Button, Card, draw_chips, window_size,
)
from images import fitted, is_blank, load_frame, trim
from walk import STANDING_DIRECTIONS, find_direction, standing_pose, suggested_sources
from widgets import CardGrid, draw_dialog_box

PICK_CARD_SIZE = (116, 178)
PICK_THUMB_SIZE = (100, 130)
PICK_MAX_SIZE = (980, 760)
PICK_MODES = ((True, 'Mirrored'), (False, 'As it is'))


class FramePicker:
    """Pick one of the NPC's frames or standing sprites to save, mirrored or not, as the chosen one."""

    def __init__(self, npc, sheet, counts, fonts, on_pick):
        """
        Args:
            npc: The WalkNpc.
            sheet: The FrameSheet the new frame (or standing sprite) is for.
            counts: {Direction: frames in its cycle}.
            fonts: widgets.Fonts.
            on_pick: Called with (source path, source label, mirror) for the frame clicked.
        """
        self.sheet = sheet
        self.fonts = fonts
        self.on_pick = on_pick
        self.mirror = True
        self.grid = CardGrid(centred=False)
        self.chips = []
        self.cancel_button = Button('Cancel', w=120)

        suggested = suggested_sources(sheet.direction, sheet.frame, sheet.count)
        target = npc.sprite_path(sheet.pose)
        several = len(npc.motions) > 1
        # (direction, frame, label): the standing sprites (frame 0) first, then every frame.
        # The standing sprites count as the sheet's motion, so they match its suggestions.
        sources = [(find_direction(sheet.direction.motion, key), 0) for key in STANDING_DIRECTIONS]
        sources = [(d, 0, f'Standing {d.label.lower()}') for d, _ in sources]
        for direction in (d for motion in npc.motions for d in npc.directions(motion)):
            name = f'{direction.motion.label} {direction.label.lower()}' if several else direction.label
            sources += [(direction, frame, f'{name} {frame}') for frame in range(1, counts[direction] + 1)]
        cards = []
        for direction, frame, label in sources:
            path = npc.sprite_path(standing_pose(direction) if frame == 0 else direction.pose(frame))
            sprite = load_frame(path) if path != target else None
            if is_blank(sprite):
                continue
            cards.append(Card(
                (direction, frame, path), label, fitted(trim(sprite), PICK_THUMB_SIZE),
                'suggested' if (direction, frame) in suggested else '',
                note_color=DONE_COLOR, size=PICK_CARD_SIZE))
        # Suggestions first, the rest in the order of the direction list.
        order = {source: index for index, source in enumerate(suggested)}
        cards.sort(key=lambda card: order.get(card.key[:2], len(order)))
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
        screen.blit(title.render(f'Make {self.sheet.pose} from another frame', True, TEXT), (x, y))
        y += 48
        self.chips, bottom = draw_chips(screen, small, [m for m, _ in PICK_MODES],
                                        lambda m: dict(PICK_MODES)[m], self.mirror,
                                        x, y, width, mouse)
        self.cancel_button.rect.bottomright = (rect.right - DIALOG_PAD, rect.bottom - DIALOG_PAD)
        area = pygame.Rect(x, bottom + 16, width, self.cancel_button.rect.y - 16 - bottom - 16)

        if not self.grid.cards:
            text = font.render('This NPC has no other frames yet.', True, TEXT_DIM)
            screen.blit(text, text.get_rect(center=area.center))
        self.grid.layout(area)
        self.grid.draw(screen, self.fonts, mouse)

        hint = 'Click the frame to use. The frame there now is replaced.'
        screen.blit(small.render(hint, True, TEXT_DIM),
                    (x, self.cancel_button.rect.centery - small.get_linesize() // 2))
        self.cancel_button.draw(screen, font, mouse)

    def click(self, pos):
        """Handles one click; returns 'close' when the dialog is done."""
        if self.cancel_button.hit(pos) or not self.rect().collidepoint(pos):
            return 'close'
        for rect, mode in self.chips:
            if rect.collidepoint(pos):
                self.mirror = mode
                return None
        card = self.grid.card_at(pos)
        if card:
            direction, frame, path = card.key
            source = f'standing {direction.label.lower()}' if frame == 0 else f'{direction.title} {frame}'
            self.on_pick(path, source, self.mirror)
            return 'close'
        return None
