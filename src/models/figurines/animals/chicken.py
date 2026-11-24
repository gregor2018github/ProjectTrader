"""A chicken that wanders freely about its pen, pecking at the ground.

Unlike a sheep, which walks a strip left and right, a chicken goes anywhere in
its zone (a Tiled rectangle, the pen's inside): it picks a spot a few tiles
off and trots there, stands about, or pecks for a while, and scurries away
from the player when they come too close. It only faces left and right. Its
frames are painted by code from its look (chicken_look.py), 16 pixels, drawn
SIZE_PX big at base zoom and scaled without smoothing, so it stays pixel art.

It does not block anyone and is not saved: only the flock's looks are
(models/chickens.py).
"""

import math
import random
from typing import Dict, List, Optional, Tuple

import pygame

from .animal import Animal
from .chicken_look import FRAME, FRAME_H, FRAME_W, frames, mirrored

SIZE_PX = 24                 # how big it is drawn at tile_size 32: its 16-px grid half as big again
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

_frame_cache: Dict[Tuple[str, str, str], Dict[str, Dict[str, list]]] = {}


def chicken_frames(look) -> Dict[str, Dict[str, list]]:
    """{"left"/"right": {"stand": [s], "walk": [4], "peck": [down, up, step]}} for a look, made once."""
    key = (look.head, look.tail, look.colour)
    if key not in _frame_cache:
        left = frames(look.head, look.tail, look.colour)
        left = {"stand": [left["stand"]], "walk": left["walk"], "peck": left["peck"]}
        right = {pose: [mirrored(f) for f in fs] for pose, fs in left.items()}
        _frame_cache[key] = {"left": left, "right": right}
    return _frame_cache[key]


class Chicken(Animal):
    """A chicken of the pen."""

    def __init__(self, zone: pygame.Rect, tile_size: int, look, rng: Optional[random.Random] = None) -> None:
        """Args:
            zone: Where its feet may go, world pixels (the pen's inside).
            tile_size: Base tile size.
            look: Its ChickenLook (head, tail, colour).
            rng: Its random choices; the module's by default.
        """
        super().__init__(zone.x, zone.y, tile_size)
        self.rng = rng or random.Random()
        self.zone = pygame.Rect(zone)
        self.look = look
        scale = SIZE_PX / FRAME * tile_size / 32
        self.sprite_width, self.sprite_height = round(FRAME_W * scale), round(FRAME_H * scale)
        self._sized: Dict[int, pygame.Surface] = {}
        self.collision_width = self.sprite_width // 2
        self.collision_height = max(2, self.sprite_height // 4)
        self.poses = chicken_frames(look)
        self.direction = self.rng.choice(("left", "right"))
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
        self.place_feet(self.rng.uniform(self.zone.left, self.zone.right),
                        self.rng.uniform(self.zone.top, self.zone.bottom))
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

    def _spot_near(self, distance: float) -> Tuple[float, float]:
        """A spot of its zone about `distance` px off in a random direction (nearer at its edges)."""
        fx, fy = self.feet
        angle = self.rng.uniform(0, 2 * math.pi)
        x = min(max(fx + math.cos(angle) * distance, self.zone.left), self.zone.right)
        y = min(max(fy + math.sin(angle) * distance, self.zone.top), self.zone.bottom)
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
        x = min(max(fx + math.cos(angle) * run, self.zone.left), self.zone.right)
        y = min(max(fy + math.sin(angle) * run, self.zone.top), self.zone.bottom)
        self._start("walk")
        self.target = (x, y)
        self.fleeing = True
        if self.alarm_wait <= 0:
            self.wants_sound = "alarm"
            self.alarm_wait = ALARM_GAP_S

    def update(self, dt: float, player_feet: Optional[Tuple[float, float]] = None) -> None:
        """Advance behaviour and animation by dt seconds.

        Args:
            dt: Seconds.
            player_feet: Where the player stands, to run from them; None to take no notice.
        """
        self.wants_sound = None
        self.alarm_wait -= dt
        if (player_feet is not None and not self.fleeing
                and math.dist(self.feet, player_feet) < FLEE_TILES * self.tile_size):
            self._flee_from(player_feet)
        if self.state == "walk":
            self._walk(dt)
        else:
            self.timer -= dt
            if self.timer <= 0:
                self._next()
        self._animate(dt)
        self.cluck_timer -= dt
        if self.cluck_timer <= 0:
            self.cluck_timer = self.rng.uniform(*CLUCK_SECONDS)
            self.wants_sound = self.wants_sound or "cluck"

    def _walk(self, dt: float) -> None:
        speed = (FLEE_SPEED if self.fleeing else CHICKEN_SPEED) * self.tile_size / 32.0
        fx, fy = self.feet
        tx, ty = self.target
        gap = math.hypot(tx - fx, ty - fy)
        if abs(tx - fx) > 0.5:
            self.direction = "right" if tx > fx else "left"
        if gap <= speed * dt or gap < 0.5:
            self.place_feet(tx, ty)
            self.target = None
            self._start("idle" if self.fleeing else self.rng.choice(("idle", "peck")))
            return
        self.place_feet(fx + (tx - fx) * speed * dt / gap, fy + (ty - fy) * speed * dt / gap)

    def _animate(self, dt: float) -> None:
        self.frame_timer += dt
        if self.state == "walk":
            step = FLEE_FRAME_S if self.fleeing else WALK_FRAME_S
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
        ahead = -px if self.direction == "left" else px
        fx, fy = self.feet
        if not self.zone.left <= fx + ahead <= self.zone.right:
            self.direction = "right" if self.direction == "left" else "left"
            return
        self.place_feet(fx + ahead, fy)

    def _set_frame(self) -> None:
        pose = {"walk": "walk", "peck": "peck"}.get(self.state, "stand")
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
        state = "running off" if self.fleeing else {"walk": "walking", "peck": "pecking"}.get(self.state, "standing")
        return super().inspect_lines(observer) + [
            "**Behaviour**",
            f"Look: {self.look.head} head, {self.look.tail} tail, {self.look.colour}",
            f"State: {state}",
            f"Zone: {self.zone.x},{self.zone.y} {self.zone.width}x{self.zone.height}",
        ]
