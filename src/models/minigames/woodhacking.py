"""Woodhacking minigame — a double-gauge (aim + power) mini-game for early income.

Two independent mechanics must be juggled at the same time:

  1. AIM needle — oscillates left and right across a semicircular gauge.
                  The green zone at the bottom is where you want it. Holding
                  the mouse button speeds it up, so charging power makes aim
                  harder to hold.

  2. POWER bar  — fills while the mouse button is held. The green band is
                  the sweet spot; too weak or too strong both cost points,
                  and the far top/bottom of the bar is an outright miss.

Hold the left mouse button to charge power, release to swing. Both gauges
are graded independently at the moment of release, and the payout (booked
straight to the player's cash via ``Depot.book_labor_income``) follows a
steep curve that rewards near-perfect play far more than mediocre play.

The gauges are part of the chopping scene (``ChoppingScene`` in
``woodhacking_scene.py``): power is a gauge post at its left, the aim a plumb
bob swinging over a scale board that hangs from a beam above the log, its
sweet spot right over where the blade comes down. The player swings an axe
at the log: lifted while power gathers, and by the grade a clean
split, a bite that cracks the log, a swish past it or a swing that falls
short. Splits in a row make a streak: each one adds ``STREAK_BONUS`` (5%) to
the next swing's points, so the third split in a row scores 10% more and so
on, until a swing fails to split its log and the streak starts again from
nothing. A new swing can be gathered once the last one has landed, and the
result shows once the last swing's chips have settled.
"""

import os
import math
import random
from typing import Optional, Tuple

import pygame

from .base import MinigameOverlay, score_to_coins, score_to_display
from .woodhacking_scene import (
    ChoppingScene, SPLIT, BITE, WHIFF, SHORT, SCENE_W, SCENE_H, POWER_RECT, AIM_PIVOT, AIM_RADIUS,
)
from ...config.colors import (
    BEIGE, SANDY_BROWN, PALE_BROWN, DARK_BROWN,
    MUTED_GREEN as GREEN, MUTED_DARK_GREEN as DARK_GREEN,
    MUTED_RED as RED, MUTED_DARK_RED as DARK_RED,
    MUTED_YELLOW as YELLOW, MUTED_ORANGE as ORANGE,
    WHITE, BLACK, GOLD,
)
from ...config.constants import SCREEN_WIDTH, SCREEN_HEIGHT, SIDEBAR_WIDTH, FONTS_PATH
from ...ui.transaction_feedback import on_money_received

_TOTAL_W = SCREEN_WIDTH + SIDEBAR_WIDTH

# The minigame is drawn onto a fixed-size canvas and centered on screen —
# keeps all gauge geometry below in simple, self-contained pixel coordinates.
# The chopping scene fills it between the title and the status bar; the
# gauges are drawn into the scene, in its pixels.
_TOP_BAR, _BOTTOM_BAR, _MARGIN = 44, 46, 6
_CANVAS_W = SCENE_W + 2 * _MARGIN
_CANVAS_H = _TOP_BAR + SCENE_H + 2 * _MARGIN + _BOTTOM_BAR
_CX = _CANVAS_W // 2
_SCENE_RECT = pygame.Rect(_MARGIN, _TOP_BAR + _MARGIN, SCENE_W, SCENE_H)
_RESULT_DELAY_S = 0.4      # after the last swing has settled, before the result shows
_THUD_VOLUME = 0.3         # a new log dropping onto the block

MINIGAME_NAME = "Woodhacking"

# ── gauge constants ─────────────────────────────────────────────────────────
_AIM_CX, _AIM_CY = AIM_PIVOT       # in the scene: the plumb line's pivot under the beam
_AIM_R = AIM_RADIUS

# Left-side zone boundaries (negative angles, more forgiving)
# PERFECT is the tight inner sliver; VERY GOOD covers the rest of what used
# to be a single (too generous) PERFECT zone — same points and color as
# PERFECT, just a distinct label so "PERFECT" reads as genuinely rare.
_AIM_PERFECT_L = math.radians(3.5)
_AIM_VERYGOOD_L = math.radians(7)
_AIM_GOOD_L = math.radians(18)
_AIM_OK_L = math.radians(52)

# Right-side zone boundaries (positive angles, tighter green zones)
_AIM_PERFECT_R = math.radians(2)
_AIM_VERYGOOD_R = math.radians(4)
_AIM_GOOD_R = math.radians(10)
_AIM_OK_R = math.radians(40)

_AIM_MAX = math.radians(84)
_AIM_MISS_MARGIN = math.radians(14)  # last stretch before AIM_MAX is dark red — an outright miss

_BASE_AIM_SPEED = math.radians(58)  # radians / second when idle
_CHARGE_SPEED_K = 1.8  # aim speed multiplier per full-power unit

_POWER_RECT = POWER_RECT           # in the scene: the channel in the gauge post
_OPT_WIDTH = 0.14  # green zone width (perfect power should be rare)
_OPT_CENTER_0 = 0.64  # starting center (gives lo=0.57, hi=0.71)
_POWER_RATE = 0.72  # fills from 0->1 in ~1.4 seconds

_YELLOW_MARGIN = 0.12  # yellow band width either side of green
_RED_MARGIN = 0.12  # red band width beyond the yellow band
_MISS_EDGE = 0.06  # dark red always reaches this close to 0/1, whatever the zone
# The very top and bottom of the power bar (within MISS_EDGE) are always dark
# red, no matter where the green zone sits, so a bare tip of the mouse or
# holding all the way to full power is always a miss.

_SPEED_BONUS_PER_HIT = math.radians(6)  # added to base needle speed each good/perfect
_MAX_SPEED_BONUS = _BASE_AIM_SPEED * 2.0

# The look shared by both gauges: dark wood, brass fittings, inked text
_WOOD, _WOOD_DARK, _WOOD_LIGHT = (122, 86, 54), (86, 58, 36), (150, 112, 72)
_BRASS, _BRASS_LIGHT, _BRASS_DARK = (196, 154, 64), (236, 204, 120), (120, 86, 30)
_IRON = (64, 62, 60)
_INK = (44, 32, 22)
_CORD = (70, 56, 40)
_PAPER = (236, 222, 186)

STREAK_BONUS = 0.05        # extra points on a swing for each split in a row before it

MAX_SWINGS = 30
MAX_SCORE = MAX_SWINGS * 5


def swing_outcome(points: int, power: float, opt_lo: float) -> str:
    """What the axe does: a good swing splits the log, a fair one bites into it,
    one that scores nothing falls short (too little power) or swishes past."""
    if points >= 3:
        return SPLIT
    if points > 0:
        return BITE
    return SHORT if power < opt_lo else WHIFF


def _power_zone_bounds(opt_lo: float, opt_hi: float) -> Tuple[float, float, float, float]:
    """Yellow and red band edges around the green sweet spot.

    Shared by drawing and scoring so the visible zones and the scored
    zones never drift apart.
    """
    ylo = max(0.0, opt_lo - _YELLOW_MARGIN)
    yhi = min(1.0, opt_hi + _YELLOW_MARGIN)
    rlo = max(_MISS_EDGE, opt_lo - _YELLOW_MARGIN - _RED_MARGIN)
    rhi = min(1.0 - _MISS_EDGE, opt_hi + _YELLOW_MARGIN + _RED_MARGIN)
    # Keep bands monotonic (dark red <= red <= yellow <= green) even when the
    # green zone sits close enough to an edge to compress the red band.
    ylo = max(ylo, rlo)
    yhi = min(yhi, rhi)
    return ylo, yhi, rlo, rhi


def _new_opt_zone() -> Tuple[float, float]:
    center = random.uniform(0.22, 0.78)
    return center - _OPT_WIDTH / 2, center + _OPT_WIDTH / 2


def _arc_pts(cx: int, cy: int, r: int, a0: float, a1: float, steps: int = 48):
    """Arc points where angle 0 = bottom, +angle = right (U-shape opening up)."""
    pts = []
    for i in range(steps + 1):
        t = a0 + (a1 - a0) * i / steps
        pts.append((cx + r * math.sin(t), cy + r * math.cos(t)))
    return pts


def _arc_ring_poly(cx: int, cy: int, r: float, width: float, a0: float, a1: float, steps: int = 48):
    """Vertices of a filled ring segment (a thick arc band with smooth edges).

    Drawing thick arcs with ``pygame.draw.lines`` butt-joins each straight
    segment, which leaves visible notches/gaps along the outer curve. A
    filled polygon between an inner and outer arc renders as one smooth
    band instead.
    """
    outer = r + width / 2
    inner = r - width / 2
    steps = max(steps, int(abs(a1 - a0) / math.radians(2)) + 1)
    top = [(cx + outer * math.sin(a0 + (a1 - a0) * i / steps),
            cy + outer * math.cos(a0 + (a1 - a0) * i / steps)) for i in range(steps + 1)]
    bottom = [(cx + inner * math.sin(a0 + (a1 - a0) * i / steps),
               cy + inner * math.cos(a0 + (a1 - a0) * i / steps)) for i in range(steps + 1)]
    return top + bottom[::-1]


def _grade_aim(aim: float) -> Tuple[int, str, tuple, bool]:
    """Aim: 0-3 points — right side uses tighter thresholds.

    The far edge of travel (within AIM_MISS_MARGIN of AIM_MAX) is dark red —
    a hard miss (last element True), no matter how good the power was.
    """
    if aim < 0:
        perfect, very_good, good, fair = _AIM_PERFECT_L, _AIM_VERYGOOD_L, _AIM_GOOD_L, _AIM_OK_L
    else:
        perfect, very_good, good, fair = _AIM_PERFECT_R, _AIM_VERYGOOD_R, _AIM_GOOD_R, _AIM_OK_R
    a = abs(aim)
    if a >= _AIM_MAX - _AIM_MISS_MARGIN:
        return 0, "MISS", DARK_RED, True
    if a < perfect:
        return 3, "PERFECT", DARK_GREEN, False
    if a < very_good:
        return 3, "VERY GOOD", DARK_GREEN, False
    if a < good:
        return 2, "GOOD", GREEN, False
    if a < fair:
        return 1, "FAIR", YELLOW, False
    return 0, "MISS", RED, False


def _grade_power(power: float, opt_lo: float, opt_hi: float) -> Tuple[int, str, tuple, bool]:
    """Power: 0-2 points (uses the current dynamic zone).

    The green sweet spot is split into an inner PERFECT sliver and an outer
    VERY GOOD band (same points/color as PERFECT, just a distinct label —
    mirrors the aim gauge's PERFECT/VERY GOOD split) so PERFECT reads as
    genuinely rare. Landing in the dark-red zone is a hard miss (last
    element True) — too weak or too strong to count no matter how good the
    aim was.
    """
    ylo, yhi, rlo, rhi = _power_zone_bounds(opt_lo, opt_hi)
    green_span = opt_hi - opt_lo
    perfect_lo = opt_lo + green_span * 0.25
    perfect_hi = opt_hi - green_span * 0.25
    if power < rlo or power > rhi:
        return 0, "MISS", DARK_RED, True
    if perfect_lo <= power <= perfect_hi:
        return 2, "PERFECT", DARK_GREEN, False
    if opt_lo <= power <= opt_hi:
        return 2, "VERY GOOD", DARK_GREEN, False
    if ylo <= power < opt_lo or opt_hi < power <= yhi:
        return 1, "GOOD", YELLOW, False
    return 0, "WEAK", RED, False


class WoodhackingMinigame(MinigameOverlay):
    """Full-screen overlay for the woodhacking double-gauge minigame.

    Follows the same lifecycle as ``ContractView``/``game_state.contract_acquisition``:
    the launcher pauses the sim and assigns the instance to ``game_state.minigame``;
    ``Game.run()`` calls ``update``/``draw`` each frame while ``self.active`` is
    True; ``EventHandler`` routes all input to ``handle_event`` exclusively.
    """

    def __init__(self, screen: pygame.Surface, game) -> None:
        self.screen = screen
        self.game = game
        self.active = True

        self.canvas = pygame.Surface((_CANVAS_W, _CANVAS_H))
        self.canvas_rect = self.canvas.get_rect(
            center=(_TOTAL_W // 2, SCREEN_HEIGHT // 2)
        )

        try:
            self.font = pygame.font.Font(os.path.join(FONTS_PATH, "RomanAntique.ttf"), 18)
            self.font_small = pygame.font.Font(os.path.join(FONTS_PATH, "RomanAntique.ttf"), 15)
            self.font_grade = pygame.font.Font(os.path.join(FONTS_PATH, "RomanAntique.ttf"), 26)
            self.font_large = pygame.font.Font(os.path.join(FONTS_PATH, "Medici Text.ttf"), 28)
            self.font_hit = pygame.font.Font(os.path.join(FONTS_PATH, "RomanAntique.ttf"), 34)
        except Exception:
            self.font = pygame.font.SysFont("georgia", 18)
            self.font_small = pygame.font.SysFont("georgia", 15)
            self.font_grade = pygame.font.SysFont("georgia", 26, bold=True)
            self.font_large = pygame.font.SysFont("georgia", 28, bold=True)
            self.font_hit = pygame.font.SysFont("georgia", 34, bold=True)

        self.scene = ChoppingScene(self.font_hit)
        self.close_rect = pygame.Rect(0, 0, 160, 44)
        self.congrats_close_rect = pygame.Rect(0, 0, 160, 44)
        self._payout_booked = False
        self._reset_round()

    # ------------------------------------------------------------------
    # Round state
    # ------------------------------------------------------------------

    def _reset_round(self) -> None:
        lo = _OPT_CENTER_0 - _OPT_WIDTH / 2
        hi = _OPT_CENTER_0 + _OPT_WIDTH / 2
        self.aim = 0.0
        self.aim_dir = 1
        self.aim_speed_bonus = 0.0
        self.power = 0.0
        self.opt_lo = lo
        self.opt_hi = hi
        self.charging = False
        self.score = 0.0
        self.attempt = 0
        self.streak = 0            # logs split in a row
        self.best_streak = 0
        self.last_gain = 0.0       # points the last swing earned, its streak bonus included
        self._streak_lost_alpha = 0
        self.done = False
        self._ending = False       # all swings made, waiting for the last to settle
        self._end_timer = 0.0
        self.aim_hit_text = ""
        self.aim_hit_color = WHITE
        self.pow_hit_text = ""
        self.pow_hit_color = WHITE
        self.hit_alpha = 0
        self._payout_booked = False
        self.highscore = self.game.depot.stats.woodhacking_highscore
        self.new_highscore = False
        self._show_congrats = False

    def _to_canvas(self, pos: Tuple[int, int]) -> Tuple[int, int]:
        return (pos[0] - self.canvas_rect.left, pos[1] - self.canvas_rect.top)

    # ------------------------------------------------------------------
    # Payout
    # ------------------------------------------------------------------

    def _book_payout(self) -> None:
        if self._payout_booked:
            return
        self._payout_booked = True
        coins = score_to_coins(self.score, MAX_SCORE)
        depot = self.game.depot
        state = self.game.state

        # A completed session (all swings played, result screen shown) always
        # counts as "played" and can set a new highscore, even if the round
        # itself scored no payout.
        depot.stats.minigames_played += 1
        if self.score > depot.stats.woodhacking_highscore:
            depot.stats.woodhacking_highscore = self.score
            self.new_highscore = True
            self._show_congrats = True
        self.highscore = depot.stats.woodhacking_highscore

        if coins <= 0:
            return
        depot.book_labor_income(coins, MINIGAME_NAME)
        depot.stats.minigame_income_total += coins
        on_money_received(state, coins)
        state.log_event("FINANCE", f"Earned {coins:.2f}g woodhacking")

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.active = False
                return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.done:
                if self._show_congrats:
                    if self.congrats_close_rect.collidepoint(self._to_canvas(event.pos)):
                        self._show_congrats = False
                    return
                if self.close_rect.collidepoint(self._to_canvas(event.pos)):
                    self.active = False
                return
            if not self.charging and not self._ending and self.scene.can_charge:
                self.charging = True

        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self.charging and not self.done:
                self.charging = False
                self._resolve_swing()

    def _play_scene_sounds(self, kinds) -> None:
        """Play what the scene asks for: "chop" as the axe bites, "swoosh" as it
        swings past or short, "thud" (a soft chop) as a new log lands."""
        for kind in kinds:
            prefix = "swoosh_" if kind == "swoosh" else "chop_"
            candidates = [name for name in self.game.sounds if name.startswith(prefix)]
            if not candidates:
                continue
            channel = self.game.play_sound(random.choice(candidates))
            if kind == "thud" and channel is not None:
                channel.set_volume(_THUD_VOLUME)

    def _resolve_swing(self) -> None:
        self.attempt += 1
        aim_pts, aim_label, aim_color, aim_miss = _grade_aim(self.aim)
        pow_pts, pow_label, pow_color, pow_miss = _grade_power(
            self.power, self.opt_lo, self.opt_hi
        )
        pts = 0 if (aim_miss or pow_miss) else aim_pts + pow_pts
        bonus = self.streak_bonus
        self.last_gain = round(pts * (1.0 + bonus), 2)
        self.score = round(self.score + self.last_gain, 2)
        self.aim_hit_text, self.aim_hit_color = aim_label, aim_color
        self.pow_hit_text, self.pow_hit_color = pow_label, pow_color
        self.hit_alpha = 255
        outcome = swing_outcome(pts, self.power, self.opt_lo)
        popup_color = DARK_GREEN if pts >= 4 else (GREEN if pts >= 3 else (ORANGE if pts > 0 else DARK_RED))
        label = f"+{self.last_gain:g}" if pts > 0 else "miss"
        if pts > 0 and bonus > 0:
            label += f"  (+{round(bonus * 100)}%)"
        self._play_scene_sounds(self.scene.swing(outcome, pts, popup_color, label=label))
        # The scene has the last word on what happened to the log (a second bite splits it)
        if self.scene.outcome == SPLIT:
            self.streak += 1
            self.best_streak = max(self.best_streak, self.streak)
        else:
            if self.streak > 0:
                self._streak_lost_alpha = 255
            self.streak = 0
        self.power = 0.0
        if pts >= 3:
            self.aim_speed_bonus = min(
                self.aim_speed_bonus + _SPEED_BONUS_PER_HIT, _MAX_SPEED_BONUS
            )
            self.opt_lo, self.opt_hi = _new_opt_zone()
        if self.attempt >= MAX_SWINGS:
            self._ending = True

    @property
    def streak_bonus(self) -> float:
        """The share of extra points the next swing earns for the splits in a row before it."""
        return self.streak * STREAK_BONUS

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(self, delta_time: float) -> None:
        if not self.done:
            spd = (_BASE_AIM_SPEED + self.aim_speed_bonus) * (1.0 + self.power * _CHARGE_SPEED_K)
            self.aim += self.aim_dir * spd * delta_time
            if abs(self.aim) >= _AIM_MAX:
                self.aim_dir *= -1
                self.aim = math.copysign(_AIM_MAX, self.aim)

            if self.charging:
                self.power = min(1.0, self.power + _POWER_RATE * delta_time)
                self.scene.charge(self.power)

        self._play_scene_sounds(self.scene.update(delta_time))
        if self._ending and not self.done and self.scene.settled:
            self._end_timer += delta_time
            if self._end_timer >= _RESULT_DELAY_S:
                self.done = True
                self._book_payout()

        if self.hit_alpha > 0:
            self.hit_alpha = max(0, self.hit_alpha - 6)
        if self._streak_lost_alpha > 0:
            self._streak_lost_alpha = max(0, self._streak_lost_alpha - 4)

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _draw_gauges(self, surf: pygame.Surface) -> None:
        self._draw_power_bar(surf)
        self._draw_aim_gauge(surf)

    def _draw_aim_gauge(self, surf: pygame.Surface) -> None:
        """The zones painted on the scale board, and the plumb bob swinging over them."""
        cx, cy, r = _AIM_CX, _AIM_CY, _AIM_R
        dark_lo = _AIM_MAX - _AIM_MISS_MARGIN
        zones = [
            (-_AIM_MAX, -dark_lo, DARK_RED), (dark_lo, _AIM_MAX, DARK_RED),
            (-dark_lo, -_AIM_OK_L, RED), (_AIM_OK_R, dark_lo, RED),
            (-_AIM_OK_L, -_AIM_GOOD_L, YELLOW), (_AIM_GOOD_R, _AIM_OK_R, YELLOW),
            (-_AIM_GOOD_L, -_AIM_VERYGOOD_L, GREEN), (_AIM_VERYGOOD_R, _AIM_GOOD_R, GREEN),
            (-_AIM_VERYGOOD_L, _AIM_VERYGOOD_R, DARK_GREEN),
        ]
        for a0, a1, col in zones:
            if a1 > a0:
                pygame.draw.polygon(surf, col, _arc_ring_poly(cx, cy, r, 18, a0, a1))
        pygame.draw.polygon(surf, _INK, _arc_ring_poly(cx, cy, r, 18, -_AIM_MAX, _AIM_MAX), 2)
        # Ticks cut into the board's outer edge every 10 degrees, the centre one long
        for deg in range(-80, 81, 10):
            a = math.radians(deg)
            r0 = r + 12 if deg else r + 4
            pygame.draw.line(surf, _INK, (cx + r0 * math.sin(a), cy + r0 * math.cos(a)),
                             (cx + (r + 16) * math.sin(a), cy + (r + 16) * math.cos(a)), 2 if deg == 0 else 1)
        self._plaque(surf, "AIM", (cx - 96, cy - 9))

        # The cord and the brass bob at its end, pointing along it
        a = self.aim
        along = pygame.Vector2(math.sin(a), math.cos(a))
        side = pygame.Vector2(along.y, -along.x)
        pivot = pygame.Vector2(cx, cy)
        bob = pivot + along * (r - 4)
        pygame.draw.line(surf, _CORD, pivot, bob - along * 13, 2)
        tip = bob + along * 19
        body = [bob - along * 13 + side * 4, bob + side * 11, tip, bob - side * 11, bob - along * 13 - side * 4]
        pygame.draw.polygon(surf, _BRASS, body)
        pygame.draw.line(surf, _BRASS_LIGHT, bob - along * 8 + side * 3, tip - along * 4 + side * 1, 2)
        pygame.draw.polygon(surf, _INK, body, 2)
        pygame.draw.circle(surf, _IRON, pivot, 4)

    def _draw_power_bar(self, surf: pygame.Surface) -> None:
        """The gauge post: the zones inlaid in its channel, the power rising in it,
        and a brass pointer on its side at the level."""
        r = _POWER_RECT
        ground = SCENE_H - 70
        # The post, pointed at the top, planted in the ground
        post = pygame.Rect(r.left - 16, r.top - 36, r.width + 32, ground - r.top + 36)
        shadow = pygame.Surface((post.width + 30, 14), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, 60), shadow.get_rect())
        surf.blit(shadow, (post.left - 6, ground - 6))
        top = [(post.left, post.top + 14), (post.centerx, post.top - 4), (post.right, post.top + 14),
               (post.right, post.bottom), (post.left, post.bottom)]
        pygame.draw.polygon(surf, _WOOD, top)
        for i, x in enumerate(range(post.left + 5, post.right - 3, 9)):
            pygame.draw.line(surf, _WOOD_DARK, (x, post.top + 16 + 30 * (i % 2)), (x, post.bottom - 10 - 40 * (i % 3)), 1)
        pygame.draw.line(surf, _WOOD_LIGHT, (post.left + 2, post.top + 15), (post.left + 2, post.bottom - 2), 2)
        pygame.draw.polygon(surf, _INK, top, 2)
        for y in (r.top - 12, r.bottom + 8):              # iron bands
            band = pygame.Rect(post.left - 2, y, post.width + 4, 7)
            pygame.draw.rect(surf, _IRON, band)
            pygame.draw.rect(surf, _INK, band, 1)
            for x in (band.left + 5, band.right - 5):
                pygame.draw.circle(surf, (120, 116, 110), (x, band.centery), 1)

        # The channel and its zones
        ylo, yhi, rlo, rhi = _power_zone_bounds(self.opt_lo, self.opt_hi)
        zone_defs = [
            (0.0, rlo, DARK_RED), (rlo, ylo, RED), (ylo, self.opt_lo, YELLOW),
            (self.opt_lo, self.opt_hi, DARK_GREEN),
            (self.opt_hi, yhi, YELLOW), (yhi, rhi, RED), (rhi, 1.0, DARK_RED),
        ]
        pygame.draw.rect(surf, _INK, r.inflate(6, 6))
        for lo, hi, col in zone_defs:
            yb = r.bottom - int(lo * r.height)
            yt = r.bottom - int(hi * r.height)
            pygame.draw.rect(surf, col, pygame.Rect(r.left, yt, r.width, yb - yt))
        for i in range(1, 10):                             # notches every tenth
            y = r.bottom - r.height * i // 10
            pygame.draw.line(surf, _INK, (r.left, y), (r.left + (8 if i == 5 else 5), y), 1)
        fill_h = int(self.power * r.height)
        if fill_h > 0:
            sap = pygame.Surface((r.width, fill_h), pygame.SRCALPHA)
            sap.fill((255, 255, 240, 70))
            surf.blit(sap, (r.left, r.bottom - fill_h))

        # The pointer: a brass wedge on the post's side, bright while in the sweet spot
        y = r.bottom - self.power * r.height
        pygame.draw.line(surf, WHITE, (r.left, y), (r.right - 1, y), 2)
        sweet = self.opt_lo <= self.power <= self.opt_hi
        x = post.right + 2
        wedge = [(r.right + 2, y), (x + 14, y - 9), (x + 14, y + 9)]
        pygame.draw.polygon(surf, _BRASS_LIGHT if sweet and self.charging else _BRASS, wedge)
        pygame.draw.polygon(surf, _INK, wedge, 2)
        self._plaque(surf, "POWER", (post.centerx, post.top + 30))

    def _draw_streak(self, surf: pygame.Surface, center: Tuple[int, int]) -> None:
        """The streak under the woodpile's count: how many in a row and what the next swing gains,
        one brass notch per split; and for a moment "Streak lost" when it breaks."""
        if self.streak > 0:
            self._plaque(surf, f"Streak {self.streak}:  next +{round(self.streak_bonus * 100)}%", center)
            notches = min(self.streak, 12)
            x0 = center[0] - (notches - 1) * 6
            for i in range(notches):
                x, y = x0 + i * 12, center[1] + 22
                pygame.draw.polygon(surf, _BRASS_LIGHT, [(x, y - 6), (x + 5, y), (x, y + 6), (x - 5, y)])
                pygame.draw.polygon(surf, _INK, [(x, y - 6), (x + 5, y), (x, y + 6), (x - 5, y)], 1)
        elif self._streak_lost_alpha > 0:
            lost = self._inked("Streak lost", self.font_grade, RED)
            lost.set_alpha(self._streak_lost_alpha)
            surf.blit(lost, lost.get_rect(center=center))

    def _plaque(self, surf: pygame.Surface, text: str, center: Tuple[float, float]) -> None:
        """A small brass plate with engraved text, nailed on."""
        label = self.font_small.render(text, True, _INK)
        rect = label.get_rect(center=center).inflate(14, 6)
        pygame.draw.rect(surf, _BRASS, rect, border_radius=3)
        pygame.draw.line(surf, _BRASS_LIGHT, (rect.left + 3, rect.top + 2), (rect.right - 4, rect.top + 2), 1)
        pygame.draw.rect(surf, _BRASS_DARK, rect, 2, border_radius=3)
        surf.blit(label, label.get_rect(center=rect.center))

    def _inked(self, text: str, font: pygame.font.Font, colour) -> pygame.Surface:
        """Text with a dark rim, so it reads on sky, grass and wood alike."""
        face = font.render(text, True, colour)
        rim = font.render(text, True, _INK)
        out = pygame.Surface((face.get_width() + 2, face.get_height() + 2), pygame.SRCALPHA)
        for dx, dy in ((0, 1), (2, 1), (1, 0), (1, 2)):
            out.blit(rim, (dx, dy))
        out.blit(face, (1, 1))
        return out

    def _draw_scene_overlay(self, surf: pygame.Surface) -> None:
        """Over the scene: the grades of the last swing, the woodpile's count and the hint."""
        if self.hit_alpha > 0:
            aim_txt = self._inked(self.aim_hit_text, self.font_hit, self.aim_hit_color)
            aim_txt.set_alpha(self.hit_alpha)
            surf.blit(aim_txt, aim_txt.get_rect(center=(_AIM_CX, _AIM_CY + 62)))
            pow_txt = self._inked(self.pow_hit_text, self.font_grade, self.pow_hit_color)
            pow_txt.set_alpha(self.hit_alpha)
            surf.blit(pow_txt, pow_txt.get_rect(midleft=(_POWER_RECT.right + 40, _POWER_RECT.bottom - 40)))

        self._plaque(surf, f"Logs split: {self.scene.pile}", (SCENE_W - 90, 26))
        self._draw_streak(surf, (SCENE_W - 90, 56))

        if self.charging:
            hint, colour = "Release to swing!", _INK
        elif self._ending:
            hint, colour = "That was the last swing", PALE_BROWN
        else:
            hint, colour = "Hold the left mouse button to gather power, release to swing", PALE_BROWN
        label = self.font.render(hint, True, colour)
        ribbon = label.get_rect(center=(SCENE_W // 2, SCENE_H - 26)).inflate(28, 10)
        pygame.draw.rect(surf, _PAPER, ribbon, border_radius=4)
        pygame.draw.rect(surf, _WOOD_DARK, ribbon, 2, border_radius=4)
        surf.blit(label, label.get_rect(center=ribbon.center))

    def _draw_status_bar(self, coins: float) -> None:
        pygame.draw.rect(self.canvas, DARK_BROWN, (0, 0, _CANVAS_W, 44))
        pygame.draw.line(self.canvas, SANDY_BROWN, (0, 44), (_CANVAS_W, 44), 1)
        title = self.font.render("WOODHACKING", True, SANDY_BROWN)
        self.canvas.blit(title, title.get_rect(center=(_CANVAS_W // 2, 22)))

        pygame.draw.rect(self.canvas, DARK_BROWN, (0, _CANVAS_H - 46, _CANVAS_W, 46))
        pygame.draw.line(self.canvas, SANDY_BROWN, (0, _CANVAS_H - 46), (_CANVAS_W, _CANVAS_H - 46), 1)

        left = self.font.render(f"Score: {score_to_display(self.score, MAX_SCORE)}", True, SANDY_BROWN)
        self.canvas.blit(left, (20, _CANVAS_H - 32))

        mid = self.font.render(f"Swing  {self.attempt} / {MAX_SWINGS}", True, SANDY_BROWN)
        self.canvas.blit(mid, mid.get_rect(centerx=_CANVAS_W // 2, y=_CANVAS_H - 32))

        right = self.font.render(f"Coins: {coins:.2f}", True, SANDY_BROWN)
        self.canvas.blit(right, right.get_rect(right=_CANVAS_W - 20, y=_CANVAS_H - 32))

    def _draw_result_overlay(self, coins: float) -> None:
        overlay = pygame.Surface((_CANVAS_W, _CANVAS_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        self.canvas.blit(overlay, (0, 0))

        panel = pygame.Rect(_CX - 200, 145, 400, 300)
        pygame.draw.rect(self.canvas, BEIGE, panel, border_radius=8)
        pygame.draw.rect(self.canvas, DARK_BROWN, panel, 3, border_radius=8)

        title = self.font_large.render("Session Complete!", True, DARK_BROWN)
        self.canvas.blit(title, title.get_rect(center=(_CX, 205)))

        score_txt = self.font.render(f"Score:  {score_to_display(self.score, MAX_SCORE)}", True, BLACK)
        self.canvas.blit(score_txt, score_txt.get_rect(center=(_CX, 250)))

        hs_color = GOLD if self.new_highscore else DARK_BROWN
        hs_txt = self.font.render(f"Highscore:  {score_to_display(self.highscore, MAX_SCORE)}", True, hs_color)
        self.canvas.blit(hs_txt, hs_txt.get_rect(center=(_CX, 276)))

        streak_txt = self.font.render(f"Best streak:  {self.best_streak} in a row", True, DARK_BROWN)
        self.canvas.blit(streak_txt, streak_txt.get_rect(center=(_CX, 302)))

        coin_color = DARK_GREEN if coins >= 15 else (ORANGE if coins >= 8 else RED)
        coin_txt = self.font_large.render(f"+{coins:.2f}g earned today", True, coin_color)
        self.canvas.blit(coin_txt, coin_txt.get_rect(center=(_CX, 338)))

        hint = self.font.render("Come back tomorrow for another swing", True, PALE_BROWN)
        self.canvas.blit(hint, hint.get_rect(center=(_CX, 374)))

        self.close_rect.center = (_CX, 413)
        mouse_pos = self._to_canvas(pygame.mouse.get_pos())
        hovered = self.close_rect.collidepoint(mouse_pos)
        pygame.draw.rect(self.canvas, PALE_BROWN if hovered else SANDY_BROWN, self.close_rect, border_radius=4)
        pygame.draw.rect(self.canvas, DARK_BROWN, self.close_rect, 2, border_radius=4)
        close_txt = self.font.render("Close", True, DARK_BROWN)
        self.canvas.blit(close_txt, close_txt.get_rect(center=self.close_rect.center))

    def _draw_congrats_overlay(self) -> None:
        overlay = pygame.Surface((_CANVAS_W, _CANVAS_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 190))
        self.canvas.blit(overlay, (0, 0))

        panel = pygame.Rect(_CX - 180, 190, 360, 220)
        pygame.draw.rect(self.canvas, BEIGE, panel, border_radius=8)
        pygame.draw.rect(self.canvas, GOLD, panel, 4, border_radius=8)

        title = self.font_large.render("New Highscore!", True, GOLD)
        self.canvas.blit(title, title.get_rect(center=(_CX, 240)))

        score_txt = self.font_hit.render(f"{score_to_display(self.score, MAX_SCORE)}", True, DARK_BROWN)
        self.canvas.blit(score_txt, score_txt.get_rect(center=(_CX, 285)))

        sub = self.font.render("Well hacked, woodcutter!", True, PALE_BROWN)
        self.canvas.blit(sub, sub.get_rect(center=(_CX, 325)))

        self.congrats_close_rect.center = (_CX, 370)
        mouse_pos = self._to_canvas(pygame.mouse.get_pos())
        hovered = self.congrats_close_rect.collidepoint(mouse_pos)
        pygame.draw.rect(self.canvas, PALE_BROWN if hovered else SANDY_BROWN, self.congrats_close_rect, border_radius=4)
        pygame.draw.rect(self.canvas, DARK_BROWN, self.congrats_close_rect, 2, border_radius=4)
        close_txt = self.font.render("Nice!", True, DARK_BROWN)
        self.canvas.blit(close_txt, close_txt.get_rect(center=self.congrats_close_rect.center))

    def draw(self) -> None:
        # Darken the game behind the overlay
        backdrop = pygame.Surface((_TOTAL_W, SCREEN_HEIGHT), pygame.SRCALPHA)
        backdrop.fill((0, 0, 0, 160))
        self.screen.blit(backdrop, (0, 0))

        self.canvas.fill(DARK_BROWN)
        # The scene with its gauges, shaken a little by a clean split
        dx, dy = self.scene.shake_offset
        picture = self.scene.draw(underlay=self._draw_gauges, overlay=self._draw_scene_overlay)
        self.canvas.set_clip(_SCENE_RECT)
        self.canvas.blit(picture, (_SCENE_RECT.x + dx, _SCENE_RECT.y + dy))
        self.canvas.set_clip(None)
        pygame.draw.rect(self.canvas, SANDY_BROWN, _SCENE_RECT.inflate(2, 2), 1)

        coins = score_to_coins(self.score, MAX_SCORE)
        self._draw_status_bar(coins)

        if self.done:
            self._draw_result_overlay(coins)
            if self._show_congrats:
                self._draw_congrats_overlay()

        pygame.draw.rect(self.screen, DARK_BROWN, self.canvas_rect.inflate(8, 8), border_radius=6)
        self.screen.blit(self.canvas, self.canvas_rect.topleft)
        pygame.draw.rect(self.screen, DARK_BROWN, self.canvas_rect, 3, border_radius=6)
