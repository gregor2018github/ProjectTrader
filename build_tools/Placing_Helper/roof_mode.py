"""The Placing Helper's roof mode (O): the map's roofs and their holes, edited point by point.

Mixed into PlacingHelper. Every roof is shown filled (its holes cut out of
it) and outlined, a hole in another colour. A click picks one; then its
points can be dragged, a click on an edge puts a new point there, a
right-click on a point (or Delete over it) takes it away, a drag inside it
moves it whole, arrows nudge it. P draws a new roof, H a new hole: click its
points, then click the first one again or press Enter. A new roof is named
after the building painted under it, a new hole after the roof it lies in.
A point dropped near another ring's point snaps onto it (Alt: not), so a hole
can share its roof's edge. Ctrl+Z / Ctrl+Y undo and redo. The changes go
into Map1.tmx with "Save to map", or when closing, which asks first.
"""

import math

import pygame

from roof_edits import MIN_POINTS, RoofEdits, Ring, nearest_on_segment
from theme import DONE_COLOR, ERROR_COLOR, TEXT, TEXT_DIM
from widgets import Button, fit_text, wrap_text

ROOF_FILL = (60, 200, 255, 90)
ROOF_LINE = (60, 200, 255)
HOLE_LINE = (255, 150, 40)
SELECTED_LINE = (255, 255, 255)
VERTEX_COLOUR = (255, 255, 255)
VERTEX_HOVER = (255, 225, 80)
VERTEX_GRAB_PX = 8       # screen px from a point that grab it
EDGE_GRAB_PX = 6         # screen px from an edge where a click puts a new point
MAGNET_PX = 7            # screen px within which a point snaps onto another ring's point
VERTEX_PX = 7
ROOF_KEYS_HINT = ('Click a roof   drag its points   click an edge: new point   right-click a point: away   '
                  'P new roof   H new hole   Ctrl+Z undo   O done')


class RoofMode:
    def init_roofs(self):
        self.roof_mode = False
        self.roof_edits = RoofEdits([Ring(*r) for r in self.scene.roofs])
        self.roof_sel = None              # the Ring chosen
        self.drawing = None               # {'hole': bool, 'points': [...]} while a new ring is drawn
        self.new_roof_button = Button('New roof  (P)', w=128, h=34)
        self.new_hole_button = Button('New hole  (H)', w=128, h=34)
        self.delete_ring_button = Button('Delete  (Del)', w=118, h=34)
        self.reset_ring_button = Button('Reset  (R)', w=100, h=34)
        self.undo_button = Button('Undo', w=80, h=34)
        self.redo_button = Button('Redo', w=80, h=34)
        self.close_drawing_button = Button('Close it  (Enter)', w=150, h=34)

    # ----- switching

    def set_roof_mode(self, on):
        self.roof_mode = on
        self.drawing = None
        self.roof_sel = None
        if on:
            self.ghost = None
            self.choose(None)
            self.edit_light = None
            self.status = 'Roofs: click one to edit it, P draws a new roof, H a hole, O when done'
        else:
            self.status = f'Roofs: {self.roof_edits.count} changes to save' if self.roof_edits.count else 'Roofs closed'

    def select_ring(self, ring):
        self.roof_sel = ring
        if ring:
            self.status = (f'{ring.kind.title()} of {self.building_label(ring.name)}: drag its points, click an edge '
                           'for a new one, right-click a point to take it away, drag inside to move it')

    def building_label(self, name):
        thing = next((t for t in self.scene.things if t.layer == 'Houses' and t.name == name), None)
        shown = thing.props.get('Display_name') if thing else None
        return f'{shown} ({name})' if shown and shown != name else name

    # ----- geometry on screen

    def to_screen(self, point):
        area = self.map_area()
        return area.x + (point[0] - self.cam_x) * self.zoom, area.y + (point[1] - self.cam_y) * self.zoom

    def vertex_at(self, pos, ring=None):
        """The index of the chosen ring's point under the pointer, or None."""
        ring = ring or self.roof_sel
        if not ring:
            return None
        best, index = VERTEX_GRAB_PX, None
        for i, point in enumerate(ring.points):
            sx, sy = self.to_screen(point)
            d = math.hypot(sx - pos[0], sy - pos[1])
            if d <= best:
                best, index = d, i
        return index

    def edge_at(self, pos):
        """(index for a new point, world point) on the chosen ring's edge under the pointer, or None."""
        ring = self.roof_sel
        if not ring:
            return None
        best, found = EDGE_GRAB_PX, None
        pts = [self.to_screen(p) for p in ring.points]
        for i, a in enumerate(pts):
            b = pts[(i + 1) % len(pts)]
            q, d = nearest_on_segment(a, b, pos)
            if d <= best:
                best, found = d, (i + 1, q)
        if not found:
            return None
        index, (qx, qy) = found
        return index, self.to_world((qx, qy))

    def magnet(self, wx, wy, skip=None):
        """A world point for a ring's point: onto another ring's point near it (not with Alt), else whole pixels."""
        if not pygame.key.get_mods() & pygame.KMOD_ALT:
            reach = MAGNET_PX / self.zoom
            best, snap = reach, None
            for ring in self.roof_edits.rings:
                left, top, right, bottom = ring.box()
                if not (left - reach <= wx <= right + reach and top - reach <= wy <= bottom + reach):
                    continue
                for i, (px, py) in enumerate(ring.points):
                    if skip == (ring, i):
                        continue
                    d = math.hypot(px - wx, py - wy)
                    if d <= best:
                        best, snap = d, (px, py)
            if self.drawing:
                for px, py in self.drawing['points'][1:]:    # the first point closes the ring instead
                    if math.hypot(px - wx, py - wy) <= best:
                        best, snap = math.hypot(px - wx, py - wy), (px, py)
            if snap:
                return snap
        return float(round(wx)), float(round(wy))

    # ----- changing

    def undo_roofs(self, redo=False):
        done = self.roof_edits.redo() if redo else self.roof_edits.undo()
        if self.roof_sel not in self.roof_edits.rings:
            self.roof_sel = None
        self.status = ('Redone' if redo else 'Undone') if done else ('Nothing to redo' if redo else 'Nothing to undo')

    def start_drawing(self, hole):
        self.drawing = {'hole': hole, 'points': []}
        self.roof_sel = None
        self.status = (f'New {"hole" if hole else "roof"}: click its points, then the first one again '
                       '(or Enter); Backspace takes the last back, Esc stops')

    def finish_drawing(self):
        points = self.drawing['points']
        hole = self.drawing['hole']
        if len(points) < MIN_POINTS:
            self.status = f'A {"hole" if hole else "roof"} needs at least {MIN_POINTS} points'
            return
        cx = sum(p[0] for p in points) / len(points)
        cy = sum(p[1] for p in points) / len(points)
        name = None
        if hole:
            roof = self.roof_edits.roof_around(cx, cy) or next(
                (r for p in points for r in [self.roof_edits.roof_around(*p)] if r), None)
            name = roof.name if roof else None
            if not name:
                self.status = 'A hole goes inside a roof: this one lies in none'
                return
        else:
            house = self.scene.house_at(cx, cy) or next(
                (h for p in points for h in [self.scene.house_at(*p)] if h), None)
            name = house.name if house else None
            if not name:
                self.status = 'No building is painted under this roof: draw it over one'
                return
        self.roof_edits.checkpoint()
        ring = self.roof_edits.add(name, hole, points)
        self.drawing = None
        self.select_ring(ring)
        self.status = f'New {ring.kind} of {self.building_label(name)}, {len(points)} points'

    def delete_at_or_ring(self, pos):
        """Delete the chosen ring's point under the pointer, or else the whole ring."""
        ring = self.roof_sel
        index = self.vertex_at(pos)
        if index is not None:
            self.delete_point(ring, index)
            return
        self.roof_edits.checkpoint()
        self.roof_edits.remove(ring)
        self.roof_sel = None
        self.status = f'{ring.kind.title()} of {self.building_label(ring.name)} deleted (Ctrl+Z brings it back)'

    def delete_point(self, ring, index):
        self.roof_edits.checkpoint()
        if self.roof_edits.remove_point(ring, index):
            self.status = f'Point taken away: {len(ring.points)} left'
        else:
            self.roof_edits.drop_unchanged_checkpoint()
            self.status = f'A ring keeps at least {MIN_POINTS} points (Delete away from its points deletes it whole)'

    def reset_ring(self, ring):
        self.roof_edits.checkpoint()
        if self.roof_edits.reset(ring):
            self.status = f'{ring.kind.title()} back as on the map'
        else:
            self.roof_edits.drop_unchanged_checkpoint()

    # ----- input

    def roof_key(self, event):
        """A key in roof mode; True if it was the roof mode's."""
        k, mods = event.key, event.mod
        ctrl, shift = mods & pygame.KMOD_CTRL, mods & pygame.KMOD_SHIFT
        if ctrl and k == pygame.K_z:
            self.undo_roofs(redo=bool(shift))
            return True
        if ctrl and k == pygame.K_y:
            self.undo_roofs(redo=True)
            return True
        if ctrl:
            return False
        if self.drawing:
            if k in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.finish_drawing()
            elif k == pygame.K_BACKSPACE:
                if self.drawing['points']:
                    self.drawing['points'].pop()
            elif k == pygame.K_ESCAPE:
                self.drawing = None
                self.status = 'Drawing stopped'
            else:
                return k in (pygame.K_p, pygame.K_h, pygame.K_DELETE)
            return True
        ring = self.roof_sel
        if k == pygame.K_p:
            self.start_drawing(False)
        elif k == pygame.K_h:
            self.start_drawing(True)
        elif k in (pygame.K_DELETE, pygame.K_BACKSPACE) and ring:
            self.delete_at_or_ring(pygame.mouse.get_pos())
        elif k == pygame.K_r and ring:
            self.reset_ring(ring)
        elif k == pygame.K_ESCAPE:
            if ring:
                self.roof_sel = None
            else:
                self.set_roof_mode(False)
        elif k in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN) and ring:
            step = 8 if shift else 1
            dx = ((k == pygame.K_RIGHT) - (k == pygame.K_LEFT)) * step
            dy = ((k == pygame.K_DOWN) - (k == pygame.K_UP)) * step
            self.roof_edits.checkpoint()
            ring.points = [(x + dx, y + dy) for x, y in ring.points]
        elif k in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_n, pygame.K_d):
            pass                              # the placements' keys do nothing here
        else:
            return False
        return True

    def roof_mouse_down(self, pos):
        """A left press on the map in roof mode."""
        world = self.to_world(pos)
        if self.drawing:
            points = self.drawing['points']
            if len(points) >= MIN_POINTS:
                fx, fy = self.to_screen(points[0])
                if math.hypot(fx - pos[0], fy - pos[1]) <= VERTEX_GRAB_PX:
                    self.finish_drawing()
                    return
            points.append(self.magnet(*world))
            return
        ring = self.roof_sel
        if ring:
            index = self.vertex_at(pos)
            if index is not None:
                self.roof_edits.checkpoint()
                self.drag = ('vertex', ring, index)
                return
            edge = self.edge_at(pos)
            if edge:
                index, (wx, wy) = edge
                self.roof_edits.checkpoint()
                ring.points.insert(index, self.magnet(wx, wy))
                self.drag = ('vertex', ring, index)
                return
        hit = self.roof_edits.ring_at(*world)
        if hit is not None and hit is ring:
            self.roof_edits.checkpoint()
            self.drag = ('ring', ring, world, list(ring.points))
        elif hit is not None:
            self.select_ring(hit)
        else:
            self.roof_sel = None
            self.drag = ('maybe', pos, (self.cam_x, self.cam_y), 1)

    def roof_mouse_move(self, pos):
        kind = self.drag[0]
        wx, wy = self.to_world(pos)
        if kind == 'vertex':
            _, ring, index = self.drag
            ring.points[index] = self.magnet(wx, wy, skip=(ring, index))
        elif kind == 'ring':
            _, ring, (sx, sy), start = self.drag
            dx, dy = round(wx - sx), round(wy - sy)
            ring.points = [(x + dx, y + dy) for x, y in start]

    def roof_right_click(self, pos):
        """A right-click without a drag: takes the chosen ring's point under the pointer away."""
        if self.drawing:
            if self.drawing['points']:
                self.drawing['points'].pop()
            return
        index = self.vertex_at(pos)
        if index is not None:
            self.delete_point(self.roof_sel, index)

    def roof_cursor(self, mouse):
        if self.drag and self.drag[0] in ('vertex', 'ring'):
            return pygame.SYSTEM_CURSOR_SIZEALL
        if not self.map_area().collidepoint(mouse):
            return pygame.SYSTEM_CURSOR_ARROW
        if self.drawing:
            return pygame.SYSTEM_CURSOR_CROSSHAIR
        if self.roof_sel:
            if self.vertex_at(mouse) is not None:
                return pygame.SYSTEM_CURSOR_HAND
            if self.edge_at(mouse):
                return pygame.SYSTEM_CURSOR_CROSSHAIR
            if self.roof_edits.ring_at(*self.to_world(mouse)) is self.roof_sel:
                return pygame.SYSTEM_CURSOR_SIZEALL
        return pygame.SYSTEM_CURSOR_ARROW

    def roof_panel_click(self, pos):
        """A click on the roof mode's panel buttons; True if it hit one."""
        if self.new_roof_button.hit(pos):
            self.start_drawing(False)
        elif self.new_hole_button.hit(pos):
            self.start_drawing(True)
        elif self.undo_button.hit(pos):
            self.undo_roofs()
        elif self.redo_button.hit(pos):
            self.undo_roofs(redo=True)
        elif self.drawing and self.close_drawing_button.hit(pos):
            self.finish_drawing()
        elif self.roof_sel and not self.drawing and self.delete_ring_button.hit(pos):
            ring = self.roof_sel
            self.roof_edits.checkpoint()
            self.roof_edits.remove(ring)
            self.roof_sel = None
            self.status = f'{ring.kind.title()} deleted (Ctrl+Z brings it back)'
        elif self.roof_sel and not self.drawing and self.reset_ring_button.hit(pos):
            self.reset_ring(self.roof_sel)
        elif self.save_lights_button.hit(pos):
            self.save_map()
        else:
            return False
        return True

    # ----- drawing

    def draw_roofs(self, area, mouse):
        """Every roof in view filled less its holes, outlined; the chosen one with its points."""
        z = self.zoom
        view = (self.cam_x, self.cam_y, self.cam_x + area.w / z, self.cam_y + area.h / z)
        hover = None
        if area.collidepoint(mouse) and not self.drag and not self.drawing:
            hover = self.roof_edits.ring_at(*self.to_world(mouse))
        self.screen.set_clip(area)
        for name, rings in self.roof_edits.by_name().items():
            boxes = [r.box() for r in rings]
            left, top = min(b[0] for b in boxes), min(b[1] for b in boxes)
            right, bottom = max(b[2] for b in boxes), max(b[3] for b in boxes)
            if right < view[0] or left > view[2] or bottom < view[1] or top > view[3]:
                continue
            (sl, st), (sr, sb) = self.to_screen((left, top)), self.to_screen((right, bottom))
            rect = pygame.Rect(math.floor(sl), math.floor(st), math.ceil(sr - sl) + 2, math.ceil(sb - st) + 2).clip(area)
            if rect.w <= 0 or rect.h <= 0:
                continue
            fill = pygame.Surface(rect.size, pygame.SRCALPHA)
            shapes = [(r, [(x - rect.x, y - rect.y) for x, y in map(self.to_screen, r.points)]) for r in rings]
            for ring, pts in shapes:
                if not ring.hole:
                    pygame.draw.polygon(fill, ROOF_FILL, pts)
            for ring, pts in shapes:
                if ring.hole:
                    pygame.draw.polygon(fill, (0, 0, 0, 0), pts)
            self.screen.blit(fill, rect.topleft)
            for ring, pts in shapes:
                if ring is self.roof_sel:
                    continue
                screen_pts = [(x + rect.x, y + rect.y) for x, y in pts]
                pygame.draw.lines(self.screen, HOLE_LINE if ring.hole else ROOF_LINE, True, screen_pts,
                                  2 if ring is hover else 1)
        ring = self.roof_sel
        if ring:
            pts = [self.to_screen(p) for p in ring.points]
            pygame.draw.lines(self.screen, HOLE_LINE if ring.hole else SELECTED_LINE, True, pts, 2)
            hot = self.vertex_at(mouse) if not self.drag else (self.drag[2] if self.drag[0] == 'vertex' else None)
            for i, (x, y) in enumerate(pts):
                handle = pygame.Rect(0, 0, VERTEX_PX, VERTEX_PX)
                handle.center = (round(x), round(y))
                pygame.draw.rect(self.screen, VERTEX_HOVER if i == hot else VERTEX_COLOUR, handle)
                pygame.draw.rect(self.screen, (0, 0, 0), handle, 1)
            if hot is None and not self.drag and area.collidepoint(mouse):
                edge = self.edge_at(mouse)
                if edge:
                    pygame.draw.circle(self.screen, VERTEX_HOVER, [round(v) for v in self.to_screen(edge[1])], 4)
        if self.drawing:
            colour = HOLE_LINE if self.drawing['hole'] else ROOF_LINE
            pts = [self.to_screen(p) for p in self.drawing['points']]
            if area.collidepoint(mouse):
                pts_to_mouse = pts + [self.to_screen(self.magnet(*self.to_world(mouse)))]
            else:
                pts_to_mouse = pts
            if len(pts_to_mouse) >= 2:
                pygame.draw.lines(self.screen, colour, False, pts_to_mouse, 2)
            for i, (x, y) in enumerate(pts):
                size = VERTEX_PX + (4 if i == 0 else 0)
                handle = pygame.Rect(0, 0, size, size)
                handle.center = (round(x), round(y))
                pygame.draw.rect(self.screen, VERTEX_HOVER if i == 0 else VERTEX_COLOUR, handle)
                pygame.draw.rect(self.screen, (0, 0, 0), handle, 1)
        self.screen.set_clip(None)

    def draw_roof_detail(self, box, mouse):
        small, edits = self.fonts.small, self.roof_edits
        y = box.y + 4
        roofs = sum(1 for r in edits.rings if not r.hole)
        head = self.fonts.font.render('Roofs', True, TEXT)
        self.screen.blit(head, (box.x, y))
        count = small.render(f'{roofs} roofs, {len(edits.rings) - roofs} holes'.replace(' 1 holes', ' 1 hole'), True, TEXT_DIM)
        self.screen.blit(count, count.get_rect(midright=(box.right, y + head.get_height() // 2)))
        y += 28
        ring = self.roof_sel
        if self.drawing:
            kind = 'hole' if self.drawing['hole'] else 'roof'
            lines = [(f'Drawing a new {kind}: {len(self.drawing["points"])} points', TEXT),
                     ('Click its points, then the first one again or Enter. Backspace or a right-click '
                      'takes the last back, Esc stops.', TEXT_DIM)]
        elif ring:
            w = ring.box()[2] - ring.box()[0]
            h = ring.box()[3] - ring.box()[1]
            lines = [(f'{ring.kind.title()} of {self.building_label(ring.name)}', TEXT),
                     (f'{"new" if ring.obj_id is None else f"id {ring.obj_id}"}   {len(ring.points)} points   '
                      f'{w:.0f} x {h:.0f} px', TEXT),
                     ('Changed, not saved yet' if edits.is_changed(ring) else 'As on the map',
                      DONE_COLOR if edits.is_changed(ring) else TEXT_DIM)]
        else:
            lines = [('Click a roof (filled) or a hole (orange outline) to edit it.', TEXT_DIM),
                     ('Rain splashes only inside a roof, less its holes, and where its building is painted.',
                      TEXT_DIM)]
        for text, colour in lines:
            for part in wrap_text(small, text, box.w, 2):
                self.screen.blit(small.render(part, True, colour), (box.x, y))
                y += 19
        y += 6
        if self.drawing:
            row = [self.close_drawing_button]
        elif ring:
            row = [self.delete_ring_button, self.reset_ring_button]
            self.reset_ring_button.enabled = ring.obj_id is not None and edits.is_changed(ring)
        else:
            row = []
        x = box.x
        for button in row:
            button.rect.topleft = (x, y)
            button.draw(self.screen, small, mouse)
            x = button.rect.right + 8
        if row:
            y += 42
        x = box.x
        for button in (self.new_roof_button, self.new_hole_button):
            button.rect.topleft = (x, y)
            button.draw(self.screen, small, mouse)
            x = button.rect.right + 8
        y += 42
        self.undo_button.rect.topleft = (box.x, y)
        self.redo_button.rect.topleft = (self.undo_button.rect.right + 8, y)
        self.undo_button.enabled = bool(edits._undo)
        self.redo_button.enabled = bool(edits._redo)
        self.save_lights_button.rect.topleft = (self.redo_button.rect.right + 8, y)
        self.save_lights_button.enabled = bool(self.unsaved())
        for button in (self.undo_button, self.redo_button, self.save_lights_button):
            button.draw(self.screen, small, mouse)
        self.save_lights_button.enabled = True
        y += 40
        changes = self.unsaved()
        text = f'{changes} change{"s" if changes != 1 else ""} to save (roofs {edits.count}, lights {self.edits.count})' if changes else 'Nothing to save'
        self.screen.blit(small.render(fit_text(small, text, box.w), True, DONE_COLOR if changes else TEXT_DIM),
                         (box.x, y))
        y += 22
        if y < box.bottom - 18 and not self.drawing:
            tip = 'Points snap onto points near them (Alt: not).'
            for part in wrap_text(small, tip, box.w, 2):
                if y > box.bottom - 18:
                    break
                self.screen.blit(small.render(part, True, TEXT_DIM), (box.x, y))
                y += 19
