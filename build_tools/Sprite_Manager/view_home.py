"""The start page: all sprites at a glance, and a big card into each of humans, plants, buildings and crops.

Along the top, over everything:

    All sprites   how many there are, and how many of them humans, plants, buildings
    Today         sprites new and redone today, by their file dates
    Work          answers waiting for review, and unfinished new plants and buildings

Under it one card per area; clicking it (or 1, 2, 3, 4; Tab is the humans)
opens it, and Escape there comes back here.

    Humans        the share of their sprites done, a bar per kind, and the figures
    Plants        how many, one bar split by kind with the biggest kinds, and the newest
    Buildings     the same
    Crops         the share of their stage sprites done, a bar per stage, and the ripe crops

The pictures fill whatever room the card has left, so a taller window shows more.
"""

from dataclasses import dataclass, field
from typing import Optional

import pygame

import pose_review
from crops import find_crops
from daily_progress import Today, made_today
from figures import TRADER_CATEGORY
from images import pixel_fit
from library_summary import Stats, gather, mini
from npc import PLAYER_CATEGORY
from pose_review import ReviewStore
from theme import BAR_BG, CARD_BG, CARD_HOVER, DONE_COLOR, PANEL_GAP, STATUS_COLORS, TEXT, TEXT_DIM, THUMB_BG
from view import View
from view_npcs import KINDS, figure_progress
from widgets import draw_panel, fit_text, progress_color

SUMMARY_H = 96
PAD = 18
ROW_H = 24
BAR_H = 8
LABEL_W = 116
COUNT_W = 70
PICTURE = 58             # the small pictures along an area's card
PICTURE_GAP = 8
WORK_H = 52              # the work line and the hint along a card's foot
NEW_COLOR = STATUS_COLORS[pose_review.ACCEPTED]
WAIT_COLOR = STATUS_COLORS[pose_review.PENDING]


@dataclass
class Humans:
    figures: int = 0
    traders: int = 0
    townsfolk: int = 0
    totals: dict = field(default_factory=dict)   # {kind: [done, needed]}
    waiting: int = 0
    today: Today = Today(0, 0)

    @property
    def done(self):
        return sum(done for done, _ in self.totals.values())

    @property
    def needed(self):
        return sum(needed for _, needed in self.totals.values())


def gather_humans(app):
    """The numbers of the humans' card, counted as their own screen counts them."""
    humans = Humans()
    for figure in app.npcs + app.new_figures:
        humans.figures += 1
        humans.traders += figure.category == TRADER_CATEGORY
        humans.townsfolk += figure.category not in (TRADER_CATEGORY, PLAYER_CATEGORY)
        for kind, done, needed in figure_progress(app, figure):
            totals = humans.totals.setdefault(kind, [0, 0])
            totals[0] += done
            totals[1] += needed
        humans.waiting += len(ReviewStore(figure.out_dir).pending())
    humans.today = made_today()
    return humans


@dataclass
class Crops:
    crops: int = 0
    stages: list = field(default_factory=list)   # [(stage title, done, needed)] over all crops, by stage
    done: int = 0
    needed: int = 0
    waiting: int = 0
    today: Optional[Today] = None
    pictures: list = field(default_factory=list)  # the crops' pictures


def gather_crops():
    """The numbers of the crops' card: their stage sprites by stage, summed over the crops by stage title."""
    totals = {}
    stats = Crops()
    paths = []
    for crop in find_crops():
        stats.crops += 1
        for stage in crop.growing:
            row = totals.setdefault(stage.title, [0, 0])
            row[0] += crop.done(stage)
            row[1] += crop.needed(stage)
            paths += [crop.sprite_path(stage.key, v) for v in range(1, crop.variants + 1)]
        stats.waiting += len(ReviewStore(crop.out_dir).pending())
        sprite = crop.thumb_sprite()
        if sprite is not None:
            stats.pictures.append(HomeView.face(sprite.subsurface(sprite.get_bounding_rect())))
    stats.stages = [(title, done, needed) for title, (done, needed) in totals.items()]
    stats.done = sum(done for _, done, _ in stats.stages)
    stats.needed = sum(needed for _, _, needed in stats.stages)
    stats.today = made_today([p for p in paths if p.is_file()])
    return stats


class Area:
    """One of the three cards: which screen it opens, and its rect as last drawn."""

    def __init__(self, key, title, shortcut):
        self.key = key
        self.title = title
        self.shortcut = shortcut
        self.rect = pygame.Rect(0, 0, 0, 0)


class HomeView(View):
    def __init__(self, app):
        super().__init__(app)
        self.areas = [Area(key, title, str(index + 1)) for index, (key, title) in enumerate(app.screens())]
        self.humans = Humans()
        self.domains = {}    # {domain key: library_summary.Stats}
        self.today = {}      # {domain key: Today}, of the plants' and buildings' files
        self.faces = []      # small pictures of the figures, for the humans' card
        self.crops = Crops()

    def refresh(self):
        app = self.app
        self.humans = gather_humans(app)
        for domain in app.domains():
            sprites = app.library(domain)
            self.domains[domain.key] = gather(domain, sprites, app.jobs(domain), app.atlas_fills)
            self.today[domain.key] = made_today([s.path for s in sprites if s.path])
        self.faces = [self.face(app.npc_thumbs[n.name]) for n in app.npcs]
        self.crops = gather_crops()

    @staticmethod
    def face(thumb):
        tile = pygame.Surface((PICTURE, PICTURE))
        tile.fill(THUMB_BG)
        image = pixel_fit(thumb, (PICTURE - 4, PICTURE - 4))
        tile.blit(image, image.get_rect(center=tile.get_rect().center))
        return tile

    def header(self):
        return ('Sprite Manager',
                'Every sprite of the game at a glance. Click an area, or press 1 to 4, to work on it; '
                'Escape there comes back here, and here closes the tool.')

    def footer(self):
        return (), (self.app.settings_button,)

    def stats(self, key):
        return self.domains.get(key, Stats())

    # --- drawing ----------------------------------------------------------

    def draw(self, screen, mouse):
        area = self.app.card_area()
        self.draw_summary(screen, pygame.Rect(area.x, area.y, area.w, SUMMARY_H))
        top = area.y + SUMMARY_H + PANEL_GAP + 8
        height = area.bottom - top
        width = (area.w - (len(self.areas) - 1) * PANEL_GAP) // len(self.areas)
        for index, card in enumerate(self.areas):
            card.rect = pygame.Rect(area.x + index * (width + PANEL_GAP), top, width, height)
            self.draw_area(screen, card, mouse)

    def draw_summary(self, screen, rect):
        """All sprites, today's and the work waiting, over the three areas."""
        third = (rect.w - 2 * PANEL_GAP) // 3
        panels = [pygame.Rect(rect.x + i * (third + PANEL_GAP), rect.y, third, rect.h) for i in range(3)]
        domains = {key: self.stats(key).total for key in self.domains}
        counts = [('humans', self.humans.done)] + list(domains.items()) + [('crops', self.crops.done)]
        self.draw_numbers(screen, panels[0], 'All sprites', [(sum(n for _, n in counts), 'sprites', TEXT)],
                          ', '.join(f'{n} {key}' for key, n in counts))
        today = [self.humans.today, *self.today.values(), self.crops.today or Today(0, 0)]
        new = sum(t.new for t in today)
        redone = sum(t.redone for t in today)
        self.draw_numbers(screen, panels[1], 'Today', [(new, 'new', NEW_COLOR), (redone, 'redone', DONE_COLOR)])
        waiting = self.humans.waiting + self.crops.waiting + sum(self.stats(key).waiting for key in self.domains)
        unfinished = sum(self.stats(key).unfinished for key in self.domains)
        self.draw_numbers(screen, panels[2], 'Work',
                          [(waiting, 'to review', WAIT_COLOR), (unfinished, 'unfinished', DONE_COLOR)])

    def draw_numbers(self, screen, panel, title, numbers, note=''):
        """A panel of big numbers side by side, each with its label, and a dim line under them."""
        fonts = self.app.fonts
        draw_panel(screen, fonts, panel, title)
        part = panel.w // len(numbers)
        for index, (number, label, color) in enumerate(numbers):
            centre = panel.x + part * index + part // 2
            big = fonts.title.render(str(number), True, color if number else TEXT_DIM)
            text = fonts.small.render(label, True, TEXT_DIM)
            height = big.get_height() + text.get_height()
            y = panel.centery - height // 2 - (9 if note else 0)
            screen.blit(big, big.get_rect(midtop=(centre, y)))
            screen.blit(text, text.get_rect(midtop=(centre, y + big.get_height() - 4)))
            if index:
                pygame.draw.line(screen, BAR_BG, (panel.x + part * index, panel.y + 14),
                                 (panel.x + part * index, panel.bottom - 14), 2)
        if note:
            line = fonts.small.render(fit_text(fonts.small, note, panel.w - 2 * PAD), True, TEXT_DIM)
            screen.blit(line, line.get_rect(midbottom=(panel.centerx, panel.bottom - 8)))

    def draw_area(self, screen, card, mouse):
        """An area's card: its title and big number, its pictures, its rows and its work."""
        fonts = self.app.fonts
        rect = card.rect
        hover = rect.collidepoint(mouse)
        pygame.draw.rect(screen, CARD_HOVER if hover else CARD_BG, rect, border_radius=10)
        if hover:
            pygame.draw.rect(screen, DONE_COLOR, rect, 2, border_radius=10)
        clip = screen.get_clip()
        screen.set_clip(rect)
        inner = rect.inflate(-2 * PAD, -2 * PAD)

        if card.key == 'humans':
            humans = self.humans
            share = humans.done / humans.needed if humans.needed else 0
            big, big_color = f'{humans.done * 100 // max(1, humans.needed)}%', progress_color(share)
            subtitle = f'{humans.figures} figures: {humans.traders} traders, {humans.townsfolk} townsfolk'
            pictures = self.faces
        elif card.key == 'crops':
            crops = self.crops
            share = crops.done / crops.needed if crops.needed else 0
            big, big_color = f'{crops.done * 100 // max(1, crops.needed)}%', progress_color(share)
            subtitle = f'{crops.crops} crop{"" if crops.crops == 1 else "s"}, {crops.done} of {crops.needed} stage sprites'
            pictures = crops.pictures
        else:
            stats = self.stats(card.key)
            big, big_color = str(stats.total), TEXT
            parts = [f'{stats.singles} files'] + ([f'{stats.motifs} cut out'] if stats.motifs else [])
            subtitle = f'{stats.total} sprites: ' + ', '.join(parts)
            pictures = [mini(sprite) for sprite in stats.newest]   # made lazily: only the first few are drawn

        title = fonts.title.render(card.title, True, TEXT)
        screen.blit(title, inner.topleft)
        number = fonts.title.render(big, True, big_color)
        screen.blit(number, number.get_rect(topright=inner.topright))
        y = inner.y + title.get_height()
        line = fonts.small.render(fit_text(fonts.small, subtitle, inner.w), True, TEXT_DIM)
        screen.blit(line, (inner.x, y))
        y += line.get_height() + 16

        if card.key == 'humans':
            y = self.draw_kind_rows(screen, inner, y)
        elif card.key == 'crops':
            y = self.draw_stage_rows(screen, inner, y)
        else:
            y = self.draw_kinds(screen, inner, y, self.stats(card.key))
        self.draw_pictures(screen, pygame.Rect(inner.x, y + 12, inner.w, inner.bottom - WORK_H - 12 - y - 12),
                           pictures)
        self.draw_work(screen, card, inner)
        screen.set_clip(clip)

    @staticmethod
    def draw_pictures(screen, rect, pictures):
        """The figures, or the newest sprites, in rows, as many as fit into `rect`."""
        per_row = max(1, (rect.w + PICTURE_GAP) // (PICTURE + PICTURE_GAP))
        rows = max(0, (rect.h + PICTURE_GAP) // (PICTURE + PICTURE_GAP))
        for index, picture in enumerate(pictures[:per_row * rows]):
            row, col = divmod(index, per_row)
            screen.blit(picture, (rect.x + col * (PICTURE + PICTURE_GAP), rect.y + row * (PICTURE + PICTURE_GAP)))

    def draw_kind_rows(self, screen, inner, y):
        """The humans: a bar per kind of sprite, with done / needed."""
        fonts = self.app.fonts
        for kind, label in KINDS:
            done, needed = self.humans.totals.get(kind, (0, 0))
            if not needed:
                continue
            self.draw_row(screen, inner, y, label, done / needed, f'{done} / {needed}', progress_color(done / needed))
            y += ROW_H
        missing = self.humans.needed - self.humans.done
        text = fonts.small.render(f'{missing} still to make' if missing else 'all done', True, TEXT_DIM)
        screen.blit(text, (inner.x, y + 4))
        return y + ROW_H

    def draw_stage_rows(self, screen, inner, y):
        """The crops: a bar per growth stage, with done / needed."""
        for title, done, needed in self.crops.stages:
            self.draw_row(screen, inner, y, title, done / max(1, needed), f'{done} / {needed}',
                          progress_color(done / max(1, needed)))
            y += ROW_H
        return y

    def draw_kinds(self, screen, inner, y, stats):
        """Plants or buildings: one bar split by kind, then the kinds largest first."""
        total = sum(n for _, n, _ in stats.kinds) or 1
        bar = pygame.Rect(inner.x, y, inner.w, BAR_H + 4)
        pygame.draw.rect(screen, BAR_BG, bar, border_radius=bar.h // 2)
        shown = [(title, n, color) for title, n, color in stats.kinds if n]
        x = bar.x
        for index, (_, n, color) in enumerate(shown):
            width = bar.right - x if index == len(shown) - 1 else round(bar.w * n / total)
            pygame.draw.rect(screen, color, (x, bar.y, width, bar.h))
            x += width
        y = bar.bottom + 12
        biggest = max((n for _, n, _ in shown), default=1)
        for title, n, color in sorted(shown, key=lambda k: -k[1]):
            self.draw_row(screen, inner, y, title, n / biggest, str(n), color)
            y += ROW_H
        return y

    def draw_row(self, screen, inner, y, label, share, count, color):
        """A label, a bar filled to `share` and a count, on one line."""
        small = self.app.fonts.small
        middle = y + ROW_H // 2
        text = small.render(fit_text(small, label, LABEL_W - 6), True, TEXT)
        screen.blit(text, text.get_rect(midleft=(inner.x, middle)))
        bar = pygame.Rect(inner.x + LABEL_W, middle - BAR_H // 2, max(20, inner.w - LABEL_W - COUNT_W), BAR_H)
        pygame.draw.rect(screen, BAR_BG, bar, border_radius=BAR_H // 2)
        if round(bar.w * share):
            pygame.draw.rect(screen, color, (bar.x, bar.y, max(BAR_H, round(bar.w * share)), bar.h),
                             border_radius=BAR_H // 2)
        number = small.render(count, True, TEXT)
        screen.blit(number, number.get_rect(midright=(inner.right, middle)))

    def draw_work(self, screen, card, inner):
        """Along the card's foot: what is waiting there, and how to open it."""
        small = self.app.fonts.small
        if card.key == 'humans':
            humans = self.humans
            work = [(humans.waiting, 'to review', WAIT_COLOR), (humans.today.new, 'new today', NEW_COLOR),
                    (humans.today.redone, 'redone today', DONE_COLOR)]
        elif card.key == 'crops':
            today = self.crops.today or Today(0, 0)
            work = [(self.crops.waiting, 'to review', WAIT_COLOR), (today.new, 'new today', NEW_COLOR),
                    (today.redone, 'redone today', DONE_COLOR)]
        else:
            stats = self.stats(card.key)
            work = [(stats.waiting, 'to review', WAIT_COLOR), (stats.unfinished, 'unfinished', DONE_COLOR),
                    (stats.today, 'new today', NEW_COLOR)]
        x = inner.x
        bottom = inner.bottom
        for number, label, color in work:
            text = small.render(f'{number} {label}', True, color if number else TEXT_DIM)
            screen.blit(text, text.get_rect(bottomleft=(x, bottom - 26)))
            x += text.get_width() + 18
        hint = small.render(f'Open ({card.shortcut})', True, TEXT_DIM)
        screen.blit(hint, hint.get_rect(bottomleft=(inner.x, bottom)))
        pygame.draw.line(screen, BAR_BG, (inner.x, bottom - WORK_H), (inner.right, bottom - WORK_H), 2)

    # --- input ------------------------------------------------------------

    def click(self, pos):
        for card in self.areas:
            if card.rect.collidepoint(pos):
                self.app.switch_to(card.key)
                return

    def key(self, event):
        for card in self.areas:
            if event.unicode == card.shortcut:
                self.app.switch_to(card.key)
                return
        if event.key == pygame.K_TAB:
            self.app.switch_to(self.areas[0].key)
