"""The fences and walls: one card each with how many of its pieces are drawn, and one to add a style."""

import pygame

import pose_review
from fences import find_styles
from images import fitted
from new_fence_dialog import NewFenceDialog
from pose_review import ReviewStore
from theme import CARD_BG, NPC_THUMB_SIZE, STATUS_COLORS, TEXT_DIM, THUMB_BG
from view import View
from widgets import Card, CardGrid

CARD_SIZE = (172, 262)
ADD = 'add'


class FencesView(View):
    def __init__(self, app):
        super().__init__(app)
        self.grid = CardGrid()
        self.switch_buttons = app.switch_buttons('fences')
        self.plus = pygame.Surface(NPC_THUMB_SIZE)
        self.plus.fill(CARD_BG)
        plus = pygame.font.SysFont('segoeui', 90).render('+', True, TEXT_DIM)
        self.plus.blit(plus, plus.get_rect(center=self.plus.get_rect().center))

    def refresh(self):
        cards = []
        for style in find_styles():
            sprite = style.thumb_sprite()
            if sprite is None or not sprite.get_bounding_rect().w:
                thumb = pygame.Surface(NPC_THUMB_SIZE)
                thumb.fill(THUMB_BG)
            else:
                thumb = fitted(sprite.subsurface(sprite.get_bounding_rect()), NPC_THUMB_SIZE)
            done, needed = style.done(), style.needed()
            waiting = len(ReviewStore(style.out_dir).pending())
            posts = 'posts at the ends' if style.posts_every == 0 else f'posts every {style.posts_every}'
            extra = [(f'{style.material.title}, {posts}', TEXT_DIM)]
            if waiting:
                extra.append((f'{waiting} to review', STATUS_COLORS[pose_review.PENDING]))
            color = STATUS_COLORS[pose_review.ACCEPTED] if needed and done == needed else TEXT_DIM
            cards.append(Card(style, style.title, thumb, f'{done}/{needed} pieces', note_color=color,
                              extra=extra, progress=done / max(1, needed), size=CARD_SIZE))
        cards.append(Card(ADD, 'Add fence or wall', self.plus, note='name and material', size=CARD_SIZE))
        self.grid.cards = cards

    def header(self):
        return ('Fences and walls',
                'Every fence and wall, made of straight pieces laid end to end on the tiles, horizontal and '
                'vertical. Click one to make its pieces, + to add one. Tab = the next area.')

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
            self.app.dialog = NewFenceDialog(self.app.fonts, self.style_created)
        else:
            self.app.open_fence(self, card.key)

    def style_created(self, style):
        self.app.open_fence(self, style)
        self.app.set_status(f'Created fences/{style.name}/ - pick the lengths it wants, then sketch its first piece')

    def key(self, event):
        if event.key == pygame.K_TAB:
            self.app.switch_to_next()

    def scroll_by(self, steps):
        self.grid.scroll_by(steps)

    def back(self):
        self.app.go_home()
        return True
