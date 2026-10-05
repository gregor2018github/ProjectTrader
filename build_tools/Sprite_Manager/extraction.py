"""From an image the model returned to a finished sprite.

The model returns the sheet it was given with the empty cell filled in. Both
layouts are understood:

    1x2 (first sprite of a new figure)    2x2 (a frame's sheet)
    +-----------+-----------+             +-----------+-----------+
    | player    | new NPC   |             | reference | NPC       |
    +-----------+-----------+             +-----------+-----------+
                                          | reference | new NPC   |
                                          | (pose)    | (pose)    |
                                          +-----------+-----------+

The cells are found, the reference and the new sprite are cut out of their
white background, the reference's pose is recognised among the reference
sprites, and the new sprite is scaled by the same factor that brings the
reference back to the size of the real sprite. That keeps every frame in
proportion with the player and with each other. Result.output is the
transparent sprite on the reference's canvas.
"""

from pathlib import Path

import pygame

# Cell detection
DARK_TOLERANCE = 70      # a pixel darker than this in every channel counts as frame line
LINE_FILL = 0.85         # share of a row/column that must be dark to be a frame line
BORDER_ZONE = 0.08       # outer frame lines are searched in this share of each edge
EMPTY_LINE = 0.04        # a row/column with this little ink is white background
CELL_INSET = 0.012       # at most this much frame leftover is trimmed off a cell edge (share of its smaller side)

# Background removal
WHITE_TOLERANCE = 24     # every channel above 255 - this counts as background white
FRINGE_TOLERANCE = 60    # light pixels next to the background are eaten as anti-alias fringe
FRINGE_PASSES = 2
FRAME_RED = (220, 20, 20)  # the red target frame, in case Gemini draws it too
RED_TOLERANCE = 70
SPECK_RATIO = 0.005      # blobs smaller than this share of the largest blob are dropped

POSE_MATCH_SIZE = (32, 52)


# ---------------------------------------------------------------------------
# Cell detection
# ---------------------------------------------------------------------------

def line_fill(dark, length, vertical):
    """Share of dark pixels in every column (vertical) or row of `dark`."""
    w, h = dark.get_size()
    if vertical:
        return [pygame.transform.average_color(dark, (i, 0, 1, h))[0] / 255 for i in range(length)]
    return [pygame.transform.average_color(dark, (0, i, w, 1))[0] / 255 for i in range(length)]


def dark_runs(fills, start, end):
    """Runs [a, b) of consecutive frame lines within [start, end)."""
    runs, run_start = [], None
    for i in range(start, end + 1):
        is_line = i < end and fills[i] >= LINE_FILL
        if is_line and run_start is None:
            run_start = i
        elif not is_line and run_start is not None:
            runs.append((run_start, i))
            run_start = None
    return runs


def empty_runs(fills, start, end):
    """Runs [a, b) of consecutive near-white rows/columns within [start, end)."""
    runs, run_start = [], None
    for i in range(start, end + 1):
        empty = i < end and fills[i] <= EMPTY_LINE
        if empty and run_start is None:
            run_start = i
        elif not empty and run_start is not None:
            runs.append((run_start, i))
            run_start = None
    return runs


def middle_gap(fills, length, start, end):
    """Where two cells meet although no frame line was drawn between them.

    Small answers often come back without the line: the cells then only meet
    in the white margin around their sprites. The widest such gap, nearest
    the middle, takes the line's place. Without it the two cells would be
    read as one and the sprite would come out as two figures stacked.

    Returns:
        (a, b) of the gap, or twice the exact middle if there is no gap.
    """
    runs = empty_runs(fills, start, end)
    if not runs:
        return length // 2, length // 2
    return max(runs, key=lambda run: (run[1] - run[0],
                                      -abs((run[0] + run[1]) / 2 - length / 2)))


def split_axis(fills, length, expect_split=False):
    """Return (content_start, split_a, split_b, content_end) along one axis.

    split_a..split_b is the inner frame line; both are None if there is none.

    Args:
        fills: Ink share per row or column.
        length: Number of rows or columns.
        expect_split: True when the caller knows the sheet is divided along
            this axis, so a missing frame line is looked for as a white gap
            instead of being taken for "there is only one cell here".
    """
    zone = max(1, int(length * BORDER_ZONE))
    first = dark_runs(fills, 0, zone)
    last = dark_runs(fills, length - zone, length)
    start = first[-1][1] if first else 0
    end = last[0][0] if last else length

    low, high = int(length * 0.3), int(length * 0.7)
    inner = dark_runs(fills, low, high)
    if inner:
        a, b = min(inner, key=lambda run: abs((run[0] + run[1]) / 2 - length / 2))
        return start, a, b, end
    if expect_split:
        a, b = middle_gap(fills, length, low, high)
        return start, a, b, end
    return start, None, None, end


def find_cells(image, layout=None):
    """Return (reference_rect, target_rect, layout) for a Gemini result.

    Args:
        image: The image the model returned.
        layout: '1x2', '2x1' or '2x2' when the caller knows which sheet was
            sent. The cells are then separated even where the model drew no
            frame line, which happens in small answers. None guesses the
            layout from the frame lines alone. '2x1' is a split image with
            its cells above each other, the reference on top; it is never
            guessed.
    """
    w, h = image.get_size()
    dark = dark_lines(image)
    if layout == '2x1':
        left, _, _, right = split_axis(line_fill(dark, w, True), w)
        top, row_a, row_b, bottom = split_axis(line_fill(dark, h, False), h, True)
        ref = pygame.Rect(left, top, right - left, row_a - top)
        target = pygame.Rect(left, row_b, right - left, bottom - row_b)
        ink = ink_lines(image)
        return trim_frame(ink, ref), trim_frame(ink, target), layout
    # A 2x2 sheet is always clearly taller than wide. An answer that is not
    # did not keep the layout, and guessing beats forcing a split onto it.
    if layout == '2x2' and w >= h:
        layout = None
    left, col_a, col_b, right = split_axis(line_fill(dark, w, True), w, layout is not None)
    top, row_a, row_b, bottom = split_axis(line_fill(dark, h, False), h, layout == '2x2')

    if col_a is None:  # no visible middle line: split in the middle
        col_a = col_b = (left + right) // 2
    if row_a is None:
        layout = '1x2'
        ref = pygame.Rect(left, top, col_a - left, bottom - top)
        target = pygame.Rect(col_b, top, right - col_b, bottom - top)
    else:
        layout = '2x2'
        ref = pygame.Rect(left, row_b, col_a - left, bottom - row_b)
        target = pygame.Rect(col_b, row_b, right - col_b, bottom - row_b)

    ink = ink_lines(image)
    return trim_frame(ink, ref), trim_frame(ink, target), layout


def dark_lines(image):
    """The image's near-black pixels, where the frame lines are."""
    return pygame.mask.from_threshold(
        image, (0, 0, 0, 255), (DARK_TOLERANCE, DARK_TOLERANCE, DARK_TOLERANCE, 255)).to_surface()


def ink_lines(image):
    """Everything that is not near-white: frame lines plus their blurry edges."""
    t = FRINGE_TOLERANCE
    ink = pygame.mask.from_threshold(image, (255, 255, 255, 255), (t, t, t, 255))
    ink.invert()
    return ink.to_surface()


def trim_frame(ink, rect):
    """Shrink `rect` past leftovers of the frame lines along its edges.

    Only rows/columns that are mostly ink are removed, so a sprite that
    reaches right down to the frame keeps its feet.
    """
    limit = int(min(rect.size) * CELL_INSET) + 3

    def fill(r):
        return pygame.transform.average_color(ink, r)[0] / 255

    rect = rect.copy()
    for _ in range(limit):
        if fill((rect.x, rect.y, rect.w, 1)) < LINE_FILL / 2:
            break
        rect.y += 1
        rect.h -= 1
    for _ in range(limit):
        if fill((rect.x, rect.bottom - 1, rect.w, 1)) < LINE_FILL / 2:
            break
        rect.h -= 1
    for _ in range(limit):
        if fill((rect.x, rect.y, 1, rect.h)) < LINE_FILL / 2:
            break
        rect.x += 1
        rect.w -= 1
    for _ in range(limit):
        if fill((rect.right - 1, rect.y, 1, rect.h)) < LINE_FILL / 2:
            break
        rect.w -= 1
    return rect


# ---------------------------------------------------------------------------
# Background removal
# ---------------------------------------------------------------------------

def dilate(mask):
    grown = mask.copy()
    for offset in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        grown.draw(mask, offset)
    return grown


class Extraction:
    """One cell of the Gemini image, cut out of its white background."""

    def __init__(self, cell_surface, drop_red=True):
        """
        Args:
            drop_red: Take the red of the target frame for background too.
                A plant may be red itself; its cell has the frame cut off
                beforehand instead (plant_extraction.py).
        """
        self.surface = cell_surface
        w, h = cell_surface.get_size()
        t = WHITE_TOLERANCE
        self.background = pygame.mask.from_threshold(cell_surface, (255, 255, 255, 255), (t, t, t, 255))
        if drop_red:
            self.background.draw(pygame.mask.from_threshold(
                cell_surface, FRAME_RED + (255,), (RED_TOLERANCE, RED_TOLERANCE, RED_TOLERANCE, 255)), (0, 0))

        # Background = every background-coloured area connected to the cell edge.
        self.outside = pygame.Mask((w, h))
        edge = [(x, y) for x in range(w) for y in (0, h - 1)] + [(x, y) for y in range(h) for x in (0, w - 1)]
        for point in edge:
            if self.background.get_at(point) and not self.outside.get_at(point):
                self.outside.draw(self.background.connected_component(point), (0, 0))

        # Eat the light anti-alias fringe between the outline and the background.
        f = FRINGE_TOLERANCE
        light = pygame.mask.from_threshold(cell_surface, (255, 255, 255, 255), (f, f, f, 255))
        for _ in range(FRINGE_PASSES):
            self.outside.draw(light.overlap_mask(dilate(self.outside), (0, 0)), (0, 0))

        self.holes = []  # enclosed background areas the user made transparent
        self.update()

    def update(self):
        sprite = pygame.Mask(self.outside.get_size(), fill=True)
        sprite.erase(self.outside, (0, 0))
        for hole in self.holes:
            sprite.erase(hole, (0, 0))

        blobs = sprite.connected_components()
        self.mask = pygame.Mask(sprite.get_size())
        if blobs:
            largest = max(blob.count() for blob in blobs)
            for blob in blobs:
                if blob.count() >= largest * SPECK_RATIO:
                    self.mask.draw(blob, (0, 0))

        rects = self.mask.get_bounding_rects()
        self.bbox = rects[0].unionall(rects[1:]) if rects else None
        if self.bbox is None:
            self.sprite = None
            return
        rgba = self.surface.convert_alpha()
        alpha = self.mask.to_surface(setcolor=(255, 255, 255, 255), unsetcolor=(0, 0, 0, 0))
        rgba.blit(alpha, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        self.sprite = rgba.subsurface(self.bbox).copy()

    def toggle_hole(self, point):
        """Switch an enclosed white area at `point` (cell coordinates) on/off."""
        for hole in self.holes:
            if hole.get_at(point):
                self.holes.remove(hole)
                self.update()
                return True
        if self.background.get_at(point) and not self.outside.get_at(point):
            self.holes.append(self.background.connected_component(point))
            self.update()
            return True
        return False


def shape_mask(mask, rect):
    """Mask content inside `rect`, squeezed to POSE_MATCH_SIZE."""
    part = pygame.Mask(rect.size)
    part.draw(mask, (-rect.x, -rect.y))
    return part.scale(POSE_MATCH_SIZE)


def detect_pose(extraction, player_shapes):
    ref = shape_mask(extraction.mask, extraction.bbox)

    def similarity(shape):
        overlap = ref.overlap_area(shape, (0, 0))
        return overlap / max(1, ref.count() + shape.count() - overlap)

    return max(player_shapes, key=lambda pose: similarity(player_shapes[pose]))


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

class Result:
    """A loaded Gemini image and the sprite made from it."""

    def __init__(self, path, player_poses, player_shapes, layout=None):
        self.path = Path(path)
        self.image = pygame.image.load(str(path)).convert()
        self.ref_rect, self.target_rect, self.layout = find_cells(self.image, layout)
        self.ref = Extraction(self.image.subsurface(self.ref_rect).copy())
        self.target = Extraction(self.image.subsurface(self.target_rect).copy())
        if self.ref.bbox is None:
            raise ValueError('No player sprite found in the reference cell.')
        if self.target.bbox is None:
            raise ValueError('The target cell is empty.')
        self.player_poses = player_poses
        self.detected_pose = detect_pose(self.ref, player_shapes)
        self.pose = self.detected_pose
        self.build()

    def build(self):
        """Scale the NPC like the reference and place it on the player's canvas."""
        player = pygame.image.load(str(self.player_poses[self.pose])).convert_alpha()
        self.player = player
        content = player.get_bounding_rect()
        self.scale = content.height / self.ref.bbox.height

        sprite = self.target.sprite
        size = (max(1, round(sprite.get_width() * self.scale)), max(1, round(sprite.get_height() * self.scale)))
        scaled = pygame.transform.smoothscale(sprite, size)

        # Bottom-centred on the player's feet; the canvas grows if the NPC is bigger.
        x, y = content.centerx - size[0] // 2, content.bottom - size[1]
        cw, ch = player.get_size()
        left, top = min(0, x), min(0, y)
        right, bottom = max(cw, x + size[0]), max(ch, y + size[1])
        self.output = pygame.Surface((right - left, bottom - top), pygame.SRCALPHA)
        self.paste = (x - left, y - top)
        self.output.blit(scaled, self.paste)
        # Where the player canvas sits on the output canvas, for the side-by-side preview.
        self.player_offset = (-left, -top)

    def set_pose(self, pose):
        self.pose = pose
        self.build()

    def output_to_cell(self, point):
        """Map a point on the output canvas back to target cell coordinates."""
        x = (point[0] - self.paste[0]) / self.scale + self.target.bbox.x
        y = (point[1] - self.paste[1]) / self.scale + self.target.bbox.y
        return int(x), int(y)
