"""Sound Manager: every sound of the game at a glance - which ones the game plays, where and what for,
and which are not used yet.

Run from anywhere:

    python build_tools/Sound_Manager/Sound_Manager.py

The game loads every file in assets/sound/ by its name without the extension
(Game._load_sounds); its subfolders ("Raw Materials") are not loaded, and
assets/music/ is the music player's rotation. The tool reads all three, and
reads the game's code (src/) for where each sound is used - by name, by an
f-string building it (f"knock_{n}") or by a prefix naming its family
(startswith('sheep_')); see usage_scan.py. Nothing is run: a sound counts as
used if the code names it.

Left, every family of sounds (knock_1 ... knock_5 are one, "knock"), by kind:
interface, paper and books, coins, ambience, animals, town, work, the player,
voices; then the music and the raw recordings. The dot says how far the game
uses it: green played, yellow some variants never played, grey not used yet,
blue music. Under the name, the function playing it, else the note written
on it. Badges: "new" (not in git yet), "loop", "very quiet" (loudness under
-40 dB, far below the rest), "two files, one name" (the same name with two
extensions: which one the game gets is luck). The chips above filter (Tab
goes round them), the field beside them searches names, kinds, notes and the
code using them (Ctrl+F). The header counts it all up and names what is
wrong: sounds the code plays that have no file, clashing names, quiet ones.

Right, the chosen family:
- In the game: each place in the code using it, with the function, file,
  line and the line itself; click to open it there in VS Code (or the
  file's default program, without VS Code on the PATH).
- Note (N): what it is for, or meant for; Enter saves it to
  sound_catalog.json, beside this file, which also holds the credits of the
  files that came from Freesound (author, title, licence; click to open).
- The files: play (or click the waveform), length, peak and loudness,
  "Copy name" for the key to play it by, "Show in folder".

Keys: Up/Down (Page Up/Down) pick a family, Space plays one of its files at
random as the game does (or stops), 1-9 a given one, L loops what is played
(on by itself for *_loop files, to hear the seam), Escape stops the sound,
then leaves the search, then closes. F5 reads files and code again, which
also happens whenever the window gets the focus back - after copying sounds
in or wiring one into the game, coming back shows it.

The code, for whoever works on it next:

    Sound_Manager.py   this file: the window, the main loop, header, filters, footer and keys
    sound_library.py   the files, their families and kinds, git's new files, sound_catalog.json (no pygame)
    usage_scan.py      reading src/ for where each sound is used (no pygame)
    audio.py           decoding, length, levels, waveforms, and playing
    sound_list.py      the left pane: the families by kind, filtered and searched
    sound_detail.py    the right pane: one family's uses, note and files
    sound_widgets.py   states, badges, play buttons, waveforms

It borrows the Sprite Manager's theme, buttons and clipboard
(../Sprite_Manager/theme.py, widgets.py, win_clipboard.py), so the two tools
look alike.
"""

import os
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path

os.environ.setdefault('SDL_MOUSE_FOCUS_CLICKTHROUGH', '1')
os.environ.setdefault('SDL_VIDEO_CENTERED', '1')

import pygame  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(1, str(HERE.parent / 'Sprite_Manager'))   # its theme and widgets
import audio  # noqa: E402
from sound_detail import DetailPanel  # noqa: E402
from sound_library import MUSIC, MUSIC_DIR, RAW, ROOT, SOUND, SOUND_DIR, Library  # noqa: E402
from sound_list import FILTERS, SoundList, pick_variant  # noqa: E402
from sound_widgets import QUIET_DB  # noqa: E402
from theme import (  # noqa: E402
    BG, CHIP_HEIGHT, ERROR_COLOR, FOOTER_HEIGHT, PANEL_GAP, TEXT, TEXT_DIM,
)
from widgets import Button, Fonts, TextField, Toast, draw_chips, fit_text  # noqa: E402
from win_clipboard import copy_text  # noqa: E402

WINDOW_TITLE = "Merchant's Rise - Sound Manager"
WINDOW_SIZE = (1500, 920)
HEADER_HEIGHT = 96
FILTER_BAR = CHIP_HEIGHT + 16
SEARCH_W = 300
LIST_SHARE = 0.5          # of the width, for the list
MIN_LIST_W = 480
RESCAN_AFTER_MS = 1500    # at most this often on getting the focus back
FPS = 30
KEYS_HINT = 'Up/Down pick   Space play   1-9 a variant   L loop   N note   Ctrl+F search   F5 read again'


class SoundManager:
    def __init__(self):
        pygame.init()
        audio.init_mixer()
        self.screen = pygame.display.set_mode(WINDOW_SIZE, pygame.RESIZABLE)
        pygame.display.set_caption(WINDOW_TITLE)
        pygame.key.stop_text_input()     # typing only goes anywhere while a field has the focus
        pygame.key.set_repeat(350, 40)
        self.fonts = Fonts(pygame.font.SysFont('segoeui', 18),
                           pygame.font.SysFont('segoeui', 15),
                           pygame.font.SysFont('segoeui', 30, bold=True))
        self.mono = pygame.font.SysFont('consolas', 15)
        self.clock = pygame.time.Clock()
        self.toast = Toast()
        self.status = ''
        self.status_error = False

        self.library = Library()
        self.decoded = {}                # {path: (Sound, Analysis, mtime)}, filled by the decoder
        self.decoder = audio.Decoder([f.path for f in self.library.sound_files()], self.decoded)
        self.player = audio.Player()
        self.last_played = None
        self.selected = None
        self.loop = False
        self.filter = 'all'
        self.filter_chips = []
        self.search = TextField(placeholder='Search  (Ctrl+F)')
        self.sound_list = SoundList(self)
        self.detail = DetailPanel(self)
        self.last_scan = pygame.time.get_ticks()

        self.rescan_button = Button('Read again  (F5)', w=170)
        self.folder_button = Button('Open sound folder', w=180)
        self.music_button = Button('Open music folder', w=180)
        self.stop_button = Button('Stop  (Esc)', w=130)
        self.sound_list.rebuild()
        if self.sound_list.families:
            self.select(self.sound_list.families[0])

    # ----- what the panes ask for

    def set_status(self, text, error=False):
        self.status, self.status_error = text, error

    def select(self, family):
        if family is self.selected:
            return
        self.selected = family
        self.loop = bool(family) and any(f.loop for f in family.files)
        self.detail.reset()
        if family:
            self.sound_list.ensure_visible(family)

    def play(self, file):
        """Play a file, or stop it if it is the one playing."""
        if self.player.is_playing(file):
            self.player.stop()
            return
        try:
            self.player.play(file, self.decoded.get(file.path) if file.place == SOUND else None, self.loop)
            self.last_played = file
        except pygame.error as exc:
            self.set_status(f'Cannot play {file.path.name}: {exc}', error=True)

    def play_family(self, family):
        """One of the family's files at random, as the game picks them; stop if one is playing."""
        if self.player.file in family.files:
            self.player.stop()
        else:
            self.play(pick_variant(family, self.last_played))

    def act(self, action, argument):
        """Something clicked in the detail pane."""
        if action == 'code':
            self.open_code(argument)
        elif action == 'play':
            self.play(argument)
        elif action == 'play family':
            self.play_family(argument)
        elif action == 'copy':
            copy_text(argument.key)
            self.toast.show(f'Copied "{argument.key}"')
        elif action == 'folder':
            subprocess.Popen(f'explorer /select,"{argument.path}"')
        elif action == 'url':
            webbrowser.open(argument)
        elif action == 'note':
            if not self.detail.editing:
                self.detail.start_editing()
        elif action == 'loop':
            self.loop = not self.loop

    def open_code(self, ref):
        """Open a use in VS Code at its line, else in the file's default program."""
        path = ROOT / ref.path
        code = shutil.which('code')
        if code:
            subprocess.Popen(f'"{code}" -g "{path}:{ref.line}"', shell=True)
        else:
            os.startfile(path)
        self.set_status(f'Opened {ref.path}:{ref.line}')

    def clipboard_text(self):
        try:
            return pygame.scrap.get_text() or ''
        except (AttributeError, pygame.error):
            return ''

    def rescan(self, quiet=False):
        """Read the files and the code again, keeping the family chosen."""
        chosen = (self.selected.place, self.selected.name) if self.selected else None
        self.library.reload()
        audio.forget_changed(self.decoded)
        self.decoder = audio.Decoder([f.path for f in self.library.sound_files()], self.decoded)
        self.sound_list.rebuild()
        self.selected = None
        again = next((f for f in self.library.families if (f.place, f.name) == chosen), None)
        self.select(again or (self.sound_list.families[0] if self.sound_list.families else None))
        self.last_scan = pygame.time.get_ticks()
        if not quiet:
            self.set_status('Read the sounds and the code again')

    # ----- drawing

    def layout(self):
        width, height = self.screen.get_size()
        top = HEADER_HEIGHT + FILTER_BAR + 10
        body_h = height - FOOTER_HEIGHT - 10 - top
        list_w = max(MIN_LIST_W, int((width - 3 * PANEL_GAP) * LIST_SHARE))
        list_area = pygame.Rect(PANEL_GAP, top, list_w, body_h)
        detail_area = pygame.Rect(list_area.right + PANEL_GAP, top, width - list_area.right - 2 * PANEL_GAP, body_h)
        return list_area, detail_area

    def draw(self):
        screen = self.screen
        screen.fill(BG)
        mouse = pygame.mouse.get_pos()
        list_area, detail_area = self.layout()
        self.draw_header(screen)
        self.draw_filters(screen, mouse)
        self.sound_list.draw(screen, list_area, mouse)
        self.detail.draw(screen, detail_area, mouse)
        self.draw_footer(screen, mouse)
        self.toast.draw(screen, self.fonts)
        pygame.display.flip()

    def draw_header(self, screen):
        fonts = self.fonts
        width = screen.get_width()
        title = fonts.title.render('Sound Manager', True, TEXT)
        screen.blit(title, (PANEL_GAP, 12))
        hint = fonts.small.render(KEYS_HINT, True, TEXT_DIM)
        screen.blit(hint, hint.get_rect(topright=(width - PANEL_GAP, 22)))

        sounds = self.library.sound_files()
        played = sum(1 for f in sounds if f.uses)
        new = sum(1 for f in sounds if f.new)
        music = sum(len(f.files) for f in self.library.families if f.place == MUSIC)
        raw = sum(len(f.files) for f in self.library.families if f.place == RAW)
        parts = [f'{len(sounds)} sounds in assets/sound/:  {played} played by the game,  '
                 f'{len(sounds) - played} not used yet' + (f'  ({new} new, not in git)' if new else ''),
                 f'{music} music tracks', f'{raw} raw recordings']
        if self.decoder.busy:
            parts.append(f'reading {len(self.decoded)} / {len(sounds)}...')
        summary = fonts.small.render('     ·     '.join(parts), True, TEXT)
        screen.blit(summary, (PANEL_GAP, 54))

        problems = [f'"{ref.text}" is played at {ref.path}:{ref.line} but there is no such file'
                    for ref in self.library.missing]
        problems += [f'{same[0].key}: {len(same)} files share the name ({", ".join(f.path.suffix for f in same)})'
                     for same in self.library.clashes]
        quiet = [f.key for f in sounds if f.path in self.decoded and self.decoded[f.path][1].loud_db < QUIET_DB]
        if quiet:
            problems.append(f'very quiet: {", ".join(quiet)}')
        if problems:
            text = fit_text(fonts.small, '   ·   '.join(problems), width - 2 * PANEL_GAP)
            screen.blit(fonts.small.render(text, True, ERROR_COLOR), (PANEL_GAP, 74))

    def draw_filters(self, screen, mouse):
        width = screen.get_width()
        y = HEADER_HEIGHT + 6
        counts = {key: sum(1 for f in self.library.families if test(f)) for key, _, test in FILTERS}
        labels = {key: f'{label}  {counts[key]}' for key, label, _ in FILTERS}
        self.filter_chips, _ = draw_chips(screen, self.fonts.small, [key for key, _, _ in FILTERS],
                                          labels.get, self.filter, PANEL_GAP, y,
                                          width - SEARCH_W - 3 * PANEL_GAP, mouse)
        self.search.rect = pygame.Rect(width - PANEL_GAP - SEARCH_W, y - 2, SEARCH_W, CHIP_HEIGHT + 4)
        self.search.draw(screen, self.fonts.small, mouse)

    def draw_footer(self, screen, mouse):
        width, height = screen.get_size()
        y = height - FOOTER_HEIGHT + (FOOTER_HEIGHT - 44) // 2
        x = PANEL_GAP
        for button in (self.rescan_button, self.folder_button, self.music_button):
            button.rect.topleft = (x, y)
            button.draw(screen, self.fonts.font, mouse)
            x = button.rect.right + 10
        self.stop_button.rect.topright = (width - PANEL_GAP, y)
        self.stop_button.enabled = self.player.file is not None
        self.stop_button.draw(screen, self.fonts.font, mouse)
        if self.status:
            room = self.stop_button.rect.x - x - 2 * PANEL_GAP
            text = fit_text(self.fonts.small, self.status, room)
            label = self.fonts.small.render(text, True, ERROR_COLOR if self.status_error else TEXT_DIM)
            screen.blit(label, label.get_rect(midleft=(x + PANEL_GAP, y + 22)))

    # ----- input

    def set_filter(self, key):
        self.filter = key
        self.sound_list.scroll = 0
        self.sound_list.rebuild()
        if self.selected not in self.sound_list.families and self.sound_list.families:
            self.select(self.sound_list.families[0])

    def click(self, pos):
        self.search.focus(self.search.rect.collidepoint(pos))
        if self.detail.click(pos):
            return
        if self.rescan_button.hit(pos):
            self.rescan()
        elif self.folder_button.hit(pos):
            os.startfile(SOUND_DIR)
        elif self.music_button.hit(pos):
            os.startfile(MUSIC_DIR)
        elif self.stop_button.hit(pos):
            self.player.stop()
        else:
            for rect, key in self.filter_chips:
                if rect.collidepoint(pos):
                    self.set_filter(key)
                    return
            self.sound_list.click(pos)

    def key(self, event):
        """A key; returns False to close the tool."""
        ctrl = event.mod & pygame.KMOD_CTRL
        if self.detail.editing:
            self.detail.key(event)
            return True
        if self.search.focused:
            if event.key == pygame.K_v and ctrl:
                self.search.type(self.clipboard_text().strip())
            elif event.key in (pygame.K_UP, pygame.K_DOWN):
                self.search.focus(False)
                return self.key(event)
            else:
                self.search.key(event)
            self.sound_list.rebuild()
            return True
        family = self.selected
        if event.key == pygame.K_ESCAPE:
            if self.player.file:
                self.player.stop()
            elif self.search.text:
                self.search.text = ''
                self.sound_list.rebuild()
            else:
                return False
        elif event.key in (pygame.K_UP, pygame.K_DOWN, pygame.K_PAGEUP, pygame.K_PAGEDOWN):
            step = {pygame.K_UP: -1, pygame.K_DOWN: 1, pygame.K_PAGEUP: -8, pygame.K_PAGEDOWN: 8}[event.key]
            self.select(self.sound_list.neighbour(family, step))
        elif event.key == pygame.K_SPACE and family:
            self.play_family(family)
        elif pygame.K_1 <= event.key <= pygame.K_9 and family:
            index = event.key - pygame.K_1
            if index < len(family.files):
                self.play(family.files[index])
        elif event.key == pygame.K_l:
            self.loop = not self.loop
        elif event.key == pygame.K_n and family:
            self.detail.start_editing()
        elif (event.key == pygame.K_f and ctrl) or event.key == pygame.K_SLASH:
            self.search.focus(True)
        elif event.key == pygame.K_F5:
            self.rescan()
        elif event.key == pygame.K_TAB:
            keys = [key for key, _, _ in FILTERS]
            step = -1 if event.mod & pygame.KMOD_SHIFT else 1
            self.set_filter(keys[(keys.index(self.filter) + step) % len(keys)])
        return True

    def run(self):
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    running = self.key(event)
                elif event.type == pygame.TEXTINPUT:
                    if self.detail.editing:
                        self.detail.text_input(event.text)
                    elif self.search.focused:
                        self.search.type(event.text)
                        self.sound_list.rebuild()
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self.click(event.pos)
                elif event.type == pygame.MOUSEWHEEL:
                    list_area, detail_area = self.layout()
                    if detail_area.collidepoint(pygame.mouse.get_pos()):
                        self.detail.scroll_by(event.y)
                    else:
                        self.sound_list.scroll_by(event.y)
                elif event.type == pygame.WINDOWFOCUSGAINED:
                    if pygame.time.get_ticks() - self.last_scan > RESCAN_AFTER_MS and not self.detail.editing:
                        self.rescan(quiet=True)
            self.player.tick()
            self.draw()
            self.clock.tick(FPS)
        self.player.stop()
        pygame.quit()


if __name__ == '__main__':
    SoundManager().run()
