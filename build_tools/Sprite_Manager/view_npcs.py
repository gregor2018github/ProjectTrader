"""Screen 1: the player and every NPC, in their groups, with how far their sprites are."""

import pygame

import pose_review
from daily_progress import made_today
from figures import CATEGORIES, OTHER, TRADER_CATEGORY
from new_figure import name_usage
from npc import PLAYER_CATEGORY
from pose_review import ReviewStore
from theme import (
    BAR_BG, CARD_BG, DONE_COLOR, NPC_THUMB_SIZE, PANEL_GAP, STATUS_COLORS, TEXT, TEXT_DIM, THUMB_BG,
)
from view import View
from walk import DIRECTIONS, NPC_DIRECTION_KEYS, STANDING_DIRECTIONS
from widgets import BAR_STEP, Button, Card, SectionGrid, draw_panel, fit_text, progress_color

# An NPC's card, with a line and a bar per motion and the standing sprites
CARD_W = 172
CARD_BASE_H = 244        # with one line and one bar
LINE_H = 18
SECTIONS = ((PLAYER_CATEGORY, 'Main character'),) + tuple(
    (key, title) for key, title, _ in CATEGORIES + (OTHER,))
ADDABLE = {key for key, _, can_add in CATEGORIES if can_add}   # the groups with a "+" card
NPC_CARD_H = CARD_BASE_H + LINE_H + BAR_STEP   # an NPC's card: walk frames and standing sprites

# The overview above the cards: all sprites, today's, the names
SUMMARY_H = 112
SUMMARY_PAD = 14
SUMMARY_ROW = 28
FIGURES_W = 170
HERO_W = 150             # the big percentage of all sprites done
TODAY_W = 180
NAMES_SHARE = 0.27       # of the width; at least NAMES_MIN_W
NAMES_MIN_W = 300
BAR_H = 8
BAR_MAX_W = 440          # bars stop growing here, so a wide window does not stretch them thin
BAR_MIN_W = 100         # narrower than this, a row leaves out its dim last column
ROW_GAP = 12             # between the columns of a row
NEW_COLOR = STATUS_COLORS[pose_review.ACCEPTED]
POOL_USED_UP = (220, 90, 70)   # a name pool with nothing left
NAME_POOLS = (('female', 'Women'), ('male', 'Men'))
KINDS = (('walk', 'Walk frames'), ('run', 'Run frames'), ('standing', 'Standing sprites'))


class NpcListView(View):
    def __init__(self, app):
        super().__init__(app)
        self.grid = SectionGrid('figure')  # filled by refresh(), when the app shows the view
        self.totals = {}                   # {kind: [done, needed]} over everyone listed
        self.names = ({}, [])              # new_figure.name_usage()
        self.today = None                  # daily_progress.Today
        self.plants_button = Button('Plants', w=120)
        self.placeholder = pygame.Surface(NPC_THUMB_SIZE)
        self.placeholder.fill(THUMB_BG)
        text = app.fonts.small.render('no sprite yet', True, (120, 120, 120))
        self.placeholder.blit(text, text.get_rect(center=self.placeholder.get_rect().center))
        self.plus = pygame.Surface(NPC_THUMB_SIZE)
        self.plus.fill(CARD_BG)
        plus = pygame.font.SysFont('segoeui', 90).render('+', True, TEXT_DIM)
        self.plus.blit(plus, plus.get_rect(center=self.plus.get_rect().center))

    def npc_card(self, npc):
        """The figure's card: a line and a bar per motion, and the standing sprites."""
        app = self.app
        done_color = STATUS_COLORS[pose_review.ACCEPTED]
        lines, shares = [], []
        for motion in npc.motions:
            total = npc.total_frames(app.counts, motion)
            done = sum(npc.done(d, app.counts[d]) for d in npc.directions(motion))
            lines.append((f'{done}/{total} {motion.key} frames', done_color if done == total else TEXT_DIM))
            shares.append(done / max(1, total))
            self.count(motion.key, done, total)
        standing_total = len(STANDING_DIRECTIONS)
        standing_done = npc.standing_done()
        self.count('standing', standing_done, standing_total)
        lines.append((f'{standing_done}/{standing_total} standing sprites',
                      done_color if standing_done == standing_total else TEXT_DIM))
        shares.append(standing_done / standing_total)
        waiting = len(ReviewStore(npc.out_dir).pending())
        if waiting:
            lines.append((f'{waiting} to review', STATUS_COLORS[pose_review.PENDING]))

        # Room for every line beyond the first, even the review line, so cards stay one size
        extra_rows = len(shares) - 1
        size = (CARD_W, CARD_BASE_H + extra_rows * (LINE_H + BAR_STEP))
        (note, note_color), extra = lines[0], lines[1:]
        return Card(npc, npc.label, app.npc_thumbs[npc.name], note=note, note_color=note_color,
                    extra=extra, size=size, progress=tuple(shares))

    def new_figure_card(self, figure):
        """A person without a front standing sprite: that is the next thing to make."""
        # Everything of an NPC is still to do.
        self.count('walk', 0, sum(self.app.counts[d] for d in DIRECTIONS if d.key in NPC_DIRECTION_KEYS))
        self.count('standing', 0, len(STANDING_DIRECTIONS))
        waiting = len(ReviewStore(figure.out_dir).pending())
        extra = [(f'{waiting} to review', STATUS_COLORS[pose_review.PENDING])] if waiting else []
        return Card(figure, figure.label, self.placeholder, note='make the first sprite',
                    extra=extra, size=(CARD_W, NPC_CARD_H))

    def add_card(self, key, title):
        is_trader = key == TRADER_CATEGORY
        card = Card(('add', key, title), 'Add trader' if is_trader else 'Add NPC', self.plus,
                    note='the trade' if is_trader else 'woman or man', size=(CARD_W, NPC_CARD_H))
        card.counted = False  # not one of the group's figures
        return card

    def count(self, kind, done, needed):
        """Add a figure's sprites of one kind to the overview."""
        totals = self.totals.setdefault(kind, [0, 0])
        totals[0] += done
        totals[1] += needed

    def refresh(self):
        """A section for the player, then one per group of figures.CATEGORIES, each with a "+" card."""
        app = self.app
        self.totals = {}
        self.names = name_usage()
        self.today = made_today()
        sections = []
        for key, title in SECTIONS:
            cards = [self.npc_card(n) for n in app.npcs if n.category == key]
            cards += [self.new_figure_card(f) for f in app.new_figures if f.category == key]
            if key in ADDABLE:
                cards.append(self.add_card(key, title))
            sections.append((title, cards))
        self.grid.set_sections(sections)

    def header(self):
        return ('Sprite Manager',
                'The player walks and runs in all 8 directions, the NPCs only walk: down, right, up '
                'and left. "+" adds an NPC. The left-hand walks are optional. Tab switches to the plants.')

    def footer(self):
        return (self.plants_button,), (self.app.settings_button,)

    def draw(self, screen, mouse):
        area = self.app.card_area()
        summary = pygame.Rect(area.x, area.y, area.w, SUMMARY_H)
        self.draw_summary(screen, summary)
        top = summary.bottom + PANEL_GAP
        self.grid.layout(pygame.Rect(area.x, top, area.w, area.bottom - top))
        self.grid.draw(screen, self.app.fonts, mouse)

    # --- the overview -----------------------------------------------------

    def draw_summary(self, screen, rect):
        """Four panels: the figures, all sprites done and missing, today's, and how many names are left."""
        names_w = max(NAMES_MIN_W, int(rect.w * NAMES_SHARE))
        names = pygame.Rect(rect.right - names_w, rect.y, names_w, rect.h)
        today = pygame.Rect(names.x - PANEL_GAP - TODAY_W, rect.y, TODAY_W, rect.h)
        figures = pygame.Rect(rect.x, rect.y, FIGURES_W, rect.h)
        sprites = pygame.Rect(figures.right + PANEL_GAP, rect.y, today.x - 2 * PANEL_GAP - figures.right, rect.h)
        self.draw_figures(screen, figures)
        self.draw_sprites(screen, sprites)
        self.draw_today(screen, today)
        self.draw_names(screen, names)

    def draw_figures(self, screen, panel):
        """How many figures there are, big, and how many of them are traders and townsfolk."""
        fonts = self.app.fonts
        draw_panel(screen, fonts, panel, 'Figures')
        figures = [c.key for c in self.grid.cards if getattr(c, 'counted', True)]
        traders = sum(f.category == TRADER_CATEGORY for f in figures)
        townsfolk = sum(f.category not in (TRADER_CATEGORY, PLAYER_CATEGORY) for f in figures)
        surfaces = (fonts.title.render(str(len(figures)), True, TEXT),
                    fonts.small.render('figures', True, TEXT_DIM),
                    fonts.small.render(f'{traders} traders, {townsfolk} townsfolk', True, TEXT_DIM))
        y = panel.centery - sum(s.get_height() for s in surfaces) // 2
        for surface in surfaces:
            screen.blit(surface, surface.get_rect(midtop=(panel.centerx, y)))
            y += surface.get_height()

    def draw_sprites(self, screen, panel):
        """The share of all sprites done, big, beside a bar per kind."""
        fonts = self.app.fonts
        draw_panel(screen, fonts, panel, 'All sprites')
        kinds = [(label, *self.totals.get(kind, (0, 0))) for kind, label in KINDS]
        done, needed = sum(k[1] for k in kinds), sum(k[2] for k in kinds)
        share = done / needed if needed else 0
        percent = done * 100 // needed if needed else 0   # rounded down: 100% only when all are done

        hero = pygame.Rect(panel.x, panel.y, HERO_W, panel.h)
        big = fonts.title.render(f'{percent}%', True, progress_color(share))
        lines = (fonts.font.render(f'{done} / {needed}', True, TEXT),
                 fonts.small.render(f'{needed - done} still to make', True, TEXT_DIM))
        y = hero.centery - (big.get_height() + sum(line.get_height() for line in lines)) // 2
        for surface in (big,) + lines:
            screen.blit(surface, surface.get_rect(midtop=(hero.centerx, y)))
            y += surface.get_height()
        pygame.draw.line(screen, BAR_BG, (hero.right, panel.y + SUMMARY_PAD),
                         (hero.right, panel.bottom - SUMMARY_PAD), 2)

        rows = pygame.Rect(hero.right + SUMMARY_PAD, panel.y, panel.right - hero.right - SUMMARY_PAD, panel.h)
        self.draw_rows(screen, rows, [
            (label, part, whole, f'{part} / {whole}', f'{whole - part} missing' if part < whole else 'all done')
            for label, part, whole in kinds], label_w=120)

    def draw_today(self, screen, panel):
        """The sprites new and redone today, as two big numbers."""
        fonts = self.app.fonts
        draw_panel(screen, fonts, panel, 'Today')
        new, redone = self.today
        half = panel.w // 2
        for index, (number, label, color) in enumerate(((new, 'new', NEW_COLOR), (redone, 'redone', DONE_COLOR))):
            centre = panel.x + half * index + half // 2
            big = fonts.title.render(str(number), True, color if number else TEXT_DIM)
            text = fonts.small.render(label, True, TEXT_DIM)
            y = panel.centery - (big.get_height() + text.get_height()) // 2
            screen.blit(big, big.get_rect(midtop=(centre, y)))
            screen.blit(text, text.get_rect(midtop=(centre, y + big.get_height())))
        pygame.draw.line(screen, BAR_BG, (panel.x + half, panel.y + SUMMARY_PAD),
                         (panel.x + half, panel.bottom - SUMMARY_PAD), 2)

    def draw_names(self, screen, panel):
        """How much of each name pool the townsfolk have used."""
        fonts = self.app.fonts
        usage, typed = self.names
        draw_panel(screen, fonts, panel, 'Names from medieval_names.py  -  each only once')
        rows = []
        for gender, label in NAME_POOLS:
            used, pool = usage.get(gender, (0, 0))
            rows.append((label, used, pool, f'{used} / {pool}', f'{pool - used} free'))
        bottom = self.draw_rows(screen, panel, rows, label_w=60, fill_is_good=False,
                                count_w=70, rest_w=60, lines=len(rows) + bool(typed))
        if typed:
            text = f'Not from the list: {", ".join(typed)}'
            line = fonts.small.render(fit_text(fonts.small, text, panel.w - 2 * SUMMARY_PAD), True, TEXT_DIM)
            screen.blit(line, (panel.x + SUMMARY_PAD, bottom + 4))

    def draw_rows(self, screen, panel, rows, label_w, fill_is_good=True, count_w=90, rest_w=100, lines=None):
        """(label, part, whole, count, rest) rows, each with a bar, centred in the panel.

        Args:
            fill_is_good: A full bar is work done (green); for names it is a
                pool used up, drawn as a warning instead.
            lines: How many rows' worth of room to centre; more than the rows
                leaves room for a line under them.

        Returns:
            The bottom of the last row.
        """
        fonts = self.app.fonts
        x = panel.x + SUMMARY_PAD
        room = panel.right - SUMMARY_PAD - x - label_w - count_w - 2 * ROW_GAP
        if room - rest_w - ROW_GAP < BAR_MIN_W:
            rest_w = 0   # too narrow: the bar and the count matter more
        else:
            room -= rest_w + ROW_GAP
        bar_w = max(30, min(BAR_MAX_W, room))
        y = panel.centery - (lines or len(rows)) * SUMMARY_ROW // 2
        for label, part, whole, count, rest in rows:
            middle = y + SUMMARY_ROW // 2
            text = fonts.small.render(label, True, TEXT)
            screen.blit(text, text.get_rect(midleft=(x, middle)))
            bar = pygame.Rect(x + label_w + ROW_GAP, middle - BAR_H // 2, bar_w, BAR_H)
            pygame.draw.rect(screen, BAR_BG, bar, border_radius=BAR_H // 2)
            share = part / whole if whole else 0
            if round(bar.w * share):
                if fill_is_good:
                    color = progress_color(share)
                else:
                    color = DONE_COLOR if share < 1 else POOL_USED_UP
                pygame.draw.rect(screen, color, (bar.x, bar.y, max(BAR_H, round(bar.w * share)), bar.h),
                                 border_radius=BAR_H // 2)
            count_text = fonts.font.render(count, True, TEXT)
            screen.blit(count_text, count_text.get_rect(midright=(bar.right + ROW_GAP + count_w, middle)))
            if rest_w:
                rest_text = fonts.small.render(fit_text(fonts.small, rest, rest_w), True, TEXT_DIM)
                screen.blit(rest_text, rest_text.get_rect(midleft=(bar.right + 2 * ROW_GAP + count_w, middle)))
            y += SUMMARY_ROW
        return y

    def click(self, pos):
        if self.plants_button.hit(pos):
            self.app.show_plants()
            return
        card = self.grid.card_at(pos)
        if not card:
            return
        if isinstance(card.key, tuple) and card.key[0] == 'add':
            self.app.open_add_dialog(*card.key[1:])
        else:
            self.app.open_npc(card.key)

    def key(self, event):
        if event.key == pygame.K_TAB:
            self.app.show_plants()

    def scroll_by(self, steps):
        self.grid.scroll_by(steps)
