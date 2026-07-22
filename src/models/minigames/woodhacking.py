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
"""

import os
import math
import random
from typing import Optional, Tuple

import pygame

from .base import MinigameOverlay, score_to_coins
from ...config.colors import (
    BEIGE, SANDY_BROWN, PALE_BROWN, DARK_BROWN,
    MUTED_GREEN as GREEN, MUTED_DARK_GREEN as DARK_GREEN,
    MUTED_RED as RED, MUTED_DARK_RED as DARK_RED,
    MUTED_YELLOW as YELLOW, MUTED_ORANGE as ORANGE,
    WHITE, BLACK,
)
from ...config.constants import SCREEN_WIDTH, SCREEN_HEIGHT, SIDEBAR_WIDTH, FONTS_PATH
from ...ui.transaction_feedback import on_money_received

_TOTAL_W = SCREEN_WIDTH + SIDEBAR_WIDTH

# The minigame is drawn onto a fixed-size canvas and centered on screen —
# keeps all gauge geometry below in simple, self-contained pixel coordinates.
_CANVAS_W, _CANVAS_H = 800, 600

MINIGAME_NAME = "Woodhacking"

# ── gauge constants ─────────────────────────────────────────────────────────
_AIM_CX, _AIM_CY = _CANVAS_W // 2, 305
_AIM_R = 148

# Left-side zone boundaries (negative angles, more forgiving)
_AIM_PERFECT_L = math.radians(7)
_AIM_GOOD_L = math.radians(18)
_AIM_OK_L = math.radians(52)

# Right-side zone boundaries (positive angles, tighter green zones)
_AIM_PERFECT_R = math.radians(4)
_AIM_GOOD_R = math.radians(10)
_AIM_OK_R = math.radians(40)

_AIM_MAX = math.radians(84)
_AIM_MISS_MARGIN = math.radians(14)  # last stretch before AIM_MAX is dark red — an outright miss

_BASE_AIM_SPEED = math.radians(58)  # radians / second when idle
_CHARGE_SPEED_K = 1.8  # aim speed multiplier per full-power unit

_POWER_RECT = pygame.Rect(82, 200, 44, 200)
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

MAX_SWINGS = 30
MAX_SCORE = MAX_SWINGS * 5


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
        perfect, good, ok = _AIM_PERFECT_L, _AIM_GOOD_L, _AIM_OK_L
    else:
        perfect, good, ok = _AIM_PERFECT_R, _AIM_GOOD_R, _AIM_OK_R
    a = abs(aim)
    if a >= _AIM_MAX - _AIM_MISS_MARGIN:
        return 0, "MISS", DARK_RED, True
    if a < perfect:
        return 3, "PERFECT", DARK_GREEN, False
    if a < good:
        return 2, "GOOD", GREEN, False
    if a < ok:
        return 1, "OK", YELLOW, False
    return 0, "MISS", RED, False


def _grade_power(power: float, opt_lo: float, opt_hi: float) -> Tuple[int, str, tuple, bool]:
    """Power: 0-2 points (uses the current dynamic zone).

    Landing in the dark-red zone is a hard miss (last element True) — too
    weak or too strong to count no matter how good the aim was.
    """
    ylo, yhi, rlo, rhi = _power_zone_bounds(opt_lo, opt_hi)
    if power < rlo or power > rhi:
        return 0, "MISS", DARK_RED, True
    if opt_lo <= power <= opt_hi:
        return 2, "PERFECT", DARK_GREEN, False
    if ylo <= power < opt_lo or opt_hi < power <= yhi:
        return 1, "OK", YELLOW, False
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
            self.font_large = pygame.font.Font(os.path.join(FONTS_PATH, "Medici Text.ttf"), 28)
            self.font_hit = pygame.font.Font(os.path.join(FONTS_PATH, "RomanAntique.ttf"), 34)
        except Exception:
            self.font = pygame.font.SysFont("georgia", 18)
            self.font_large = pygame.font.SysFont("georgia", 28, bold=True)
            self.font_hit = pygame.font.SysFont("georgia", 34, bold=True)

        self.close_rect = pygame.Rect(0, 0, 160, 44)
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
        self.score = 0
        self.attempt = 0
        self.done = False
        self.aim_hit_text = ""
        self.aim_hit_color = WHITE
        self.pow_hit_text = ""
        self.pow_hit_color = WHITE
        self.hit_alpha = 0
        self._payout_booked = False

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
            if event.key == pygame.K_r and self.done:
                self._reset_round()
                return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.done:
                if self.close_rect.collidepoint(self._to_canvas(event.pos)):
                    self.active = False
                return
            if not self.charging:
                self.charging = True

        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self.charging and not self.done:
                self.charging = False
                self._resolve_swing()

    def _resolve_swing(self) -> None:
        self.attempt += 1
        aim_pts, aim_label, aim_color, aim_miss = _grade_aim(self.aim)
        pow_pts, pow_label, pow_color, pow_miss = _grade_power(
            self.power, self.opt_lo, self.opt_hi
        )
        pts = 0 if (aim_miss or pow_miss) else aim_pts + pow_pts
        self.score += pts
        self.aim_hit_text, self.aim_hit_color = aim_label, aim_color
        self.pow_hit_text, self.pow_hit_color = pow_label, pow_color
        self.hit_alpha = 255
        self.power = 0.0
        if pts >= 3:
            self.aim_speed_bonus = min(
                self.aim_speed_bonus + _SPEED_BONUS_PER_HIT, _MAX_SPEED_BONUS
            )
            self.opt_lo, self.opt_hi = _new_opt_zone()
        if self.attempt >= MAX_SWINGS:
            self.done = True
            self._book_payout()

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

        if self.hit_alpha > 0:
            self.hit_alpha = max(0, self.hit_alpha - 6)

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _draw_aim_gauge(self) -> None:
        cx, cy, r = _AIM_CX, _AIM_CY, _AIM_R
        dark_lo = _AIM_MAX - _AIM_MISS_MARGIN
        zones = [
            (-_AIM_MAX, -dark_lo, DARK_RED, 16),
            (dark_lo, _AIM_MAX, DARK_RED, 16),
            (-dark_lo, -_AIM_OK_L, RED, 16),
            (_AIM_OK_R, dark_lo, RED, 16),
            (-_AIM_OK_L, -_AIM_GOOD_L, YELLOW, 17),
            (_AIM_GOOD_R, _AIM_OK_R, YELLOW, 17),
            (-_AIM_GOOD_L, -_AIM_PERFECT_L, GREEN, 18),
            (_AIM_PERFECT_R, _AIM_GOOD_R, GREEN, 18),
            (-_AIM_PERFECT_L, 0, DARK_GREEN, 22),
            (0, _AIM_PERFECT_R, DARK_GREEN, 22),
        ]
        for a0, a1, col, w in zones:
            if a1 > a0:
                poly = _arc_ring_poly(cx, cy, r, w, a0, a1)
                pygame.draw.polygon(self.canvas, col, poly)

        outline = _arc_pts(cx, cy, r, -_AIM_MAX, _AIM_MAX)
        if len(outline) > 1:
            pygame.draw.lines(self.canvas, DARK_BROWN, False, outline, 2)

        nx = cx + r * math.sin(self.aim)
        ny = cy + r * math.cos(self.aim)
        pygame.draw.line(self.canvas, DARK_BROWN, (cx, cy), (int(nx), int(ny)), 5)
        pygame.draw.circle(self.canvas, SANDY_BROWN, (cx, cy), 10)
        pygame.draw.circle(self.canvas, DARK_BROWN, (cx, cy), 10, 2)

        lbl = self.font.render("AIM", True, DARK_BROWN)
        self.canvas.blit(lbl, lbl.get_rect(center=(cx, cy + r + 20)))

    def _draw_power_bar(self) -> None:
        r = _POWER_RECT
        ylo, yhi, rlo, rhi = _power_zone_bounds(self.opt_lo, self.opt_hi)

        zone_defs = [
            (0.0, rlo, DARK_RED),
            (rlo, ylo, RED),
            (ylo, self.opt_lo, YELLOW),
            (self.opt_lo, self.opt_hi, DARK_GREEN),
            (self.opt_hi, yhi, YELLOW),
            (yhi, rhi, RED),
            (rhi, 1.0, DARK_RED),
        ]
        for lo, hi, col in zone_defs:
            yb = r.bottom - int(lo * r.height)
            yt = r.bottom - int(hi * r.height)
            pygame.draw.rect(self.canvas, col, pygame.Rect(r.left, yt, r.width, yb - yt))

        fill_h = int(self.power * r.height)
        if fill_h > 0:
            ov = pygame.Surface((r.width, fill_h), pygame.SRCALPHA)
            ov.fill((255, 255, 255, 55))
            self.canvas.blit(ov, (r.left, r.bottom - fill_h))

        my = r.bottom - int(self.power * r.height)
        pygame.draw.line(self.canvas, WHITE, (r.left, my), (r.right, my), 2)

        pygame.draw.rect(self.canvas, DARK_BROWN, r, 2, border_radius=3)
        lbl = self.font.render("POWER", True, DARK_BROWN)
        self.canvas.blit(lbl, lbl.get_rect(center=(r.centerx, r.top - 16)))

    def _draw_status_bar(self, coins: float) -> None:
        pygame.draw.rect(self.canvas, DARK_BROWN, (0, 0, _CANVAS_W, 44))
        pygame.draw.line(self.canvas, SANDY_BROWN, (0, 44), (_CANVAS_W, 44), 1)
        title = self.font.render(f"WOODHACKING  —  {MINIGAME_NAME}", True, SANDY_BROWN)
        self.canvas.blit(title, title.get_rect(center=(_CANVAS_W // 2, 22)))

        pygame.draw.rect(self.canvas, DARK_BROWN, (0, _CANVAS_H - 46, _CANVAS_W, 46))
        pygame.draw.line(self.canvas, SANDY_BROWN, (0, _CANVAS_H - 46), (_CANVAS_W, _CANVAS_H - 46), 1)

        left = self.font.render(f"Score: {self.score} / {MAX_SCORE}", True, SANDY_BROWN)
        self.canvas.blit(left, (20, _CANVAS_H - 32))

        mid = self.font.render(f"Swing  {self.attempt} / {MAX_SWINGS}", True, SANDY_BROWN)
        self.canvas.blit(mid, mid.get_rect(centerx=_CANVAS_W // 2, y=_CANVAS_H - 32))

        right = self.font.render(f"Coins: {coins:.2f} / 20", True, SANDY_BROWN)
        self.canvas.blit(right, right.get_rect(right=_CANVAS_W - 20, y=_CANVAS_H - 32))

    def _draw_result_overlay(self, coins: float) -> None:
        overlay = pygame.Surface((_CANVAS_W, _CANVAS_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        self.canvas.blit(overlay, (0, 0))

        panel = pygame.Rect(200, 145, 400, 300)
        pygame.draw.rect(self.canvas, BEIGE, panel, border_radius=8)
        pygame.draw.rect(self.canvas, DARK_BROWN, panel, 3, border_radius=8)

        title = self.font_large.render("Session Complete!", True, DARK_BROWN)
        self.canvas.blit(title, title.get_rect(center=(400, 205)))

        score_txt = self.font.render(f"Score:  {self.score} / {MAX_SCORE}", True, BLACK)
        self.canvas.blit(score_txt, score_txt.get_rect(center=(400, 258)))

        coin_color = DARK_GREEN if coins >= 15 else (ORANGE if coins >= 8 else RED)
        coin_txt = self.font_large.render(f"+{coins:.2f}g earned today", True, coin_color)
        self.canvas.blit(coin_txt, coin_txt.get_rect(center=(400, 308)))

        hint = self.font.render("R — play again", True, PALE_BROWN)
        self.canvas.blit(hint, hint.get_rect(center=(400, 355)))

        self.close_rect.center = (400, 405)
        mouse_pos = self._to_canvas(pygame.mouse.get_pos())
        hovered = self.close_rect.collidepoint(mouse_pos)
        pygame.draw.rect(self.canvas, PALE_BROWN if hovered else SANDY_BROWN, self.close_rect, border_radius=4)
        pygame.draw.rect(self.canvas, DARK_BROWN, self.close_rect, 2, border_radius=4)
        close_txt = self.font.render("Close", True, DARK_BROWN)
        self.canvas.blit(close_txt, close_txt.get_rect(center=self.close_rect.center))

    def draw(self) -> None:
        # Darken the game behind the overlay
        backdrop = pygame.Surface((_TOTAL_W, SCREEN_HEIGHT), pygame.SRCALPHA)
        backdrop.fill((0, 0, 0, 160))
        self.screen.blit(backdrop, (0, 0))

        self.canvas.fill(BEIGE)
        self._draw_aim_gauge()
        self._draw_power_bar()

        if self.hit_alpha > 0:
            aim_txt = self.font_hit.render(self.aim_hit_text, True, self.aim_hit_color)
            aim_txt.set_alpha(self.hit_alpha)
            self.canvas.blit(aim_txt, aim_txt.get_rect(center=(_AIM_CX, _AIM_CY + 36)))

            pow_txt = self.font_hit.render(self.pow_hit_text, True, self.pow_hit_color)
            pow_txt.set_alpha(self.hit_alpha)
            self.canvas.blit(pow_txt, pow_txt.get_rect(center=(_POWER_RECT.centerx, _POWER_RECT.bottom + 24)))

        if self.charging:
            hint = self.font.render("CHARGING — release to swing!", True, DARK_BROWN)
        else:
            hint = self.font.render("Hold LMB to charge power - release to swing", True, PALE_BROWN)
        self.canvas.blit(hint, hint.get_rect(center=(_CANVAS_W // 2, _CANVAS_H - 60)))

        coins = score_to_coins(self.score, MAX_SCORE)
        self._draw_status_bar(coins)

        if self.done:
            self._draw_result_overlay(coins)

        pygame.draw.rect(self.screen, DARK_BROWN, self.canvas_rect.inflate(8, 8), border_radius=6)
        self.screen.blit(self.canvas, self.canvas_rect.topleft)
        pygame.draw.rect(self.screen, DARK_BROWN, self.canvas_rect, 3, border_radius=6)
