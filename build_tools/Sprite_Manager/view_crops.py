"""The crops: one card each with how many of its stage sprites there are, and one to add a crop."""

import pygame

import pose_review
from crops import find_crops
from images import fitted
from new_crop_dialog import NewCropDialog
from pose_review import ReviewStore
from theme import CARD_BG, NPC_THUMB_SIZE, STATUS_COLORS, TEXT_DIM, THUMB_BG
from view import View
from widgets import Card, CardGrid

CARD_SIZE = (172, 262)
ADD = 'add'


class CropsView(View):
    def __init__(self, app):
        super().__init__(app)
        self.grid = CardGrid()
        self.switch_buttons = app.switch_buttons('crops')
        self.plus = pygame.Surface(NPC_THUMB_SIZE)
        self.plus.fill(CARD_BG)
        plus = pygame.font.SysFont('segoeui', 90).render('+', True, TEXT_DIM)
        self.plus.blit(plus, plus.get_rect(center=self.plus.get_rect().center))

    def refresh(self):
        cards = []
        for crop in find_crops():
            sprite = crop.thumb_sprite()
            if sprite is None:
                thumb = pygame.Surface(NPC_THUMB_SIZE)
                thumb.fill(THUMB_BG)
            else:
                thumb = fitted(sprite.subsurface(sprite.get_bounding_rect()), NPC_THUMB_SIZE)
            done, needed = crop.done(), crop.needed()
            waiting = len(ReviewStore(crop.out_dir).pending())
            extra = [(f'{len(crop.stages)} stages, {crop.variants} variants', TEXT_DIM)]
            if waiting:
                extra.append((f'{waiting} to review', STATUS_COLORS[pose_review.PENDING]))
            color = STATUS_COLORS[pose_review.ACCEPTED] if done == needed else TEXT_DIM
            cards.append(Card(crop, crop.title, thumb, f'{done}/{needed} stage sprites', note_color=color,
                              extra=extra, progress=done / max(1, needed), size=CARD_SIZE))
        cards.append(Card(ADD, 'Add crop', self.plus, note='name and look', size=CARD_SIZE))
        self.grid.cards = cards

    def header(self):
        return ('Crops',
                'Every crop of the fields, grown in stages from the ploughed field to the ripe crop. Click one to '
                'make its stage sprites, + to add a crop. Tab = humans, plants, buildings.')

    def footer(self):
        return (self.app.home_button,) + tuple(self.switch_buttons), (self.app.settings_button,)

    def draw(self, screen, mouse):
        self.grid.layout(self.app.card_area())
        self.grid.draw(screen, self.app.fonts, mouse)

    def click(self, pos):
        for button in self.switch_buttons:
            if button.hit(pos):
                self.app.switch_to(button.screen)
                return
        card = self.grid.card_at(pos)
        if card is None:
            return
        if card.key == ADD:
            self.app.dialog = NewCropDialog(self.app.fonts, self.crop_created)
        else:
            self.app.open_crop(card.key)

    def crop_created(self, crop):
        self.app.open_crop(crop)
        self.app.set_status(f'Created {crop.folder.name}/ - its first sprite is drawn from another crop\'s ripe one')

    def key(self, event):
        if event.key == pygame.K_TAB:
            self.app.switch_to_next()

    def scroll_by(self, steps):
        self.grid.scroll_by(steps)

    def back(self):
        self.app.go_home()
        return True
