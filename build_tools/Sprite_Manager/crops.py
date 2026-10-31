"""The crops of the fields: their growth stages and the sprites of each, on disk.

A crop is a folder assets/map_sprites/fields/<crop>/ holding a crop.json and
its sprites, so adding a crop is adding the folder (create_crop()):

    {"title": "Wheat",
     "description": "tall stalks of wheat with golden ears",   # for the prompt
     "variants": 4,                                            # sprites per stage
     "stages": [{"key": "bare", "title": "Ploughed", "description": "...", "height": 0.0},
                {"key": "sprouts", ...}, ..., {"key": "ripe", ...}]}

The stages run from the bare field to the ripe crop, at least MIN_STAGES of
them. The first one, the ploughed field, has no sprites: its furrows are
ground tiles (build_tools/Field_Plougher). Every other stage has `variants`
sprites, <crop>_<stage key>_<n>.png, scattered at random over the field's
tiles as the game draws the ripe ones now (src/models/field.py). A stage's
height is the share of the ripe plant's height it grows to; its sheet draws
the line the new sprite reaches up to from it. Stages can be added between
the others and taken out again; a stage's key is fixed when it is made, so
renaming one does not rename its files.

Like the walk frames, every stage sprite is drawn from another: the
reference_for() a stage and variant is the nearest sprite of the same plant
(the same variant) at a later stage, else at an earlier one, else another
variant, else another crop's ripe one, which is how a new crop starts.
"""

import json
import re
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from images import load_frame
from sprite_library import MAP_SPRITES
from theme import OUTPUT_DIR

CROPS_DIR = MAP_SPRITES / 'fields'
CROP_FILE = 'crop.json'
CROPS_OUTPUT = OUTPUT_DIR / 'crops'
REMOVED = 'removed'          # under a crop's output: the sprites of stages and variants taken out

MIN_STAGES = 4               # the bare field, two stages of growth and the ripe crop
DEFAULT_VARIANTS = 4
MAX_VARIANTS = 8
BARE = 'bare'                # the first stage's key: the ploughed field, ground tiles only
NAME_MAX_LENGTH = 20


@dataclass
class Stage:
    key: str              # in the file names, never changed
    title: str            # 'Sprouting', for the tool and the prompt
    description: str      # what the plant looks like at this stage, for the prompt
    height: float         # share of the ripe plant's height

    @property
    def bare(self):
        return self.key == BARE


def default_stages(ripe='fully grown and ripe, ready for the harvest'):
    """A new crop's stages: the bare field, three stages of growth and the ripe crop."""
    return [
        Stage(BARE, 'Ploughed', 'the bare ploughed field, nothing sown yet', 0.0),
        Stage('sprouts', 'Sprouting', 'a few tiny green tips just broken through the soil, short and sparse', 0.12),
        Stage('young', 'Young', 'a low tuft of fresh green leaves and blades', 0.35),
        Stage('growing', 'Growing', 'tall green stalks, nearly full height, the ears or heads forming but '
                                    'still green', 0.75),
        Stage('ripe', 'Ripe', ripe, 1.0),
    ]


@dataclass
class Reference:
    """The sprite a stage sprite is drawn from."""

    crop: 'Crop'
    stage: Stage
    variant: int

    @property
    def path(self):
        return self.crop.sprite_path(self.stage.key, self.variant)


class Crop:
    """One crop's folder: its stages, variants and sprites."""

    is_new = False
    is_player = False

    def __init__(self, folder):
        """
        Raises:
            OSError, ValueError, KeyError, TypeError: If crop.json cannot be read.
        """
        self.folder = Path(folder)
        data = json.loads((self.folder / CROP_FILE).read_text(encoding='utf-8'))
        self.title = data.get('title') or self.name.capitalize()
        self.description = data.get('description', '')
        self.variants = max(1, int(data.get('variants', DEFAULT_VARIANTS)))
        self.stages = [Stage(s['key'], s.get('title', s['key']), s.get('description', ''),
                             float(s.get('height', 1.0))) for s in data['stages']]

    # --- what the app needs of a figure -------------------------------------

    @property
    def name(self):
        """The folder's name, which every file name of the crop starts with."""
        return self.folder.name

    @property
    def prefix(self):
        return self.name

    @property
    def label(self):
        return self.title

    @property
    def out_dir(self):
        """build_tools/output/crops/<crop>: sheets, answers and review.json."""
        return CROPS_OUTPUT / self.name

    # --- state ----------------------------------------------------------------

    def save(self):
        data = {'title': self.title, 'description': self.description, 'variants': self.variants,
                'stages': [asdict(s) for s in self.stages]}
        (self.folder / CROP_FILE).write_text(json.dumps(data, indent=1) + '\n', encoding='utf-8')

    @property
    def growing(self):
        """The stages with sprites: all but the bare field."""
        return [s for s in self.stages if not s.bare]

    @property
    def ripe(self):
        return self.stages[-1]

    def stage(self, key):
        return next((s for s in self.stages if s.key == key), None)

    def sprite_path(self, stage_key, variant):
        """assets/map_sprites/fields/<crop>/<crop>_<stage>_<n>.png."""
        return self.folder / f'{self.name}_{stage_key}_{variant}.png'

    @staticmethod
    def pose(stage_key, variant):
        """What the answers for a stage sprite are booked under: 'sprouts_2'."""
        return f'{stage_key}_{variant}'

    def has(self, stage_key, variant):
        return self.sprite_path(stage_key, variant).is_file()

    def sprite(self, stage_key, variant):
        """The stage sprite, or None while it is not drawn."""
        return load_frame(self.sprite_path(stage_key, variant))

    def done(self, stage=None):
        """How many stage sprites there are, of one stage or of all."""
        stages = [stage] if stage else self.growing
        return sum(self.has(s.key, v) for s in stages for v in range(1, self.variants + 1))

    def needed(self, stage=None):
        return self.variants * (1 if stage else len(self.growing))

    def thumb_sprite(self):
        """The picture of the crop: its ripe first variant, else the latest stage sprite it has."""
        for stage in reversed(self.growing):
            for variant in range(1, self.variants + 1):
                sprite = self.sprite(stage.key, variant)
                if sprite is not None:
                    return sprite
        return None

    # --- changing the stages and variants -------------------------------------

    def can_add_stage_after(self, index):
        """A stage goes between two others: after any but the ripe one."""
        return 0 <= index < len(self.stages) - 1

    def add_stage_after(self, index):
        """A new stage between the one at `index` and the next, halfway in height; returns its index."""
        before, after = self.stages[index], self.stages[index + 1]
        number = 1
        while self.stage(f'stage{number}'):
            number += 1
        stage = Stage(f'stage{number}', f'Stage {number}', '', round((before.height + after.height) / 2, 2))
        self.stages.insert(index + 1, stage)
        self.save()
        return index + 1

    def can_remove_stage(self, index):
        """Neither the bare field nor the ripe crop, and never fewer than MIN_STAGES."""
        return 0 < index < len(self.stages) - 1 and len(self.stages) > MIN_STAGES

    def remove_stage(self, index):
        """Take a stage out; its sprites are moved to the output's removed/ folder, not deleted.

        Returns:
            How many sprites were moved.
        """
        stage = self.stages.pop(index)
        moved = self._put_away([self.sprite_path(stage.key, v) for v in range(1, self.variants + 1)])
        self.save()
        return moved

    def set_variants(self, count):
        """Grow or shrink the variants per stage; the sprites of those dropped are moved away.

        Returns:
            How many sprites were moved.
        """
        count = max(1, min(MAX_VARIANTS, count))
        dropped = [self.sprite_path(s.key, v) for s in self.growing for v in range(count + 1, self.variants + 1)]
        self.variants = count
        moved = self._put_away(dropped)
        self.save()
        return moved

    def _put_away(self, paths):
        """Move sprites to <output>/removed/, stamped, so nothing is lost."""
        moved = 0
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        for path in paths:
            if path.is_file():
                target = self.out_dir / REMOVED / f'{path.stem}_{stamp}{path.suffix}'
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(path), str(target))
                moved += 1
        return moved

    # --- what a stage sprite is drawn from ------------------------------------

    def reference_for(self, stage_index, variant, others=()):
        """The Reference a stage sprite is drawn from, or None if there is nothing to draw it from.

        The same plant later in its growth, else earlier; else another variant
        of the same stage; else another variant of the nearest stage; else
        the ripe sprite of one of `others`, the other crops.
        """
        stages = self.stages
        later = stages[stage_index + 1:]
        earlier = [s for s in reversed(stages[1:stage_index])]
        for stage in later + earlier:
            if self.has(stage.key, variant):
                return Reference(self, stage, variant)
        nearest = sorted(range(1, len(stages)), key=lambda i: (abs(i - stage_index), -i))
        for index in nearest:
            for other in range(1, self.variants + 1):
                if other != variant and self.has(stages[index].key, other):
                    return Reference(self, stages[index], other)
        for crop in others:
            if crop.name != self.name and crop.has(crop.ripe.key, 1):
                return Reference(crop, crop.ripe, 1)
        return None


def crop_folder_name(title):
    """The folder (and file name start) for a crop's title: its letters, lower case."""
    return re.sub(r'[^a-z]', '', title.lower())[:NAME_MAX_LENGTH]


def find_crops():
    """Every crop with a crop.json, by title; a broken one is skipped."""
    crops = []
    if CROPS_DIR.is_dir():
        for folder in sorted(CROPS_DIR.iterdir()):
            if (folder / CROP_FILE).is_file():
                try:
                    crops.append(Crop(folder))
                except (OSError, ValueError, KeyError, TypeError):
                    continue
    return crops


def create_crop(title, description):
    """Make a new crop's folder with the default stages; returns the Crop.

    Raises:
        ValueError: If the name has no letters or the folder exists.
        OSError: If it cannot be written.
    """
    name = crop_folder_name(title)
    if not name:
        raise ValueError('The name needs letters.')
    folder = CROPS_DIR / name
    if folder.exists():
        raise ValueError(f'There is a crop called {name} already.')
    folder.mkdir(parents=True)
    data = {'title': title.strip().capitalize(), 'description': description.strip(), 'variants': DEFAULT_VARIANTS,
            'stages': [asdict(s) for s in default_stages()]}
    (folder / CROP_FILE).write_text(json.dumps(data, indent=1) + '\n', encoding='utf-8')
    return Crop(folder)
