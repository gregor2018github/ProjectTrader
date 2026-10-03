"""Screen 1 of the plants: every plant sprite by kind, and the new plants being made.

Clicking a sprite starts a new plant with it as the example (plant_job.py);
right-clicking it sets its kind and subcategory in plant_catalog.json
(KindDialog). The new plants not yet accepted into the game come first, to
be picked up again.
"""

import pygame

import pose_review
from images import pixel_fit
from plant_job import PlantJob
from plants import KINDS, REFERENCE, SORTABLE, UNSORTED, kind_title
from pose_review import ReviewStore
from theme import (
    CARD_BG, DIALOG_PAD, NPC_THUMB_SIZE, STATUS_COLORS, TEXT, TEXT_DIM, THUMB_BG, window_size,
)
from view import View
from widgets import Button, Card, SectionGrid, TextField, draw_chips, draw_dialog_box

CARD_W = 172
CROSS_R = 13             # the cross that scraps an unfinished plant, on its card's top right
CROSS_INSET = 8
CROSS_BG = (60, 56, 52)
CROSS_HOVER = (190, 70, 60)
CARD_H = 222
UNFINISHED = 'Unfinished new plants'


def plant_thumb(surface):
    """A sprite on a light tile, blown up by whole pixels where it is small."""
    tile = pygame.Surface(NPC_THUMB_SIZE)
    tile.fill(THUMB_BG)
    image = pixel_fit(surface, (NPC_THUMB_SIZE[0] - 12, NPC_THUMB_SIZE[1] - 12))
    tile.blit(image, image.get_rect(center=tile.get_rect().center))
    return tile


class PlantListView(View):
    def __init__(self, app):
        super().__init__(app)
        self.grid = SectionGrid('sprite')
        self.humans_button = Button('Humans', w=120)
        self.armed = None   # an unfinished plant with answers, whose cross was clicked once
        self.empty = pygame.Surface(NPC_THUMB_SIZE)
        self.empty.fill(CARD_BG)
        text = app.fonts.small.render('none yet', True, TEXT_DIM)
        self.empty.blit(text, text.get_rect(center=self.empty.get_rect().center))

    @staticmethod
    def thumb(key, surface_fn):
        """The card picture of a sprite or job, made once and kept on it."""
        if getattr(key, 'thumb', None) is None:
            key.thumb = plant_thumb(surface_fn())
        return key.thumb

    def refresh(self):
        app = self.app
        plants = app.plant_library()
        sections = []
        cards = []
        for job in app.plant_jobs():
            if job.accepted:
                continue
            waiting = len(ReviewStore(job.out_dir).pending())
            cards.append(Card(job, job.label, self.thumb(job, lambda j=job: j.build_sheet()),
                              note=f'{waiting} to review' if waiting else 'from ' + job.example_label,
                              note_color=STATUS_COLORS[pose_review.PENDING] if waiting else TEXT_DIM,
                              size=(CARD_W, CARD_H)))
        sections.append((UNFINISHED, cards))
        for key in [k.key for k in KINDS] + [UNSORTED, REFERENCE]:
            cards = [Card(p, p.label, self.thumb(p, lambda p=p: p.surface), note=p.where, size=(CARD_W, CARD_H))
                     for p in plants if p.kind == key]
            if not cards and key not in (UNSORTED, REFERENCE):
                card = Card(('empty', key), 'No sprite yet', self.empty,
                            note='start from any sprite', size=(CARD_W, CARD_H))
                card.counted = False
                cards = [card]
            sections.append((kind_title(key), cards))
        self.grid.set_sections(sections)

    def header(self):
        return ('Plants',
                'Click a sprite to make a new plant from it, right-click it to set its kind, '
                'the cross on an unfinished one scraps it. '
                'Tab switches to the humans.')

    def footer(self):
        return (self.humans_button,), (self.app.settings_button,)

    def draw(self, screen, mouse):
        self.grid.layout(self.app.card_area())
        self.grid.draw(screen, self.app.fonts, mouse)
        card = self.grid.card_at(mouse)
        if card and isinstance(card.key, PlantJob):
            self.draw_cross(screen, card, mouse)

    @staticmethod
    def cross_rect(card):
        return pygame.Rect(card.rect.right - CROSS_INSET - 2 * CROSS_R, card.rect.y + CROSS_INSET,
                           2 * CROSS_R, 2 * CROSS_R)

    def draw_cross(self, screen, card, mouse):
        """The cross scrapping an unfinished plant; red under the mouse, or once clicked for one with answers."""
        rect = self.cross_rect(card)
        hot = rect.collidepoint(mouse) or self.armed is card.key
        screen.set_clip(self.grid.area)
        pygame.draw.circle(screen, CROSS_HOVER if hot else CROSS_BG, rect.center, CROSS_R)
        arm = CROSS_R // 2 - 1
        for dx in (-arm, arm):
            pygame.draw.line(screen, TEXT, (rect.centerx - dx, rect.centery - arm),
                             (rect.centerx + dx, rect.centery + arm), 3)
        screen.set_clip(None)

    def scrap(self, job):
        """Delete an unfinished plant; one with answers only on the second click."""
        answers = len(ReviewStore(job.out_dir).entries)
        if answers and self.armed is not job:
            self.armed = job
            self.app.set_status(f'{job.label} has {answers} answer{"s" if answers > 1 else ""} - '
                                f'click the cross again to delete it with them', error=True)
            return
        self.armed = None
        job.discard()
        self.app.set_status(f'Scrapped the {job.label} from {job.example_label}')
        self.refresh()

    def click(self, pos):
        if self.humans_button.hit(pos):
            self.app.show_humans()
            return
        card = self.grid.card_at(pos)
        if card and isinstance(card.key, PlantJob) and self.cross_rect(card).collidepoint(pos):
            self.scrap(card.key)
            return
        self.armed = None
        if not card:
            return
        key = card.key
        if isinstance(key, tuple):
            self.app.set_status(f'No {kind_title(key[1]).lower()} yet: start from any sprite, '
                                f'then pick the type on the next screen')
        elif hasattr(key, 'surface'):
            self.app.start_plant_job(key)
        else:
            self.app.open_plant_job(key)

    def right_click(self, pos):
        card = self.grid.card_at(pos)
        if card and hasattr(card.key, 'surface'):
            self.app.dialog = KindDialog(card.key, self.app)

    def key(self, event):
        if event.key == pygame.K_TAB:
            self.app.show_humans()

    def scroll_by(self, steps):
        self.grid.scroll_by(steps)


class KindDialog:
    """Set a listed sprite's kind and subcategory in plant_catalog.json."""

    WIDTH = 620

    def __init__(self, sprite, app):
        self.sprite = sprite
        self.app = app
        self.kind = sprite.kind if sprite.kind in SORTABLE else None
        self.field = TextField(sprite.subcategory, placeholder='subcategory, e.g. oak (optional)')
        self.field.focus(True)
        self.chips = []
        self.save_button = Button('Save', w=120)
        self.cancel_button = Button('Cancel', w=120)
        self.error = ''

    def rect(self):
        width, height = window_size()
        size = (min(self.WIDTH, width - 40), 330)
        return pygame.Rect(((width - size[0]) // 2, (height - size[1]) // 2), size)

    def draw(self, screen, mouse):
        font, small, title = self.app.fonts
        rect = self.rect()
        draw_dialog_box(screen, rect)
        x, y, w = rect.x + DIALOG_PAD, rect.y + DIALOG_PAD, rect.w - 2 * DIALOG_PAD
        screen.blit(title.render('Kind of plant', True, TEXT), (x, y))
        y += 48
        screen.blit(small.render(self.sprite.where, True, TEXT_DIM), (x, y))
        y += 26
        self.chips, y = draw_chips(screen, small, SORTABLE, kind_title, self.kind, x, y, w, mouse)
        y += 14
        self.field.rect = pygame.Rect(x, y, w, 36)
        self.field.draw(screen, font, mouse)
        self.save_button.rect.bottomright = (rect.right - DIALOG_PAD, rect.bottom - DIALOG_PAD)
        self.cancel_button.rect.bottomright = (self.save_button.rect.x - 12, self.save_button.rect.bottom)
        self.save_button.enabled = self.kind is not None
        for button in (self.cancel_button, self.save_button):
            button.draw(screen, font, mouse)
        if self.error:
            screen.blit(small.render(self.error, True, STATUS_COLORS[pose_review.REJECTED]),
                        (x, self.save_button.rect.y + 12))

    def click(self, pos):
        for rect, value in self.chips:
            if rect.collidepoint(pos):
                self.kind = value
                return None
        if self.field.rect.collidepoint(pos):
            self.field.focus(True)
        elif self.cancel_button.hit(pos):
            return self.close()
        elif self.save_button.hit(pos):
            return self.save()
        return None

    def event(self, event):
        if event.type == pygame.TEXTINPUT:
            self.field.type(event.text)
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                return self.close()
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                return self.save()
            if event.key == pygame.K_BACKSPACE:
                self.field.text = self.field.text[:-1]
        return None

    def scroll_by(self, steps):
        pass

    def save(self):
        if self.kind is None:
            self.error = 'Pick a kind first'
            return None
        try:
            self.app.plant_catalog().set_kind(self.sprite, self.kind, self.field.text.strip())
        except OSError as exc:
            self.error = str(exc)
            return None
        self.app.set_status(f'{self.sprite.where} is now {kind_title(self.kind)}')
        self.app.reload_plants()
        return self.close()

    def close(self):
        self.field.focus(False)
        return 'close'
