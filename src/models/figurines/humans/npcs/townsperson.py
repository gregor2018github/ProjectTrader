"""An ordinary townsperson, who does nothing all day but go for a walk.

Unlike a trader, a townsperson has no stall, no round and no drawn path. They
live behind one of the front doors on the Tiled "Doors" layer, and when
:class:`~....town_life.StreetLife` picks them they step out of it, walk across
town to another door -- stopping to look at something now and then -- and
disappear inside. Whichever door that was is where they live from then on, so
the next time they come out, they come out of it.

Knocking on the house they are in may also bring them to the door: they open
it, stand on the doorstep a moment and go back in.

There is one class for all of them: who they are comes from their sprite
folder, ``npcs/<class>_<name>/``, and the ``npc.json`` inside it. Adding a
townsperson is a matter of adding the folder, nothing more.
"""

import datetime
import json
import os
import random
from typing import TYPE_CHECKING, List, Optional, Sequence, Tuple

from .....config.constants import KNOCK_ANSWER_SECONDS
from ...patrol_path import PatrolPath
from .npc import NPC, NPC_SPRITE_ROOT

if TYPE_CHECKING:
    from ....door import Door

#: Walking speed in pixels per second at tile_size 32, before each person's own
#: variation. Above the traders' 35 -- someone crossing town walks with more
#: purpose than someone minding a stall -- but well under the player's 120.
STROLL_SPEED = 52.0

#: How much faster or slower than :data:`STROLL_SPEED` one person may be, as a
#: fraction. Rolled once, when they are created, so each of them keeps a pace
#: of their own.
SPEED_VARIATION = 0.18

#: How far a walker gets, in world pixels, between two chances to stop and
#: look at something.
PAUSE_GAP_MIN = 140.0
PAUSE_GAP_MAX = 520.0

#: How long the fade at a doorway takes, in real seconds. It runs with the
#: walker standing still at the door, facing it, rather than over a stretch of
#: walking: they come to a stop at the entry and only then fade, which reads as
#: a door opening and closing instead of someone dissolving on the move.
DOORWAY_FADE_SECONDS = 0.9

#: How long such a stop lasts, in real seconds.
PAUSE_SECONDS_MIN = 1.5
PAUSE_SECONDS_MAX = 6.0

#: How long someone stays in after an outing before they feel like another
#: one, in real seconds. The spread keeps the same few faces from taking turn
#: after turn while the rest of the town never comes out.
REST_SECONDS_MIN = 20.0
REST_SECONDS_MAX = 180.0

#: Folder-name prefix to social class, for the classes in NPC.SOCIAL_CLASSES.
CLASS_BY_FOLDER_PREFIX = {
    "poor": "Poor",
    "commons": "Commons",
    "middling": "Middling Sort",
    "nobility": "Nobility",
}

#: Filename holding a townsperson's name and gender, in their sprite folder.
PROFILE_FILE = "npc.json"

# Where a townsperson is in their outing. STEPPING_OUT, ANSWERING and GOING_IN
# are all spent standing at a door while the fade runs.
AT_HOME = "Indoors"
STEPPING_OUT = "Stepping outside"
STROLLING = "Walking through town"
PAUSED = "Stopped to look"
GOING_IN = "Going indoors"

# Answering a knock: the same door, out and straight back in again. The fade at
# the start is a doorway fade like any other; the three after it are a walk out
# to the doorstep, a wait there, and the walk back.
ANSWERING = "Opening the door"
STEPPING_UP = "Coming to the door"
AT_THE_DOOR = "Standing in the doorway"
TURNING_IN = "Going back inside"

#: The states of answering a knock that are walked or waited rather than faded.
ANSWERING_STATES = (STEPPING_UP, AT_THE_DOOR, TURNING_IN)


def discover_townsfolk(tile_size: int) -> List['Townsperson']:
    """Create one townsperson per sprite folder that holds an ``npc.json``.

    Trader folders have no profile file, so they are passed over here and
    placed from the Tiled "Movements" layer instead.

    Args:
        tile_size: Base tile size for scaling.

    Returns:
        List: Everyone the artwork tree knows about, in folder order.
    """
    townsfolk: List['Townsperson'] = []
    if not os.path.isdir(NPC_SPRITE_ROOT):
        return townsfolk
    for folder in sorted(os.listdir(NPC_SPRITE_ROOT)):
        profile_path = os.path.join(NPC_SPRITE_ROOT, folder, PROFILE_FILE)
        if not os.path.isfile(profile_path):
            continue
        try:
            with open(profile_path, encoding="utf-8") as handle:
                profile = json.load(handle)
        except (OSError, ValueError) as error:
            print(f"Skipping townsperson {folder}: {error}")
            continue
        name = profile.get("name") or folder
        townsfolk.append(Townsperson(folder, name, tile_size))
    return townsfolk


class Townsperson(NPC):
    """A townsperson who walks from one front door to another."""

    def __init__(self, folder: str, name: str, tile_size: int) -> None:
        """Create a townsperson from their sprite folder.

        They start indoors and out of sight; :class:`StreetLife` gives them a
        door to live behind and sends them out when it wants them.

        Args:
            folder: Their folder under ``NPC_SPRITE_ROOT``, e.g.
                ``"commons_avice"``. Its prefix gives their social class.
            name: Display name, from their ``npc.json``.
            tile_size: Base tile size for scaling.
        """
        super().__init__(name, 0.0, 0.0, tile_size)
        # Instance attributes shadowing the class ones NPC reads: every
        # townsperson is the same class, told apart only by their folder.
        self.SPRITE_FOLDER = folder
        self.SPRITE_PREFIX = folder.split("_", 1)[-1]
        self.SOCIAL_CLASS = CLASS_BY_FOLDER_PREFIX.get(
            folder.split("_", 1)[0], NPC.SOCIAL_CLASS
        )

        self.speed = (
            STROLL_SPEED
            * random.uniform(1.0 - SPEED_VARIATION, 1.0 + SPEED_VARIATION)
            * tile_size / 32.0
        )
        self._init_human_animator(
            sprite_dir=self.sprite_dir,
            sprite_definitions=self._sprite_definitions(),
            fallback_static=self._fallback_static(),
            normalize=True,
        )

        #: The door they are behind, or last went into. Set by StreetLife.
        self.home_door: Optional['Door'] = None
        #: Where they are headed while out; None when indoors.
        self.target_door: Optional['Door'] = None

        self.state: str = AT_HOME
        self.opacity = 0.0

        # Next stop-and-look, as a distance along the outing, and how much of
        # it is left to stand through, in real seconds.
        self._next_pause_distance: float = 0.0
        self._pause_left: float = 0.0
        #: Real seconds they still want to spend indoors before going out again.
        self.rest_left: float = 0.0
        #: Real seconds left standing in the doorway after answering a knock.
        self._answer_left: float = 0.0

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_out(self) -> bool:
        """Whether they are out on the streets rather than indoors."""
        return self.state != AT_HOME

    @property
    def is_available(self) -> bool:
        """Whether they are in, rested, and could be sent out again."""
        return self.state == AT_HOME and self.rest_left <= 0.0 and self.home_door is not None

    # ------------------------------------------------------------------
    # Outings
    # ------------------------------------------------------------------

    def go_indoors(self, door: 'Door') -> None:
        """Put them behind a door at once, out of sight and off duty.

        They stay in for a while before they are willing to come out again,
        see :data:`REST_SECONDS_MIN`.

        Args:
            door: The door they live behind from now on.
        """
        self.home_door = door
        self.target_door = None
        self.rest_left = random.uniform(REST_SECONDS_MIN, REST_SECONDS_MAX)
        self.state = AT_HOME
        self.stop()
        self.path = None
        self.fade_out(0.0)
        self.place_feet(*door.entry)

    def begin_outing(
        self,
        route: Sequence[Tuple[float, float]],
        target_door: 'Door',
    ) -> bool:
        """Send them out of their door, along a route, to another door.

        Args:
            route: World points from the step outside their own door to the
                step outside the target's, as :meth:`NavGrid.find_route`
                returns them.
            target_door: The door they are to disappear into.

        Returns:
            bool: True if they set off. False when the route cannot be walked,
            in which case they stay indoors and someone else can be picked.
        """
        if self.home_door is None or not route:
            return False
        # From doorway to doorway, but only as far in as the entry: walking all
        # the way onto the Tiled point would put them behind the house.
        points = [self.home_door.entry] + list(route) + [target_door.entry]
        path = PatrolPath(points, closed=False)
        if not path:
            return False

        self.target_door = target_door
        self.state = STEPPING_OUT
        self.set_path(path, 0.0)
        # They stand in the doorway until the fade is done; the walk only
        # starts once they are all the way there to be seen.
        self.stop()
        self.opacity = 0.0
        self.fade_in(DOORWAY_FADE_SECONDS)
        self._pause_left = 0.0
        return True

    def answer_door(self) -> bool:
        """Come out of their own door for a moment, as if someone knocked.

        They fade in at the doorway, step out onto the doorstep, stand there
        for :data:`KNOCK_ANSWER_SECONDS` and go back in the way they came. The
        wait is held for as long as the player has them in conversation, so
        nobody turns their back on you mid-sentence.

        Returns:
            bool: True if they came out. False when they are out already, have
            no door, or their doorstep is right in the doorway and so leaves
            them nowhere to step.
        """
        if self.state != AT_HOME or self.home_door is None:
            return False
        path = PatrolPath([self.home_door.entry, self.home_door.step], closed=False)
        if not path:
            return False

        self.target_door = self.home_door
        self.state = ANSWERING
        self.set_path(path, 0.0)
        # Standing in the doorway until the fade is through, as when they set
        # off on a walk -- the door opens, and only then is there someone in it.
        self.stop()
        self.opacity = 0.0
        self.fade_in(DOORWAY_FADE_SECONDS)
        self._answer_left = KNOCK_ANSWER_SECONDS
        return True

    def _schedule_pause(self) -> None:
        """Pick how far they walk before they next stop to look at something."""
        self._next_pause_distance = self.path_distance + random.uniform(
            PAUSE_GAP_MIN, PAUSE_GAP_MAX
        )

    def _doorway_fade(self, dt: float) -> None:
        """Stand at the door facing it while the fade runs, then move on.

        Nothing interrupts this, not even the player stopping them for a word:
        it lasts about a second and they are half in the house already.

        Args:
            dt: Delta time in real seconds.
        """
        going_in = self.state == GOING_IN
        door = (self.target_door or self.home_door) if going_in else self.home_door
        self._animate(dt, False, door.facing_in if going_in else door.facing_out)
        if self.is_fading:
            return
        if going_in:
            self.go_indoors(door)
        elif self.state == ANSWERING:
            self.state = STEPPING_UP
            self.walk_to_distance(self.path.length)
        else:
            self.state = STROLLING
            self.walk_to_distance(self.path.length)
            self._schedule_pause()

    def _answer_the_door(self, dt: float) -> None:
        """Walk the doorstep, wait there, and walk back in again.

        Covers the three states after the door has opened. Being stopped for a
        word holds all of it, the wait included: they will stand there as long
        as the player keeps them talking, and only then turn back inside.

        Args:
            dt: Delta time in real seconds.
        """
        if self._hold_for_talk(dt):
            return

        if self.state == AT_THE_DOOR:
            self._answer_left -= dt
            if self._answer_left > 0.0:
                self._animate(dt, False, self.home_door.facing_out)
                return
            self.state = TURNING_IN
            self.walk_to_distance(0.0)

        # A word with the player leaves the walk without a target, just as on a
        # stroll, so it is picked back up here.
        if self.path is not None and self.path_target is None:
            self.walk_to_distance(self.path.length if self.state == STEPPING_UP else 0.0)

        is_moving = self._follow_path(dt)
        if is_moving:
            self._animate(dt, is_moving)
            return

        if self.state == STEPPING_UP:
            self.state = AT_THE_DOOR
            self.stop()
            self._animate(dt, False, self.home_door.facing_out)
            return

        # Back at the doorway: fade out facing it, like any other way in.
        self.state = GOING_IN
        self.fade_out(DOORWAY_FADE_SECONDS)
        self._doorway_fade(dt)

    # ------------------------------------------------------------------
    # Per-frame update
    # ------------------------------------------------------------------

    def update(self, dt: float, current_time: datetime.datetime) -> None:
        """Advance the outing, the movement and the animation.

        Args:
            dt: Delta time in real seconds.
            current_time: The current in-game time. Unused -- a townsperson
                keeps no hours of their own; :class:`StreetLife` decides when
                they go out.
        """
        if self.state == STROLLING:
            if self._hold_for_talk(dt):
                # Their walk is on hold; a doorway fade is not theirs to hold up.
                return
            # Being stopped for a word clears the walk target, so the walk has
            # to be picked back up once the player is done with them.
            if self.path is not None and self.path_target is None:
                self.walk_to_distance(self.path.length)

        if self.state == AT_HOME:
            self.rest_left = max(0.0, self.rest_left - dt)
            self._animate(dt, False)
            return

        if self.state in (STEPPING_OUT, GOING_IN, ANSWERING):
            self._doorway_fade(dt)
            return

        if self.state in ANSWERING_STATES:
            self._answer_the_door(dt)
            return

        if self.state == PAUSED:
            self._pause_left -= dt
            if self._pause_left <= 0.0 and self.path is not None:
                self.state = STROLLING
                self.walk_to_distance(self.path.length)
                self._schedule_pause()
            self._animate(dt, False)
            return

        is_moving = self._follow_path(dt)

        if not is_moving:
            # The far doorway: stop here, a step short of the house, and fade
            # out on the spot rather than walking on into the wall.
            self.state = GOING_IN
            self.fade_out(DOORWAY_FADE_SECONDS)
            self._doorway_fade(dt)
            return

        if self.path_distance >= self._next_pause_distance:
            self.state = PAUSED
            self._pause_left = random.uniform(PAUSE_SECONDS_MIN, PAUSE_SECONDS_MAX)
            self.stop()

        self._animate(dt, is_moving)

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    def inspect_lines(self, observer=None) -> List[str]:
        """Debug lines for the "Inspect" window, plus the outing."""
        lines = super().inspect_lines(observer)
        lines.append(f"Doing: {self.state}")
        lines.append(f"Home door: {self.home_door.id if self.home_door else 'none'}")
        lines.append(f"Heading for door: {self.target_door.id if self.target_door else 'none'}")
        if self.state == AT_THE_DOOR:
            lines.append(f"Standing for: {self._answer_left:.1f} s more")
        elif self.state == PAUSED:
            lines.append(f"Standing for: {self._pause_left:.1f} s more")
        elif self.state == AT_HOME and self.rest_left > 0.0:
            lines.append(f"Staying in for: {self.rest_left:.0f} s more")
        return lines
