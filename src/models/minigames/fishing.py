"""Fishing minigame: cast, wait in the dark, strike at the right moment, fight the fish home.

Unlike the woodhacking, there is no gauge to read: everything is in the
movement of the mouse and in what the pond shows.

  1. CAST     — hold the left button and drag the mouse back: the rod goes
                back over the shoulder. Whip it forward and let go. How fast
                the rod moves when you let go sets how far the bait flies
                (``V_FULL``; overdo it and the line tangles), *when* you let go
                its arc: best as the rod passes the faint mark a little ahead
                of upright (``SWEET_THETA``). That timing is the cast's grade
                (``CAST_GRADES``, PERFECT to POOR), which multiplies the coins
                of whatever bites on it, and a clean cast lands softly while a
                poor one slaps the water and scares the fish near it. Farther
                out is deeper water and bigger fish (``fishing_pond``).
  2. WAIT     — the bait sinks under its float to the line's depth, which
                the wheel sets before the cast and is fixed once it is out:
                set deeper than the water where it lands, the hook sinks onto
                the bottom, catches and rips off (``STUCK``), as it does on the
                roots under the bank when reeled over them. You only see round
                the bait. A click twitches it,
                which draws fish (and, overdone, scares the wary ones);
                holding the button reels it in slowly. Fish come, look,
                nibble (the float trembles) and take (the float goes under).
  3. STRIKE   — flick the mouse sharply upwards (or press Space) while a fish
                has the bait: graded by how quickly after its take
                (``STRIKE_GRADES``), which sets how well the hook holds. Too
                early and it flees, too late and the worm is gone.
  4. FIGHT    — hold the button to reel, let go to give line. Along the top of
                the scene a marker swings left and right over a wide bar
                (``Fight.bar_x``): keep the mouse under it. Off its zone the
                reel gains nothing, the fish drags line out and the line takes
                more strain. Any but the tiniest fish strains the line while it
                runs (``PULL_FORCE``), and the strain hardly eases until the
                button is let go, so reel in bursts. Now and then the fish braces
                itself (the bar flashes) and rages: let go until it calms, and
                reel while it is spent.
                The fish is lost only when its power (``Fight.stamina``, the
                bar under the marker) is full. It starts at half or a little
                under (``FRESH_POWER``), falls while it is reeled and rises while
                the line is let go. A line strained to its limit gives way a
                little and hands the fish a jump of power (``OVERLOAD_POWER``),
                as does holding on to a leaping fish; a slack line on a fish
                shaking its head lets it gain faster. A bigger fish
                (``Fight.heft``) has a narrower zone, a faster marker, rages
                more often and for longer and gains more from an overload. Once
                its power is low (``LAND_STAMINA``) and it is near the bank it
                is netted.

Escape asks first ("Exit Mini Game now?"), the game waiting for the answer,
unless the session is over.

Coins come only for fish brought in: the kind's value, times its size against
the usual, times the cast's grade (``fish_coins``), booked as it lands. A
session is ``WORMS`` worms: one is used up by every fish hooked or lost and
every worm stolen or snagged; a fish caught on a PERFECT cast with a PERFECT
strike earns an extra one (``MAX_EXTRA_WORMS`` at most). The fishing is once a day, and the clock moves on
by the share of ``HOURS_OF_WORK`` the worms used took.
"""

import math
import os
import random
from array import array
from collections import deque
from typing import Callable, Deque, List, Optional, Tuple

import pygame

from .base import MinigameOverlay
from .fishing_pond import (
    Pond, Hook, Fish, SPECIES, WATER_Y, BANK_EDGE, LOW_W, SNAGS, PX_PER_FOOT, bottom_y, in_water,
    APPROACH, INSPECT, NIBBLE, TAKE, HOOKED,
)
from .fishing_scene import PondScene, PondView, PX, SCENE_W, SCENE_H, rod_points, curve, fish_sprite
from .outdoors import Conditions
from ...config.colors import BEIGE, SANDY_BROWN, PALE_BROWN, DARK_BROWN, BLACK, GOLD
from ...config.constants import SCREEN_WIDTH, SCREEN_HEIGHT, SIDEBAR_WIDTH, FONTS_PATH
from ...ui.paper import draw_paper

MINIGAME_NAME = "Fishing"
WORMS = 4                       # a session's worms
MAX_EXTRA_WORMS = 1             # at most this many earned back in a session
HOURS_OF_WORK = 3.0             # a whole session takes this long: the clock has moved on when you leave

# The cast
READY_THETA = 26.0              # the rod's angle from upright, held out over the water
THETA_RANGE = (-88.0, 72.0)
DEG_PER_PX = 0.32               # how far the rod turns for a pixel the mouse moves
ROD_SPRING = 700.0              # how stiffly the rod follows the hand (1/s²)
ROD_DAMPING = 40.0
SWEET_THETA = 8.0               # let go here: a little ahead of upright
LAUNCH_ANGLE = 33.0             # the bait's best arc, let go at the sweet spot
TIMING_DEG_PER_S = 320.0        # each second too early (late) lifts (flattens) the arc this much
V_FULL = 600.0                  # the rod tip's speed (low px/s) of a full cast
V_LAUNCH = 262.0                # the bait's speed leaving a full cast
GRAVITY = 300.0
TANGLE_POWER = 1.75             # a whip this much harder than full tangles the line
MIN_WHIP_DEG_S = 160.0          # slower than this when let go is no cast at all
# Cast grades: (most seconds off the sweet spot, label, coin multiplier, colour)
CAST_GRADES = ((0.035, "PERFECT CAST", 1.5, (246, 214, 110)), (0.07, "GREAT CAST", 1.25, (150, 214, 120)),
               (0.12, "GOOD CAST", 1.0, (226, 226, 200)), (99.0, "POOR CAST", 0.75, (226, 132, 92)))

# Waiting
LEADER_RANGE = (6.0, 90.0)      # how deep the bait hangs under the float (low px)
LEADER_STEP = 4.0
LEADER_START = 26.0
SINK_SPEED = 20.0
REEL_IDLE_SPEED = 14.0          # reeling an untouched bait in, low px/s
TAP_S = 0.2                     # a press shorter than this is a twitch, longer is reeling
TWITCH_WINDOW_S = 4.0           # twitches are counted over this long
SNAG_RATE = 1.4                 # a bait dragged over the roots catches at this rate a second
STUCK_S = 1.1                   # a hook caught on the bottom: the rod tugs this long, then the hook rips off
STUCK_RIP_AT = 0.75             # the moment it goes (seconds in)
CLEAR_OF_BOTTOM = 3.0           # a bait being reeled in rises this far clear of the bottom
DUCK_BOB_RANGE = 7.0            # the duck paddling this near rocks the float

# The strike: a flick up of at least this many pixels at this speed within the window
STRIKE_PX = 40.0
STRIKE_SPEED = 1000.0
STRIKE_WINDOW_S = 0.15
# Strike grades: (most of the take window, label, hold of the hook)
STRIKE_GRADES = ((0.42, "PERFECT STRIKE", 1.0), (0.75, "GOOD STRIKE", 0.8), (1.01, "LATE STRIKE", 0.55))

# The fight
REEL_SPEED = 20.0
OFF_MARK_DRAG = 0.5             # off the marker, a fish drags out this share of its swim (the line stays taut)
OFF_MARK_TENSION = (0.25, 0.8)  # what being off the marker adds to the tension, lightest to heaviest fish
SNAP_TENSION = 0.9              # the line takes strain above this tension
STRAIN_RATE = 2.6               # strain a second for each unit of tension above it (at 1 the line gives way)
MAX_TENSION = 1.7
# How hard a running fish pulls on a held line, by its heft: only the tiniest can be simply held
PULL_FORCE = ((0.0, 1.05), (0.06, 1.2), (0.1, 1.75), (1.0, 1.75))
FIGHT_ANCHOR = rod_points(20.0, 0.0)[-1]   # the fight measures the line from here: not the moving tip (see below)
TINY_HEFT = 0.06                # a fish no heftier than this never rages
ENDURANCE = 2.4                 # how long fish fight, for all kinds
MAX_ENDURANCE = 1.9             # the biggest are hard through their pull, not through taking for ever
STRAIN_EASE_HOLDING = 0.08      # the strain the line sheds a second while the reel is still held
STRAIN_EASE_LET_GO = 0.6        # and once it is let go
SLACK_TENSION = 0.1             # a line this slack lets the hook work loose, slowly
# The fish's power, 0 to 1: full, and it is lost
FRESH_POWER = (0.4, 0.5)        # what it starts with
FRESH = 0.5                     # at this power it fights as a fresh fish; above it, harder still
FISH_RECOVERY = 0.045           # the power it gets back a second while the line is let go
OVERLOAD_POWER = (0.38, 0.42)   # what a line giving way hands it, lightest to heaviest fish
OVERLOAD_GIVE = 8.0             # and the line it runs out then, low px
OVERLOAD_STRAIN = 0.5           # the strain left on the line after that
LEAP_HELD_POWER = 0.15          # what holding on to a leaping fish hands it, for a perfect strike's hook
SHAKE_SLACK_POWER = 0.08        # what a slack line on a fish shaking its head adds a second, likewise
# The marker on the bar, in shares of the bar's width, lightest to heaviest fish
BAR_ZONE = (0.085, 0.04)        # half the width of the zone to keep the mouse in
BAR_FALLOFF = 1.0               # the grip is gone this many zone widths outside it
BAR_SPEED = (0.16, 0.40)        # its average speed a second, fresh fish
BAR_MODE_SPEED = {"run": 1.15, "shake": 1.2, "rest": 0.7, "brace": 0.5, "rage": 1.35}
BAR_LEG = (0.22, 0.7)           # how far it swings before turning back
BAR_EDGE = 0.05                 # it stays this far from the bar's ends
# The rage
RAGE_WEIGHT = (0.8, 2.8)        # against the other moves' weights, about 5 together when fresh
RAGE_FROM_STAMINA = 0.3         # a fish more tired than this does not rage
BRACE_S = (0.65, 0.42)          # the warning before it breaks loose
RAGE_S = (1.2, 2.0)             # how long it lasts, this times 1 + RAGE_S_HEFT * heft
RAGE_S_HEFT = 0.6
RAGE_SPEED = 2.0                # its speed, of the kind's fair swim
RAGE_PULL = (1.05, 1.55)        # how hard it pulls on a held line when fresh
RAGE_DRAIN = 0.06               # the stamina the rage costs it a second, on a let-go line
RAGE_REST_S = 0.9               # spent after it: the moment to reel
LAND_STAMINA = 0.16             # beaten: it can be netted near the bank
LAND_ZONE = (BANK_EDGE + 26, WATER_Y + 22)
NET_S = 0.8
LIFT_S = 0.5
CARD_S = 6.0
CARD_FISH_W, CARD_FISH_H = 300, 130   # the landed fish is shown at most this big on its card

_TOTAL_W = SCREEN_WIDTH + SIDEBAR_WIDTH
_TOP_BAR, _BOTTOM_BAR, _MARGIN = 44, 46, 6
_CANVAS_W = SCENE_W + 2 * _MARGIN
_CANVAS_H = _TOP_BAR + SCENE_H + 2 * _MARGIN + _BOTTOM_BAR
_SCENE_RECT = pygame.Rect(_MARGIN, _TOP_BAR + _MARGIN, SCENE_W, SCENE_H)
_BAR = pygame.Rect(44, 42, SCENE_W - 88, 26)   # the fight's bar, in the scene's pixels
_METER_W, _METER_H = 260, 9                    # the line's strain and the fish's strength under it

_INK = (44, 32, 22)
_PAPER = (236, 222, 186)
_BRASS, _BRASS_LIGHT, _BRASS_DARK = (198, 164, 92), (232, 206, 140), (120, 92, 44)
_GOOD, _BAD, _WARN = (150, 214, 120), (226, 110, 86), (236, 186, 96)

_EXIT_TITLE = "Exit Mini Game now?"
_EXIT_TEXT = "Your coins are kept; the worms left are lost."
_EXIT_FISH_TEXT = "The fish on your line gets away."

READY, DRAW, FLIGHT, WAIT, FIGHT, LANDING, CARD, RETRIEVE, STUCK, DONE = (
    "ready", "draw", "flight", "wait", "fight", "landing", "card", "retrieve", "stuck", "done")


def fish_coins(fish: Fish, cast_mult: float) -> float:
    """What a landed fish pays: its kind's value, times its size against the usual, times the cast's grade."""
    return round(fish.species.value * (fish.cm / fish.species.avg_cm) * cast_mult, 2)


def cast_grade(seconds_off: float) -> Tuple[str, float, Tuple[int, int, int]]:
    for limit, label, mult, colour in CAST_GRADES:
        if abs(seconds_off) <= limit:
            return label, mult, colour
    return CAST_GRADES[-1][1:]


def strike_grade(reaction: float, window: float) -> Tuple[str, float]:
    for share, label, hold in STRIKE_GRADES:
        if reaction <= max(0.3 if share < 0.5 else 0.0, share * window):
            return label, hold
    return STRIKE_GRADES[-1][1:]


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if x < lo else hi if x > hi else x


def _lerp(ends: Tuple[float, float], k: float) -> float:
    return ends[0] + (ends[1] - ends[0]) * k


def _pull_force(heft: float) -> float:
    """PULL_FORCE at a fish's heft, between its points."""
    for (h0, f0), (h1, f1) in zip(PULL_FORCE, PULL_FORCE[1:]):
        if heft <= h1:
            return f0 + (f1 - f0) * _clamp((heft - h0) / (h1 - h0))
    return PULL_FORCE[-1][1]


# ----------------------------------------------------------------------
# Sounds made from sine waves (none without a mixer)
# ----------------------------------------------------------------------

def _synth(seconds: float, wave: Callable[[float], float], volume: float = 0.5) -> Optional[pygame.mixer.Sound]:
    init = pygame.mixer.get_init()
    if not init or abs(init[1]) != 16:
        return None
    rate, _size, channels = init
    samples = array("h")
    for i in range(int(rate * seconds)):
        v = max(-1.0, min(1.0, volume * wave(i / rate)))
        samples.extend([int(v * 32767)] * channels)
    try:
        return pygame.mixer.Sound(buffer=samples.tobytes())
    except pygame.error:
        return None


def _make_sounds() -> dict:
    rnd = random.Random(7)
    noise = [rnd.uniform(-1, 1) for _ in range(4096)]
    return {
        # The reel's pawl clicking over a tooth
        "tick": _synth(0.03, lambda t: math.exp(-t / 0.004) * (0.6 * math.sin(math.tau * 2600 * t)
                                                               + 0.5 * noise[int(t * 44100) % 4096]), 0.5),
        # The line snapping: a high twang falling
        "twang": _synth(0.6, lambda t: math.exp(-t / 0.18) * math.sin(math.tau * (980 - 500 * t) * t)
                        + 0.4 * math.exp(-t / 0.02) * noise[int(t * 44100) % 4096], 0.5),
        # The taut line humming (a seamless loop: every partial whole cycles in half a second)
        "hum": _synth(0.5, lambda t: (0.55 * math.sin(math.tau * 196 * t) + 0.3 * math.sin(math.tau * 392 * t)
                                      + 0.15 * math.sin(math.tau * 590 * t)) * (0.8 + 0.2 * math.sin(math.tau * 6 * t)), 0.4),
    }


# ----------------------------------------------------------------------
# The fight
# ----------------------------------------------------------------------

class Fight:
    """A hooked fish against the line (see the module)."""

    def __init__(self, fish: Fish, hold: float, tip: Tuple[float, float], rng: random.Random,
                 hand: float = 0.5) -> None:
        self.fish, self.hold, self.rng = fish, hold, rng
        sp = fish.species
        self.size = fish.cm / sp.avg_cm
        self.power = _clamp(sp.power * self.size ** 0.8, 0.25, 1.3)
        self.heft = (self.power - 0.25) / 1.05     # 0 the lightest fish, 1 the heaviest: the fight's difficulty
        self.zone = _lerp(BAR_ZONE, self.heft)
        self.force = _pull_force(self.heft)
        self.endurance = min(MAX_ENDURANCE, ENDURANCE * sp.stamina * self.size ** 0.5)
        self.stamina = rng.uniform(*FRESH_POWER)
        self.line = math.hypot(fish.x - tip[0], fish.y - tip[1]) + 1
        self.T = 0.35
        self.strain = 0.0
        self.t = 0.0
        self.track = 1.0                # how well the mouse is under the marker, 0 to 1
        self.leg_dir = rng.choice((-1, 1))
        self.recentre(hand)             # so the fight does not start with the mouse off the marker
        self.mode, self.mode_t = "run", rng.uniform(0.8, 1.5)
        self.dir = self._run_dir(away=True)
        self.jump_phase = ""
        self.held_in_air = 0.0
        self.air_v = [0.0, 0.0]

    @property
    def vigor(self) -> float:
        """How hard it fights: 1 as a fresh fish, more as its power climbs."""
        return self.stamina / FRESH

    def _run_dir(self, away: bool) -> Tuple[float, float]:
        vx = 1.0 if away else -1.0
        vy = self.rng.uniform(-0.5, 0.8)
        n = math.hypot(vx, vy)
        return vx / n, vy / n

    def recentre(self, hand: float) -> None:
        """The marker over the mouse, setting off from there."""
        self.bar_x = _clamp(hand, BAR_EDGE, 1 - BAR_EDGE)
        self.leg_from = self.leg_to = self.bar_x
        self.leg_t, self.leg_len = 1.0, 1.0

    def _new_leg(self) -> None:
        """The marker sets off for its next turning point, on the other side of it."""
        side = -self.leg_dir
        room = (self.bar_x - BAR_EDGE) if side < 0 else (1 - BAR_EDGE - self.bar_x)
        if room < BAR_LEG[0]:
            side, room = -side, 1 - 2 * BAR_EDGE - room
        self.leg_dir = side
        self.leg_len = min(room, self.rng.uniform(*BAR_LEG))
        self.leg_from, self.leg_to = self.bar_x, self.bar_x + side * self.leg_len
        self.leg_t = 0.0

    def _swing(self, dt: float) -> None:
        """The marker eases from turning point to turning point, faster for a bigger, fresher fish."""
        speed = _lerp(BAR_SPEED, self.heft) * BAR_MODE_SPEED.get(self.mode, 1.0) * (0.65 + 0.35 * self.vigor)
        self.leg_t += dt * speed / max(0.01, self.leg_len)
        k = _clamp(self.leg_t)
        self.bar_x = self.leg_from + (self.leg_to - self.leg_from) * k * k * (3 - 2 * k)
        if self.leg_t >= 1:
            self._new_leg()

    def tracking(self, hand: float) -> float:
        """How well the mouse (as a share of the bar) is under the marker: 1 in its zone, 0 well outside it."""
        return _clamp(1 - (abs(hand - self.bar_x) - self.zone) / (self.zone * BAR_FALLOFF))

    def _start_rage(self) -> None:
        self.mode = "rage"
        self.mode_t = self.rng.uniform(*RAGE_S) * (1 + RAGE_S_HEFT * self.heft)
        self.dir = self._run_dir(away=True)
        self._new_leg()

    def _pick(self) -> None:
        s = min(1.0, self.vigor)
        sp = self.fish.species
        options = [("run", 2.5 * s + 0.4), ("shake", 1.4), ("rest", 0.5 + 2.0 * (1 - s)),
                   ("dive", 1.0 if self.fish.zone[2] == "bottom" else 0.3)]
        if sp.jumps > 0 and s > 0.25 and self.fish.y < WATER_Y + 45:
            options.append(("jump", sp.jumps * 3 * s))
        if s > RAGE_FROM_STAMINA and self.heft > TINY_HEFT:
            options.append(("brace", _lerp(RAGE_WEIGHT, self.heft)))
        total = sum(w for _, w in options)
        r = self.rng.uniform(0, total)
        for mode, w in options:
            r -= w
            if r <= 0:
                break
        self.mode = mode
        if mode == "run":
            self.dir = self._run_dir(away=self.rng.random() < 0.75)
            self.mode_t = self.rng.uniform(0.8, 2.0)
        elif mode == "shake":
            self.mode_t = self.rng.uniform(0.7, 1.4)
        elif mode == "rest":
            self.mode_t = self.rng.uniform(0.7, 1.6)
        elif mode == "dive":
            self.dir = (0.3, 0.95)
            self.mode_t = self.rng.uniform(0.8, 1.4)
        elif mode == "brace":
            self.mode_t = _lerp(BRACE_S, self.heft)
        else:
            self.jump_phase = "rise"
            self.mode_t = 3.0

    def update(self, dt: float, tip: Tuple[float, float], reeling: bool, hand: float) -> List[str]:
        """dt seconds of the fight, hand being the mouse as a share of the bar; returns what happened:
        "free" (its power is full: the only way to lose it), "overload", "wrench", "rise", "jump_out", "jump_in", "kept", "brace", "rage", "calm", "land"."""
        f, sp = self.fish, self.fish.species
        events: List[str] = []
        self.t += dt
        self._swing(dt)
        self.track = self.tracking(hand)
        strength = 0.3 + 0.7 * self.vigor
        if self.mode == "jump":
            return self._update_jump(dt, tip, reeling, events)
        self.mode_t -= dt
        if self.mode_t <= 0:
            if self.mode == "brace":
                self._start_rage()
                events.append("rage")
            elif self.mode == "rage":
                self.mode, self.mode_t = "rest", RAGE_REST_S
                events.append("calm")
            else:
                self._pick()
                if self.mode == "jump":
                    events.append("rise")
                    return events
                if self.mode == "brace":
                    events.append("brace")
        raging = self.mode in ("brace", "rage")
        if f.x < BANK_EDGE + 26 and self.stamina >= LAND_STAMINA and self.mode != "run" and not raging:
            self.mode, self.mode_t, self.dir = "run", 1.3, self._run_dir(away=True)

        speed = sp.speed
        if self.mode == "run":
            vx, vy = self.dir[0] * speed * 1.5 * strength, self.dir[1] * speed * 1.5 * strength
        elif self.mode == "rage":
            vx, vy = self.dir[0] * speed * RAGE_SPEED * strength, self.dir[1] * speed * RAGE_SPEED * strength
        elif self.mode in ("shake", "brace"):
            vx, vy = self.dir[0] * speed * 0.15 * strength, 0.0
            f.facing = 1 if int(self.t * (16 if self.mode == "brace" else 9)) % 2 else -1
        elif self.mode == "dive":
            vx, vy = self.dir[0] * speed * strength, self.dir[1] * speed * strength
        else:
            vx, vy = speed * 0.08, speed * 0.05
        nx, ny = f.x + vx * dt, f.y + vy * dt
        rx, ry = nx - tip[0], ny - tip[1]
        d = max(0.01, math.hypot(rx, ry))
        ux, uy = rx / d, ry / d
        away = max(0.0, vx * ux + vy * uy)
        out = away / (speed * 1.5)
        pull = out * self.force
        if self.mode == "rage":
            pull = _lerp(RAGE_PULL, self.heft) * (0.6 + 0.4 * self.vigor)
        elif self.mode == "shake":
            pull += 0.25 * self.power * abs(math.sin(self.t * 26))
        off = 1 - self.track
        if reeling:
            gain = 0.0 if self.mode == "rage" else REEL_SPEED * (1 - 0.65 * min(1.0, pull)) * self.track
            self.line = max(5.0, self.line - gain * dt + OFF_MARK_DRAG * off * away * dt)
            if d > self.line:
                nx, ny = tip[0] + ux * self.line, tip[1] + uy * self.line
                target = 0.24 + 0.78 * pull + _lerp(OFF_MARK_TENSION, self.heft) * off
            else:
                target = 0.05
        else:
            if d > self.line:
                give = self.line + (d - self.line) * (0.55 + 0.35 * off)
                nx, ny = tip[0] + ux * give, tip[1] + uy * give
                self.line = give
                target = 0.08 + 0.3 * pull
            else:
                target = 0.04
        nx, ny = in_water(nx, ny, 1.5)
        if dt > 0:
            f.vx, f.vy = (nx - f.x) / dt, (ny - f.y) / dt
        f.x, f.y = nx, ny
        if self.mode not in ("shake", "brace") and abs(f.vx) > 1:
            f.facing = 1 if f.vx > 0 else -1
        f.tail += dt * (5 + 10 * strength) * (2.0 if raging else 1.0)
        self.T += (min(MAX_TENSION, target) - self.T) * min(1.0, dt * 9)
        self._strain_and_slack(dt, events, reeling)
        if reeling:
            drain = FRESH * (0.04 + 0.16 * self.T) * (0.35 + 0.65 * self.track) / self.endurance
        elif self.mode == "rage":
            drain = FRESH * RAGE_DRAIN / self.endurance
        else:
            drain = -FISH_RECOVERY * (1.5 - 0.5 * self.hold)   # a let-go line: it gets its power back
        self.stamina = _clamp(self.stamina - drain * dt)
        f.tired = self.stamina < LAND_STAMINA and self.mode == "rest"
        if self.stamina < LAND_STAMINA and f.x < LAND_ZONE[0] and f.y < LAND_ZONE[1]:
            events.append("land")
        return events

    def _strain_and_slack(self, dt: float, events: List[str], reeling: bool) -> None:
        if self.T > SNAP_TENSION:
            self.strain += (self.T - SNAP_TENSION) * dt * STRAIN_RATE
        else:
            self.strain = max(0.0, self.strain - dt * (STRAIN_EASE_HOLDING if reeling else STRAIN_EASE_LET_GO))
        if self.strain >= 1:
            self.strain = OVERLOAD_STRAIN
            self.stamina = _clamp(self.stamina + _lerp(OVERLOAD_POWER, self.heft))
            self.line += OVERLOAD_GIVE
            events.append("overload")
        if self.mode == "shake" and self.T < 0.17:
            self.stamina = _clamp(self.stamina + SHAKE_SLACK_POWER * (1.3 - self.hold) * dt)
        if self.stamina >= 1:
            events.append("free")

    def _update_jump(self, dt: float, tip: Tuple[float, float], reeling: bool, events: List[str]) -> List[str]:
        f = self.fish
        if self.jump_phase == "rise":
            f.steer(dt, f.x + 12 * (1 if f.facing > 0 else -1), WATER_Y + 1, f.species.speed * 2.2, turn=8)
            self.T += (0.3 - self.T) * min(1.0, dt * 6)
            self.mode_t -= dt
            if f.y <= WATER_Y + 3 or self.mode_t <= 0:
                self.jump_phase = "air"
                f.above_water = True
                self.air_v = [(1 if self.rng.random() < 0.7 else -1) * 18.0, -78.0]
                f.facing = 1 if self.air_v[0] > 0 else -1
                self.held_in_air = 0.0
                events.append("jump_out")
        else:
            f.x = min(max(f.x + self.air_v[0] * dt, BANK_EDGE + 6), LOW_W - 4)
            self.air_v[1] += 220 * dt
            f.y += self.air_v[1] * dt
            f.angle = -math.degrees(math.atan2(self.air_v[1], abs(self.air_v[0]))) * 0.7 * f.facing
            f.tail += dt * 20
            if reeling:
                self.held_in_air += dt
            self.T += ((1.15 if reeling else 0.1) - self.T) * min(1.0, dt * 9)
            if f.y >= WATER_Y and self.air_v[1] > 0:
                f.above_water = False
                f.angle = 0.0
                f.y = WATER_Y + 2
                events.append("jump_in")
                if self.held_in_air > 0.2:
                    self.stamina = _clamp(self.stamina + LEAP_HELD_POWER * (1.25 - self.hold))
                    events.append("wrench")
                else:
                    events.append("kept")
                self.mode, self.mode_t = "run", self.rng.uniform(0.6, 1.2)
                self.dir = self._run_dir(away=True)
        self.line = max(self.line, math.hypot(f.x - tip[0], f.y - tip[1]))
        self._strain_and_slack(dt, events, reeling)
        return events


# ----------------------------------------------------------------------
# The minigame
# ----------------------------------------------------------------------

class FishingMinigame(MinigameOverlay):
    """Full-screen overlay for the fishing minigame (see the module)."""

    def __init__(self, screen: pygame.Surface, game, rng: Optional[random.Random] = None) -> None:
        self.screen = screen
        self.game = game
        self.active = True
        self.rng = rng or random.Random()
        self.canvas = pygame.Surface((_CANVAS_W, _CANVAS_H))
        sw, sh = screen.get_size()
        self.canvas_rect = self.canvas.get_rect(center=(sw // 2, sh // 2))
        try:
            roman = os.path.join(FONTS_PATH, "RomanAntique.ttf")
            medici = os.path.join(FONTS_PATH, "Medici Text.ttf")
            self.font = pygame.font.Font(roman, 18)
            self.font_small = pygame.font.Font(roman, 15)
            self.font_grade = pygame.font.Font(roman, 28)
            self.font_large = pygame.font.Font(medici, 28)
            self.font_title = pygame.font.Font(medici, 40)
        except Exception:
            self.font = pygame.font.SysFont("georgia", 18)
            self.font_small = pygame.font.SysFont("georgia", 15)
            self.font_grade = pygame.font.SysFont("georgia", 28, bold=True)
            self.font_large = pygame.font.SysFont("georgia", 28, bold=True)
            self.font_title = pygame.font.SysFont("georgia", 40, bold=True)

        weather = Conditions.of(getattr(game, "weather", None))
        when = getattr(getattr(game, "state", None), "date", None)
        self.scene = PondScene(when, weather, self.rng)
        self.pond = Pond(self.rng, self.scene.hour, self.scene.season, weather.rain, weather.storm,
                         weather.snow, weather.clouds)
        self.hook = Hook()
        self.sounds = _make_sounds()
        self._hum_channel: Optional[pygame.mixer.Channel] = None

        self.t = 0.0
        self.phase = READY
        self.worms = WORMS
        self.total_worms = WORMS
        self.baited = True
        self.catches: List[dict] = []
        self.coins = 0.0
        # The rod
        self.theta, self.omega, self.theta_target = READY_THETA, 0.0, READY_THETA
        self.kick = 0.0
        self.press_x = 0
        # The bait, the float, the line
        self.hook_x = self.hook_y = 0.0
        self.vx = self.vy = 0.0
        self.float_x = 0.0
        self.float_dip = 0.0
        self.float_under = False
        self.leader = LEADER_START
        self.settled_t = 0.0
        self.wait_t = 0.0
        self.take_t = 0.0
        self.cast_label, self.cast_mult, self.cast_colour = "", 1.0, (255, 255, 255)
        self.strike_label = ""
        self.tangled = False
        # Input
        self.lmb = False
        self.lmb_t = 0.0
        self.mouse_trail: Deque[Tuple[float, float]] = deque()
        self.strike_cool = 0.0
        self.twitches: Deque[float] = deque()
        self.twitch_age = 99.0
        self.lean = 0.0
        self.hand = 0.5                 # the mouse as a share of the fight's bar
        self._tick_t = 0.0
        # The fight and after
        self.fight: Optional[Fight] = None
        self.landing_t = 0.0
        self.landed: Optional[Fish] = None
        self.card: Optional[dict] = None
        self.card_t = 0.0
        self.retrieve_from: Tuple[float, float] = (0.0, 0.0)
        self.stuck_t = 0.0
        self.hook_lost = False         # retrieving a line whose hook has ripped off
        self.popups: List[list] = []     # text, colour, x, y (scene px), age, life, font
        self._guide = pygame.Surface((2, SCENE_H - _BAR.bottom), pygame.SRCALPHA)   # dashes from the marker down
        for y in range(0, self._guide.get_height(), 14):
            self._guide.fill((255, 244, 214, 70), (0, y, 2, 7))
        # The end
        self.close_rect = pygame.Rect(0, 0, 160, 44)
        self.exit_asked = False        # "Exit Mini Game now?" is open
        self.exit_back_rect = pygame.Rect(0, 0, 130, 40)
        self.exit_yes_rect = pygame.Rect(0, 0, 130, 40)
        self._booked = False
        stats = self._stats()
        self.highscore = getattr(stats, "fishing_highscore", 0.0) if stats else 0.0
        self.new_highscore = False

    # ------------------------------------------------------------------
    # Small helpers
    # ------------------------------------------------------------------

    def _stats(self):
        depot = getattr(self.game, "depot", None)
        return getattr(depot, "stats", None)

    def _to_scene(self, pos: Tuple[int, int]) -> Tuple[float, float]:
        return (pos[0] - self.canvas_rect.left - _SCENE_RECT.left, pos[1] - self.canvas_rect.top - _SCENE_RECT.top)

    def _tip(self) -> Tuple[float, float]:
        return rod_points(self.theta + self.kick, self._bend())[-1]

    def _bend(self) -> float:
        if self.phase == FIGHT and self.fight is not None:
            return 55 * min(1.1, self.fight.T)
        if self.phase == DRAW:
            return _clamp(-self.omega * 0.035, -30, 30)
        if self.phase == WAIT:
            return 6 + 10 * self.float_dip
        if self.phase == STUCK:
            return 0.0 if self.stuck_t >= STUCK_RIP_AT else 40 + 12 * math.sin(self.stuck_t * 38)
        return _clamp(-self.omega * 0.02, -20, 20)

    def _popup(self, text: str, colour, low_pos: Tuple[float, float], big: bool = False, life: float = 1.6) -> None:
        self.popups.append([text, colour, low_pos[0] * PX, low_pos[1] * PX, 0.0, life, big])

    def _play(self, name: str, volume: float = 1.0) -> None:
        sounds = getattr(self.game, "sounds", {}) or {}
        if name.endswith("_"):
            names = [n for n in sounds if n.startswith(name)]
            if not names:
                return
            name = self.rng.choice(names)
        sound = sounds.get(name)
        if sound is None:
            return
        try:
            channel = sound.play()
        except pygame.error:
            return
        if channel is not None:
            channel.set_volume(volume)

    def _play_synth(self, name: str, volume: float = 1.0) -> None:
        sound = self.sounds.get(name)
        if sound is not None:
            channel = sound.play()
            if channel is not None:
                channel.set_volume(volume)

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------

    def _ask_to_exit(self) -> None:
        """Ask before leaving a session under way. A button held now is let go of, its release going unseen."""
        self.exit_asked = True
        self.lmb = False
        if self.phase == DRAW:
            self.phase = READY
            self.theta_target = READY_THETA
        if self._hum_channel is not None:
            self._hum_channel.pause()

    def _go_back(self) -> None:
        """On with the session, where it stood. The mouse may be far from the marker now: it starts over it."""
        self.exit_asked = False
        self.mouse_trail.clear()
        if self.fight is not None:
            self.fight.recentre(self.hand)
        if self._hum_channel is not None:
            self._hum_channel.unpause()

    def _handle_exit_question(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self._go_back()
            elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self._leave()
        elif event.type == pygame.MOUSEMOTION:
            self._track_mouse(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self._track_mouse(event.pos)
            pos = (event.pos[0] - self.canvas_rect.left, event.pos[1] - self.canvas_rect.top)
            if self.exit_back_rect.collidepoint(pos):
                self._go_back()
            elif self.exit_yes_rect.collidepoint(pos):
                self._leave()

    def _track_mouse(self, pos: Tuple[int, int]) -> None:
        sx, _ = self._to_scene(pos)
        self.lean = _clamp((sx - SCENE_W * 0.42) / (SCENE_W * 0.3), -1.0, 1.0)
        self.hand = (sx - _BAR.left) / _BAR.width

    def handle_event(self, event: pygame.event.Event) -> None:
        if self.exit_asked:
            self._handle_exit_question(event)
            return
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                if self.phase == DONE:          # the session is over: nothing is lost by leaving
                    self._leave()
                else:
                    self._ask_to_exit()
            elif event.key == pygame.K_SPACE:
                self._strike()
            return
        if event.type == pygame.MOUSEWHEEL:
            if self.phase in (READY, DRAW):
                lo, hi = LEADER_RANGE
                self.leader = min(hi, max(lo, self.leader - event.y * LEADER_STEP))
                self.settled_t = 0.0
            return
        if event.type == pygame.MOUSEMOTION:
            now = pygame.time.get_ticks() / 1000.0
            self.mouse_trail.append((now, event.pos[1]))
            while self.mouse_trail and now - self.mouse_trail[0][0] > STRIKE_WINDOW_S:
                self.mouse_trail.popleft()
            if self.phase == DRAW:
                self.theta_target = min(THETA_RANGE[1], max(THETA_RANGE[0],
                                        READY_THETA + (event.pos[0] - self.press_x) * DEG_PER_PX))
            elif self.phase == WAIT and len(self.mouse_trail) >= 2:
                t0, y0 = self.mouse_trail[0]
                rise = y0 - event.pos[1]
                if rise >= STRIKE_PX and rise / max(0.008, now - t0) >= STRIKE_SPEED:
                    self.mouse_trail.clear()
                    self._strike()
            self._track_mouse(event.pos)
            return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.lmb, self.lmb_t = True, 0.0
            if self.phase == DONE:
                pos = (event.pos[0] - self.canvas_rect.left, event.pos[1] - self.canvas_rect.top)
                if self.close_rect.collidepoint(pos):
                    self._leave()
            elif self.phase == CARD:
                self._after_card()
                self.lmb = False
            elif self.phase == READY:
                self.phase = DRAW
                self.press_x = event.pos[0]
            return
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            pressed, held = self.lmb, self.lmb_t
            self.lmb = False
            if not pressed:                     # the press was on the exit question's button
                return
            if self.phase == DRAW:
                self._release_cast()
            elif self.phase == WAIT and held < TAP_S:
                self._twitch()

    def _leave(self) -> None:
        """Back to the map, the share of HOURS_OF_WORK the worms used took."""
        if self.phase != DONE:
            self._finish()
        used = (self.total_worms - self.worms) / max(1, self.total_worms)
        state = getattr(self.game, "state", None)
        if state is not None and hasattr(state, "date"):
            self.pass_time(state, HOURS_OF_WORK * min(1.0, used))
        self._stop_hum()
        self.active = False

    # ------------------------------------------------------------------
    # The cast
    # ------------------------------------------------------------------

    def _release_cast(self) -> None:
        omega = self.omega                          # degrees a second, + towards the water
        if omega < MIN_WHIP_DEG_S:
            self._popup("Drag back, then whip it forward!", _WARN, (130, 30))
            self.phase = READY
            self.theta_target = READY_THETA
            return
        power = math.radians(omega) * 40.0 / V_FULL
        early = (SWEET_THETA - self.theta) / omega   # seconds before the sweet spot (negative: after it)
        label, mult, colour = cast_grade(early)
        angle = math.radians(_clamp(LAUNCH_ANGLE + early * TIMING_DEG_PER_S, -15, 80))
        speed = V_LAUNCH * min(1.0, power)
        self.cast_power = power
        self.tangled = power > TANGLE_POWER
        if self.tangled:
            speed *= 0.35
            label, mult, colour = "TANGLED LINE", CAST_GRADES[-1][2], _BAD
        self.cast_label, self.cast_mult, self.cast_colour = label, mult, colour
        self.hook_x, self.hook_y = self._tip()
        self.vx, self.vy = speed * math.cos(angle), -speed * math.sin(angle)
        self.phase = FLIGHT
        self.theta_target = 48.0
        self._play("swoosh_", 0.5 + 0.4 * min(1.0, power))

    def _land_cast(self) -> None:
        x = min(self.hook_x, LOW_W - 5)
        if x <= BANK_EDGE + 4:
            self._popup("Too short!", _WARN, (max(x, 60), 52))
            self._start_retrieve()
            return
        soft = self.cast_label.startswith("PERFECT")
        strength = 0.25 if soft else 0.55 if self.cast_mult >= 1.0 else 0.95
        self.scene.add_splash(x, strength)
        self._play("splash_", 0.12 + 0.35 * strength)
        if soft:
            self.twitch_age = 0.0       # a soft landing draws the fish rather than scaring them
        else:
            self.pond.scare(x, WATER_Y + 10, 18 + 30 * strength, 2 + 5 * strength, self.hook)
        self._popup(self.cast_label, self.cast_colour, (x, WATER_Y - 18), big=True)
        feet = (x - BANK_EDGE) / PX_PER_FOOT
        self._popup(f"{feet:.0f} feet out", (226, 226, 210), (x, WATER_Y - 6), life=1.4)
        self.hook_x, self.hook_y = x, WATER_Y + 1
        self.float_x = x
        self.float_under = False
        self.settled_t = 0.0
        self.wait_t = 0.0
        self.phase = WAIT

    # ------------------------------------------------------------------
    # Waiting and striking
    # ------------------------------------------------------------------

    def _twitch(self) -> None:
        self.hook_y -= 4
        self.hook_x = max(BANK_EDGE + 4, self.hook_x - 1.0)
        self.float_dip = 0.8
        self.twitch_age = 0.0
        self.twitches.append(self.t)
        self.settled_t = 0.0
        self._play_synth("tick", 0.2)

    def _strike(self) -> None:
        if self.phase != WAIT or self.strike_cool > 0:
            return
        self.strike_cool = 0.45
        self.kick = -26.0
        self._play("swoosh_", 0.25)
        fish = self.hook.engaged
        if fish is not None and fish.state == TAKE:
            reaction = self.t - self.take_t
            label, hold = strike_grade(reaction, fish.species.take_window)
            self.strike_label = label
            self._start_fight(fish, hold, label)
            return
        if fish is not None and fish.state in (APPROACH, INSPECT, NIBBLE):
            self._popup("Only minnows!" if fish.species.minnow else "Too early!", _WARN, (self.hook_x, WATER_Y - 12))
            fish.flee(self.hook, self.rng)
        else:
            self.pond.scare(self.hook_x, self.hook_y, 14, 3, self.hook)
        self.hook_y = max(WATER_Y + 2, self.hook_y - 8)
        self.float_dip = 1.0
        self.settled_t = 0.0

    def _update_wait(self, dt: float) -> None:
        reeling = self.lmb and self.lmb_t >= TAP_S
        fish = self.hook.engaged
        taking = fish is not None and fish.state == TAKE
        if taking:
            self.hook_x, self.hook_y = fish.mouth
            self.float_x += (fish.x - self.float_x) * min(1.0, dt * 1.5)
            self.float_under = True
        else:
            self.float_under = False
            if reeling:
                self.float_x -= REEL_IDLE_SPEED * dt
                self._reel_ticks(dt, 0.08)
            floor = bottom_y(self.hook_x) - 1
            if reeling:
                target = min(WATER_Y + self.leader * 0.55, floor - CLEAR_OF_BOTTOM)
            else:
                target = min(WATER_Y + self.leader, floor)
            self.hook_x += (self.float_x - self.hook_x) * min(1.0, dt * (1.2 if reeling else 2.5))
            if self.hook_y < target:
                self.hook_y = min(target, self.hook_y + SINK_SPEED * dt)
            else:
                self.hook_y = max(target, self.hook_y - 30 * dt)
            if abs(self.hook_y - target) < 1 and not reeling:
                self.settled_t += dt
            else:
                self.settled_t = 0.0
            if not reeling and WATER_Y + self.leader >= floor and self.hook_y >= floor - 0.3:
                self._start_stuck()             # set too deep: it has sunk onto the bottom
                return
            near_bottom = self.hook_y >= floor - CLEAR_OF_BOTTOM - 1
            if reeling and near_bottom and any(x0 <= self.hook_x <= x1 for x0, x1 in SNAGS) \
                    and self.rng.random() < SNAG_RATE * dt:
                self._start_stuck()             # dragged over the roots
                return
            if self.float_x <= BANK_EDGE + 3:
                self._start_retrieve()
                return
        self.hook.reeling = reeling
        self.wait_t += dt
        self.hook.alluring = self.baited and not taking and not reeling and self.wait_t > 0.4

    def _start_stuck(self) -> None:
        """The hook has caught on the bottom: the fish keep off, the rod tugs at it."""
        self.phase = STUCK
        self.stuck_t = 0.0
        self.hook.alluring = False
        if self.hook.engaged is not None:
            self.hook.engaged.flee(self.hook, self.rng, 3.0)
        self.hook.engaged = None
        self.scene.add_puff(self.hook_x, self.hook_y)
        self._play_synth("tick", 0.35)

    def _update_stuck(self, dt: float) -> None:
        before = self.stuck_t
        self.stuck_t += dt
        if self.stuck_t < STUCK_RIP_AT:
            # Tug, tug: the rod jerks back, the float is drawn under, mud puffs up
            self.kick = -10 * abs(math.sin(self.stuck_t * 19))
            self.float_under = True
            if int(self.stuck_t * 6) != int(before * 6):
                self.scene.add_puff(self.hook_x, self.hook_y)
                self._play_synth("tick", 0.3)
        elif before < STUCK_RIP_AT:
            self._play_synth("twang", 0.5)
            self.scene.add_puff(self.hook_x, self.hook_y)
            self._popup("Hook ripped off!", _BAD, (self.float_x, WATER_Y - 14), big=True, life=2.0)
            self.kick = -30.0
            self.float_under = False
            self._use_worm()
        if self.stuck_t >= STUCK_S:
            self.hook_lost = True
            self._start_retrieve()

    def _reel_ticks(self, dt: float, every: float) -> None:
        self._tick_t -= dt
        if self._tick_t <= 0:
            self._tick_t = every
            self._play_synth("tick", 0.18)

    def _pond_events(self, events: List[tuple]) -> None:
        for ev in events:
            kind = ev[0]
            if kind == "nibble":
                self.float_dip = 1.0 + (0.4 if ev[1].species.minnow else 0.9)
                self.scene.add_ring(self.float_x, 1.6)
                self._play_synth("tick", 0.3)
            elif kind == "take":
                self.take_t = self.t
                self.scene.add_ring(self.float_x, 3.5)
                self._play("splash_", 0.12)
            elif kind == "stolen":
                if self.phase == WAIT:
                    self._popup("Too late: the worm is gone!", _BAD, (self.float_x, WATER_Y - 12))
                    self._use_worm()
                    self._start_retrieve()
            elif kind == "bubble":
                self.scene.add_bubble(ev[1], ev[2])
            elif kind == "rise":
                self.scene.add_ring(ev[1], 3.0)

    def _use_worm(self) -> None:
        self.worms = max(0, self.worms - 1)
        self.baited = False

    # ------------------------------------------------------------------
    # The fight, the landing
    # ------------------------------------------------------------------

    def _start_fight(self, fish: Fish, hold: float, label: str) -> None:
        self.hook.engaged = None
        self.hook.alluring = False
        fish.state = HOOKED
        self.fight = Fight(fish, hold, FIGHT_ANCHOR, self.rng, self.hand)
        self.phase = FIGHT
        colour = _GOOD if hold >= 1.0 else (226, 226, 200) if hold >= 0.8 else _WARN
        self._popup(label, colour, (fish.x, WATER_Y - 14), big=True)
        self.scene.add_splash(fish.x, 0.35)
        self._play("splash_", 0.3)
        if self.sounds.get("hum") is not None:
            self._hum_channel = self.sounds["hum"].play(loops=-1)
            if self._hum_channel is not None:
                self._hum_channel.set_volume(0.0)

    def _stop_hum(self) -> None:
        if self._hum_channel is not None:
            self._hum_channel.stop()
            self._hum_channel = None

    def _update_fight(self, dt: float) -> None:
        fight = self.fight
        fish = fight.fish
        reeling = self.lmb
        # From a fixed point, not the rod's tip: tension bends the rod towards the fish and the mouse swings it,
        # and a tip moving nearer the fish would slacken the line, dropping the tension each time it rose
        events = fight.update(dt, FIGHT_ANCHOR, reeling, self.hand)
        if reeling:
            self._reel_ticks(dt, 0.05 + 0.1 * fight.T)
        if self._hum_channel is not None:
            self._hum_channel.set_volume(_clamp((fight.T - 0.45) * 1.5) * 0.45)
        self.float_under = True
        self.float_x = fish.x
        self.hook_x, self.hook_y = fish.mouth
        for ev in events:
            if ev == "brace":
                self.scene.add_ring(fish.x, 5)
                self._play("splash_", 0.2)
                self._popup("He rages! Let go!", _BAD, (fish.x, WATER_Y - 14), big=True, life=1.2)
            elif ev == "rage":
                self.kick = -14.0
                self.scene.add_splash(fish.x, 0.5)
                self._play("splash_", 0.3)
            elif ev == "calm":
                self._popup("He's spent: reel!", _GOOD, (fish.x, WATER_Y - 14), life=1.0)
            elif ev == "rise":
                self.scene.add_ring(fish.x, 6)
            elif ev == "jump_out":
                self.scene.add_splash(fish.x, 0.7)
                self._play("splash_", 0.35)
                self._popup("He leaps! Let go!", _WARN, (fish.x, WATER_Y - 26))
            elif ev == "jump_in":
                self.scene.add_splash(fish.x, 0.8)
                self._play("splash_", 0.4)
            elif ev == "kept":
                self._popup("Well kept!", _GOOD, (fish.x, WATER_Y - 18), life=1.2)
            elif ev == "overload":
                self.kick = -18.0
                self._play_synth("twang", 0.3)
                self._popup("The line gives: he gains power!", _BAD, (fish.x, WATER_Y - 14), life=1.3)
            elif ev == "wrench":
                self._popup("You held on: he gains power!", _BAD, (fish.x, WATER_Y - 18), life=1.2)
            elif ev == "free":
                self._lose_fish()
                return
            elif ev == "land":
                self._start_landing()
                return

    def _lose_fish(self) -> None:
        """Its power is full: it breaks free, hook and worm with it, and lives on in the pond."""
        fish = self.fight.fish
        self._popup("He broke free!", _BAD, (fish.x, WATER_Y - 14), big=True, life=2.0)
        self._play_synth("twang", 0.6)
        fish.state = "wander"
        fish.above_water = False
        fish.angle = 0.0
        fish.tired = False
        fish.flee(None, self.rng)
        self.fight = None
        self._stop_hum()
        self._use_worm()
        self._start_retrieve(from_tip=True)

    def _start_landing(self) -> None:
        self._stop_hum()
        self.phase = LANDING
        self.landing_t = 0.0
        self.landed = self.fight.fish
        self.landed.tired = True
        self.scene.add_splash(self.landed.x, 0.4)

    def _update_landing(self, dt: float) -> None:
        self.landing_t += dt
        fish = self.landed
        if self.landing_t > NET_S:
            k = _clamp((self.landing_t - NET_S) / LIFT_S)
            if not fish.above_water:
                fish.above_water = True
                self.scene.add_splash(fish.x, 0.5)
                self._play("splash_", 0.35)
                self._lift_from = (fish.x, fish.y)
            fx, fy = self._lift_from
            fish.x = fx + (BANK_EDGE - 6 - fx) * k
            fish.y = fy + (WATER_Y - 12 - fy) * k - 10 * math.sin(math.pi * k)
            fish.tail += dt * 14
            if k >= 1:
                self._land_fish()

    def _land_fish(self) -> None:
        fish = self.landed
        sp = fish.species
        coins = fish_coins(fish, self.cast_mult)
        size = fish.cm / sp.avg_cm
        record = False
        stats = self._stats()
        if stats is not None:
            records = getattr(stats, "fishing_records", None)
            if records is None:
                records = {}
                stats.fishing_records = records
            if fish.cm > records.get(sp.key, 0):
                record = True
                records[sp.key] = fish.cm
            stats.fish_caught = getattr(stats, "fish_caught", 0) + 1
        self._book(coins)
        extra = self.cast_label.startswith("PERFECT") and self.strike_label.startswith("PERFECT")             and self.total_worms - WORMS < MAX_EXTRA_WORMS
        self.catches.append({"name": sp.name, "cm": fish.cm, "coins": coins, "species": sp})
        self.card = {"fish": fish, "coins": coins, "size": size, "record": record, "extra": extra,
                     "cast": (self.cast_label, self.cast_mult, self.cast_colour)}
        self.card_t = 0.0
        self.pond.remove(fish)
        self.fight = None
        self._use_worm()
        if extra:
            self.worms += 1
            self.total_worms += 1
        self.phase = CARD
        self._play("splash_", 0.2)

    def _book(self, coins: float) -> None:
        """A landed fish's coins, straight into the purse."""
        if coins <= 0:
            return
        self.coins = round(self.coins + coins, 2)
        depot = getattr(self.game, "depot", None)
        if depot is None:
            return
        depot.book_labor_income(coins, MINIGAME_NAME)
        stats = depot.stats
        stats.minigame_income_total += coins
        state = getattr(self.game, "state", None)
        try:
            from ...ui.transaction_feedback import on_money_received
            on_money_received(state, coins)
        except Exception:
            self._play("coin_single_", 0.6)
        if state is not None and hasattr(state, "log_event"):
            state.log_event("FINANCE", f"Earned {coins:.2f}g fishing")

    def _after_card(self) -> None:
        self.card = None
        self.baited = self.worms > 0
        self.phase = READY
        self.theta_target = READY_THETA
        if self.worms <= 0:
            self._finish()

    # ------------------------------------------------------------------
    # Retrieving, ending
    # ------------------------------------------------------------------

    def _start_retrieve(self, from_tip: bool = False) -> None:
        self.hook.alluring = False
        if self.hook.engaged is not None:
            self.hook.engaged.flee(self.hook, self.rng, 3.0)
        self.hook.engaged = None
        self.float_under = False
        if from_tip:
            self.hook_x, self.hook_y = self._tip()
        self.retrieve_from = (self.hook_x, self.hook_y)
        self.phase = RETRIEVE
        self.theta_target = READY_THETA

    def _update_retrieve(self, dt: float) -> None:
        tx, ty = self._tip()
        dx, dy = tx - self.hook_x, ty + 7 - self.hook_y
        d = math.hypot(dx, dy)
        step = 160 * dt
        if d <= step:
            self.baited = self.worms > 0
            self.hook_lost = False
            self.phase = READY
            if self.worms <= 0:
                self._finish()
            return
        self.hook_x += dx / d * step
        self.hook_y += dy / d * step
        if self.hook_y > WATER_Y:
            self.float_x = self.hook_x
        self._reel_ticks(dt, 0.04)

    def _finish(self) -> None:
        """The session is over: count it, keep the best day."""
        self.phase = DONE
        self._stop_hum()
        if self._booked:
            return
        self._booked = True
        stats = self._stats()
        if stats is None:
            return
        stats.minigames_played += 1
        best = getattr(stats, "fishing_highscore", 0.0)
        if self.coins > best:
            stats.fishing_highscore = self.coins
            self.new_highscore = best > 0 or self.coins > 0
        self.highscore = max(best, self.coins)

    # ------------------------------------------------------------------
    # Each frame
    # ------------------------------------------------------------------

    def update(self, delta_time: float) -> None:
        if self.exit_asked:                     # everything waits for the answer
            return
        dt = min(0.05, max(0.0, delta_time))
        self.t += dt
        for sound in self.scene.update(dt):
            if sound == "thunder":
                self._play("thunder_", 0.6)
        if self.lmb:
            self.lmb_t += dt
        self.strike_cool = max(0.0, self.strike_cool - dt)
        self.twitch_age += dt
        while self.twitches and self.t - self.twitches[0] > TWITCH_WINDOW_S:
            self.twitches.popleft()
        self.float_dip = max(0.0, self.float_dip - dt * 4)
        self.kick *= math.exp(-dt * 9)

        # The rod follows the hand, springily; in a fight it leans with the mouse
        if self.phase == FIGHT:
            self.theta_target = 20 + 12 * self.lean
        elif self.phase in (WAIT, RETRIEVE):
            self.theta_target = READY_THETA - (8 if self.lmb and self.phase == WAIT and self.lmb_t >= TAP_S else 0)
        acc = ROD_SPRING * (self.theta_target - self.theta) - ROD_DAMPING * self.omega
        self.omega += acc * dt
        self.theta += self.omega * dt

        if self.phase == FLIGHT:
            self.vy += GRAVITY * dt
            self.vx *= 1 - 0.12 * dt
            self.hook_x += self.vx * dt
            self.hook_y += self.vy * dt
            if self.hook_y >= WATER_Y and self.vy > 0:
                self._land_cast()
            elif self.hook_x > LOW_W - 4:
                self.hook_x = LOW_W - 4
                self.vx = 0
        elif self.phase == WAIT:
            self._update_wait(dt)
        elif self.phase == FIGHT:
            self._update_fight(dt)
        elif self.phase == LANDING:
            self._update_landing(dt)
        elif self.phase == CARD:
            self.card_t += dt
            if self.card_t > CARD_S:
                self._after_card()
        elif self.phase == RETRIEVE:
            self._update_retrieve(dt)
        elif self.phase == STUCK:
            self._update_stuck(dt)

        self.hook.x, self.hook.y = self.hook_x, self.hook_y
        self.hook.twitch_age = self.twitch_age
        self.hook.twitches_recent = len(self.twitches)
        if self.phase != WAIT:
            self.hook.alluring = False
            self.hook.reeling = False
        self._pond_events(self.pond.update(dt, self.hook))
        # The duck rocks the float as it paddles by: is that a bite?
        if self.phase == WAIT and abs(self.scene.duck_x - self.float_x) < DUCK_BOB_RANGE and self.rng.random() < dt * 1.2:
            self.float_dip = max(self.float_dip, 0.9)
        for p in self.popups:
            p[4] += dt
        self.popups = [p for p in self.popups if p[4] < p[5]]

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _view(self) -> PondView:
        v = PondView(rod_theta=self.theta + self.kick, rod_bend=self._bend(), fish=self.pond.fish,
                     worm=self.baited)
        tip = rod_points(v.rod_theta, v.rod_bend)[-1]
        if self.phase in (READY, DRAW):
            hang = (tip[0] + 0.5, tip[1] + 7)
            v.line = [tip, hang]
            v.hook = hang
            if self.phase == DRAW:
                v.sweet_theta = SWEET_THETA
        elif self.phase == FLIGHT:
            v.line = curve(tip, (self.hook_x, self.hook_y), 3)
            v.hook = (self.hook_x, self.hook_y)
        elif self.phase == WAIT:
            bob = math.sin(self.t * 2.2) * 0.4 + self.float_dip
            fy = WATER_Y + (3 if self.float_under else round(bob))
            v.float_at = (self.float_x, fy)
            v.float_under = self.float_under
            v.line = curve(tip, (self.float_x, fy - 2), 5) + [(self.hook_x, self.hook_y)]
            v.hook = (self.hook_x, self.hook_y)
            v.focus = (self.hook_x, self.hook_y, self.scene.sight)
        elif self.phase == FIGHT and self.fight is not None:
            fish = self.fight.fish
            sag = (1 - _clamp(self.fight.T * 1.5)) * 10
            v.line = curve(tip, fish.mouth, sag)
            v.hook = None
            v.worm = False
            v.tension = min(1.1, self.fight.T)
            v.focus = (fish.x, fish.y, self.scene.sight + 5) if not fish.above_water else (fish.x, WATER_Y + 4, self.scene.sight)
        elif self.phase == LANDING and self.landed is not None:
            fish = self.landed
            v.line = curve(tip, fish.mouth, 2)
            v.worm = False
            k = _clamp(self.landing_t / NET_S)
            v.net = (BANK_EDGE - 4 + (fish.x - BANK_EDGE + 4) * k, WATER_Y - 6 + (fish.y - WATER_Y + 6) * k) \
                if not fish.above_water else (fish.x, fish.y + 2)
            v.focus = (fish.x, fish.y, self.scene.sight + 5)
        elif self.phase == STUCK:
            ripped = self.stuck_t >= STUCK_RIP_AT
            fy = WATER_Y + (2 if self.float_under else 0)
            v.float_at = (self.float_x, fy)
            v.float_under = self.float_under
            if ripped:          # the line springs back, slack, without its hook
                v.line = curve(tip, (self.float_x, fy - 2), 9) + [(self.float_x + 1, fy + 6)]
            else:               # taut and glinting, the hook caught in the mud
                v.line = [tip, (self.float_x, fy - 2), (self.hook_x, self.hook_y)]
                v.hook = (self.hook_x, self.hook_y)
                v.tension = 1.0
            v.focus = (self.hook_x, self.hook_y, self.scene.sight)
        elif self.phase == RETRIEVE:
            v.line = [tip, (self.hook_x, self.hook_y)]
            v.hook = None if self.hook_lost else (self.hook_x, self.hook_y)
            v.worm = self.baited
            if self.hook_y > WATER_Y:
                v.focus = (self.hook_x, self.hook_y, self.scene.sight)
        return v

    def _inked(self, text: str, font: pygame.font.Font, colour) -> pygame.Surface:
        face = font.render(text, True, colour)
        rim = font.render(text, True, _INK)
        out = pygame.Surface((face.get_width() + 4, face.get_height() + 4), pygame.SRCALPHA)
        for dx, dy in ((0, 2), (4, 2), (2, 0), (2, 4), (1, 1), (3, 3), (1, 3), (3, 1)):
            out.blit(rim, (dx, dy))
        out.blit(face, (2, 2))
        return out

    def _plaque(self, surf: pygame.Surface, text: str, pos: Tuple[int, int], anchor: str = "topright") -> pygame.Rect:
        label = self.font_small.render(text, True, _INK)
        rect = label.get_rect(**{anchor: pos}).inflate(16, 8)
        pygame.draw.rect(surf, _BRASS, rect, border_radius=3)
        pygame.draw.line(surf, _BRASS_LIGHT, (rect.left + 3, rect.top + 2), (rect.right - 4, rect.top + 2), 1)
        pygame.draw.rect(surf, _BRASS_DARK, rect, 2, border_radius=3)
        surf.blit(label, label.get_rect(center=rect.center))
        return rect

    def _draw_hud(self, surf: pygame.Surface) -> None:
        # Worms left, as little worms
        rect = self._plaque(surf, f"Worms: {self.worms}", (SCENE_W - 14, 12))
        for i in range(min(self.worms, 12)):
            x, y = rect.left - 16 - i * 13, rect.centery
            pygame.draw.lines(surf, (214, 112, 112), False,
                              [(x, y + 3), (x + 3, y - 2), (x + 6, y + 2), (x + 9, y - 3)], 3)
        feet = f"Line depth: {self.leader / PX_PER_FOOT:.0f} ft"
        if self.phase in (READY, DRAW):
            self._plaque(surf, feet + "  (wheel to set)", (SCENE_W - 14, 44))
        elif self.phase in (FLIGHT, WAIT, STUCK):
            self._plaque(surf, feet, (SCENE_W - 14, 44))
        lore = self._inked(self.pond.lore, self.font_small, (236, 230, 206))
        surf.blit(lore, (12, 10))

    def _hint(self) -> Tuple[str, Tuple[int, int, int]]:
        if self.phase == READY:
            return "Wheel: set the depth   |   Hold the left button, drag back, whip forward and let go", PALE_BROWN
        if self.phase == DRAW:
            return "Whip forward, and let go as the rod passes the golden mark!", _INK
        if self.phase == WAIT:
            return "Click: twitch the bait   |   Hold: reel in   |   Flick the mouse UP to strike when it takes", PALE_BROWN
        if self.phase == FIGHT and self.fight is not None:
            mode = self.fight.mode
            if mode in ("brace", "rage"):
                return "He rages: let go of the button until he calms!", _shade_text(_BAD)
            if mode == "jump":
                return "He leaps: let go while he is in the air!", _shade_text(_BAD)
            if self.fight.T > SNAP_TENSION:
                return "The line is straining: let go, or he gains power!", _shade_text(_BAD)
            return "Hold to reel, keeping the mouse under the marker   |   Let go when the line strains", _INK
        if self.phase == CARD:
            return "Click to go on", PALE_BROWN
        return "", PALE_BROWN

    def _draw_overlay(self, surf: pygame.Surface) -> None:
        self._draw_hud(surf)
        if self.phase == FIGHT and self.fight is not None:
            self._draw_fight_bar(surf)
        # The line straining: the edges glow red
        if self.phase == FIGHT and self.fight is not None and self.fight.strain > 0.05:
            glow = pygame.Surface((SCENE_W, SCENE_H), pygame.SRCALPHA)
            a = round(_clamp(self.fight.strain) * 110)
            for k in range(10):
                pygame.draw.rect(glow, (200, 40, 30, max(0, a - k * 11)), glow.get_rect().inflate(-k * 6, -k * 6), 3)
            surf.blit(glow, (0, 0))
        for text, colour, x, y, age, life, big in self.popups:
            label = self._inked(text, self.font_grade if big else self.font, colour)
            label.set_alpha(round(255 * min(1.0, (life - age) / 0.4, age / 0.08 if age < 0.08 else 1.0)))
            rect = label.get_rect(center=(x, y - 18 * age / life))
            rect.clamp_ip(surf.get_rect().inflate(-8, -8))
            surf.blit(label, rect)
        hint, colour = self._hint()
        if hint:
            label = self.font.render(hint, True, colour)
            ribbon = label.get_rect(center=(SCENE_W // 2, SCENE_H - 24)).inflate(28, 10)
            pygame.draw.rect(surf, _PAPER, ribbon, border_radius=4)
            pygame.draw.rect(surf, DARK_BROWN, ribbon, 2, border_radius=4)
            surf.blit(label, label.get_rect(center=ribbon.center))
        if self.card is not None:
            self._draw_card(surf)

    def _draw_fight_bar(self, surf: pygame.Surface) -> None:
        """The bar along the top: the marker swinging on it, its zone, and where the mouse is under it."""
        fight = self.fight
        flash = 0.5 + 0.5 * math.sin(self.t * 22)
        if fight.mode == "rage":
            zone_colour = _BAD
        elif fight.mode == "brace":
            zone_colour = _mix_rgb(_WARN, _BAD, flash)
        else:
            zone_colour = _mix_rgb(_BAD, _GOOD, fight.track)
        pygame.draw.rect(surf, _BRASS_DARK, _BAR.inflate(10, 10), border_radius=5)
        heat = _clamp((fight.T - SNAP_TENSION + 0.15) / 0.3)
        pygame.draw.rect(surf, _mix_rgb(_BRASS, _BAD, heat), _BAR.inflate(6, 6), border_radius=4)
        pygame.draw.rect(surf, (34, 26, 20), _BAR, border_radius=2)
        x = _BAR.left + fight.bar_x * _BAR.width
        half = fight.zone * _BAR.width
        surf.blit(self._guide, (round(x) - 1, _BAR.bottom))
        # Where the grip fades out, then the zone itself
        fade = pygame.Rect(0, 0, round(2 * half * (1 + BAR_FALLOFF)), _BAR.height - 8)
        fade.center = (round(x), _BAR.centery)
        pygame.draw.rect(surf, _mix_rgb((34, 26, 20), zone_colour, 0.3), fade.clip(_BAR), border_radius=2)
        zone = pygame.Rect(0, 0, round(2 * half), _BAR.height - 4)
        zone.center = (round(x), _BAR.centery)
        pygame.draw.rect(surf, zone_colour, zone.clip(_BAR), border_radius=2)
        # The marker: a needle through the bar, pointing down at the mouse
        needle = pygame.Rect(round(x) - 3, _BAR.top - 5, 6, _BAR.height + 10)
        pygame.draw.rect(surf, _PAPER, needle)
        pygame.draw.rect(surf, _INK, needle, 1)
        tip_y = _BAR.bottom + 16
        pygame.draw.polygon(surf, _PAPER, [(x - 9, _BAR.bottom + 5), (x + 9, _BAR.bottom + 5), (x, tip_y)])
        pygame.draw.polygon(surf, _INK, [(x - 9, _BAR.bottom + 5), (x + 9, _BAR.bottom + 5), (x, tip_y)], 1)
        # The mouse, under the bar, pointing up at the marker
        hx = _BAR.left + _clamp(self.hand) * _BAR.width
        hand = [(hx, tip_y + 2), (hx - 8, tip_y + 14), (hx + 8, tip_y + 14)]
        pygame.draw.polygon(surf, zone_colour, hand)
        pygame.draw.polygon(surf, _INK, hand, 1)
        # The line's strain and the fish's strength
        y = _BAR.bottom + 36
        self._draw_meter(surf, "Line", fight.strain, _BAD, (SCENE_W // 2 - _METER_W - 60, y))
        power = _mix_rgb(_WARN, _BAD, _clamp((fight.stamina - 0.6) / 0.3))
        self._draw_meter(surf, "Fish", fight.stamina, power, (SCENE_W // 2 + 60, y))
        beaten = SCENE_W // 2 + 60 + round(_METER_W * LAND_STAMINA)    # below this mark it can be netted
        pygame.draw.line(surf, _PAPER, (beaten, y - 2), (beaten, y + _METER_H + 1), 1)

    def _draw_meter(self, surf: pygame.Surface, name: str, level: float, colour, pos: Tuple[int, int]) -> None:
        rect = pygame.Rect(pos[0], pos[1], _METER_W, _METER_H)
        pygame.draw.rect(surf, (34, 26, 20), rect)
        pygame.draw.rect(surf, colour, (rect.left, rect.top, round(rect.width * _clamp(level)), rect.height))
        pygame.draw.rect(surf, _BRASS_DARK, rect, 1)
        label = self._inked(name, self.font_small, (236, 230, 206))
        surf.blit(label, label.get_rect(midright=(rect.left - 6, rect.centery)))

    def _draw_card(self, surf: pygame.Surface) -> None:
        """The landed fish on a sheet of paper, the sheet sized to the fish and the lines under it."""
        card = self.card
        fish = card["fish"]
        sp = fish.species
        img = fish_sprite(sp, fish.length, (0, 1, 0, 2)[int(self.t * 5) % 4])
        k = max(2, min(12, CARD_FISH_W // img.get_width(), CARD_FISH_H // img.get_height()))
        big = pygame.transform.scale(img, (img.get_width() * k, img.get_height() * k))
        label, mult, colour = card["cast"]
        lines = [(self.font.render(f"{fish.cm:.0f} cm   |   size ×{card['size']:.2f}", True, DARK_BROWN), 26),
                 (self.font.render(f"{label.title()}   ×{mult:g}", True, _shade_text(colour)), 30),
                 (self.font_large.render(f"+{card['coins']:.2f} coins", True, (60, 110, 40)), 42)]
        if card["record"]:
            lines.append((self.font_small.render(f"Your biggest {sp.name.lower()} yet!", True, (150, 108, 30)), 20))
        if card["extra"]:
            lines.append((self.font_small.render("Perfect cast and strike: an extra worm!", True, (150, 108, 30)), 20))
        title = self.font_large.render(sp.name, True, DARK_BROWN)
        width = max(400, big.get_width() + 80, max(t.get_width() for t, _ in lines) + 60)
        height = 18 + title.get_height() + 10 + big.get_height() + 14 + sum(h for _, h in lines) + 18
        rect = pygame.Rect(0, 0, width, height)
        rect.center = (SCENE_W // 2, SCENE_H // 2 - 30)
        rect.clamp_ip(pygame.Rect(0, 0, SCENE_W, SCENE_H - 52))
        rect.y += round(20 * (1 - _clamp(self.card_t / 0.25)) ** 2)
        shadow = pygame.Surface(rect.size, pygame.SRCALPHA)
        shadow.fill((0, 0, 0, 90))
        surf.blit(shadow, rect.move(6, 8))
        draw_paper(surf, rect, rect.topleft)
        pygame.draw.rect(surf, DARK_BROWN, rect, 3, border_radius=2)
        pygame.draw.rect(surf, _BRASS_DARK, rect.inflate(-12, -12), 1)
        y = rect.top + 18
        surf.blit(title, title.get_rect(midtop=(rect.centerx, y)))
        y += title.get_height() + 10
        surf.blit(big, big.get_rect(midtop=(rect.centerx, y)))
        y += big.get_height() + 14
        for text, h in lines:
            surf.blit(text, text.get_rect(midtop=(rect.centerx, y)))
            y += h

    def _draw_bars(self) -> None:
        pygame.draw.rect(self.canvas, DARK_BROWN, (0, 0, _CANVAS_W, _TOP_BAR))
        pygame.draw.line(self.canvas, SANDY_BROWN, (0, _TOP_BAR), (_CANVAS_W, _TOP_BAR), 1)
        title = self.font.render("FISHING", True, SANDY_BROWN)
        self.canvas.blit(title, title.get_rect(center=(_CANVAS_W // 2, _TOP_BAR // 2)))
        y0 = _CANVAS_H - _BOTTOM_BAR
        pygame.draw.rect(self.canvas, DARK_BROWN, (0, y0, _CANVAS_W, _BOTTOM_BAR))
        pygame.draw.line(self.canvas, SANDY_BROWN, (0, y0), (_CANVAS_W, y0), 1)
        left = self.font.render(f"Fish caught: {len(self.catches)}", True, SANDY_BROWN)
        self.canvas.blit(left, (20, y0 + 14))
        mid = self.font.render(f"Worms left: {self.worms} / {self.total_worms}", True, SANDY_BROWN)
        self.canvas.blit(mid, mid.get_rect(centerx=_CANVAS_W // 2, y=y0 + 14))
        right = self.font.render(f"Coins: {self.coins:.2f}", True, SANDY_BROWN)
        self.canvas.blit(right, right.get_rect(right=_CANVAS_W - 20, y=y0 + 14))

    def _draw_result(self) -> None:
        shade = pygame.Surface((_CANVAS_W, _CANVAS_H), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 150))
        self.canvas.blit(shade, (0, 0))
        cx = _CANVAS_W // 2
        rows = self.catches[-9:]
        panel = pygame.Rect(0, 0, 460, 250 + 24 * max(1, len(rows)))
        panel.center = (cx, _CANVAS_H // 2)
        draw_paper(self.canvas, panel, panel.topleft)
        pygame.draw.rect(self.canvas, DARK_BROWN, panel, 3, border_radius=2)
        y = panel.top + 18
        title = self.font_large.render("A Day by the Water", True, DARK_BROWN)
        self.canvas.blit(title, title.get_rect(midtop=(cx, y)))
        y += 52
        if not rows:
            t = self.font.render("Nothing caught today.", True, PALE_BROWN)
            self.canvas.blit(t, t.get_rect(midtop=(cx, y)))
            y += 24
        for c in rows:
            t = self.font.render(f"{c['name']}, {c['cm']:.0f} cm", True, DARK_BROWN)
            self.canvas.blit(t, (panel.left + 60, y))
            m = self.font.render(f"{c['coins']:.2f}", True, DARK_BROWN)
            self.canvas.blit(m, m.get_rect(topright=(panel.right - 60, y)))
            y += 24
        y += 12
        pygame.draw.line(self.canvas, PALE_BROWN, (panel.left + 50, y), (panel.right - 50, y), 1)
        y += 12
        total = self.font_large.render(f"+{self.coins:.2f} coins", True, (60, 110, 40))
        self.canvas.blit(total, total.get_rect(midtop=(cx, y)))
        y += 40
        best = self.font.render(f"Best day: {self.highscore:.2f} coins" + ("  — a new best!" if self.new_highscore else ""),
                                True, GOLD if self.new_highscore else DARK_BROWN)
        self.canvas.blit(best, best.get_rect(midtop=(cx, y)))
        self.close_rect.center = (cx, panel.bottom - 34)
        mouse = pygame.mouse.get_pos()
        hovered = self.close_rect.collidepoint((mouse[0] - self.canvas_rect.left, mouse[1] - self.canvas_rect.top))
        pygame.draw.rect(self.canvas, PALE_BROWN if hovered else SANDY_BROWN, self.close_rect, border_radius=4)
        pygame.draw.rect(self.canvas, DARK_BROWN, self.close_rect, 2, border_radius=4)
        t = self.font.render("Close", True, DARK_BROWN)
        self.canvas.blit(t, t.get_rect(center=self.close_rect.center))

    def _draw_exit_question(self) -> None:
        """Whether to leave a session under way, on a paper box over the shaded scene."""
        lines = [_EXIT_TEXT]
        if self.phase in (FIGHT, LANDING):
            lines.insert(0, _EXIT_FISH_TEXT)
        shade = pygame.Surface((_CANVAS_W, _CANVAS_H), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 110))
        self.canvas.blit(shade, (0, 0))
        panel = pygame.Rect(0, 0, 440, 112 + 24 * len(lines))
        panel.center = _SCENE_RECT.center
        pygame.draw.rect(self.canvas, _PAPER, panel, border_radius=6)
        pygame.draw.rect(self.canvas, _BRASS, panel, 3, border_radius=6)
        pygame.draw.rect(self.canvas, _BRASS_DARK, panel.inflate(-8, -8), 1, border_radius=4)
        title = self.font_grade.render(_EXIT_TITLE, True, _INK)
        self.canvas.blit(title, title.get_rect(center=(panel.centerx, panel.top + 30)))
        for i, line in enumerate(lines):
            text = self.font.render(line, True, _INK)
            self.canvas.blit(text, text.get_rect(center=(panel.centerx, panel.top + 64 + 24 * i)))
        self.exit_back_rect.center = (panel.centerx - 75, panel.bottom - 32)
        self.exit_yes_rect.center = (panel.centerx + 75, panel.bottom - 32)
        mouse = pygame.mouse.get_pos()
        mouse = (mouse[0] - self.canvas_rect.left, mouse[1] - self.canvas_rect.top)
        for rect, label in ((self.exit_back_rect, "Go back"), (self.exit_yes_rect, "Exit")):
            pygame.draw.rect(self.canvas, _BRASS_LIGHT if rect.collidepoint(mouse) else _BRASS, rect, border_radius=4)
            pygame.draw.rect(self.canvas, _BRASS_DARK, rect, 2, border_radius=4)
            text = self.font.render(label, True, _INK)
            self.canvas.blit(text, text.get_rect(center=rect.center))

    def draw(self) -> None:
        backdrop = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        backdrop.fill((0, 0, 0, 160))
        self.screen.blit(backdrop, (0, 0))
        self.canvas.fill(DARK_BROWN)
        picture = self.scene.draw(self._view())
        self._draw_overlay(picture)
        self.canvas.blit(picture, _SCENE_RECT.topleft)
        pygame.draw.rect(self.canvas, SANDY_BROWN, _SCENE_RECT.inflate(2, 2), 1)
        self._draw_bars()
        if self.phase == DONE:
            self._draw_result()
        if self.exit_asked:
            self._draw_exit_question()
        pygame.draw.rect(self.screen, DARK_BROWN, self.canvas_rect.inflate(8, 8), border_radius=6)
        self.screen.blit(self.canvas, self.canvas_rect.topleft)
        pygame.draw.rect(self.screen, DARK_BROWN, self.canvas_rect, 3, border_radius=6)


def _mix_rgb(a, b, k: float) -> Tuple[int, int, int]:
    return tuple(round(x + (y - x) * k) for x, y in zip(a, b))


def _shade_text(colour) -> Tuple[int, int, int]:
    """A grade's bright colour, darkened to read on paper."""
    return tuple(round(c * 0.55) for c in colour)
