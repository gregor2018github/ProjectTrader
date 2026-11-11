"""A homebody: someone who keeps to one house and the ground in front of it.

Unlike a townsperson, a homebody is never sent across town, and unlike a
trader he has no stall. He lives behind the front door of one building, steps
out of it in the morning and spends the day in front of it -- standing about,
shuffling to another spot now and then -- and now and again takes a little
walk, out to some spot nearby and back, before going in again in the evening.
The old woodcutter by the wood shed, who lets the player split his logs, is
the first of them.

Who he is comes from his sprite folder, ``npcs/<class>_<name>/``, and its
``npc.json``, as for a townsperson; a ``"home"`` in it is what makes him a
homebody (and keeps him out of :class:`~....town_life.StreetLife`):

* ``"home"`` -- the Tiled name of the building he lives in; he uses its first
  door on the "Doors" layer.
* ``"stand_in"`` -- optional: a sprite folder to borrow the looks of while his
  own has no standing sprite yet (he is drawn like that person meanwhile).
* ``"tiled_prefix"`` -- optional: the name stem of his objects on the
  "Movements" layer; his ``"name"`` if not given.
* ``"sentences"`` -- optional: a sentence file of his own in
  ``assets/texts/NPCs/``, said more often than his class's lines.
* ``"introduces"`` -- optional: the minigame he shows the player (so far
  ``"woodhacking"``); the UI reads it.

On the "Movements" layer, named after his prefix (``Osric`` for Osric):

* ``<prefix>_Yard`` -- polygon he walks while about in front of his house,
  as a trader walks his stall's. Without one he stands on his doorstep.
* ``<prefix>_Walk_1``, ``<prefix>_Walk_2``, ... -- points he walks out to now
  and then, stands at a while and comes back from: any number, each with a
  name of its own starting ``<prefix>_Walk`` (the layer is read by name).

The ways between the door, the yard and the walks' ends are worked out on the
:class:`~....navigation.NavGrid` once, when the map is loaded (:meth:`settle`).
His hours follow the daylight (:func:`~....daylight.sun_hour`), not the clock:
out in ``OUT_WINDOW``, in by ``IN_WINDOW``, drawn afresh each day. Where he is,
is session state and not saved, as for the townsfolk.
"""

import datetime
import os
import random
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, List, Optional, Sequence, Tuple

from ....daylight import sun_hour
from ...patrol_path import PatrolPath
from .npc import NPC, NPC_SPRITE_ROOT
from .sentences import load_sentences, rumours_for, RUMOUR_CHANCE, sentences_for
from .townsperson import (
    CLASS_BY_FOLDER_PREFIX, DOORWAY_FADE_SECONDS, HOME_KEY, profile_gender, read_profiles,
)

if TYPE_CHECKING:
    from ....door import Door

Point = Tuple[float, float]
#: Works out a walkable way between two world points (NavGrid.find_route), or None.
RouteFinder = Callable[[Point, Point], Optional[List[Point]]]

#: Walking speed in pixels per second at tile_size 32: an old man's, slower
#: than a trader minding his stall (35).
HOMEBODY_SPEED = 26.0

#: When he comes out and goes in, in sun hours (see daylight.sun_hour): drawn
#: anew each day within these windows.
OUT_WINDOW = (6.5, 8.0)
IN_WINDOW = (19.0, 20.5)

#: How long he stands at one spot in front of the house, in in-game minutes.
IDLE_MIN_MINUTES = 30
IDLE_MAX_MINUTES = 80
#: A new spot in the yard is at least this far along it from the last.
MIN_STEP_DISTANCE = 40.0
SPOT_ATTEMPTS = 8

#: Each time he is done standing somewhere, the chance he goes for a walk
#: instead, once WALK_GAP_MINUTES have passed since his last one came back.
WALK_CHANCE = 0.3
WALK_GAP_MINUTES = 120
#: How long he stays out at a walk's end, in in-game minutes.
LINGER_MIN_MINUTES = 15
LINGER_MAX_MINUTES = 40

#: Which way he looks while standing in front of his house: mostly out at the
#: world, the house at his back.
YARD_FACINGS = ("front", "front", "front_left", "front_right", "left", "right")

#: A gap between updates longer than this, in in-game minutes, means the map
#: was not shown and time ran on without him; he is then put straight where
#: his day would have taken him.
CATCH_UP_MINUTES = 30

#: Of his chats, the share said from his own sentence file (if he has one).
OWN_LINE_CHANCE = 0.6

# Where he is in his day. STEPPING_OUT and GOING_IN stand at the door while the fade runs.
INDOORS = "Indoors"
STEPPING_OUT = "Stepping outside"
TO_YARD = "Coming out to the yard"
IN_YARD = "About in front of the house"
LEAVING_YARD = "Crossing the yard"
ON_WALK = "Out for a little walk"
LINGERING = "Looking about"
WALKING_BACK = "Walking back"
GOING_HOME = "Going home"
GOING_IN = "Going indoors"

#: LEAVING_YARD towards the door rather than one of the walks.
TO_DOOR = -1


@dataclass
class Walk:
    """One of his walks: the way out from the yard and where on the yard it starts."""
    path: PatrolPath
    yard_distance: float


def discover_homebodies(tile_size: int) -> List['Homebody']:
    """Create one homebody per sprite folder whose ``npc.json`` names a home.

    Args:
        tile_size: Base tile size for scaling.

    Returns:
        List: Every homebody the artwork tree knows about, in folder order.
    """
    return [Homebody(folder, profile, tile_size)
            for folder, profile in read_profiles() if profile.get(HOME_KEY)]


def _has_standing_sprite(folder: str, prefix: str) -> bool:
    directory = os.path.join(NPC_SPRITE_ROOT, folder)
    return any(os.path.exists(os.path.join(directory, f"{prefix}_{direction}_static.png"))
               for direction in ("front", "left", "right", "back"))


def _prefix_of(folder: str) -> str:
    """A sprite folder's file prefix: ``trader_woodcutter`` -> ``woodcutter``."""
    return folder.split("_", 1)[-1]


class Homebody(NPC):
    """Someone who stays about his own house all day (see the module)."""

    def __init__(self, folder: str, profile: dict, tile_size: int) -> None:
        """Create him from his sprite folder and profile; indoors, until settled.

        Args:
            folder: His folder under ``NPC_SPRITE_ROOT``, e.g. ``"commons_osric"``.
                Its prefix gives his social class.
            profile: What his ``npc.json`` says (see the module).
            tile_size: Base tile size for scaling.
        """
        name = profile.get("name") or folder
        super().__init__(name, 0.0, 0.0, tile_size)
        self.folder: str = folder
        self.SOCIAL_CLASS = CLASS_BY_FOLDER_PREFIX.get(folder.split("_", 1)[0], NPC.SOCIAL_CLASS)
        self.GENDER = profile_gender(profile)
        #: The Tiled name of the building he lives in.
        self.home_name: str = str(profile.get(HOME_KEY))
        #: Name stem of his objects on the "Movements" layer.
        self.tiled_prefix: str = str(profile.get("tiled_prefix") or name)
        #: The minigame he shows the player, or None.
        self.introduces: Optional[str] = profile.get("introduces")
        self.sentence_file: Optional[str] = profile.get("sentences")

        # His own looks once he has a standing sprite, a stand-in's until then
        self.SPRITE_FOLDER, self.SPRITE_PREFIX = folder, _prefix_of(folder)
        stand_in = profile.get("stand_in")
        if stand_in and not _has_standing_sprite(folder, self.SPRITE_PREFIX):
            self.SPRITE_FOLDER, self.SPRITE_PREFIX = stand_in, _prefix_of(stand_in)

        self.speed = HOMEBODY_SPEED * tile_size / 32.0
        self._init_human_animator(
            sprite_dir=self.sprite_dir,
            sprite_definitions=self._sprite_definitions(),
            fallback_static=self._fallback_static(),
            normalize=True,
        )

        #: Set by settle(): his door, the way from it to the yard, the yard, the walks.
        self.door: Optional['Door'] = None
        self.homeway: Optional[PatrolPath] = None
        self.yard: Optional[PatrolPath] = None
        self.yard_home_distance: float = 0.0
        self.walks: List[Walk] = []

        self.state: str = INDOORS
        self.opacity = 0.0
        #: In-game time he next feels like moving on, from a spot or a walk's end.
        self.idle_until: Optional[datetime.datetime] = None
        #: When his last walk brought him back; None if he has not been on one.
        self.last_walk_end: Optional[datetime.datetime] = None
        self._walk: Optional[Walk] = None        # the walk he is on or heading for
        self._exit_to: int = TO_DOOR             # LEAVING_YARD: TO_DOOR or a walk's index
        self._facing: Optional[str] = None       # while standing in the yard
        self.last_update_time: Optional[datetime.datetime] = None
        self._hours_day: Optional[datetime.date] = None
        self.out_at: float = OUT_WINDOW[0]
        self.in_at: float = IN_WINDOW[1]

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def settle(self, door: 'Door', yard: Optional[PatrolPath], walk_targets: Sequence[Point],
               find_route: RouteFinder) -> None:
        """Give him his house's door, his yard and his walks, and work out the ways between.

        Args:
            door: The front door he goes in and out by.
            yard: The path he walks in front of the house, or None to stand on the doorstep.
            walk_targets: World points he walks out to now and then.
            find_route: Works out a walkable way between two points (NavGrid.find_route).
        """
        self.door = door
        self.yard = yard if yard else None
        if self.yard is not None:
            self.yard_home_distance = self.yard.closest_distance(door.step)
            yard_point = self.yard.position_at(self.yard_home_distance)
            route = find_route(door.step, yard_point)
            if not route:
                print(f"{self.name}: no way from his door to his yard; walking it straight")
                route = [door.step, yard_point]
            self.homeway = PatrolPath([door.entry] + list(route), closed=False)
        else:
            self.homeway = PatrolPath([door.entry, door.step], closed=False)

        self.walks = []
        for target in walk_targets:
            if self.yard is not None:
                start_distance = self.yard.closest_distance(target)
                start = self.yard.position_at(start_distance)
            else:
                start_distance, start = 0.0, door.step
            route = find_route(start, target)
            path = PatrolPath(route, closed=False) if route else None
            if not path:
                print(f"{self.name}: no way out to his walk at ({target[0]:.0f}, {target[1]:.0f}); left out")
                continue
            self.walks.append(Walk(path, start_distance))
        self.go_indoors()

    @property
    def is_settled(self) -> bool:
        return self.door is not None and bool(self.homeway)

    # ------------------------------------------------------------------
    # Chat
    # ------------------------------------------------------------------

    def chat_line(self) -> str:
        """His own lines more often than not, else his class's or a rumour, as anyone's."""
        own = list(load_sentences(self.sentence_file)) if self.sentence_file else []
        if own and random.random() < OWN_LINE_CHANCE:
            return self._pick_line(own, "Good day to you.")
        sentences = rumours_for(self.SOCIAL_CLASS, False) if random.random() < RUMOUR_CHANCE else []
        return self._pick_line(sentences or sentences_for(self.SOCIAL_CLASS, False), "Good day to you.")

    # ------------------------------------------------------------------
    # Hours
    # ------------------------------------------------------------------

    def _draw_hours(self, current_time: datetime.datetime) -> None:
        if self._hours_day != current_time.date():
            self._hours_day = current_time.date()
            self.out_at = random.uniform(*OUT_WINDOW)
            self.in_at = random.uniform(*IN_WINDOW)

    def is_out_time(self, current_time: datetime.datetime) -> bool:
        """Whether he should be out of doors now (in this day's hours, by the daylight)."""
        self._draw_hours(current_time)
        return self.out_at <= sun_hour(current_time) < self.in_at

    def _is_unseen(self, current_time: datetime.datetime) -> bool:
        return (self.last_update_time is None
                or abs(current_time - self.last_update_time) > datetime.timedelta(minutes=CATCH_UP_MINUTES))

    # ------------------------------------------------------------------
    # Placing him
    # ------------------------------------------------------------------

    def go_indoors(self) -> None:
        """Put him behind his door at once, out of sight."""
        self.state = INDOORS
        self._walk = None
        self.idle_until = None
        self.stop()
        self.fade_out(0.0)
        if self.homeway:
            self.set_path(self.homeway, 0.0)

    def _put_in_yard(self, current_time: datetime.datetime, distance: Optional[float] = None,
                     stagger: bool = False) -> None:
        """Stand him in front of the house, at a distance along the yard (random if None)."""
        self.state = IN_YARD
        self._walk = None
        if self.yard is not None:
            self.set_path(self.yard, distance)
        else:
            self.set_path(self.homeway, self.homeway.length)
        self._rest(current_time, stagger)

    def _catch_up(self, current_time: datetime.datetime) -> None:
        """Put him straight where he belongs after time ran on unseen."""
        if self.is_out_time(current_time):
            self._put_in_yard(current_time, stagger=True)
            self.fade_in(0.0)
        else:
            self.go_indoors()

    def _rest(self, current_time: datetime.datetime, stagger: bool = False) -> None:
        """Stand where he is for a while, looking out from the house."""
        self.stop()
        self._facing = random.choice(YARD_FACINGS)
        low = 0 if stagger else IDLE_MIN_MINUTES
        self.idle_until = current_time + datetime.timedelta(minutes=random.uniform(low, IDLE_MAX_MINUTES))

    # ------------------------------------------------------------------
    # His day
    # ------------------------------------------------------------------

    def _head_home(self) -> None:
        """Turn whatever he is doing towards his door (nothing if he is on his way already)."""
        if self.state == TO_YARD:
            self.state = GOING_HOME
            self.walk_to_distance(0.0)
        elif self.state == IN_YARD or (self.state == LEAVING_YARD and self._exit_to != TO_DOOR):
            if self.yard is None:
                self.state = GOING_HOME
                self.set_path(self.homeway, self.homeway.length)
                self.walk_to_distance(0.0)
            else:
                self.state = LEAVING_YARD
                self._exit_to = TO_DOOR
                self.walk_to_distance(self.yard_home_distance)
        elif self.state in (ON_WALK, LINGERING):
            self.state = WALKING_BACK
            self.walk_to_distance(0.0)

    def _come_out(self) -> None:
        """Out of his door in the morning, or turned round on his way in."""
        if self.state == INDOORS:
            self.state = STEPPING_OUT
            self.set_path(self.homeway, 0.0)
            self.stop()
            self.fade_in(DOORWAY_FADE_SECONDS)
            self.wants_door_sound = True
        elif self.state == GOING_HOME:
            self.state = TO_YARD
            self.walk_to_distance(self.homeway.length)

    def _wants_walk(self, current_time: datetime.datetime) -> bool:
        if not self.walks or random.random() >= WALK_CHANCE:
            return False
        return (self.last_walk_end is None
                or current_time - self.last_walk_end >= datetime.timedelta(minutes=WALK_GAP_MINUTES))

    def _move_on(self, current_time: datetime.datetime) -> None:
        """Done standing at a spot in the yard: a walk, or another spot."""
        if self._wants_walk(current_time):
            index = random.randrange(len(self.walks))
            self._walk = self.walks[index]
            if self.yard is None:
                self._start_walk()
            else:
                self.state = LEAVING_YARD
                self._exit_to = index
                self.walk_to_distance(self._walk.yard_distance)
            return
        if self.yard is None:
            self._rest(current_time)
            return
        for _ in range(SPOT_ATTEMPTS):
            candidate = self.yard.random_distance()
            if abs(self.yard.signed_gap(self.path_distance, candidate)) >= MIN_STEP_DISTANCE:
                break
        self._facing = None
        self.walk_to_distance(candidate)

    def _start_walk(self) -> None:
        self.state = ON_WALK
        self.set_path(self._walk.path, 0.0)
        self.walk_to_distance(self._walk.path.length)

    def _arrive(self, current_time: datetime.datetime) -> None:
        """At the end of a leg: on to the next one."""
        if self.state == TO_YARD:
            self._put_in_yard(current_time, self.yard_home_distance)
        elif self.state == LEAVING_YARD:
            if self._exit_to == TO_DOOR:
                self.state = GOING_HOME
                self.set_path(self.homeway, self.homeway.length)
                self.walk_to_distance(0.0)
            else:
                self._start_walk()
        elif self.state == ON_WALK:
            self.state = LINGERING
            self.idle_until = current_time + datetime.timedelta(
                minutes=random.uniform(LINGER_MIN_MINUTES, LINGER_MAX_MINUTES))
        elif self.state == WALKING_BACK:
            self.last_walk_end = current_time
            walk = self._walk
            self._put_in_yard(current_time, walk.yard_distance if walk else None)
        elif self.state == GOING_HOME:
            self.state = GOING_IN
            self.fade_out(DOORWAY_FADE_SECONDS)
            self.wants_door_sound = True

    def _doorway_fade(self, dt: float) -> None:
        """Stand at the door facing it, or out of it, while the fade runs."""
        going_in = self.state == GOING_IN
        self._animate(dt, False, self.door.facing_in if going_in else self.door.facing_out)
        if self.is_fading:
            return
        if going_in:
            self.go_indoors()
        else:
            self.state = TO_YARD
            self.walk_to_distance(self.homeway.length)

    # ------------------------------------------------------------------
    # Per-frame update
    # ------------------------------------------------------------------

    def update(self, dt: float, current_time: datetime.datetime) -> None:
        """Advance his day, his walking and his animation.

        Args:
            dt: Delta time in real seconds.
            current_time: The current in-game time, which keeps his hours and his rests.
        """
        if not self.is_settled:
            self._animate(dt, False)
            return
        if self.state in (STEPPING_OUT, GOING_IN):
            # A doorway fade is not to be held up, not even for a word
            self.last_update_time = current_time
            self._doorway_fade(dt)
            return
        if self._hold_for_talk(dt):
            # As for a trader: time spent talking was watched, not unseen
            self.last_update_time = current_time
            return

        if self._is_unseen(current_time):
            self._catch_up(current_time)
        self.last_update_time = current_time

        if self.is_out_time(current_time):
            self._come_out()
        else:
            self._head_home()
        if self.state in (INDOORS, STEPPING_OUT):
            self._animate(dt, False)
            return

        if self.state in (IN_YARD, LINGERING) and self.path_target is None:
            if self.idle_until is not None and current_time >= self.idle_until:
                if self.state == LINGERING:
                    self.state = WALKING_BACK
                    self.walk_to_distance(0.0)
                else:
                    self._move_on(current_time)

        is_moving = self._follow_path(dt)
        if not is_moving and self.path_target is None:
            if self.state == IN_YARD and self.was_moving:
                self._rest(current_time)   # at a new spot: stand there a while
            elif self.state not in (IN_YARD, LINGERING):
                self._arrive(current_time)
        if self.state == GOING_IN:
            self._doorway_fade(dt)
            return
        facing = self._facing if (self.state == IN_YARD and not is_moving) else None
        self._animate(dt, is_moving, facing)

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    def inspect_lines(self, observer=None) -> List[str]:
        """Debug lines for the "Inspect" window, plus his day."""
        lines = super().inspect_lines(observer)
        lines.append(f"Day: {self.state}")
        lines.append(f"Home: {self.home_name} (door {self.door.id if self.door else 'none'})")
        lines.append(f"Out from {self.out_at:.2f} to {self.in_at:.2f} (sun hours)")
        lines.append(f"Yard: {'drawn' if self.yard else 'none, stands on the doorstep'}; walks: {len(self.walks)}")
        if self.SPRITE_FOLDER != self.folder:
            lines.append(f"Looks borrowed from: {self.SPRITE_FOLDER}")
        if self.state in (IN_YARD, LINGERING) and self.path_target is None and self.idle_until is not None:
            lines.append(f"Moves on at: {self.idle_until:%H:%M}")
        return lines
