"""An NPC's or the player's sprite folder, as the Sprite Manager sees it."""

from collections import namedtuple

from create_new_NPC import CATEGORIES, OTHER, read_profile
from create_new_pose import OUTPUT_DIR, PLAYER_DIR, Npc
from images import crop_alike, load_frame, mirrored
from walk import (
    DIRECTIONS_OF, NPC_DIRECTION_KEYS, NPC_MOTIONS, PLAYER_MOTIONS, STANDING_DIRECTIONS, find_direction,
    game_mirror_source,
    parse_pose, partner_of,
)

# A standing pose a sheet can start from: the chibi's match for it (its idle strip,
# mirrored or not) and how the prompt names it
BasePose = namedtuple('BasePose', 'idle mirror view')
BASE_POSES = {
    'front_static': BasePose('Idle_Down', False, 'facing the viewer'),
    'back_static': BasePose('Idle_Up', False, 'seen from behind'),
    'right_static': BasePose('Idle_Side', False, 'seen from the side, facing to the right'),
    'left_static': BasePose('Idle_Side', True, 'seen from the side, facing to the left'),
}
DEFAULT_BASE = 'front_static'
WALK_FOLDER = 'walk'      # holds the run's output too, for the player
PLAYER_CATEGORY = 'player'


class WalkNpc:
    """An NPC folder, or the player's: its sprites and its walk (and run) output."""

    is_new = False   # has a front standing sprite, unlike a new_figure.NewFigure

    def __init__(self, npc):
        """
        Args:
            npc: A create_new_pose.Npc (a folder with a front standing sprite).
        """
        self.is_player = npc.folder == PLAYER_DIR
        self.motions = PLAYER_MOTIONS if self.is_player else NPC_MOTIONS
        self.folder = npc.folder
        self.name = npc.name
        self.prefix = npc.prefix
        self.base_path = npc.base_path
        first = self.name.split('_', 1)[0]
        # The groups of create_new_NPC.py: 'trader', 'poor', ..., or 'other'
        if self.is_player:
            self.category = PLAYER_CATEGORY
        else:
            self.category = first if first in [key for key, _, _ in CATEGORIES] else OTHER[0]
        self.is_townsperson = self.category not in ('trader', OTHER[0])
        profile = read_profile(self.folder)
        if self.is_player:
            self.display_name = 'the player'
        elif profile.get('name'):
            self.display_name = profile['name']
        elif self.name.startswith('trader_'):
            self.display_name = f'the {self.prefix}'
        else:
            self.display_name = self.prefix.capitalize()

    @property
    def label(self):
        """Card label, as in create_new_NPC.py: the folder for traders, the name for townsfolk."""
        if self.is_player:
            return 'Player'
        return self.display_name if self.is_townsperson else self.name

    def directions(self, motion):
        """The directions of one of the figure's motions: all eight for the player,
        down, right, up and left for an NPC."""
        if self.is_player:
            return DIRECTIONS_OF[motion]
        return tuple(d for d in DIRECTIONS_OF[motion] if d.key in NPC_DIRECTION_KEYS)

    def total_frames(self, counts, motion):
        """How many frames a full set of one of his motions has.

        Args:
            counts: {Direction: frames in its cycle}.
        """
        return sum(counts[d] for d in self.directions(motion))

    def direction_like(self, other):
        """`other` if the figure has it, else the nearest way he does have.

        Another motion becomes his first one; a diagonal he does not walk
        becomes its side (down right -> right).
        """
        motion = other.motion if other.motion in self.motions else self.motions[0]
        keys = [d.key for d in self.directions(motion)]
        key = other.key
        if key not in keys:
            key = 'right' if 'right' in key else 'left' if 'left' in key else keys[0]
        return find_direction(motion, key)

    def parse_pose(self, pose):
        """(Direction, frame) of one of the figure's frames, or (None, 0).

        A standing sprite, 'right_static', is frame 0 of the direction in the
        figure's first motion.
        """
        key, _, rest = pose.rpartition('_')
        if rest == 'static' and key in STANDING_DIRECTIONS:
            return find_direction(self.motions[0], key), 0
        return parse_pose(pose, self.motions)

    def sprite_path(self, pose):
        return self.folder / f'{self.prefix}_{pose}.png'

    def frame_path(self, direction, frame):
        return self.sprite_path(direction.pose(frame))

    def has(self, pose):
        return self.sprite_path(pose).is_file()

    @property
    def out_dir(self):
        """Sheets, prompts, answers and review.json of the walk and run frames."""
        return OUTPUT_DIR / self.name / WALK_FOLDER

    def base_for(self, direction):
        """The standing pose a direction's sheets start from.

        The one facing the same way where the figure has it - the side view
        for left and right, the back view for up and its diagonals - else
        the front one.
        """
        if direction.key in ('left', 'right'):
            side = f'{direction.key}_static'
            if self.has(side):
                return side
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


def player():
    """The player, as a WalkNpc."""
    return WalkNpc(Npc(PLAYER_DIR, 'front_static', 'player'))
