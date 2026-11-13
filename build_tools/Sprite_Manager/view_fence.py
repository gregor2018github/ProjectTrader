"""One fence or wall style: its settings, its pieces, the chosen piece on its raster, and all of them laid together.

Left the style: its material (wood, stone, metal), how far apart its posts
stand (or at the ends only), how tall its raster is, its description for the
prompt, and which lengths of piece it wants, horizontal and vertical, offered
in steps of the post spacing so every piece keeps it. In the middle its
pieces, each with its state. Right the chosen piece on its raster, with the
tiles, the run and where the posts stand, the Tiled properties of its object,
and the ways on: "Sketch it" (Enter) opens its sketch screen
(view_fence_design.py), "Answers" (Tab) its answers, and "Assemble" (A) lays
it out of another length of the same style without the model (fences.assemble).
Under it every piece drawn, laid together into a yard as the map would have
them, so the joins and corners can be judged.
"""

import os
import sys

import pygame

import pose_review
from fence_sheets import FOOT_COLOR, POST_COLOR, chosen_reference
from fences import (
    HEIGHTS, HORIZONTAL, MATERIALS, ORIENTATION_TITLES, ORIENTATIONS, TILE, VERTICAL, can_assemble, assemble,
    default_reference, find_styles, lengths_offered, reference_options,
)
from images import fitted
from theme import (
    CARD_BG, CHIP_BG, CHIP_HOVER, CHIP_ON, ERROR_COLOR, PANEL_GAP, STATUS_COLORS, TEXT, TEXT_DIM, THUMB_BG,
)
from view import View
from widgets import Button, Checker, TextField, draw_chips, draw_panel, fit_text

SETTINGS_SHARE = 0.27
PIECES_SHARE = 0.25
ROW_H = 52
ROW_THUMB = (72, 44)
BUTTON_H = 38
BUTTON_GAP = 10
LABEL_GAP = 22
GRASS = (92, 122, 70)
GRASS_LINE = (84, 112, 64)
GRID_LINE = (200, 200, 210)
POSTS_CHOICES = (0, 1, 2, 3, 4)
MAX_ZOOM = 6


def draw_toggles(screen, font, values, labels, chosen, x, y, width, mouse):
    """Chips like widgets.draw_chips, any number of them on at once; returns ([(rect, value)], bottom)."""
    chips = []
    cx, cy = x, y
    for value in values:
        label = labels(value)
        w = font.size(label)[0] + 22
        if cx > x and cx + w > x + width:
            cx, cy = x, cy + 32 + 8
        rect = pygame.Rect(cx, cy, w, 32)
        color = CHIP_ON if value in chosen else CHIP_HOVER if rect.collidepoint(mouse) else CHIP_BG
        pygame.draw.rect(screen, color, rect, border_radius=6)
        text = font.render(label, True, TEXT)
        screen.blit(text, text.get_rect(center=rect.center))
        chips.append((rect, value))
        cx += w + 8
    return chips, cy + 32


def yard(style):
    """Every piece drawn, laid together at the game's scale: the horizontal ones end to end along the top and
    the bottom, the vertical ones down both sides; a surface on grass, or None if nothing is drawn."""
    drawn = {o: [p for p in style.pieces(o) if p.exists()] for o in ORIENTATIONS}
    across = sorted(drawn[HORIZONTAL], key=lambda p: -p.length)
    down = sorted(drawn[VERTICAL], key=lambda p: -p.length)
    if not across and not down:
        return None
    width = sum(p.length for p in across)
    depth = sum(p.length for p in down)
    placed = []                                   # [(piece, first post's foot in tiles)]

    def run(pieces, start, step):
        x, y = start
        for piece in pieces:
            placed.append((piece, (x, y)))
            x, y = x + step[0] * piece.length, y + step[1] * piece.length

    run(across, (0, 0), (1, 0))
    if down:
        run(down, (0, 0), (0, 1))
        if across:
            run(down, (width, 0), (0, 1))
            run(across, (0, depth), (1, 0))
    rise = style.height - 0.5                     # from a run's line up to its raster's top
    margin = 0.5                                  # grass round the yard, in tiles
    sprites = []
    for piece, (x, y) in placed:
        left = x - (0.5 if piece.orientation == HORIZONTAL else 1)
        sprite = piece.sprite()
        if sprite is not None:
            # A raster's top lies `rise` above its run, and the topmost run lies `rise` below the yard's top
            sprites.append((round((left + 1 + margin) * TILE), round((y + margin) * TILE), sprite))
    w = round((width + 2 + 2 * margin) * TILE)
    h = round((rise + depth + 0.5 + 2 * margin) * TILE)
    surface = pygame.Surface((w, h))
    surface.fill(GRASS)
    for gx in range(0, w, TILE):
        pygame.draw.line(surface, GRASS_LINE, (gx, 0), (gx, h))
    for gy in range(0, h, TILE):
        pygame.draw.line(surface, GRASS_LINE, (0, gy), (w, gy))
    # As the game draws buildings: whatever stands lower in the picture in front
    for x, y, sprite in sorted(sprites, key=lambda s: (s[1] + s[2].get_height(), s[0])):
        surface.blit(sprite, (x, y))
    return surface


class FenceView(View):
    def __init__(self, app, styles_view):
        """
        Args:
            styles_view: The view_fences.FencesView to go back to.
        """
        super().__init__(app)
        self.styles_view = styles_view
        self.style = app.npc
        self.chosen = None              # the Piece chosen
        self.rows = []                  # [(rect, Piece)] as last drawn
        self.chips = []                 # [(rect, action, value)] as last drawn
        self.thumbs = {}
        self.yard = None
        self.checker = Checker()
        self.field = TextField(self.style.description, placeholder='what it looks like, for the prompt')
        self.sketch_button = Button('Sketch it', h=BUTTON_H)
        self.answers_button = Button('Answers', h=BUTTON_H)
        self.assemble_button = Button('Assemble', h=BUTTON_H)
        self.sprites_button = Button('Sprites folder', w=150)
        self.actions = ((self.sketch_button, self.open_sketch),
                        (self.answers_button, self.open_answers),
                        (self.assemble_button, self.assemble),
                        (self.sprites_button, self.open_sprites_folder))

    # --- state ------------------------------------------------------------

    def refresh(self):
        self.thumbs = {}
        self.yard = yard(self.style)
        pieces = self.style.pieces()
        if self.chosen not in pieces:
            missing = [p for p in pieces if not p.exists()]
            self.chosen = (missing or pieces or [None])[0]

    def changed(self):
        """The style's settings changed: keep them, and show what follows from them."""
        try:
            self.style.save()
        except OSError as exc:
            self.app.set_status(f'Cannot save fence.json: {exc}', error=True)
        self.refresh()

    def assemble_source(self):
        """The piece of this style the chosen one can be assembled from, the nearest length first; or None."""
        piece = self.chosen
        if piece is None:
            return None
        sources = [p for p in self.style.pieces(piece.orientation) if can_assemble(piece, p)]
        return min(sources, key=lambda p: (abs(p.length - piece.length), -p.length), default=None)

    def answers(self, piece):
        return self.app.store.for_pose(piece.pose) if piece else []

    # --- actions ----------------------------------------------------------

    def sketch(self):
        """The fence_sheets.FenceSketch of the chosen piece from its chosen reference; None, with the reason
        shown, if there is none."""
        from fence_sheets import FenceSketch
        piece = self.chosen
        styles = find_styles()
        options = reference_options(piece, styles)
        reference = chosen_reference(piece, options, default_reference(piece, styles))
        if reference is None:
            self.app.set_status('Nothing to draw it from yet', error=True)
            return None
        try:
            return FenceSketch(piece, reference)
        except (pygame.error, OSError) as exc:
            self.app.set_status(f'Cannot draw from {reference.label()}: {exc}', error=True)
            return None

    def open_sketch(self):
        if self.chosen is None:
            return
        sketch = self.sketch()
        if sketch is None:
            return
        from view_fence_design import FenceDesignView
        fresh = not sketch.has_sketch()
        if fresh:
            sketch.draft()
            sketch.undo_stack.clear()
            try:
                sketch.save()
            except (pygame.error, OSError):
                pass
        self.app.show(FenceDesignView(self.app, self, sketch))
        if fresh:
            self.app.set_status(f'A first draft of {self.chosen.title.lower()} from its raster - change it as you '
                                f'like, then send it')

    def open_answers(self):
        if not self.answers(self.chosen):
            return
        sketch = self.sketch()
        if sketch is None:
            return
        try:
            sheet = sketch.sheet()
        except (pygame.error, OSError) as exc:
            self.app.set_status(f'Cannot write the split image: {exc}', error=True)
            return
        from view_fence_answers import FenceAnswersView
        self.app.show(FenceAnswersView(self.app, self, sheet))

    def assemble(self):
        source = self.assemble_source()
        if source is None:
            return
        piece = self.chosen
        try:
            replaced = piece.save(assemble(piece, source, source.sprite()))
        except (pygame.error, OSError) as exc:
            self.app.set_status(f'Cannot save {piece.path.name}: {exc}', error=True)
            return
        self.refresh()
        self.app.set_status(f'{"Replaced" if replaced else "Saved"} {piece.path.name}, assembled from '
                            f'{source.title.lower()}. {piece.tiled_hint()}')
        self.app.toast.show(f'{piece.title} assembled')

    def open_sprites_folder(self):
        self.style.folder.mkdir(parents=True, exist_ok=True)
        if sys.platform == 'win32':
            os.startfile(self.style.folder)
        else:
            self.app.set_status(str(self.style.folder))

    # --- view -------------------------------------------------------------

    def header(self):
        style = self.style
        return (f'{style.title} - {style.material.title.lower()}, {style.done()}/{style.needed()} pieces',
                'Set the style on the left and the lengths it wants; pick a piece, Enter sketches it, Tab its '
                'answers, A assembles it from another length. Up/Down choose.')

    def footer(self):
        app = self.app
        return (app.back_button, app.folder_button, self.sprites_button), (app.settings_button,)

    def areas(self):
        body = self.app.body()
        settings_w, pieces_w = int(body.w * SETTINGS_SHARE), int(body.w * PIECES_SHARE)
        settings = pygame.Rect(body.x, body.y, settings_w, body.h)
        pieces = pygame.Rect(settings.right + PANEL_GAP, body.y, pieces_w, body.h)
        piece = pygame.Rect(pieces.right + PANEL_GAP, body.y, body.right - pieces.right - PANEL_GAP, body.h)
        return settings, pieces, piece

    def draw(self, screen, mouse):
        settings, pieces, piece = self.areas()
        self.chips = []
        self.draw_settings(screen, settings, mouse)
        self.draw_pieces(screen, pieces, mouse)
        self.draw_piece(screen, piece, mouse)

    def draw_settings(self, screen, rect, mouse):
        fonts = self.app.fonts
        small = fonts.small
        style = self.style
        draw_panel(screen, fonts, rect, 'The style')
        inner = rect.inflate(-28, -28)
        x, y, w = inner.x, inner.y, inner.w

        def label(text):
            screen.blit(small.render(text, True, TEXT_DIM), (x, y))
            return y + LABEL_GAP

        def chips(action, values, names, chosen, toggles=False):
            draw = draw_toggles if toggles else draw_chips
            found, bottom = draw(screen, small, values, names, chosen, x, y, w, mouse)
            self.chips += [(r, action, v) for r, v in found]
            return bottom + 16

        y = label('Material')
        y = chips('material', [m.key for m in MATERIALS], lambda k: next(m.title for m in MATERIALS if m.key == k),
                  style.material.key)
        y = label(f'{style.material.post.title()}s stand')
        y = chips('posts', POSTS_CHOICES, lambda n: 'at the ends only' if n == 0 else f'every {n}',
                  style.posts_every)
        y = label('Raster height, in tiles')
        y = chips('height', HEIGHTS, str, style.height)
        y = label('Description, goes into the prompt')
        self.field.rect = pygame.Rect(x, y, w, 36)
        self.field.draw(screen, fonts.font, mouse)
        y += 36 + 18
        offered = lengths_offered(style.posts_every)
        for orientation in ORIENTATIONS:
            y = label(f'{ORIENTATION_TITLES[orientation]} pieces wanted, tiles long')
            y = chips(orientation, offered, str, set(style.lengths[orientation]), toggles=True)

    def draw_pieces(self, screen, rect, mouse):
        fonts = self.app.fonts
        small = fonts.small
        draw_panel(screen, fonts, rect, 'Pieces')
        inner = rect.inflate(-20, -20)
        self.rows = []
        clip = screen.get_clip()
        screen.set_clip(inner)
        y = inner.y
        for orientation in ORIENTATIONS:
            pieces = self.style.pieces(orientation)
            screen.blit(small.render(ORIENTATION_TITLES[orientation], True, TEXT), (inner.x, y))
            y += LABEL_GAP
            if not pieces:
                screen.blit(small.render('none wanted', True, TEXT_DIM), (inner.x + 8, y))
                y += LABEL_GAP
            for piece in pieces:
                row = pygame.Rect(inner.x, y, inner.w, ROW_H - 6)
                chosen = piece == self.chosen
                if chosen or row.collidepoint(mouse):
                    pygame.draw.rect(screen, CHIP_ON if chosen else CHIP_HOVER, row, border_radius=6)
                thumb = self.thumb(piece)
                screen.blit(thumb, thumb.get_rect(midleft=(row.x + 4, row.centery)))
                tx = row.x + ROW_THUMB[0] + 14
                title = fonts.font.render(f'{piece.length} tile{"" if piece.length == 1 else "s"}', True, TEXT)
                screen.blit(title, (tx, row.y + 2))
                note, colour = self.state(piece)
                screen.blit(small.render(fit_text(small, note, row.right - tx - 6), True, colour),
                            (tx, row.y + 24))
                self.rows.append((row, piece))
                y += ROW_H
            y += 10
        screen.set_clip(clip)

    def state(self, piece):
        """(words, colour) for a piece's row."""
        answers = self.answers(piece)
        waiting = sum(e.status == pose_review.PENDING for e in answers)
        wanted = piece.length in self.style.lengths[piece.orientation]
        if waiting:
            return f'{waiting} answer{"" if waiting == 1 else "s"} to review', STATUS_COLORS[pose_review.PENDING]
        if piece.exists():
            return ('drawn' if wanted else 'drawn, not on the list'), STATUS_COLORS[pose_review.ACCEPTED]
        if answers:
            return f'not drawn, {len(answers)} answers', TEXT_DIM
        return 'not drawn yet', TEXT_DIM

    def thumb(self, piece):
        if piece not in self.thumbs:
            sprite = piece.sprite() if piece.exists() else None
            if sprite is None:
                tile = pygame.Surface(ROW_THUMB)
                tile.fill(CARD_BG)
                pygame.draw.rect(tile, TEXT_DIM, tile.get_rect(), 1)
            else:
                tile = fitted(sprite.subsurface(sprite.get_bounding_rect()), ROW_THUMB, THUMB_BG)
            self.thumbs[piece] = tile
        return self.thumbs[piece]

    def draw_piece(self, screen, rect, mouse):
        fonts = self.app.fonts
        small = fonts.small
        piece = self.chosen
        top = pygame.Rect(rect.x, rect.y, rect.w, rect.h * 55 // 100)
        bottom = pygame.Rect(rect.x, top.bottom + PANEL_GAP, rect.w, rect.bottom - top.bottom - PANEL_GAP)
        draw_panel(screen, fonts, top, piece.name if piece else 'No piece')
        draw_panel(screen, fonts, bottom, 'Laid together, as on the map')
        inner = top.inflate(-20, -20)

        # Along the foot: the buttons, the Tiled properties over them
        y = inner.bottom - BUTTON_H
        buttons = (self.sketch_button, self.answers_button, self.assemble_button)
        width = (inner.w - 2 * BUTTON_GAP) // 3
        for index, button in enumerate(buttons):
            button.rect = pygame.Rect(inner.x + index * (width + BUTTON_GAP), y, width, BUTTON_H)
        source = self.assemble_source()
        answers = self.answers(piece)
        waiting = sum(e.status == pose_review.PENDING for e in answers)
        self.sketch_button.enabled = piece is not None
        self.answers_button.enabled = bool(answers)
        self.answers_button.label = f'Answers ({waiting} new)' if waiting else f'Answers ({len(answers)})'
        self.assemble_button.enabled = source is not None
        self.assemble_button.label = f'Assemble from {source.length}' if source else 'Assemble'
        for button in buttons:
            button.draw(screen, fonts.font, mouse)
        if piece is None:
            return
        hint = small.render(fit_text(small, f'{piece.file_name}', inner.w), True, TEXT_DIM)
        screen.blit(hint, (inner.x, y - 2 * LABEL_GAP))
        props = piece.raster.tiled_properties()
        line = ', '.join(f'{k.replace("_pixel", "")} {v}' for k, v in props.items())
        screen.blit(small.render(fit_text(small, line, inner.w), True, TEXT_DIM), (inner.x, y - LABEL_GAP))

        area = pygame.Rect(inner.x, inner.y, inner.w, y - 2 * LABEL_GAP - 8 - inner.y)
        self.draw_raster(screen, area, piece)
        self.draw_yard(screen, bottom.inflate(-20, -20))

    def draw_raster(self, screen, area, piece):
        """The piece on its raster, blown up by whole pixels, with its tiles, run and posts."""
        raster = piece.raster
        w, h = raster.pixels
        factor = max(1, min(MAX_ZOOM, int(min(area.w / w, area.h / h))))
        rect = pygame.Rect(0, 0, w * factor, h * factor)
        rect.center = area.center
        self.checker.draw(screen, rect)
        sprite = piece.sprite() if piece.exists() else None
        if sprite is not None:
            screen.blit(pygame.transform.scale(sprite, rect.size), rect)
        unit = TILE * factor
        tiles_w, tiles_h = raster.size
        for x in range(tiles_w + 1):
            pygame.draw.line(screen, GRID_LINE, (rect.x + x * unit, rect.y), (rect.x + x * unit, rect.bottom))
        for y in range(tiles_h + 1):
            pygame.draw.line(screen, GRID_LINE, (rect.x, rect.y + y * unit), (rect.right, rect.y + y * unit))

        def at(point):
            return round(rect.x + point[0] * unit), round(rect.y + point[1] * unit)

        pygame.draw.line(screen, FOOT_COLOR, at(raster.start), at(raster.end()), 2)
        for post in raster.posts():
            pygame.draw.circle(screen, POST_COLOR, at(post), max(3, unit // 10), 2)
        if sprite is None:
            text = self.app.fonts.font.render('not drawn yet', True, ERROR_COLOR)
            screen.blit(text, text.get_rect(midbottom=(rect.centerx, rect.y - 6)))

    def draw_yard(self, screen, area):
        if self.yard is None:
            text = self.app.fonts.small.render('Draw a piece to see the pieces laid together', True, TEXT_DIM)
            screen.blit(text, text.get_rect(center=area.center))
            return
        w, h = self.yard.get_size()
        factor = min(area.w / w, area.h / h, MAX_ZOOM)
        if factor >= 1:
            factor = int(factor)
            image = pygame.transform.scale(self.yard, (w * factor, h * factor))
        else:
            image = pygame.transform.smoothscale(self.yard, (max(1, int(w * factor)), max(1, int(h * factor))))
        screen.blit(image, image.get_rect(center=area.center))

    # --- input ------------------------------------------------------------

    def click(self, pos):
        for button, action in self.actions:
            if button.hit(pos):
                action()
                return
        self.field.focus(self.field.rect.collidepoint(pos))
        if not self.field.focused:
            self.take_description()
        for rect, action, value in self.chips:
            if rect.collidepoint(pos):
                self.set(action, value)
                return
        for rect, piece in self.rows:
            if rect.collidepoint(pos):
                self.chosen = piece
                return

    def set(self, action, value):
        style = self.style
        if action == 'material':
            if value != style.material.key:
                style.set_material(value)
                self.app.set_status(f'Now {style.material.title.lower()}: the {style.material.post}s stand '
                                    + ('at the ends only' if style.posts_every == 0 else
                                       f'every {style.posts_every} tiles'))
        elif action == 'posts':
            style.set_posts_every(value)
        elif action == 'height':
            style.height = value
            self.app.set_status('A new height changes every raster: pieces already drawn keep theirs and may '
                                'no longer match', error=bool(style.done()))
        else:
            style.toggle_length(action, value)
        self.changed()

    def take_description(self):
        text = self.field.text.strip()
        if text != self.style.description:
            self.style.description = text
            self.changed()

    def captures_keys(self):
        return self.field.focused

    def text_input(self, text):
        self.field.type(text)

    def key(self, event):
        if self.field.focused:
            if self.field.key(event) == 'done':
                self.take_description()
            return
        pieces = self.style.pieces()
        if event.key in (pygame.K_UP, pygame.K_DOWN) and pieces:
            index = pieces.index(self.chosen) if self.chosen in pieces else 0
            index += -1 if event.key == pygame.K_UP else 1
            self.chosen = pieces[index % len(pieces)]
        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.open_sketch()
        elif event.key == pygame.K_TAB:
            self.open_answers()
        elif event.key == pygame.K_a:
            self.assemble()

    def back(self):
        self.field.focus(False)
        self.take_description()
        self.app.close_fence(self.styles_view)
        return True
