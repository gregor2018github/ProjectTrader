"""The fishing minigame's how-to sheet: two parchment pages, as big as the minigame.

The first, the cast: the wheel setting the depth, and a hook set too deep ripping off on the
bottom (I); the rod dragged back, whipped forward and let go at different moments (II); a fish
nibbling and taking, and the flick of the mouse that strikes it, in time, too early and too late
(III). The second, the fight: the fish in and out of the bar and the meter answering (I); the bar
rising, falling and hovering on the space bar (II); a whole fight with a chest, up to the net (III).

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
    CARD, DEG_PER_PX, DRAW, FIGHT, FLIGHT, FishingMinigame, Fight, LANDING, LEADER_START, LEADER_STEP, PAGE_CAST,
    PAGE_FIGHT, PERFECT_CATCH_MULT, READY, READY_THETA, RETRIEVE, SWEET_THETA, STUCK, WAIT, WORMS,
)
from .fishing_pond import APPROACH, NIBBLE, PX_PER_FOOT, SPECIES, TAKE, Fish, length_px
from .fishing_scene import PX
from .tutorial_sheet import (
    BAD, BRASS_LIGHT, BUTTON_SIZE, GOOD, INK, MAX_DT, SheetLayout, build_sheet, draw_button, hold_sign, mouse_icon, plaque,
    space_icon,
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
        ("Keep him in the bar", "The fish moves by itself. While he is *inside the green bar* the meter fills; "
                                "out of it, it *drains*. Full: he is yours. Empty: he is gone."),
        ("Tap to hover", "*Hold Space* and the bar rises, *let go* and it falls, and it keeps moving a moment. "
                         "*Tap* to keep it hovering. The left button works too."),
        ("Chests and perfection", "A *chest* pays coins if kept in the bar a moment, and the meter waits meanwhile. "
                                  f"A fish that never left the bar is a *perfect catch*: it pays ×{PERFECT_CATCH_MULT:g}."),
    ),
}

_LAYOUTS = {
    PAGE_CAST: SheetLayout(card_widths=(290, 614, 320), cards_bottom=650, picture_h=340, button_y=692),
    PAGE_FIGHT: SheetLayout(card_widths=(330, 330, 564), cards_bottom=650, picture_h=340, button_y=692),
}
_TURN_GAP = 16

# Which part of the scene (1296 x 640) each picture shows; the first and last of the first page at full size
_DEPTH_X, _STRIKE_X = 124, 149           # where in the pond (low pixels) their bait goes in
_DEPTH_CROP = pygame.Rect(_DEPTH_X * PX - 133, 200, 266, 340)
_CAST_CROP = pygame.Rect(0, 0, 1118, 640)
_STRIKE_CROP = pygame.Rect(_STRIKE_X * PX - 148, 200, 296, 340)
_MARK_CROP = pygame.Rect(312, 0, 576, 640)
_WHOLE_CROP = pygame.Rect(0, 0, 1016, 640)

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
_FIGHT_FISH = ("perch", 25.0)            # lively, and not too heavy for a script to keep in the bar
_FIGHT_FROM = (159.0, 85.0)
_FIGHT_HOLD = 0.8                        # a good strike's hook
_AFTER_FIGHT_S = 1.8                     # looking at how it ended
_LOOK_AHEAD_S = 0.28                     # how far ahead the script's hand reckons the bar's way
_IN_S, _OUT_S = 4.0, 2.2                 # the meter's picture: in the bar so long, let go so long
_METER_KEPT = (0.2, 0.85)                # and it never ends there: the meter stays between these
_HOVER_STAGES = (("hold", 0.9, "Hold: it rises"), ("drop", 0.9, "Let go: it falls"), ("tap", 4.0, "Tap: it hovers"))
_HOVER_AT = 0.5                          # where it hovers
_CHEST_AT_S = 2.5                        # the whole fight's picture: when the chest comes
_COLUMN_INSET, _COLUMN_W, _METER_W_SMALL, _COLUMN_FOOT = 14, 34, 10, 58


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


def _hand_for(fight: Fight, aim: float) -> bool:
    """The script's hand: whether to hold the button for the bar to go to aim."""
    return fight.bar_at + fight.bar_v * _LOOK_AHEAD_S < aim


class _CalmFight(Fight):
    """A fish that moves smoothly, without a chest: nothing to distract from what a picture shows."""

    def __init__(self, fish: Fish, hold: float, rng: random.Random) -> None:
        super().__init__(fish, hold, rng)
        self.chest_in = None
        self.band, self.keep_s, self.turn, self.anywhere = (0.25, 0.75), (1.6, 2.8), 4.0, 0.0


class _StillFight(_CalmFight):
    """A fish that stays where it is, and a meter that stays too: only the bar moves."""

    def __init__(self, fish: Fish, hold: float, rng: random.Random) -> None:
        super().__init__(fish, hold, rng)
        self.fill = self.drain = 0.0

    def _swim(self, dt: float) -> None:
        pass


class _ChestFight(Fight):
    """Always with a chest, soon."""

    def __init__(self, fish: Fish, hold: float, rng: random.Random) -> None:
        super().__init__(fish, hold, rng)
        self.chest_in = _CHEST_AT_S


class FightDemo(PondDemo):
    """A fish on the line and a script at the reel; when the fight is over, another one."""

    fight_class = Fight

    def __init__(self, screen: pygame.Surface, seed: int) -> None:
        super().__init__(screen, seed)
        self.sign = ""
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
        g.fight = self.fight_class(fish, _FIGHT_HOLD, g.rng)
        g.popups.clear()
        self.verdict, self.held, self.timer, self.ended = None, False, 0.0, 0.0

    def _play(self, dt: float, fight: Fight) -> None:
        """Works the button for this moment of the fight."""
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


class MeterDemo(FightDemo):
    """In the bar for a while and the meter fills, then let go and it drains. It never ends here."""

    fight_class = _CalmFight

    def _play(self, dt: float, fight: Fight) -> None:
        fight.catch = min(max(fight.catch, _METER_KEPT[0]), _METER_KEPT[1])
        out = self.timer % (_IN_S + _OUT_S) >= _IN_S
        self.held = False if out else _hand_for(fight, fight.fish_at)
        if fight.grace > 0:
            self.verdict = None
        elif fight.fish_in_bar:
            self.verdict = ("In the bar: it fills", GOOD)
        else:
            self.verdict = ("Out of it: it drains", BAD)


class HoverDemo(FightDemo):
    """Only the bar: it rises while held, falls when let go, and hovers on quick taps."""

    fight_class = _StillFight

    def __init__(self, screen: pygame.Surface) -> None:
        self.stage = 0
        self.stage_t = 0.0
        super().__init__(screen, 25)

    def _play(self, dt: float, fight: Fight) -> None:
        fight.grace = 0.0
        kind, seconds, text = _HOVER_STAGES[self.stage]
        self.stage_t += dt
        if self.stage_t >= seconds:
            self.stage = (self.stage + 1) % len(_HOVER_STAGES)
            self.stage_t = 0.0
        self.held = kind == "hold" or (kind == "tap" and _hand_for(fight, _HOVER_AT))
        self.verdict = (text, (226, 226, 200))


class WholeDemo(FightDemo):
    """A whole fight, played as it should be: following the fish, taking the chest in passing, up to the net."""

    fight_class = _ChestFight

    def _play(self, dt: float, fight: Fight) -> None:
        aim = fight.chest.at if fight.chest is not None else fight.fish_at
        self.held = _hand_for(fight, aim)
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
        self._space = {False: space_icon(False), True: space_icon(True)}
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
                                [MeterDemo(screen, 24), HoverDemo(screen), WholeDemo(screen, 26)])

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
                  (rect.left + 351 + round(demo.mouse_offset), rect.top + 62))
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

    def _draw_fight(self, surf: pygame.Surface, rect: pygame.Rect, demo: FightDemo, crop: pygame.Rect) -> None:
        """The fight's scene with its column at its own size, not made small with the scene, and the key."""
        self._scene(surf, demo, rect, crop)
        g = demo.game
        if g.phase == FIGHT and g.fight is not None:
            well = pygame.Rect(rect.left + _COLUMN_INSET, rect.top + _COLUMN_INSET, _COLUMN_W,
                               rect.height - _COLUMN_INSET - _COLUMN_FOOT)
            g._draw_column(surf, well, _METER_W_SMALL)
        hold_sign(surf, self.minigame.font_small, self._space[demo.held], "Space: held" if demo.held else "Space: let go",
                  (rect.right - 54, rect.top + 40))
        self._say(surf, demo.verdict, (rect.centerx, rect.bottom - 26), rect.width)

    def _draw_meter(self, surf: pygame.Surface, rect: pygame.Rect, demo: MeterDemo) -> None:
        self._draw_fight(surf, rect, demo, _MARK_CROP)

    def _draw_hover(self, surf: pygame.Surface, rect: pygame.Rect, demo: HoverDemo) -> None:
        self._draw_fight(surf, rect, demo, _MARK_CROP)

    def _draw_whole(self, surf: pygame.Surface, rect: pygame.Rect, demo: WholeDemo) -> None:
        self._draw_fight(surf, rect, demo, _WHOLE_CROP)

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
                   [self._draw_meter, self._draw_hover, self._draw_whole])
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
