"""The pond of the fishing minigame: its shape, its fish and how they behave.

Everything here is in the scene's own low-resolution pixels (``LOW_W`` x
``LOW_H``, drawn four times larger as pixel art, see ``fishing_scene.py``):
the water's surface lies at ``WATER_Y``, the player's bank ends at
``BANK_EDGE`` and the bottom follows ``bottom_y(x)``: a shelf under the bank,
a steep drop-off, the deep hollow in the middle and the shallows with the
reeds on the far side. Each kind of fish (``SPECIES``) keeps to its own parts
of it (``Species.zones``), so how far the player casts, and how deep the bait
hangs, decides what can bite.

A fish (``Fish``) wanders its zone until it notices a bait it likes the look
of, then swims up, inspects it, nibbles it a few times (``Species.nibbles``)
and takes it, swimming off with it for ``Species.take_window`` seconds: the
moment to strike. Struck too early it flees, too late it has the worm. What it
likes depends on what it is: most fish only come to a bait lying calm, and a
twitch turns away one on its way; the predators (``Species.lure`` above 0) hardly
look at a still bait, but come to one kept stirring (``Hook.stir``): twitches
draw them, repeated short pulls most of all. They chase a bait being pulled and
hit it at once, holding on longer (``REEL_TAKE_STRETCH``), as the player has the
reel to let go of first. A bait pulled in at length (``Hook.ignored``) is of no
interest to any fish, so it can always be brought home.
Minnows nibble and never take. Only one fish deals with the bait at a time
(``Hook.engaged``). Once hooked, the fight (``fishing.py``) moves it.

No pygame here: what a fish does is plain numbers, so it can be tested and
tuned headless.
"""

import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

LOW_W, LOW_H = 324, 160
WATER_Y = 66                     # the water's surface
BANK_EDGE = 78                   # where the player's bank meets the water
# The bottom, (x, y) from the bank across: a shelf, the drop-off, the deep hollow, the far shallows
_PROFILE = ((BANK_EDGE, WATER_Y), (86, 74), (98, 88), (114, 116), (132, 140), (158, 150), (190, 153),
            (218, 149), (236, 136), (252, 114), (268, 101), (288, 95), (308, 90), (LOW_W, 87))

PX_PER_FOOT = 5.0                # how deep the line hangs, for the player: low pixels a foot


def bottom_y(x: float) -> float:
    """The bottom's height at x (the bank's top over the bank)."""
    if x <= _PROFILE[0][0]:
        return WATER_Y
    for (x0, y0), (x1, y1) in zip(_PROFILE, _PROFILE[1:]):
        if x0 <= x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return _PROFILE[-1][1]


def profile() -> Sequence[Tuple[int, int]]:
    return _PROFILE


def in_water(x: float, y: float, margin: float = 2.0) -> Tuple[float, float]:
    """The nearest point to (x, y) that is in the water, margin clear of the surface, bottom and sides."""
    x = min(max(x, BANK_EDGE + 4), LOW_W - 3)
    floor = bottom_y(x) - margin
    y = min(max(y, WATER_Y + margin), max(WATER_Y + margin, floor))
    return x, y


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if v < lo else hi if v > hi else v


# ----------------------------------------------------------------------
# The species
# ----------------------------------------------------------------------

@dataclass(frozen=True)
class Species:
    key: str
    name: str
    cm: Tuple[int, int]            # the smallest and biggest (the big ones are rarer)
    value: float                   # coins for one of average size, from a plain cast
    zones: Tuple[Tuple[float, float, str, float, float], ...]   # x0, x1, "surface"/"bottom", depth from it d0..d1
    speed: float                   # low pixels a second at a fair swim
    sense: float                   # how far off it notices a bait
    nibbles: Tuple[int, int]       # nibbles before it takes (0: takes at once, as a pike does)
    take_window: float             # seconds from its taking the bait to its spitting it out with the worm
    take_chance: float             # after its nibbles, the chance it takes rather than wanders off
    caution: float                 # how long it looks, and how easily twitching scares it
    lure: float                    # how much a moving bait draws it, a predator; 0: it only comes to a calm one
    power: float                   # how hard it pulls on the line, for its average size
    stamina: float                 # how long it fights
    style: str                     # how it moves up and down in the fight (fishing.STYLES)
    shape: str                     # how its sprite is drawn (fishing_scene.fish_sprite)
    height: float                  # its body's height for its length
    colours: Tuple[Tuple[int, int, int], ...]   # back, side, belly, fins, marks
    count: int                     # how many live in the pond
    night_only: bool = False
    minnow: bool = False           # nibbles but never takes
    lore: str = ""

    @property
    def avg_cm(self) -> float:
        lo, hi = self.cm
        return lo + (hi - lo) * 0.38   # the mean of the draw in Fish.__init__


SPECIES: Dict[str, Species] = {s.key: s for s in (
    Species("roach", "Roach", (14, 32), 0.6,
            ((82, 199, "surface", 4, 26),), speed=15, sense=26, nibbles=(1, 2), take_window=0.75,
            take_chance=0.9, caution=0.7, lure=0.0, power=0.35, stamina=0.55, style="smooth", shape="roach",
            height=0.36, colours=((66, 88, 96), (190, 200, 198), (232, 230, 220), (196, 72, 52), (66, 88, 96)),
            count=5, lore="Greedy and quick: it takes after a nibble or two."),
    Species("rudd", "Rudd", (14, 30), 0.75,
            ((174, 304, "surface", 2, 16),), speed=15, sense=28, nibbles=(1, 3), take_window=0.75,
            take_chance=0.85, caution=0.8, lure=0.0, power=0.38, stamina=0.6, style="floater", shape="roach",
            height=0.38, colours=((78, 90, 66), (200, 184, 124), (230, 218, 180), (218, 64, 40), (78, 90, 66)),
            count=3, lore="Golden flanks and red fins, just under the surface."),
    Species("tench", "Tench", (25, 55), 1.5,
            ((224, 310, "bottom", 1, 6),), speed=9, sense=24, nibbles=(2, 5), take_window=1.05,
            take_chance=0.7, caution=1.2, lure=0.0, power=0.7, stamina=1.2, style="sinker", shape="carp",
            height=0.4, colours=((52, 68, 38), (94, 110, 54), (150, 148, 88), (66, 80, 42), (52, 68, 38)),
            count=2, lore="The doctor fish, olive and slimy, grubbing in the weedy shallows."),
    Species("perch", "Perch", (15, 40), 0.9,
            ((90, 136, "surface", 6, 40), (256, 318, "surface", 4, 24)), speed=17, sense=30, nibbles=(1, 3),
            take_window=0.7, take_chance=0.85, caution=0.8, lure=1.3, power=0.5, stamina=0.8, style="dart",
            shape="perch", height=0.42,
            colours=((64, 92, 48), (150, 160, 72), (214, 206, 150), (212, 92, 40), (44, 58, 30)),
            count=3, lore="Lurks by the drop-off and the reeds; a twitch draws it."),
    Species("bream", "Bream", (30, 56), 1.3,
            ((128, 246, "bottom", 2, 12),), speed=10, sense=24, nibbles=(2, 5), take_window=1.0,
            take_chance=0.7, caution=1.3, lure=0.0, power=0.6, stamina=1.0, style="sinker", shape="bream",
            height=0.5, colours=((96, 84, 52), (168, 146, 92), (204, 192, 150), (88, 76, 56), (96, 84, 52)),
            count=2, lore="Grubs on the bottom of the deep water, slow to make up its mind."),
    Species("carp", "Carp", (40, 82), 2.0,
            ((148, 230, "bottom", 2, 10),), speed=11, sense=22, nibbles=(3, 7), take_window=1.15,
            take_chance=0.6, caution=1.6, lure=0.0, power=0.95, stamina=1.6, style="smooth", shape="carp",
            height=0.42, colours=((84, 74, 38), (166, 136, 58), (210, 182, 112), (124, 82, 48), (70, 60, 30)),
            count=2, lore="The old one of the hollow: many nibbles, then a slow, sliding take."),
    Species("pike", "Pike", (45, 100), 2.4,
            ((252, 318, "surface", 6, 26), (108, 136, "surface", 10, 36)), speed=24, sense=40, nibbles=(0, 0),
            take_window=0.6, take_chance=1.0, caution=0.6, lure=2.6, power=1.05, stamina=1.3, style="dart",
            shape="pike", height=0.2,
            colours=((48, 78, 50), (106, 138, 78), (210, 208, 168), (138, 100, 58), (206, 204, 132)),
            count=2, lore="Waits in the weeds and strikes at what moves, without a nibble."),
    Species("eel", "Eel", (40, 90), 1.8,
            ((94, 256, "bottom", 1, 5),), speed=12, sense=26, nibbles=(2, 4), take_window=0.9,
            take_chance=0.75, caution=1.0, lure=0.0, power=0.75, stamina=1.2, style="dart", shape="eel",
            height=0.13, colours=((40, 40, 30), (70, 66, 44), (128, 116, 72), (52, 50, 36), (40, 40, 30)),
            count=2, night_only=True, lore="Only comes out of the mud at night."),
    Species("golden_carp", "Golden Carp", (45, 86), 6.0,
            ((148, 230, "bottom", 2, 10),), speed=11, sense=22, nibbles=(4, 8), take_window=1.1,
            take_chance=0.55, caution=1.8, lure=0.0, power=1.0, stamina=1.7, style="dart", shape="carp",
            height=0.42, colours=((196, 128, 30), (236, 186, 70), (250, 226, 140), (220, 110, 40), (180, 110, 20)),
            count=0, lore="A rare gold one among the carp. Few have seen it."),
    Species("minnow", "Minnows", (4, 7), 0.0,
            ((84, 234, "surface", 2, 18),), speed=19, sense=30, nibbles=(3, 7), take_window=0.0,
            take_chance=0.0, caution=0.3, lure=0.0, power=0.0, stamina=0.1, style="smooth", shape="roach",
            height=0.32, colours=((90, 104, 100), (176, 190, 184), (210, 214, 206), (150, 150, 140), (90, 104, 100)),
            count=3, minnow=True, lore="Pluck at the worm and are far too small for the hook."),
)}

GOLDEN_CARP_CHANCE = 0.06        # a session's pond has a golden carp among the carp


def length_px(cm: float, species: Species) -> int:
    """How long a fish of that size is drawn, in low pixels."""
    if species.minnow:
        return 4
    return max(6, round(3 + cm * 0.2))


# ----------------------------------------------------------------------
# The bait as the fish see it
# ----------------------------------------------------------------------

@dataclass
class Hook:
    """What the fish know of the bait; the game keeps it up to date."""
    x: float = 0.0
    y: float = 0.0
    alluring: bool = False         # in the water, baited, and not flying, fighting or being taken
    reeling: bool = False          # on a short pull: the predators chase it, the others keep off
    ignored: bool = False          # being pulled in at length: no fish cares
    stir: float = 0.0              # how much it has been moved of late, in small movements: what draws a predator
    twitch_age: float = 99.0       # seconds since the player last twitched it
    engaged: Optional["Fish"] = None   # the one fish dealing with it


# A fish's states
WANDER, APPROACH, INSPECT, NIBBLE, TAKE, HOOKED, FLEE = "wander", "approach", "inspect", "nibble", "take", "hooked", "flee"

NOTICE_RATE = 0.4                # a fish in reach of a still bait comes over at this rate a second, times the mood
TWITCH_LURES_S = 2.5             # a twitch moves the bait for this long, as the fish see it
STIR_DRAW = 0.35                 # a predator comes to a stirred bait at this rate, times NOTICE_RATE, its lure and the stir
STIR_REACH = 0.25                # and notices it this much farther off, times its lure, at a stir of 1 or more
PREDATOR_STILL = 0.25            # and to a still bait, of the rate the others have
CHASE_SPEED = 1.3                # chasing a reeled bait, of its fair swim
CHASE_REACH = 6.0                # it hits the bait from this near: a fish easing up to a moving point stays behind it
REEL_TAKE_STRETCH = 2.0          # a bait taken on a pull is held this much longer: the reel is to be let go first
SPOOK_S = 7.0                    # a scared fish keeps off baits this long
BORED_S = 5.0                    # one that wandered off from the bait this long


class Fish:
    """One fish of the pond (see the module)."""

    def __init__(self, species: Species, rng: random.Random) -> None:
        self.species = species
        self.zone = rng.choice(species.zones)
        lo, hi = species.cm
        self.cm = round(lo + (hi - lo) * rng.random() ** 1.6, 1)
        self.length = length_px(self.cm, species)
        self.x, self.y = self._point_in_zone(rng)
        self.vx = self.vy = 0.0
        self.facing = rng.choice((-1, 1))
        self.state = WANDER
        self.timer = rng.uniform(1, 5)
        self.target = self._point_in_zone(rng)
        self.side = 1                # which side of the bait it deals with it from
        self.spooked = 0.0
        self.bored = 0.0
        self.nibbles_left = 0
        self.take_window = species.take_window   # how long it holds on to the bait it has taken
        self.sub = ""                # within NIBBLE: "pause", "dart", "back"
        self.tail = rng.random() * 10
        self.tired = False           # rolls on its side once beaten
        self.angle = 0.0             # tilted while leaping
        self.above_water = False

    # -- where it lives -------------------------------------------------

    def _point_in_zone(self, rng: random.Random) -> Tuple[float, float]:
        x0, x1, mode, d0, d1 = self.zone
        x = rng.uniform(x0, x1)
        if mode == "surface":
            y = WATER_Y + rng.uniform(d0, d1)
        else:
            y = bottom_y(x) - rng.uniform(d0, d1)
        return in_water(x, y, 2 if mode == "surface" else 1.5)

    @property
    def mouth(self) -> Tuple[float, float]:
        return self.x + self.facing * self.length / 2, self.y

    # -- moving ---------------------------------------------------------

    def steer(self, dt: float, tx: float, ty: float, speed: float, turn: float = 4.0) -> float:
        """Swim towards (tx, ty) at up to speed; returns the distance left."""
        dx, dy = tx - self.x, ty - self.y
        dist = math.hypot(dx, dy)
        if dist > 0.01:
            want = min(speed, dist * 3.0)
            dvx, dvy = dx / dist * want, dy / dist * want
        else:
            dvx = dvy = 0.0
        k = min(1.0, dt * turn)
        self.vx += (dvx - self.vx) * k
        self.vy += (dvy - self.vy) * k
        self.x, self.y = in_water(self.x + self.vx * dt, self.y + self.vy * dt, 1.5)
        if abs(self.vx) > 0.8:
            self.facing = 1 if self.vx > 0 else -1
        return math.hypot(tx - self.x, ty - self.y)

    def flee(self, hook: Optional[Hook], rng: random.Random, seconds: float = SPOOK_S) -> None:
        if hook is not None and hook.engaged is self:
            hook.engaged = None
        self.state = FLEE
        self.timer = rng.uniform(1.0, 1.6)
        self.spooked = max(self.spooked, seconds)
        away = 1 if (hook is None or self.x >= hook.x) else -1
        self.target = in_water(self.x + away * rng.uniform(30, 60), self.y + rng.uniform(-8, 12))

    def leave(self, hook: Hook, rng: random.Random) -> None:
        """Loses interest in the bait and swims off."""
        if hook.engaged is self:
            hook.engaged = None
        self.state = WANDER
        self.bored = BORED_S * rng.uniform(0.7, 1.4)
        self.target = self._point_in_zone(rng)
        self.timer = rng.uniform(3, 7)

    # -- what it does ---------------------------------------------------

    @property
    def predator(self) -> bool:
        return self.species.lure > 0

    def _notice_odds(self, hook: Hook) -> Tuple[float, float]:
        """How far off it notices the bait as it is now, and how keen it is: 0 and it will not come."""
        lure = self.species.lure
        if not self.predator:
            return self.species.sense, 0.0 if hook.twitch_age < TWITCH_LURES_S or hook.reeling else 1.0
        keen = max(PREDATOR_STILL, STIR_DRAW * lure * hook.stir)
        return self.species.sense * (1.0 + STIR_REACH * lure * min(1.0, hook.stir)), keen

    def _notices(self, hook: Hook, dt: float, mood: float, rng: random.Random) -> bool:
        if self.spooked > 0 or self.bored > 0 or not hook.alluring or hook.engaged is not None:
            return False
        reach, keen = self._notice_odds(hook)
        if math.hypot(hook.x - self.x, hook.y - self.y) > reach:
            return False
        return rng.random() < NOTICE_RATE * mood * keen * dt

    def update(self, dt: float, hook: Hook, rng: random.Random, mood: float = 1.0) -> List[tuple]:
        """Live for dt seconds; returns what happened: ("nibble", fish), ("take", fish),
        ("stolen", fish), ("bubble", x, y), ("rise", x)."""
        events: List[tuple] = []
        sp = self.species
        self.spooked = max(0.0, self.spooked - dt)
        self.bored = max(0.0, self.bored - dt)
        self.tail += dt * (4 + math.hypot(self.vx, self.vy) * 0.6)
        hx, hy = hook.x, hook.y

        if self.state == WANDER:
            self.timer -= dt
            if self.timer <= 0 or math.hypot(self.target[0] - self.x, self.target[1] - self.y) < 2:
                self.target = self._point_in_zone(rng)
                self.timer = rng.uniform(3, 8)
            self.steer(dt, *self.target, sp.speed * 0.4, turn=2.0)
            if self.zone[2] == "bottom" and rng.random() < dt * 0.15:
                events.append(("bubble", self.mouth[0], self.y - 1))
            if self.zone[2] == "surface" and self.y < WATER_Y + 9 and rng.random() < dt * 0.04:
                events.append(("rise", self.x))
            if self._notices(hook, dt, mood, rng):
                self.state = APPROACH
                hook.engaged = self
                self.side = 1 if self.x >= hx else -1

        elif self.state in (APPROACH, INSPECT, NIBBLE) and hook.ignored:
            self.leave(hook, rng)

        elif self.state == APPROACH:
            if not hook.alluring or (hook.reeling and not self.predator):
                self.flee(hook, rng, 3.0)
            elif not self.predator and hook.twitch_age < dt * 1.01:
                self.leave(hook, rng)       # it wanted a calm bait
            elif hook.reeling:              # the chase: it hits it as it catches up
                if self.steer(dt, hx + self.side * (self.length / 2), hy, sp.speed * CHASE_SPEED, turn=6) < CHASE_REACH:
                    self._take(hook, events)
            else:
                d = self.steer(dt, hx + self.side * (self.length / 2 + 4), hy + 1, sp.speed * 0.55)
                if d < 2.0:
                    self.state = INSPECT
                    self.timer = rng.uniform(0.7, 2.0) * sp.caution
                    self.facing = -self.side

        elif self.state == INSPECT:
            if self.predator and hook.alluring and (hook.reeling or hook.twitch_age < dt * 1.01):
                self._take(hook, events)    # it was making up its mind, and the bait moves
            elif hook.reeling or not hook.alluring:
                self.flee(hook, rng, 4.0)
            else:
                sway = math.sin(self.tail * 0.35) * 2
                self.steer(dt, hx + self.side * (self.length / 2 + 4 + sway), hy + 1 + math.sin(self.tail * 0.2), sp.speed * 0.3)
                self.facing = -self.side
                self.timer -= dt
                if self.timer <= 0:
                    lo, hi = sp.nibbles
                    if hi <= 0:
                        self._take(hook, events)
                    else:
                        self.state = NIBBLE
                        self.nibbles_left = rng.randint(lo, hi)
                        self.sub, self.timer = "pause", rng.uniform(0.2, 0.6)

        elif self.state == NIBBLE:
            if hook.reeling or not hook.alluring:
                self.flee(hook, rng, 4.0)
            else:
                self.facing = -self.side
                back = (hx + self.side * (self.length / 2 + 3), hy + 1)
                touch = (hx + self.side * (self.length / 2 - 0.5), hy)
                self.timer -= dt
                if self.sub == "pause":
                    self.steer(dt, *back, sp.speed * 0.35)
                    self.facing = -self.side
                    if self.timer <= 0:
                        self.sub, self.timer = "dart", 0.12
                elif self.sub == "dart":
                    self.steer(dt, *touch, sp.speed * 1.6, turn=12)
                    self.facing = -self.side
                    if self.timer <= 0:
                        events.append(("nibble", self))
                        self.nibbles_left -= 1
                        self.sub, self.timer = "back", 0.25
                elif self.sub == "back":
                    self.steer(dt, *back, sp.speed * 0.8, turn=8)
                    self.facing = -self.side
                    if self.timer <= 0:
                        if self.nibbles_left > 0:
                            self.sub, self.timer = "pause", rng.uniform(0.35, 1.1) * sp.caution
                        elif not sp.minnow and rng.random() < min(1.0, sp.take_chance * mood ** 0.5):
                            self._take(hook, events)
                        else:
                            self.leave(hook, rng)

        elif self.state == TAKE:
            # Off with the bait, away and down; the hook goes with its mouth
            self.timer -= dt
            away_x = self.x + self.side * 30
            self.steer(dt, away_x, self.y + 10, sp.speed * 0.75, turn=6)
            self.facing = self.side
            if self.timer <= 0:
                events.append(("stolen", self))
                self.flee(hook, rng)

        elif self.state == FLEE:
            self.timer -= dt
            self.steer(dt, *self.target, sp.speed * 1.5, turn=6)
            if self.timer <= 0:
                self.state = WANDER
                self.target = self._point_in_zone(rng)
                self.timer = rng.uniform(3, 7)

        # HOOKED: moved by the fight
        return events

    def _take(self, hook: Hook, events: List[tuple]) -> None:
        self.state = TAKE
        self.take_window = self.species.take_window * (REEL_TAKE_STRETCH if hook.reeling else 1.0)
        self.timer = self.take_window
        self.side = 1 if self.x >= hook.x else -1
        events.append(("take", self))


# ----------------------------------------------------------------------
# The pond: who lives in it, and how hungry they are
# ----------------------------------------------------------------------

def bite_mood(hour: float, season: int, rain: float, storm: float, snow: float, clouds: float) -> Tuple[float, str]:
    """How keen the fish are to bite (1 as usual) and a line saying why, by the sun hour,
    the season (0 Spring .. 3 Winter) and the weather."""
    mood, why = 1.0, "A quiet day by the water."
    night = hour < 5.0 or hour > 21.0
    dawn = 5.0 <= hour < 8.5
    dusk = 17.5 <= hour <= 21.0
    if dawn or dusk:
        mood, why = 1.5, ("Dawn: the fish are feeding." if dawn else "Dusk: the fish are feeding.")
    elif night:
        mood, why = 0.85, "Night: the eels are about."
    elif 11.0 <= hour <= 15.0 and clouds < 0.4 and rain < 0.1:
        mood, why = 0.75, "Bright noon: the fish keep to the deep."
    if storm > 0.2:
        mood, why = mood * 1.4, "A storm is coming: the fish bite boldly."
    elif rain > 0.15:
        mood, why = mood * 1.25, "Rain on the water: the fish are bold."
    if season == 3:
        mood *= 0.7
        why = "Winter: the fish are slow and sluggish." if mood < 1.0 else why
    elif season == 1 and not night:
        mood *= 1.1
    return mood, why


class Pond:
    """The fish of one session, by the hour, the season and the weather."""

    def __init__(self, rng: random.Random, hour: float = 12.0, season: int = 0, rain: float = 0.0,
                 storm: float = 0.0, snow: float = 0.0, clouds: float = 0.0) -> None:
        self.rng = rng
        self.night = hour < 5.0 or hour > 21.0
        self.mood, self.lore = bite_mood(hour, season, rain, storm, snow, clouds)
        self.fish: List[Fish] = []
        golden = rng.random() < GOLDEN_CARP_CHANCE
        for sp in SPECIES.values():
            n = sp.count
            if sp.night_only and not self.night:
                n = 0
            if sp.key == "carp" and season == 1:
                n += 1
            if season == 3 and n > 1 and not sp.minnow:
                n = max(1, round(n * 0.6))
            for i in range(n):
                kind = sp
                if golden and sp.key == "carp" and i == 0:
                    kind = SPECIES["golden_carp"]
                    golden = False
                self.fish.append(Fish(kind, rng))
        self._respawn: List[Tuple[float, Species]] = []

    def update(self, dt: float, hook: Hook) -> List[tuple]:
        events: List[tuple] = []
        for fish in self.fish:
            if fish.state != HOOKED:
                events.extend(fish.update(dt, hook, self.rng, self.mood))
        for i in range(len(self._respawn) - 1, -1, -1):
            left, sp = self._respawn[i]
            left -= dt
            if left <= 0:
                del self._respawn[i]
                self.fish.append(Fish(sp, self.rng))
            else:
                self._respawn[i] = (left, sp)
        return events

    def remove(self, fish: Fish, respawn_s: float = 15.0) -> None:
        """Take a fish out (caught, or gone off with a hook); another of its kind swims in later
        (a golden carp is gone for good: an ordinary carp takes its place)."""
        if fish in self.fish:
            self.fish.remove(fish)
        sp = SPECIES["carp"] if fish.species.key == "golden_carp" else fish.species
        self._respawn.append((respawn_s, sp))

    def scare(self, x: float, y: float, radius: float, seconds: float, hook: Optional[Hook] = None) -> None:
        for fish in self.fish:
            if fish.state != HOOKED and math.hypot(fish.x - x, fish.y - y) < radius:
                fish.flee(hook, self.rng, seconds)
