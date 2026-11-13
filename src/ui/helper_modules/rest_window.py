"""Resting: the clock on which the player chooses how long ("Rest" in the uncle's shop menu).

A 24-hour dial with the moment the window opened at its top and the hours
running clockwise from it, so the gold arc from the top to the hand is the time
rested. The dial's ring is coloured by the daylight of the day ahead (the map's
own light, `daylight.ambient_light`): deep blue with stars by night, pale by day,
the sun at the brightest hour and the moon at the darkest; the clock's hours are
written round it. In the middle, on a slate disc, how long the rest is and when
it ends.

The hand starts at the next sunrise (`rest.default_end`) and moves in steps of
`REST_STEP_MINUTES`: dragged, clicked to on the ring, by the wheel (Shift: a
whole hour) or the arrow keys (left and right a step, up and down an hour).
"Rest" (or Enter) first lets everything behind the window go dark
(`DARKEN_SECONDS`), then sets the clock turning: a hand sweeps clockwise from the
top, now, round to the chosen moment (`turn_seconds`, slow to start and to stop,
and a short rest slower than its share of the dial would have it), the slate
counting the hours as they pass and the tiredness bar emptying with them, and
the gold of the rest still to come shrinking ahead of it. It rests there a
moment (`ARRIVED_SECONDS`); then the clock is moved on and the tiredness brought
down (`Tiredness.rest`), and the window on black dissolves into the game as it
now is (`Game.fade_in_from`). A click or a key meanwhile wakes the player at
once, at the chosen moment all the same. The game is
paused while the window is open; `animate(dt)` is called by the main loop.
"""

import datetime
import math
import os
import random
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

import pygame
import pygame.gfxdraw

from .loan_dialog import _BaseDialog, _close_dialog
from ...config.colors import BLACK, DARK_BROWN
from ...config.constants import FONTS_PATH
from ...models.daylight import ambient_light
from ...models.rest import (MAX_REST_HOURS, REST_STEP_MINUTES, default_end, first_step, latest_end,
                            snap_end, tiredness_after_rest)
from ...sim.calendar import format_long

if TYPE_CHECKING:
    from ...game_state import GameState

#: The dial's size: its outer edge, the ring's inner edge and the slate's edge
DIAL_RADIUS = 236
RING_WIDTH = 64
SLATE_RADIUS = DIAL_RADIUS - RING_WIDTH - 10
#: The ring is drawn in this many pieces, and twice as large, then smoothed down
RING_SEGMENTS = 240
SUPERSAMPLE = 2

#: The ring's colours: the night's blue and the day's parchment, the light between them by channel
NIGHT_BLUE = (24, 44, 112)
DAY_PALE = (238, 232, 212)
NIGHT_LIGHT = (30, 30, 70)          # daylight.AMBIENT_KEYFRAMES' night
GOLD = (222, 182, 64)
GOLD_DARK = (150, 110, 30)
GOLD_LIGHT = (255, 232, 150)
RIM_SILVER = (196, 198, 204)
RIM_DARK = (92, 94, 104)
SLATE = (98, 100, 104)
TEXT_PALE = (238, 236, 228)
TEXT_SOFT = (200, 200, 196)
NUMERAL_DARK = (70, 72, 96)
STAR = (250, 240, 200)

#: How long everything behind the window takes to go dark before the clock turns
DARKEN_SECONDS = 0.8
#: How long the clock takes to turn to the chosen moment: a base, more by the square root of the
#: hours (so a short rest turns slower for its share of the dial than a long one), within limits
TURN_SECONDS_BASE = 2.2
TURN_SECONDS_PER_ROOT_HOUR = 0.6
TURN_SECONDS_MIN = 2.5
TURN_SECONDS_MAX = 5.0
#: How long the hand stays at the chosen moment before the game comes back
ARRIVED_SECONDS = 0.35
#: The most a frame moves it on, so a stutter does not skip the dark or the turn
MAX_FRAME_SECONDS = 0.05
HAND_SILVER = (226, 228, 234)

PANEL_W = 620
DIAL_TOP = 66             # the dial's top, below the panel's
BUTTON_W, BUTTON_H, BUTTON_GAP = 160, 38, 14


def open_rest_window(game_state: 'GameState') -> None:
    game_state.info_window = RestWindow(game_state.screen, game_state)


def turn_seconds(hours: float) -> float:
    """How long the clock takes to turn through a rest of that many hours."""
    return min(TURN_SECONDS_MAX, max(TURN_SECONDS_MIN,
                                     TURN_SECONDS_BASE + TURN_SECONDS_PER_ROOT_HOUR * math.sqrt(max(0.0, hours))))


def _ease(t: float) -> float:
    """Slow to start and to stop."""
    t = min(1.0, max(0.0, t))
    return t * t * (3 - 2 * t)


def describe_hours(span: datetime.timedelta) -> str:
    """'8 h 30 min', '1 h', '45 min' (to the whole minute)."""
    minutes = max(0, round(span.total_seconds() / 60))
    hours, minutes = divmod(minutes, 60)
    if hours and minutes:
        return f"{hours} h {minutes} min"
    return f"{hours} h" if hours else f"{minutes} min"


def _font(name: str, size: int) -> pygame.font.Font:
    try:
        return pygame.font.Font(os.path.join(FONTS_PATH, name), size)
    except Exception:
        return pygame.font.SysFont("georgia", size)


def _mix(a, b, t: float) -> Tuple[int, int, int]:
    t = min(1.0, max(0.0, t))
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def _ring_colour(light: Tuple[int, int, int]) -> Tuple[int, int, int]:
    """The ring's colour under that light: night blue at the night's light, pale in full day, each
    channel on its own between them, so the dawn and the dusk show their red."""
    return tuple(round(n + (d - n) * min(1.0, max(0.0, (l - k) / (255 - k))))
                 for n, d, l, k in zip(NIGHT_BLUE, DAY_PALE, light, NIGHT_LIGHT))


def _brightness(light: Tuple[int, int, int]) -> float:
    return min(1.0, max(0.0, (sum(light) / 3 - 43) / (255 - 43)))


class RestWindow(_BaseDialog):
    #: Keeps the map from zooming under the wheel (EventHandler skips it for a window with this)
    _max_scroll = 0

    def __init__(self, screen: pygame.Surface, game_state: 'GameState') -> None:
        self.now: datetime.datetime = game_state.date
        self.sunrise: datetime.datetime = default_end(self.now)
        self.end: datetime.datetime = self.sunrise
        self.dragging = False
        self._drag_hours = self.hours_ahead
        # The seconds since "Rest" was pressed (None till then): the dark falling, the clock
        # turning (turn_s of it), and its pause at the chosen moment
        self.turn_t: Optional[float] = None
        self.turn_s = 0.0
        self._veil: Optional[pygame.Surface] = None
        self.big_font = _font("Medici Text.ttf", 46)
        self.caption_font = _font("Augusta.ttf", 19)
        self.small_font = _font("Augusta.ttf", 18)
        height = DIAL_TOP + 2 * DIAL_RADIUS + 22 + 64 + BUTTON_H + 38
        super().__init__(screen, game_state, PANEL_W, height)
        self.centre = (self.panel.centerx, self.panel.top + DIAL_TOP + DIAL_RADIUS)
        buttons_y = self.panel.bottom - BUTTON_H - 22
        left = self.panel.centerx - (3 * BUTTON_W + 2 * BUTTON_GAP) // 2
        self.buttons: Dict[str, pygame.Rect] = {
            key: pygame.Rect(left + i * (BUTTON_W + BUTTON_GAP), buttons_y, BUTTON_W, BUTTON_H)
            for i, key in enumerate(("sunrise", "rest", "cancel"))}
        self.labels = {"sunrise": "Until sunrise", "rest": "Rest", "cancel": "Cancel"}
        self.dial = self._make_dial()
        # The game waits while the hand is being set
        self.restore_time_level = game_state.time_level
        game_state.time_level = 1

    # -- the hand --------------------------------------------------------------

    @property
    def hours_ahead(self) -> float:
        return (self.end - self.now).total_seconds() / 3600.0

    @property
    def turning(self) -> bool:
        return self.turn_t is not None

    @property
    def hours_turned(self) -> float:
        """How far the clock has turned, in hours from now: 0 until it is set turning."""
        if self.turn_t is None:
            return 0.0
        turning_for = self.turn_t - DARKEN_SECONDS
        return self.hours_ahead * _ease(turning_for / self.turn_s if self.turn_s > 0 else 1.0)

    @property
    def darkness(self) -> float:
        """How dark everything behind the window is, 0 to 1: falling once "Rest" is pressed."""
        if self.turn_t is None:
            return 0.0
        return _ease(self.turn_t / DARKEN_SECONDS)

    @property
    def total_seconds(self) -> float:
        """From pressing "Rest" to waking: the dark falling, the turn, the pause at its end."""
        return DARKEN_SECONDS + self.turn_s + ARRIVED_SECONDS

    def angle_of(self, hours: float) -> float:
        """The angle on the dial, clockwise from its top in radians, of a moment that many hours on."""
        return hours / MAX_REST_HOURS * 2 * math.pi

    def point_at(self, hours: float, radius: float) -> Tuple[float, float]:
        angle = self.angle_of(hours)
        return self.centre[0] + radius * math.sin(angle), self.centre[1] - radius * math.cos(angle)

    def hours_at(self, pos: Tuple[int, int]) -> float:
        """The hours on, 0 to 24, of the dial's direction to `pos`."""
        angle = math.atan2(pos[0] - self.centre[0], self.centre[1] - pos[1]) % (2 * math.pi)
        return angle / (2 * math.pi) * MAX_REST_HOURS

    def set_end(self, end: datetime.datetime) -> None:
        self.end = snap_end(self.now, end)
        self._drag_hours = self.hours_ahead

    def step(self, steps: int) -> None:
        self.set_end(self.end + datetime.timedelta(minutes=REST_STEP_MINUTES * steps))

    def _follow(self, pos: Tuple[int, int]) -> None:
        """Put the hand where the pointer points, going round the dial the shorter way from where it
        was, so a drag past the top stops at the shortest or the longest rest instead of jumping."""
        raw = self.hours_at(pos)
        hours = min((raw + turn * MAX_REST_HOURS for turn in (-1, 0, 1)), key=lambda h: abs(h - self._drag_hours))
        lowest = (first_step(self.now) - self.now).total_seconds() / 3600.0
        highest = (latest_end(self.now) - self.now).total_seconds() / 3600.0
        hours = min(highest, max(lowest, hours))
        self._drag_hours = hours
        self.end = snap_end(self.now, self.now + datetime.timedelta(hours=hours))

    def on_dial(self, pos: Tuple[int, int]) -> bool:
        """Whether `pos` is on the ring (or just outside it), where a press takes the hand."""
        distance = math.hypot(pos[0] - self.centre[0], pos[1] - self.centre[1])
        return SLATE_RADIUS - 6 <= distance <= DIAL_RADIUS + 14

    # -- input -----------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> None:
        if self.turning:
            if event.type == pygame.KEYDOWN:
                self.wake()           # any key: up at once
            return
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.close()
            elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.rest()
            elif event.key == pygame.K_RIGHT:
                self.step(1)
            elif event.key == pygame.K_LEFT:
                self.step(-1)
            elif event.key == pygame.K_UP:
                self.step(60 // REST_STEP_MINUTES)
            elif event.key == pygame.K_DOWN:
                self.step(-60 // REST_STEP_MINUTES)
        elif event.type == pygame.MOUSEMOTION and self.dragging:
            self._follow(event.pos)
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.dragging = False
        elif event.type == pygame.MOUSEWHEEL:
            hour = 60 // REST_STEP_MINUTES
            self.step(event.y * (hour if pygame.key.get_mods() & pygame.KMOD_SHIFT else 1))

    def handle_click(self, pos: Tuple[int, int]) -> bool:
        if self.turning:
            self.wake()               # any click: up at once
            return True
        if self.close_rect.collidepoint(pos) or not self.panel.collidepoint(pos):
            self.close()
            return True
        if self.buttons["cancel"].collidepoint(pos):
            self.close()
        elif self.buttons["rest"].collidepoint(pos):
            self.rest()
        elif self.buttons["sunrise"].collidepoint(pos):
            self.set_end(self.sunrise)
        elif self.on_dial(pos):
            self._drag_hours = self.hours_ahead
            self._follow(pos)
            self.dragging = True
        return True

    def close(self) -> None:
        self.game_state.time_level = self.restore_time_level
        _close_dialog(self.game_state)

    def rest(self) -> None:
        """Set the clock turning to the hand; the rest is taken when it gets there (`animate`)."""
        if self.turning:
            return
        self.dragging = False
        self.turn_t = 0.0
        self.turn_s = turn_seconds(self.hours_ahead)

    def animate(self, dt: float) -> None:
        """The clock turns on (called each frame by the main loop)."""
        if self.turn_t is None:
            return
        self.turn_t += min(dt, MAX_FRAME_SECONDS)   # a slow frame does not jump the dark or the turn
        if self.turn_t >= self.total_seconds:
            self.wake()

    def wake(self) -> None:
        """Rest until the hand: the clock moves on, the tiredness falls, the picture comes back from black."""
        if self.game_state.info_window is not self:
            return
        game = self.game_state.game
        # What the game comes back from: the window with the hand at the chosen moment, on black
        self.turn_t = max(self.turn_t or 0.0, DARKEN_SECONDS + self.turn_s)
        cover = self._snapshot_on_black()
        span = self.end - self.now
        hours = game.tiredness.rest(self.game_state, self.end)
        weather = getattr(game, "weather", None)
        if weather is not None:
            # The weather takes a jump of the clock as at most MAX_STEP_MINUTES (meant for loading a
            # save): the rest of the time rested is spent on it here, so the night's weather has passed
            from ...models.weather import MAX_STEP_MINUTES
            weather.advance(max(0.0, hours - MAX_STEP_MINUTES / 60.0))
        self.game_state.log_event("SYSTEM", f"Rested {describe_hours(span)}, until {format_long(self.end)}, "
                                            f"{self.end:%H:%M}")
        self.game_state.time_level = self.restore_time_level
        self.game_state.info_window = None
        self.game_state.active_house_menu = None
        if hasattr(game, "fade_in_from"):
            game.fade_in_from(cover)

    def _snapshot_on_black(self) -> pygame.Surface:
        """The window as it is drawn now, on a black screen."""
        cover = pygame.Surface(self.screen.get_size())
        cover.fill(BLACK)
        screen, self.screen = self.screen, cover
        try:
            self.draw()
        finally:
            self.screen = screen
        return cover

    def _draw_veil(self) -> None:
        """Everything behind the window, darkening once "Rest" is pressed."""
        alpha = round(255 * self.darkness)
        if alpha <= 0:
            return
        if self._veil is None or self._veil.get_size() != self.screen.get_size():
            self._veil = pygame.Surface(self.screen.get_size())
            self._veil.fill(BLACK)
        self._veil.set_alpha(alpha)
        self.screen.blit(self._veil, (0, 0))

    # -- the dial, drawn once --------------------------------------------------

    def _make_dial(self) -> pygame.Surface:
        """The ring of the day ahead with its stars, sun, moon and hours, its rims and the slate,
        drawn SUPERSAMPLE times larger and smoothed down."""
        k = SUPERSAMPLE
        size = 2 * (DIAL_RADIUS + 8)
        big = pygame.Surface((size * k, size * k), pygame.SRCALPHA)
        c = (size * k / 2, size * k / 2)
        outer, inner = DIAL_RADIUS * k, (DIAL_RADIUS - RING_WIDTH) * k

        def at(hours: float, radius: float) -> Tuple[float, float]:
            angle = self.angle_of(hours)
            return c[0] + radius * math.sin(angle), c[1] - radius * math.cos(angle)

        # The outer rim, then the ring piece by piece in the light of its hour
        pygame.draw.circle(big, RIM_DARK, c, outer + 7 * k)
        pygame.draw.circle(big, RIM_SILVER, c, outer + 5 * k)
        lights: List[Tuple[int, int, int]] = []
        for i in range(RING_SEGMENTS):
            h0 = i * MAX_REST_HOURS / RING_SEGMENTS
            h1 = (i + 1.05) * MAX_REST_HOURS / RING_SEGMENTS
            light = ambient_light(self.now + datetime.timedelta(hours=h0 + 0.5 * MAX_REST_HOURS / RING_SEGMENTS))
            lights.append(light)
            colour = _ring_colour(light)
            points = [at(h0, outer), at(h1, outer), at(h1, inner), at(h0, inner)]
            pygame.draw.polygon(big, colour, points)

        def light_at(hours: float) -> Tuple[int, int, int]:
            return lights[int(hours / MAX_REST_HOURS * RING_SEGMENTS) % RING_SEGMENTS]

        # Stars where it is dark, the same every time for the same moment
        rng = random.Random(self.now.toordinal() * 24 + self.now.hour)
        mid = (outer + inner) / 2
        first_numeral = (60 - self.now.minute - self.now.second / 60) % 60 / 60   # hours to the next whole hour
        for _ in range(70):
            hours = rng.uniform(0, MAX_REST_HOURS)
            darkness = 1.0 - _brightness(light_at(hours))
            if darkness < 0.55 or rng.random() > darkness:
                continue
            off_numeral = abs((hours - first_numeral + 0.5) % 1.0 - 0.5)
            if off_numeral < 0.3:   # keep clear of the hour written there
                continue
            x, y = at(hours, rng.uniform(inner + 8 * k, outer - 8 * k))
            if rng.random() < 0.3:
                self._sparkle(big, (x, y), rng.uniform(4, 7) * k, STAR)
            else:
                pygame.draw.circle(big, STAR, (x, y), rng.uniform(0.8, 1.6) * k)

        # The sun at the brightest hour ahead, the moon at the darkest
        sums = [sum(light) for light in lights]
        emblems: List[float] = []   # the hours they stand at, which no numeral is written over
        noon = self._middle_of(sums, max(sums))
        if _brightness(lights[int(noon / MAX_REST_HOURS * RING_SEGMENTS) % RING_SEGMENTS]) > 0.6:
            emblems.append(noon)
            self._sun(big, at(noon, mid), 17 * k)
        midnight = self._middle_of(sums, min(sums))
        darkest = lights[int(midnight / MAX_REST_HOURS * RING_SEGMENTS) % RING_SEGMENTS]
        if _brightness(darkest) < 0.3:
            emblems.append(midnight)
            self._moon(big, at(midnight, mid), 15 * k, _ring_colour(darkest))
        numeral_font = _font("Medici Text.ttf", 25 * k)

        # Quarter-hour ticks on the inner edge, and the clock's hours, each where it falls
        first_quarter = first_step(self.now - datetime.timedelta(seconds=1))
        quarter = datetime.timedelta(minutes=REST_STEP_MINUTES)
        moment = first_quarter
        while moment < self.now + datetime.timedelta(hours=MAX_REST_HOURS):
            hours = (moment - self.now).total_seconds() / 3600.0
            bright = _brightness(light_at(hours)) > 0.5
            ink = NUMERAL_DARK if bright else TEXT_SOFT
            if moment.minute == 0:
                if all(abs(hours - e) > 0.8 for e in emblems):
                    text = numeral_font.render(str(moment.hour), True, ink)
                    big.blit(text, text.get_rect(center=at(hours, mid)))
                length = 7 * k
            else:
                length = 3 * k
            pygame.draw.line(big, ink, at(hours, inner + 2 * k), at(hours, inner + 2 * k + length),
                             max(1, k if moment.minute else 2 * k))
            moment += quarter

        # The inner rim and the slate, a little uneven, darker towards its edge
        pygame.draw.circle(big, RIM_DARK, c, inner)
        pygame.draw.circle(big, RIM_SILVER, c, inner - 2 * k)
        slate = SLATE_RADIUS * k
        pygame.draw.circle(big, RIM_DARK, c, slate + 3 * k)
        pygame.draw.circle(big, SLATE, c, slate)
        grain = random.Random(7)
        for _ in range(2600):
            r = slate * math.sqrt(grain.random())
            a = grain.uniform(0, 2 * math.pi)
            shade = grain.randint(-18, 16)
            colour = tuple(max(0, min(255, v + shade)) for v in SLATE)
            pygame.draw.circle(big, colour, (c[0] + r * math.cos(a), c[1] + r * math.sin(a)),
                               grain.uniform(0.6, 2.2) * k)
        for step in range(14):
            shadow = pygame.Surface(big.get_size(), pygame.SRCALPHA)
            pygame.draw.circle(shadow, (0, 0, 0, 9), c, slate - step * 2 * k, 2 * k)
            big.blit(shadow, (0, 0))
        return pygame.transform.smoothscale(big, (size, size))

    @staticmethod
    def _middle_of(sums: List[int], extreme: int) -> float:
        """The hours on to the middle of the longest stretch of the ring as light (or dark) as
        `extreme`, kept an hour from the top so it does not cover the mark of now."""
        near = [abs(value - extreme) <= 6 for value in sums]
        best_start, best_len, start = 0, 0, None
        for i, flag in enumerate(near + [False]):
            if flag and start is None:
                start = i
            elif not flag and start is not None:
                if i - start > best_len:
                    best_start, best_len = start, i - start
                start = None
        segment = MAX_REST_HOURS / RING_SEGMENTS
        hours = (best_start + best_len / 2) * segment
        return min(MAX_REST_HOURS - 1.0, max(1.0, hours))

    @staticmethod
    def _sparkle(surf: pygame.Surface, centre: Tuple[float, float], size: float, colour) -> None:
        """A four-pointed star."""
        x, y = centre
        thin = size * 0.22
        pygame.draw.polygon(surf, colour, [(x, y - size), (x + thin, y - thin), (x + size, y), (x + thin, y + thin),
                                           (x, y + size), (x - thin, y + thin), (x - size, y), (x - thin, y - thin)])

    @staticmethod
    def _sun(surf: pygame.Surface, centre: Tuple[float, float], radius: float) -> None:
        x, y = centre
        for i in range(12):
            a = i * math.pi / 6
            long = radius * (1.75 if i % 2 == 0 else 1.45)
            side = a + math.pi / 2
            base = radius * 0.28
            pygame.draw.polygon(surf, GOLD, [
                (x + long * math.cos(a), y + long * math.sin(a)),
                (x + radius * math.cos(a) + base * math.cos(side), y + radius * math.sin(a) + base * math.sin(side)),
                (x + radius * math.cos(a) - base * math.cos(side), y + radius * math.sin(a) - base * math.sin(side))])
        pygame.draw.circle(surf, GOLD_DARK, centre, radius + 2)
        pygame.draw.circle(surf, GOLD, centre, radius)
        pygame.draw.circle(surf, GOLD_LIGHT, (x - radius * 0.25, y - radius * 0.25), radius * 0.45)

    @staticmethod
    def _moon(surf: pygame.Surface, centre: Tuple[float, float], radius: float, sky) -> None:
        x, y = centre
        pygame.draw.circle(surf, (236, 230, 200), centre, radius)
        pygame.draw.circle(surf, sky, (x + radius * 0.45, y - radius * 0.2), radius * 0.85)

    # -- drawing ---------------------------------------------------------------

    def _draw_hand(self, surf: pygame.Surface, off: Tuple[int, int]) -> None:
        """The gold arc from the top round to the hand, the mark at the top and the hand with its knob."""
        hours = self.hours_ahead
        turned = self.hours_turned
        ox, oy = off
        # The gold of the rest still to come, from where the clock has turned to round to the hand
        band_out, band_in = DIAL_RADIUS - 2, DIAL_RADIUS - 11
        left = hours - turned
        steps = max(2, int(left / MAX_REST_HOURS * 180))
        outer = [self.point_at(turned + left * i / steps, band_out) for i in range(steps + 1)]
        inner = [self.point_at(turned + left * i / steps, band_in) for i in range(steps + 1)]
        band = [(x + ox, y + oy) for x, y in outer + inner[::-1]]
        if left > 0.01 and len(band) >= 3:
            pygame.draw.polygon(surf, GOLD, band)
            pygame.draw.aalines(surf, GOLD_DARK, True, band)
        # The mark of now, at the top
        top_out, top_in = self.point_at(0, DIAL_RADIUS + 6), self.point_at(0, DIAL_RADIUS - RING_WIDTH)
        pygame.draw.line(surf, GOLD_DARK, (top_out[0] + ox, top_out[1] + oy), (top_in[0] + ox, top_in[1] + oy), 4)
        pygame.draw.line(surf, GOLD_LIGHT, (top_out[0] + ox, top_out[1] + oy), (top_in[0] + ox, top_in[1] + oy), 2)
        # The hand: a gold needle across the ring, its knob on the outer rim
        tip, foot = self.point_at(hours, DIAL_RADIUS + 4), self.point_at(hours, DIAL_RADIUS - RING_WIDTH + 2)
        pygame.draw.line(surf, GOLD_DARK, (tip[0] + ox, tip[1] + oy), (foot[0] + ox, foot[1] + oy), 6)
        pygame.draw.line(surf, GOLD, (tip[0] + ox, tip[1] + oy), (foot[0] + ox, foot[1] + oy), 3)
        knob = (round(tip[0] + ox), round(tip[1] + oy))
        hovered = (not self.turning
                   and math.hypot(pygame.mouse.get_pos()[0] - tip[0], pygame.mouse.get_pos()[1] - tip[1]) < 16)
        radius = 12 if (hovered or self.dragging) else 10
        pygame.gfxdraw.filled_circle(surf, *knob, radius + 2, GOLD_DARK)
        pygame.gfxdraw.aacircle(surf, *knob, radius + 2, GOLD_DARK)
        pygame.gfxdraw.filled_circle(surf, *knob, radius, GOLD)
        pygame.gfxdraw.aacircle(surf, *knob, radius, GOLD)
        pygame.gfxdraw.filled_circle(surf, knob[0] - 3, knob[1] - 3, max(2, radius // 3), GOLD_LIGHT)
        if self.turning:
            self._draw_turning_hand(surf, off, turned)

    def _draw_turning_hand(self, surf: pygame.Surface, off: Tuple[int, int], turned: float) -> None:
        """The clock's own hand while it turns: a silver needle from the slate across the ring."""
        ox, oy = off
        tip, foot = self.point_at(turned, DIAL_RADIUS + 10), self.point_at(turned, SLATE_RADIUS - 4)
        tip, foot = (tip[0] + ox, tip[1] + oy), (foot[0] + ox, foot[1] + oy)
        pygame.draw.line(surf, RIM_DARK, foot, tip, 7)
        pygame.draw.line(surf, HAND_SILVER, foot, tip, 3)
        knob = (round(foot[0]), round(foot[1]))
        pygame.gfxdraw.filled_circle(surf, *knob, 7, RIM_DARK)
        pygame.gfxdraw.aacircle(surf, *knob, 7, RIM_DARK)
        pygame.gfxdraw.filled_circle(surf, *knob, 5, HAND_SILVER)
        pygame.gfxdraw.aacircle(surf, *knob, 5, HAND_SILVER)

    def _draw_slate_text(self, surf: pygame.Surface, off: Tuple[int, int]) -> None:
        cx, cy = self.centre[0] + off[0], self.centre[1] + off[1]
        if self.turning:
            # The hours going by: the clock's time, how long is still to come, and the day
            moment = self.now + datetime.timedelta(hours=self.hours_turned)
            caption = self.caption_font.render("RESTING", True, TEXT_SOFT)
            clock = self.big_font.render(f"{moment:%H:%M}", True, TEXT_PALE)
            to_go = self.caption_font.render(f"{describe_hours(self.end - moment)} to go", True, TEXT_PALE)
            day = self.small_font.render(format_long(moment), True, TEXT_SOFT)
            surf.blit(caption, caption.get_rect(center=(cx, cy - 66)))
            surf.blit(clock, clock.get_rect(center=(cx, cy - 12)))
            surf.blit(to_go, to_go.get_rect(center=(cx, cy + 36)))
            surf.blit(day, day.get_rect(center=(cx, cy + 62)))
            return
        until_sunrise = self.end == self.sunrise
        caption = self.caption_font.render("REST UNTIL SUNRISE" if until_sunrise else "REST FOR", True, TEXT_SOFT)
        span = self.big_font.render(describe_hours(self.end - self.now), True, TEXT_PALE)
        day = self.small_font.render(format_long(self.end), True, TEXT_SOFT)
        clock = self.caption_font.render(f"until {self.end:%H:%M}", True, TEXT_PALE)
        surf.blit(caption, caption.get_rect(center=(cx, cy - 66)))
        surf.blit(span, span.get_rect(center=(cx, cy - 12)))
        surf.blit(clock, clock.get_rect(center=(cx, cy + 36)))
        surf.blit(day, day.get_rect(center=(cx, cy + 62)))

    def _draw_tiredness(self, surf: pygame.Surface, off: Tuple[int, int]) -> None:
        """The tiredness now and after the rest, as two bars."""
        player = self.game_state.game.player
        # While the clock turns, the bar empties with the hours passed
        now = tiredness_after_rest(player.tiredness, self.hours_turned)
        after = tiredness_after_rest(player.tiredness, self.hours_ahead)
        y = self.centre[1] + DIAL_RADIUS + 26 + off[1]
        label = self.small_font.render("Tiredness", True, DARK_BROWN)
        bar_w, bar_h = 260, 14
        left = self.panel.centerx + off[0] - (label.get_width() + 14 + bar_w + 70) // 2
        surf.blit(label, label.get_rect(midleft=(left, y + bar_h // 2)))
        bar = pygame.Rect(left + label.get_width() + 14, y, bar_w, bar_h)
        draw_tiredness_bar(surf, bar, now, after)
        text = self.small_font.render(f"{now * 100:.0f} % > {after * 100:.0f} %", True, BLACK)
        surf.blit(text, text.get_rect(midleft=(bar.right + 10, bar.centery)))

    def draw(self, alpha_scale: float = 1.0) -> None:
        if alpha_scale <= 0:
            return
        use_temp = alpha_scale < 1.0
        if use_temp:
            surf = pygame.Surface(self.panel.size, pygame.SRCALPHA)
            off = (-self.panel.left, -self.panel.top)
        else:
            surf = self.screen
            off = (0, 0)
            self._draw_veil()

        self._draw_panel(surf, off)
        self._draw_close_btn(surf, off)
        self._draw_title(surf, off, "Rest a While")
        surf.blit(self.dial, self.dial.get_rect(center=(self.centre[0] + off[0], self.centre[1] + off[1])))
        self._draw_hand(surf, off)
        self._draw_slate_text(surf, off)
        self._draw_tiredness(surf, off)
        mouse_pos = pygame.mouse.get_pos() if not use_temp and not self.turning else (-1, -1)
        for key, rect in self.buttons.items():
            self._draw_btn(surf, rect.move(*off), self.labels[key], mouse_pos, active=False)
        hint_text = ("Click or press a key to wake at once." if self.turning
                     else "Drag the hand or turn the wheel; Enter rests.")
        hint = self.small_font.render(hint_text, True, (90, 70, 50))
        surf.blit(hint, hint.get_rect(centerx=self.panel.centerx + off[0], bottom=self.buttons["rest"].top + off[1] - 6))

        if use_temp:
            surf.set_alpha(int(255 * alpha_scale))
            self.screen.blit(surf, self.panel.topleft)


#: The bar's colours: the frame, its empty part, and the fill from a little tired to worn out
BAR_FRAME = DARK_BROWN
BAR_EMPTY = (226, 212, 180)
BAR_LOW = (196, 164, 84)
BAR_HIGH = (150, 42, 30)


def tiredness_colour(tiredness: float) -> Tuple[int, int, int]:
    return _mix(BAR_LOW, BAR_HIGH, tiredness)


def draw_tiredness_bar(surf: pygame.Surface, rect: pygame.Rect, tiredness: float,
                       after: Optional[float] = None) -> None:
    """A bar filled as far as the tiredness; with `after`, the part a rest takes away is drawn pale."""
    pygame.draw.rect(surf, BAR_EMPTY, rect, border_radius=3)
    inner = rect.inflate(-4, -4)
    filled = inner.copy()
    filled.width = round(inner.width * min(1.0, max(0.0, tiredness)))
    if filled.width > 0:
        pygame.draw.rect(surf, tiredness_colour(tiredness), filled, border_radius=2)
    if after is not None and after < tiredness:
        kept = inner.copy()
        kept.width = round(inner.width * after)
        gone = pygame.Rect(inner.left + kept.width, inner.top, filled.width - kept.width, inner.height)
        pale = pygame.Surface(gone.size, pygame.SRCALPHA)
        pale.fill((255, 250, 235, 150))
        surf.blit(pale, gone)
    pygame.draw.rect(surf, BAR_FRAME, rect, 2, border_radius=3)
