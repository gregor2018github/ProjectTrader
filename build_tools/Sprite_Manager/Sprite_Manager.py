"""Sprite Manager: make and look after the walk and run animations of the NPCs and the player.

For every frame of a walk (or run) cycle the tool builds a 2x2 reference sheet from
the base chibi (see sheets.py) and the prompt that goes with it. The image
model draws the NPC into the sheet's red frame; the answer is cut out,
scaled like the NPC's standing sprite and, once accepted, saved as
<prefix>_<direction>_move<n>.png in the NPC's folder - the name the game
loads walk frames by.

Run from anywhere:

    python build_tools/Sprite_Manager/Sprite_Manager.py

The window can be resized or maximised; F11 switches to full screen.

1. Pick the NPC or the player, in their groups (traders, poor, commons,
   middling sort, nobility; see figures.py). Each card
   shows how many walk (and run) frames and standing sprites there are; the
   overview above adds them up over everyone, says how many sprites are new or
   redone today (by the dates of their files, see daily_progress.py) and shows how much of the name pool in
   medieval_names.py the townsfolk have used (a name only once).
   "+" at the end of a group adds a person: woman or man and a name (typed,
   or rolled from medieval_names.py), or for a trader his trade. Someone without a front standing sprite yet opens on
   "First sprite": describe them in description.txt ("Edit description"; the
   prompt follows the file as it is saved), send the split image - the
   player's front sprite beside an empty cell - to Gemini like any sheet,
   and accept an answer. It is scaled like the player, saved as
   <name>_front_static.png, and the person goes on to his walk frames.
   "Redo first sprite" (F) on the frames screen opens the same screen for
   someone who has a front sprite already; accepting replaces it.
2. Pick a direction on the left. Its sheets are rebuilt from the base files
   every time a direction or a frame is clicked, so edits to the chibi or
   ghost strips show up straight away. The box under the directions plays
   the frames the NPC already has. Down, up, left and right start with the
   NPC's standing sprite of that direction (<prefix>_<direction>_static.png).
   For up, left and right it can be made like a frame: its sheet shows the
   chibi standing front on and turned that way, the NPC's front standing
   sprite, and the ghost of the turned chibi to draw him on. "From other
   frame" also offers the standing sprites, e.g. the right one mirrored for
   the left. The front one is the reference for all of them; it is only shown.
3. Pick a frame. If it is already done, the frame in the game is shown under
   its sheet next to the ghost it was aimed at, and laid over it. Then either
   - for free, through the Gemini web view: "Copy image" (Ctrl+C) and
     "Copy prompt" (Ctrl+Shift+C), paste both there, copy the answer and
     "Paste answer" (Ctrl+V) - or drop the image file onto the window, or
     "Open image" (Ctrl+O);
   - or through the API: "Send to Gemini" for this frame, or "Send missing"
     in the footer for every frame of the direction that is not done yet.
     "Settings" (S) chooses the model, aspect ratio, image size and how many
     answers to ask for per sheet.
4. Every answer opens for review: the image next to the frame it would
   become. "Accept" (Enter) saves the frame into the game, "Not good enough"
   (Del) keeps it on disk for later. "Review" (R) lists every answer.

The player: in the game he only runs, so for him the run is what the game
plays, player_<direction>_move<n>.png, built from the chibi's run strips.
His walk is player_<direction>_walk<n>.png, which the game does not load
yet. Walk / Run above the directions (Tab) switches between the two. The
NPCs only walk: their walk is <prefix>_<direction>_move<n>.png.

Which figure gets which animations: the player walks and runs in all eight
directions; an NPC only walks, and only down, right, up and left. NPCs still
move any way on the map - walking diagonally, the game shows their walk down
or up (DirectionalAnimator.DIRECTION_FALLBACKS) - so diagonals are not worth
drawing for them.

Directions: the chibi was drawn walking down, up, right, down-right and
up-right. The left-hand directions are those mirrored; the game mirrors
right-hand frames on its own for an NPC without left-hand ones, so they are
only needed where the NPC is not symmetrical.

Frames from frames: "From other frame" (M) lists every frame the NPC already
has and saves the one clicked as the chosen frame, mirrored or as it is,
replacing the one there. The likely ones come first: the mirror partner's
frame of the same number, and for the walks down and up the frame half a
cycle on (1 <-> 4, 2 <-> 5, 3 <-> 6), which is the same step with the other
foot. In a direction with a mirror partner (left and right, and both
diagonal pairs) "Mirror missing from ..." in the footer mirrors every frame
the direction lacks and its partner has.

"Copy as GIF" under the animation saves the direction's frames as the game
plays them as <prefix>_<direction>_<walk|run>.gif in the output folder and
puts the file on the clipboard, to paste into a chat, a browser or the
Explorer. It needs Pillow (build_tools/requirements.txt).

"Edit in GIMP" (G) opens a frame the NPC already has in GIMP (found through
GIMP_PATH, the PATH or Program Files). Once it is saved back with File >
Overwrite, the tool notices and shows the new version.

"Even out colours" (E) under the animation fights flicker: every frame comes
back from the model a little lighter, darker or warmer here and there, and
played as a walk that flickers. It pulls the colours of all the direction's
frames onto its standing sprite (else the front one), material by material,
keeping each frame's shading (see even_colours.py), and saves over them. The
frames as they were go to colour_backups/ in the output folder; right after,
the button reads "Undo even out" and puts them back. It needs numpy
(build_tools/requirements.txt).

Ghosts: <Walk|Run>_<strip>_Sheet_Ghost.png is used where it exists. For the other
strips a ghost is made on the fly (outline black, skin in greys, face left
out); drawing one by hand gives the model a cleaner guide.

Sheets, prompts, answers and review.json live in build_tools/output/<npc>/walk/.

The code, for whoever works on it next:

    Sprite_Manager.py  this file: the window, the main loop, shared state
    view.py            View, the base of every screen
    view_npcs.py       screen 1, the NPC list
    view_frames.py     screen 2, directions, frames and the chosen sheet
    view_review.py     screens 3 and 4, all answers and one answer
    view_first.py      screen 2 for a new person: his first sprite
    new_figure.py      adding a person; his split image, description and prompt
    new_npc_dialog.py  the dialog asking for a new person's gender and name, or trade
    frame_picker.py    the dialog making a frame from another frame
    settings_dialog.py the dialog choosing the image model and size
    theme.py           paths, colours, sizes and the window
    widgets.py         buttons, cards, panels, card grid, notices, the goal comparison
    walk.py            motions, directions, frame names, mirror relations (no pygame)
    figures.py         the sprite folders, their groups and npc.json; making a new one
    npc.py             an NPC's or the player's folder: sprites and output
    medieval_names.py  the pool of townsfolk names
    chibi.py           the base chibi strips and ghosts
    sheets.py          the 2x2 sheets and prompts
    gemini_client.py   the Gemini API: key, models, settings, one request
    gemini_worker.py   requests sent in a background thread
    answers.py         answers from the web view and the API into review.json
    pose_review.py     review.json, and accepting an answer into the game
    extraction.py      cutting the sprite out of an answer and scaling it
    gif_export.py      animations as GIF files
    daily_progress.py  the sprites new and redone today, by file dates
    even_colours.py    evening out the colours of a direction's frames against flicker
    gimp.py            GIMP and the watch on files edited outside
    images.py          small surface helpers
    win_clipboard.py   the Windows clipboard
"""

import os
import sys
from pathlib import Path

import pygame

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gemini_client  # noqa: E402
from answers import record_answer  # noqa: E402
from chibi import strip_length  # noqa: E402
from figures import FigureFolder, find_figure_folders, find_player_poses  # noqa: E402
from gemini_client import Settings  # noqa: E402
from gemini_worker import GeminiWorker  # noqa: E402
from images import make_thumb  # noqa: E402
from new_figure import AddFigureDialog, NewFigure, find_new_figures  # noqa: E402
from npc import WalkNpc, player  # noqa: E402
from pose_review import ReviewStore, load_player_shapes  # noqa: E402
from settings_dialog import SettingsDialog  # noqa: E402
from theme import (  # noqa: E402
    BG, CARD_BG, CARD_GAP, DONE_COLOR, ERROR_COLOR, FOOTER_HEIGHT, HEADER_HEIGHT, NPC_THUMB_SIZE,
    PANEL_GAP, ROOT, TEXT, TEXT_DIM, open_window, toggle_fullscreen, window_size,
)
from view_first import FirstSpriteView  # noqa: E402
from view_frames import FramesView  # noqa: E402
from view_npcs import NpcListView  # noqa: E402
from view_review import DetailView, ReviewView  # noqa: E402
from walk import ALL_DIRECTIONS, DEFAULT_DIRECTION  # noqa: E402
from widgets import PANEL_TITLE, Button, Fonts, Toast, fit_text  # noqa: E402

WINDOW_TITLE = "Merchant's Rise - Sprite Manager"
FPS = 30


class SpriteManager:
    """The window and what every screen shares; shows one View at a time."""

    def __init__(self):
        pygame.init()
        self.screen = open_window(WINDOW_TITLE)
        self.fonts = Fonts(pygame.font.SysFont('segoeui', 18),
                           pygame.font.SysFont('segoeui', 15),
                           pygame.font.SysFont('segoeui', 30, bold=True))
        self.clock = pygame.time.Clock()
        self.toast = Toast()
        self.status = ''
        self.status_error = False
        self.dialog = None            # a modal on top of the view, if one is open
        self.settings = Settings.load()
        self.worker = None            # the Gemini requests running, or last run

        self.counts = {d: strip_length(d) for d in ALL_DIRECTIONS}   # {Direction: frames}
        self.npcs = []                # the player and every NPC with a front standing sprite
        self.new_figures = []         # NPC folders without one yet
        self.npc_thumbs = {}
        self.reload_npcs()
        self._player_references = None
        self.npc = None               # the NPC being worked on
        self.store = None             # its answers
        self.frames = None            # its frames screen, kept while it is open
        self.last_direction = DEFAULT_DIRECTION

        # Footer buttons several screens show; the app handles them
        self.back_button = Button('Back', w=90)
        self.folder_button = Button('Open folder', w=130)
        self.settings_button = Button('Settings', w=110)

        self.view = None
        self.show(NpcListView(self))

    # --- shared state -----------------------------------------------------

    def set_status(self, text, error=False):
        self.status = text
        self.status_error = error

    def busy(self):
        return self.worker is not None and not self.worker.finished

    def reload_npcs(self):
        """Read the sprite folders again, after a person was added or got his first sprite."""
        self.npcs = [player()] + [WalkNpc(f) for f in find_figure_folders() if f.has_front()]
        self.new_figures = find_new_figures()
        for npc in self.npcs:
            if npc.name not in self.npc_thumbs:
                self.npc_thumbs[npc.name] = make_thumb(npc.base_path, NPC_THUMB_SIZE)

    def player_references(self):
        """({pose: path}, {pose: mask}) of the player, which a first sprite is scaled against."""
        if self._player_references is None:
            poses = find_player_poses()
            self._player_references = (poses, load_player_shapes(poses))
        return self._player_references

    # --- screens ----------------------------------------------------------

    def show(self, view):
        """Make `view` the screen shown, brought up to date with the files."""
        self.view = view
        view.refresh()
        self.place_footer()

    def open_npc(self, npc):
        """Work on a figure: his frames, or his first sprite if he has none yet."""
        self.npc = npc
        self.store = ReviewStore(npc.out_dir)
        self.worker = None
        self.set_status('')
        if getattr(npc, 'is_new', False):
            self.frames = None
            self.show(FirstSpriteView(self))
            return
        self.frames = FramesView(self, npc.direction_like(self.last_direction))
        self.show(self.frames)

    def redo_first_sprite(self):
        """Make the front standing sprite of the figure being worked on anew; back returns to his frames."""
        npc = self.npc
        if npc.is_player:
            return
        figure = NewFigure(FigureFolder(npc.folder))
        self.npc = figure
        self.store = ReviewStore(figure.out_dir)
        self.frames = self.worker = None
        self.set_status('')
        self.show(FirstSpriteView(self, return_to=npc))

    def open_add_dialog(self, category, title):
        """Add a person to a group."""
        self.dialog = AddFigureDialog(category, title, self.fonts, self.figure_created)

    def figure_created(self, folder):
        self.reload_npcs()
        figure = next(f for f in self.new_figures if f.folder == folder)
        self.open_npc(figure)
        note = ' - write his Trader subclass to put him in town' if figure.category == 'trader' else ''
        self.set_status(f'Created {folder.relative_to(ROOT)}{note}')

    def first_sprite_saved(self, folder):
        """A person has a new front standing sprite: on to his other sprites."""
        self.npc_thumbs.pop(folder.name, None)  # it shows the front sprite, which may have changed
        self.reload_npcs()
        self.open_npc(next(n for n in self.npcs if n.folder == folder))

    def close_npc(self):
        self.npc = self.store = self.frames = self.worker = None
        self.set_status('')
        self.show(NpcListView(self))

    def open_review(self):
        self.show(ReviewView(self))

    def open_detail(self, entry, return_to):
        """Judge one answer; back from it goes to `return_to`."""
        try:
            view = DetailView(self, entry, return_to)
        except ValueError as exc:
            self.set_status(str(exc), error=True)
            return
        except Exception as exc:  # a deleted or unreadable file
            self.set_status(f'Cannot open {entry.image}: {exc}', error=True)
            return
        self.show(view)
        self.set_status(*view.opening_status())

    def back(self):
        """Escape or Back; False if there is nowhere to go back to."""
        return self.view.back()

    # --- Gemini API -------------------------------------------------------

    def send(self, sheets):
        """Send sheets with their prompts to the API in the background."""
        if self.busy() or not sheets:
            return
        if gemini_client.SDK_ERROR:
            self.set_status(f'Gemini: {gemini_client.SDK_ERROR}', error=True)
            return
        jobs = [(s.pose, s.path, s.prompt) for s in sheets for _ in range(self.settings.tries)]
        self.worker = GeminiWorker(self.npc, jobs, self.settings, record_answer(self.npc, self.store))
        self.set_status(self.worker.status())

    def poll_worker(self):
        if self.worker is None:
            return
        was_finished = self.worker.finished
        before = len(self.store.entries)
        self.worker.poll()
        self.set_status(self.worker.status(), error=bool(self.worker.error))
        if len(self.store.entries) != before or (self.worker.finished and not was_finished):
            self.view.refresh()

    # --- dialogs ----------------------------------------------------------

    def open_settings(self):
        self.dialog = SettingsDialog(self.settings, self.fonts)

    def close_dialog(self):
        if isinstance(self.dialog, SettingsDialog):
            self.settings = self.dialog.settings
            self.settings.save()
        self.dialog = None

    def open_folder(self):
        folder = self.npc.out_dir
        folder.mkdir(parents=True, exist_ok=True)
        if sys.platform == 'win32':
            os.startfile(folder)
        else:
            self.set_status(str(folder))

    # --- layout -----------------------------------------------------------

    def body(self):
        """The area between header and footer."""
        width, height = window_size()
        top = HEADER_HEIGHT + PANEL_TITLE
        return pygame.Rect(PANEL_GAP, top, width - 2 * PANEL_GAP,
                           height - FOOTER_HEIGHT - 10 - top)

    def card_area(self):
        """Where a screen that is only cards puts them."""
        return self.body().inflate(0, -CARD_GAP)

    def place_footer(self):
        """Line the view's footer buttons up along the foot of the window."""
        self.screen = pygame.display.get_surface()
        if not self.view:
            return
        width, height = window_size()
        y = height - FOOTER_HEIGHT + 13
        left, right = self.view.footer()
        x = 20
        for button in left:
            button.rect.topleft = (x, y)
            x += button.rect.w + 12
        x = width - 20
        for button in reversed(right):
            button.rect.topright = (x, y)
            x -= button.rect.w + 12

    # --- drawing ----------------------------------------------------------

    def draw_header(self):
        width = window_size()[0]
        small = self.fonts.small
        title, hint = self.view.header()
        self.screen.blit(self.fonts.title.render(title, True, TEXT), (20, 12))
        if self.status:
            text = small.render(self.status, True, ERROR_COLOR if self.status_error else DONE_COLOR)
            self.screen.blit(text, text.get_rect(topright=(width - 20, 20)))
        summary = small.render(self.settings.summary(), True, TEXT_DIM)
        summary_rect = summary.get_rect(topright=(width - 20, 44))
        self.screen.blit(summary, summary_rect)
        hint = fit_text(small, hint, summary_rect.x - 40)
        self.screen.blit(small.render(hint, True, TEXT_DIM), (22, 56))

    def draw_footer(self, mouse):
        width, height = window_size()
        pygame.draw.line(self.screen, CARD_BG, (0, height - FOOTER_HEIGHT),
                         (width, height - FOOTER_HEIGHT), 2)
        self.view.update_footer()
        for group in self.view.footer():
            for button in group:
                button.draw(self.screen, self.fonts.font, mouse)

    def draw(self):
        mouse = pygame.mouse.get_pos()
        self.screen.fill(BG)
        self.view.draw(self.screen, mouse)
        self.draw_header()
        self.draw_footer(mouse)
        if self.dialog:
            self.dialog.draw(self.screen, mouse)
        self.toast.draw(self.screen, self.fonts)
        pygame.display.flip()

    # --- input ------------------------------------------------------------

    def click(self, pos):
        if self.dialog:
            if self.dialog.click(pos) == 'close':
                self.close_dialog()
            return
        left, right = self.view.footer()
        if self.settings_button in right and self.settings_button.hit(pos):
            self.open_settings()
        elif self.back_button in left and self.back_button.hit(pos):
            self.back()
        elif self.folder_button in left and self.folder_button.hit(pos):
            self.open_folder()
        else:
            self.view.click(pos)

    def dialog_event(self, event):
        """Typing into a dialog that takes it; Escape closes any other."""
        if hasattr(self.dialog, 'event'):
            if self.dialog.event(event) == 'close':
                self.close_dialog()
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.close_dialog()

    def key(self, event):
        """Handles one key; returns 'quit' when the tool should close."""
        if self.dialog:
            self.dialog_event(event)
            return None
        if event.key == pygame.K_F11:
            toggle_fullscreen()
            self.place_footer()
        elif event.key == pygame.K_ESCAPE:
            if not self.back():
                return 'quit'
        elif event.key == pygame.K_s and not event.mod & pygame.KMOD_CTRL:
            self.open_settings()
        else:
            self.view.key(event)
        return None

    def scroll(self, steps):
        if self.dialog:
            scroll = getattr(self.dialog, 'scroll_by', None) or self.dialog.scroll_models
            scroll(steps)
        else:
            self.view.scroll_by(steps)

    def run(self):
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return
                if event.type == pygame.VIDEORESIZE:
                    self.place_footer()
                elif event.type == pygame.KEYDOWN:
                    if self.key(event) == 'quit':
                        return
                elif event.type == pygame.TEXTINPUT and self.dialog:
                    self.dialog_event(event)
                elif event.type == pygame.DROPFILE and not self.dialog:
                    self.view.drop_file(Path(event.file))
                elif event.type == pygame.MOUSEWHEEL:
                    self.scroll(event.y)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self.click(event.pos)
            self.poll_worker()
            self.view.tick()
            self.draw()
            self.clock.tick(FPS)


if __name__ == '__main__':
    SpriteManager().run()
    pygame.quit()
