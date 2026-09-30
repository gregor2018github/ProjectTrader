"""Screen 1: the player and every NPC, grouped as in create_new_NPC.py, with how far their sprites are."""

import pygame

import pose_review
from create_new_NPC import CATEGORIES, OTHER, TRADER_CATEGORY
from create_new_pose import CARD_BG, NPC_THUMB_SIZE, STATUS_COLORS, TEXT_DIM, THUMB_BG, Card
from npc import PLAYER_CATEGORY
from pose_review import ReviewStore
from view import View
from walk import DIRECTIONS, STANDING_DIRECTIONS, WALK
from widgets import BAR_STEP, SectionGrid

# create_new_pose's NPC card, taller for a line and a bar per motion and the standing sprites
CARD_W = 172
CARD_BASE_H = 244        # with one line and one bar, as in create_new_pose.py
LINE_H = 18
SECTIONS = ((PLAYER_CATEGORY, 'Main character'),) + tuple(
    (key, title) for key, title, _ in CATEGORIES + (OTHER,))
ADDABLE = {key for key, _, can_add in CATEGORIES if can_add}   # the groups with a "+" card
NPC_CARD_H = CARD_BASE_H + LINE_H + BAR_STEP   # an NPC's card: walk frames and standing sprites


class NpcListView(View):
    def __init__(self, app):
        super().__init__(app)
        self.grid = SectionGrid('figure')  # filled by refresh(), when the app shows the view
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
            total = app.total_frames(motion)
            done = sum(npc.done(d, app.counts[d]) for d in npc.directions(motion))
            lines.append((f'{done}/{total} {motion.key} frames', done_color if done == total else TEXT_DIM))
            shares.append(done / max(1, total))
        standing_total = len(STANDING_DIRECTIONS)
        standing_done = npc.standing_done()
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

    def refresh(self):
        """A section for the player, then one per group of create_new_NPC.py, each with a "+" card."""
        app = self.app
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
                f'The player and every NPC; "+" adds one. {self.app.total_frames(WALK)} walk frames '
                f'make a full set ({len(DIRECTIONS)} directions); the left-hand ones are optional.')

    def footer(self):
        return (), (self.app.settings_button,)

    def draw(self, screen, mouse):
        self.grid.layout(self.app.card_area())
        self.grid.draw(screen, self.app.fonts, mouse)

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
