"""The left pane: every family of sounds, by kind, filtered and searched, each with its play button."""

import random

import pygame

from sound_library import KIND_ORDER, MUSIC, RAW, SOUND
from sound_widgets import draw_badge, draw_play, draw_progress, lengths_text, NEW_COLOR, quiet, state
from theme import CARD_BG, CARD_HOVER, CARD_SELECTED, DONE_COLOR, ERROR_COLOR, TEXT, TEXT_DIM
from widgets import SCROLL_STEP, fit_text

ROW_H = 56
ROW_GAP = 6
SECTION_H = 36
PLAY_SIZE = 30

# (key, label, test) for the chips above the list
FILTERS = (
    ('all', 'All', lambda f: True),
    ('used', 'In the game', lambda f: f.place == SOUND and f.used),
    ('unused', 'Not used yet', lambda f: f.place == SOUND and (not f.used or f.unused_files)),
    ('new', 'New', lambda f: f.new),
    ('music', 'Music', lambda f: f.place == MUSIC),
    ('raw', 'Raw', lambda f: f.place == RAW),
)
SECTION_OF_PLACE = {MUSIC: 'Music', RAW: 'Raw recordings (assets/sound subfolders, not loaded)'}


def section_of(family):
    return SECTION_OF_PLACE.get(family.place, family.kind)


def section_order(family):
    if family.place == SOUND:
        return KIND_ORDER.index(family.kind)
    return len(KIND_ORDER) + (family.place == RAW)


def matches(family, words, note):
    """True if every search word is somewhere in the family's names, kind, note or uses."""
    text = ' '.join([family.name, family.kind, note, *(f.path.name for f in family.files),
                     *(f'{ref.where} {ref.path}' for ref in family.uses)]).lower()
    return all(word in text for word in words)


class SoundList:
    def __init__(self, app):
        self.app = app
        self.entries = []        # ('section', title, count) and ('family', Family), in the order shown
        self.families = []       # the families shown, in order
        self.hits = []           # [(row rect, play rect, family)] as last drawn
        self.area = pygame.Rect(0, 0, 0, 0)
        self.scroll = 0
        self.max_scroll = 0
        self.pending = None      # a family to scroll to once the list has been laid out

    def rebuild(self):
        """Filter and sort the library's families again (filter, search or files changed)."""
        app = self.app
        test = dict((key, test) for key, _, test in FILTERS)[app.filter]
        words = app.search.text.lower().split()
        shown = [f for f in app.library.families
                 if test(f) and matches(f, words, app.library.catalog.note(f))]
        shown.sort(key=lambda f: (section_order(f), f.name.lower()))
        self.entries, self.families = [], shown
        section = None
        for family in shown:
            title = section_of(family)
            if section is None or section[1] != title:
                section = ['section', title, 0]
                self.entries.append(section)
            section[2] += 1
            self.entries.append(('family', family))
        self.scroll = min(self.scroll, self.max_scroll)

    def _y_of(self, family):
        y = 0
        for entry in self.entries:
            if entry[0] == 'section':
                y += SECTION_H
            elif entry[1] is family:
                return y
            else:
                y += ROW_H + ROW_GAP
        return None

    def ensure_visible(self, family):
        """Scroll so the family's row shows; before the list has a size, once it has one."""
        if not self.area.h:
            self.pending = family
            return
        y = self._y_of(family)
        if y is None:
            return
        if y < self.scroll:
            self.scroll = max(0, y - SECTION_H)
        elif y + ROW_H > self.scroll + self.area.h:
            self.scroll = y + ROW_H - self.area.h

    def neighbour(self, family, step):
        """The family `step` rows from `family` (or the first one shown)."""
        if not self.families:
            return None
        if family not in self.families:
            return self.families[0]
        index = self.families.index(family) + step
        return self.families[max(0, min(len(self.families) - 1, index))]

    def scroll_by(self, steps):
        self.scroll = max(0, min(self.max_scroll, self.scroll - steps * SCROLL_STEP))

    def draw(self, screen, area, mouse):
        app = self.app
        fonts = app.fonts
        self.area = area
        height = sum(SECTION_H if e[0] == 'section' else ROW_H + ROW_GAP for e in self.entries)
        self.max_scroll = max(0, height - area.h)
        if self.pending is not None:
            self.ensure_visible(self.pending)
            self.pending = None
        self.scroll = max(0, min(self.scroll, self.max_scroll))
        self.hits = []
        screen.set_clip(area)
        if not self.entries:
            text = fonts.font.render('No sound matches.', True, TEXT_DIM)
            screen.blit(text, (area.x + 8, area.y + 8))
        y = area.y - self.scroll
        for entry in self.entries:
            if entry[0] == 'section':
                if y + SECTION_H > area.y and y < area.bottom:
                    _, title, count = entry
                    text = fonts.font.render(title, True, TEXT)
                    screen.blit(text, (area.x + 4, y + 8))
                    number = fonts.small.render(f'{count}', True, TEXT_DIM)
                    screen.blit(number, (area.x + text.get_width() + 14, y + 11))
                    line_x = area.x + text.get_width() + number.get_width() + 26
                    pygame.draw.line(screen, CARD_BG, (line_x, y + 21), (area.right - 4, y + 21))
                y += SECTION_H
                continue
            family = entry[1]
            rect = pygame.Rect(area.x, y, area.w - 4, ROW_H)
            if rect.bottom > area.y and rect.y < area.bottom:
                play = self._draw_row(screen, rect, family, mouse)
                self.hits.append((rect, play, family))
            y += ROW_H + ROW_GAP
        screen.set_clip(None)

    def _draw_row(self, screen, rect, family, mouse):
        app = self.app
        fonts = app.fonts
        hover = rect.collidepoint(mouse) and self.area.collidepoint(mouse)
        color = CARD_SELECTED if family is app.selected else CARD_HOVER if hover else CARD_BG
        pygame.draw.rect(screen, color, rect, border_radius=6)
        dot_color, _ = state(family)
        pygame.draw.circle(screen, dot_color, (rect.x + 16, rect.y + 19), 6)

        play = pygame.Rect(0, 0, PLAY_SIZE, PLAY_SIZE)
        play.midright = (rect.right - 12, rect.centery)
        playing = app.player.file in family.files
        draw_play(screen, play, playing, mouse)
        length = fonts.small.render(lengths_text(family, app.decoded), True, TEXT_DIM)
        screen.blit(length, length.get_rect(midright=(play.x - 10, rect.y + 19)))
        right = play.x - 16 - length.get_width()

        x = rect.x + 32
        name = fonts.font.render(fit_text(fonts.font, family.name, right - x - 60), True, TEXT)
        screen.blit(name, (x, rect.y + 7))
        x += name.get_width() + 8
        if len(family.files) > 1:
            count = fonts.small.render(f'x{len(family.files)}', True, TEXT_DIM)
            screen.blit(count, (x, rect.y + 11))
            x += count.get_width() + 10
        badges = []
        if family.new:
            badges.append(('new', NEW_COLOR))
        if any(f.loop for f in family.files):
            badges.append(('loop', TEXT_DIM))
        if family.used and family.unused_files:
            badges.append((f'{len(family.unused_files)} never played', DONE_COLOR))
        if any(f.clash for f in family.files):
            badges.append(('two files, one name', ERROR_COLOR))
        if quiet(family, app.decoded):
            badges.append(('very quiet', ERROR_COLOR))
        for text, badge_color in badges:
            if x + fonts.small.size(text)[0] + 12 > right:
                break
            x = draw_badge(screen, fonts.small, text, x, rect.y + 19, badge_color)

        line, line_color = self._summary(family)
        text = fonts.small.render(fit_text(fonts.small, line, right - rect.x - 32), True, line_color)
        screen.blit(text, (rect.x + 32, rect.y + 31))
        if playing:
            share = app.player.position()
            if share is not None:
                draw_progress(screen, pygame.Rect(rect.x + 32, rect.bottom - 5, right - rect.x - 32, 3), share)
        return play

    def _summary(self, family):
        """The second line of a row: where the game uses it, else the note, else its state."""
        uses = family.uses
        if uses:
            first = uses[0]
            more = f'   +{len(uses) - 1} more' if len(uses) > 1 else ''
            return f'{first.where}   {first.path.removeprefix("src/")}:{first.line}{more}', TEXT
        note = self.app.library.catalog.note(family)
        if note:
            return note, TEXT_DIM
        return state(family)[1], TEXT_DIM

    def click(self, pos):
        """Select the row clicked, or play from its button."""
        if not self.area.collidepoint(pos):
            return False
        for rect, play, family in self.hits:
            if play.collidepoint(pos):
                self.app.select(family)
                self.app.play_family(family)
                return True
            if rect.collidepoint(pos):
                self.app.select(family)
                return True
        return False


def pick_variant(family, last):
    """A random file of the family, not the one played last if there is a choice (as the game does)."""
    choices = [f for f in family.files if f is not last] or family.files
    return random.choice(choices)
