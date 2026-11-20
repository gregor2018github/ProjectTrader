"""The Placing Helper's fence mode (W): draw where fences and walls are to go, for Claude to design them.

Mixed into PlacingHelper; the fences are fence_plans.py's, saved to
fence_plans.json after every change. Each fence has a material (wood, stone,
metal: 1, 2, 3) and a description of how it is to look, typed into the
panel's field, which Claude reads when designing it.

Drawing: a click puts down the first post, on the middle of a tile; every
further click ends a straight run there, across or down (the longer way
wins), and goes on from it, so corners are just more clicks. A click on the
last post, Enter or a right-click ends the line; Backspace takes its last
run back, Escape stops. A line started with no fence chosen starts a new
one (N does too). A click on another fence (not while drawing) chooses it.

Gates: G switches to the gate tool; a click on a run puts a gate of the
width chosen ([ and ], 1 to 4 tiles, post to post) in it, centred on the
click, a click on a gate takes it out again. Right-click a gate or a run
(not while drawing) to delete it. Delete removes the chosen fence,
Ctrl+Z / Ctrl+Y undo and redo.
"""

import math

import pygame
from theme import DONE_COLOR, ERROR_COLOR, TEXT, TEXT_DIM
from widgets import Button, TextField, draw_chips, fit_text, wrap_text

from fence_plans import (
    DEFAULT_GATE_WIDTH,
    DEFAULT_MATERIAL,
    GATE_WIDTHS,
    HORIZONTAL,
    MATERIAL_TITLES,
    MATERIALS,
    TILE,
    FencePlans,
    post_foot,
    run_between,
    straightened,
)

MATERIAL_COLOURS = {'wood': (176, 112, 52), 'stone': (196, 190, 176), 'metal': (70, 74, 92)}
GATE_COLOUR = (255, 214, 60)
CHOSEN_GLOW = (255, 255, 255)
PREVIEW_COLOUR = (120, 230, 255)
FENCE_KEYS_HINT = ('Click posts: runs across or down   right-click / Enter: end   G gates  [ ] width   '
                   '1 2 3 material   N new   Del delete   Ctrl+Z undo   W done')
HIT_PX = 10              # screen px from a run that a click or right-click still finds it


class FenceMode:
    def init_fences(self, path):
        self.fence_mode = False
        self.fence_plans = FencePlans(path)
        self.fence_sel = None             # the Fence chosen
        self.fence_line = []              # post tiles of the line being drawn
        self.fence_tool = 'draw'          # or 'gate'
        self.gate_width = DEFAULT_GATE_WIDTH
        self.fence_material = DEFAULT_MATERIAL   # for a new fence
        self.fence_desc = TextField(placeholder='How it looks: e.g. low wattle of hazel rods between oak posts')
        self.fence_chips = []
        self.fence_material_chips = []
        self.fence_tool_chips = []
        self.gate_width_chips = []
        self.fence_rows = []
        self.new_fence_button = Button('New  (N)', w=92, h=32)
        self.delete_fence_button = Button('Delete  (Del)', w=106, h=32)
        self.fence_undo_button = Button('Undo', w=66, h=32)
        self.fence_redo_button = Button('Redo', w=66, h=32)

    # ----- switching and choosing

    def set_fence_mode(self, on):
        self.commit_fence_desc()
        self.fence_mode = on
        self.fence_line = []
        if on:
            if getattr(self, 'roof_mode', False):
                self.set_roof_mode(False)
            self.ghost = None
            self.choose(None)
            self.edit_light = None
            self.status = ('Fences: click on the map to put down posts, a click per corner; '
                           'G for gates; describe each fence in the panel')
        else:
            count = len([f for f in self.fence_plans.fences if f.runs])
            self.status = f'Fences: {count} drawn, in {self.fence_plans.path.name}'

    def choose_fence(self, fence):
        self.commit_fence_desc()
        self.fence_sel = fence
        self.fence_desc.text = fence.description if fence else ''
        if fence:
            self.fence_material = fence.material
            self.status = f'{fence.title}: {fence.length()} tiles, {len(fence.gates)} gates'

    def commit_fence_desc(self):
        """What is typed in the description field goes into the chosen fence."""
        fence = getattr(self, 'fence_sel', None)
        if fence is not None and fence.description != self.fence_desc.text:
            self.fence_plans.checkpoint()
            fence.description = self.fence_desc.text.strip()
            self.fence_plans.save()
        if self.fence_desc.focused:
            self.fence_desc.focus(False)

    def new_fence(self):
        self.commit_fence_desc()
        self.fence_plans.checkpoint()
        fence = self.fence_plans.new_fence(self.fence_material)
        self.fence_line = []
        self.choose_fence(fence)
        self.status = f'{fence.title}: click on the map for its first post, then a click per corner'
        return fence

    def delete_fence(self, fence):
        self.fence_plans.checkpoint()
        self.fence_plans.fences.remove(fence)
        self.fence_plans.save()
        if fence is self.fence_sel:
            self.choose_fence(None)
        self.fence_line = []
        self.status = f'{fence.title} deleted (Ctrl+Z brings it back)'

    def set_fence_material(self, material):
        self.fence_material = material
        fence = self.fence_sel
        if fence and fence.material != material:
            self.fence_plans.checkpoint()
            fence.material = material
            self.fence_plans.save()
            self.status = f'{fence.title}'

    def set_fence_tool(self, tool):
        self.fence_tool = tool
        self.fence_line = []
        self.status = (f'Gates: click on a run to put a gate of {self.gate_width} tiles in it, on a gate to take '
                       'it out; [ ] the width' if tool == 'gate' else 'Drawing: a click per post')

    def set_gate_width(self, width):
        self.gate_width = max(GATE_WIDTHS[0], min(GATE_WIDTHS[-1], width))
        self.status = f'Gates {self.gate_width} tiles wide, post to post'

    def undo_fences(self, redo=False):
        chosen = self.fence_sel.id if self.fence_sel else None
        done = self.fence_plans.redo() if redo else self.fence_plans.undo()
        self.fence_sel = self.fence_plans.find(chosen) if chosen is not None else None
        self.fence_desc.text = self.fence_sel.description if self.fence_sel else ''
        self.fence_line = []
        self.status = ('Redone' if redo else 'Undone') if done else ('Nothing to redo' if redo else 'Nothing to undo')

    # ----- geometry

    def tile_at(self, pos):
        wx, wy = self.to_world(pos)
        return math.floor(wx / TILE), math.floor(wy / TILE)

    def post_screen(self, tile):
        return self.to_screen(post_foot(*tile))

    def fence_hit(self, pos):
        """(fence, run) of the run nearest the pointer within HIT_PX, the chosen fence's first."""
        wx, wy = self.to_world(pos)
        reach = max(HIT_PX / self.zoom, 4)
        best = None
        fences = sorted(self.fence_plans.fences, key=lambda f: f is not self.fence_sel)
        for fence in fences:
            for run in fence.runs:
                (ax, ay), (bx, by) = post_foot(*run.at(0)), post_foot(*run.end)
                px = min(max(wx, min(ax, bx)), max(ax, bx))
                py = min(max(wy, min(ay, by)), max(ay, by))
                d = math.hypot(wx - px, wy - py)
                if d <= reach and (best is None or d < best[0]):
                    best = (d, fence, run)
        return (best[1], best[2]) if best else None

    def line_end(self, pos):
        """Where the line being drawn would end at the pointer: straight on from its last post."""
        tile = self.tile_at(pos)
        return straightened(self.fence_line[-1], tile) if self.fence_line else tile

    # ----- input

    def fence_key(self, event):
        """A key in fence mode; True if it was the mode's."""
        k, mods = event.key, event.mod
        if self.fence_desc.focused:
            if self.fence_desc.key(event) == 'done':
                self.commit_fence_desc()
                self.status = 'Description kept'
            return True
        ctrl = mods & pygame.KMOD_CTRL
        if k == pygame.K_z and ctrl:
            self.undo_fences(redo=bool(mods & pygame.KMOD_SHIFT))
        elif k == pygame.K_y and ctrl:
            self.undo_fences(redo=True)
        elif k == pygame.K_ESCAPE:
            if self.fence_line:
                self.fence_line = []
                self.status = 'Line stopped'
            elif self.fence_tool == 'gate':
                self.set_fence_tool('draw')
            elif self.fence_sel:
                self.choose_fence(None)
            else:
                self.set_fence_mode(False)
        elif k in (pygame.K_RETURN, pygame.K_KP_ENTER):
            if self.fence_line:
                self.finish_fence_line()
            elif self.fence_sel:
                self.fence_desc.focus(True)
        elif k == pygame.K_BACKSPACE and self.fence_line:
            self.undo_line_step()
        elif k == pygame.K_g:
            self.set_fence_tool('draw' if self.fence_tool == 'gate' else 'gate')
        elif k in (pygame.K_LEFTBRACKET, pygame.K_MINUS, pygame.K_KP_MINUS):
            self.set_gate_width(self.gate_width - 1)
        elif k in (pygame.K_RIGHTBRACKET, pygame.K_PLUS, pygame.K_KP_PLUS, pygame.K_EQUALS):
            self.set_gate_width(self.gate_width + 1)
        elif k in (pygame.K_1, pygame.K_2, pygame.K_3):
            self.set_fence_material(MATERIALS[k - pygame.K_1])
        elif k == pygame.K_n:
            self.new_fence()
        elif k == pygame.K_DELETE and self.fence_sel and not self.fence_line:
            self.delete_fence(self.fence_sel)
        else:
            return False
        return True

    def fence_mouse_down(self, pos):
        """A left click on the map in fence mode."""
        if self.fence_desc.focused:
            self.commit_fence_desc()
        tile = self.tile_at(pos)
        if self.fence_tool == 'gate':
            self.gate_click(tile, pos)
            return
        if not self.fence_line:
            hit = self.fence_hit(pos)
            if hit and hit[0] is not self.fence_sel:
                self.choose_fence(hit[0])        # a click on another fence chooses it
                return
            if self.fence_sel is None:
                self.new_fence()
            self.fence_line = [tile]
            self.status = f'{self.fence_sel.title}: first post at tile {tile[0]}, {tile[1]}; click the next corner'
            return
        end = self.line_end(pos)
        if end == self.fence_line[-1]:
            self.finish_fence_line()             # a click on the last post ends the line
            return
        run = run_between(self.fence_line[-1], end)
        self.fence_plans.checkpoint()
        self.fence_sel.add_run(run)
        self.fence_plans.save()
        self.fence_line.append(end)
        self.status = (f'{self.fence_sel.title}: {run.length} tiles {"across" if run.orientation == HORIZONTAL else "down"}'
                       f', {self.fence_sel.length()} in all; next corner, or right-click to end')

    def gate_click(self, tile, pos):
        found = self.fence_plans.gate_at(*tile)
        if found:
            fence, gate = found
            self.fence_plans.checkpoint()
            fence.gates.remove(gate)
            self.fence_plans.save()
            self.choose_fence(fence)
            self.status = f'Gate taken out of {fence.title}'
            return
        hit = self.fence_hit(pos)
        if hit is None:
            self.status = 'Click on a run of a fence to put a gate in it'
            return
        fence = hit[0]
        self.fence_plans.checkpoint()
        result = fence.place_gate(*self.on_run(hit[1], tile), self.gate_width)
        if isinstance(result, str):
            self.fence_plans._undo.pop()
            self.status = result
            return
        self.fence_plans.save()
        self.choose_fence(fence)
        self.status = (f'Gate of {result.width} tiles in {fence.title} at tile {result.x}, {result.y} '
                       '(a click on it takes it out)')

    @staticmethod
    def on_run(run, tile):
        """The tile on the run nearest to `tile` (a click a little off the line still counts)."""
        if run.orientation == HORIZONTAL:
            return min(max(tile[0], run.x), run.x + run.length), run.y
        return run.x, min(max(tile[1], run.y), run.y + run.length)

    def undo_line_step(self):
        """Backspace while drawing: the last run of the line taken back."""
        if len(self.fence_line) <= 1:
            self.fence_line = []
            return
        self.fence_plans.undo()
        self.fence_sel = self.fence_plans.find(self.fence_sel.id) if self.fence_sel else None
        self.fence_line.pop()

    def finish_fence_line(self):
        fence = self.fence_sel
        self.fence_line = []
        if fence:
            self.status = (f'{fence.title}: {fence.length()} tiles. Describe how it looks in the panel, '
                           'G for gates, or click on for another line')

    def fence_right_click(self, pos):
        """A right-click without a drag: ends the line, or deletes the gate or run under the pointer."""
        if self.fence_line:
            self.finish_fence_line()
            return
        tile = self.tile_at(pos)
        found = self.fence_plans.gate_at(*tile)
        if found:
            fence, gate = found
            self.fence_plans.checkpoint()
            fence.gates.remove(gate)
            self.fence_plans.save()
            self.status = f'Gate taken out of {fence.title}'
            return
        hit = self.fence_hit(pos)
        if hit:
            fence, run = hit
            self.fence_plans.checkpoint()
            fence.remove_run(run)
            self.fence_plans.save()
            self.status = f'A run of {run.length} tiles taken out of {fence.title} (Ctrl+Z brings it back)'

    def fence_cursor(self, mouse):
        if not self.map_area().collidepoint(mouse):
            return pygame.SYSTEM_CURSOR_ARROW
        if self.fence_tool == 'gate':
            return pygame.SYSTEM_CURSOR_HAND if self.fence_hit(mouse) else pygame.SYSTEM_CURSOR_NO
        return pygame.SYSTEM_CURSOR_CROSSHAIR

    def fence_panel_click(self, pos):
        """A click on the fence mode's part of the panel; True if it hit something."""
        if self.fence_desc.rect.collidepoint(pos):
            if self.fence_sel is None:
                self.new_fence()
            self.fence_desc.focus(True)
            return True
        self.commit_fence_desc()
        for rect, material in self.fence_material_chips:
            if rect.collidepoint(pos):
                self.set_fence_material(material)
                return True
        for rect, tool in self.fence_tool_chips:
            if rect.collidepoint(pos):
                self.set_fence_tool(tool)
                return True
        for rect, width in self.gate_width_chips:
            if rect.collidepoint(pos):
                self.set_gate_width(width)
                return True
        for rect, fence in self.fence_rows:
            if rect.collidepoint(pos):
                self.choose_fence(fence)
                if fence.runs:
                    posts = fence.posts()
                    xs, ys = [p[0] for p in posts], [p[1] for p in posts]
                    self.centre_on((min(xs) + max(xs) + 1) / 2 * TILE, (min(ys) + max(ys) + 1) / 2 * TILE)
                return True
        if self.new_fence_button.hit(pos):
            self.new_fence()
        elif self.fence_sel and self.delete_fence_button.hit(pos):
            self.delete_fence(self.fence_sel)
        elif self.fence_undo_button.hit(pos):
            self.undo_fences()
        elif self.fence_redo_button.hit(pos):
            self.undo_fences(redo=True)
        else:
            return False
        return True

    # ----- drawing

    def draw_fences(self, area, mouse):
        """Every fence drawn as a line through its posts, its gates gold; faint outside the fence mode."""
        width = max(3, round(TILE * self.zoom * 0.18))
        self.screen.set_clip(area)
        for fence in self.fence_plans.fences:
            chosen = fence is self.fence_sel and self.fence_mode
            colour = MATERIAL_COLOURS.get(fence.material, (200, 200, 200))
            if not self.fence_mode:
                colour = tuple(c // 2 + 60 for c in colour)
            for run in fence.runs:
                a, b = self.post_screen(run.at(0)), self.post_screen(run.end)
                if chosen:
                    pygame.draw.line(self.screen, CHOSEN_GLOW, a, b, width + 4)
                pygame.draw.line(self.screen, (0, 0, 0), a, b, width + 2)
                pygame.draw.line(self.screen, colour, a, b, width)
            for gate in fence.gates:
                self.draw_gate(gate.orientation, (gate.x, gate.y), gate.end, width)
            radius = max(3, width // 2 + 2)
            for post in fence.posts():
                x, y = self.post_screen(post)
                pygame.draw.circle(self.screen, (0, 0, 0), (round(x), round(y)), radius + 1)
                pygame.draw.circle(self.screen, colour, (round(x), round(y)), radius)
            if fence.runs and (self.fence_mode or self.zoom >= 0.5):
                x, y = self.post_screen(fence.origin())
                label = self.fonts.small.render(fence.title, True, TEXT)
                pygame.draw.rect(self.screen, (0, 0, 0), (x + 6, y - 24, label.get_width() + 8, label.get_height() + 2))
                self.screen.blit(label, (x + 10, y - 23))
        if self.fence_mode and area.collidepoint(mouse) and not self.drag:
            self.draw_fence_preview(mouse, width)
        self.screen.set_clip(None)

    def draw_gate(self, orientation, start, end, width, preview=False):
        a, b = self.post_screen(start), self.post_screen(end)
        pygame.draw.line(self.screen, (0, 0, 0), a, b, width + 2)
        pygame.draw.line(self.screen, (255, 255, 255) if preview else GATE_COLOUR, a, b, width)
        # Two leaves meeting in the middle, drawn as short ticks across the gap
        mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        tick = width * 2
        for p in (a, mid, b):
            if orientation == HORIZONTAL:
                pygame.draw.line(self.screen, (0, 0, 0), (p[0], p[1] - tick), (p[0], p[1] + tick), 2)
            else:
                pygame.draw.line(self.screen, (0, 0, 0), (p[0] - tick, p[1]), (p[0] + tick, p[1]), 2)

    def draw_fence_preview(self, mouse, width):
        if self.fence_tool == 'gate':
            hit = self.fence_hit(mouse)
            if hit:
                run = hit[1]
                tx, ty = self.on_run(run, self.tile_at(mouse))
                along = run.along_of(tx, ty)
                start = min(max(0, round(along - self.gate_width / 2)), max(0, run.length - self.gate_width))
                if run.length >= self.gate_width:
                    s = run.at(start)
                    e = run.at(start + self.gate_width)
                    self.draw_gate(run.orientation, s, e, width, preview=True)
            return
        if self.fence_line:
            pts = [self.post_screen(p) for p in self.fence_line]
            end = self.line_end(mouse)
            if len(pts) >= 2:
                pygame.draw.lines(self.screen, PREVIEW_COLOUR, False, pts, 2)
            a, b = pts[-1], self.post_screen(end)
            pygame.draw.line(self.screen, PREVIEW_COLOUR, a, b, width)
            run = run_between(self.fence_line[-1], end)
            if run:
                label = self.fonts.small.render(f'{run.length} tiles', True, TEXT)
                pygame.draw.rect(self.screen, (0, 0, 0), (b[0] + 10, b[1] + 8, label.get_width() + 8,
                                                         label.get_height() + 2))
                self.screen.blit(label, (b[0] + 14, b[1] + 9))
            target = end
        else:
            target = self.tile_at(mouse)
        x, y = self.post_screen(target)
        pygame.draw.circle(self.screen, (0, 0, 0), (round(x), round(y)), max(4, width // 2 + 3))
        pygame.draw.circle(self.screen, PREVIEW_COLOUR, (round(x), round(y)), max(3, width // 2 + 2))

    def draw_fence_detail(self, box, mouse):
        small, font = self.fonts.small, self.fonts.font
        plans = self.fence_plans
        y = box.y + 2
        head = font.render('Fences and walls', True, TEXT)
        self.screen.blit(head, (box.x, y))
        drawn = [f for f in plans.fences if f.runs]
        count = small.render(f'{len(drawn)} drawn, for Claude', True, TEXT_DIM)
        self.screen.blit(count, count.get_rect(midright=(box.right, y + head.get_height() // 2)))
        y += 28
        # The fences, the chosen one lit
        self.fence_rows = []
        for fence in plans.fences[-4:]:
            row = pygame.Rect(box.x, y, box.w, 21)
            if fence is self.fence_sel:
                pygame.draw.rect(self.screen, (70, 70, 90), row, border_radius=4)
            elif row.collidepoint(mouse):
                pygame.draw.rect(self.screen, (50, 50, 64), row, border_radius=4)
            pygame.draw.circle(self.screen, MATERIAL_COLOURS.get(fence.material, TEXT), (row.x + 9, row.centery), 5)
            line = f'{fence.title}   {fence.length()} tiles, {len(fence.gates)} gates'
            if fence.description:
                line += f'  - {fence.description}'
            self.screen.blit(small.render(fit_text(small, line, box.w - 24), True, TEXT), (row.x + 20, row.y + 1))
            self.fence_rows.append((row, fence))
            y += 23
        if len(plans.fences) > 4:
            more = small.render(f'... {len(plans.fences) - 4} more, on the map', True, TEXT_DIM)
            self.screen.blit(more, (box.x, y))
            y += 20
        if not plans.fences:
            for part in wrap_text(small, 'Click on the map to put down a fence\'s first post, then a click per '
                                         'corner. Each fence gets a material and a description.', box.w, 3):
                self.screen.blit(small.render(part, True, TEXT_DIM), (box.x, y))
                y += 19
        y += 4
        # Material, then the description of the chosen (or next) fence
        label = small.render('Material', True, TEXT_DIM)
        self.screen.blit(label, (box.x, y + 6))
        mx = box.x + label.get_width() + 10
        self.fence_material_chips, y2 = draw_chips(self.screen, small, MATERIALS,
                                                   lambda m: f'{MATERIAL_TITLES[m]}  {MATERIALS.index(m) + 1}',
                                                   self.fence_material, mx, y, box.right - mx, mouse)
        y = y2 + 6
        self.fence_desc.rect = pygame.Rect(box.x, y, box.w, 34)
        self.fence_desc.draw(self.screen, small, mouse)
        y += 38
        if self.fence_sel and len(self.fence_desc.text) > 46 and not self.fence_desc.focused:
            for part in wrap_text(small, self.fence_desc.text, box.w, 2):
                self.screen.blit(small.render(part, True, TEXT_DIM), (box.x, y))
                y += 18
            y += 6
        # Tools
        self.fence_tool_chips, _ = draw_chips(self.screen, small, ('draw', 'gate'),
                                              lambda t: {'draw': 'Draw', 'gate': 'Gates  (G)'}[t],
                                              self.fence_tool, box.x, y, 200, mouse)
        gx = self.fence_tool_chips[-1][0].right + 14
        width_label = small.render('Gate', True, TEXT_DIM)
        self.screen.blit(width_label, width_label.get_rect(midleft=(gx, self.fence_tool_chips[0][0].centery)))
        self.gate_width_chips, y = draw_chips(self.screen, small, GATE_WIDTHS, lambda w: f'{w}', self.gate_width,
                                              gx + width_label.get_width() + 8, y, box.right - gx, mouse)
        y += 8
        x = box.x
        self.delete_fence_button.enabled = self.fence_sel is not None
        self.fence_undo_button.enabled = bool(plans._undo)
        self.fence_redo_button.enabled = bool(plans._redo)
        for button in (self.new_fence_button, self.delete_fence_button, self.fence_undo_button,
                       self.fence_redo_button):
            button.rect.topleft = (x, y)
            button.draw(self.screen, small, mouse)
            x = button.rect.right + 6
        self.delete_fence_button.enabled = True
        y += 40
        if self.fence_line:
            tip = 'Drawing: click the next corner; right-click, Enter or a click on the last post ends it.'
            colour = DONE_COLOR
        elif self.fence_tool == 'gate':
            tip = f'Click a run for a gate of {self.gate_width} tiles; click a gate to take it out.'
            colour = DONE_COLOR
        elif self.fence_sel and not self.fence_sel.description:
            tip = 'Say how it should look in the field above: Claude designs it from that.'
            colour = ERROR_COLOR
        else:
            tip = f'Saved as you go to {plans.path.name}. Right-click a run or gate to delete it.'
            colour = TEXT_DIM
        for part in wrap_text(small, tip, box.w, 2):
            if y > box.bottom - 16:
                break
            self.screen.blit(small.render(part, True, colour), (box.x, y))
            y += 18
