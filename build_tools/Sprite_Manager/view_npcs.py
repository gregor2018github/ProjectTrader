"""Screen 1: every NPC, with how far its walk frames are."""

import pose_review
from create_new_pose import NPC_CARD_SIZE, STATUS_COLORS, TEXT_DIM, Card
from pose_review import ReviewStore
from view import View
from walk import DIRECTIONS
from widgets import CardGrid


class NpcListView(View):
    def __init__(self, app):
        super().__init__(app)
        self.grid = CardGrid()  # filled by refresh(), when the app shows the view

    def refresh(self):
        """One card per NPC, with how many walk frames he already has."""
        app = self.app
        total = app.total_frames()
        cards = []
        for npc in app.npcs:
            done = sum(npc.done(d, app.counts[d.key]) for d in DIRECTIONS)
            waiting = len(ReviewStore(npc.out_dir).pending())
            extra = [(f'{waiting} to review', STATUS_COLORS[pose_review.PENDING])] if waiting else []
            cards.append(Card(
                npc, npc.name, app.npc_thumbs[npc.name],
                note=f'{done}/{total} walk frames',
                note_color=STATUS_COLORS[pose_review.ACCEPTED] if done == total else TEXT_DIM,
                extra=extra, progress=done / max(1, total), size=NPC_CARD_SIZE))
        self.grid.cards = cards

    def header(self):
        return ('1. Choose the NPC',
                f'Every NPC with a front standing sprite. {self.app.total_frames()} walk frames '
                f'make a full set ({len(DIRECTIONS)} directions); the left-hand ones are optional.')

    def footer(self):
        return (), (self.app.settings_button,)

    def draw(self, screen, mouse):
        self.grid.layout(self.app.card_area())
        self.grid.draw(screen, self.app.fonts, mouse)

    def click(self, pos):
        card = self.grid.card_at(pos)
        if card:
            self.app.open_npc(card.key)

    def scroll_by(self, steps):
        self.grid.scroll_by(steps)
