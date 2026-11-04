"""The animals: one card each with how many of its frames there are, and one to add an animal."""

import pygame

import pose_review
from animals import find_animals
from images import fitted
from new_animal_dialog import NewAnimalDialog
from pose_review import ReviewStore
from theme import CARD_BG, NPC_THUMB_SIZE, STATUS_COLORS, TEXT_DIM, THUMB_BG
from view import View
from widgets import Card, CardGrid

CARD_SIZE = (172, 262)
ADD = 'add'


class AnimalsView(View):
    def __init__(self, app):
        super().__init__(app)
        self.grid = CardGrid()
        self.switch_buttons = app.switch_buttons('animals')
        self.plus = pygame.Surface(NPC_THUMB_SIZE)
        self.plus.fill(CARD_BG)
        plus = pygame.font.SysFont('segoeui', 90).render('+', True, TEXT_DIM)
        self.plus.blit(plus, plus.get_rect(center=self.plus.get_rect().center))

    def refresh(self):
        cards = []
        for animal in find_animals():
            sprite = animal.thumb_sprite()
            if sprite is None:
                thumb = pygame.Surface(NPC_THUMB_SIZE)
                thumb.fill(THUMB_BG)
            else:
                thumb = fitted(sprite.subsurface(sprite.get_bounding_rect()), NPC_THUMB_SIZE)
            done, needed = animal.done(), animal.needed()
            waiting = len(ReviewStore(animal.out_dir).pending())
            extra = [('the pose guide' if animal.is_base else 'needs its standing sprite' if animal.is_new
                      else 'facing left', TEXT_DIM)]
            if waiting:
                extra.append((f'{waiting} to review', STATUS_COLORS[pose_review.PENDING]))
            color = STATUS_COLORS[pose_review.ACCEPTED] if done == needed else TEXT_DIM
            cards.append(Card(animal, animal.title, thumb, f'{done}/{needed} frames', note_color=color,
                              extra=extra, progress=done / max(1, needed), size=CARD_SIZE))
        cards.append(Card(ADD, 'Add animal', self.plus, note='name and look', size=CARD_SIZE))
        self.grid.cards = cards

    def header(self):
        return ('Animals',
                'The animals of the map, seen from the side facing left; the game mirrors them for the right. '
                'Click one to make its frames, + to add one. Tab = the next area.')

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
            self.app.dialog = NewAnimalDialog(self.app.fonts, self.animal_created)
        else:
            self.app.open_animal(card.key)

    def animal_created(self, animal):
        self.app.open_animal(animal)
        self.app.set_status(f'Created {animal.folder.name}/ - first its standing sprite, drawn beside the sheep')

    def key(self, event):
        if event.key == pygame.K_TAB:
            self.app.switch_to_next()

    def scroll_by(self, steps):
        self.grid.scroll_by(steps)

    def back(self):
        self.app.go_home()
        return True
