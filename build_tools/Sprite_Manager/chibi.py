"""The base chibi: horizontal strips of 64x64 frames the sheets are built from.

base_Chibi/Idle holds the standing chibi, base_Chibi/Walk and base_Chibi/Run
the cycles. <Walk|Run>_<strip>_Sheet_Ghost.png is the pose as a faint guide
for the image model; where it does not exist, a ghost is made on the fly.
"""

from pathlib import Path

import pygame

from images import mirrored, trim

CHIBI_DIR = Path(__file__).resolve().parent / 'base_Chibi'
IDLE_DIR = CHIBI_DIR / 'Idle'
CHIBI_FRAME_SIZE = 64
GHOST_SUFFIX = '_Ghost'

# A ghost made on the fly, in the colours of the hand-drawn one
GHOST_LINE = (0, 0, 0)
GHOST_LEVELS = ((185, (179, 179, 179)), (215, (206, 206, 206)), (256, (234, 234, 234)))
OUTLINE_LUMA = 120       # darker than this is outline
FACE_SHARE = 0.5         # this top share of the figure is the head: drawn without a face


def strip_path(folder, name, ghost=False):
    return folder / f'{name}_Sheet{GHOST_SUFFIX if ghost else ""}.png'


def motion_strip_path(direction, ghost=False):
    """The chibi's strip of a direction of a motion, or its hand-drawn ghost, drawn or not."""
    return strip_path(CHIBI_DIR / direction.motion.folder, direction.strip_name, ghost)


def ghost_path(direction):
    """Where the hand-drawn ghost strip of a direction lives, drawn or not."""
    return motion_strip_path(direction, ghost=True)


def load_strip(path, mirror=False):
    """Every frame of a strip, trimmed, in order."""
    sheet = pygame.image.load(str(path)).convert_alpha()
    frames = []
    for index in range(sheet.get_width() // CHIBI_FRAME_SIZE):
        frame = sheet.subsurface((index * CHIBI_FRAME_SIZE, 0, CHIBI_FRAME_SIZE, CHIBI_FRAME_SIZE))
        if frame.get_bounding_rect().w:
            frame = trim(frame)
            frames.append(mirrored(frame) if mirror else frame)
    return frames


def idle_frame(name, mirror=False):
    """The standing chibi, e.g. 'Idle_Down'; the first frame of its idle strip."""
    return load_strip(strip_path(IDLE_DIR, name), mirror)[0]


def idle_ghost(direction):
    """(ghost, made_on_the_fly) of the standing chibi facing a direction.

    Idle_<strip>_Sheet_Ghost.png is used where it exists, like the walk ghosts.
    """
    path = strip_path(IDLE_DIR, f'Idle_{direction.strip}', ghost=True)
    if path.is_file():
        return load_strip(path, direction.mirror)[0], False
    return make_ghost(idle_frame(f'Idle_{direction.strip}', direction.mirror)), True


def cycle_frames(direction):
    """The chibi's walk or run cycle for a direction, mirrored where it has to be."""
    return load_strip(motion_strip_path(direction), direction.mirror)


def strip_length(direction):
    """How many frames the direction's cycle has."""
    image = pygame.image.load(str(motion_strip_path(direction)))
    return image.get_width() // CHIBI_FRAME_SIZE


def make_ghost(frame):
    """A grey, faceless version of a chibi frame, like the hand-drawn ghosts.

    The outline stays black and the skin tones of the body become three
    greys. The head is one flat grey: its inner lines and shading are the
    face, which would only tempt the model into copying it.
    """
    w, h = frame.get_size()
    ghost = pygame.Surface((w, h), pygame.SRCALPHA)
    face_limit = int(h * FACE_SHARE)

    def is_outside(x, y):
        return not (0 <= x < w and 0 <= y < h) or frame.get_at((x, y)).a == 0

    for y in range(h):
        for x in range(w):
            color = frame.get_at((x, y))
            if color.a == 0:
                continue
            luma = 0.299 * color.r + 0.587 * color.g + 0.114 * color.b
            if luma < OUTLINE_LUMA:
                on_edge = any(is_outside(x + dx, y + dy)
                              for dx in (-1, 0, 1) for dy in (-1, 0, 1))
                if on_edge or y >= face_limit:
                    ghost.set_at((x, y), GHOST_LINE)
                    continue
            if y < face_limit:
                luma = 255  # the head is one flat grey: no face, no shading
            ghost.set_at((x, y), next(grey for limit, grey in GHOST_LEVELS if luma < limit))
    return ghost


def ghost_frames(direction):
    """(frames, made_on_the_fly) of the direction's ghost strip."""
    path = ghost_path(direction)
    if path.is_file():
        return load_strip(path, direction.mirror), False
    return [make_ghost(f) for f in cycle_frames(direction)], True
