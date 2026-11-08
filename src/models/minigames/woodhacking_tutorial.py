"""The woodhacking minigame's how-to page: one parchment sheet, as big as the minigame.

Three cards, each a few words under a moving picture that plays by itself: the
power post with a mouse being held and let go (I), the plumb bob speeding up
while the mouse is held (II), and a small copy of the real chopping scene
playing the two together, a good swing and two bad ones (III). The gauges are
the game's own, drawn by ``WoodhackingMinigame`` and run by the game's rules
(``next_aim``, ``POWER_RATE``), so the page cannot drift from what it explains.

The minigame opens it by itself the first time (``TIP_TUTORIAL``, remembered in
``Statistics.minigame_tips_seen``); its "How to play" button opens it again.
"""

import random
from dataclasses import dataclass
from typing import Optional, Tuple

import pygame

from .tutorial_sheet import (
    BAD, BRASS_LIGHT, BUTTON_SIZE, GOOD, MAX_DT, SheetLayout, build_sheet, draw_button, hold_sign, mouse_icon,
)
from .woodhacking import OPT_WIDTH, POWER_RATE, WoodhackingMinigame, next_aim
from .woodhacking_scene import SHORT, SPLIT, WHIFF, ChoppingScene

TITLE = "How to Swing the Axe"
BUTTON = "To the axe!"
#: Each card: its heading, and its words, *these* in red ink
CARDS = (
    ("Gather power", "*Hold* the left mouse button and the power rises. *Let go* in the green. "
                     "After a good swing the green moves."),
    ("Mind the plumb bob", "It never rests, and it swings *faster* while you hold. "
                           "Its best place is right in the *middle*."),
    ("Strike!", "Let go when power and plumb bob both stand *in the green*: the log splits. "
                "The nearer their middles, the more you earn."),
)

_LAYOUT = SheetLayout(card_widths=(268, 268, 396), cards_bottom=532, picture_h=244, button_y=572)

# Which part of the scene (1000 x 520) each picture shows
_POST_CROP = pygame.Rect(0, 60, 378, 378)
_BOB_CROP = pygame.Rect(370, 30, 380, 380)
_SCENE_CROP = pygame.Rect(20, 15, 744, 488)

# The power post's picture: where each try lets go, and how the green moves on after a good one
_POWER_TRIES = (0.64, 0.14, 0.36, 0.92)   # right, too weak, right (the green has moved), too strong
_POWER_ZONES = (0.64, 0.36, 0.36, 0.64)   # where the green's middle stands during each try
_WAIT_S = 0.7                             # before a try's hold
_VERDICT_S = 1.3                          # how long a try's outcome stays
_ZONE_GLIDE_S = 0.35                      # the green gliding to its new place, at the end of that

# The plumb bob's picture: the bob swings on its own for a while, then with the button held
_BOB_FREE_S = 2.6
_BOB_HELD_S = 1.6


@dataclass(frozen=True)
class _Try:
    """A swing of the scene's picture: the green's middle during it, the power it lets go at,
    where the bob must then be, what the axe does and what is said about it."""
    zone: float
    release: float
    aim: float
    outcome: str
    verdict: str
    good: bool


_SCENE_TRIES = (
    _Try(0.64, 0.64, 0.0, SPLIT, "Split!", True),
    _Try(0.45, 0.45, 1.33, WHIFF, "Bob off the mark!", False),   # in the dark red, an outright miss
    _Try(0.45, 0.45, 0.0, SPLIT, "Split!", True),
    _Try(0.72, 0.24, 0.0, SHORT, "Too little power!", False),
    _Try(0.72, 0.72, 0.0, SPLIT, "Split!", True),
)
_AIM_TOLERANCE = 0.05                     # the hold starts when it will end this near the aim wanted
_SCENE_WAIT_S = 0.9                       # at least this long between swings
_SCENE_VERDICT_S = 1.1
_PILE_KEPT = 9                            # the little scene's woodpile starts over past this
_PREDICT_DT = 1 / 60


def _zone(centre: float) -> Tuple[float, float]:
    return centre - OPT_WIDTH / 2, centre + OPT_WIDTH / 2


class PowerDemo:
    """Hold, let go, see how it went; the green moves on after a good try."""

    def __init__(self) -> None:
        self.index = 0
        self.power = 0.0
        self.held = False
        self.verdict: Optional[Tuple[str, bool]] = None
        self._phase, self._timer = "wait", 0.0
        self.centre = _POWER_ZONES[0]

    @property
    def zone(self) -> Tuple[float, float]:
        return _zone(self.centre)

    def update(self, dt: float) -> None:
        self._timer += dt
        if self._phase == "wait":
            if self._timer >= _WAIT_S:
                self._phase, self._timer, self.held = "hold", 0.0, True
        elif self._phase == "hold":
            target = _POWER_TRIES[self.index]
            self.power = min(target, self.power + POWER_RATE * dt)
            if self.power >= target:
                lo, hi = self.zone
                good = lo <= self.power <= hi
                text = "Just right!" if good else ("Too weak!" if self.power < lo else "Too strong!")
                self.verdict = (text, good)
                self._phase, self._timer, self.held = "verdict", 0.0, False
        else:
            next_index = (self.index + 1) % len(_POWER_TRIES)
            glide_from = _VERDICT_S - _ZONE_GLIDE_S
            if self._timer >= glide_from:          # the post empties and the green goes to its next place
                k = min(1.0, (self._timer - glide_from) / _ZONE_GLIDE_S)
                self.power = _POWER_TRIES[self.index] * (1 - k)
                self.centre = _POWER_ZONES[self.index] + (_POWER_ZONES[next_index] - _POWER_ZONES[self.index]) * k
            if self._timer >= _VERDICT_S:
                self.index = next_index
                self.power, self.verdict = 0.0, None
                self._phase, self._timer = "wait", 0.0


class BobDemo:
    """The bob on its own, then with the button held: the speed-up is the point."""

    def __init__(self) -> None:
        self.aim, self.direction = 0.0, 1
        self.power = 0.0
        self.held = False
        self._timer = 0.0

    def update(self, dt: float) -> None:
        self._timer += dt
        if self._timer >= (_BOB_HELD_S if self.held else _BOB_FREE_S):
            self.held, self._timer = not self.held, 0.0
        self.power = min(1.0, self.power + POWER_RATE * dt) if self.held else 0.0
        self.aim, self.direction = next_aim(self.aim, self.direction, 0.0, self.power, dt)


class SceneDemo:
    """The real chopping scene with its gauges, playing swings by itself. It waits to hold
    until the bob, by the game's own rule, will be where this try wants it on letting go."""

    def __init__(self, font: pygame.font.Font) -> None:
        self.scene = ChoppingScene(font, random.Random(11))    # noon and clear, whatever it is outside
        self.aim, self.direction = -0.7, 1
        self.power = 0.0
        self.held = False
        self.index = 0
        self.verdict: Optional[Tuple[str, bool]] = None
        self._waited = 0.0
        self._verdict_left = 0.0

    @property
    def current(self) -> _Try:
        return _SCENE_TRIES[self.index]

    @property
    def zone(self) -> Tuple[float, float]:
        return _zone(self.current.zone)

    def _aim_at_release(self) -> float:
        """Where the bob will be on letting go at this try's power, if the hold begins now."""
        aim, direction, power = self.aim, self.direction, 0.0
        while power < self.current.release:
            power = min(self.current.release, power + POWER_RATE * _PREDICT_DT)
            aim, direction = next_aim(aim, direction, 0.0, power, _PREDICT_DT)
        return aim

    def update(self, dt: float) -> None:
        self.scene.update(dt)                              # its sounds are not played: the page is quiet
        self.aim, self.direction = next_aim(self.aim, self.direction, 0.0, self.power, dt)
        if self._verdict_left > 0:
            self._verdict_left -= dt
            if self._verdict_left <= 0:
                self.verdict = None
        if self.held:
            self.power = min(self.current.release, self.power + POWER_RATE * dt)
            self.scene.charge(self.power)
            if self.power >= self.current.release:
                self._let_go()
            return
        self._waited += dt
        if self._waited >= _SCENE_WAIT_S and self.scene.can_charge and self.scene.log_ready \
                and self.scene.state != "swing" and abs(abs(self._aim_at_release()) - self.current.aim) < _AIM_TOLERANCE:
            self.held = True

    def _let_go(self) -> None:
        self.held, self.power = False, 0.0
        self.scene.swing(self.current.outcome, label="")   # its popup is left out: the verdict says it
        self.verdict = (self.current.verdict, self.current.good)
        self._verdict_left = _SCENE_VERDICT_S
        self._waited = 0.0
        self.index = (self.index + 1) % len(_SCENE_TRIES)
        if self.index == 0 and self.scene.pile > _PILE_KEPT:
            self.scene.pile = 0


class WoodhackingTutorial:
    """The how-to page: drawn on the minigame's canvas over everything, closed by its button,
    Enter, Space or Escape. The game waits behind it."""

    def __init__(self, minigame: WoodhackingMinigame) -> None:
        self.minigame = minigame
        self.closed = False
        self.power_demo = PowerDemo()
        self.bob_demo = BobDemo()
        self.scene_demo = SceneDemo(minigame.font_hit)
        self.button = pygame.Rect((0, 0), BUTTON_SIZE)
        self.button.center = (minigame.canvas.get_width() // 2, _LAYOUT.button_y)
        self._page: Optional[pygame.Surface] = None          # all that does not move
        self._pictures = _LAYOUT.picture_rects()
        self._backdrop: Optional[pygame.Surface] = None      # the scene at rest, under the first two pictures
        self._work: Optional[pygame.Surface] = None
        self._mouse = {False: mouse_icon(False), True: mouse_icon(True)}

    # ------------------------------------------------------------------
    # Input and time
    # ------------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_KP_ENTER,
                                                          pygame.K_SPACE, pygame.K_ESCAPE):
            self.closed = True
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 \
                and self.button.collidepoint(self.minigame._to_canvas(event.pos)):
            self.closed = True

    def update(self, delta_time: float) -> None:
        dt = min(delta_time, MAX_DT)
        self.power_demo.update(dt)
        self.bob_demo.update(dt)
        self.scene_demo.update(dt)

    # ------------------------------------------------------------------
    # The moving pictures
    # ------------------------------------------------------------------

    def _hold_sign(self, surf: pygame.Surface, held: bool, center: Tuple[int, int]) -> None:
        hold_sign(surf, self.minigame.font_small, self._mouse[held], "Hold" if held else "Let go", center)

    def _verdict(self, surf: pygame.Surface, verdict: Optional[Tuple[str, bool]], center: Tuple[int, int]) -> None:
        if verdict is not None:
            text, good = verdict
            label = self.minigame._inked(text, self.minigame.font_grade, GOOD if good else BAD)
            surf.blit(label, label.get_rect(center=center))

    def _crop(self, crop: pygame.Rect, size: Tuple[int, int], draw_gauge) -> pygame.Surface:
        """That part of the resting scene, with a gauge drawn on it at its own place, made small."""
        self._work.blit(self._backdrop, crop.topleft, crop)
        draw_gauge(self._work)
        return pygame.transform.smoothscale(self._work.subsurface(crop), size)

    def _draw_power_picture(self, surf: pygame.Surface, rect: pygame.Rect) -> None:
        demo = self.power_demo
        lo, hi = demo.zone
        picture = self._crop(_POST_CROP, rect.size,
                             lambda s: self.minigame._draw_power_bar(s, demo.power, lo, hi, demo.held))
        surf.blit(picture, rect)
        self._hold_sign(surf, demo.held, (rect.left + 170, rect.top + 92))
        self._verdict(surf, demo.verdict, (rect.left + 156, rect.top + 170))

    def _draw_bob_picture(self, surf: pygame.Surface, rect: pygame.Rect) -> None:
        demo = self.bob_demo
        picture = self._crop(_BOB_CROP, rect.size, lambda s: self.minigame._draw_aim_gauge(s, demo.aim))
        surf.blit(picture, rect)
        self._hold_sign(surf, demo.held, (rect.left + 36, rect.bottom - 62))
        if demo.held:
            label = self.minigame._inked("Faster!", self.minigame.font_grade, BRASS_LIGHT)
            surf.blit(label, label.get_rect(center=(rect.right - 54, rect.bottom - 30)))

    def _draw_scene_picture(self, surf: pygame.Surface, rect: pygame.Rect) -> None:
        demo = self.scene_demo
        lo, hi = demo.zone

        def gauges(s: pygame.Surface) -> None:
            self.minigame._draw_power_bar(s, demo.power, lo, hi, demo.held)
            self.minigame._draw_aim_gauge(s, demo.aim)

        frame = demo.scene.draw(underlay=gauges)
        surf.blit(pygame.transform.smoothscale(frame.subsurface(_SCENE_CROP), rect.size), rect)
        self._hold_sign(surf, demo.held, (rect.left + 92, rect.top + 44))
        self._verdict(surf, demo.verdict, (rect.right - 104, rect.bottom - 20))

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def draw(self, canvas: pygame.Surface) -> None:
        if self._page is None:
            self._page = build_sheet(canvas.get_size(), self.minigame, _LAYOUT, TITLE, CARDS)
            self._backdrop = self.scene_demo.scene.draw(player=False).copy()
            self._work = self._backdrop.copy()
        canvas.blit(self._page, (0, 0))
        power, bob, scene = self._pictures
        clip = canvas.get_clip()
        for picture, draw in ((power, self._draw_power_picture), (bob, self._draw_bob_picture),
                              (scene, self._draw_scene_picture)):
            canvas.set_clip(picture)
            draw(canvas, picture)
        canvas.set_clip(clip)

        hovered = self.button.collidepoint(self.minigame._to_canvas(pygame.mouse.get_pos()))
        draw_button(canvas, self.button, BUTTON, self.minigame.font_grade, hovered)
