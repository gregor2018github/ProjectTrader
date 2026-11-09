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
    F                  put a figure down at the pointer for scale (again on it: take it away)
    C                  collision boxes of what is on the map
    G                  snap to the tile grid on / off
    Tab, U             next tab, only sprites not on the map on / off
    Ctrl+S             save now (it saves by itself anyway)
    Escape             drop what is on the mouse, then the choice, then close

The code: map_scene.py (the map, its chunks and objects, the sprites),
placements.py (a placement and the file), this file (the window).
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
from map_scene import TABS, TILE, Scene, draw_box  # noqa: E402
from placements import Placement, load, save  # noqa: E402
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
FIGURE_GRAB_PX = 18              # world px around a figure's feet that take it away
#: Which tabs show only the sprites not on the map at first; trees are planted again and again
UNPLACED_ONLY = {'Buildings': True, 'Decoration': True, 'Trees': False}
KEYS_HINT = 'Wheel zoom   [ ] scale   G grid   C collision   F figure   D another   Enter note   Del delete'


class PlacingHelper:
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
        self.drag = None                  # ('pan', start, cam) or ('move', placement, grab dx, dy) or ('maybe', start, cam)
        self.dirty_at = None
        self.note_field = TextField(placeholder='Note: what it is for, what it needs  (Enter)')
        self.delete_button = Button('Delete  (Del)', w=150, h=34)
        self.goto_button = Button('Go to it', w=110, h=34)
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
        top = PAD + 40 + CHIP_HEIGHT * 2 + 24
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
                if self.handle(event) == 'quit':
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

    def key(self, event):
        if self.note_field.focused:
            if self.note_field.key(event) == 'done':
                self.finish_note()
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
        if self.ghost:
            self.put_down(pos, keep=bool(pygame.key.get_mods() & pygame.KMOD_SHIFT))
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
        elif self.drag[0] == 'move':
            _, p, gx, gy = self.drag
            wx, wy = self.to_world(event.pos)
            x, y = self.snapped(wx - gx, wy - gy)
            if (x, y) != (p.x, p.y):
                p.x, p.y = x, y
                self.mark_dirty()

    def mouse_up(self, event):
        if not self.drag:
            return
        if self.drag[0] == 'maybe':
            # A click without a drag: on empty ground it lets go of the choice,
            # with the right button it also drops what is on the mouse
            if self.drag[3] == 3 and self.ghost:
                self.ghost = None
            elif self.drag[3] in (1, 3):
                self.choose(None)
        self.drag = None

    def panel_click(self, pos):
        for rect, tab in self.tab_chips:
            if rect.collidepoint(pos):
                self.tab, self.list_scroll = tab, 0
                return
        for rect, _ in self.toggle_chips:
            if rect.collidepoint(pos):
                self.unplaced_only[self.tab] = not self.unplaced_only[self.tab]
                self.list_scroll = 0
                return
        for rect, sprite in self.rows:
            if rect.collidepoint(pos):
                self.ghost = sprite
                self.ghost_scale = 1.0
                self.choose(None)
                self.status = f'{sprite.stem} on the mouse: click on the map to put it down (Shift+click for another)'
                return
        if self.chosen:
            if self.note_field.rect.collidepoint(pos):
                self.note_field.focus(True)
            elif self.delete_button.hit(pos):
                self.delete(self.chosen)
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
        ox, oy = self.scene.draw(self.screen, area, self.cam_x, self.cam_y, self.zoom, extra, self.show_collision)

        self.screen.set_clip(area)
        for p in self.placements:
            box = p.collision
            if box:
                draw_box(self.screen, box, ox, oy, self.zoom, PLACEMENT_COLLISION)
            draw_box(self.screen, p.rect, ox, oy, self.zoom,
                     CHOSEN_LINE if p is self.chosen else PLACEMENT_LINE, 2 if p is self.chosen else 1)
            label = self.fonts.small.render(f'{p.id} {p.sprite.stem}', True, TEXT)
            lx, ly = ox + round(p.x * self.zoom), oy + round(p.y * self.zoom) + 2
            pygame.draw.rect(self.screen, (0, 0, 0), (lx, ly, label.get_width() + 6, label.get_height()))
            self.screen.blit(label, (lx + 3, ly))
        if ghost_point:
            box = self.ghost.collision(ghost_point[0], ghost_point[1], self.ghost_scale)
            if box:
                draw_box(self.screen, box, ox, oy, self.zoom, PLACEMENT_COLLISION)
        self.screen.set_clip(None)

        self.draw_overlay(area, mouse, ghost_point)
        self.draw_footer(area)
        self.draw_panel(mouse)
        self.toast.draw(self.screen, self.fonts)

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
        hint = self.fonts.small.render(fit_text(self.fonts.small, KEYS_HINT, area.w // 2 - 20), True, TEXT_DIM)
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
        on = self.unplaced_only[self.tab]
        self.toggle_chips, _ = draw_chips(self.screen, self.fonts.font, ['only'],
                                          lambda _: 'Only those not on the map  (U)', 'only' if on else None,
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
        self.goto_button.rect.topleft = (self.delete_button.rect.right + 10, y)
        self.delete_button.draw(self.screen, small, mouse)
        self.goto_button.draw(self.screen, small, mouse)
        y += 44
        tips = 'Drag it on the map. [ ] or Ctrl+wheel scale, arrows nudge, D another one.'
        for line in wrap_text(small, tips, box.w, 2):
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
