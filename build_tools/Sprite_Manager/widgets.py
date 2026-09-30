"""Drawing pieces shared by the views: panels, card grids, notices.

Buttons, cards and colours come from create_new_pose.py, so both tools
look alike.
"""

from collections import namedtuple

import pygame

import pose_review
from create_new_pose import (
    BAR_BG, CARD_BG, CARD_GAP, CARD_HOVER, CARD_SELECTED, DIALOG_BG, DIALOG_LINE, DONE_COLOR,
    SHADE, STATUS_COLORS, TEXT, TEXT_DIM, THUMB_BG, checkerboard, fit_text, window_size,
)
from images import smooth_fit, trim

Fonts = namedtuple('Fonts', 'font small title')

SCROLL_STEP = 60         # pixels per mouse wheel step
PANEL_TITLE = 22         # room above a panel for its title
BAR_STEP = 9             # from one progress bar of a card to the next
SECTION_HEADER = 42      # a section's title line in a SectionGrid, as in create_new_NPC.py

# The notice in the middle of the window after something was done
TOAST_HOLD_MS = 700      # fully visible for this long
TOAST_FADE_MS = 600      # then fades out over this long
TOAST_PAD = (36, 20)
TOAST_BG = (30, 28, 26)
TOAST_LINE = (110, 190, 120)

# An accepted frame next to the goal it was aimed at
COMPARE_TILES = ('Goal', 'Accepted', 'Both')
COMPARE_PAD = 12
COMPARE_OVERLAY_ALPHA = 150


def draw_panel(screen, fonts, rect, title):
    """A card-coloured panel with its title just above it."""
    pygame.draw.rect(screen, CARD_BG, rect, border_radius=8)
    text = fonts.small.render(fit_text(fonts.small, title, rect.w), True, TEXT_DIM)
    screen.blit(text, (rect.x + 4, rect.y - 20))


def draw_dialog_box(screen, rect):
    """Shade the window and draw a dialog's box on top."""
    shade = pygame.Surface(window_size(), pygame.SRCALPHA)
    shade.fill(SHADE)
    screen.blit(shade, (0, 0))
    pygame.draw.rect(screen, DIALOG_BG, rect, border_radius=10)
    pygame.draw.rect(screen, DIALOG_LINE, rect, 2, border_radius=10)


def draw_card(screen, fonts, card, mouse, selected=False):
    """A create_new_pose.Card: thumb, label, note lines and progress bar."""
    if selected:
        color = CARD_SELECTED
    elif card.rect.collidepoint(mouse):
        color = CARD_HOVER
    else:
        color = CARD_BG
    small = fonts.small
    pygame.draw.rect(screen, color, card.rect, border_radius=8)
    thumb_w, thumb_h = card.thumb.get_size()
    screen.blit(card.thumb, (card.rect.x + (card.rect.w - thumb_w) // 2, card.rect.y + 10))
    y = card.rect.y + thumb_h + 16
    width = card.rect.w - 12
    label = small.render(fit_text(small, card.label, width), True, TEXT)
    screen.blit(label, label.get_rect(midtop=(card.rect.centerx, y)))
    for note, note_color in card.lines():
        y += 18
        text = small.render(fit_text(small, note, width), True, note_color)
        screen.blit(text, text.get_rect(midtop=(card.rect.centerx, y)))
    if card.progress is None:
        return
    # One share, or several drawn as bars stacked in the order of the note lines
    shares = card.progress if isinstance(card.progress, (tuple, list)) else (card.progress,)
    for index, share in enumerate(shares):
        from_bottom = 13 + (len(shares) - 1 - index) * BAR_STEP
        bar = pygame.Rect(card.rect.x + 12, card.rect.bottom - from_bottom, card.rect.w - 24, 5)
        pygame.draw.rect(screen, BAR_BG, bar, border_radius=3)
        share = max(0.0, min(1.0, share))
        if round(bar.w * share):
            bar_color = STATUS_COLORS[pose_review.ACCEPTED] if share >= 1 else DONE_COLOR
            pygame.draw.rect(screen, bar_color, (bar.x, bar.y, round(bar.w * share), bar.h),
                             border_radius=3)


class CardGrid:
    """Cards laid out in rows inside an area, scrolled with the mouse wheel."""

    def __init__(self, centred=True):
        self.cards = []
        self.centred = centred
        self.scroll = 0
        self.max_scroll = 0
        self.area = pygame.Rect(0, 0, 0, 0)

    def layout(self, area):
        """Place the cards inside `area`, from the current scroll position."""
        self.area = area
        if not self.cards:
            self.max_scroll = self.scroll = 0
            return
        card_w, card_h = self.cards[0].rect.size
        per_row = max(1, (area.w + CARD_GAP) // (card_w + CARD_GAP))
        rows = (len(self.cards) + per_row - 1) // per_row
        self.max_scroll = max(0, rows * (card_h + CARD_GAP) - CARD_GAP - area.h)
        self.scroll = min(self.scroll, self.max_scroll)
        row_w = per_row * card_w + (per_row - 1) * CARD_GAP
        left = area.x + (max(0, (area.w - row_w) // 2) if self.centred else 0)
        for index, card in enumerate(self.cards):
            row, col = divmod(index, per_row)
            card.rect.topleft = (left + col * (card_w + CARD_GAP),
                                 area.y + row * (card_h + CARD_GAP) - self.scroll)

    def scroll_by(self, steps):
        self.scroll = max(0, min(self.max_scroll, self.scroll - steps * SCROLL_STEP))

    def draw(self, screen, fonts, mouse, selected_key=None):
        screen.set_clip(self.area)
        for card in self.cards:
            if card.rect.colliderect(self.area):
                draw_card(screen, fonts, card, mouse, card.key == selected_key)
        screen.set_clip(None)

    def card_at(self, pos):
        """The card under a click, or None."""
        if self.area.collidepoint(pos):
            for card in self.cards:
                if card.rect.collidepoint(pos):
                    return card
        return None


class SectionGrid(CardGrid):
    """A CardGrid in titled sections, each starting on a row of its own."""

    def __init__(self, noun='card'):
        """
        Args:
            noun: What a card is, for the count beside each title ('NPC').
        """
        super().__init__()
        self.noun = noun
        self.sections = []   # [(title, [cards])]
        self.titles = []     # [(title, count, x, y)] as last laid out

    def set_sections(self, sections):
        """[(title, [cards])]; empty sections are left out."""
        self.sections = [(title, cards) for title, cards in sections if cards]
        self.cards = [card for _, cards in self.sections for card in cards]

    def layout(self, area):
        """Place the sections one under the other; each section's cards share one size."""
        self.area = area
        self.titles = []
        if not self.cards:
            self.max_scroll = self.scroll = 0
            return
        # The rows line up on the widest card, whatever the section.
        card_w = max(card.rect.w for card in self.cards)
        per_row = max(1, (area.w + CARD_GAP) // (card_w + CARD_GAP))
        row_w = per_row * card_w + (per_row - 1) * CARD_GAP
        left = area.x + max(0, (area.w - row_w) // 2)
        y = area.y - self.scroll
        for title, cards in self.sections:
            card_h = cards[0].rect.h
            self.titles.append((title, len(cards), left, y))
            y += SECTION_HEADER
            for index, card in enumerate(cards):
                row, col = divmod(index, per_row)
                card.rect.topleft = (left + col * (card_w + CARD_GAP), y + row * (card_h + CARD_GAP))
            y += ((len(cards) + per_row - 1) // per_row) * (card_h + CARD_GAP)
        height = y + self.scroll - area.y - CARD_GAP
        self.max_scroll = max(0, height - area.h)
        if self.scroll > self.max_scroll:  # the window grew: lay out again from the new scroll
            self.scroll = self.max_scroll
            self.layout(area)

    def draw(self, screen, fonts, mouse, selected_key=None):
        screen.set_clip(self.area)
        for title, count, x, y in self.titles:
            text = fonts.font.render(title, True, TEXT)
            screen.blit(text, (x, y + 8))
            number = fonts.small.render(f'{count} {self.noun}{"" if count == 1 else "s"}', True, TEXT_DIM)
            screen.blit(number, (x + text.get_width() + 12, y + 11))
            line_x = x + text.get_width() + number.get_width() + 24
            pygame.draw.line(screen, CARD_BG, (line_x, y + 21), (self.area.right - (x - self.area.x), y + 21))
        screen.set_clip(None)
        super().draw(screen, fonts, mouse, selected_key)


class Checker:
    """A checkerboard backdrop for transparent images, rebuilt only when it grows."""

    def __init__(self):
        self.board = checkerboard((1, 1))

    def draw(self, screen, rect):
        area = pygame.Rect((0, 0), rect.size)
        if not self.board.get_rect().contains(area):
            self.board = checkerboard(rect.size)
        screen.blit(self.board, rect, area)


class Toast:
    """A short notice in the middle of the window: solid for a moment, then fading."""

    def __init__(self):
        self.text = ''
        self.start = 0

    def show(self, text):
        self.text, self.start = text, pygame.time.get_ticks()

    def draw(self, screen, fonts):
        if not self.text:
            return
        age = pygame.time.get_ticks() - self.start
        if age >= TOAST_HOLD_MS + TOAST_FADE_MS:
            self.text = ''
            return
        fade = max(0, age - TOAST_HOLD_MS) / TOAST_FADE_MS
        label = fonts.title.render(self.text, True, TEXT)
        box = pygame.Surface((label.get_width() + 2 * TOAST_PAD[0],
                              label.get_height() + 2 * TOAST_PAD[1]), pygame.SRCALPHA)
        rect = box.get_rect()
        pygame.draw.rect(box, TOAST_BG + (235,), rect, border_radius=12)
        pygame.draw.rect(box, TOAST_LINE, rect, 3, border_radius=12)
        box.blit(label, label.get_rect(center=rect.center))
        box.set_alpha(round(255 * (1 - fade)))
        width, height = window_size()
        screen.blit(box, box.get_rect(center=(width // 2, height // 2)))


class Comparison:
    """Goal, accepted frame and both on top of each other, as COMPARE_TILES tiles.

    The ghost and a saved frame are both at the scale of the NPC's standing
    sprite, so they are compared pixel for pixel: trimmed, standing on one
    ground line and centred alike. In the third tile the frame is see-through
    over the solid ghost, so it shows where the pose drifted from the goal.
    """

    def __init__(self, ghost, sprite):
        ghost, sprite = trim(ghost), trim(sprite)
        tile_w = max(ghost.get_width(), sprite.get_width()) + 2 * COMPARE_PAD
        tile_h = max(ghost.get_height(), sprite.get_height()) + 2 * COMPARE_PAD
        overlay = sprite.copy()
        overlay.set_alpha(COMPARE_OVERLAY_ALPHA)
        layers = ((ghost,), (sprite,), (ghost, overlay))
        self.tile_w = tile_w
        self.image = pygame.Surface((len(layers) * tile_w + (len(layers) - 1) * COMPARE_PAD, tile_h))
        self.image.fill(CARD_BG)
        for index, tile_layers in enumerate(layers):
            tile = pygame.Rect(index * (tile_w + COMPARE_PAD), 0, tile_w, tile_h)
            self.image.fill(THUMB_BG, tile)
            for layer in tile_layers:
                self.image.blit(layer, layer.get_rect(midbottom=(tile.centerx, tile.bottom - COMPARE_PAD)))

    def draw(self, screen, fonts, area):
        """The tiles fitted into the foot of `area`, each named above it."""
        label_h = fonts.small.get_linesize()
        shown = smooth_fit(self.image, (area.w, area.h - label_h))
        factor = shown.get_width() / self.image.get_width()
        pos = shown.get_rect(midbottom=(area.centerx, area.bottom))
        screen.blit(shown, pos)
        for index, name in enumerate(COMPARE_TILES):
            centre = pos.x + (index * (self.tile_w + COMPARE_PAD) + self.tile_w / 2) * factor
            label = fonts.small.render(name, True, TEXT_DIM)
            screen.blit(label, label.get_rect(midbottom=(centre, pos.y - 2)))
