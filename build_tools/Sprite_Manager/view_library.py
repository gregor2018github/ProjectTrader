"""Screen 1 of the plants or the buildings: every sprite of the domain by kind, and the new ones being made.

Clicking a sprite starts a new one with it as the example (sprite_job.py);
right-clicking it sets its kind and subcategory in the domain's catalog
(KindDialog); "GIMP" on its card, or G over it, opens its file in GIMP, and
once saved back the app puts it into its collection again
(sprite_library.restamp()). The new sprites not yet accepted into the game come first, to
be picked up again, or scrapped with the cross on their card.
"""

import pygame

import pose_review
from images import pixel_fit
from library_summary import SUMMARY_H, Stats, draw_summary, gather
from pose_review import ReviewStore
from sprite_job import SpriteJob
from sprite_library import REFERENCE, UNSORTED
from theme import (
    CARD_BG, DIALOG_PAD, NPC_THUMB_SIZE, PANEL_GAP, STATUS_COLORS, TEXT, TEXT_DIM, THUMB_BG, window_size,
)
from view import View
from widgets import Button, Card, SectionGrid, TextField, draw_chips, draw_dialog_box

CARD_W = 172
CARD_H = 222
CROSS_R = 13             # the cross that scraps an unfinished sprite, on its card's top right
CROSS_INSET = 8
CROSS_BG = (60, 56, 52)
CROSS_HOVER = (190, 70, 60)
GIMP_BUTTON = (58, 26)   # the button opening a sprite's file in GIMP, on its card's top left
GIMP_HOVER = (150, 120, 70)


def sprite_thumb(surface):
    """A sprite on a light tile, blown up by whole pixels where it is small."""
    tile = pygame.Surface(NPC_THUMB_SIZE)
    tile.fill(THUMB_BG)
    image = pixel_fit(surface, (NPC_THUMB_SIZE[0] - 12, NPC_THUMB_SIZE[1] - 12))
    tile.blit(image, image.get_rect(center=tile.get_rect().center))
    return tile


class LibraryView(View):
    def __init__(self, app, domain):
        super().__init__(app)
        self.domain = domain
        self.grid = SectionGrid('sprite')
        self.switch_buttons = app.switch_buttons(domain.key)
        self.armed = None   # an unfinished sprite with answers, whose cross was clicked once
        self.stats = Stats()
        self.empty = pygame.Surface(NPC_THUMB_SIZE)
        self.empty.fill(CARD_BG)
        text = app.fonts.small.render('none yet', True, TEXT_DIM)
        self.empty.blit(text, text.get_rect(center=self.empty.get_rect().center))

    @staticmethod
    def thumb(key, surface_fn):
        """The card picture of a sprite or job, made once and kept on it."""
        if getattr(key, 'thumb', None) is None:
            key.thumb = sprite_thumb(surface_fn())
        return key.thumb

    def refresh(self):
        app, domain = self.app, self.domain
        sprites = app.library(domain)
        jobs = app.jobs(domain)
        self.stats = gather(domain, sprites, jobs, app.atlas_fills)
        sections = []
        cards = []
        for job in jobs:
            if job.accepted:
                continue
            waiting = len(ReviewStore(job.out_dir).pending())
            cards.append(Card(job, job.label, self.thumb(job, lambda j=job: j.build_sheet()),
                              note=f'{waiting} to review' if waiting else 'from ' + job.example_label,
                              note_color=STATUS_COLORS[pose_review.PENDING] if waiting else TEXT_DIM,
                              size=(CARD_W, CARD_H)))
        sections.append((f'Unfinished new {domain.key}', cards))
        for key in [k.key for k in domain.kinds] + [UNSORTED, REFERENCE]:
            cards = [Card(s, s.label, self.thumb(s, lambda s=s: s.surface), note=s.where, size=(CARD_W, CARD_H))
                     for s in sprites if s.kind == key]
            if not cards and key not in (UNSORTED, REFERENCE):
                card = Card(('empty', key), 'No sprite yet', self.empty,
                            note='start from any sprite', size=(CARD_W, CARD_H))
                card.counted = False
                cards = [card]
            sections.append((domain.kind_title(key), cards))
        self.grid.set_sections(sections)

    def header(self):
        return (self.domain.title,
                f'Click: a new {self.domain.noun} from it. Right-click: its kind. '
                'GIMP / G: edit it. Cross: scrap an unfinished one. Tab: humans, plants, buildings. '
                'Escape: start page.')

    def footer(self):
        return (self.app.home_button,) + tuple(self.switch_buttons), (self.app.settings_button,)

    def back(self):
        self.app.go_home()
        return True

    def draw(self, screen, mouse):
        area = self.app.card_area()
        summary = pygame.Rect(area.x, area.y, area.w, SUMMARY_H)
        draw_summary(screen, self.app.fonts, summary, self.stats, self.domain.noun)
        top = summary.bottom + PANEL_GAP
        self.grid.layout(pygame.Rect(area.x, top, area.w, area.bottom - top))
        self.grid.draw(screen, self.app.fonts, mouse)
        card = self.grid.card_at(mouse)
        if card and isinstance(card.key, SpriteJob):
            self.draw_cross(screen, card, mouse)
        elif card and getattr(card.key, 'path', None):
            self.draw_gimp_button(screen, card, mouse)

    @staticmethod
    def cross_rect(card):
        return pygame.Rect(card.rect.right - CROSS_INSET - 2 * CROSS_R, card.rect.y + CROSS_INSET,
                           2 * CROSS_R, 2 * CROSS_R)

    def draw_cross(self, screen, card, mouse):
        """The cross scrapping an unfinished sprite; red under the mouse, or once clicked for one with answers."""
        rect = self.cross_rect(card)
        hot = rect.collidepoint(mouse) or self.armed is card.key
        screen.set_clip(self.grid.area)
        pygame.draw.circle(screen, CROSS_HOVER if hot else CROSS_BG, rect.center, CROSS_R)
        arm = CROSS_R // 2 - 1
        for dx in (-arm, arm):
            pygame.draw.line(screen, TEXT, (rect.centerx - dx, rect.centery - arm),
                             (rect.centerx + dx, rect.centery + arm), 3)
        screen.set_clip(None)

    @staticmethod
    def gimp_rect(card):
        return pygame.Rect((card.rect.x + CROSS_INSET, card.rect.y + CROSS_INSET), GIMP_BUTTON)

    def draw_gimp_button(self, screen, card, mouse):
        """The button opening the sprite's file in GIMP."""
        rect = self.gimp_rect(card)
        screen.set_clip(self.grid.area)
        pygame.draw.rect(screen, GIMP_HOVER if rect.collidepoint(mouse) else CROSS_BG, rect, border_radius=6)
        label = self.app.fonts.small.render('GIMP', True, TEXT)
        screen.blit(label, label.get_rect(center=rect.center))
        screen.set_clip(None)

    def scrap(self, job):
        """Delete an unfinished sprite; one with answers only on the second click."""
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
        for button in self.switch_buttons:
            if button.hit(pos):
                self.app.switch_to(button.screen)
                return
        card = self.grid.card_at(pos)
        if card and isinstance(card.key, SpriteJob) and self.cross_rect(card).collidepoint(pos):
            self.scrap(card.key)
            return
        if card and getattr(card.key, 'path', None) and self.gimp_rect(card).collidepoint(pos):
            self.app.edit_in_gimp(self.domain, card.key.path)
            return
        self.armed = None
        if not card:
            return
        key = card.key
        if isinstance(key, tuple):
            self.app.set_status(f'No {self.domain.kind_title(key[1]).lower()} yet: start from any sprite, '
                                f'then pick the type on the next screen')
        elif isinstance(key, SpriteJob):
            self.app.open_job(key)
        else:
            self.app.start_job(self.domain, key)

    def right_click(self, pos):
        card = self.grid.card_at(pos)
        if card and hasattr(card.key, 'surface'):
            self.app.dialog = KindDialog(self.domain, card.key, self.app)

    def key(self, event):
        if event.key == pygame.K_TAB:
            self.app.switch_to_next()
        elif event.key == pygame.K_g:
            card = self.grid.card_at(pygame.mouse.get_pos())
            if card and getattr(card.key, 'path', None):
                self.app.edit_in_gimp(self.domain, card.key.path)

    def scroll_by(self, steps):
        self.grid.scroll_by(steps)


class KindDialog:
    """Set a listed sprite's kind and subcategory in its domain's catalog."""

    WIDTH = 620

    def __init__(self, domain, sprite, app):
        self.domain = domain
        self.sprite = sprite
        self.app = app
        self.kind = sprite.kind if sprite.kind in domain.sortable else None
        self.field = TextField(sprite.subcategory, placeholder='subcategory (optional)')
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
        screen.blit(title.render(f'Kind of {self.domain.noun}', True, TEXT), (x, y))
        y += 48
        screen.blit(small.render(self.sprite.where, True, TEXT_DIM), (x, y))
        y += 26
        self.chips, y = draw_chips(screen, small, self.domain.sortable, self.domain.kind_title, self.kind,
                                   x, y, w, mouse)
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
            self.app.catalog(self.domain).set_kind(self.sprite, self.kind, self.field.text.strip())
        except OSError as exc:
            self.error = str(exc)
            return None
        self.app.set_status(f'{self.sprite.where} is now {self.domain.kind_title(self.kind)}')
        self.app.reload_library(self.domain)
        return self.close()

    def close(self):
        self.field.focus(False)
        return 'close'
