"""The sprite folders of the townsfolk, traders and the player, and adding a new one.

Folders in humans/npcs are grouped by their name: trader_<trade> for traders,
<class>_<name> for townsfolk, e.g. poor_matilda (class: poor, commons,
middling, nobility). A townsperson's folder holds an npc.json with name and
gender, which is what puts them on the street; a trader needs none, he is put
in town by his own Trader subclass.
"""

import json

from medieval_names import gender_of
from theme import NPC_DIR, PLAYER_DIR

# NPC groups: (folder name start, title, can add new ones)
CATEGORIES = (
    ('trader', 'Traders', True),
    ('poor', 'Poor', True),
    ('commons', 'Commons', True),
    ('middling', 'Middling Sort', True),
    ('nobility', 'Nobility', True),
)
OTHER = ('other', 'Other folders', False)
GENDERS = (('female', 'Woman'), ('male', 'Man'))
TRADER_CATEGORY = 'trader'
PROFILE_FILE = 'npc.json'   # name and gender of a townsperson, in their folder

# Standing poses a figure can be recognised by, in order of preference
STANDING_POSES = ('front_static', 'left_static', 'right_static', 'back_static')
FRONT_POSE = 'front_static'


def find_base(folder, poses=STANDING_POSES):
    """Return (pose, prefix) of the folder's first standing sprite, or None.

    'vintner_front_static.png' -> ('front_static', 'vintner')
    """
    for pose in poses:
        matches = sorted(folder.glob(f'*_{pose}.png'))
        if matches:
            return pose, matches[0].stem[:-len(pose) - 1]
    return None


def read_profile(folder):
    try:
        return json.loads((folder / PROFILE_FILE).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


class FigureFolder:
    """One sprite folder, with or without sprites in it yet."""

    def __init__(self, folder):
        self.folder = folder
        self.name = folder.name
        first = folder.name.split('_', 1)[0]
        keys = [key for key, _, _ in CATEGORIES]
        self.category = first if first in keys else OTHER[0]
        self.is_townsperson = self.category not in (TRADER_CATEGORY, OTHER[0])
        base = find_base(folder)
        # No sprite yet: 'trader_vintner' -> 'vintner', 'poor_matilda' -> 'matilda'
        self.prefix = base[1] if base else folder.name.rsplit('_', 1)[-1]

        self.display_name = self.prefix.capitalize()
        self.gender = None
        if self.is_townsperson:
            profile = read_profile(folder)
            self.display_name = profile.get('name', self.display_name)
            self.gender = profile.get('gender') or gender_of(self.prefix)

    @property
    def label(self):
        """Card label: the folder for traders, the name for townsfolk."""
        return self.display_name if self.is_townsperson else self.name

    @property
    def base_path(self):
        """First standing sprite, the front one if there is one; None if there is none."""
        base = find_base(self.folder)
        return self.sprite_path(base[0]) if base else None

    def sprite_path(self, pose):
        return self.folder / f'{self.prefix}_{pose}.png'

    def has_front(self):
        return self.sprite_path(FRONT_POSE).is_file()


def find_figure_folders():
    """Every folder in humans/npcs."""
    return [FigureFolder(p) for p in sorted(NPC_DIR.iterdir()) if p.is_dir()]


def player_folder():
    return FigureFolder(PLAYER_DIR)


def find_player_poses():
    """Return {pose: path}, e.g. {'front_move1': .../player_front_move1.png}."""
    return {path.stem[len('player_'):]: path for path in sorted(PLAYER_DIR.glob('player_*.png'))}


def taken_names(folders, is_trader):
    """{lower-case name: folder name} a new NPC's name must not clash with.

    A trade clashes with the other trades, a name with the other people.
    """
    return {f.prefix.lower(): f.name for f in folders
            if f.is_townsperson != is_trader and f.category != OTHER[0]}


def create_npc_folder(category, name, gender=None):
    """Make the folder of a new NPC, as NewNpcDialog asked for it.

    Only townsfolk are discovered by their folder, and only they need a
    profile; a trader is put in town by his Trader subclass instead.

    Returns:
        The new folder.
    """
    folder = NPC_DIR / f'{category}_{name.lower()}'
    folder.mkdir()
    if category != TRADER_CATEGORY:
        profile = {'name': name.capitalize(), 'gender': gender}
        (folder / PROFILE_FILE).write_text(json.dumps(profile, indent=2) + '\n', encoding='utf-8')
    return folder
