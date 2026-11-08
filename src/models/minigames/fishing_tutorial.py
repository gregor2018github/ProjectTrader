"""The fishing minigame's how-to sheet: two parchment pages, as big as the minigame.

The first, the cast: the wheel setting the depth, and a hook set too deep ripping off on the
bottom (I); the rod dragged back, whipped forward and let go at different moments (II); a fish
nibbling and taking, and the flick of the mouse that strikes it, in time, too early and too late
(III). The second, the fight: the mouse following the marker (I); reeling in bursts, the line's
strain against the fish's power (II); a whole fight with its rages, up to the net (III).

Each picture is a ``FishingMinigame`` of its own, with no player: ``demo`` makes it silent, a
script below works it as a hand would, and all that then happens and is drawn is the game's, so
the pages cannot drift from what they explain. Nothing of the real session is touched.

The minigame opens the first page by itself the first time (``TIP_TUTORIAL_CAST``) and the second
when the first fish is hooked (``TIP_TUTORIAL_FIGHT``), both remembered in
``Statistics.minigame_tips_seen``; its "How to play" button opens them again, and only a player
who has hooked a fish can turn to the second.
"""

import random
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Optional, Sequence, Tuple

import pygame

from .fishing import (
    BRACE_S, CARD, DEG_PER_PX, DRAW, FIGHT, FIGHT_ANCHOR, FLIGHT, FishingMinigame, FRESH, Fight, LANDING, LEADER_START,
    LEADER_STEP, PAGE_CAST, PAGE_FIGHT, RAGE_FROM_STAMINA, READY, READY_THETA, RETRIEVE, SWEET_THETA, STUCK, WAIT,
    WORMS, _lerp,
)
from .fishing_pond import APPROACH, NIBBLE, PX_PER_FOOT, SPECIES, TAKE, WATER_Y, Fish, length_px
from .fishing_scene import PX
from .tutorial_sheet import (
    BAD, BRASS_LIGHT, BUTTON_SIZE, GOOD, INK, MAX_DT, SheetLayout, build_sheet, draw_button, hold_sign, mouse_icon, plaque,
)

#: Each card: its heading, and its words, *these* in red ink
TITLES = {PAGE_CAST: "How to Cast and Strike", PAGE_FIGHT: "How to Land a Fish"}
BUTTONS = {PAGE_CAST: "To the water!", PAGE_FIGHT: "To the fish!"}
TURN_LABELS = {PAGE_CAST: "The cast", PAGE_FIGHT: "The fight"}
CARDS = {
    PAGE_CAST: (
        ("Set the depth", "Before the cast, the *wheel* sets how deep the bait hangs. "
                          "Too deep, and the hook *catches on the bottom* and rips off."),
        ("Whip the rod", "*Hold* the left button and drag back. Whip forward and *let go* as the rod passes "
                         "the golden mark: the cleaner the cast, the more its fish pay. "
                         "Farther out is deeper water and bigger fish."),
        ("Strike!", "The float trembles: only a nibble, wait. When it *goes under*, flick the mouse *up* "
                    "(or press Space). Too soon he flees, too late the worm is gone."),
    ),
    PAGE_FIGHT: (
        ("Keep on the mark", "A marker swings along the bar. *Keep the mouse under it*: off it the reel "
                             "gains nothing, he takes line and it strains."),
        ("Reel in bursts", "*Hold* to reel and he tires, but the *Line* strains. *Let go* and it eases while he "
                           "gets power back. If the line gives he gains much; full power, and he is gone."),
        ("Bring him in", "When he *rages*, the bar flashes: let go until he is spent, then reel. With his power "
                         "under the mark on the *Fish* bar and him near the bank, the net takes him."),
    ),
}

_LAYOUTS = {
    PAGE_CAST: SheetLayout(card_widths=(290, 518, 320), cards_bottom=650, picture_h=340, button_y=692),
    PAGE_FIGHT: SheetLayout(card_widths=(330, 330, 468), cards_bottom=650, picture_h=340, button_y=692),
}
_TURN_GAP = 16

# Which part of the scene (1200 x 640) each picture shows; the first and last of the first page at full size
_DEPTH_X, _STRIKE_X = 100, 125           # where in the pond (low pixels) their bait goes in
_DEPTH_CROP = pygame.Rect(_DEPTH_X * PX - 133, 200, 266, 340)
_CAST_CROP = pygame.Rect(0, 0, 930, 640)
_STRIKE_CROP = pygame.Rect(_STRIKE_X * PX - 148, 200, 296, 340)
_MARK_CROP = pygame.Rect(216, 0, 576, 640)
_WHOLE_CROP = pygame.Rect(0, 0, 836, 640)

# The depth's picture: the depths it tries, the last deeper than the water where it goes in
_DEPTH_TRIES = (LEADER_START, LEADER_START + 6 * LEADER_STEP, LEADER_START + 13 * LEADER_STEP)
_WHEEL_NOTCH_S = 0.14                    # a notch of the wheel
_WHEEL_REST_S = 0.5                      # before the bait goes in
_HANGING_S = 1.5                         # how long a bait hanging free is looked at


@dataclass(frozen=True)
class _Cast:
    """A cast of the rod's picture: the rod's angle it lets go at, and how fast the hand whips."""
    release: float
    whip: float


# The rod's picture: dragged back and whipped by the hand's angle, in degrees and degrees a second
_READY_S = 0.8
_BACK_THETA = -62.0
_BACK_S, _BACK_HOLD_S = 0.75, 0.25
_WHIP_TO = 48.0
_CAST_TRIES = (
    _Cast(SWEET_THETA, 900.0),           # at the mark, a good way out
    _Cast(-56.0, 900.0),                 # far too early: straight up and hardly out
    _Cast(SWEET_THETA, 620.0),           # at the mark, not so hard: not so far
    _Cast(42.0, 900.0),                  # too late: flat
)
_CAST_REST_S = 1.5                       # looking at where it landed
_MOUSE_TRAVEL = 0.32                     # the mouse's picture moves this share of what the hand would

# The strike's picture
_STRIKE_DEPTH = LEADER_START + 2 * LEADER_STEP
_STRIKE_TRIES = ("good", "early", "good", "late")
_FISH_COMES_FROM = (24.0, 6.0)           # where the fish starts, from the bait, low pixels
_FISH_KEEN = 4.0                         # the pond's mood: this fish always takes after its nibbles
_EARLY_AFTER_S = 0.4                     # a strike too early, into the nibbling
_STRIKE_AFTER_S = 0.2                    # one in time, after the take
_FLICK_S = 0.22                          # the mouse's jump upwards
_AFTER_STRIKE_S = 1.6                    # looking at how it went

# The fights' pictures
_FIGHT_FISH = ("perch", 34.0)            # big enough to run and rage, small enough to come in soon
_FIGHT_FROM = (135.0, 85.0)
_FIGHT_HOLD = 0.8                        # a good strike's hook
_AFTER_FIGHT_S = 1.8                     # looking at how it ended
_PLAIN_RUN_S, _PLAIN_REST_S = (1.4, 2.2), (1.2, 2.0)    # a fish with no tricks: how long it runs and rests
_RAGE_EVERY = 4                         # the whole fight's picture: every this many moves it rages
_MARK_ON_S, _MARK_OFF_S = 3.4, 1.8       # the marker's picture: on the mark so long, off it so long
_MARK_OFF_BY = 0.3                       # and this far beside it, of the bar
_MARK_FOLLOW = 8.0                       # how quickly the hand gets there
_MARK_FRESH_S = 20.0                     # it starts over now and then, the fish far out again
_STRAIN_LIMITS = (0.65, 0.65, 1.2)       # the strain's picture: lets go at this strain; above 1 the line gives way
_STRAIN_EASED = 0.05                     # and reels again at this
_STRAIN_RISK_BELOW = 0.45                # it only lets the line give way on a fish this tired, or he would be gone
_FIGHT_BAR_INSET, _FIGHT_BAR_H = 16, 18
_METERS_LEFT = 48                        # room for their names
_WHOLE_METERS_LEFT = 170                 # and for the player, in the picture he is in


class PondDemo:
    """One of the pictures: a real minigame, with nobody at the rod and no fish but the script's."""

    def __init__(self, screen: pygame.Surface, seed: int) -> None:
        self.game = FishingMinigame(screen, SimpleNamespace(), random.Random(seed), demo=True)
        self.held = False
        self.verdict: Optional[Tuple[str, Tuple[int, int, int]]] = None
        self._empty_the_pond()

    def _empty_the_pond(self) -> None:
        g = self.game
        g.pond.fish.clear()
        g.pond._respawn.clear()
        g.popups.clear()
        g.hook.engaged = None
        g.fight, g.landed, g.card = None, None, None
        g.worms, g.baited, g.hook_lost = WORMS, True, False

    def _bait_in_water(self, x: float, depth: float) -> None:
        """The bait comes down at x, by the game's own landing, without a cast to look at."""
        g = self.game
        g.leader = depth
        g.hook_x = x
        g.cast_label, g.cast_mult, g.cast_colour = "GOOD CAST", 1.0, (255, 255, 255)
        g._land_cast()
        g.popups.clear()

    def _newest_popup(self) -> Optional[Tuple[str, Tuple[int, int, int]]]:
        popups = self.game.popups
        return (popups[-1][0], popups[-1][1]) if popups else None

    def picture(self) -> pygame.Surface:
        return self.game.scene.draw(self.game._view())


class DepthDemo(PondDemo):
    """The wheel turns the depth up notch by notch, the bait goes in and sinks to it, or to the bottom."""

    def __init__(self, screen: pygame.Surface) -> None:
        super().__init__(screen, 21)
        self.index = 0
        self.game.leader = _DEPTH_TRIES[-1]
        self.stage, self.timer = "wheel", 0.0
        self.turning = 0                 # which way the wheel is going: 1 deeper, -1 shallower, 0 not at all

    @property
    def depth(self) -> float:
        return self.game.leader

    def update(self, dt: float) -> None:
        g = self.game
        self.timer += dt
        if self.stage == "wheel":
            wanted = _DEPTH_TRIES[self.index]
            if abs(g.leader - wanted) < 0.01:
                self.turning = 0
                if self.timer >= _WHEEL_REST_S:
                    self._bait_in_water(_DEPTH_X, wanted)
                    self.stage, self.timer = "sink", 0.0
            elif self.timer >= _WHEEL_NOTCH_S:
                self.turning = 1 if wanted > g.leader else -1
                g.leader += self.turning * LEADER_STEP
                self.timer = 0.0
        elif self.stage == "sink":
            if g.phase == WAIT and g.settled_t >= _HANGING_S:
                g._start_retrieve()
                self.verdict = None
                self.stage = "home"
            elif g.phase == WAIT and g.settled_t > 0.1:
                self.verdict = ("Hangs free", GOOD)
            elif g.phase in (STUCK, RETRIEVE):
                self.stage = "ripped"
        elif self.stage == "ripped":
            self.verdict = self._newest_popup() or self.verdict
            if g.phase == READY:
                self.stage = "home"
        if self.stage == "home" and g.phase == READY:
            self._empty_the_pond()
            self.verdict = None
            self.index = (self.index + 1) % len(_DEPTH_TRIES)
            self.stage, self.timer = "wheel", 0.0
        g.update(dt)


class CastDemo(PondDemo):
    """The rod on the game's own spring, by the hand's angle as a dragging mouse would set it."""

    def __init__(self, screen: pygame.Surface) -> None:
        super().__init__(screen, 22)
        self.index = 0
        self.stage, self.timer = "ready", 0.0
        self.landing: Optional[str] = None     # how far out, once it has landed

    @property
    def current(self) -> _Cast:
        return _CAST_TRIES[self.index]

    @property
    def sign(self) -> str:
        return {"back": "Hold, drag back", "whip": "Whip forward!", "fly": "Let go!"}.get(self.stage, "Ready")

    @property
    def mouse_offset(self) -> float:
        """Where the mouse's picture is, in pixels off its resting place."""
        return (self.game.theta_target - READY_THETA) / DEG_PER_PX * _MOUSE_TRAVEL

    def update(self, dt: float) -> None:
        g = self.game
        self.timer += dt
        if self.stage == "ready":
            if self.timer >= _READY_S:
                g.phase = DRAW
                self.held = True
                self.stage, self.timer = "back", 0.0
        elif self.stage == "back":
            k = min(1.0, self.timer / _BACK_S)
            g.theta_target = READY_THETA + (_BACK_THETA - READY_THETA) * k * k * (3 - 2 * k)
            if self.timer >= _BACK_S + _BACK_HOLD_S:
                self.stage, self.timer = "whip", 0.0
        elif self.stage == "whip":
            g.theta_target = min(_WHIP_TO, g.theta_target + self.current.whip * dt)
            if g.theta >= self.current.release:
                g._release_cast()
                self.held = False
                self.stage, self.timer = "fly", 0.0
        elif self.stage == "fly":
            if g.phase == WAIT:
                self.verdict = (g.cast_label.title(), g.cast_colour)
                self.landing = self._newest_popup()[0]
                self.stage, self.timer = "rest", 0.0
            elif g.phase != FLIGHT:      # it fell short of the water
                self.verdict = self._newest_popup() or (g.cast_label.title(), g.cast_colour)
                self.stage, self.timer = "rest", 0.0
        elif self.stage == "rest":
            if self.timer >= _CAST_REST_S:
                if g.phase == WAIT:
                    g._start_retrieve()
                self.verdict, self.landing = None, None
                self.stage = "home"
        elif self.stage == "home" and g.phase == READY:
            self._empty_the_pond()
            self.index = (self.index + 1) % len(_CAST_TRIES)
            self.stage, self.timer = "ready", 0.0
        g.update(dt)



class StrikeDemo(PondDemo):
    """A roach comes to the bait, nibbles and takes, by the pond's own rules; the script strikes."""

    def __init__(self, screen: pygame.Surface) -> None:
        super().__init__(screen, 23)
        self.game.pond.mood = _FISH_KEEN
        self.index = 0
        self.fish: Optional[Fish] = None
        self.flick = 0.0
        self.stage, self.timer = "bait", 0.0
        self._bait_in_water(_STRIKE_X, _STRIKE_DEPTH)

    @property
    def current(self) -> str:
        return _STRIKE_TRIES[self.index]

    @property
    def sign(self) -> str:
        return "Flick up!" if self.flick > 0 else "Wait"

    def _send_fish(self) -> None:
        g = self.game
        kind = SPECIES["roach"]
        self.fish = fish = Fish(kind, g.rng)
        fish.cm = kind.avg_cm
        fish.length = length_px(fish.cm, kind)
        fish.x, fish.y = g.hook_x + _FISH_COMES_FROM[0], g.hook_y + _FISH_COMES_FROM[1]
        fish.state, fish.side = APPROACH, 1
        g.hook.engaged = fish
        g.pond.fish.append(fish)

    def _flick_up(self) -> None:
        self.flick = _FLICK_S
        self.game._strike()
        self.verdict = None
        self.stage, self.timer = "after", 0.0

    def update(self, dt: float) -> None:
        g = self.game
        self.timer += dt
        self.flick = max(0.0, self.flick - dt)
        if self.stage == "bait":
            if g.hook.alluring:
                self._send_fish()
                self.stage, self.timer = "bite", 0.0
        elif self.stage == "bite":
            state = self.fish.state
            if state == NIBBLE:
                self.verdict = ("Only a nibble: wait", (226, 226, 200))
                if self.current == "early" and self.timer >= _EARLY_AFTER_S:
                    self._flick_up()
                elif self.current != "early":
                    self.timer = 0.0
            elif state == TAKE:
                self.verdict = ("It takes!", GOOD)
                if self.current == "good" and g.t - g.take_t >= _STRIKE_AFTER_S:
                    self._flick_up()
                elif self.current == "late" and g.phase != WAIT:
                    self.stage, self.timer = "after", 0.0
            elif g.phase != WAIT:              # the worm was stolen while it waited
                self.stage, self.timer = "after", 0.0
            else:
                self.timer = 0.0
        else:
            if g.phase == FIGHT:
                g.hand = g.fight.bar_x
                self.verdict = (g.strike_label.title(), GOOD)
            else:
                self.verdict = self._newest_popup() or self.verdict
            if self.timer >= _AFTER_STRIKE_S:
                self._next()
        g.update(dt)

    def _next(self) -> None:
        g = self.game
        self._empty_the_pond()
        g.phase = READY
        self.verdict, self.fish = None, None
        self.index = (self.index + 1) % len(_STRIKE_TRIES)
        self.stage, self.timer = "bait", 0.0
        self._bait_in_water(_STRIKE_X, _STRIKE_DEPTH)


class _PlainFight(Fight):
    """A fish that runs away and rests by turns: no rages or leaps to distract from what a picture shows."""

    def _pick(self) -> None:
        if self.mode == "run":
            self.mode, self.mode_t = "rest", self.rng.uniform(*_PLAIN_REST_S)
        else:
            self.mode, self.mode_t, self.dir = "run", self.rng.uniform(*_PLAIN_RUN_S), self._run_dir(away=True)


class _RagingFight(Fight):
    """The fish's own moves, with a rage every so often, so that a short fight shows them."""

    _moves = 0

    def _pick(self) -> None:
        self._moves += 1
        if self._moves % _RAGE_EVERY == 1 and self.vigor > RAGE_FROM_STAMINA:
            self.mode, self.mode_t = "brace", _lerp(BRACE_S, self.heft)
        else:
            super()._pick()


class FightDemo(PondDemo):
    """A fish on the line and a script at the reel; when the fight is over, another one."""

    fight_class = Fight

    def __init__(self, screen: pygame.Surface, seed: int) -> None:
        super().__init__(screen, seed)
        self.timer = 0.0
        self.ended = 0.0
        self._new_fight()

    def _new_fight(self) -> None:
        g = self.game
        self._empty_the_pond()
        kind, cm = SPECIES[_FIGHT_FISH[0]], _FIGHT_FISH[1]
        fish = Fish(kind, g.rng)
        fish.cm = cm
        fish.length = length_px(cm, kind)
        fish.x, fish.y = _FIGHT_FROM
        g.pond.fish.append(fish)
        g._start_fight(fish, _FIGHT_HOLD, "GOOD STRIKE")
        g.fight = self.fight_class(fish, _FIGHT_HOLD, FIGHT_ANCHOR, g.rng, g.hand)
        g.popups.clear()
        self.verdict, self.held, self.timer, self.ended = None, False, 0.0, 0.0

    def _play(self, dt: float, fight: Fight) -> None:
        """Works the reel and the mouse for this moment of the fight."""
        raise NotImplementedError

    def update(self, dt: float) -> None:
        g = self.game
        self.timer += dt
        if g.phase == FIGHT:
            self._play(dt, g.fight)
            g.lmb = self.held
        else:
            g.lmb = self.held = False
            self.ended += dt
            if g.phase in (LANDING, CARD):
                self.verdict = ("Netted!", GOOD)
            else:
                self.verdict = self._newest_popup() or self.verdict
            if self.ended >= _AFTER_FIGHT_S and g.phase != LANDING:
                self._new_fight()
                return
        g.update(dt)


class MarkerDemo(FightDemo):
    """On the mark for a while, then off it. The fish neither tires nor gains: only the mark counts here."""

    fight_class = _PlainFight

    def _play(self, dt: float, fight: Fight) -> None:
        g = self.game
        if self.timer >= _MARK_FRESH_S:
            self._new_fight()
            return
        fight.stamina, fight.strain = FRESH, 0.0
        off = self.timer % (_MARK_ON_S + _MARK_OFF_S) >= _MARK_ON_S
        if not off:                      # the side it will miss on is settled before it goes
            self._side = 1 if fight.bar_x < 0.5 else -1
        wanted = fight.bar_x + (self._side * _MARK_OFF_BY if off else 0.0)
        g.hand += (wanted - g.hand) * min(1.0, dt * _MARK_FOLLOW)
        self.held = True
        if fight.track > 0.8:
            self.verdict = ("On the mark!", GOOD)
        elif fight.track < 0.3:
            self.verdict = ("Off the mark!", BAD)


class StrainDemo(FightDemo):
    """Reels until the line has taken so much, lets go until it has eased; now and then holds on too long."""

    fight_class = _PlainFight

    def __init__(self, screen: pygame.Surface) -> None:
        self.burst = 0
        super().__init__(screen, 25)

    def _play(self, dt: float, fight: Fight) -> None:
        self.game.hand = fight.bar_x
        limit = _STRAIN_LIMITS[self.burst % len(_STRAIN_LIMITS)]
        if limit > 1 and fight.stamina >= _STRAIN_RISK_BELOW:
            limit = _STRAIN_LIMITS[0]
        if self.held:
            if fight.strain >= limit or (limit > 1 and self._newest_popup() is not None):
                self.held = False
                self.burst += 1
        elif fight.strain <= _STRAIN_EASED:
            self.game.popups.clear()
            self.held = True
        popup = self._newest_popup()
        if popup is not None:
            self.verdict = popup
        elif self.held:
            self.verdict = ("He tires, the line strains", (226, 226, 200))
        else:
            self.verdict = ("The line eases, he gains", (226, 226, 200))


class WholeDemo(FightDemo):
    """A whole fight, played as it should be: on the mark, and letting go through rages and leaps."""

    fight_class = _RagingFight

    def _play(self, dt: float, fight: Fight) -> None:
        self.game.hand = fight.bar_x
        self.held = fight.mode not in ("brace", "rage", "jump") and fight.strain < 0.4
        self.verdict = self._newest_popup()


class FishingTutorial:
    """The how-to sheet: drawn on the minigame's canvas over everything, closed by its button, Enter,
    Space or Escape, turned by its other button or the arrow keys. The game waits behind it."""

    def __init__(self, minigame: FishingMinigame, page: int, pages: Sequence[int]) -> None:
        self.minigame = minigame
        self.pages = tuple(pages)
        self.closed = False
        self.page = page if page in self.pages else self.pages[0]
        self.button = pygame.Rect((0, 0), BUTTON_SIZE)
        self.turn_button = pygame.Rect((0, 0), BUTTON_SIZE)
        self.demos: dict = {}                # each page's, made when it is first shown
        self._sheets: dict = {}
        self._mouse = {False: mouse_icon(False), True: mouse_icon(True)}
        self._wheel = mouse_icon(wheel=True)
        self._show(self.page)

    def _show(self, page: int) -> None:
        self.page = page
        layout = _LAYOUTS[page]
        centre = self.minigame.canvas.get_width() // 2
        self.button.center = (centre, layout.button_y)
        side = BUTTON_SIZE[0] + _TURN_GAP
        self.turn_button.center = (centre + (side if page == PAGE_CAST else -side), layout.button_y)
        if page not in self.demos:
            screen = self.minigame.screen
            self.demos[page] = ([DepthDemo(screen), CastDemo(screen), StrikeDemo(screen)] if page == PAGE_CAST else
                                [MarkerDemo(screen, 24), StrainDemo(screen), WholeDemo(screen, 26)])

    @property
    def can_turn(self) -> bool:
        return len(self.pages) > 1

    def _turn(self) -> None:
        if self.can_turn:
            self._show(PAGE_FIGHT if self.page == PAGE_CAST else PAGE_CAST)

    # ------------------------------------------------------------------
    # Input and time
    # ------------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE, pygame.K_ESCAPE):
                self.closed = True
            elif event.key in (pygame.K_LEFT, pygame.K_RIGHT):
                self._turn()
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            pos = self._to_canvas(event.pos)
            if self.button.collidepoint(pos):
                self.closed = True
            elif self.can_turn and self.turn_button.collidepoint(pos):
                self._turn()

    def update(self, delta_time: float) -> None:
        dt = min(delta_time, MAX_DT)
        for demo in self.demos[self.page]:
            demo.update(dt)

    def _to_canvas(self, pos: Tuple[int, int]) -> Tuple[int, int]:
        rect = self.minigame.canvas_rect
        return pos[0] - rect.left, pos[1] - rect.top

    # ------------------------------------------------------------------
    # The moving pictures
    # ------------------------------------------------------------------

    def _scene(self, surf: pygame.Surface, demo: PondDemo, rect: pygame.Rect, crop: pygame.Rect) -> None:
        part = demo.picture().subsurface(crop)
        surf.blit(part if part.get_size() == rect.size else pygame.transform.smoothscale(part, rect.size), rect)

    def _say(self, surf: pygame.Surface, verdict, center: Tuple[int, int], width: int) -> None:
        """How it went, as large as fits."""
        if verdict is None:
            return
        text, colour = verdict
        minigame = self.minigame
        font = minigame.font_grade if minigame.font_grade.size(text)[0] <= width - 12 else minigame.font
        label = minigame._inked(text, font, colour)
        surf.blit(label, label.get_rect(center=center))

    def _draw_depth(self, surf: pygame.Surface, rect: pygame.Rect, demo: DepthDemo) -> None:
        self._scene(surf, demo, rect, _DEPTH_CROP)
        font = self.minigame.font_small
        plaque(surf, font, f"Line depth: {demo.depth / PX_PER_FOOT:.0f} ft", (rect.centerx, rect.top + 18))
        sign = (rect.right - 36, rect.top + 72)
        hold_sign(surf, font, self._wheel, "Wheel", sign)
        if demo.turning:                     # which way it is going
            x, y, d = sign[0] - 32, sign[1], demo.turning
            pygame.draw.polygon(surf, BRASS_LIGHT, [(x - 8, y - 8 * d), (x + 8, y - 8 * d), (x, y + 8 * d)])
        self._say(surf, demo.verdict, (rect.centerx, rect.bottom - 26), rect.width)

    def _draw_cast(self, surf: pygame.Surface, rect: pygame.Rect, demo: CastDemo) -> None:
        self._scene(surf, demo, rect, _CAST_CROP)
        hold_sign(surf, self.minigame.font_small, self._mouse[demo.held], demo.sign,
                  (rect.left + 300 + round(demo.mouse_offset), rect.top + 62))
        self._say(surf, demo.verdict, (rect.centerx + 60, rect.top + 150), rect.width)
        if demo.landing:
            self._say(surf, (demo.landing, (226, 226, 210)), (rect.centerx + 60, rect.top + 184), rect.width)

    def _draw_strike(self, surf: pygame.Surface, rect: pygame.Rect, demo: StrikeDemo) -> None:
        self._scene(surf, demo, rect, _STRIKE_CROP)
        rise = round(30 * demo.flick / _FLICK_S) if demo.flick > 0 else 0
        center = (rect.left + 40, rect.bottom - 64 - rise)
        hold_sign(surf, self.minigame.font_small, self._mouse[False], demo.sign, center)
        if demo.flick > 0:                   # the flick's arrow
            x, y = center[0] + 34, center[1]
            pygame.draw.polygon(surf, BRASS_LIGHT, [(x - 9, y), (x + 9, y), (x, y - 16)])
            pygame.draw.rect(surf, BRASS_LIGHT, (x - 3, y, 6, 14))
        self._say(surf, demo.verdict, (rect.centerx, rect.top + 26), rect.width)

    def _draw_fight(self, surf: pygame.Surface, rect: pygame.Rect, demo: FightDemo, crop: pygame.Rect,
                    meters_left: Optional[int] = None) -> pygame.Rect:
        """The fight's scene with its bar and meters at their own size, not made small with the scene."""
        self._scene(surf, demo, rect, crop)
        bar = pygame.Rect(rect.left + _FIGHT_BAR_INSET, rect.top + 14, rect.width - 2 * _FIGHT_BAR_INSET, _FIGHT_BAR_H)
        g = demo.game
        if g.phase == FIGHT and g.fight is not None:
            g._draw_fight_bar(surf, bar)
            if meters_left is not None:
                left, y = rect.left + meters_left, bar.bottom + 36
                width = rect.right - _FIGHT_BAR_INSET - left
                g._draw_fight_meters(surf, pygame.Rect(left, y, width, 9), pygame.Rect(left, y + 16, width, 9))
        return bar

    def _draw_marker(self, surf: pygame.Surface, rect: pygame.Rect, demo: MarkerDemo) -> None:
        bar = self._draw_fight(surf, rect, demo, _MARK_CROP)
        x = bar.left + max(0.0, min(1.0, demo.game.hand)) * bar.width
        icon = self._mouse[demo.held]
        icon_rect = icon.get_rect(center=(round(x), bar.bottom + 66))
        icon_rect.clamp_ip(rect)
        surf.blit(icon, icon_rect)
        self._say(surf, demo.verdict, (rect.centerx, rect.bottom - 26), rect.width)

    def _draw_strain(self, surf: pygame.Surface, rect: pygame.Rect, demo: StrainDemo) -> None:
        self._draw_fight(surf, rect, demo, _MARK_CROP, _METERS_LEFT)
        hold_sign(surf, self.minigame.font_small, self._mouse[demo.held], "Hold" if demo.held else "Let go",
                  (rect.right - 40, rect.bottom - 90))
        self._say(surf, demo.verdict, (rect.centerx, rect.bottom - 26), rect.width)

    def _draw_whole(self, surf: pygame.Surface, rect: pygame.Rect, demo: WholeDemo) -> None:
        self._draw_fight(surf, rect, demo, _WHOLE_CROP, _WHOLE_METERS_LEFT)
        hold_sign(surf, self.minigame.font_small, self._mouse[demo.held], "Hold" if demo.held else "Let go",
                  (rect.right - 40, rect.bottom - 90))
        self._say(surf, demo.verdict, (rect.centerx, rect.bottom - 26), rect.width)

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def draw(self, canvas: pygame.Surface) -> None:
        minigame = self.minigame
        if self.page not in self._sheets:
            self._sheets[self.page] = build_sheet(canvas.get_size(), minigame, _LAYOUTS[self.page], TITLES[self.page],
                                                  CARDS[self.page])
        canvas.blit(self._sheets[self.page], (0, 0))
        drawers = ([self._draw_depth, self._draw_cast, self._draw_strike] if self.page == PAGE_CAST else
                   [self._draw_marker, self._draw_strain, self._draw_whole])
        clip = canvas.get_clip()
        for picture, demo, draw in zip(_LAYOUTS[self.page].picture_rects(), self.demos[self.page], drawers):
            canvas.set_clip(picture)
            draw(canvas, picture, demo)
        canvas.set_clip(clip)

        mouse = self._to_canvas(pygame.mouse.get_pos())
        draw_button(canvas, self.button, BUTTONS[self.page], minigame.font_grade, self.button.collidepoint(mouse))
        if self.can_turn:
            other = PAGE_FIGHT if self.page == PAGE_CAST else PAGE_CAST
            draw_button(canvas, self.turn_button, TURN_LABELS[other], minigame.font_grade,
                        self.turn_button.collidepoint(mouse))
            self._draw_turn_arrow(canvas, other)

    def _draw_turn_arrow(self, canvas: pygame.Surface, other: int) -> None:
        """A little arrow on the other page's button, on the side it lies."""
        rect, d = self.turn_button, 1 if other == PAGE_FIGHT else -1
        x = rect.right - 14 if d > 0 else rect.left + 14
        y = rect.centery
        pygame.draw.polygon(canvas, INK, [(x - 5 * d, y - 7), (x - 5 * d, y + 7), (x + 4 * d, y)])
