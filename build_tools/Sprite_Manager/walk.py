"""The motions (walk, run), their eight directions, how their frames are named,
and which directions mirror which.

Pure data: nothing here loads an image or needs pygame.
"""

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Motion:
    key: str          # 'walk'
    label: str        # 'Walk'
    pose_word: str    # frames are <prefix>_<direction>_<pose_word><n>.png
    folder: str       # base_Chibi/<folder>/<folder>_<strip>_Sheet.png
    verb: str         # how the prompt describes it: 'walking'


# The NPCs only walk: their walk is what the game plays, <prefix>_<direction>_move<n>.png.
WALK = Motion('walk', 'Walk', 'move', 'Walk', 'walking')
# The player only runs in the game, so there it is the run that is player_<direction>_move<n>.png;
# a walk of his, which the game does not load yet, is player_<direction>_walk<n>.png.
PLAYER_WALK = Motion('walk', 'Walk', 'walk', 'Walk', 'walking')
RUN = Motion('run', 'Run', 'move', 'Run', 'running')
MOTIONS = (WALK, PLAYER_WALK, RUN)
NPC_MOTIONS = (WALK,)
PLAYER_MOTIONS = (PLAYER_WALK, RUN)


@dataclass(frozen=True)
class Direction:
    key: str          # the game's name for it: <prefix>_<key>_move<n>.png
    label: str
    strip: str        # the chibi's strip of it: <motion folder>_<strip>_Sheet.png
    mirror: bool      # the chibi was drawn facing the other way
    view: str         # how the prompt describes it, {verb} filled from the motion
    from_behind: bool = False  # starts from the back view if the NPC has one
    motion: Motion = WALK

    def pose(self, frame):
        """'right_move3' for frame 3 of the walk right (counted from 1, like the game)."""
        return f'{self.key}_{self.motion.pose_word}{frame}'

    @property
    def strip_name(self):
        """'Walk_Down_Side'."""
        return f'{self.motion.folder}_{self.strip}'

    @property
    def description(self):
        """How the prompt describes the movement: 'seen from the side, walking to the right'."""
        return self.view.format(verb=self.motion.verb)

    @property
    def title(self):
        """'walk down right', for status lines."""
        return f'{self.motion.key} {self.label.lower()}'


_WALK_DIRECTIONS = (
    Direction('front', 'Down', 'Down', False,
              '{verb} towards the viewer, down the screen'),
    Direction('front_right', 'Down right', 'Down_Side', False,
              'seen three-quarters from the front, {verb} diagonally down and to the right'),
    Direction('right', 'Right', 'Side', False,
              'seen from the side, {verb} to the right'),
    Direction('back_right', 'Up right', 'Up_Side', False,
              'seen three-quarters from behind, {verb} diagonally up and to the right', True),
    Direction('back', 'Up', 'Up', False,
              'seen from behind, {verb} away from the viewer, up the screen', True),
    Direction('back_left', 'Up left', 'Up_Side', True,
              'seen three-quarters from behind, {verb} diagonally up and to the left', True),
    Direction('left', 'Left', 'Side', True,
              'seen from the side, {verb} to the left'),
    Direction('front_left', 'Down left', 'Down_Side', True,
              'seen three-quarters from the front, {verb} diagonally down and to the left'),
)
# {motion: (Direction, ...)}, every motion in the same eight directions
DIRECTIONS_OF = {m: tuple(replace(d, motion=m) for d in _WALK_DIRECTIONS) for m in MOTIONS}
DIRECTIONS = DIRECTIONS_OF[WALK]
ALL_DIRECTIONS = tuple(d for m in MOTIONS for d in DIRECTIONS_OF[m])
_BY_KEY = {(d.motion, d.key): d for d in ALL_DIRECTIONS}
DEFAULT_DIRECTION = _BY_KEY[WALK, 'right']

# Where the game borrows a left-hand walk from when the NPC has none
MIRROR_OF = {'left': 'right', 'front_left': 'front_right', 'back_left': 'back_right'}
# Directions whose frames are each other's mirror image, frame for frame
MIRROR_PARTNER = {**MIRROR_OF, **{right: left for left, right in MIRROR_OF.items()}}
# Directions with a standing sprite, <prefix>_<key>_static.png
STANDING_DIRECTIONS = ('front', 'back', 'left', 'right')


def find_direction(motion, key):
    """The Direction of a motion by its key: find_direction(RUN, 'left')."""
    return _BY_KEY[motion, key]


def standing_pose(direction):
    """'right_static' for the directions an NPC has a standing sprite in, else None.

    The walks down, up, left and right each have one; the diagonals do not.
    """
    return f'{direction.key}_static' if direction.key in STANDING_DIRECTIONS else None


def parse_pose(pose, motions=NPC_MOTIONS):
    """'front_right_move3' -> (Direction, 3), or (None, 0) if it is not a frame of a motion.

    Args:
        pose: The pose name.
        motions: The motions of the figure it belongs to; they tell what
            '_move' stands for.
    """
    for motion in motions:
        key, _, number = pose.rpartition(f'_{motion.pose_word}')
        if (motion, key) in _BY_KEY and number.isdigit():
            return _BY_KEY[motion, key], int(number)
    return None, 0


def is_optional(direction):
    """Left-hand directions: the game mirrors the right-hand ones for an NPC without them."""
    return direction.key in MIRROR_OF


def game_mirror_source(direction):
    """The direction the game mirrors when the NPC lacks this one, or None."""
    key = MIRROR_OF.get(direction.key)
    return _BY_KEY[direction.motion, key] if key else None


def partner_of(direction):
    """The direction whose frames are this one's mirror image, or None."""
    key = MIRROR_PARTNER.get(direction.key)
    return _BY_KEY[direction.motion, key] if key else None


def suggested_sources(direction, frame, count):
    """[(direction, frame)] most likely to be this frame mirrored; frame 0 is the standing sprite.

    The partner direction's frame of the same number is the same step seen
    from the other side. A walk seen from the front or the back repeats
    itself mirrored after half a cycle, the other foot forward.
    """
    partner = partner_of(direction)
    if frame == 0:  # a standing sprite: only the partner's is the same, mirrored
        return [(partner, 0)] if partner else []
    suggestions = []
    if partner:
        suggestions.append((partner, frame))
    elif count % 2 == 0:
        suggestions.append((direction, (frame - 1 + count // 2) % count + 1))
    return suggestions
