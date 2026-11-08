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
from typing import List, Optional, Tuple

import pygame

from .woodhacking import (
    AIM_MAX, OPT_WIDTH, POWER_RATE, WoodhackingMinigame, draw_divider, draw_flourish, next_aim,
)
from .woodhacking_scene import SHORT, SPLIT, WHIFF, ChoppingScene
from ...config.colors import GOLD, MUTED_DARK_RED, WHITE
from ...ui.paper import draw_paper

_INK = (44, 32, 22)
_RUBRIC = MUTED_DARK_RED                # the red ink of a manuscript's emphasised words
_BRASS, _BRASS_LIGHT, _BRASS_DARK = (196, 154, 64), (236, 204, 120), (120, 86, 30)
_GOOD, _BAD = (146, 214, 120), (240, 120, 96)
_MAX_DT = 0.05                          # a slow frame does not make the pictures jump

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

# The sheet, in the minigame's canvas pixels
_FRAME_INSET = 13
_TITLE_Y, _DIVIDER_Y = 52, 84
_CARDS_LEFT, _CARDS_TOP, _CARDS_BOTTOM = 30, 98, 532
_CARD_WIDTHS = (268, 268, 396)
_CARD_GAP = 12
_CARD_PAD = 12
_HEADING_H = 42
_PICTURE_H = 244
_LINE_H = 27
_BUTTON_SIZE = (176, 44)
_BUTTON_Y = 572

# Which part of the scene (1000 x 520) each picture shows
_POST_CROP = pygame.Rect(0, 60, 378, 378)
_BOB_CROP = pygame.Rect(370, 30, 380, 380)
_SCENE_CROP = pygame.Rect(20, 15, 744, 488)

_MOUSE_SIZE = (40, 60)
_SUPERSAMPLE = 4

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


def _mouse_icon(pressed: bool) -> pygame.Surface:
    """A mouse, drawn large and smoothed down: its left button gilded while it is pressed."""
    k = _SUPERSAMPLE
    w, h = _MOUSE_SIZE
    art = pygame.Surface((w * k, h * k), pygame.SRCALPHA)
    body = art.get_rect().inflate(-2 * k, -2 * k)
    radius = 17 * k
    pygame.draw.rect(art, (236, 222, 186), body, border_radius=radius)
    split_y = body.top + 25 * k
    if pressed:
        left = pygame.Surface(art.get_size(), pygame.SRCALPHA)
        pygame.draw.rect(left, (*GOLD, 255), body, border_radius=radius)
        left.fill((0, 0, 0, 0), (body.centerx, 0, art.get_width(), art.get_height()))
        left.fill((0, 0, 0, 0), (0, split_y, art.get_width(), art.get_height()))
        art.blit(left, (0, 0))
    pygame.draw.rect(art, _INK, body, 2 * k, border_radius=radius)
    pygame.draw.line(art, _INK, (body.left, split_y), (body.right, split_y), 2 * k)
    pygame.draw.line(art, _INK, (body.centerx, body.top), (body.centerx, split_y), 2 * k)
    return pygame.transform.smoothscale(art, _MOUSE_SIZE)


class WoodhackingTutorial:
    """The how-to page: drawn on the minigame's canvas over everything, closed by its button,
    Enter, Space or Escape. The game waits behind it."""

    def __init__(self, minigame: WoodhackingMinigame) -> None:
        self.minigame = minigame
        self.closed = False
        self.power_demo = PowerDemo()
        self.bob_demo = BobDemo()
        self.scene_demo = SceneDemo(minigame.font_hit)
        self.button = pygame.Rect((0, 0), _BUTTON_SIZE)
        self._page: Optional[pygame.Surface] = None          # all that does not move
        self._pictures = self._picture_rects()
        self._backdrop: Optional[pygame.Surface] = None      # the scene at rest, under the first two pictures
        self._work: Optional[pygame.Surface] = None
        self._mouse = {False: _mouse_icon(False), True: _mouse_icon(True)}

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
        dt = min(delta_time, _MAX_DT)
        self.power_demo.update(dt)
        self.bob_demo.update(dt)
        self.scene_demo.update(dt)

    # ------------------------------------------------------------------
    # The sheet
    # ------------------------------------------------------------------

    @staticmethod
    def _card_rects() -> List[pygame.Rect]:
        rects, x = [], _CARDS_LEFT
        for width in _CARD_WIDTHS:
            rects.append(pygame.Rect(x, _CARDS_TOP, width, _CARDS_BOTTOM - _CARDS_TOP))
            x += width + _CARD_GAP
        return rects

    def _picture_rects(self) -> List[pygame.Rect]:
        return [pygame.Rect(card.left + _CARD_PAD, card.top + _HEADING_H + 8, card.width - 2 * _CARD_PAD, _PICTURE_H)
                for card in self._card_rects()]

    def _build_page(self, size: Tuple[int, int]) -> pygame.Surface:
        minigame = self.minigame
        page = pygame.Surface(size)
        sheet = page.get_rect()
        draw_paper(page, sheet, sheet.topleft)
        pygame.draw.rect(page, (150, 108, 30), sheet, 6)
        pygame.draw.rect(page, GOLD, sheet.inflate(-4, -4), 3)
        inner = sheet.inflate(-2 * _FRAME_INSET, -2 * _FRAME_INSET)
        pygame.draw.rect(page, (150, 108, 30), inner, 1)
        for sx, sy, corner in ((1, 1, inner.topleft), (-1, 1, inner.topright),
                               (1, -1, inner.bottomleft), (-1, -1, inner.bottomright)):
            draw_flourish(page, corner, sx, sy)

        title = minigame._inked(TITLE, minigame.font_title, GOLD)
        page.blit(title, title.get_rect(center=(sheet.centerx, _TITLE_Y)))
        draw_divider(page, (sheet.centerx, _DIVIDER_Y), 170)

        for number, (card, picture, (heading, words)) in enumerate(zip(self._card_rects(), self._pictures, CARDS), 1):
            self._draw_card(page, card, picture, number, heading, words)
        self.button.center = (sheet.centerx, _BUTTON_Y)
        return page

    def _draw_card(self, page: pygame.Surface, card: pygame.Rect, picture: pygame.Rect,
                   number: int, heading: str, words: str) -> None:
        """A card: a paler leaf, ruled in brass, with a rubric numeral, a heading, a frame
        waiting for its picture, and the words under it."""
        minigame = self.minigame
        leaf = pygame.Surface(card.size, pygame.SRCALPHA)
        leaf.fill((255, 248, 226, 96))
        page.blit(leaf, card.topleft)
        pygame.draw.rect(page, _BRASS_DARK, card, 2, border_radius=4)
        pygame.draw.rect(page, _BRASS, card.inflate(-6, -6), 1, border_radius=3)

        seal = pygame.Rect(card.left + _CARD_PAD, card.top + 10, 32, 32)
        pygame.draw.rect(page, _RUBRIC, seal, border_radius=3)
        pygame.draw.rect(page, GOLD, seal, 2, border_radius=3)
        numeral = minigame.font.render("I" * number, True, _BRASS_LIGHT)
        page.blit(numeral, numeral.get_rect(center=seal.center))
        title = minigame.font_large.render(heading, True, _INK)
        page.blit(title, title.get_rect(midleft=(seal.right + 8, seal.centery)))

        pygame.draw.rect(page, _INK, picture.inflate(8, 8), border_radius=3)
        pygame.draw.rect(page, _BRASS, picture.inflate(6, 6), 2, border_radius=3)
        pygame.draw.rect(page, _BRASS_DARK, picture.inflate(2, 2), 1)

        self._draw_words(page, words, card.left + _CARD_PAD + 2, picture.bottom + 16, card.width - 2 * _CARD_PAD - 4)

    def _draw_words(self, page: pygame.Surface, words: str, x: int, y: int, width: int) -> None:
        """The words broken to the width, those between stars in red ink."""
        font = self.minigame.font_words
        space = font.size(" ")[0]
        cx = x
        red = False
        for word in words.split():
            opens = word.startswith("*")
            red = red or opens
            bare = word.replace("*", "")
            if cx > x and cx + font.size(bare)[0] > x + width:
                cx, y = x, y + _LINE_H
            page.blit(font.render(bare, True, _RUBRIC if red else _INK), (cx, y))
            cx += font.size(bare)[0] + space
            if word.rstrip(".,:;!?").endswith("*"):
                red = False

    # ------------------------------------------------------------------
    # The moving pictures
    # ------------------------------------------------------------------

    def _hold_sign(self, surf: pygame.Surface, held: bool, center: Tuple[int, int]) -> None:
        """The mouse and what it is doing."""
        icon = self._mouse[held]
        rect = icon.get_rect(center=center)
        surf.blit(icon, rect)
        self.minigame._plaque(surf, "Hold" if held else "Let go", (rect.centerx, rect.bottom + 15))

    def _verdict(self, surf: pygame.Surface, verdict: Optional[Tuple[str, bool]], center: Tuple[int, int]) -> None:
        if verdict is not None:
            text, good = verdict
            label = self.minigame._inked(text, self.minigame.font_grade, _GOOD if good else _BAD)
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
            label = self.minigame._inked("Faster!", self.minigame.font_grade, _BRASS_LIGHT)
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
            self._page = self._build_page(canvas.get_size())
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
        pygame.draw.rect(canvas, _BRASS_LIGHT if hovered else _BRASS, self.button, border_radius=4)
        pygame.draw.line(canvas, WHITE if hovered else _BRASS_LIGHT, (self.button.left + 4, self.button.top + 3),
                         (self.button.right - 5, self.button.top + 3), 1)
        pygame.draw.rect(canvas, _BRASS_DARK, self.button, 2, border_radius=4)
        label = self.minigame.font_grade.render(BUTTON, True, _INK)
        canvas.blit(label, label.get_rect(center=self.button.center))
