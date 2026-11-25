"""A chicken that wanders freely about its pen, pecking at the ground.

Unlike a sheep, which walks a strip left and right, a chicken goes anywhere in
its zone (a Tiled rectangle, the pen's inside): it picks a spot a few tiles
off and trots there, stands about, or pecks for a while, and scurries away
from the player when they come too close. It only faces left and right. Its
frames are painted by code from its look (chicken_look.py), 16 pixels, drawn
SIZE_PX big at base zoom and scaled without smoothing, so it stays pixel art.

At night it sleeps in the pen's coop (models/chicken_coop.py): at dusk it walks
to the hen ladder's foot, climbs it (drawn in front of the coop) and goes in
through the pop hole, out of sight; at dawn it comes out and down again. One
without a place in the coop (more chickens than it holds) settles down near it
instead and stands there till morning. After a jump of the clock, and when the
game starts or is loaded, it is simply put where it would be by then.

It is one Hen of the flock (models/chickens.py), which says how old it is:
grow() sizes it (a chick half as big, a grown one by its own size) and pales
it (a chick's down, its colour coming as it grows up). It does not block
anyone and is not saved: only the flock is.
"""

import math
import random
from typing import Dict, List, Optional, Tuple

import pygame

from ....sim.calendar import format_date
from ...chicken_coop import BED_SPREAD_HOURS, ROOST_TILES, is_bedtime
from ...daylight import sun_hour
from .animal import Animal
from .chicken_look import FRAME, FRAME_H, FRAME_W, frames, mirrored, upright_frames

SIZE_PX = 24                 # how big a chicken of size 1 is drawn at tile_size 32: its 16-px grid half as big again
YOUTH_STEPS = 8              # a chick pales by so many steps, each its own frames
CHICKEN_SPEED = 22.0         # px per second at tile_size 32, trotting about
FLEE_SPEED = 58.0            # px per second, scurrying away from the player
FLEE_TILES = 1.3             # the player this near makes it run
FLEE_DISTANCE = (2.0, 3.5)   # tiles it runs, at the least and the most
WANDER_TILES = 4.0           # how far off the next spot may be
IDLE_SECONDS = (0.8, 4.0)
PECK_SECONDS = (1.2, 4.5)
NEXT = (("walk", 0.5), ("peck", 0.3), ("idle", 0.2))   # what it does next, by chance
WALK_FRAME_S = 0.11
FLEE_FRAME_S = 0.06
# Pecking, frame by frame: (frame of "peck": 0 down, 1 up, 2 a step on; seconds); it walks on
# PECK_STEP_PX in the step, so it feeds its way forward
PECK_SEQUENCE = ((0, 0.16), (1, 0.20), (0, 0.16), (1, 0.32), (2, 0.20))
PECK_STEP_PX = 3.0           # at tile_size 32
CLUCK_SECONDS = (25.0, 70.0)  # between one chicken's clucks
ALARM_GAP_S = 6.0            # at least this long between one chicken's alarms
UPRIGHT_SHARE = 1.3          # it faces the front or back when its way runs this much more up or down than across
#: Which way it steps on facing each way (x, y)
CLIMB_SPEED = 10.0           # px per second up or down the hen ladder, at tile_size 32
CLIMB_FRAME_S = 0.16
JUMP_MINUTES = 30            # a jump of the clock past this puts it where it would be by then
#: What it does by day, the only states it leaves for the night
DAY_STATES = ("idle", "walk", "peck")
#: Walking somewhere (with a target), in its walk frames
WALKING = ("walk", "to_coop", "to_roost")
#: On the ladder, drawn in front of the coop
CLIMBING = ("climb", "leave")
AHEAD = {"left": (-1, 0), "right": (1, 0), "front": (0, 1), "back": (0, -1)}
TURNED = {"left": "right", "right": "left", "front": "back", "back": "front"}

_frame_cache: Dict[Tuple[str, str, str, float], Dict[str, Dict[str, list]]] = {}


def chicken_frames(look, youth: float = 0.0) -> Dict[str, Dict[str, list]]:
    """{"left"/"right"/"front"/"back": {"stand": [s], "walk": [4], "peck": [down, up, step]}} for a look
    at a youth (one of the YOUTH_STEPS), made once."""
    key = (look.head, look.tail, look.colour, youth)
    if key not in _frame_cache:
        left = frames(look.head, look.tail, look.colour, youth)
        left = {"stand": [left["stand"]], "walk": left["walk"], "peck": left["peck"]}
        right = {pose: [mirrored(f) for f in fs] for pose, fs in left.items()}
        views = {"left": left, "right": right}
        for view in ("front", "back"):
            upright = upright_frames(view, look.head, look.tail, look.colour, youth)
            views[view] = {"stand": [upright["stand"]], "walk": upright["walk"], "peck": upright["peck"]}
        _frame_cache[key] = views
    return _frame_cache[key]


class Chicken(Animal):
    """A chicken of the pen."""

    def __init__(self, zone: pygame.Rect, tile_size: int, hen, now=None,
                 rng: Optional[random.Random] = None, coop=None, has_place: bool = True) -> None:
        """Args:
            zone: Where its feet may go, world pixels (the pen's inside).
            tile_size: Base tile size.
            hen: Which chicken of the flock it is (models/chickens.py Hen).
            now: The game's date, for its age; grown up and of size 1 without one.
            rng: Its random choices; the module's by default.
            coop: The pen's coop (chicken_coop.Coop), or None: then it stays out at night.
            has_place: Whether it has a place in the coop; without one it sleeps near it.
        """
        super().__init__(zone.x, zone.y, tile_size)
        self.rng = rng or random.Random()
        self.zone = pygame.Rect(zone)
        self.hen = hen
        self.look = hen.look
        self._grown: Optional[Tuple[float, int]] = None
        self._sized: Dict[int, pygame.Surface] = {}
        self.grow(now)
        self.direction = self.rng.choice(("left", "right", "front", "back"))
        self.state = "idle"
        self.timer = self.rng.uniform(*IDLE_SECONDS)
        self.target: Optional[Tuple[float, float]] = None
        self.fleeing = False
        self.frame_index = 0
        self.frame_timer = 0.0
        #: "cluck" or "alarm" when it has just made a sound (game.py plays it), else None
        self.wants_sound: Optional[str] = None
        self.cluck_timer = self.rng.uniform(*CLUCK_SECONDS)
        self.alarm_wait = 0.0
        self.coop = coop
        self.has_place = has_place and coop is not None
        # Its own hours: each goes in and comes out a little after the others
        self.bed_offset = self.rng.uniform(0.0, BED_SPREAD_HOURS)
        self.wake_offset = self.rng.uniform(0.0, BED_SPREAD_HOURS)
        self._last_now = None
        self._after_flight: Optional[str] = None    # what it was on its way to when the player scared it
        self.place_feet(*self._free_spot())
        self._set_frame()
        if now is not None:
            self._keep_hours(now)

    def grow(self, now=None) -> None:
        """Size and colour it for its age at `now`: new frames only when it has changed to be seen
        (its paleness by YOUTH_STEPS, its size by whole pixels); its feet stay where they are."""
        youth = round(self.hen.youth(now) * YOUTH_STEPS) / YOUTH_STEPS if now is not None else 0.0
        size = self.hen.size(now) if now is not None else self.hen.adult_size
        height = max(4, round(FRAME_H * SIZE_PX / FRAME * size * self.tile_size / 32))
        if self._grown == (youth, height):
            return
        feet = self.feet if self._grown is not None else None
        self._grown = (youth, height)
        self.sprite_height = height
        self.sprite_width = max(4, round(height * FRAME_W / FRAME_H))
        self.collision_width = self.sprite_width // 2
        self.collision_height = max(2, self.sprite_height // 4)
        self.poses = chicken_frames(self.look, youth)
        self._sized.clear()
        self.scaled_sprite_cache.clear()
        if feet is not None:
            self.x, self.y = feet[0] - self.sprite_width / 2.0, feet[1] - self.sprite_height
            self._set_frame()

    # ------------------------------------------------------------------
    # Where it is
    # ------------------------------------------------------------------

    @property
    def display_name(self) -> str:
        return "Chicken"

    @property
    def feet(self) -> Tuple[float, float]:
        return (self.x + self.sprite_width / 2.0, self.y + self.sprite_height)

    def place_feet(self, x: float, y: float) -> None:
        x = min(max(x, self.zone.left), self.zone.right)
        y = min(max(y, self.zone.top), self.zone.bottom)
        self.x = x - self.sprite_width / 2.0
        self.y = y - self.sprite_height

    def _clear(self, x: float, y: float) -> bool:
        """Whether feet may stand at (x, y) by day: not in the coop."""
        return self.coop is None or not self.coop.blocks(x, y)

    def _in_zone(self, x: float, y: float) -> Tuple[float, float]:
        return min(max(x, self.zone.left), self.zone.right), min(max(y, self.zone.top), self.zone.bottom)

    def _free_spot(self) -> Tuple[float, float]:
        """A random spot of its zone, out of the coop."""
        for _ in range(20):
            x, y = self.rng.uniform(self.zone.left, self.zone.right), self.rng.uniform(self.zone.top, self.zone.bottom)
            if self._clear(x, y):
                break
        return x, y

    def _spot_near(self, distance: float, around=None) -> Tuple[float, float]:
        """A spot of its zone about `distance` px off `around` (its feet) in a random direction (nearer at its
        edges), out of the coop."""
        fx, fy = around or self.feet
        for _ in range(12):
            angle = self.rng.uniform(0, 2 * math.pi)
            x, y = self._in_zone(fx + math.cos(angle) * distance, fy + math.sin(angle) * distance)
            if self._clear(x, y):
                break
        return x, y

    # ------------------------------------------------------------------
    # Behaviour
    # ------------------------------------------------------------------

    def _start(self, state: str) -> None:
        self.state = state
        self.frame_index = 0
        self.frame_timer = 0.0
        self.fleeing = False
        if state == "walk":
            self.target = self._spot_near(self.rng.uniform(1.0, WANDER_TILES) * self.tile_size)
        elif state == "to_coop":
            self.target = self.coop.foot
        elif state == "to_roost":
            self.target = self._roost_spot()
        elif state == "climb":
            self.target = self.coop.hole
            self.direction = "back"
        elif state == "leave":
            self.place_feet(*self.coop.hole)
            self.target = self.coop.foot
            self.direction = "front"
        elif state == "roost":
            self.direction = self.rng.choice(("left", "right"))
        elif state == "peck":
            self.timer = self.rng.uniform(*PECK_SECONDS)
        else:
            self.timer = self.rng.uniform(*IDLE_SECONDS)

    def _next(self) -> None:
        roll, total = self.rng.random(), 0.0
        for state, chance in NEXT:
            total += chance
            if roll < total:
                self._start(state)
                return
        self._start("idle")

    def _flee_from(self, player_feet: Tuple[float, float]) -> None:
        """Run off away from the player, as far as the pen allows."""
        fx, fy = self.feet
        dx, dy = fx - player_feet[0], fy - player_feet[1]
        length = math.hypot(dx, dy) or 1.0
        run = self.rng.uniform(*FLEE_DISTANCE) * self.tile_size
        angle = math.atan2(dy / length, dx / length) + self.rng.uniform(-0.6, 0.6)
        x, y = self._in_zone(fx + math.cos(angle) * run, fy + math.sin(angle) * run)
        if not self._clear(x, y):
            x, y = self._spot_near(run)
        back = self.state if self.state in ("to_coop", "to_roost", "roost") else None
        self._start("walk")
        self.target = (x, y)
        self.fleeing = True
        self._after_flight = back
        if self.alarm_wait <= 0:
            self.wants_sound = "alarm"
            self.alarm_wait = ALARM_GAP_S

    # ------------------------------------------------------------------
    # Night and day
    # ------------------------------------------------------------------

    def bedtime(self, now) -> bool:
        """Whether it is meant to be in for the night (or settled down, without a place) at `now`."""
        return is_bedtime(sun_hour(now), self.bed_offset, self.wake_offset)

    def _roost_spot(self) -> Tuple[float, float]:
        """Where one without a place in the coop sleeps: near its ladder, or where it stands with no coop."""
        if self.coop is None:
            return self.feet
        return self._spot_near(self.rng.uniform(0.8, ROOST_TILES) * self.tile_size, around=self.coop.foot)

    def settle(self, night: bool) -> None:
        """Put it where it would be by now: in the coop (or roosting by it) at night, out in the pen by day."""
        self.fleeing = False
        if night:
            if self.has_place:
                self.place_feet(*self.coop.hole)
                self._start("inside")
            else:
                self.place_feet(*self._roost_spot())
                self._start("roost")
        elif self.state in ("inside", "roost", "to_coop", "to_roost") + CLIMBING:
            self.place_feet(*self._free_spot())
            self._start("idle")
        self._set_frame()

    def _keep_hours(self, now) -> None:
        """Go in at its bedtime and out in the morning; after a jump of the clock, be where it would be."""
        last, self._last_now = self._last_now, now
        night = self.bedtime(now)
        if last is None or abs((now - last).total_seconds()) > JUMP_MINUTES * 60:
            self.settle(night)
            return
        if night:
            if self.state in DAY_STATES and not self.fleeing:
                self._start("to_coop" if self.has_place else "to_roost")
        elif self.state == "inside":
            self._start("leave")
        elif self.state in ("roost", "to_roost", "to_coop") and not self.fleeing:
            self._start("idle")

    @property
    def is_hidden(self) -> bool:
        """In the coop: not drawn, not clicked."""
        return self.state == "inside"

    @property
    def y_sort(self) -> float:
        """On the ladder it is drawn in front of the coop, whose base is below its feet."""
        if self.state in CLIMBING and self.coop is not None:
            return max(self.feet[1], self.coop.base_y + 1)
        return self.y + self.sprite_height

    def update(self, dt: float, player_feet: Optional[Tuple[float, float]] = None, now=None) -> None:
        """Advance behaviour and animation by dt seconds.

        Args:
            dt: Seconds.
            player_feet: Where the player stands, to run from them; None to take no notice.
            now: The game's date, for going in at night; None to take no notice of the hour.
        """
        self.wants_sound = None
        self.alarm_wait -= dt
        if now is not None:
            self._keep_hours(now)
        if self.state == "inside":
            return
        if (player_feet is not None and not self.fleeing and self.state not in CLIMBING
                and math.dist(self.feet, player_feet) < FLEE_TILES * self.tile_size):
            self._flee_from(player_feet)
        if self.state in WALKING:
            self._walk(dt)
        elif self.state in CLIMBING:
            self._climb(dt)
        elif self.state != "roost":
            self.timer -= dt
            if self.timer <= 0:
                self._next()
        self._animate(dt)
        if self.state in ("roost", "inside"):
            return                                   # asleep: no clucking
        self.cluck_timer -= dt
        if self.cluck_timer <= 0:
            self.cluck_timer = self.rng.uniform(*CLUCK_SECONDS)
            self.wants_sound = self.wants_sound or "cluck"

    def _climb(self, dt: float) -> None:
        """Up the ladder into the coop, or down it in the morning, facing the way it goes."""
        speed = CLIMB_SPEED * self.tile_size / 32.0
        fx, fy = self.feet
        tx, ty = self.target
        gap = math.hypot(tx - fx, ty - fy)
        if gap <= speed * dt or gap < 0.5:
            self.place_feet(tx, ty)
            if self.state == "climb":
                self._start("inside")
            else:
                self._start("walk")                  # off the ladder and away from the coop
            return
        self.place_feet(fx + (tx - fx) * speed * dt / gap, fy + (ty - fy) * speed * dt / gap)

    def _walk(self, dt: float) -> None:
        speed = (FLEE_SPEED if self.fleeing else CHICKEN_SPEED) * self.tile_size / 32.0
        fx, fy = self.feet
        tx, ty = self.target
        gap = math.hypot(tx - fx, ty - fy)
        self._face(tx - fx, ty - fy)
        if gap <= speed * dt or gap < 0.5:
            self.place_feet(tx, ty)
            self.target = None
            if self.state == "to_coop":
                self._start("climb")
            elif self.state == "to_roost":
                self._start("roost")
            elif self.fleeing and self._after_flight:
                self._start(self._after_flight)      # on its way to bed again
            else:
                self._start("idle" if self.fleeing else self.rng.choice(("idle", "peck")))
            return
        self.place_feet(fx + (tx - fx) * speed * dt / gap, fy + (ty - fy) * speed * dt / gap)

    def _face(self, dx: float, dy: float) -> None:
        """Face the way it goes: the front or back when that is mostly down or up the picture."""
        if abs(dy) > UPRIGHT_SHARE * abs(dx) and abs(dy) > 0.5:
            self.direction = "front" if dy > 0 else "back"
        elif abs(dx) > 0.5:
            self.direction = "right" if dx > 0 else "left"

    def _animate(self, dt: float) -> None:
        self.frame_timer += dt
        if self.state in WALKING + CLIMBING:
            step = (CLIMB_FRAME_S if self.state in CLIMBING else FLEE_FRAME_S if self.fleeing
                    else WALK_FRAME_S)
            if self.frame_timer >= step:
                self.frame_timer -= step
                self.frame_index = (self.frame_index + 1) % len(self.poses[self.direction]["walk"])
        elif self.state == "peck":
            frame, seconds = PECK_SEQUENCE[self.frame_index]
            if frame == 2:
                self._step_on(PECK_STEP_PX * self.tile_size / 32.0 * dt / seconds)
            if self.frame_timer >= seconds:
                self.frame_timer -= seconds
                self.frame_index = (self.frame_index + 1) % len(PECK_SEQUENCE)
        self._set_frame()

    def _step_on(self, px: float) -> None:
        """A little way on the way it faces while feeding; at its pen's edge it turns about."""
        ax, ay = AHEAD[self.direction]
        fx, fy = self.feet
        x, y = fx + ax * px, fy + ay * px
        if not (self.zone.left <= x <= self.zone.right and self.zone.top <= y <= self.zone.bottom):
            self.direction = TURNED[self.direction]
            return
        self.place_feet(x, y)

    def _set_frame(self) -> None:
        pose = "walk" if self.state in WALKING + CLIMBING else "peck" if self.state == "peck" else "stand"
        frames_ = self.poses[self.direction][pose]
        if pose == "peck":
            frame = frames_[PECK_SEQUENCE[self.frame_index % len(PECK_SEQUENCE)][0]]
        else:
            frame = frames_[self.frame_index % len(frames_)]
        self.source_sprite = frame
        if id(frame) not in self._sized:
            self._sized[id(frame)] = pygame.transform.scale(frame, (self.sprite_width, self.sprite_height))
        self.sprite = self._sized[id(frame)]

    def _get_scaled_sprite(self, zoom: float) -> pygame.Surface:
        """The frame at the camera's zoom, scaled without smoothing so the pixels stay sharp."""
        cache = self.scaled_sprite_cache.setdefault(round(float(zoom), 3), {})
        frame = self.source_sprite
        if id(frame) not in cache:
            size = (max(1, round(self.sprite_width * zoom)), max(1, round(self.sprite_height * zoom)))
            cache[id(frame)] = pygame.transform.scale(frame, size)
        return cache[id(frame)]

    def inspect_lines(self, observer=None) -> List[str]:
        state = "running off" if self.fleeing else {
            "walk": "walking", "peck": "pecking", "to_coop": "going to the coop", "climb": "climbing in",
            "inside": "in the coop", "leave": "coming out", "to_roost": "going to sleep outside",
            "roost": "asleep outside"}.get(self.state, "standing")
        hen = self.hen
        return super().inspect_lines(observer) + [
            "**Behaviour**",
            f"Look: {self.look.head} head, {self.look.tail} tail, {self.look.colour}",
            f"Hatched: {format_date(hen.hatched)}, lives {hen.lifespan_days:.0f} days",
            f"Grows to size {hen.adult_size:.2f}; now {self.sprite_height} px tall, youth {self._grown[0]:.2f}",
            f"State: {state}",
            f"Coop: {'a place in ' + self.coop.name if self.has_place else 'no place, sleeps outside'}",
            f"Zone: {self.zone.x},{self.zone.y} {self.zone.width}x{self.zone.height}",
        ]
