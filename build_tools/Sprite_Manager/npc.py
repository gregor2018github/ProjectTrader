"""An NPC sprite folder, as the Sprite Manager sees it."""

from create_new_NPC import CATEGORIES, OTHER, read_profile
from create_new_pose import OUTPUT_DIR
from images import crop_alike, load_frame, mirrored
from walk import STANDING_DIRECTIONS, game_mirror_source, partner_of

# The NPC's standing pose a sheet starts from: (the chibi's match for it, how the prompt names it)
BASE_POSES = {
    'front_static': ('Idle_Down', 'facing the viewer'),
    'back_static': ('Idle_Up', 'seen from behind'),
}
DEFAULT_BASE = 'front_static'
WALK_FOLDER = 'walk'


class WalkNpc:
    """An NPC folder: its sprites and its walk output."""

    def __init__(self, npc):
        """
        Args:
            npc: A create_new_pose.Npc (a folder with a front standing sprite).
        """
        self.folder = npc.folder
        self.name = npc.name
        self.prefix = npc.prefix
        self.base_path = npc.base_path
        first = self.name.split('_', 1)[0]
        # The groups of create_new_NPC.py: 'trader', 'poor', ..., or 'other'
        self.category = first if first in [key for key, _, _ in CATEGORIES] else OTHER[0]
        self.is_townsperson = self.category not in ('trader', OTHER[0])
        profile = read_profile(self.folder)
        if profile.get('name'):
            self.display_name = profile['name']
        elif self.name.startswith('trader_'):
            self.display_name = f'the {self.prefix}'
        else:
            self.display_name = self.prefix.capitalize()

    @property
    def label(self):
        """Card label, as in create_new_NPC.py: the folder for traders, the name for townsfolk."""
        return self.display_name if self.is_townsperson else self.name

    def sprite_path(self, pose):
        return self.folder / f'{self.prefix}_{pose}.png'

    def frame_path(self, direction, frame):
        return self.sprite_path(direction.pose(frame))

    def has(self, pose):
        return self.sprite_path(pose).is_file()

    @property
    def out_dir(self):
        """Sheets, prompts, answers and review.json of the walk frames."""
        return OUTPUT_DIR / self.name / WALK_FOLDER

    def base_for(self, direction):
        """The standing pose a direction's sheets start from."""
        if direction.from_behind and self.has('back_static'):
            return 'back_static'
        return DEFAULT_BASE

    def done(self, direction, count):
        """How many of the direction's frames the NPC has."""
        return sum(self.frame_path(direction, f).is_file() for f in range(1, count + 1))

    def standing_done(self):
        """How many of the standing sprites (down, up, left, right) the NPC has."""
        return sum(self.has(f'{key}_static') for key in STANDING_DIRECTIONS)

    def mirror_source(self, direction, frame):
        """The partner direction's frame that mirrors to this one, None if it does not exist."""
        partner = partner_of(direction)
        path = self.frame_path(partner, frame) if partner else None
        return path if path and path.is_file() else None

    def game_frames(self, direction, count):
        """(frames, note): the walk as the game plays it, cropped alike.

        For a left-hand direction the NPC has no frames of, that is the
        right-hand walk, mirrored.
        """
        source, mirror = direction, False
        paths = [self.frame_path(direction, f) for f in range(1, count + 1)]
        if not any(p.is_file() for p in paths) and game_mirror_source(direction):
            source, mirror = game_mirror_source(direction), True
            paths = [self.frame_path(source, f) for f in range(1, count + 1)]
        frames = [image for image in map(load_frame, paths) if image]
        if not frames:
            return [], 'no frames yet'
        if mirror:
            frames = [mirrored(f) for f in frames]
        note = f'{len(frames)}/{count} frames'
        if mirror:
            note += f', mirrored from {source.label.lower()} as in the game'
        return crop_alike(frames), note
