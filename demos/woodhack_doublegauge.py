"""
Woodhacking Demo B — Double Gauge
-----------------------------------
Two independent mechanics you must juggle at the same time:

  1. AIM needle  — oscillates left and right across a semicircular gauge.
                   The green zone at the bottom is where you want it.
                   Hold the mouse button and it speeds up — the longer
                   you charge, the harder it is to keep aim.

  2. POWER bar   — fills while you hold the mouse button.
                   The green band in the middle is the sweet spot;
                   too weak or too strong both penalise the score.

Hold LMB to charge power, release to swing. Both gauges are evaluated
at the moment you release.

Run: python demos/woodhack_doublegauge.py
"""
import sys
import math
import random
import pygame

# ── palette (mirrors src/config/colors.py — no src/ import needed) ─────────────
WHITE        = (255, 255, 255)
BLACK        = (0,   0,   0)
BEIGE        = (245, 245, 220)
SANDY_BROWN  = (210, 184, 116)
PALE_BROWN   = (152, 118,  84)
DARK_BROWN   = (101,  67,  33)
GREEN        = ( 76, 175,  80)
DARK_GREEN   = ( 46, 125,  50)
RED          = (200,  60,  50)
DARK_RED     = (120,  25,  20)
YELLOW       = (230, 200,  60)
ORANGE       = (220, 140,  40)

SCREEN_W, SCREEN_H = 800, 600


def score_to_coins(score: int, max_score: int) -> float:
    """Non-linear: poor skill earns little, mastery earns up to 20.

    Returns coins with cent precision (2 decimals) rather than rounding
    down to whole coins, so small skill differences still show up in the
    reward.
    """
    if max_score == 0:
        return 0.0
    ratio = max(0.0, min(1.0, score / max_score))
    return round(20 * ratio ** 2.5, 2)


def draw_result_overlay(surface: pygame.Surface, font_large, font_small, coins: float,
                        score: int, max_score: int) -> None:
    overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 160))
    surface.blit(overlay, (0, 0))

    panel = pygame.Rect(200, 155, 400, 270)
    pygame.draw.rect(surface, BEIGE, panel, border_radius=8)
    pygame.draw.rect(surface, DARK_BROWN, panel, 3, border_radius=8)

    title = font_large.render("Session Complete!", True, DARK_BROWN)
    surface.blit(title, title.get_rect(center=(400, 215)))

    score_txt = font_small.render(f"Score:  {score} / {max_score}", True, BLACK)
    surface.blit(score_txt, score_txt.get_rect(center=(400, 268)))

    coin_color = DARK_GREEN if coins >= 15 else (ORANGE if coins >= 8 else RED)
    coin_txt = font_large.render(f"+{coins:.2f} coins earned today", True, coin_color)
    surface.blit(coin_txt, coin_txt.get_rect(center=(400, 318)))

    hint = font_small.render("R — play again     ESC — quit", True, PALE_BROWN)
    surface.blit(hint, hint.get_rect(center=(400, 385)))


def draw_status_bar(surface: pygame.Surface, font, score: int, max_score: int,
                    coins: float, attempt: int, max_attempts: int, mechanic_name: str) -> None:
    # Top title bar
    pygame.draw.rect(surface, DARK_BROWN, (0, 0, SCREEN_W, 44))
    pygame.draw.line(surface, SANDY_BROWN, (0, 44), (SCREEN_W, 44), 1)
    title = font.render(f"WOODHACKING  —  {mechanic_name}", True, SANDY_BROWN)
    surface.blit(title, title.get_rect(center=(SCREEN_W // 2, 22)))

    # Bottom status bar
    pygame.draw.rect(surface, DARK_BROWN, (0, SCREEN_H - 46, SCREEN_W, 46))
    pygame.draw.line(surface, SANDY_BROWN, (0, SCREEN_H - 46), (SCREEN_W, SCREEN_H - 46), 1)

    left = font.render(f"Score: {score} / {max_score}", True, SANDY_BROWN)
    surface.blit(left, (20, SCREEN_H - 32))

    mid = font.render(f"Swing  {attempt} / {max_attempts}", True, SANDY_BROWN)
    surface.blit(mid, mid.get_rect(centerx=SCREEN_W // 2, y=SCREEN_H - 32))

    right = font.render(f"Coins: {coins:.2f} / 20", True, SANDY_BROWN)
    surface.blit(right, right.get_rect(right=SCREEN_W - 20, y=SCREEN_H - 32))


# ── gauge constants ────────────────────────────────────────────────────────────
AIM_CX, AIM_CY = SCREEN_W // 2, 305
AIM_R          = 148

# Left-side zone boundaries (negative angles, more forgiving)
# Perfect/good bands are narrower than they used to be — the steeper coin
# payout curve means "PERFECT!"/"GREAT!" should be rare, not routine.
AIM_PERFECT_L  = math.radians(7)
AIM_GOOD_L     = math.radians(18)
AIM_OK_L       = math.radians(52)

# Right-side zone boundaries (positive angles, tighter green zones)
AIM_PERFECT_R  = math.radians(4)
AIM_GOOD_R     = math.radians(10)
AIM_OK_R       = math.radians(40)

AIM_MAX        = math.radians(84)
AIM_MISS_MARGIN = math.radians(14)  # last stretch before AIM_MAX is dark red — an outright miss

BASE_AIM_SPEED = math.radians(58)   # radians / second when idle
CHARGE_SPEED_K = 1.8                # aim speed multiplier per full-power unit

POWER_RECT     = pygame.Rect(82, 200, 44, 200)
OPT_WIDTH      = 0.14              # green zone width (narrowed — perfect power should be rare)
OPT_CENTER_0   = 0.64              # starting center (gives lo=0.57, hi=0.71)
POWER_RATE     = 0.72               # fills from 0→1 in ~1.4 seconds

YELLOW_MARGIN  = 0.12              # yellow band width either side of green
RED_MARGIN     = 0.12              # red band width beyond the yellow band
MISS_EDGE      = 0.06              # dark red always reaches this close to 0/1
# Anything beyond the red band (too weak / too strong) is dark red — a miss.
# The very top and bottom of the scale (within MISS_EDGE) are always dark
# red, no matter where the green zone sits, so a bare tip of the mouse or
# holding all the way to full power is always a miss.

SPEED_BONUS_PER_HIT = math.radians(6)   # added to base needle speed each good/perfect
MAX_SPEED_BONUS     = BASE_AIM_SPEED * 2.0


def _power_zone_bounds(opt_lo: float, opt_hi: float) -> tuple[float, float, float, float]:
    """Yellow and red band edges around the green sweet spot.

    Shared by drawing and scoring so the visible zones and the
    scored zones never drift apart.
    """
    ylo = max(0.0, opt_lo - YELLOW_MARGIN)
    yhi = min(1.0, opt_hi + YELLOW_MARGIN)
    rlo = max(MISS_EDGE, opt_lo - YELLOW_MARGIN - RED_MARGIN)
    rhi = min(1.0 - MISS_EDGE, opt_hi + YELLOW_MARGIN + RED_MARGIN)
    # Keep bands monotonic (dark red <= red <= yellow <= green) even when
    # the green zone sits close enough to an edge to compress the red band.
    ylo = max(ylo, rlo)
    yhi = min(yhi, rhi)
    return ylo, yhi, rlo, rhi


def _new_opt_zone() -> tuple[float, float]:
    center = random.uniform(0.22, 0.78)
    return center - OPT_WIDTH / 2, center + OPT_WIDTH / 2

MAX_SWINGS  = 30
MAX_SCORE   = MAX_SWINGS * 5


# ─────────────────────────────────────────────────────────────────────────────

def _arc_pts(cx: int, cy: int, r: int, a0: float, a1: float,
             steps: int = 48) -> list[tuple[float, float]]:
    """Arc points where angle 0 = bottom, +angle = right (U-shape opening up)."""
    pts = []
    for i in range(steps + 1):
        t = a0 + (a1 - a0) * i / steps
        pts.append((cx + r * math.sin(t), cy + r * math.cos(t)))
    return pts


def _draw_aim_gauge(surface: pygame.Surface, aim: float, font) -> None:
    cx, cy, r = AIM_CX, AIM_CY, AIM_R

    # Coloured zone arcs — left side more forgiving, right side tighter
    dark_lo = AIM_MAX - AIM_MISS_MARGIN
    zones = [
        (-AIM_MAX,      -dark_lo,       DARK_RED,   16),
        (dark_lo,        AIM_MAX,       DARK_RED,   16),
        (-dark_lo,      -AIM_OK_L,      RED,        16),
        (AIM_OK_R,       dark_lo,       RED,        16),
        (-AIM_OK_L,     -AIM_GOOD_L,    YELLOW,     17),
        (AIM_GOOD_R,     AIM_OK_R,      YELLOW,     17),
        (-AIM_GOOD_L,   -AIM_PERFECT_L, GREEN,      18),
        (AIM_PERFECT_R,  AIM_GOOD_R,    GREEN,      18),
        (-AIM_PERFECT_L, 0,             DARK_GREEN, 22),
        (0,              AIM_PERFECT_R, DARK_GREEN, 22),
    ]
    for a0, a1, col, w in zones:
        pts = _arc_pts(cx, cy, r, a0, a1)
        if len(pts) > 1:
            pygame.draw.lines(surface, col, False, pts, w)

    # Dark outline
    outline = _arc_pts(cx, cy, r, -AIM_MAX, AIM_MAX)
    if len(outline) > 1:
        pygame.draw.lines(surface, DARK_BROWN, False, outline, 2)

    # Needle
    nx = cx + r * math.sin(aim)
    ny = cy + r * math.cos(aim)
    pygame.draw.line(surface, DARK_BROWN, (cx, cy), (int(nx), int(ny)), 5)
    pygame.draw.circle(surface, SANDY_BROWN, (cx, cy), 10)
    pygame.draw.circle(surface, DARK_BROWN,  (cx, cy), 10, 2)

    lbl = font.render("AIM", True, DARK_BROWN)
    surface.blit(lbl, lbl.get_rect(center=(cx, cy + r + 20)))


def _draw_power_bar(surface: pygame.Surface, power: float, font,
                    opt_lo: float, opt_hi: float) -> None:
    r = POWER_RECT
    ylo, yhi, rlo, rhi = _power_zone_bounds(opt_lo, opt_hi)

    # Zone background (bottom-up: dark red / red / yellow / green / yellow / red / dark red)
    zone_defs = [
        (0.0,    rlo,    DARK_RED),
        (rlo,    ylo,    RED),
        (ylo,    opt_lo, YELLOW),
        (opt_lo, opt_hi, DARK_GREEN),
        (opt_hi, yhi,    YELLOW),
        (yhi,    rhi,    RED),
        (rhi,    1.0,    DARK_RED),
    ]
    for lo, hi, col in zone_defs:
        yb = r.bottom - int(lo * r.height)
        yt = r.bottom - int(hi * r.height)
        pygame.draw.rect(surface, col, pygame.Rect(r.left, yt, r.width, yb - yt))

    # Translucent fill overlay
    fill_h = int(power * r.height)
    if fill_h > 0:
        ov = pygame.Surface((r.width, fill_h), pygame.SRCALPHA)
        ov.fill((255, 255, 255, 55))
        surface.blit(ov, (r.left, r.bottom - fill_h))

    # Current-level marker
    my = r.bottom - int(power * r.height)
    pygame.draw.line(surface, WHITE, (r.left, my), (r.right, my), 2)

    pygame.draw.rect(surface, DARK_BROWN, r, 2, border_radius=3)
    lbl = font.render("POWER", True, DARK_BROWN)
    surface.blit(lbl, lbl.get_rect(center=(r.centerx, r.top - 16)))



def _grade_aim(aim: float) -> tuple[int, str, tuple, bool]:
    """Aim: 0-3 points — right side uses tighter thresholds.

    The far edge of travel (within AIM_MISS_MARGIN of AIM_MAX) is dark red —
    a hard miss (last element True), no matter how good the power was.
    """
    if aim < 0:
        perfect, good, ok = AIM_PERFECT_L, AIM_GOOD_L, AIM_OK_L
    else:
        perfect, good, ok = AIM_PERFECT_R, AIM_GOOD_R, AIM_OK_R
    a = abs(aim)
    if a >= AIM_MAX - AIM_MISS_MARGIN: return 0, "MISS", DARK_RED, True
    if a < perfect: return 3, "PERFECT", DARK_GREEN, False
    if a < good:    return 2, "GOOD",    GREEN,      False
    if a < ok:      return 1, "OK",      YELLOW,     False
    return 0, "MISS", RED, False


def _grade_power(power: float, opt_lo: float, opt_hi: float) -> tuple[int, str, tuple, bool]:
    """Power: 0-2 points (uses the current dynamic zone).

    Landing in the dark-red zone is a hard miss (last element True) —
    too weak or too strong to count no matter how good the aim was.
    """
    ylo, yhi, rlo, rhi = _power_zone_bounds(opt_lo, opt_hi)
    if power < rlo or power > rhi:
        return 0, "MISS", DARK_RED, True
    if opt_lo <= power <= opt_hi:
        return 2, "PERFECT", DARK_GREEN, False
    if ylo <= power < opt_lo or opt_hi < power <= yhi:
        return 1, "OK", YELLOW, False
    return 0, "WEAK", RED, False


def _reset() -> dict:
    lo = OPT_CENTER_0 - OPT_WIDTH / 2
    hi = OPT_CENTER_0 + OPT_WIDTH / 2
    return dict(
        aim             = 0.0,
        aim_dir         = 1,
        aim_speed_bonus = 0.0,
        power           = 0.0,
        opt_lo          = lo,
        opt_hi          = hi,
        charging        = False,
        score           = 0,
        attempt         = 0,
        done            = False,
        aim_hit_text    = "",
        aim_hit_color   = WHITE,
        pow_hit_text    = "",
        pow_hit_color   = WHITE,
        hit_alpha       = 0,
    )


def run() -> None:
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption("Woodhacking — Double Gauge")
    clock  = pygame.time.Clock()

    font       = pygame.font.SysFont("Georgia", 18)
    font_large = pygame.font.SysFont("Georgia", 28, bold=True)
    font_hit   = pygame.font.SysFont("Georgia", 34, bold=True)

    state = _reset()

    while True:
        dt = clock.tick(60) / 1000.0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    pygame.quit(); sys.exit()
                if event.key == pygame.K_r and state["done"]:
                    state = _reset()

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if not state["done"] and not state["charging"]:
                    state["charging"] = True

            if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if state["charging"] and not state["done"]:
                    state["charging"] = False
                    state["attempt"] += 1
                    aim_pts, aim_label, aim_color, aim_miss = _grade_aim(state["aim"])
                    pow_pts, pow_label, pow_color, pow_miss = _grade_power(
                        state["power"], state["opt_lo"], state["opt_hi"])
                    pts = 0 if (aim_miss or pow_miss) else aim_pts + pow_pts
                    state["score"] += pts
                    state["aim_hit_text"],  state["aim_hit_color"] = aim_label, aim_color
                    state["pow_hit_text"],  state["pow_hit_color"] = pow_label, pow_color
                    state["hit_alpha"] = 255
                    state["power"]     = 0.0
                    if pts >= 3:
                        state["aim_speed_bonus"] = min(
                            state["aim_speed_bonus"] + SPEED_BONUS_PER_HIT,
                            MAX_SPEED_BONUS)
                        state["opt_lo"], state["opt_hi"] = _new_opt_zone()
                    if state["attempt"] >= MAX_SWINGS:
                        state["done"] = True

        # ── update ──────────────────────────────────────────────────────────
        if not state["done"]:
            spd = (BASE_AIM_SPEED + state["aim_speed_bonus"]) * (1.0 + state["power"] * CHARGE_SPEED_K)
            state["aim"] += state["aim_dir"] * spd * dt
            if abs(state["aim"]) >= AIM_MAX:
                state["aim_dir"] *= -1
                state["aim"] = math.copysign(AIM_MAX, state["aim"])

            if state["charging"]:
                state["power"] = min(1.0, state["power"] + POWER_RATE * dt)

        if state["hit_alpha"] > 0:
            state["hit_alpha"] = max(0, state["hit_alpha"] - 6)

        # ── draw ─────────────────────────────────────────────────────────────
        screen.fill(BEIGE)

        _draw_aim_gauge(screen, state["aim"], font)
        _draw_power_bar(screen, state["power"], font, state["opt_lo"], state["opt_hi"])

        # Hit text — aim and power grade independently, so each gets its own word
        if state["hit_alpha"] > 0:
            aim_txt = font_hit.render(state["aim_hit_text"], True, state["aim_hit_color"])
            aim_txt.set_alpha(state["hit_alpha"])
            screen.blit(aim_txt, aim_txt.get_rect(center=(AIM_CX, AIM_CY + 36)))

            pow_txt = font_hit.render(state["pow_hit_text"], True, state["pow_hit_color"])
            pow_txt.set_alpha(state["hit_alpha"])
            screen.blit(pow_txt, pow_txt.get_rect(center=(POWER_RECT.centerx, POWER_RECT.bottom + 24)))

        # Instruction
        if state["charging"]:
            hint = font.render("CHARGING — release to swing!", True, DARK_BROWN)
        else:
            hint = font.render("Hold LMB to charge power · release to swing", True, PALE_BROWN)
        screen.blit(hint, hint.get_rect(center=(SCREEN_W // 2, SCREEN_H - 60)))

        coins = score_to_coins(state["score"], MAX_SCORE)
        draw_status_bar(screen, font, state["score"], MAX_SCORE,
                        coins, state["attempt"], MAX_SWINGS, "Double Gauge")

        if state["done"]:
            draw_result_overlay(screen, font_large, font,
                                coins, state["score"], MAX_SCORE)

        pygame.display.flip()


if __name__ == "__main__":
    run()
