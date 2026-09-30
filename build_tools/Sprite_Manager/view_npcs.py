"""Screen 1: every NPC, grouped as in create_new_NPC.py, with how far his sprites are."""

import pose_review
from create_new_NPC import CATEGORIES, OTHER
from create_new_pose import STATUS_COLORS, TEXT_DIM, Card
from pose_review import ReviewStore
from view import View
from walk import DIRECTIONS, STANDING_DIRECTIONS
from widgets import SectionGrid

# create_new_pose's NPC card, taller for the standing sprites' line and bar
NPC_CARD_SIZE = (172, 270)


class NpcListView(View):
    def __init__(self, app):
        super().__init__(app)
        self.grid = SectionGrid('NPC')  # filled by refresh(), when the app shows the view

    def npc_card(self, npc):
        """The NPC's card: walk frames and standing sprites done, each with a bar."""
        app = self.app
        done_color = STATUS_COLORS[pose_review.ACCEPTED]
        walk_total = app.total_frames()
        walk_done = sum(npc.done(d, app.counts[d.key]) for d in DIRECTIONS)
        standing_total = len(STANDING_DIRECTIONS)
        standing_done = npc.standing_done()
        waiting = len(ReviewStore(npc.out_dir).pending())
        extra = [(f'{standing_done}/{standing_total} standing sprites',
                  done_color if standing_done == standing_total else TEXT_DIM)]
        if waiting:
            extra.append((f'{waiting} to review', STATUS_COLORS[pose_review.PENDING]))
        return Card(
            npc, npc.label, app.npc_thumbs[npc.name],
            note=f'{walk_done}/{walk_total} walk frames',
            note_color=done_color if walk_done == walk_total else TEXT_DIM,
            extra=extra, size=NPC_CARD_SIZE,
            progress=(walk_done / max(1, walk_total), standing_done / standing_total))

    def refresh(self):
        """One section per group of create_new_NPC.py, one card per NPC."""
        self.grid.set_sections(
            (title, [self.npc_card(n) for n in self.app.npcs if n.category == key])
            for key, title, _ in CATEGORIES + (OTHER,))

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
