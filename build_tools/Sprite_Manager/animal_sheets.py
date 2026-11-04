"""An animal's frame: its split image and prompt, and cutting the answer out.

A walk or grazing frame is drawn on a 2x2 sheet, as a human's walk frame is
drawn on the chibi's (sheets.py), with the sheep in the chibi's place:

    +---------------------------+---------------------------+
    | the sheep standing        | the sheep in the pose     |
    +---------------------------+---------------------------+
    | the animal standing       | red frame: the sheep's    |
    | (<animal>_left_static)    | pose as a faint grey      |
    |                           | ghost, the animal's size  |
    +---------------------------+---------------------------+

The animal's standing sprite comes first, on a split image beside the sheep
standing, the red frame empty:

    +---------------------------+---------------------------+
    | the sheep standing        | red frame: draw the new   |
    |                           | animal here               |
    +---------------------------+---------------------------+

Every sprite is trimmed and stands on its cell's ground line, centred. The
answer is cut out as a new plant's is (sprite_extraction.py): the red frame
is cut off the target cell's edges and the sprite scaled by what brings the
bottom left sprite (the sheep, for a standing sprite) back to its real size,
so a new animal keeps the size the model gave it beside the sheep.
"""

from dataclasses import dataclass
from pathlib import Path

import pygame

from animals import STATIC, base_animal, find_pose
from images import trim
from sheets import FRAME_COLOR, FRAME_WIDTH, GHOST_ALPHA, MARGIN_RATIO, MIN_MARGIN, TARGET_FRAME_COLOR, \
    TARGET_FRAME_WIDTH
from sprite_extraction import SpriteResult

GRID_LAYOUT = '2x2'
PAIR_LAYOUT = '1x2'
GHOST_LIGHTEN = (40, 40, 40)   # added to the greyed pose, so it reads as a faint guide
DONE_COLOR = (80, 180, 90)     # the target frame once its sprite is accepted (cards only)

POSE_WORDS = {
    'move': 'in step {n} of its walk, walking to the left',
    'eat': 'grazing, its head lowered to the grass (frame {n} of the grazing)',
}

FRAME_PROMPT = """\
The attached picture is a 2x2 grid of pixel-art sprites for my medieval trading game "Merchant's Rise", every animal seen from the side, facing left.

Top left: a sheep standing still. Top right: the same sheep {pose}.
Bottom left: {bottom_left}.
Bottom right, in the red frame: a faint grey copy of the sheep from top right, scaled to {name_short}'s size. It only shows the pose.

Draw {name_short} in the red frame in exactly that pose. Each leg, hoof or foot, the head, neck and tail go where the grey sheep has them, at the same height and angle, as far as {name_short}'s own build allows. Do not make up a pose of your own, and do not copy the standing pose from the bottom left.

Keep {name_short}'s look from the bottom left: build, proportions, head, coat, colours and outline, and the same crisp pixel art with hard pixel edges. The same size, standing on the same ground line, facing left, on the plain white background, with nothing of the grey sheep left. Change nothing outside the red frame.
"""


FIRST_PROMPT = """\
The attached picture is a split view for my medieval trading game "Merchant's Rise". The left cell shows a sheep from the game: a pixel-art sprite seen from the side, standing still and facing left.

Draw {name}{about} in the red frame in the right cell, standing still on all its legs, seen from the side and facing left, just like the sheep.
- Size: as big beside the sheep as a real {title} is beside a real sheep, standing on the same ground line.
- Copy the sheep's art style exactly: the same size of pixels (not finer), the same dark outline, the same way of shading with few shades per colour, the same amount of detail, the same viewing angle and the same light from the same side.
- Plain white background. No ground, shadow or grass: only the animal.

Draw nothing outside the red frame and leave the left cell exactly as it is. Output the full split image.
"""


def with_article(title):
    word = title.lower()
    return f'{"an" if word[:1] in "aeiou" else "a"} {word}'


@dataclass
class AnimalSheet:
    """One frame's split image and prompt, shaped like a sheets.FrameSheet for the API and the answers."""

    animal: object
    frame: object            # animals.Pose
    surface: pygame.Surface
    path: Path
    prompt: str
    layout: str
    sketched: bool = True    # nothing to sketch: every sheet is ready to send

    @property
    def pose(self):
        return self.frame.key

    @property
    def name(self):
        return self.frame.title


def ghost_of(sprite, height):
    """The sprite greyed, lightened and scaled to `height`, as a faint guide."""
    w, h = sprite.get_size()
    ghost = pygame.transform.smoothscale(sprite, (max(1, round(w * height / h)), max(1, height)))
    ghost = pygame.transform.grayscale(ghost)
    ghost.fill(GHOST_LIGHTEN + (0,), special_flags=pygame.BLEND_RGBA_ADD)
    ghost.set_alpha(GHOST_ALPHA)
    return ghost


def lay_out(sprites, rows):
    """A sheet of 2 x `rows` cells, each sprite standing on its cell's ground line; (sheet, cells)."""
    max_w = max(s.get_width() for s in sprites)
    max_h = max(s.get_height() for s in sprites)
    margin = max(MIN_MARGIN, int(max(max_w, max_h) * MARGIN_RATIO))
    cell_w, cell_h = max_w + 2 * margin, max_h + 2 * margin
    sheet = pygame.Surface((2 * cell_w + 3 * FRAME_WIDTH, rows * cell_h + (rows + 1) * FRAME_WIDTH))
    sheet.fill(FRAME_COLOR)
    cells = []
    for row in range(rows):
        for col in range(2):
            rect = pygame.Rect(FRAME_WIDTH + col * (cell_w + FRAME_WIDTH),
                               FRAME_WIDTH + row * (cell_h + FRAME_WIDTH), cell_w, cell_h)
            sheet.fill((255, 255, 255), rect)
            cells.append(rect)
    for sprite, cell in zip(sprites, cells):
        sheet.blit(sprite, sprite.get_rect(midbottom=(cell.centerx, cell.bottom - margin)))
    pygame.draw.rect(sheet, TARGET_FRAME_COLOR, cells[-1], TARGET_FRAME_WIDTH)
    return sheet, cells


def _load(animal, pose_key):
    """The frame trimmed; raises OSError if it is not there."""
    sprite = animal.sprite(pose_key)
    if sprite is None or not sprite.get_bounding_rect().w:
        raise OSError(f'{animal.sprite_path(pose_key).name} is missing')
    return trim(sprite)


def can_draw(animal, pose):
    """(possible, why not): a frame needs the sheep's frame of that pose and the animal's standing sprite."""
    base = base_animal()
    if base is None or not base.has(STATIC.key):
        return False, 'the sheep\'s standing sprite is missing'
    if pose.key != STATIC.key:
        if animal.is_new:
            return False, 'make its standing sprite first'
        if not base.has(pose.key):
            return False, f'the sheep has no {pose.title.lower()} to take the pose from'
    return True, ''


def animal_sheet(animal, pose, write=False):
    """The AnimalSheet of a frame; written to disk with its prompt if `write`.

    Raises:
        pygame.error, OSError: If a sprite is missing or it cannot be written.
    """
    base = base_animal()
    if base is None:
        raise OSError('the sheep\'s folder is missing')
    sheep = _load(base, STATIC.key)
    title = animal.title.lower()
    about = f' ({animal.description})' if animal.description else ''
    if pose.key == STATIC.key:
        target = pygame.Surface(sheep.get_size(), pygame.SRCALPHA)
        target.fill((0, 0, 0, 0))
        surface, _ = lay_out([sheep, target], 1)
        layout = PAIR_LAYOUT
        prompt = FIRST_PROMPT.format(name=with_article(title), about=about, title=title)
    else:
        standing = _load(animal, STATIC.key)
        posed = _load(base, pose.key)
        ghost = ghost_of(posed, round(posed.get_height() * standing.get_height() / sheep.get_height()))
        surface, _ = lay_out([sheep, posed, standing, ghost], 2)
        layout = GRID_LAYOUT
        if animal.is_base:
            name_short, bottom_left = 'the sheep', 'the same sheep again, standing still'
        else:
            name_short = f'the {title}'
            bottom_left = f'{with_article(title)}{about}, standing still like the sheep top left'
        prompt = FRAME_PROMPT.format(pose=POSE_WORDS[pose.group].format(n=pose.number), bottom_left=bottom_left,
                                     name_short=name_short)
    path = animal.out_dir / f'{animal.prefix}_{pose.key}_sheet.png'
    if write:
        animal.out_dir.mkdir(parents=True, exist_ok=True)
        pygame.image.save(surface, str(path))
        path.with_suffix('.txt').write_text(prompt, encoding='utf-8')
    return AnimalSheet(animal, pose, surface, path, prompt, layout)


def example_for(animal, pose_key):
    """The sprite in the answer's bottom left, at its real size, which the new one is scaled against.

    Raises:
        pygame.error, OSError: If it is missing.
    """
    if pose_key == STATIC.key:
        base = base_animal()
        if base is None:
            raise OSError('the sheep\'s folder is missing')
        return _load(base, STATIC.key)
    return _load(animal, STATIC.key)


class AnimalDetail:
    """One answer and the frame accepting it would make."""

    def __init__(self, animal, entry):
        """
        Raises:
            pygame.error, OSError: If the answer's image cannot be read.
        """
        self.animal = animal
        self.entry = entry
        self.path = animal.out_dir / entry.image
        image = pygame.image.load(str(self.path))
        entry.width, entry.height = image.get_size()
        self.reference = None
        self.result = None
        self.error = ''
        pose = find_pose(entry.pose)
        try:
            if pose is None:
                raise ValueError(f'{entry.pose} is not a frame of an animal')
            self.reference = example_for(animal, pose.key)
            layout = PAIR_LAYOUT if pose.key == STATIC.key else GRID_LAYOUT
            self.result = SpriteResult(self.path, self.reference, layout)
        except Exception as exc:  # a sprite gone, or cell detection and extraction failing
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
