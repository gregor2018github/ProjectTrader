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
from widgets import BAR_STEP, Card, SectionGrid, draw_panel, fit_text, progress_color

# An NPC's card, with a line and a bar per motion and the standing sprites
CARD_W = 172
CARD_BASE_H = 244        # with one line and one bar
LINE_H = 18
SECTIONS = ((PLAYER_CATEGORY, 'Main character'),) + tuple(
    (key, title) for key, title, _ in CATEGORIES + (OTHER,))
ADDABLE = {key for key, _, can_add in CATEGORIES if can_add}   # the groups with a "+" card
NPC_CARD_H = CARD_BASE_H + LINE_H + BAR_STEP   # an NPC's card: walk frames and standing sprites

# The overview above the cards
SUMMARY_ROW = 26
SUMMARY_ROWS = 4         # walk, run, standing, total - and as many lines of names
SUMMARY_PAD = 10
SUMMARY_H = SUMMARY_ROWS * SUMMARY_ROW + 2 * SUMMARY_PAD
SPRITES_SHARE = 0.58     # of the width, for the sprites; the names get the rest
SUMMARY_LABEL_W = 150
SUMMARY_COUNT_W = 210
POOL_USED_UP = (220, 90, 70)   # a name pool with nothing left
NAME_POOLS = (('female', "Women's names"), ('male', "Men's names"))
KINDS = (('walk', 'Walk frames'), ('run', 'Run frames'), ('standing', 'Standing sprites'))


class NpcListView(View):
    def __init__(self, app):
        super().__init__(app)
        self.grid = SectionGrid('figure')  # filled by refresh(), when the app shows the view
        self.totals = {}                   # {kind: [done, needed]} over everyone listed
        self.names = ({}, [])              # new_figure.name_usage()
        self.today = None                  # daily_progress.Today
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
        return ('1. Choose the NPC',
                'The player walks and runs in all 8 directions, the NPCs only walk: down, right, up '
                'and left. "+" adds an NPC. The left-hand walks are optional.')

    def footer(self):
        return (), (self.app.settings_button,)

    def draw(self, screen, mouse):
        area = self.app.card_area()
        summary = pygame.Rect(area.x, area.y, area.w, SUMMARY_H)
        self.draw_summary(screen, summary)
        top = summary.bottom + PANEL_GAP
        self.grid.layout(pygame.Rect(area.x, top, area.w, area.bottom - top))
        self.grid.draw(screen, self.app.fonts, mouse)

    # --- the overview -----------------------------------------------------

    def draw_summary(self, screen, rect):
        """All sprites done and missing, and how many names are left."""
        sprites_w = int((rect.w - PANEL_GAP) * SPRITES_SHARE)
        sprites = pygame.Rect(rect.x, rect.y, sprites_w, rect.h)
        names = pygame.Rect(sprites.right + PANEL_GAP, rect.y, rect.right - sprites.right - PANEL_GAP, rect.h)
        fonts = self.app.fonts
        figures = sum(getattr(c, 'counted', True) for c in self.grid.cards)
        title = f'All sprites  -  {figures} figures'
        if self.today:
            title += f'  -  today {self.today.new} new, {self.today.redone} redone'
        draw_panel(screen, fonts, sprites, title)
        rows = []
        for kind, label in KINDS:
            done, needed = self.totals.get(kind, (0, 0))
            rows.append((label, done, needed, f'{done}/{needed} done, {needed - done} missing'))
        done, needed = sum(r[1] for r in rows), sum(r[2] for r in rows)
        percent = done * 100 // needed if needed else 0   # rounded down: 100% only when all are done
        rows.append(('Total', done, needed, f'{done}/{needed} ({percent}%), {needed - done} missing'))
        self.draw_rows(screen, sprites, rows)

        usage, typed = self.names
        draw_panel(screen, fonts, names, 'Names from medieval_names.py  -  each only once')
        rows = []
        for gender, label in NAME_POOLS:
            used, pool = usage.get(gender, (0, 0))
            rows.append((label, used, pool, f'{used}/{pool} used, {pool - used} free'))
        self.draw_rows(screen, names, rows, fill_is_good=False)
        if typed:
            text = f'Not from the list: {", ".join(typed)}'
            y = names.y + SUMMARY_PAD + len(rows) * SUMMARY_ROW
            line = fonts.small.render(fit_text(fonts.small, text, names.w - 2 * SUMMARY_PAD), True, TEXT_DIM)
            screen.blit(line, (names.x + SUMMARY_PAD, y + 3))

    def draw_rows(self, screen, panel, rows, fill_is_good=True):
        """(label, part, whole, text) rows, each with a bar.

        Args:
            fill_is_good: A full bar is work done (green); for names it is a
                pool used up, drawn as a warning instead.
        """
        small = self.app.fonts.small
        x = panel.x + SUMMARY_PAD
        bar_x = x + SUMMARY_LABEL_W
        bar_w = max(40, panel.right - SUMMARY_PAD - SUMMARY_COUNT_W - bar_x - SUMMARY_PAD)
        for index, (label, part, whole, text) in enumerate(rows):
            y = panel.y + SUMMARY_PAD + index * SUMMARY_ROW
            screen.blit(small.render(label, True, TEXT), (x, y + 3))
            bar = pygame.Rect(bar_x, y + 9, bar_w, 7)
            pygame.draw.rect(screen, BAR_BG, bar, border_radius=3)
            share = part / whole if whole else 0
            if round(bar.w * share):
                if fill_is_good:
                    color = progress_color(share)
                else:
                    color = DONE_COLOR if share < 1 else POOL_USED_UP
                pygame.draw.rect(screen, color, (bar.x, bar.y, round(bar.w * share), bar.h), border_radius=3)
            count = small.render(fit_text(small, text, SUMMARY_COUNT_W), True, TEXT_DIM)
            screen.blit(count, (bar.right + SUMMARY_PAD, y + 3))

    def click(self, pos):
        card = self.grid.card_at(pos)
        if not card:
            return
        if isinstance(card.key, tuple) and card.key[0] == 'add':
            self.app.open_add_dialog(*card.key[1:])
        else:
            self.app.open_npc(card.key)

    def scroll_by(self, steps):
        self.grid.scroll_by(steps)
