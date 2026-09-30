"""The eight walk directions, how their frames are named, and which mirror which.

Pure data: nothing here loads an image or needs pygame.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Direction:
    key: str          # the game's name for it: <prefix>_<key>_move<n>.png
    label: str
    strip: str        # Walk_<strip>_Sheet.png
    mirror: bool      # the chibi was drawn facing the other way
    motion: str       # how the prompt describes the walk
    from_behind: bool = False  # starts from the back view if the NPC has one

    def pose(self, frame):
        """'right_move3' for frame 3 (counted from 1, like the game)."""
        return f'{self.key}_move{frame}'


DIRECTIONS = (
    Direction('front', 'Down', 'Walk_Down', False,
              'walking towards the viewer, down the screen'),
    Direction('front_right', 'Down right', 'Walk_Down_Side', False,
              'seen three-quarters from the front, walking diagonally down and to the right'),
    Direction('right', 'Right', 'Walk_Side', False,
              'seen from the side, walking to the right'),
    Direction('back_right', 'Up right', 'Walk_Up_Side', False,
              'seen three-quarters from behind, walking diagonally up and to the right', True),
    Direction('back', 'Up', 'Walk_Up', False,
              'seen from behind, walking away from the viewer, up the screen', True),
    Direction('back_left', 'Up left', 'Walk_Up_Side', True,
              'seen three-quarters from behind, walking diagonally up and to the left', True),
    Direction('left', 'Left', 'Walk_Side', True,
              'seen from the side, walking to the left'),
    Direction('front_left', 'Down left', 'Walk_Down_Side', True,
              'seen three-quarters from the front, walking diagonally down and to the left'),
)
DIRECTION_BY_KEY = {d.key: d for d in DIRECTIONS}
DEFAULT_DIRECTION = DIRECTION_BY_KEY['right']

# Where the game borrows a left-hand walk from when the NPC has none
MIRROR_OF = {'left': 'right', 'front_left': 'front_right', 'back_left': 'back_right'}
# Directions whose frames are each other's mirror image, frame for frame
MIRROR_PARTNER = {**MIRROR_OF, **{right: left for left, right in MIRROR_OF.items()}}


def parse_pose(pose):
    """'front_right_move3' -> (Direction, 3), or (None, 0) if it is not a walk frame."""
    key, _, number = pose.rpartition('_move')
    if key in DIRECTION_BY_KEY and number.isdigit():
        return DIRECTION_BY_KEY[key], int(number)
    return None, 0


def is_optional(direction):
    """Left-hand walks: the game mirrors the right-hand ones for an NPC without them."""
    return direction.key in MIRROR_OF


def game_mirror_source(direction):
    """The direction the game mirrors when the NPC lacks this one, or None."""
    key = MIRROR_OF.get(direction.key)
    return DIRECTION_BY_KEY[key] if key else None


def partner_of(direction):
    """The direction whose frames are this one's mirror image, or None."""
    key = MIRROR_PARTNER.get(direction.key)
    return DIRECTION_BY_KEY[key] if key else None


def suggested_sources(direction, frame, count):
    """[(direction, frame)] most likely to be this frame mirrored.

    The partner direction's frame of the same number is the same step seen
    from the other side. A walk seen from the front or the back repeats
    itself mirrored after half a cycle, the other foot forward.
    """
    suggestions = []
    partner = partner_of(direction)
    if partner:
        suggestions.append((partner, frame))
    elif count % 2 == 0:
        suggestions.append((direction, (frame - 1 + count // 2) % count + 1))
    return suggestions
