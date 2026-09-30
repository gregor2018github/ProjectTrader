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
"""

from dataclasses import dataclass
from pathlib import Path

import pygame

import chibi
from create_new_NPC import shape_mask
from images import scaled, trim
from npc import BASE_POSES, DEFAULT_BASE
from walk import Direction, standing_pose

# Sheet appearance (same look as create_new_pose.py)
MARGIN_RATIO = 0.06
MIN_MARGIN = 16
FRAME_WIDTH = 4
FRAME_COLOR = (0, 0, 0)
TARGET_FRAME_COLOR = (220, 0, 0)
TARGET_FRAME_WIDTH = 3
GHOST_ALPHA = 110        # 0 = invisible, 255 = solid

PROMPT_TEMPLATE = """\
The attached picture holds a 2x2 grid of pixel-art sprites for my medieval trading game "Merchant's Rise".

Top left: a plain, featureless chibi mannequin standing still, {base_view}.
Top right: the same mannequin in frame {frame} of {count} of a {cycle} cycle, {motion}.
Bottom left: {name}, standing still, {base_view}, in the same pose as the mannequin top left.
Bottom right (red frame): a faint, see-through grey ghost of the mannequin in the same {verb} pose as top right. It is only a guide. Draw {name} over it, {motion}, so that the head, body, arms, legs and feet sit exactly where the ghost's are: same step, same position of the legs and arms, same lean of the body. No trace of the ghost may remain in the finished drawing.

The mannequin and the ghost show only the pose. Do not copy their proportions, bald head, skin or grey colour. Keep {name}'s own look from the bottom left sprite: proportions, head size, face, hair, headwear, clothing, colours and outline, and the same crisp pixel-art style with hard pixel edges and no anti-aliasing or blur.
Parts that the bottom left sprite does not show should follow on naturally from what it does show.
Keep {name} at the same size as in the bottom left, with the feet on the same ground line, on the plain white background. Do not draw anything outside the red frame and do not change the other three cells.
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
# How the standing prompt describes each direction a standing sprite can be made for
STANDING_VIEWS = {
    'back': 'seen from behind, facing away from the viewer',
    'left': 'seen from the side, facing to the left',
    'right': 'seen from the side, facing to the right',
}

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


def build_sheet(idle, pose, ghost, npc):
    """Lay out the three sprites plus the red-framed target cell holding the ghost.

    Every sprite stands on the ground line of its cell, so the cycle's frame
    keeps the bob of the cycle and the ghost stands where the NPC will.

    Returns:
        (sheet, ghost) - the ghost solid, at the scale of the NPC sprite, which
        is also the scale an accepted frame is saved at.
    """
    # One scale for all chibi sprites, taken from the standing one, so every
    # frame of a cycle comes out the same size.
    factor = max(1, round(npc.get_height() / idle.get_height()))
    sprites = [scaled(idle, factor), scaled(pose, factor), npc]
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

    for sprite, cell in zip(sprites + [ghost], cells):
        sheet.blit(sprite, sprite.get_rect(midbottom=(cell.centerx, cell.bottom - margin)))
    pygame.draw.rect(sheet, TARGET_FRAME_COLOR, cells[3], TARGET_FRAME_WIDTH)
    return sheet, solid_ghost


def prompt_for(npc, direction, frame, count):
    base_view = BASE_POSES[npc.base_for(direction)][1]
    return PROMPT_TEMPLATE.format(base_view=base_view, frame=frame, count=count,
                                  cycle=direction.motion.key, verb=direction.motion.verb,
                                  motion=direction.description, name=npc.display_name)


def write_sheets(npc, direction, frames=None):
    """Build a direction's sheets from the base files and write them.

    Args:
        npc: The WalkNpc.
        direction: The Direction.
        frames: Frame numbers (from 1) to build; None builds them all.

    Returns:
        [FrameSheet], in frame order.

    Raises:
        One of SHEET_ERRORS if a base file is missing or unreadable.
    """
    base = npc.base_for(direction)
    idle = chibi.idle_frame(BASE_POSES[base][0])
    reference = trim(pygame.image.load(str(npc.sprite_path(base))).convert_alpha())
    cycle = chibi.cycle_frames(direction)
    ghosts, auto_ghost = chibi.ghost_frames(direction)
    count = len(cycle)

    npc.out_dir.mkdir(parents=True, exist_ok=True)
    sheets = []
    for frame in frames or range(1, count + 1):
        surface, ghost = build_sheet(idle, cycle[frame - 1], ghosts[min(frame, len(ghosts)) - 1],
                                     reference)
        stem = f'{npc.prefix}_{direction.pose(frame)}'
        path = npc.out_dir / f'{stem}_sheet.png'
        prompt = prompt_for(npc, direction, frame, count)
        pygame.image.save(surface, str(path))
        (npc.out_dir / f'{stem}_prompt.txt').write_text(prompt, encoding='utf-8')
        sheets.append(FrameSheet(direction, frame, count, surface, path, prompt, auto_ghost, ghost))
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
    idle = chibi.idle_frame(BASE_POSES[DEFAULT_BASE][0])
    target = chibi.idle_frame(f'Idle_{direction.strip}', direction.mirror)
    ghost_source, auto_ghost = chibi.idle_ghost(direction)
    reference = trim(pygame.image.load(str(npc.sprite_path(DEFAULT_BASE))).convert_alpha())
    surface, ghost = build_sheet(idle, target, ghost_source, reference)

    npc.out_dir.mkdir(parents=True, exist_ok=True)
    pose = standing_pose(direction)
    stem = f'{npc.prefix}_{pose}'
    path = npc.out_dir / f'{stem}_sheet.png'
    prompt = STANDING_PROMPT_TEMPLATE.format(
        base_view=BASE_POSES[DEFAULT_BASE][1], view=STANDING_VIEWS[direction.key],
        name=npc.display_name)
    pygame.image.save(surface, str(path))
    (npc.out_dir / f'{stem}_prompt.txt').write_text(prompt, encoding='utf-8')
    return FrameSheet(direction, 0, 0, surface, path, prompt, auto_ghost, ghost)


def reference_shapes(npc, pose, base):
    """({pose: path}, {pose: mask}) that make create_new_NPC's extraction scale
    the answer like the NPC's own standing sprite instead of the player."""
    path = npc.sprite_path(base)
    sprite = pygame.image.load(str(path)).convert_alpha()
    mask = shape_mask(pygame.mask.from_surface(sprite), sprite.get_bounding_rect())
    return {pose: path}, {pose: mask}
