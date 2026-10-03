"""From the model's answer to a new sprite, a plant or a building.

The answer is the split image of sprite_job.py with the right cell drawn in.
Both cells are found as for a new figure's first sprite (extraction.py,
layout 1x2). The example is cut out of the left cell and the new sprite out
of the right one, after the red frame is cut off its edges - the sprite may
well be red itself, so red cannot count as background as it does for the
humans. The new sprite is then scaled by the factor that brings the example
in the answer back to the example's real size, which keeps the size the
sketch gave it next to the example.
"""

import pygame

from extraction import Extraction, find_cells

FRAME_REDNESS = 70        # red minus the larger of green and blue, for a pixel of the red frame
FRAME_ROW_SHARE = 0.3     # a row or column this red is part of the frame
FRAME_SEARCH = 0.06       # the frame is looked for in this share of the cell along each edge
FRAME_EXTRA = 3           # pixels cut off past the frame, for its blurred edge


def _red_share(surface, rect):
    red = 0
    total = 0
    for x in range(rect.x, rect.right, max(1, rect.w // 200)):
        for y in range(rect.y, rect.bottom, max(1, rect.h // 200)):
            r, g, b, *_ = surface.get_at((x, y))
            red += r - max(g, b) > FRAME_REDNESS
            total += 1
    return red / max(1, total)


def strip_red_frame(cell):
    """The cell without the red frame along its edges, and how far it was cut in: (surface, (dx, dy))."""
    w, h = cell.get_size()
    reach = max(4, int(min(w, h) * FRAME_SEARCH))
    left = top = 0
    right, bottom = w, h
    edges = {
        'left': lambda i: pygame.Rect(i, 0, 1, h),
        'right': lambda i: pygame.Rect(w - 1 - i, 0, 1, h),
        'top': lambda i: pygame.Rect(0, i, w, 1),
        'bottom': lambda i: pygame.Rect(0, h - 1 - i, w, 1),
    }
    cut = {}
    for edge, line in edges.items():
        last = -1
        for i in range(reach):
            if _red_share(cell, line(i)) >= FRAME_ROW_SHARE:
                last = i
        cut[edge] = last + 1 + FRAME_EXTRA if last >= 0 else 0
    left, top = cut['left'], cut['top']
    right, bottom = w - cut['right'], h - cut['bottom']
    rect = pygame.Rect(left, top, max(1, right - left), max(1, bottom - top))
    inner = cell.subsurface(rect).copy()
    return inner, rect.topleft


class SpriteResult:
    """A loaded answer and the sprite made from it."""

    def __init__(self, path, example):
        """
        Args:
            path: The answer image.
            example: The example sprite as it is in the game (trimmed).

        Raises:
            ValueError, pygame.error: If the cells or the sprites cannot be found.
        """
        self.image = pygame.image.load(str(path)).convert()
        ref_rect, target_rect, _ = find_cells(self.image, '1x2')
        self.ref = Extraction(self.image.subsurface(ref_rect).copy())
        cell, _ = strip_red_frame(self.image.subsurface(target_rect).copy())
        self.target = Extraction(cell, drop_red=False)
        if self.ref.bbox is None:
            raise ValueError('No example found in the left cell.')
        if self.target.bbox is None:
            raise ValueError('The right cell is empty.')
        self.example = example
        self.build()

    def build(self):
        """Scale the new sprite by what brings the example back to its real size."""
        w, h = self.example.get_size()
        # Along the example's longer side, where the measure is the most exact
        if h >= w:
            self.scale = h / self.ref.bbox.height
        else:
            self.scale = w / self.ref.bbox.width
        sprite = self.target.sprite
        size = (max(1, round(sprite.get_width() * self.scale)), max(1, round(sprite.get_height() * self.scale)))
        self.output = pygame.transform.smoothscale(sprite, size)

    def output_to_cell(self, point):
        """A point on the output back in the right cell's coordinates."""
        return (int(point[0] / self.scale + self.target.bbox.x),
                int(point[1] / self.scale + self.target.bbox.y))


class SpriteDetail:
    """One answer of a job and the sprite accepting it would make."""

    def __init__(self, job, entry):
        """
        Raises:
            pygame.error, OSError: If the answer's image cannot be read.
        """
        self.job = job
        self.entry = entry
        self.path = job.out_dir / entry.image
        image = pygame.image.load(str(self.path))
        entry.width, entry.height = image.get_size()
        self.result = None
        self.error = ''
        try:
            self.result = SpriteResult(self.path, job.example)
        except Exception as exc:  # cell detection and extraction fail in many ways
            self.error = f'Cannot use this image: {exc}'
        self.preview = None   # (rect, factor) of the sprite where it was last drawn

    def toggle_hole(self, pos):
        """Click on the preview: switch an enclosed white area see-through, or back."""
        if not (self.result and self.preview):
            return
        rect, factor = self.preview
        if not rect.collidepoint(pos):
            return
        point = self.result.output_to_cell(((pos[0] - rect.x) / factor, (pos[1] - rect.y) / factor))
        target = self.result.target
        if target.surface.get_rect().collidepoint(point) and target.toggle_hole(point):
            self.result.build()
