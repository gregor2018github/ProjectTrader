"""Placing Helper: put sprites that are not on the map yet onto it, freely, and hand the spots over.

Run from anywhere:

    python build_tools/Placing_Helper/Placing_Helper.py

Left, the map as the game draws it (assets/tiles/Map1.tmx: the ground layers,
then the buildings and trees y-sorted on their base, so a roof covers what
stands behind it as it will in the game). Right, the sprites of
assets/map_sprites/houses/ and trees/ by tab (Buildings, Decoration, Trees),
by default only those no object on the map uses yet.

Pick a sprite in the list and it hangs on the mouse by the middle of its
base; a left click puts it down (Shift+click keeps another on the mouse,
for rows of trees). A placement put down can be picked up and dragged,
scaled, given a note ("a home for 20, door to the street", "warehouse,
600 gold") and deleted. By default the object's point - the sprite's
bottom-left corner - snaps to the tile grid, as Tiled's previews need; G
lets it go anywhere.

Everything is saved as you go to placements.json beside this file
(placements.py has the format): per placement the sprite, the Tiled
object's x, y and Scale, its drawn and collision boxes, what it overlaps,
the note, and a first command for the place-building skill's script. When
it starts, the helper drops the placements it finds on the map by then.

Keys:
    Mouse wheel        zoom (towards the pointer); Ctrl+wheel scales the held or chosen sprite
    Drag (left on empty ground, right or middle anywhere)   pan; arrows pan too
    [ / ]              scale down / up by 0.05 (Shift: 0.01), 0 back to 1
    Arrows             with a placement chosen: nudge it a tile (a pixel with G off)
    D                  another of the chosen placement on the mouse
    Enter or N         write the chosen placement's note
    Delete             delete the chosen placement
    White handles      on the chosen building's collision box: drag an edge or corner to fit it
                       to the walls (in the sprite's pixels, so it moves and scales with it)
    R                  its collision box back to the catalog's
    F                  put a figure down at the pointer for scale (again on it: take it away)
    C                  collision boxes of what is on the map (white; also the panel's switch)
    T                  day or night (the panel's switch too): 22:00 on the 1st of Spring, darkened
                       and lit as the game does it
    L                  at night, which windows are lit: none, as the game picks them (again: a
                       new night), or all of them
    Right-click a window light (outlined under the pointer, lit or not): edit it. Drag it, or a
                       rectangle's edges and corners by the white handles; arrows nudge it a
                       pixel, Shift+arrows make it wider or taller; R puts it back, Delete
                       removes it, Escape is done. Shaped windows (the Townhall's, Church's,
                       Guildhall's polygons) only move. The changes go into Map1.tmx with
                       "Save to map", or when closing, which asks first.
    O                  roof mode: the roofs and their holes, edited point by point (roof_mode.py
                       has its keys: click a roof, drag its points, click an edge for a new one,
                       right-click a point to take it away, P a new roof, H a new hole, Ctrl+Z
                       undo); saved into Map1.tmx with the lights
    G                  snap to the tile grid on / off
    Tab, U             next tab, only sprites not on the map on / off
    Ctrl+S             save now (it saves by itself anyway)
    Escape             drop what is on the mouse, then the choice, then close

The code: map_scene.py (the map, its chunks and objects, the sprites),
placements.py (a placement and the file), light_edits.py (window lights
moved, resized, removed, and writing them into the map), roof_edits.py (the
roofs and holes, their undo, and writing them into the map), roof_mode.py
(the roof mode's input and drawing), this file (the window).
"""

import os
import sys
from pathlib import Path

os.environ.setdefault('SDL_MOUSE_FOCUS_CLICKTHROUGH', '1')
os.environ.setdefault('SDL_VIDEO_CENTERED', '1')

import pygame  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(1, str(HERE.parent / 'Sprite_Manager'))   # its theme and widgets, as the Sound Manager does
from light_edits import LightEdits, geometry  # noqa: E402
from map_scene import LIGHT_MODES, TABS, TILE, BuildingLight, Scene, boxes_overlap, draw_box  # noqa: E402
from placements import Placement, load, save  # noqa: E402
from roof_mode import ROOF_KEYS_HINT, RoofMode  # noqa: E402
from theme import (  # noqa: E402
    BAR_BG, BG, CARD_BG, CARD_HOVER, CARD_SELECTED, CHIP_HEIGHT, DIALOG_LINE, DONE_COLOR, ERROR_COLOR,
    TEXT, TEXT_DIM, THUMB_BG,
)
from widgets import Button, Fonts, TextField, Toast, draw_chips, fit_text, wrap_text  # noqa: E402

WINDOW_TITLE = "Merchant's Rise - Placing Helper"
WINDOW_SIZE = (1600, 940)
PLACEMENTS_FILE = HERE / 'placements.json'
PANEL_W = 380
PAD = 14
ROW_H = 84
THUMB = 72
DETAIL_H = 290
FOOTER_H = 30
FPS = 60
ZOOMS = (0.125, 0.1875, 0.25, 0.375, 0.5, 0.75, 1.0, 1.5, 2.0)
START_ZOOM = 4
SCALE_STEP, SCALE_FINE = 0.05, 0.01
WHEEL_SCALE_STEP = 0.02
MIN_SCALE, MAX_SCALE = 0.1, 4.0
PAN_KEY_PX = 120                 # screen pixels per arrow press
DRAG_THRESHOLD = 4
AUTOSAVE_MS = 400
GHOST_ALPHA = 170
PLACEMENT_LINE = (255, 200, 60)
CHOSEN_LINE = (90, 220, 255)
PLACEMENT_COLLISION = (255, 140, 0)
OVERLAP_COLLISION = (255, 30, 30)   # both boxes of a collision that overlaps another
EDGE_GRAB_PX = 7                    # screen px from an edge of the chosen collision box that grab it
HANDLE_PX = 7                       # its handles' size
MIN_BOX_PX = 4                      # sprite px a collision box keeps at least
FIGURE_GRAB_PX = 18              # world px around a figure's feet that take it away
#: Which tabs show only the sprites not on the map at first; trees are planted again and again
UNPLACED_ONLY = {'Buildings': True, 'Decoration': True, 'Trees': False}
KEYS_HINT = ('Wheel zoom   [ ] scale   G grid   C collision   T night   L lights   O roofs   F figure   '
             'D another   Enter note   Del delete')
LIGHT_LABELS = {'none': 'No lights', 'random': 'As in game  (L)', 'all': 'All lights'}
LIGHT_HOVER = (255, 225, 120)       # the window light under the pointer, ready for a right-click
LIGHT_EDITED = (90, 220, 255)       # the one being edited, with its handles
LIGHT_GRAB_SLACK_PX = 4             # screen px around a window light that still pick it
DIALOG_W = 520


class PlacingHelper(RoofMode):
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode(WINDOW_SIZE, pygame.RESIZABLE)
        pygame.display.set_caption(WINDOW_TITLE)
        pygame.key.stop_text_input()
        pygame.key.set_repeat(300, 40)
        self.fonts = Fonts(pygame.font.SysFont('segoeui', 17),
                           pygame.font.SysFont('segoeui', 14),
                           pygame.font.SysFont('segoeui', 26, bold=True))
        self.mono = pygame.font.SysFont('consolas', 14)
        self.clock = pygame.time.Clock()
        self.toast = Toast()
        self._loading_screen()

        self.scene = Scene()
        placements, figures, view, notes = load(PLACEMENTS_FILE, self.scene)
        self.placements = placements
        self.figures = list(figures)
        self.next_id = max((p.id for p in placements), default=0) + 1
        self.zoom_index = START_ZOOM
        self.cam_x, self.cam_y = self._town_centre()
        if view:
            self.zoom_index = min(len(ZOOMS) - 1, max(0, int(view.get('zoom_index', START_ZOOM))))
            self.cam_x, self.cam_y = float(view.get('x', self.cam_x)), float(view.get('y', self.cam_y))
        else:
            area = self.map_area()
            self.cam_x -= area.w / 2 / self.zoom
            self.cam_y -= area.h / 2 / self.zoom

        self.tab = TABS[0]
        self.unplaced_only = dict(UNPLACED_ONLY)
        self.list_scroll = 0
        self.tab_chips, self.toggle_chips, self.rows = [], [], []
        self.ghost = None                 # the Sprite on the mouse
        self.ghost_scale = 1.0
        self.chosen = None                # the Placement chosen
        self.snap = True
        self.show_collision = False
        self.night = False                # the map at NIGHT_TIME, lit by its windows
        self.light_mode = 'random'        # which of them: LIGHT_MODES
        self.lit = []                     # the window lights lit now
        self.time_chips, self.light_chips = [], []
        self.edits = LightEdits(self.scene)   # window lights moved, resized, removed: written on saving
        self.edit_light = None            # the window light being edited (right-click one)
        self.dialog = False               # the "save the light changes?" question on closing
        self.remove_light_button = Button('Remove  (Del)', w=124, h=34)
        self.reset_light_button = Button('Reset  (R)', w=104, h=34)
        self.done_light_button = Button('Done  (Esc)', w=110, h=34)
        self.save_lights_button = Button('Save to map', w=130, h=34)
        self.dialog_buttons = [Button('Save', w=140, h=40), Button('Discard', w=140, h=40),
                               Button('Keep editing', w=160, h=40)]
        self.init_roofs()                 # the roof mode's (roof_mode.py)
        self.roof_chips = []
        self.drag = None                  # ('pan', start, cam) or ('move', placement, grab dx, dy) or ('maybe', start, cam)
        self.dirty_at = None
        self.note_field = TextField(placeholder='Note: what it is for, what it needs  (Enter)')
        self.delete_button = Button('Delete  (Del)', w=112, h=34)
        self.goto_button = Button('Go to it', w=86, h=34)
        self.reset_box_button = Button('Reset box  (R)', w=134, h=34)
        self.pending_rows = []
        self.status = ' / '.join(notes) if notes else f'{len(self.placements)} placements in {PLACEMENTS_FILE.name}'
        if notes:
            self.mark_dirty()

    # ----- geometry

    @property
    def zoom(self):
        return ZOOMS[self.zoom_index]

    def map_area(self):
        w, h = self.screen.get_size()
        return pygame.Rect(0, 0, max(200, w - PANEL_W), max(200, h - FOOTER_H))

    def panel_rect(self):
        w, h = self.screen.get_size()
        return pygame.Rect(w - PANEL_W, 0, PANEL_W, h)

    def to_world(self, pos):
        area = self.map_area()
        return self.cam_x + (pos[0] - area.x) / self.zoom, self.cam_y + (pos[1] - area.y) / self.zoom

    def _town_centre(self):
        houses = [t for t in self.scene.things if t.layer == 'Houses']
        if not houses:
            return self.scene.width / 2, self.scene.height / 2
        return sum(t.x for t in houses) / len(houses), sum(t.y for t in houses) / len(houses)

    def centre_on(self, x, y):
        area = self.map_area()
        self.cam_x = x - area.w / 2 / self.zoom
        self.cam_y = y - area.h / 2 / self.zoom
        self.clamp_camera()

    def clamp_camera(self):
        area = self.map_area()
        margin = 400
        self.cam_x = min(max(self.cam_x, -margin), self.scene.width + margin - area.w / self.zoom)
        self.cam_y = min(max(self.cam_y, -margin), self.scene.height + margin - area.h / self.zoom)

    def set_zoom(self, index, around):
        index = min(len(ZOOMS) - 1, max(0, index))
        if index == self.zoom_index:
            return
        wx, wy = self.to_world(around)
        self.zoom_index = index
        area = self.map_area()
        self.cam_x = wx - (around[0] - area.x) / self.zoom
        self.cam_y = wy - (around[1] - area.y) / self.zoom
        self.clamp_camera()

    def snapped(self, x, y):
        if self.snap:
            return round(x / TILE) * TILE, round(y / TILE) * TILE
        return round(x), round(y)

    def ghost_point(self, mouse):
        """The object point of the sprite on the mouse: held by the middle of its base."""
        wx, wy = self.to_world(mouse)
        w = self.ghost.size[0] * self.ghost_scale
        return self.snapped(wx - w / 2, wy)

    def placement_at(self, wx, wy):
        hits = [p for p in self.placements
                if p.rect[0] <= wx <= p.rect[2] and p.rect[1] <= wy <= p.rect[3]
                and self.scene.opaque_at(p.sprite.path, p.scale, p.x, p.y, wx, wy)]
        return max(hits, key=lambda p: p.y) if hits else None

    # ----- changes

    def mark_dirty(self):
        self.dirty_at = pygame.time.get_ticks()

    def save_now(self):
        view = {'x': round(self.cam_x), 'y': round(self.cam_y), 'zoom_index': self.zoom_index}
        try:
            save(PLACEMENTS_FILE, self.scene, self.placements, self.figures, view)
        except OSError as error:
            self.status = f'Could not save: {error}'
            return False
        self.dirty_at = None
        return True

    def choose(self, placement):
        if self.note_field.focused:
            self.finish_note()
        self.chosen = placement
        if placement:
            self.note_field.text = placement.note
            self.edit_light = None

    def finish_note(self):
        self.note_field.focus(False)
        if self.chosen and self.chosen.note != self.note_field.text.strip():
            self.chosen.note = self.note_field.text.strip()
            self.mark_dirty()

    def put_down(self, mouse, keep):
        x, y = self.ghost_point(mouse)
        p = Placement(self.next_id, self.ghost, x, y, round(self.ghost_scale, 4))
        self.next_id += 1
        self.placements.append(p)
        self.mark_dirty()
        self.status = f'Placement {p.id}: {p.sprite.stem} at {x:g}, {y:g}'
        if keep:
            self.choose(None)
        else:
            self.ghost = None
            self.choose(p)

    def delete(self, placement):
        self.placements.remove(placement)
        if self.chosen is placement:
            self.choose(None)
        self.status = f'Deleted placement {placement.id} ({placement.sprite.stem})'
        self.mark_dirty()

    def rescale(self, delta=None, value=None):
        if self.ghost:
            current = self.ghost_scale
        elif self.chosen:
            current = self.chosen.scale
        else:
            return
        new = value if value is not None else current + delta
        new = round(min(MAX_SCALE, max(MIN_SCALE, new)), 4)
        if self.ghost:
            self.ghost_scale = new
        else:
            # Keep it standing where it stands: the middle of its base stays put
            p = self.chosen
            mid = p.x + p.size[0] / 2
            p.scale = new
            p.x, _ = self.snapped(mid - p.size[0] / 2, p.y)
            self.mark_dirty()

    def toggle_figure(self, mouse):
        wx, wy = self.to_world(mouse)
        for f in self.figures:
            if abs(f[0] - wx) <= FIGURE_GRAB_PX and abs(f[1] - wy) <= FIGURE_GRAB_PX * 2:
                self.figures.remove(f)
                self.mark_dirty()
                return
        self.figures.append((round(wx), round(wy)))
        self.mark_dirty()

    # ----- the list

    def shown_sprites(self):
        pending = {p.sprite.key for p in self.placements}
        out = []
        for s in self.scene.sprites:
            if s.tab != self.tab:
                continue
            if self.unplaced_only[self.tab] and (s.on_map or s.key in pending):
                continue
            out.append(s)
        return out

    def list_rect(self):
        panel = self.panel_rect()
        top = PAD + 40 + CHIP_HEIGHT * 4 + 36     # under the tabs and the three rows of switches
        return pygame.Rect(panel.x + PAD, top, panel.w - 2 * PAD, panel.h - top - DETAIL_H - PAD)

    def thumb(self, sprite):
        cache = getattr(self, '_thumbs', None)
        if cache is None:
            cache = self._thumbs = {}
        image = cache.get(sprite.key)
        if image is None:
            src = self.scene.source(sprite.path)
            box = src.get_bounding_rect()
            if box.w and box.h:
                src = src.subsurface(box)
            factor = min(THUMB / src.get_width(), THUMB / src.get_height(), 2)
            size = (max(1, int(src.get_width() * factor)), max(1, int(src.get_height() * factor)))
            image = cache[sprite.key] = pygame.transform.smoothscale(src, size)
        return image

    # ----- events

    def run(self):
        while True:
            for event in pygame.event.get():
                result = self.handle(event)
                if result == 'quit' and self.unsaved() and not self.dialog:
                    self.dialog = True        # ask first: save the changes to the map?
                elif result in ('quit', 'quit now'):
                    self.finish_note()
                    self.save_now()
                    pygame.quit()
                    return
            if self.dirty_at is not None and pygame.time.get_ticks() - self.dirty_at > AUTOSAVE_MS:
                self.save_now()
            self.draw()
            pygame.display.flip()
            self.clock.tick(FPS)

    def handle(self, event):
        if self.dialog:
            return self.dialog_event(event)
        if event.type == pygame.QUIT:
            return 'quit'
        if event.type == pygame.VIDEORESIZE:
            self.clamp_camera()
            return None
        if event.type == pygame.TEXTINPUT and self.note_field.focused:
            self.note_field.type(event.text)
            return None
        if event.type == pygame.KEYDOWN:
            return self.key(event)
        if event.type == pygame.MOUSEWHEEL:
            self.wheel(event)
        elif event.type == pygame.MOUSEBUTTONDOWN:
            self.mouse_down(event)
        elif event.type == pygame.MOUSEBUTTONUP:
            self.mouse_up(event)
        elif event.type == pygame.MOUSEMOTION:
            self.mouse_move(event)
        return None

    def unsaved(self):
        """Changes to window lights and roofs not written into the map yet."""
        return self.edits.count + self.roof_edits.count

    def dialog_event(self, event):
        """The question on closing with changes to the map not saved: Save, Discard or Keep editing."""
        choice = None
        if event.type == pygame.KEYDOWN:
            choice = {pygame.K_RETURN: 'Save', pygame.K_KP_ENTER: 'Save', pygame.K_s: 'Save',
                      pygame.K_d: 'Discard', pygame.K_ESCAPE: 'Keep editing'}.get(event.key)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            choice = next((b.label for b in self.dialog_buttons if b.hit(event.pos)), None)
        if choice == 'Save':
            if self.save_map():
                return 'quit now'
            self.dialog = False
        elif choice == 'Discard':
            return 'quit now'
        elif choice == 'Keep editing':
            self.dialog = False
        return None

    def save_map(self):
        """Write the window light and roof changes into Map1.tmx; False if that failed."""
        count = self.unsaved()
        done, missing = [], []
        try:
            for edits, what in ((self.edits, 'window lights'), (self.roof_edits, 'roofs and holes')):
                if edits.count:
                    written, lost = edits.save()
                    done.append(f'{written} {what}')
                    missing += lost
        except (OSError, ValueError) as error:
            self.status = f'Could not write the map: {error}'
            return False
        self.status = (' and '.join(done) + ' written to Map1.tmx' if done else 'Nothing to save') + (
            f'; not found any more: {", ".join(map(str, missing))}' if missing else '')
        if count:
            self.toast.show('Saved to the map')
        return True

    def edit_key(self, event):
        """A key while a window light is being edited; True if it was the editor's."""
        k, shift, light = event.key, event.mod & pygame.KMOD_SHIFT, self.edit_light
        if k == pygame.K_ESCAPE:
            self.edit_light = None
        elif k in (pygame.K_DELETE, pygame.K_BACKSPACE):
            self.remove_light(light)
        elif k == pygame.K_r:
            self.edits.reset(light)
            self.status = f'Window light {light.obj_id} back where it was'
        elif k in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN):
            dx = (k == pygame.K_RIGHT) - (k == pygame.K_LEFT)
            dy = (k == pygame.K_DOWN) - (k == pygame.K_UP)
            x, y, w, h = geometry(light)
            if shift and not isinstance(light, BuildingLight):
                self.edits.set_geometry(light, x, y, w + dx, h + dy)    # Shift: wider, taller
            else:
                self.edits.set_geometry(light, x + dx, y + dy, w, h)
        else:
            return False
        return True

    def remove_light(self, light):
        self.edits.remove(light)
        if light in self.lit:
            self.lit.remove(light)
        self.edit_light = None
        self.status = f'Window light {light.obj_id} removed ({self.edits.count} light changes to save)'

    def light_screen_rect(self, light):
        area = self.map_area()
        x, y, w, h = geometry(light)
        return pygame.Rect(round((x - self.cam_x) * self.zoom) + area.x, round((y - self.cam_y) * self.zoom) + area.y,
                           max(1, round(w * self.zoom)), max(1, round(h * self.zoom)))

    def light_at_screen(self, pos):
        wx, wy = self.to_world(pos)
        return self.scene.light_at(wx, wy, LIGHT_GRAB_SLACK_PX / self.zoom)

    def light_edges_at(self, pos):
        """Edges of the edited window light under the pointer: a set of them, {'move'} inside it, or empty."""
        light = self.edit_light
        if not light or self.ghost:
            return set()
        rect, g = self.light_screen_rect(light), EDGE_GRAB_PX
        x, y = pos
        if not (rect.left - g <= x <= rect.right + g and rect.top - g <= y <= rect.bottom + g):
            return set()
        edges = set()
        if not isinstance(light, BuildingLight):     # a shaped window only moves
            if abs(x - rect.left) <= g:
                edges.add('left')
            elif abs(x - rect.right) <= g:
                edges.add('right')
            if abs(y - rect.top) <= g:
                edges.add('top')
            elif abs(y - rect.bottom) <= g:
                edges.add('bottom')
        return edges or {'move'}

    def key(self, event):
        if self.note_field.focused:
            if self.note_field.key(event) == 'done':
                self.finish_note()
            return None
        if event.key == pygame.K_o and not event.mod & pygame.KMOD_CTRL:
            self.set_roof_mode(not self.roof_mode)
            return None
        if self.roof_mode and self.roof_key(event):
            return None
        if self.edit_light and self.edit_key(event):
            return None
        k, mods = event.key, event.mod
        shift = mods & pygame.KMOD_SHIFT
        if k == pygame.K_ESCAPE:
            if self.ghost:
                self.ghost = None
            elif self.chosen:
                self.choose(None)
            else:
                return 'quit'
        elif k == pygame.K_s and mods & pygame.KMOD_CTRL:
            if self.save_now():
                self.status = f'Saved {len(self.placements)} placements to {PLACEMENTS_FILE.name}'
                self.toast.show('Saved')
        elif k in (pygame.K_LEFTBRACKET, pygame.K_MINUS, pygame.K_KP_MINUS):
            self.rescale(-(SCALE_FINE if shift else SCALE_STEP))
        elif k in (pygame.K_RIGHTBRACKET, pygame.K_PLUS, pygame.K_KP_PLUS, pygame.K_EQUALS):
            self.rescale(SCALE_FINE if shift else SCALE_STEP)
        elif k in (pygame.K_0, pygame.K_KP0):
            self.rescale(value=1.0)
        elif k == pygame.K_g:
            self.snap = not self.snap
            self.status = 'Snapping to the tile grid' if self.snap else 'Free placement, off the grid (--no-snap)'
        elif k == pygame.K_c:
            self.show_collision = not self.show_collision
        elif k == pygame.K_t:
            self.set_night(not self.night)
        elif k == pygame.K_l:
            self.set_light_mode(LIGHT_MODES[(LIGHT_MODES.index(self.light_mode) + 1) % len(LIGHT_MODES)])
        elif k == pygame.K_f and self.map_area().collidepoint(pygame.mouse.get_pos()):
            self.toggle_figure(pygame.mouse.get_pos())
        elif k == pygame.K_TAB:
            self.tab = TABS[(TABS.index(self.tab) + (-1 if shift else 1)) % len(TABS)]
            self.list_scroll = 0
        elif k == pygame.K_u:
            self.unplaced_only[self.tab] = not self.unplaced_only[self.tab]
            self.list_scroll = 0
        elif k == pygame.K_d and self.chosen:
            self.ghost, self.ghost_scale = self.chosen.sprite, self.chosen.scale
            self.choose(None)
        elif k in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_n) and self.chosen:
            self.note_field.focus(True)
        elif k == pygame.K_DELETE and self.chosen:
            self.delete(self.chosen)
        elif k == pygame.K_r and self.chosen:
            self.reset_collision()
        elif k in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN):
            dx = (k == pygame.K_RIGHT) - (k == pygame.K_LEFT)
            dy = (k == pygame.K_DOWN) - (k == pygame.K_UP)
            if self.chosen:
                step = TILE if self.snap else 1
                self.chosen.x += dx * step
                self.chosen.y += dy * step
                self.mark_dirty()
            else:
                self.cam_x += dx * PAN_KEY_PX / self.zoom
                self.cam_y += dy * PAN_KEY_PX / self.zoom
                self.clamp_camera()
        return None

    def wheel(self, event):
        mouse = pygame.mouse.get_pos()
        if self.list_rect().collidepoint(mouse):
            self.list_scroll = max(0, self.list_scroll - event.y * ROW_H // 2)
        elif self.map_area().collidepoint(mouse):
            if pygame.key.get_mods() & pygame.KMOD_CTRL and (self.ghost or self.chosen):
                fine = pygame.key.get_mods() & pygame.KMOD_SHIFT
                self.rescale(event.y * (WHEEL_SCALE_STEP / 4 if fine else WHEEL_SCALE_STEP))
            else:
                self.set_zoom(self.zoom_index + (1 if event.y > 0 else -1), mouse)

    def mouse_down(self, event):
        pos = event.pos
        if self.note_field.focused and not self.note_field.rect.collidepoint(pos):
            self.finish_note()
        if self.panel_rect().collidepoint(pos):
            if event.button == 1:
                self.panel_click(pos)
            return
        if not self.map_area().collidepoint(pos):
            return
        if event.button in (2, 3):
            self.drag = ('maybe', pos, (self.cam_x, self.cam_y), event.button)
            return
        if event.button != 1:
            return
        if self.roof_mode:
            self.roof_mouse_down(pos)
            return
        if self.ghost:
            self.put_down(pos, keep=bool(pygame.key.get_mods() & pygame.KMOD_SHIFT))
            return
        if self.edit_light:
            edges = self.light_edges_at(pos)
            if edges:
                wx, wy = self.to_world(pos)
                x, y, _, _ = geometry(self.edit_light)
                self.drag = ('light', self.edit_light, edges, wx - x, wy - y)
                return
            self.edit_light = None             # a click elsewhere ends the editing
        edges = self.collision_edges_at(pos)
        if edges:
            self.drag = ('edge', self.chosen, edges)
            return
        wx, wy = self.to_world(pos)
        hit = self.placement_at(wx, wy)
        if hit:
            self.choose(hit)
            self.drag = ('move', hit, wx - hit.x, wy - hit.y)
        else:
            self.drag = ('maybe', pos, (self.cam_x, self.cam_y), 1)

    def mouse_move(self, event):
        if not self.drag:
            return
        if self.drag[0] == 'maybe':
            _, start, cam, button = self.drag
            if abs(event.pos[0] - start[0]) + abs(event.pos[1] - start[1]) > DRAG_THRESHOLD:
                self.drag = ('pan', start, cam, button)
        if self.drag[0] == 'pan':
            _, start, cam, _ = self.drag
            self.cam_x = cam[0] - (event.pos[0] - start[0]) / self.zoom
            self.cam_y = cam[1] - (event.pos[1] - start[1]) / self.zoom
            self.clamp_camera()
        elif self.drag[0] in ('vertex', 'ring'):
            self.roof_mouse_move(event.pos)
        elif self.drag[0] == 'move':
            _, p, gx, gy = self.drag
            wx, wy = self.to_world(event.pos)
            x, y = self.snapped(wx - gx, wy - gy)
            if (x, y) != (p.x, p.y):
                p.x, p.y = x, y
                self.mark_dirty()
        elif self.drag[0] == 'edge':
            _, p, edges = self.drag
            wx, wy = self.to_world(event.pos)
            # In the sprite's own pixels, whole ones, so the margins come out whole
            sx, sy = round((wx - p.x) / p.scale), round((wy - p.y) / p.scale)
            left, top, right, bottom = p.box_px
            if 'left' in edges:
                left = min(sx, right - MIN_BOX_PX)
            if 'right' in edges:
                right = max(sx, left + MIN_BOX_PX)
            if 'top' in edges:
                top = min(sy, bottom - MIN_BOX_PX)
            if 'bottom' in edges:
                bottom = max(sy, top + MIN_BOX_PX)
            if (left, top, right, bottom) != tuple(p.box_px):
                p.collision_box = (left, top, right, bottom)
                self.mark_dirty()
        elif self.drag[0] == 'light':
            _, light, edges, gx, gy = self.drag
            wx, wy = self.to_world(event.pos)
            x, y, w, h = geometry(light)
            if edges == {'move'}:
                x, y = round(wx - gx), round(wy - gy)    # whole world pixels
            else:
                left, top, right, bottom = x, y, x + w, y + h
                if 'left' in edges:
                    left = min(round(wx), right - 2)
                if 'right' in edges:
                    right = max(round(wx), left + 2)
                if 'top' in edges:
                    top = min(round(wy), bottom - 2)
                if 'bottom' in edges:
                    bottom = max(round(wy), top + 2)
                x, y, w, h = left, top, right - left, bottom - top
            if (x, y, w, h) != geometry(light):
                self.edits.set_geometry(light, x, y, w, h)

    def collision_edges_at(self, pos):
        """Which edges of the chosen building's collision box are under the pointer (a corner: two)."""
        p = self.chosen
        if not p or p.sprite.layer != 'Houses' or self.ghost:
            return set()
        area = self.map_area()
        left, top, right, bottom = ((v - c) * self.zoom + o for v, c, o in zip(
            p.collision, (self.cam_x, self.cam_y) * 2, (area.x, area.y) * 2))
        x, y, g = pos[0], pos[1], EDGE_GRAB_PX
        if not (left - g <= x <= right + g and top - g <= y <= bottom + g):
            return set()
        edges = set()
        if abs(x - left) <= g:
            edges.add('left')
        elif abs(x - right) <= g:
            edges.add('right')
        if abs(y - top) <= g:
            edges.add('top')
        elif abs(y - bottom) <= g:
            edges.add('bottom')
        return edges

    def set_night(self, on):
        self.night = on
        if on:
            self.lit = self.scene.lit_windows(self.light_mode)
            self.status = f'Night: {len(self.lit)} windows lit ({LIGHT_LABELS[self.light_mode].split("  ")[0].lower()})'
        else:
            self.status = 'Day'

    def set_light_mode(self, mode):
        """Which windows are lit at night; "As in game" again draws a new night. Night comes with it."""
        self.light_mode = mode
        self.set_night(True)

    def reset_collision(self):
        if self.chosen and self.chosen.collision_box:
            self.chosen.collision_box = None
            self.status = f'Placement {self.chosen.id}: collision box back to the catalog\'s'
            self.mark_dirty()

    def set_cursor(self, cursor):
        if cursor != getattr(self, '_cursor', None):
            self._cursor = cursor
            try:
                pygame.mouse.set_system_cursor(cursor)
            except pygame.error:
                pass

    def update_cursor(self, mouse):
        """A resize arrow over an edge of the chosen collision box."""
        if self.roof_mode:
            self.set_cursor(self.roof_cursor(mouse))
            return
        if self.drag and self.drag[0] in ('edge', 'light'):
            edges = self.drag[2]
        else:
            edges = self.light_edges_at(mouse) or self.collision_edges_at(mouse)
        if edges == {'move'}:
            edges = set()
            cursor = pygame.SYSTEM_CURSOR_SIZEALL
            if cursor != getattr(self, '_cursor', None):
                self._cursor = cursor
                try:
                    pygame.mouse.set_system_cursor(cursor)
                except pygame.error:
                    pass
            return
        if edges in ({'left', 'top'}, {'right', 'bottom'}):
            cursor = pygame.SYSTEM_CURSOR_SIZENWSE
        elif edges in ({'right', 'top'}, {'left', 'bottom'}):
            cursor = pygame.SYSTEM_CURSOR_SIZENESW
        elif edges & {'left', 'right'}:
            cursor = pygame.SYSTEM_CURSOR_SIZEWE
        elif edges:
            cursor = pygame.SYSTEM_CURSOR_SIZENS
        else:
            cursor = pygame.SYSTEM_CURSOR_ARROW
        if cursor != getattr(self, '_cursor', None):
            self._cursor = cursor
            try:
                pygame.mouse.set_system_cursor(cursor)
            except pygame.error:
                pass

    def mouse_up(self, event):
        if not self.drag:
            return
        if self.drag[0] in ('vertex', 'ring'):
            self.roof_edits.drop_unchanged_checkpoint()
        elif self.drag[0] == 'maybe' and self.roof_mode:
            if self.drag[3] == 3:
                self.roof_right_click(event.pos)
        elif self.drag[0] == 'maybe':
            # A click without a drag: on empty ground it lets go of the choice,
            # with the right button it also drops what is on the mouse
            light = self.light_at_screen(event.pos) if self.drag[3] == 3 else None
            if self.drag[3] == 3 and self.ghost:
                self.ghost = None
            elif light:
                # A right-click on a window light: edit it
                self.choose(None)
                self.edit_light = light
                self.status = (f'Editing window light {light.obj_id}: drag it'
                               + ('' if isinstance(light, BuildingLight) else ' or its edges')
                               + ', arrows nudge, Del removes, R resets, Esc done')
            elif self.drag[3] in (1, 3):
                self.choose(None)
                self.edit_light = None
        self.drag = None

    def panel_click(self, pos):
        for rect, tab in self.tab_chips:
            if rect.collidepoint(pos):
                self.tab, self.list_scroll = tab, 0
                return
        for rect, value in self.time_chips:
            if rect.collidepoint(pos):
                self.set_night(value == 'night')
                return
        for rect, mode in self.light_chips:
            if rect.collidepoint(pos):
                self.set_light_mode(mode)
                return
        for rect, _ in self.roof_chips:
            if rect.collidepoint(pos):
                self.set_roof_mode(not self.roof_mode)
                return
        for rect, value in self.toggle_chips:
            if rect.collidepoint(pos):
                if value == 'collision':
                    self.show_collision = not self.show_collision
                else:
                    self.unplaced_only[self.tab] = not self.unplaced_only[self.tab]
                    self.list_scroll = 0
                return
        for rect, sprite in self.rows:
            if rect.collidepoint(pos):
                if self.roof_mode:
                    self.set_roof_mode(False)
                self.ghost = sprite
                self.ghost_scale = 1.0
                self.choose(None)
                self.status = f'{sprite.stem} on the mouse: click on the map to put it down (Shift+click for another)'
                return
        if self.roof_mode:
            self.roof_panel_click(pos)
            return
        if self.edit_light:
            if self.remove_light_button.hit(pos):
                self.remove_light(self.edit_light)
            elif self.reset_light_button.hit(pos):
                self.edits.reset(self.edit_light)
            elif self.done_light_button.hit(pos):
                self.edit_light = None
            elif self.save_lights_button.hit(pos):
                self.save_map()
            return
        if self.unsaved() and self.save_lights_button.hit(pos):
            self.save_map()
            return
        if self.chosen:
            if self.note_field.rect.collidepoint(pos):
                self.note_field.focus(True)
            elif self.delete_button.hit(pos):
                self.delete(self.chosen)
            elif self.reset_box_button.hit(pos):
                self.reset_collision()
            elif self.goto_button.hit(pos):
                self.centre_on(self.chosen.x + self.chosen.size[0] / 2, self.chosen.y - self.chosen.size[1] / 2)
        else:
            for rect, p in self.pending_rows:
                if rect.collidepoint(pos):
                    self.choose(p)
                    self.centre_on(p.x + p.size[0] / 2, p.y - p.size[1] / 2)
                    return

    # ----- drawing

    def draw(self):
        self.screen.fill(BG)
        area = self.map_area()
        mouse = pygame.mouse.get_pos()
        extra = []
        for p in self.placements:
            extra.append((p.y, self._placement_drawer(p)))
        for fx, fy in self.figures:
            extra.append((fy, lambda s, ox, oy, z, fx=fx, fy=fy: self.scene.draw_figure(s, ox, oy, z, fx, fy)))
        ghost_point = None
        if self.ghost and area.collidepoint(mouse):
            ghost_point = self.ghost_point(mouse)
            extra.append((ghost_point[1], self._ghost_drawer(ghost_point)))
        night = None
        if self.night:
            # The window being edited is shown lit, whichever are lit tonight
            night = self.lit + ([self.edit_light] if self.edit_light and self.edit_light not in self.lit else [])
        ox, oy = self.scene.draw(self.screen, area, self.cam_x, self.cam_y, self.zoom, extra, self.show_collision,
                                 night=night)

        self.screen.set_clip(area)
        # Collision boxes of what is being placed: red where one overlaps
        # anything (and the box it overlaps red too), only as a warning
        new_boxes = [p.collision for p in self.placements]
        if ghost_point:
            new_boxes.append(Placement(0, self.ghost, ghost_point[0], ghost_point[1], self.ghost_scale).collision)
        clashing = set()
        for t in self.scene.things:
            if t.collision and any(boxes_overlap(t.collision, b) for b in new_boxes):
                draw_box(self.screen, t.collision, ox, oy, self.zoom, OVERLAP_COLLISION, 2)
                clashing.update(i for i, b in enumerate(new_boxes) if boxes_overlap(t.collision, b))
        for i, a in enumerate(new_boxes):
            for j in range(i + 1, len(new_boxes)):
                if boxes_overlap(a, new_boxes[j]):
                    clashing.update((i, j))
        for i, box in enumerate(new_boxes):
            if box:
                red = i in clashing
                draw_box(self.screen, box, ox, oy, self.zoom,
                         OVERLAP_COLLISION if red else PLACEMENT_COLLISION, 2 if red else 1)
        if self.chosen and self.chosen.sprite.layer == 'Houses' and not self.ghost:
            # Handles on the chosen building's collision box: its edges and corners can be dragged
            left, top, right, bottom = self.chosen.collision
            xs = (ox + round(left * self.zoom), ox + round((left + right) / 2 * self.zoom), ox + round(right * self.zoom))
            ys = (oy + round(top * self.zoom), oy + round((top + bottom) / 2 * self.zoom), oy + round(bottom * self.zoom))
            for i, hx in enumerate(xs):
                for j, hy in enumerate(ys):
                    if i == 1 and j == 1:
                        continue
                    handle = pygame.Rect(0, 0, HANDLE_PX, HANDLE_PX)
                    handle.center = (hx, hy)
                    pygame.draw.rect(self.screen, (255, 255, 255), handle)
                    pygame.draw.rect(self.screen, (0, 0, 0), handle, 1)
        for p in self.placements:
            draw_box(self.screen, p.rect, ox, oy, self.zoom,
                     CHOSEN_LINE if p is self.chosen else PLACEMENT_LINE, 2 if p is self.chosen else 1)
            label = self.fonts.small.render(f'{p.id} {p.sprite.stem}', True, TEXT)
            lx, ly = ox + round(p.x * self.zoom), oy + round(p.y * self.zoom) + 2
            pygame.draw.rect(self.screen, (0, 0, 0), (lx, ly, label.get_width() + 6, label.get_height()))
            self.screen.blit(label, (lx + 3, ly))
        if not self.roof_mode:
            self.draw_light_marks(mouse)
        self.screen.set_clip(None)
        if self.roof_mode:
            self.draw_roofs(area, mouse)

        self.update_cursor(mouse)
        self.draw_overlay(area, mouse, ghost_point)
        self.draw_footer(area)
        self.draw_panel(mouse)
        if self.dialog:
            self.draw_dialog(mouse)
        self.toast.draw(self.screen, self.fonts)

    def draw_light_marks(self, mouse):
        """The window light under the pointer outlined (lit or not), and the edited one with its handles."""
        area = self.map_area()
        if area.collidepoint(mouse) and not self.ghost and not self.drag:
            hover = self.light_at_screen(mouse)
            if hover and hover is not self.edit_light:
                pygame.draw.rect(self.screen, LIGHT_HOVER, self.light_screen_rect(hover).inflate(4, 4), 1)
        light = self.edit_light
        if not light:
            return
        rect = self.light_screen_rect(light)
        pygame.draw.rect(self.screen, LIGHT_EDITED, rect.inflate(4, 4), 2)
        if isinstance(light, BuildingLight):
            return                                  # a shaped window only moves: no handles
        for hx in (rect.left, rect.centerx, rect.right):
            for hy in (rect.top, rect.centery, rect.bottom):
                if (hx, hy) == rect.center:
                    continue
                handle = pygame.Rect(0, 0, HANDLE_PX, HANDLE_PX)
                handle.center = (hx, hy)
                pygame.draw.rect(self.screen, (255, 255, 255), handle)
                pygame.draw.rect(self.screen, (0, 0, 0), handle, 1)

    def draw_dialog(self, mouse):
        """Closing with window light changes not saved: save them into the map, throw them away, or stay."""
        w, h = self.screen.get_size()
        shade = pygame.Surface((w, h), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 150))
        self.screen.blit(shade, (0, 0))
        box = pygame.Rect(0, 0, DIALOG_W, 220)
        box.center = (w // 2, h // 2)
        pygame.draw.rect(self.screen, BAR_BG, box, border_radius=10)
        pygame.draw.rect(self.screen, DIALOG_LINE, box, 2, border_radius=10)
        y = box.y + 22
        title = self.fonts.title.render('Save your changes to the map?', True, TEXT)
        self.screen.blit(title, (box.x + 24, y))
        y += 46
        lines = [f'{self.edits.count} window lights moved, resized or removed; '
                 f'{self.roof_edits.count} roofs or holes changed, added or deleted.',
                 'Save writes them into assets/tiles/Map1.tmx (close Tiled first if it has the map open).']
        for line in lines:
            for part in wrap_text(self.fonts.small, line, box.w - 48, 2):
                self.screen.blit(self.fonts.small.render(part, True, TEXT_DIM), (box.x + 24, y))
                y += 20
        x = box.x + 24
        for button in self.dialog_buttons:
            button.rect.topleft = (x, box.bottom - 60)
            button.draw(self.screen, self.fonts.font, mouse)
            x = button.rect.right + 12

    def _placement_drawer(self, p):
        def draw(screen, ox, oy, zoom):
            image = self.scene.image(p.sprite.path, p.scale * zoom)
            screen.blit(image, (ox + round(p.x * zoom), oy + round(p.y * zoom) - image.get_height()))
        return draw

    def _ghost_drawer(self, point):
        def draw(screen, ox, oy, zoom):
            image = self.scene.image(self.ghost.path, self.ghost_scale * zoom).copy()
            image.set_alpha(GHOST_ALPHA)
            screen.blit(image, (ox + round(point[0] * zoom), oy + round(point[1] * zoom) - image.get_height()))
        return draw

    def draw_overlay(self, area, mouse, ghost_point):
        lines = [f'Zoom {self.zoom:g}   Grid {"on" if self.snap else "off"}'
                 + ('   Collision shown' if self.show_collision else '')]
        if area.collidepoint(mouse):
            wx, wy = self.to_world(mouse)
            lines.append(f'Pointer {wx:.0f}, {wy:.0f}   tile {int(wx // TILE)}, {int(wy // TILE)}')
        if ghost_point:
            w, h = self.ghost.size[0] * self.ghost_scale, self.ghost.size[1] * self.ghost_scale
            lines.append(f'{self.ghost.stem} at {ghost_point[0]:g}, {ghost_point[1]:g}   '
                         f'scale {self.ghost_scale:g}   {w:.0f} x {h:.0f} px')
        if self.scene.missing:
            lines.append(f'Drawing the ground ... ({self.scene.missing} pieces to go)')
        y = area.y + 8
        for line in lines:
            text = self.mono.render(line, True, TEXT)
            pygame.draw.rect(self.screen, (0, 0, 0), (area.x + 8, y, text.get_width() + 10, text.get_height() + 4))
            self.screen.blit(text, (area.x + 13, y + 2))
            y += text.get_height() + 6

        if area.collidepoint(mouse) and not self.ghost and not self.drag:
            wx, wy = self.to_world(mouse)
            if not self.placement_at(wx, wy):
                thing = self.scene.thing_at(wx, wy)
                if thing:
                    shown = thing.props.get('Display_name') or thing.name
                    tip = f'{shown}  (id {thing.obj_id}, {thing.file_name}' \
                          + (f', Scale {thing.scale:g}' if thing.scale != 1 else '') + ')'
                    text = self.fonts.small.render(tip, True, TEXT)
                    tx = min(mouse[0] + 16, area.right - text.get_width() - 12)
                    ty = max(area.y, mouse[1] - 30)
                    pygame.draw.rect(self.screen, (0, 0, 0), (tx - 5, ty - 2, text.get_width() + 10, text.get_height() + 4))
                    self.screen.blit(text, (tx, ty))

    def draw_footer(self, area):
        bar = pygame.Rect(area.x, area.bottom, area.w, FOOTER_H)
        pygame.draw.rect(self.screen, BAR_BG, bar)
        status = self.fonts.small.render(fit_text(self.fonts.small, self.status, area.w // 2 - 20), True, TEXT)
        self.screen.blit(status, status.get_rect(midleft=(bar.x + 10, bar.centery)))
        keys = ROOF_KEYS_HINT if self.roof_mode else KEYS_HINT
        hint = self.fonts.small.render(fit_text(self.fonts.small, keys, area.w // 2 - 20), True, TEXT_DIM)
        self.screen.blit(hint, hint.get_rect(midright=(bar.right - 10, bar.centery)))

    def draw_panel(self, mouse):
        panel = self.panel_rect()
        pygame.draw.rect(self.screen, BAR_BG, panel)
        pygame.draw.line(self.screen, DIALOG_LINE, panel.topleft, panel.bottomleft)
        x = panel.x + PAD
        title = self.fonts.title.render('Placing Helper', True, TEXT)
        self.screen.blit(title, (x, PAD))
        y = PAD + 40
        self.tab_chips, y = draw_chips(self.screen, self.fonts.font, TABS, lambda t: t, self.tab,
                                       x, y, panel.w - 2 * PAD, mouse)
        y += 6
        # Two switches on one row, each lit while on
        self.toggle_chips = []
        for value, label, on in (('only', 'Unplaced only  (U)', self.unplaced_only[self.tab]),
                                 ('collision', 'Collision boxes  (C)', self.show_collision)):
            chips, _ = draw_chips(self.screen, self.fonts.font, [value], lambda _, label=label: label,
                                  value if on else None, x, y, panel.right - PAD - x, mouse)
            self.toggle_chips += chips
            x = chips[0][0].right + 8
        # Day or night, and at night which windows are lit
        x, y = panel.x + PAD, y + CHIP_HEIGHT + 6
        self.time_chips, _ = draw_chips(self.screen, self.fonts.font, ('day', 'night'),
                                        lambda t: {'day': 'Day', 'night': 'Night  (T)'}[t],
                                        'night' if self.night else 'day', x, y, panel.w - 2 * PAD, mouse)
        rx = self.time_chips[-1][0].right + 18
        self.roof_chips, y = draw_chips(self.screen, self.fonts.font, ['roofs'], lambda _: 'Roof mode  (O)',
                                        'roofs' if self.roof_mode else None, rx, y, panel.right - PAD - rx, mouse)
        y += 6
        self.light_chips, _ = draw_chips(self.screen, self.fonts.font, LIGHT_MODES,
                                         lambda m: LIGHT_LABELS[m], self.light_mode if self.night else None,
                                         x, y, panel.w - 2 * PAD, mouse)
        self.draw_list(mouse)
        self.draw_detail(mouse)

    def draw_list(self, mouse):
        rect = self.list_rect()
        sprites = self.shown_sprites()
        self.list_scroll = max(0, min(self.list_scroll, len(sprites) * ROW_H - rect.h))
        pending = {}
        for p in self.placements:
            pending[p.sprite.key] = pending.get(p.sprite.key, 0) + 1
        self.rows = []
        self.screen.set_clip(rect)
        if not sprites:
            text = self.fonts.font.render('Every sprite here is on the map.', True, TEXT_DIM)
            self.screen.blit(text, (rect.x + 4, rect.y + 8))
        for i, s in enumerate(sprites):
            row = pygame.Rect(rect.x, rect.y + i * ROW_H - self.list_scroll, rect.w, ROW_H - 6)
            if row.bottom < rect.y or row.top > rect.bottom:
                continue
            visible = row.clip(rect)
            if visible.h:
                self.rows.append((visible, s))
            held = self.ghost is s
            colour = CARD_SELECTED if held else CARD_HOVER if visible.collidepoint(mouse) else CARD_BG
            pygame.draw.rect(self.screen, colour, row, border_radius=6)
            box = pygame.Rect(row.x + 6, row.y + (row.h - THUMB) // 2, THUMB, THUMB)
            pygame.draw.rect(self.screen, THUMB_BG, box, border_radius=4)
            image = self.thumb(s)
            self.screen.blit(image, image.get_rect(center=box.center))
            tx, tw = box.right + 10, row.right - box.right - 16
            self.screen.blit(self.fonts.font.render(s.stem, True, TEXT), (tx, row.y + 6))
            desc = self.fonts.small.render(fit_text(self.fonts.small, s.description, tw), True, TEXT_DIM)
            self.screen.blit(desc, (tx, row.y + 30))
            where = f'on the map {s.on_map}x' if s.on_map else 'not on the map'
            if pending.get(s.key):
                where += f', placed here {pending[s.key]}x'
            size = f'{s.size[0]} x {s.size[1]} px'
            info = self.fonts.small.render(fit_text(self.fonts.small, f'{where}   {size}', tw), True,
                                           TEXT_DIM if s.on_map else DONE_COLOR)
            self.screen.blit(info, (tx, row.y + 50))
        self.screen.set_clip(None)

    def draw_detail(self, mouse):
        panel = self.panel_rect()
        box = pygame.Rect(panel.x + PAD, panel.bottom - DETAIL_H, panel.w - 2 * PAD, DETAIL_H - PAD)
        pygame.draw.line(self.screen, DIALOG_LINE, (box.x, box.y - 6), (box.right, box.y - 6))
        y = box.y + 4
        small = self.fonts.small
        self.pending_rows = []
        if self.roof_mode:
            self.draw_roof_detail(box, mouse)
            return
        if self.edit_light:
            self.draw_light_detail(box, mouse)
            return
        if self.unsaved():
            # Light changes waiting: a line and the button at the foot of the box
            self.save_lights_button.rect.bottomleft = (box.x, box.bottom)
            self.save_lights_button.draw(self.screen, small, mouse)
            note = small.render(f'{self.unsaved()} changes to the map', True, DONE_COLOR)
            self.screen.blit(note, note.get_rect(midleft=(self.save_lights_button.rect.right + 10,
                                                          self.save_lights_button.rect.centery)))
            box = pygame.Rect(box.x, box.y, box.w, box.h - 44)
        p = self.chosen
        if not p:
            head = self.fonts.font.render(f'{len(self.placements)} placements waiting', True, TEXT)
            self.screen.blit(head, (box.x, y))
            y += 28
            if not self.placements:
                for line in wrap_text(small, 'Pick a sprite above, then click on the map. '
                                             'Everything goes to placements.json for Claude.', box.w, 3):
                    self.screen.blit(small.render(line, True, TEXT_DIM), (box.x, y))
                    y += 20
            for q in self.placements:
                if y > box.bottom - 22:
                    more = small.render(f'... and {len(self.placements) - len(self.pending_rows)} more', True, TEXT_DIM)
                    self.screen.blit(more, (box.x, y))
                    break
                row = pygame.Rect(box.x, y, box.w, 21)
                if row.collidepoint(mouse):
                    pygame.draw.rect(self.screen, CARD_HOVER, row, border_radius=4)
                line = f'{q.id}  {q.sprite.stem}  {q.x:g}, {q.y:g}' + (f'  x{q.scale:g}' if q.scale != 1 else '')
                if q.note:
                    line += f'  - {q.note}'
                self.screen.blit(small.render(fit_text(small, line, box.w - 8), True, TEXT), (box.x + 4, y + 1))
                self.pending_rows.append((row, q))
                y += 23
            return

        s = p.sprite
        head = self.fonts.font.render(f'Placement {p.id}: {s.stem}', True, TEXT)
        self.screen.blit(head, (box.x, y))
        y += 26
        w, h = p.size
        lines = [
            (s.description, TEXT_DIM),
            (f'Object point {p.x:g}, {p.y:g}   tile {int(p.x // TILE)}, {int(p.y // TILE)}'
             + ('' if p.on_grid else '   off the grid'), TEXT),
            (f'Scale {p.scale:g}   drawn {w:.0f} x {h:.0f} px   ({s.layer} layer)', TEXT),
        ]
        if s.layer == 'Houses':
            bl, bt, br, bb = p.box_px
            lines.append((f'Collision {br - bl:.0f} x {bb - bt:.0f} px'
                          + ('   set by hand' if p.collision_box else '   from the catalog'),
                          DONE_COLOR if p.collision_box else TEXT))
        if s.layer == 'Houses' and not s.tiled:
            lines.append(('No Tiled properties in the catalog yet', ERROR_COLOR))
        for text, colour in lines:
            self.screen.blit(small.render(fit_text(small, text, box.w), True, colour), (box.x, y))
            y += 20
        y += 6
        self.note_field.rect = pygame.Rect(box.x, y, box.w, 36)
        self.note_field.draw(self.screen, small, mouse)
        y += 46
        self.delete_button.rect.topleft = (box.x, y)
        self.goto_button.rect.topleft = (self.delete_button.rect.right + 8, y)
        self.reset_box_button.rect.topleft = (self.goto_button.rect.right + 8, y)
        self.reset_box_button.enabled = bool(p.collision_box)
        self.delete_button.draw(self.screen, small, mouse)
        self.goto_button.draw(self.screen, small, mouse)
        if s.layer == 'Houses':
            self.reset_box_button.draw(self.screen, small, mouse)
        y += 44
        tips = ('Drag it on the map, its collision box by the white handles. '
                '[ ] or Ctrl+wheel scale, arrows nudge, D another one.')
        for line in wrap_text(small, tips, box.w, 3):
            self.screen.blit(small.render(line, True, TEXT_DIM), (box.x, y))
            y += 19

    def draw_light_detail(self, box, mouse):
        light, small = self.edit_light, self.fonts.small
        shaped = isinstance(light, BuildingLight)
        y = box.y + 4
        head = self.fonts.font.render(f'Window light {light.obj_id}' + (f' ({light.building_name})' if shaped else ''),
                                      True, TEXT)
        self.screen.blit(head, (box.x, y))
        y += 26
        x, yy, w, h = geometry(light)
        house = self.scene.house_at(x + w / 2, yy + h / 2)
        owner = (house.props.get('Display_name') or house.name) if house else None
        lines = [
            (f'At {x:g}, {yy:g}   {w:g} x {h:g} px' + ('   (a shaped window: it only moves)' if shaped else ''), TEXT),
            (f'On {owner}' if owner else 'On no building: the game hands it to the nearest one below',
             TEXT if owner else ERROR_COLOR),
            ('Changed, not saved yet' if self.edits.is_changed(light) else 'As on the map',
             DONE_COLOR if self.edits.is_changed(light) else TEXT_DIM),
        ]
        for text, colour in lines:
            self.screen.blit(small.render(fit_text(small, text, box.w), True, colour), (box.x, y))
            y += 20
        y += 8
        self.remove_light_button.rect.topleft = (box.x, y)
        self.reset_light_button.rect.topleft = (self.remove_light_button.rect.right + 8, y)
        self.done_light_button.rect.topleft = (self.reset_light_button.rect.right + 8, y)
        self.reset_light_button.enabled = self.edits.is_changed(light)
        for button in (self.remove_light_button, self.reset_light_button, self.done_light_button):
            button.draw(self.screen, small, mouse)
        y += 44
        self.save_lights_button.rect.topleft = (box.x, y)
        self.save_lights_button.enabled = bool(self.unsaved())
        self.save_lights_button.draw(self.screen, small, mouse)
        count = small.render(f'{self.unsaved()} changes to the map', True, DONE_COLOR if self.unsaved() else TEXT_DIM)
        self.screen.blit(count, count.get_rect(midleft=(self.save_lights_button.rect.right + 10,
                                                        self.save_lights_button.rect.centery)))
        self.save_lights_button.enabled = True
        y += 44
        tips = ('Drag it' + ('' if shaped else ', or its edges and corners by the white handles')
                + '. Arrows nudge it a pixel' + ('' if shaped else ', Shift+arrows make it wider or taller')
                + '. Closing asks whether to save the changes into the map.')
        for line in wrap_text(small, tips, box.w, 4):
            self.screen.blit(small.render(line, True, TEXT_DIM), (box.x, y))
            y += 19

    def _loading_screen(self):
        self.screen.fill(BG)
        text = self.fonts.title.render('Loading the map ...', True, TEXT)
        self.screen.blit(text, text.get_rect(center=self.screen.get_rect().center))
        pygame.display.flip()
        pygame.event.pump()


def main():
    PlacingHelper().run()


if __name__ == '__main__':
    main()
