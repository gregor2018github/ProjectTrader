"""Loan dialogs for the Bank building.

Three dialogs:
  LoanDialog        — take out a new loan
  RepayDialog       — repay an active loan early
  LoanOverviewDialog — read-only summary of active loans
"""

import pygame
import os
from typing import Optional, Tuple, List, TYPE_CHECKING
from ...config.colors import SANDY_BROWN, DARK_BROWN, BLACK, WHITE, DARK_GREEN, DARK_RED, DARK_GRAY, LIGHT_GRAY
from ...config.constants import (
    LOAN_BASE_RATES, LOAN_DURATION_FACTORS, LOAN_EQUITY_RATIOS,
    LOAN_MIN_AMOUNT, LOAN_MIN_DAILY_PCT, FONTS_PATH, SCREEN_WIDTH, SCREEN_HEIGHT, SIDEBAR_WIDTH,
)

if TYPE_CHECKING:
    from ...game_state import GameState

DURATION_OPTIONS = [10, 20, 30, 60, 90]   # allowed loan durations in days


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _calc_max_loan(wealth: float) -> int:
    ratio = 0.80
    for threshold, r in LOAN_EQUITY_RATIOS:
        if wealth < threshold:
            ratio = r
            break
    return max(500, int(wealth * ratio))


def _calc_loan_params(original_amount: float, duration_days: int, repayment_pct: float, wealth: float):
    """Compute loan payment breakdown for a proposed loan.

    repayment_pct: LOAN_MIN_DAILY_PCT–100 — percentage of principal repaid through
    daily installments. The rest is paid as a settlement at maturity.

    Returns: (daily_principal, daily_interest, settlement_principal, total_interest, total_payback)
    """
    base_rate = 0.07
    for threshold, rate in LOAN_BASE_RATES:
        if wealth < threshold:
            base_rate = rate
            break
    dur_factor = 1.35
    for max_days, factor in LOAN_DURATION_FACTORS:
        if duration_days <= max_days:
            dur_factor = factor
            break
    if original_amount <= 0 or duration_days <= 0:
        return 0.0, 0.0, 0.0, 0.0, 0.0

    repayment_pct = max(float(LOAN_MIN_DAILY_PCT), min(100.0, repayment_pct))

    # Daily principal: share of total principal spread across the term
    daily_principal = round(original_amount * (repayment_pct / 100.0) / duration_days, 2)
    # Settlement: whatever principal is left after all daily repayments
    settlement_principal = round(max(0.0, original_amount - daily_principal * duration_days), 2)

    # Fixed daily interest on the original amount (simple interest with duration factor)
    raw_daily_interest = original_amount * base_rate / 365 * dur_factor
    daily_interest = max(0.01, round(raw_daily_interest, 2))

    total_interest = round(daily_interest * duration_days, 2)
    total_payback = round(original_amount + total_interest, 2)

    return daily_principal, daily_interest, settlement_principal, total_interest, total_payback


def _close_dialog(game_state: 'GameState') -> None:
    game_state.menu_fade_window = game_state.info_window
    game_state.menu_fade_timer = game_state.menu_fade_duration
    game_state.info_window = None
    game_state.active_house_menu = None


def _load_fonts():
    try:
        title_font = pygame.font.Font(os.path.join(FONTS_PATH, "Medici Text.ttf"), 28)
        body_font = pygame.font.Font(os.path.join(FONTS_PATH, "Augusta.ttf"), 20)
    except Exception:
        title_font = pygame.font.SysFont("arial", 24)
        body_font = pygame.font.SysFont("arial", 18)
    return title_font, body_font


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------

def open_loan_dialog(game_state: 'GameState') -> None:
    depot = game_state.game.depot
    wealth = depot.wealth[-1] if depot.wealth else depot.money
    game_state.info_window = LoanDialog(game_state.screen, game_state, wealth)
    game_state.active_house_menu = None


def open_repay_dialog(game_state: 'GameState') -> None:
    game_state.info_window = RepayDialog(game_state.screen, game_state)
    game_state.active_house_menu = None


def open_loan_overview_dialog(game_state: 'GameState') -> None:
    game_state.info_window = LoanOverviewDialog(game_state.screen, game_state)
    game_state.active_house_menu = None


# ---------------------------------------------------------------------------
# Shared base: centred panel with a close [X] button
# ---------------------------------------------------------------------------

class _BaseDialog:
    PAD = 14
    HDR = 34
    BTN_H = 32
    CLOSE_SIZE = 24

    def __init__(self, screen: pygame.Surface, game_state: 'GameState',
                 width: int, height: int) -> None:
        self.screen = screen
        self.game_state = game_state
        self.title_font, self.body_font = _load_fonts()

        total_w = SCREEN_WIDTH + SIDEBAR_WIDTH
        self.panel = pygame.Rect(
            (total_w - width) // 2,
            (SCREEN_HEIGHT - height) // 2,
            width, height,
        )
        self.close_rect = pygame.Rect(
            self.panel.right - self.CLOSE_SIZE - 4,
            self.panel.top + 4,
            self.CLOSE_SIZE, self.CLOSE_SIZE,
        )

    # -- drawing helpers -------------------------------------------------------

    def _draw_panel(self, surf: pygame.Surface, off: Tuple[int, int]) -> None:
        r = self.panel.move(*off)
        pygame.draw.rect(surf, SANDY_BROWN, r, border_radius=6)
        pygame.draw.rect(surf, DARK_BROWN, r, 3, border_radius=6)

    def _draw_close_btn(self, surf: pygame.Surface, off: Tuple[int, int]) -> None:
        r = self.close_rect.move(*off)
        pygame.draw.rect(surf, DARK_BROWN, r, border_radius=4)
        mg = 5
        pygame.draw.line(surf, WHITE, (r.left + mg, r.top + mg), (r.right - mg, r.bottom - mg), 2)
        pygame.draw.line(surf, WHITE, (r.left + mg, r.bottom - mg), (r.right - mg, r.top + mg), 2)

    def _draw_title(self, surf: pygame.Surface, off: Tuple[int, int], text: str) -> None:
        ts = self.title_font.render(text, True, DARK_BROWN)
        tr = ts.get_rect(centerx=self.panel.move(*off).centerx,
                         top=self.panel.move(*off).top + 6)
        surf.blit(ts, tr)

    def _text(self, surf: pygame.Surface, text: str, x: int, y: int,
              color=BLACK, center: bool = False) -> int:
        s = self.body_font.render(text, True, color)
        r = s.get_rect()
        if center:
            r.centerx = x
            r.top = y
        else:
            r.left = x
            r.top = y
        surf.blit(s, r)
        return r.bottom

    def _draw_btn(self, surf: pygame.Surface, rect: pygame.Rect, label: str,
                  mouse_pos: Tuple[int, int], color=SANDY_BROWN,
                  border=DARK_BROWN, active: bool = False) -> None:
        bg = (180, 130, 60) if active else color
        pygame.draw.rect(surf, bg, rect, border_radius=4)
        pygame.draw.rect(surf, border, rect, 2, border_radius=4)
        if rect.collidepoint(mouse_pos) and not active:
            ov = pygame.Surface(rect.size, pygame.SRCALPHA)
            ov.fill((0, 0, 0, 30))
            surf.blit(ov, rect)
        ts = self.body_font.render(label, True, BLACK)
        surf.blit(ts, ts.get_rect(center=rect.center))

    # -- event interface -------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> None:
        pass

    def handle_click(self, pos: Tuple[int, int]) -> bool:
        if self.close_rect.collidepoint(pos):
            _close_dialog(self.game_state)
            return True
        if not self.panel.collidepoint(pos):
            _close_dialog(self.game_state)
            return True
        return True

    def draw(self, alpha_scale: float = 1.0) -> None:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# LoanDialog — take out a new loan
# ---------------------------------------------------------------------------

class LoanDialog(_BaseDialog):
    """Dialog for taking out a new loan from the bank."""

    W, H = 460, 450

    def __init__(self, screen: pygame.Surface, game_state: 'GameState', wealth: float) -> None:
        super().__init__(screen, game_state, self.W, self.H)
        depot = game_state.game.depot
        self.wealth = wealth
        self.max_loan = _calc_max_loan(wealth)
        self.min_loan = LOAN_MIN_AMOUNT

        # Amount slider
        # Layout mirrors draw(): HDR(34) + PAD(14) + wealth_line(26) + amount_label(22) = 96
        self.amount = min(self.max_loan, max(self.min_loan, self.max_loan // 2))
        asl_y = self.panel.top + self.HDR + self.PAD + 26 + 22
        self.amount_slider = pygame.Rect(
            self.panel.left + self.PAD, asl_y,
            self.W - 2 * self.PAD, 10
        )

        # Duration buttons: after slider(10) + PAD(14) + dur_label(22)
        self.duration_idx = 1               # default 20 days
        dur_y = asl_y + 10 + self.PAD + 22
        btn_w = (self.W - 2 * self.PAD - 4 * 6) // 5
        self.dur_btns: List[Tuple[pygame.Rect, int]] = []
        for i, days in enumerate(DURATION_OPTIONS):
            r = pygame.Rect(self.panel.left + self.PAD + i * (btn_w + 6), dur_y, btn_w, 30)
            self.dur_btns.append((r, days))

        # Repayment slider: after dur_btns(30) + PAD(14) + split_label(22)
        self.repayment_pct: float = 50.0   # % of principal repaid through daily installments
        spl_y = dur_y + 30 + self.PAD + 22
        self.split_slider = pygame.Rect(
            self.panel.left + self.PAD, spl_y,
            self.W - 2 * self.PAD, 10
        )

        # Confirm button
        self.confirm_btn = pygame.Rect(
            self.panel.left + self.PAD,
            self.panel.bottom - self.BTN_H - self.PAD,
            self.W - 2 * self.PAD, self.BTN_H,
        )

        self._dragging_amount = False
        self._dragging_split = False

    # -- slider helpers --------------------------------------------------------

    def _amount_thumb_x(self) -> int:
        span = self.max_loan - self.min_loan
        if span <= 0:
            return self.amount_slider.x
        ratio = (self.amount - self.min_loan) / span
        return self.amount_slider.x + int(ratio * self.amount_slider.width)

    def _split_thumb_x(self) -> int:
        # Slider maps LOAN_MIN_DAILY_PCT..100 across the full track width
        ratio = (self.repayment_pct - LOAN_MIN_DAILY_PCT) / (100.0 - LOAN_MIN_DAILY_PCT)
        return self.split_slider.x + int(ratio * self.split_slider.width)

    def _update_amount_from_x(self, x: int) -> None:
        x = max(self.amount_slider.x, min(x, self.amount_slider.right))
        ratio = (x - self.amount_slider.x) / self.amount_slider.width
        self.amount = self.min_loan + int(ratio * (self.max_loan - self.min_loan))
        self.amount = max(self.min_loan, min(self.max_loan, self.amount))

    def _update_split_from_x(self, x: int) -> None:
        x = max(self.split_slider.x, min(x, self.split_slider.right))
        ratio = (x - self.split_slider.x) / self.split_slider.width
        self.repayment_pct = round(LOAN_MIN_DAILY_PCT + ratio * (100.0 - LOAN_MIN_DAILY_PCT))

    # -- events ----------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.amount_slider.inflate(0, 20).collidepoint(event.pos):
                self._dragging_amount = True
                self._update_amount_from_x(event.pos[0])
            elif self.split_slider.inflate(0, 20).collidepoint(event.pos):
                self._dragging_split = True
                self._update_split_from_x(event.pos[0])
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self._dragging_amount = False
            self._dragging_split = False
        elif event.type == pygame.MOUSEMOTION:
            if self._dragging_amount:
                self._update_amount_from_x(event.pos[0])
            elif self._dragging_split:
                self._update_split_from_x(event.pos[0])

    def handle_click(self, pos: Tuple[int, int]) -> bool:
        if self.close_rect.collidepoint(pos):
            _close_dialog(self.game_state)
            return True
        if not self.panel.collidepoint(pos):
            _close_dialog(self.game_state)
            return True
        for r, days in self.dur_btns:
            if r.collidepoint(pos):
                self.duration_idx = DURATION_OPTIONS.index(days)
                return True
        if self.confirm_btn.collidepoint(pos) and self.max_loan >= self.min_loan:
            duration = DURATION_OPTIONS[self.duration_idx]
            daily_principal, daily_interest, settlement_principal, _, _ = _calc_loan_params(
                self.amount, duration, self.repayment_pct, self.wealth
            )
            start_str = self.game_state.date.strftime("%d.%m.%Y")
            self.game_state.game.depot.take_loan(
                self.amount, daily_principal, daily_interest, settlement_principal, duration, start_str
            )
            _close_dialog(self.game_state)
            return True
        return True

    def draw(self, alpha_scale: float = 1.0) -> None:
        if alpha_scale <= 0:
            return
        use_temp = alpha_scale < 1.0
        if use_temp:
            surf = pygame.Surface((self.W + 10, self.H + 10), pygame.SRCALPHA)
            off = (-self.panel.left + 0, -self.panel.top + 0)
        else:
            surf = self.screen
            off = (0, 0)

        self._draw_panel(surf, off)
        self._draw_close_btn(surf, off)
        self._draw_title(surf, off, "Bank — Take Out a Loan")

        mouse = pygame.mouse.get_pos()
        p = self.panel.move(*off)
        cx = p.centerx
        y = p.top + self.HDR + self.PAD

        # Wealth / max loan info
        self._text(surf, f"Your Wealth: {self.wealth:.0f}  |  Max Loan: {self.max_loan}", cx, y,
                   color=DARK_BROWN, center=True)
        y += 26

        # Amount slider label
        self._text(surf, f"Loan Amount: {self.amount}", cx, y, center=True)
        y += 22

        asl = self.amount_slider.move(*off)
        pygame.draw.rect(surf, DARK_GRAY, asl, border_radius=5)
        fill_w = self._amount_thumb_x() - self.amount_slider.x
        if fill_w > 0:
            pygame.draw.rect(surf, (120, 80, 40),
                             pygame.Rect(asl.x, asl.y, fill_w, asl.h), border_radius=5)
        tx = self._amount_thumb_x() + off[0]
        pygame.draw.circle(surf, WHITE, (tx, asl.centery), 10)
        pygame.draw.circle(surf, DARK_BROWN, (tx, asl.centery), 10, 2)
        y = asl.bottom + self.PAD

        # Duration buttons
        self._text(surf, "Duration (days):", p.left + self.PAD, y)
        y += 22
        for i, (r, days) in enumerate(self.dur_btns):
            self._draw_btn(surf, r.move(*off), str(days), mouse,
                           active=(i == self.duration_idx))
        y = self.dur_btns[0][0].move(*off).bottom + self.PAD

        # Repayment slider label
        settlement_pct = 100 - int(self.repayment_pct)
        self._text(surf,
                   f"Daily repayment: {int(self.repayment_pct)}%  ·  Settlement: {settlement_pct}%",
                   cx, y, center=True)
        y += 22

        spl = self.split_slider.move(*off)
        pygame.draw.rect(surf, DARK_GRAY, spl, border_radius=5)
        sfill_w = self._split_thumb_x() - self.split_slider.x
        if sfill_w > 0:
            pygame.draw.rect(surf, (120, 80, 40),
                             pygame.Rect(spl.x, spl.y, sfill_w, spl.h), border_radius=5)
        stx = self._split_thumb_x() + off[0]
        pygame.draw.circle(surf, WHITE, (stx, spl.centery), 10)
        pygame.draw.circle(surf, DARK_BROWN, (stx, spl.centery), 10, 2)
        y = spl.bottom + self.PAD + 4

        # Payment preview
        duration = DURATION_OPTIONS[self.duration_idx]
        daily_principal, daily_interest, settlement_principal, total_interest, total_payback = \
            _calc_loan_params(self.amount, duration, self.repayment_pct, self.wealth)
        daily_total = daily_principal + daily_interest
        self._text(surf,
                   f"Daily payment: {daily_total:.2f}  ({daily_principal:.2f} principal + {daily_interest:.2f} interest)",
                   cx, y, color=DARK_BROWN, center=True)
        y += 22
        self._text(surf, f"Settlement at end: {settlement_principal:.2f}", cx, y,
                   color=DARK_BROWN, center=True)
        y += 22
        self._text(surf, f"Total interest: {total_interest:.2f}  |  Total payback: {total_payback:.2f}",
                   cx, y, color=DARK_RED, center=True)

        # Confirm button
        self._draw_btn(surf, self.confirm_btn.move(*off), "Confirm Loan", mouse)

        if use_temp:
            surf.set_alpha(int(255 * alpha_scale))
            self.screen.blit(surf, (self.panel.left, self.panel.top))


# ---------------------------------------------------------------------------
# RepayDialog — early repayment of active loans
# ---------------------------------------------------------------------------

class RepayDialog(_BaseDialog):
    """Dialog listing active loans with a Repay button for each."""

    W = 520
    ROW_H = 72    # 3 lines × 22px + 6px padding
    PAD_TOP = 12

    def __init__(self, screen: pygame.Surface, game_state: 'GameState') -> None:
        loans = game_state.game.depot.active_loans
        n = max(1, len(loans))
        h = self.HDR + self.PAD_TOP + n * self.ROW_H + self.PAD * 2
        h = max(160, min(h, 500))
        super().__init__(screen, game_state, self.W, h)
        self._build_repay_btns()

    def _build_repay_btns(self) -> None:
        loans = self.game_state.game.depot.active_loans
        self.repay_btns: List[pygame.Rect] = []
        btn_w = 80
        y = self.panel.top + self.HDR + self.PAD_TOP
        for _ in loans:
            # Button centred vertically in each row
            r = pygame.Rect(self.panel.right - self.PAD - btn_w,
                            y + (self.ROW_H - 30) // 2, btn_w, 30)
            self.repay_btns.append(r)
            y += self.ROW_H

    def handle_click(self, pos: Tuple[int, int]) -> bool:
        if self.close_rect.collidepoint(pos):
            _close_dialog(self.game_state)
            return True
        if not self.panel.collidepoint(pos):
            _close_dialog(self.game_state)
            return True
        loans = self.game_state.game.depot.active_loans
        for i, r in enumerate(self.repay_btns):
            if i < len(loans) and r.collidepoint(pos):
                if self.game_state.game.depot.repay_loan(i, self.game_state):
                    self._build_repay_btns()
                return True
        return True

    def draw(self, alpha_scale: float = 1.0) -> None:
        if alpha_scale <= 0:
            return
        use_temp = alpha_scale < 1.0
        if use_temp:
            surf = pygame.Surface((self.panel.w + 10, self.panel.h + 10), pygame.SRCALPHA)
            off = (-self.panel.left, -self.panel.top)
        else:
            surf = self.screen
            off = (0, 0)

        self._draw_panel(surf, off)
        self._draw_close_btn(surf, off)
        self._draw_title(surf, off, "Bank — Repay Loans")

        mouse = pygame.mouse.get_pos()
        loans = self.game_state.game.depot.active_loans
        p = self.panel.move(*off)
        y = p.top + self.HDR + self.PAD_TOP
        btn_area_w = 80 + self.PAD  # width to reserve on right for repay button

        if not loans:
            self._text(surf, "No active loans.", p.centerx, y + 20, center=True)
        else:
            for i, loan in enumerate(loans):
                days_left = loan["duration_days"] - loan["days_elapsed"]
                remaining = loan.get("remaining_principal", loan.get("original_amount", loan.get("amount", 0.0)))
                daily_principal = loan.get("daily_principal", 0.0)
                daily_interest = loan.get("daily_interest", 0.0)
                settlement = loan.get("settlement_principal", 0.0)
                original = loan.get("original_amount", loan.get("amount", remaining))

                # Line 1: principal + date
                self._text(surf, f"{original:.0f} gold  ·  since {loan['start_date']}",
                           p.left + self.PAD, y + 4, color=DARK_BROWN)
                # Line 2: days left + daily payment
                self._text(surf,
                           f"Days left: {days_left}  |  Daily: {daily_principal:.2f} + {daily_interest:.2f} interest",
                           p.left + self.PAD, y + 26, color=BLACK)
                # Line 3: settlement
                self._text(surf, f"Settlement at end: {settlement:.2f}",
                           p.left + self.PAD, y + 48, color=DARK_GRAY)

                # Repay button
                if i < len(self.repay_btns):
                    btn_r = self.repay_btns[i].move(*off)
                    can_repay = self.game_state.game.depot.money >= loan["amount"]
                    border_col = DARK_GREEN if can_repay else DARK_RED
                    pygame.draw.rect(surf, SANDY_BROWN, btn_r, border_radius=4)
                    pygame.draw.rect(surf, border_col, btn_r, 2, border_radius=4)
                    if btn_r.collidepoint(mouse):
                        ov = pygame.Surface(btn_r.size, pygame.SRCALPHA)
                        ov.fill((0, 0, 0, 30))
                        surf.blit(ov, btn_r)
                    ts = self.body_font.render("Repay", True, BLACK)
                    surf.blit(ts, ts.get_rect(center=btn_r.center))

                # Divider
                if i < len(loans) - 1:
                    pygame.draw.line(surf, LIGHT_GRAY,
                                     (p.left + self.PAD, y + self.ROW_H - 2),
                                     (p.right - self.PAD, y + self.ROW_H - 2), 1)
                y += self.ROW_H

        if use_temp:
            surf.set_alpha(int(255 * alpha_scale))
            self.screen.blit(surf, (self.panel.left, self.panel.top))


# ---------------------------------------------------------------------------
# LoanOverviewDialog — read-only summary
# ---------------------------------------------------------------------------

class LoanOverviewDialog(_BaseDialog):
    """Read-only overview of all active loans."""

    W = 520
    ROW_H = 76   # 3 lines × 22px + 10px padding

    def __init__(self, screen: pygame.Surface, game_state: 'GameState') -> None:
        loans = game_state.game.depot.active_loans
        n = max(1, len(loans))
        h = self.HDR + self.PAD + n * self.ROW_H + self.PAD + 56 + self.PAD
        h = max(200, min(h, 520))
        super().__init__(screen, game_state, self.W, h)

    def draw(self, alpha_scale: float = 1.0) -> None:
        if alpha_scale <= 0:
            return
        use_temp = alpha_scale < 1.0
        if use_temp:
            surf = pygame.Surface((self.panel.w + 10, self.panel.h + 10), pygame.SRCALPHA)
            off = (-self.panel.left, -self.panel.top)
        else:
            surf = self.screen
            off = (0, 0)

        self._draw_panel(surf, off)
        self._draw_close_btn(surf, off)
        self._draw_title(surf, off, "Bank — Loan Overview")

        loans = self.game_state.game.depot.active_loans
        p = self.panel.move(*off)
        y = p.top + self.HDR + self.PAD

        if not loans:
            self._text(surf, "No active loans.", p.centerx, y + 20, center=True)
        else:
            total_principal = 0.0
            total_upcoming = 0.0
            for i, loan in enumerate(loans):
                original = loan.get("original_amount", loan.get("amount", 0.0))
                remaining = loan.get("remaining_principal", original)
                total_principal += remaining
                days_left = loan["duration_days"] - loan["days_elapsed"]
                daily_principal = loan.get("daily_principal", 0.0)
                daily_interest = loan.get("daily_interest", 0.0)
                settlement = loan.get("settlement_principal", 0.0)
                upcoming_interest = daily_interest * days_left
                total_upcoming += upcoming_interest
                daily_total = daily_principal + daily_interest

                # Line 1: original principal + date
                self._text(surf, f"Loan {i + 1}:  {original:.0f} gold  ·  since {loan['start_date']}",
                           p.left + self.PAD, y, color=DARK_BROWN)
                # Line 2: days + daily payment breakdown
                self._text(surf,
                           f"  Days left: {days_left}  |  Daily: {daily_total:.2f}  ({daily_principal:.2f} + {daily_interest:.2f})",
                           p.left + self.PAD, y + 22, color=BLACK)
                # Line 3: settlement + remaining interest
                self._text(surf, f"  Settlement: {settlement:.2f}  |  Interest remaining: {upcoming_interest:.2f}",
                           p.left + self.PAD, y + 44, color=DARK_RED)

                if i < len(loans) - 1:
                    pygame.draw.line(surf, LIGHT_GRAY,
                                     (p.left + self.PAD, y + self.ROW_H - 4),
                                     (p.right - self.PAD, y + self.ROW_H - 4), 1)
                y += self.ROW_H

            # Footer totals
            pygame.draw.line(surf, DARK_BROWN, (p.left + self.PAD, y + 4), (p.right - self.PAD, y + 4), 2)
            y += 12
            self._text(surf, f"Total remaining principal: {total_principal:.0f}",
                       p.left + self.PAD, y, color=DARK_BROWN)
            y += 24
            self._text(surf, f"Total interest still to pay: {total_upcoming:.2f}",
                       p.left + self.PAD, y, color=DARK_RED)

        if use_temp:
            surf.set_alpha(int(255 * alpha_scale))
            self.screen.blit(surf, (self.panel.left, self.panel.top))
