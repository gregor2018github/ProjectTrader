"""The animals of the map: their frames and the sprites of each, on disk.

An animal is a folder assets/map_sprites/figurines/animals/<animal>/, where
the game's animals load their sprites from (src/models/figurines/animals/).
Its frames are seen from the side, all facing left:

    <animal>_left_static.png          standing still
    <animal>_left_move1.png ... 4     the walk
    <animal>_left_eat1.png, 2         grazing, the head down to the grass

Every one is also saved mirrored as <animal>_right_<frame>.png, which is
what the game plays walking right, so only the left-hand ones are made.

An optional animal.json holds the title and a description for the prompts:

    {"title": "Goat", "description": "a nimble brown nanny goat with short horns and a beard"}

The sheep is the base animal, as the chibi is the humans': its frames are
the poses every other animal's frames are drawn in (animal_sheets.py), and
its standing sprite is what a new animal's first sprite is drawn beside.

All of an animal's frames share one canvas, the standing sprite's, since the
game scales each frame's whole canvas to the same width (Animator, legacy
path); a new frame is put on it standing on the standing sprite's ground
line, centred under it.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

import pygame

from images import is_blank, load_frame, mirrored, trim
from sprite_library import MAP_SPRITES
from theme import OUTPUT_DIR

ANIMALS_DIR = MAP_SPRITES / 'figurines' / 'animals'
ANIMAL_FILE = 'animal.json'
ANIMALS_OUTPUT = OUTPUT_DIR / 'animals'
BASE_ANIMAL = 'sheep'
SIDE = 'left'                # the side every frame is made facing
MIRROR_SIDE = 'right'        # saved too, mirrored
NAME_MAX_LENGTH = 20
CANVAS_MARGIN_X = 0.08       # a first sprite's canvas: room for the walk at each side, of its width
CANVAS_MARGIN_TOP = 0.06     # and above it, of its height


@dataclass(frozen=True)
class Pose:
    key: str          # in the file names: static, move1, eat2
    title: str        # 'Walk 1'
    group: str        # 'static', 'move' or 'eat'
    number: int = 0   # within its group, from 1


POSES = (
    Pose('static', 'Standing', 'static'),
    *(Pose(f'move{n}', f'Walk {n}', 'move', n) for n in range(1, 5)),
    *(Pose(f'eat{n}', f'Grazing {n}', 'eat', n) for n in range(1, 3)),
)
STATIC = POSES[0]
GROUPS = (('static', 'Standing'), ('move', 'Walk'), ('eat', 'Grazing'))


def poses_of(group):
    return [p for p in POSES if p.group == group]


def find_pose(key):
    return next((p for p in POSES if p.key == key), None)


class Animal:
    """One animal's folder: its frames and what the prompts say of it."""

    is_player = False

    def __init__(self, folder):
        self.folder = Path(folder)
        data = {}
        try:
            loaded = json.loads((self.folder / ANIMAL_FILE).read_text(encoding='utf-8'))
            data = loaded if isinstance(loaded, dict) else {}
        except (OSError, ValueError):
            pass
        self.title = data.get('title') or self.name.capitalize()
        self.description = data.get('description', '')

    # --- what the app needs of a figure -------------------------------------

    @property
    def name(self):
        """The folder's name, which every file name of the animal starts with."""
        return self.folder.name

    @property
    def prefix(self):
        return self.name

    @property
    def label(self):
        return self.title

    @property
    def out_dir(self):
        """build_tools/output/animals/<animal>: sheets, answers and review.json."""
        return ANIMALS_OUTPUT / self.name

    @property
    def is_base(self):
        return self.name == BASE_ANIMAL

    @property
    def is_new(self):
        """Without a standing sprite yet: that comes first, every other frame is drawn from it."""
        return not self.has(STATIC.key)

    # --- state ----------------------------------------------------------------

    def save(self):
        data = {'title': self.title, 'description': self.description}
        (self.folder / ANIMAL_FILE).write_text(json.dumps(data, indent=1) + '\n', encoding='utf-8')

    def sprite_path(self, pose_key, side=SIDE):
        """assets/map_sprites/figurines/animals/<animal>/<animal>_left_<pose>.png."""
        return self.folder / f'{self.name}_{side}_{pose_key}.png'

    def has(self, pose_key):
        return self.sprite_path(pose_key).is_file()

    def sprite(self, pose_key):
        """The frame, or None while it is not drawn."""
        return load_frame(self.sprite_path(pose_key))

    def done(self, group=None):
        """How many frames there are, of one group or of all."""
        return sum(self.has(p.key) for p in POSES if group in (None, p.group))

    @staticmethod
    def needed(group=None):
        return sum(group in (None, p.group) for p in POSES)

    def thumb_sprite(self):
        """The picture of the animal: its standing sprite, else any frame it has."""
        for pose in POSES:
            sprite = self.sprite(pose.key)
            if not is_blank(sprite):
                return sprite
        return None

    # --- saving a frame -------------------------------------------------------

    def save_frame(self, pose_key, sprite):
        """Put a new frame on the animal's canvas and save it, and its mirror image for the right.

        The canvas is the standing sprite's; the frame stands on its ground
        line, centred under it. A first standing sprite gets a canvas with
        room around it for the walk. A frame too big for the canvas makes it
        bigger, which the other frames then no longer match.

        Returns:
            (path, replaced, grown): the left-hand file, whether it was there
            before, and whether the canvas had to grow.

        Raises:
            pygame.error, OSError: If it cannot be written.
        """
        sprite = trim(sprite)
        w, h = sprite.get_size()
        static = self.sprite(STATIC.key)
        if is_blank(static):
            mx, top = round(w * CANVAS_MARGIN_X), round(h * CANVAS_MARGIN_TOP)
            size = (w + 2 * mx, h + top)
            anchor = (size[0] // 2, size[1])
        else:
            size = static.get_size()
            content = static.get_bounding_rect()
            anchor = (content.centerx, content.bottom)
        rect = sprite.get_rect(midbottom=anchor)
        grow_x = max(0, -rect.x, rect.right - size[0])
        grow_y = max(0, -rect.y)
        grown = bool(grow_x or grow_y)
        canvas = pygame.Surface((size[0] + 2 * grow_x, size[1] + grow_y), pygame.SRCALPHA)
        canvas.fill((0, 0, 0, 0))
        canvas.blit(sprite, rect.move(grow_x, grow_y))
        path = self.sprite_path(pose_key)
        replaced = path.is_file()
        self.folder.mkdir(parents=True, exist_ok=True)
        pygame.image.save(canvas, str(path))
        pygame.image.save(mirrored(canvas), str(self.sprite_path(pose_key, MIRROR_SIDE)))
        return path, replaced, grown


def animal_folder_name(title):
    """The folder (and file name start) for an animal's title: its letters, lower case."""
    return re.sub(r'[^a-z]', '', title.lower())[:NAME_MAX_LENGTH]


def find_animals():
    """Every animal folder, the base animal first, then by name."""
    if not ANIMALS_DIR.is_dir():
        return []
    folders = [f for f in ANIMALS_DIR.iterdir() if f.is_dir() and not f.name.startswith(('.', '_'))]
    folders.sort(key=lambda f: (f.name != BASE_ANIMAL, f.name))
    return [Animal(f) for f in folders]


def base_animal():
    """The sheep, whose frames give the poses; None if its folder is gone."""
    folder = ANIMALS_DIR / BASE_ANIMAL
    return Animal(folder) if folder.is_dir() else None


def create_animal(title, description):
    """Make a new animal's folder with its animal.json; returns the Animal.

    Raises:
        ValueError: If the name has no letters or the folder exists.
        OSError: If it cannot be written.
    """
    name = animal_folder_name(title)
    if not name:
        raise ValueError('The name needs letters.')
    folder = ANIMALS_DIR / name
    if folder.exists():
        raise ValueError(f'There is an animal called {name} already.')
    folder.mkdir(parents=True)
    animal = Animal(folder)
    animal.title = title.strip().capitalize()
    animal.description = description.strip()
    animal.save()
    return animal
