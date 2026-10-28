"""The right pane: one family of sounds - where the game uses it, the note on it, and each file.

Every use names the function it is in and its line; clicking it opens the
file at that line in VS Code. The note is typed straight into the pane
(click it, or N) and saved to sound_catalog.json with Enter. Each file has
its play button, length, levels and waveform, the key the code plays it by
("copy name") and, where sound_catalog.json knows it, where it came from.
"""

import pygame

from sound_library import MUSIC, RAW, SOUND
from sound_widgets import (
    QUIET_DB, Waveforms, draw_badge, draw_play, duration_text, NEW_COLOR, size_text, state,
)
from theme import (
    BAR_BG, CARD_BG, CARD_HOVER, CHIP_BG, CHIP_HOVER, CHIP_ON, DONE_COLOR, ERROR_COLOR, TEXT, TEXT_DIM,
)
from widgets import SCROLL_STEP, fit_text, wrap_text

PAD = 18
GAP = 14
WAVE_H = 46
PLAY_SIZE = 30
NOTE_LINES = 6
HOW_WORDS = {'name': 'by name', 'pattern': 'built as', 'prefix': 'every sound starting'}


class DetailPanel:
    def __init__(self, app):
        self.app = app
        self.area = pygame.Rect(0, 0, 0, 0)
        self.scroll = 0
        self.max_scroll = 0
        self.hits = []           # [(rect, action, argument)] as last drawn
        self.editing = False     # typing into the note
        self.draft = ''
        self.waves = Waveforms()

    def reset(self):
        self.scroll = 0
        self.stop_editing()

    # ----- the note

    def start_editing(self):
        if self.app.selected is None:
            return
        self.editing = True
        self.draft = self.app.library.catalog.note(self.app.selected)
        pygame.key.start_text_input()

    def stop_editing(self, save=False):
        if self.editing and save and self.app.selected is not None:
            self.app.library.catalog.set_note(self.app.selected, self.draft)
            self.app.set_status(f'Note on {self.app.selected.name} saved to sound_catalog.json')
            self.app.sound_list.rebuild()
        if self.editing:
            pygame.key.stop_text_input()
        self.editing = False

    def key(self, event):
        """A key while editing the note."""
        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.stop_editing(save=True)
        elif event.key == pygame.K_ESCAPE:
            self.stop_editing()
        elif event.key == pygame.K_BACKSPACE:
            if event.mod & pygame.KMOD_CTRL:   # the last word
                kept = self.draft.rstrip().rpartition(' ')[0]
                self.draft = kept + ' ' if kept else ''
            else:
                self.draft = self.draft[:-1]
        elif event.key == pygame.K_v and event.mod & pygame.KMOD_CTRL:
            self.draft += self.app.clipboard_text().replace('\r', ' ').replace('\n', ' ')

    def text_input(self, text):
        self.draft += text

    # ----- input

    def scroll_by(self, steps):
        self.scroll = max(0, min(self.max_scroll, self.scroll - steps * SCROLL_STEP))

    def click(self, pos):
        if not self.area.collidepoint(pos):
            if self.editing:
                self.stop_editing(save=True)
            return False
        for rect, action, argument in self.hits:
            if rect.collidepoint(pos):
                if action != 'note' and self.editing:
                    self.stop_editing(save=True)
                self.app.act(action, argument)
                return True
        if self.editing:
            self.stop_editing(save=True)
        return True

    # ----- drawing

    def draw(self, screen, area, mouse):
        self.area = area
        self.hits = []
        pygame.draw.rect(screen, CARD_BG, area, border_radius=8)
        family = self.app.selected
        if family is None:
            text = self.app.fonts.font.render('Pick a sound on the left.', True, TEXT_DIM)
            screen.blit(text, (area.x + PAD, area.y + PAD))
            return
        inner = area.inflate(-2 * PAD, 0)
        screen.set_clip(area)
        y = area.y + PAD - self.scroll
        y = self._draw_title(screen, inner, y, family, mouse)
        y = self._draw_uses(screen, inner, y, family, mouse)
        y = self._draw_note(screen, inner, y, family, mouse)
        y = self._draw_files(screen, inner, y, family, mouse)
        screen.set_clip(None)
        self.max_scroll = max(0, y + self.scroll - area.y - area.h + PAD)
        self.scroll = min(self.scroll, self.max_scroll)
        # Hits scrolled out of the pane are not there to be clicked
        self.hits = [(rect.clip(area), action, arg) for rect, action, arg in self.hits if rect.colliderect(area)]

    def _heading(self, screen, inner, y, text):
        label = self.app.fonts.font.render(text, True, TEXT)
        screen.blit(label, (inner.x, y))
        line_x = inner.x + label.get_width() + 12
        pygame.draw.line(screen, BAR_BG, (line_x, y + 13), (inner.right, y + 13), 2)
        return y + label.get_height() + 8

    def _chip(self, screen, text, x, y, mouse, on=False):
        """A small button; returns its rect."""
        font = self.app.fonts.small
        rect = pygame.Rect(x, y, font.size(text)[0] + 18, 26)
        color = CHIP_ON if on else CHIP_HOVER if rect.collidepoint(mouse) else CHIP_BG
        pygame.draw.rect(screen, color, rect, border_radius=5)
        label = font.render(text, True, TEXT)
        screen.blit(label, label.get_rect(center=rect.center))
        return rect

    def _draw_title(self, screen, inner, y, family, mouse):
        fonts = self.app.fonts
        title = fonts.title.render(fit_text(fonts.title, family.name, inner.w), True, TEXT)
        screen.blit(title, (inner.x, y))
        y += title.get_height() + 4
        color, words = state(family)
        kind = '' if family.place in (MUSIC, RAW) else f'{family.kind}  ·  '
        count = f'{len(family.files)} files  ·  ' if len(family.files) > 1 else ''
        line = fonts.small.render(f'{kind}{count}{words}', True, color)
        screen.blit(line, (inner.x, y))
        y += line.get_height() + 10
        x = inner.x
        loop = self._chip(screen, f'Loop: {"on" if self.app.loop else "off"}  (L)', x, y, mouse, self.app.loop)
        self.hits.append((loop, 'loop', None))
        x = loop.right + 8
        if len(family.files) > 1:
            rect = self._chip(screen, 'Play one at random  (Space)', x, y, mouse)
            self.hits.append((rect, 'play family', family))
        return y + 26 + GAP + 6

    def _draw_uses(self, screen, inner, y, family, mouse):
        fonts = self.app.fonts
        y = self._heading(screen, inner, y, 'In the game')
        if family.place == MUSIC:
            return self._lines(screen, inner, y, 'The music player (SoundControl) plays every track of '
                                                 'assets/music/ in random order: all of them are in the game.')
        if family.place == RAW:
            return self._lines(screen, inner, y, 'Not loaded: the game reads assets/sound/ only, not its '
                                                 'subfolders. Raw material to cut sounds from.')
        uses = family.uses
        if not uses:
            y = self._lines(screen, inner, y, 'Nothing in src/ plays it yet.', TEXT_DIM)
        for ref in uses:
            how = HOW_WORDS[ref.how]
            how_text = f'{how} "{ref.text}"' if ref.how != 'name' else ''
            code_h = self.app.mono.get_linesize()
            rect = pygame.Rect(inner.x - 8, y - 4, inner.w + 16, 22 + 18 + code_h + 10)
            if rect.collidepoint(mouse) and self.area.collidepoint(mouse):
                pygame.draw.rect(screen, CARD_HOVER, rect, border_radius=6)
            where = fonts.font.render(fit_text(fonts.font, ref.where, inner.w), True, TEXT)
            screen.blit(where, (inner.x, y))
            place = f'{ref.path}:{ref.line}' + (f'   {how_text}' if how_text else '')
            line = fonts.small.render(fit_text(fonts.small, place, inner.w), True, TEXT_DIM)
            screen.blit(line, (inner.x, y + 22))
            code = self.app.mono.render(fit_text(self.app.mono, ref.code, inner.w - 12), True, DONE_COLOR)
            screen.blit(code, (inner.x + 12, y + 22 + 18 + 2))
            self.hits.append((rect, 'code', ref))
            y = rect.bottom + 6
        unused = family.unused_files if uses else []
        if unused:
            names = ', '.join(f.key for f in unused)
            y = self._lines(screen, inner, y, f'Never played: {names}', DONE_COLOR)
        return y + GAP

    def _lines(self, screen, inner, y, text, color=TEXT, max_lines=4):
        font = self.app.fonts.small
        for line in wrap_text(font, text, inner.w, max_lines):
            screen.blit(font.render(line, True, color), (inner.x, y))
            y += font.get_linesize()
        return y + 6

    def _draw_note(self, screen, inner, y, family, mouse):
        font = self.app.fonts.small
        y = self._heading(screen, inner, y, 'Note  (N)')
        text = self.draft if self.editing else self.app.library.catalog.note(family)
        shown = text or ('' if self.editing else 'What it is for, or meant for. Click to write a note.')
        lines = wrap_text(font, shown, inner.w - 20, NOTE_LINES) if shown else ['']
        rect = pygame.Rect(inner.x, y, inner.w, max(2, len(lines)) * font.get_linesize() + 16)
        hover = rect.collidepoint(mouse) and self.area.collidepoint(mouse)
        pygame.draw.rect(screen, CHIP_HOVER if hover or self.editing else CHIP_BG, rect, border_radius=6)
        if self.editing:
            pygame.draw.rect(screen, DONE_COLOR, rect, 2, border_radius=6)
        line_y = rect.y + 8
        for line in lines:
            label = font.render(line, True, TEXT if text else TEXT_DIM)
            screen.blit(label, (rect.x + 10, line_y))
            line_y += font.get_linesize()
        if self.editing and pygame.time.get_ticks() // 500 % 2:
            last = lines[-1]
            x = rect.x + 10 + font.size(last)[0] + 1
            top = line_y - font.get_linesize()
            pygame.draw.line(screen, TEXT, (x, top + 2), (x, top + font.get_linesize() - 2), 2)
        self.hits.append((rect, 'note', None))
        y = rect.bottom + 4
        if self.editing:
            hint = font.render('Enter saves, Escape leaves it as it was', True, TEXT_DIM)
            screen.blit(hint, (inner.x, y))
            y += hint.get_height()
        return y + GAP

    def _draw_files(self, screen, inner, y, family, mouse):
        y = self._heading(screen, inner, y, 'Files' if len(family.files) > 1 else 'File')
        for index, file in enumerate(family.files):
            y = self._draw_file(screen, inner, y, file, index, mouse) + GAP
        return y

    def _draw_file(self, screen, inner, y, file, index, mouse):
        app = self.app
        fonts = app.fonts
        playing = app.player.is_playing(file)
        play = pygame.Rect(inner.x, y, PLAY_SIZE, PLAY_SIZE)
        draw_play(screen, play, playing, mouse)
        self.hits.append((play, 'play', file))

        x = play.right + 12
        number = f'{index + 1}  ' if len(app.selected.files) > 1 and index < 9 else ''
        name = fonts.font.render(f'{number}{file.path.name}', True, TEXT)
        screen.blit(name, (x, y + 4))
        x += name.get_width() + 10
        if file.new:
            x = draw_badge(screen, fonts.small, 'new, not in git', x, play.centery, NEW_COLOR)
        if file.clash:
            x = draw_badge(screen, fonts.small, 'another file has this name', x, play.centery, ERROR_COLOR)

        # Buttons on the right of the name line
        right = inner.right
        for text, action in (('Show in folder', 'folder'), ('Copy name', 'copy')):
            width = fonts.small.size(text)[0] + 18
            right -= width
            rect = self._chip(screen, text, right, y + 2, mouse)
            self.hits.append((rect, action, file))
            right -= 8
        y = play.bottom + 6

        decoded = app.decoded.get(file.path)
        facts = [size_text(file.size)]
        warn = False
        if decoded:
            info = decoded[1]
            warn = info.loud_db < QUIET_DB
            facts[:0] = [duration_text(info.length), f'peak {info.peak_db:.0f} dB',
                         f'loudness {info.loud_db:.0f} dB' + ('  - very quiet' if warn else '')]
        elif file.place == SOUND:
            facts.append('reading...' if app.decoder.busy else 'could not be read')
        else:
            facts.append('streamed: no waveform')
        if playing:
            facts.append(f'playing {duration_text(app.player.elapsed())}')
        line = fonts.small.render('   ·   '.join(facts), True, ERROR_COLOR if warn else TEXT_DIM)
        screen.blit(line, (inner.x, y))
        y += line.get_height() + 4

        if decoded:
            wave = pygame.Rect(inner.x, y, inner.w, WAVE_H)
            position = app.player.position() if playing else None
            self.waves.draw(screen, wave, file.path, decoded[1], position, warn)
            self.hits.append((wave, 'play', file))
            y = wave.bottom + 4

        for credit in app.library.catalog.credits_of(file):
            text = f'{credit.get("author", "?")}: "{credit.get("title", "")}"  ·  {credit.get("license", "")}'
            label = fonts.small.render(fit_text(fonts.small, text, inner.w), True, TEXT_DIM)
            rect = label.get_rect(topleft=(inner.x, y))
            if credit.get('url'):
                if rect.collidepoint(mouse) and self.area.collidepoint(mouse):
                    label = fonts.small.render(fit_text(fonts.small, text, inner.w), True, TEXT)
                    pygame.draw.line(screen, TEXT, (rect.x, rect.bottom), (rect.right, rect.bottom))
                self.hits.append((rect, 'url', credit['url']))
            screen.blit(label, rect)
            y = rect.bottom + 2
        return y
