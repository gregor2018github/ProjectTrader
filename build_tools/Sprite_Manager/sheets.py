"""The 2x2 reference sheets and prompts the image model is given, one per walk or run frame.

    +---------------------------+---------------------------+
    | chibi standing            | chibi walking or running, |
    | (Idle_Down / Idle_Up)     | frame n (<Walk|Run>_...)  |
    +---------------------------+---------------------------+
    | <npc>_front_static.png    | red frame: the same       |
    | (or _back_static.png)     | frame as a faint grey     |
    |                           | ghost, for the image      |
    |                           | model to draw the NPC on  |
    +---------------------------+---------------------------+

With the head locked, the NPC's own head is cut off the bottom left sprite
at the neck and put solid into the red frame where the ghost's head is,
bobbing and shifting with it, and the ghost's head is left out. That leaves
the model less to make up: heads came back warped, recoloured or turned the
other way. It is only offered where the bottom left sprite faces the way
the frame does (lock_head_possible); a standing sheet has no head facing
its way to copy yet.
"""

from dataclasses import dataclass
from pathlib import Path

import pygame

import chibi
from extraction import shape_mask
from images import scaled, trim
from npc import BASE_POSES, DEFAULT_BASE
from walk import Direction, standing_pose

# Sheet appearance
MARGIN_RATIO = 0.06
MIN_MARGIN = 16
FRAME_WIDTH = 4
FRAME_COLOR = (0, 0, 0)
TARGET_FRAME_COLOR = (220, 0, 0)
TARGET_FRAME_WIDTH = 3
GHOST_ALPHA = 110        # 0 = invisible, 255 = solid
DONE_FRAME_COLOR = (80, 180, 90)   # the target cell once its sprite is accepted (cards only)

# Finding the neck: the narrowest row in this band of the mannequin's height, from the top
NECK_BAND = (0.3, 0.65)
NECK_SEARCH = 0.08       # of the NPC's height around where the mannequin's neck would be
HEAD_ALPHA = 128         # pixels this opaque count for the NPC's outline

# Says nothing of walking or running on purpose: told it was a walk, the model drew
# its own stock stride and ignored the ghost. It is asked only to copy a pose.
PROMPT_TEMPLATE = """\
The attached picture is a 2x2 grid of pixel-art sprites.

Top left: a grey mannequin, {base_view}. Bottom left: {name} in that same pose.
Top right: the mannequin in another pose, {facing}. The red frame bottom right holds a faint grey copy of it.

Draw {name} in the red frame in exactly the grey figure's pose. Trace it: each foot, knee, hand, elbow and the head go where the grey figure has them, at the same height and lean. Do not make up a pose of your own - if its feet are close together or its arms hang down, {name}'s do too.{head}

Keep {name}'s look from the bottom left: proportions, face, hair, headwear, clothes, colours, outline, crisp pixel art with hard edges. Same size, feet on the same ground line, white background, nothing of the grey figure left. Change nothing outside the red frame.
"""

STANDING_PROMPT_TEMPLATE = """The attached picture holds a 2x2 grid of pixel-art sprites for my medieval trading game "Merchant's Rise".

Top left: a plain, featureless chibi mannequin standing still, {base_view}.
Top right: the same mannequin standing still, {view}.
Bottom left: {name}, standing still, {base_view}, in the same pose as the mannequin top left.
Bottom right (red frame): a faint, see-through grey ghost of the mannequin in the same pose as top right. It is only a guide. Draw {name} over it, standing still, {view}, so that the head, body, arms, legs and feet sit exactly where the ghost's are. No trace of the ghost may remain in the finished drawing.

The mannequin and the ghost show only the pose. Do not copy their proportions, bald head, skin or grey colour. Keep {name}'s own look from the bottom left sprite: proportions, head size, face, hair, headwear, clothing, colours and outline, and the same crisp pixel-art style with hard pixel edges and no anti-aliasing or blur.
Parts that the bottom left sprite does not show should follow on naturally from what it does show.
Keep {name} at the same size as in the bottom left, with the feet on the same ground line, on the plain white background. Do not draw anything outside the red frame and do not change the other three cells.
"""
HEAD_LOCKED = (
    " {name}'s head is already in the red frame: keep it exactly as it is and draw the body under it, "
    "joined at the neck.")

# How the frame prompt describes the way a pose faces, without saying it moves
FACING = {
    'front': 'facing the viewer',
    'front_right': 'seen three-quarters from the front, facing down and to the right',
    'right': 'seen from the side, facing to the right',
    'back_right': 'seen three-quarters from behind, facing up and to the right',
    'back': 'seen from behind, facing away from the viewer',
    'back_left': 'seen three-quarters from behind, facing up and to the left',
    'left': 'seen from the side, facing to the left',
    'front_left': 'seen three-quarters from the front, facing down and to the left',
}

# How the standing prompt describes each direction a standing sprite can be made for
STANDING_VIEWS = {key: FACING[key] for key in ('back', 'left', 'right')}

# What can go wrong building a sheet from the files on disk
SHEET_ERRORS = (pygame.error, OSError, IndexError)


@dataclass
class FrameSheet:
    """One frame of a direction, or its standing sprite: its sheet, prompt and where they were written."""

    direction: Direction
    frame: int        # counted from 1; 0 for the standing sprite
    count: int
    surface: pygame.Surface
    path: Path
    prompt: str
    auto_ghost: bool
    ghost: pygame.Surface   # the goal pose, at the scale of the saved frames
    target: pygame.Rect     # the red-framed cell on the surface
    ground: int             # the y the sprites in the target cell stand on

    @property
    def standing(self):
        return self.frame == 0

    @property
    def pose(self):
        """'right_move3', or 'right_static' for the standing sprite."""
        return standing_pose(self.direction) if self.standing else self.direction.pose(self.frame)

    @property
    def name(self):
        """'Frame 3' or 'Standing sprite', for status lines."""
        return 'Standing sprite' if self.standing else f'Frame {self.frame}'

    def with_result(self, sprite):
        """The sheet with the accepted sprite in the target cell instead of the ghost.

        Only for showing what is done: the sheet that is sent keeps its ghost.
        The sprite is at the scale of the reference, bottom left, so it goes
        in as it is, on the same ground line.
        """
        surface = self.surface.copy()
        surface.fill((255, 255, 255), self.target)
        sprite = trim(sprite)
        surface.blit(sprite, sprite.get_rect(midbottom=(self.target.centerx, self.ground)))
        pygame.draw.rect(surface, DONE_FRAME_COLOR, self.target, TARGET_FRAME_WIDTH)
        return surface


def build_sheet(idle, pose, ghost, npc, lock_head=False):
    """Lay out the three sprites plus the red-framed target cell holding the ghost.

    Every sprite stands on the ground line of its cell, so the cycle's frame
    keeps the bob of the cycle and the ghost stands where the NPC will.

    Args:
        lock_head: Put the NPC's head into the target cell where the ghost's
            head is, instead of the ghost's (see the module docstring).

    Returns:
        (sheet, ghost, target cell, ground line) - the ghost solid, at the scale
        of the NPC sprite, which is also the scale an accepted frame is saved at.
    """
    # One scale for all chibi sprites, taken from the standing one, so every
    # frame of a cycle comes out the same size.
    factor = max(1, round(npc.get_height() / idle.get_height()))
    sprites = [scaled(idle, factor), scaled(pose, factor), npc]
    ghost_source = ghost
    solid_ghost = scaled(ghost, factor)
    ghost = solid_ghost.copy()
    ghost.set_alpha(GHOST_ALPHA)

    max_w = max(s.get_width() for s in sprites + [ghost])
    max_h = max(s.get_height() for s in sprites + [ghost])
    margin = max(MIN_MARGIN, int(max(max_w, max_h) * MARGIN_RATIO))
    cell_w, cell_h = max_w + 2 * margin, max_h + 2 * margin

    sheet = pygame.Surface((2 * cell_w + 3 * FRAME_WIDTH, 2 * cell_h + 3 * FRAME_WIDTH))
    sheet.fill(FRAME_COLOR)
    cells = []
    for row in range(2):
        for col in range(2):
            rect = pygame.Rect(FRAME_WIDTH + col * (cell_w + FRAME_WIDTH),
                               FRAME_WIDTH + row * (cell_h + FRAME_WIDTH), cell_w, cell_h)
            sheet.fill((255, 255, 255), rect)
            cells.append(rect)

    head = None
    if lock_head:
        head, ghost_neck, shift = locked_head(idle, ghost_source, npc, factor)
        ghost.fill((0, 0, 0, 0), (0, 0, ghost.get_width(), ghost_neck))   # the ghost's head makes way
    for sprite, cell in zip(sprites + [ghost], cells):
        sheet.blit(sprite, sprite.get_rect(midbottom=(cell.centerx, cell.bottom - margin)))
    if head:
        # Where the head is on the bottom left sprite, moved into the target cell and on by the pose's shift
        image, rect = head
        npc_rect = npc.get_rect(midbottom=(cells[2].centerx, cells[2].bottom - margin))
        sheet.blit(image, rect.move(npc_rect.x + cells[3].x - cells[2].x + shift[0], npc_rect.y + shift[1]))
    pygame.draw.rect(sheet, TARGET_FRAME_COLOR, cells[3], TARGET_FRAME_WIDTH)
    return sheet, solid_ghost, cells[3], cells[3].bottom - margin


def neck_row(mask, start, end):
    """The narrowest row of a mask in [start, end): where the head meets the body.

    Of rows equally narrow the lowest is taken, so a chin or collar a pixel
    narrower does not cut the head short.
    """
    w = mask.get_size()[0]
    rows = range(max(1, start), max(start + 1, end))
    widths = {y: sum(mask.get_at((x, y)) for x in range(w)) for y in rows}
    return min(rows, key=lambda y: (widths[y], -y))


def mannequin_neck(frame):
    """The neck row of a trimmed chibi frame (the mannequin or its ghost)."""
    h = frame.get_height()
    return neck_row(pygame.mask.from_surface(frame), int(h * NECK_BAND[0]), int(h * NECK_BAND[1]))


def head_centre(frame, neck):
    """How far the middle of a chibi frame's head is from the frame's middle: its lean."""
    mask = pygame.mask.from_surface(frame)
    w = frame.get_width()
    middles = []
    for y in range(neck):
        xs = [x for x in range(w) if mask.get_at((x, y))]
        if xs:
            middles.append((xs[0] + xs[-1]) / 2)
    return sum(middles) / len(middles) - (w - 1) / 2 if middles else 0


def locked_head(idle, ghost, npc, factor):
    """The NPC's head and where it goes over the ghost.

    The neck is looked for on the NPC around where the mannequin's would be,
    counted from the feet, so a hat does not throw it off.

    Args:
        idle: The standing mannequin the NPC was drawn on, trimmed.
        ghost: The goal pose, trimmed, at chibi scale.
        npc: The NPC's standing sprite, trimmed.
        factor: The chibi's scale on the sheet.

    Returns:
        ((head image, its rect on the NPC sprite), the ghost's neck row at
        sheet scale, (dx, dy) the head moves from the standing pose to the goal pose).
    """
    idle_neck, ghost_neck = mannequin_neck(idle), mannequin_neck(ghost)
    h = npc.get_height()
    expected = h - round((idle.get_height() - idle_neck) * h / idle.get_height())
    reach = max(2, int(h * NECK_SEARCH))
    neck = neck_row(pygame.mask.from_surface(npc, HEAD_ALPHA), expected - reach, expected + reach + 1)
    rect = pygame.Rect(0, 0, npc.get_width(), neck)
    # Both stand on the ground line, centred, so the head's top tells the bob and its middle the lean
    dx = round((head_centre(ghost, ghost_neck) - head_centre(idle, idle_neck)) * factor)
    dy = (idle.get_height() - ghost.get_height()) * factor
    return (npc.subsurface(rect).copy(), rect), ghost_neck * factor, (dx, dy)


def lock_head_possible(npc, direction):
    """Whether a frame of the direction can have its head locked: its reference faces its way."""
    pose = standing_pose(direction)
    return bool(pose) and npc.base_for(direction) == pose


def prompt_for(npc, direction, lock_head=False):
    base_view = BASE_POSES[npc.base_for(direction)].view
    head = HEAD_LOCKED.format(name=npc.display_name) if lock_head else ''
    return PROMPT_TEMPLATE.format(base_view=base_view, facing=FACING[direction.key],
                                  name=npc.display_name, head=head)


def write_sheets(npc, direction, frames=None, lock_head=False):
    """Build a direction's sheets from the base files and write them.

    Args:
        npc: The WalkNpc.
        direction: The Direction.
        frames: Frame numbers (from 1) to build; None builds them all.
        lock_head: Lock the NPC's head into the target cell, where the
            direction allows it (lock_head_possible).

    Returns:
        [FrameSheet], in frame order.

    Raises:
        One of SHEET_ERRORS if a base file is missing or unreadable.
    """
    base_pose = npc.base_for(direction)
    base = BASE_POSES[base_pose]
    idle = chibi.idle_frame(base.idle, base.mirror)
    reference = trim(pygame.image.load(str(npc.sprite_path(base_pose))).convert_alpha())
    cycle = chibi.cycle_frames(direction)
    ghosts, auto_ghost = chibi.ghost_frames(direction)
    count = len(cycle)
    lock_head = lock_head and lock_head_possible(npc, direction)

    npc.out_dir.mkdir(parents=True, exist_ok=True)
    sheets = []
    for frame in frames or range(1, count + 1):
        surface, ghost, target, ground = build_sheet(idle, cycle[frame - 1], ghosts[min(frame, len(ghosts)) - 1],
                                                     reference, lock_head)
        stem = f'{npc.prefix}_{direction.pose(frame)}'
        path = npc.out_dir / f'{stem}_sheet.png'
        prompt = prompt_for(npc, direction, lock_head)
        pygame.image.save(surface, str(path))
        (npc.out_dir / f'{stem}_prompt.txt').write_text(prompt, encoding='utf-8')
        sheets.append(FrameSheet(direction, frame, count, surface, path, prompt, auto_ghost, ghost,
                                 target, ground))
    return sheets


def can_make_standing(direction):
    """Whether a standing sprite can be made for the direction (not the front: that is the reference)."""
    return direction.key in STANDING_VIEWS


def write_standing_sheet(npc, direction):
    """Build the sheet for a direction's standing sprite, from the NPC's front one, and write it.

    Returns:
        A FrameSheet with frame 0.

    Raises:
        One of SHEET_ERRORS if a base file is missing or unreadable.
    """
    idle = chibi.idle_frame(BASE_POSES[DEFAULT_BASE].idle)
    target = chibi.idle_frame(f'Idle_{direction.strip}', direction.mirror)
    ghost_source, auto_ghost = chibi.idle_ghost(direction)
    reference = trim(pygame.image.load(str(npc.sprite_path(DEFAULT_BASE))).convert_alpha())
    surface, ghost, target_cell, ground = build_sheet(idle, target, ghost_source, reference)

    npc.out_dir.mkdir(parents=True, exist_ok=True)
    pose = standing_pose(direction)
    stem = f'{npc.prefix}_{pose}'
    path = npc.out_dir / f'{stem}_sheet.png'
    prompt = STANDING_PROMPT_TEMPLATE.format(
        base_view=BASE_POSES[DEFAULT_BASE].view, view=STANDING_VIEWS[direction.key],
        name=npc.display_name)
    pygame.image.save(surface, str(path))
    (npc.out_dir / f'{stem}_prompt.txt').write_text(prompt, encoding='utf-8')
    return FrameSheet(direction, 0, 0, surface, path, prompt, auto_ghost, ghost, target_cell, ground)


def reference_shapes(npc, pose, base):
    """({pose: path}, {pose: mask}) that make extraction.py scale
    the answer like the NPC's own standing sprite instead of the player."""
    path = npc.sprite_path(base)
    sprite = pygame.image.load(str(path)).convert_alpha()
    mask = shape_mask(pygame.mask.from_surface(sprite), sprite.get_bounding_rect())
    return {pose: path}, {pose: mask}
