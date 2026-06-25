"""Loan dialogs for the Bank building.

Two dialogs:
  LoanDialog            — take out a new loan
  LoanManagementDialog  — overview of active loans with inline repay buttons
"""

import pygame
import os
from typing import Optional, Tuple, List, TYPE_CHECKING
from ..transaction_feedback import on_money_received
from ...config.colors import SANDY_BROWN, DARK_BROWN, BLACK, WHITE, DARK_GREEN, DARK_RED, DARK_GRAY, DARK_ORANGE, WHEAT
from ..ui_utils import draw_9slice
from ...config.constants import (
    LOAN_BASE_RATES, LOAN_DURATION_FACTORS, LOAN_EQUITY_RATIOS,
    LOAN_MIN_AMOUNT, LOAN_MIN_DAILY_PCT, LOAN_SETTLEMENT_RATE_PENALTY,
    FONTS_PATH, SCREEN_WIDTH, SCREEN_HEIGHT, SIDEBAR_WIDTH,
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

    Returns: (daily_principal, daily_interest, settlement_principal, total_interest, total_payback, yearly_rate_pct)
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
        return 0.0, 0.0, 0.0, 0.0, 0.0, 0.0

    repayment_pct = max(float(LOAN_MIN_DAILY_PCT), min(100.0, repayment_pct))

    # Daily principal: share of total principal spread across the term
    daily_principal = round(original_amount * (repayment_pct / 100.0) / duration_days, 2)
    # Settlement: whatever principal is left after all daily repayments
    settlement_principal = round(max(0.0, original_amount - daily_principal * duration_days), 2)

    # Settlement penalty: back-loading repayment increases the interest rate.
    # At 100% daily repayment → no penalty (factor = 1.0).
    # At LOAN_MIN_DAILY_PCT daily repayment → maximum penalty (factor = 1 + LOAN_SETTLEMENT_RATE_PENALTY).
    settlement_ratio = (100.0 - repayment_pct) / (100.0 - LOAN_MIN_DAILY_PCT)
    settlement_factor = 1.0 + settlement_ratio * LOAN_SETTLEMENT_RATE_PENALTY

    # Fixed daily interest on the original amount (simple interest with duration and settlement factors)
    raw_daily_interest = original_amount * base_rate / 365 * dur_factor * settlement_factor
    daily_interest = max(0.01, round(raw_daily_interest, 2))

    total_interest = round(daily_interest * duration_days, 2)
    total_payback = round(original_amount + total_interest, 2)
    yearly_rate_pct = round(base_rate * dur_factor * settlement_factor * 100, 1)

    return daily_principal, daily_interest, settlement_principal, total_interest, total_payback, yearly_rate_pct


def _close_dialog(game_state: 'GameState') -> None:
    game_state.menu_fade_window = game_state.info_window
    game_state.menu_fade_timer = game_state.menu_fade_duration
    game_state.info_window = None
    game_state.active_house_menu = None


def _load_fonts():
    try:
        title_font = pygame.font.Font(os.path.join(FONTS_PATH, "Medici Text.ttf"), 34)
        body_font = pygame.font.Font(os.path.join(FONTS_PATH, "Augusta.ttf"), 20)
    except Exception:
        title_font = pygame.font.SysFont("arial", 28)
        body_font = pygame.font.SysFont("arial", 18)
    return title_font, body_font


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------

def open_loan_dialog(game_state: 'GameState') -> None:
    depot = game_state.game.depot
    wealth = depot.wealth[-1] if depot.wealth else depot.money
    active_debt = sum(
        loan.get("remaining_principal", loan.get("original_amount", loan.get("amount", 0.0)))
        for loan in depot.active_loans
    )
    game_state.info_window = LoanDialog(game_state.screen, game_state, wealth, active_debt)
    # Keep active_house_menu set to the bank so the distance check in map_view closes this dialog


def open_loan_management_dialog(game_state: 'GameState') -> None:
    game_state.info_window = LoanManagementDialog(game_state.screen, game_state)
    # Keep active_house_menu set to the bank so the distance check in map_view closes this dialog


# Aliases kept so any future callers don't break
open_repay_dialog = open_loan_management_dialog
open_loan_overview_dialog = open_loan_management_dialog


# ---------------------------------------------------------------------------
# Shared base: centred panel with a close [X] button
# ---------------------------------------------------------------------------

class _BaseDialog:
    PAD = 14
    HDR = 48  # taller header to give the larger title font more breathing room
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
        game = self.game_state.game
        if game and hasattr(game, 'pic_info_window'):
            draw_9slice(surf, game.pic_info_window, r)
        else:
            pygame.draw.rect(surf, SANDY_BROWN, r)
            pygame.draw.rect(surf, DARK_BROWN, r, 3)

    def _draw_close_btn(self, surf: pygame.Surface, off: Tuple[int, int]) -> None:
        r = self.close_rect.move(*off)
        pygame.draw.rect(surf, DARK_BROWN, r)
        mg = 5
        pygame.draw.line(surf, WHITE, (r.left + mg, r.top + mg), (r.right - mg, r.bottom - mg), 2)
        pygame.draw.line(surf, WHITE, (r.left + mg, r.bottom - mg), (r.right - mg, r.top + mg), 2)

    def _draw_title(self, surf: pygame.Surface, off: Tuple[int, int], text: str) -> None:
        ts = self.title_font.render(text, True, DARK_BROWN)
        p = self.panel.move(*off)
        tr = ts.get_rect(centerx=p.centerx, top=p.top + 10)
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
        pygame.draw.rect(surf, bg, rect)
        pygame.draw.rect(surf, border, rect, 2)
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

    W, H = 460, 486  # +14 for taller HDR (34 → 48)

    def __init__(self, screen: pygame.Surface, game_state: 'GameState', wealth: float, active_debt: float = 0.0) -> None:
        super().__init__(screen, game_state, self.W, self.H)
        self.house = game_state.active_house_menu  # enables distance-based close in map_view
        self.wealth = wealth
        self.active_debt = active_debt
        # Max new loan = total borrowing ceiling minus what's already owed
        self.max_loan = max(0, _calc_max_loan(wealth) - int(active_debt))
        self.min_loan = LOAN_MIN_AMOUNT

        # Amount slider
        # Layout mirrors draw(): HDR(48) + PAD(14) + info_line1(22) + info_line2(22) + amount_label(22) = 128
        self.amount = min(self.max_loan, max(self.min_loan, self.max_loan // 2))
        asl_y = self.panel.top + self.HDR + self.PAD + 22 + 22 + 22
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
            daily_principal, daily_interest, settlement_principal, _, _, _ = _calc_loan_params(
                self.amount, duration, self.repayment_pct, self.wealth
            )
            start_str = self.game_state.date.strftime("%d.%m.%Y")
            self.game_state.game.depot.take_loan(
                self.amount, daily_principal, daily_interest, settlement_principal, duration, start_str
            )
            on_money_received(self.game_state, self.amount)
            self.game_state.log_event(
                "LOAN",
                f"Loan taken: {self.amount:.0f}g over {duration} days"
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
        self._draw_title(surf, off, "Take Out a Loan")

        mouse = pygame.mouse.get_pos()
        p = self.panel.move(*off)
        cx = p.centerx
        y = p.top + self.HDR + self.PAD

        # Wealth / max loan info (two lines to avoid overflow)
        self._text(surf, f"Your Wealth: {self.wealth:.0f}  |  Max New Loan: {self.max_loan}", cx, y,
                   color=DARK_BROWN, center=True)
        y += 22
        if self.active_debt > 0:
            self._text(surf, f"Active Debt: {self.active_debt:.0f}  (reducing available credit)", cx, y,
                       color=DARK_RED, center=True)
        y += 22

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

        # Repayment slider label (show interest penalty for back-loading)
        settlement_pct = 100 - int(self.repayment_pct)
        settlement_ratio = (100.0 - self.repayment_pct) / (100.0 - LOAN_MIN_DAILY_PCT)
        penalty_pct = round(settlement_ratio * LOAN_SETTLEMENT_RATE_PENALTY * 100)
        penalty_str = f"  (+{penalty_pct}% rate)" if penalty_pct > 0 else ""
        self._text(surf,
                   f"Daily: {int(self.repayment_pct)}%  ·  Settlement: {settlement_pct}%{penalty_str}",
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
        daily_principal, daily_interest, settlement_principal, total_interest, total_payback, yearly_rate_pct = \
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
        y += 22
        self._text(surf, f"Effective yearly interest rate: {yearly_rate_pct:.1f}%",
                   cx, y, color=DARK_RED, center=True)

        # Confirm button
        self._draw_btn(surf, self.confirm_btn.move(*off), "Confirm Loan", mouse)

        if use_temp:
            surf.set_alpha(int(255 * alpha_scale))
            self.screen.blit(surf, (self.panel.left, self.panel.top))


# ---------------------------------------------------------------------------
# LoanManagementDialog — overview + repay (replaces RepayDialog + LoanOverviewDialog)
# ---------------------------------------------------------------------------

class LoanManagementDialog(_BaseDialog):
    """Unified loan overview and repayment dialog.

    Each loan card shows:
      - Identity header (amount, start date, progress)
      - Two decisive numbers: "Close now" vs "Let it run"
      - Daily breakdown and days remaining
      - Repay Now button (green border if affordable, red if not)
    Footer shows totals and interest savings across all loans.
    """

    W = 640
    ROW_H = 130   # header(22) + decisive(26) + detail1(22) + detail2(22) + btn(26) + divider(12)
    FOOTER_H = 82  # separator(16) + 3 lines at 22px each
    BTN_W = 104
    MAX_VISIBLE_ROWS = 4
    SCROLLBAR_W = 6   # thin bar, inset from the right border

    def __init__(self, screen: pygame.Surface, game_state: 'GameState') -> None:
        loans = game_state.game.depot.active_loans
        n = max(1, len(loans))
        visible = min(n, self.MAX_VISIBLE_ROWS)
        h = self.HDR + self.PAD + visible * self.ROW_H + self.PAD + self.FOOTER_H + self.PAD
        h = max(200, min(h, SCREEN_HEIGHT - 60))
        super().__init__(screen, game_state, self.W, h)
        self.house = game_state.active_house_menu  # enables distance-based close in map_view
        self.scroll_offset = 0  # pixels scrolled in the loan list area
        self._build_repay_btns()

    # -- scroll area geometry --------------------------------------------------

    def _scroll_area_rect(self) -> pygame.Rect:
        """The clipped area that shows loan rows (excludes header, footer, scrollbar)."""
        visible_h = min(len(self.game_state.game.depot.active_loans),
                        self.MAX_VISIBLE_ROWS) * self.ROW_H
        # Leave 4px gap on the right for the scrollbar + its 4px inset from border
        return pygame.Rect(
            self.panel.left,
            self.panel.top + self.HDR + self.PAD,
            self.panel.width - self.SCROLLBAR_W - 8,
            visible_h,
        )

    def _total_content_h(self) -> int:
        return len(self.game_state.game.depot.active_loans) * self.ROW_H

    def _max_scroll(self) -> int:
        return max(0, self._total_content_h() - self._scroll_area_rect().height)

    # -- repay button positions (in panel coords, scroll-adjusted at draw time) -

    def _build_repay_btns(self) -> None:
        loans = self.game_state.game.depot.active_loans
        self.repay_btns: List[pygame.Rect] = []
        for i in range(len(loans)):
            # Stored at un-scrolled y; draw() shifts by scroll_offset
            y_base = self.panel.top + self.HDR + self.PAD + i * self.ROW_H
            r = pygame.Rect(
                self.panel.right - self.SCROLLBAR_W - 2 - self.PAD - self.BTN_W,
                y_base + 22, self.BTN_W, 26,
            )
            self.repay_btns.append(r)

    # -- events ----------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEWHEEL:
            self.scroll_offset = max(0, min(self._max_scroll(),
                                            self.scroll_offset - event.y * 30))

    def handle_click(self, pos: Tuple[int, int]) -> bool:
        if self.close_rect.collidepoint(pos):
            _close_dialog(self.game_state)
            return True
        if not self.panel.collidepoint(pos):
            _close_dialog(self.game_state)
            return True
        loans = self.game_state.game.depot.active_loans
        scroll_area = self._scroll_area_rect()
        for i, r in enumerate(self.repay_btns):
            # Adjust stored rect for current scroll
            scrolled_r = r.move(0, -self.scroll_offset)
            if (i < len(loans) and scrolled_r.collidepoint(pos)
                    and scroll_area.collidepoint(pos)):
                if self.game_state.game.depot.repay_loan(i, self.game_state):
                    self._build_repay_btns()
                    self.scroll_offset = min(self.scroll_offset, self._max_scroll())
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
        self._draw_title(surf, off, "Manage Loans")

        mouse = pygame.mouse.get_pos()
        loans = self.game_state.game.depot.active_loans
        p = self.panel.move(*off)

        if not loans:
            self._text(surf, "No active loans.", p.centerx,
                       p.top + self.HDR + self.PAD + 30, center=True)
        else:
            # -- Pre-compute footer totals (all loans, not just visible) --------
            total_close_now = 0.0
            total_let_run = 0.0
            total_interest_saved = 0.0
            for loan in loans:
                original = loan.get("original_amount", loan.get("amount", 0.0))
                close_now = loan.get("remaining_principal", original)
                days_left = loan["duration_days"] - loan["days_elapsed"]
                future_interest = loan.get("daily_interest", 0.0) * days_left
                total_close_now += close_now
                total_let_run += close_now + future_interest
                total_interest_saved += future_interest

            # -- Scroll area clipping -------------------------------------------
            scroll_area = self._scroll_area_rect().move(*off)
            old_clip = surf.get_clip()
            surf.set_clip(scroll_area)

            content_y = scroll_area.top - self.scroll_offset  # top of first row

            for i, loan in enumerate(loans):
                y = content_y + i * self.ROW_H
                # Skip rows entirely outside the clip
                if y + self.ROW_H < scroll_area.top or y > scroll_area.bottom:
                    continue

                original = loan.get("original_amount", loan.get("amount", 0.0))
                close_now = loan.get("remaining_principal", original)
                days_left = loan["duration_days"] - loan["days_elapsed"]
                daily_principal = loan.get("daily_principal", 0.0)
                daily_interest = loan.get("daily_interest", 0.0)
                settlement = loan.get("settlement_principal", 0.0)
                future_interest = daily_interest * days_left
                let_run = close_now + future_interest
                daily_total = daily_principal + daily_interest

                lx = scroll_area.left + self.PAD
                rx = scroll_area.left + 320

                # -- Header --
                progress = f"{loan['days_elapsed']}/{loan['duration_days']} days"
                self._text(surf,
                           f"Loan {i+1}  ·  {original:.0f} gold  ·  since {loan['start_date']}  ·  {progress}",
                           lx, y, color=DARK_BROWN)

                # -- Decisive numbers --
                self._text(surf, "Close now:", lx, y + 26, color=BLACK)
                self._text(surf, f"{close_now:.2f} gold", lx + 92, y + 26, color=DARK_RED)
                self._text(surf, "Let it run:", rx, y + 26, color=BLACK)
                self._text(surf, f"{let_run:.2f} gold", rx + 92, y + 26, color=DARK_ORANGE)

                # -- Detail line 1 --
                self._text(surf,
                           f"Daily: {daily_principal:.2f} principal + {daily_interest:.2f} interest"
                           f" = {daily_total:.2f} total  ·  {days_left} days left",
                           lx, y + 52, color=DARK_GRAY)

                # -- Detail line 2 --
                self._text(surf,
                           f"Settlement at end: {settlement:.2f}  ·  Future interest: {future_interest:.2f}",
                           lx, y + 74, color=DARK_GRAY)

                # -- Repay button --
                if i < len(self.repay_btns):
                    btn_r = self.repay_btns[i].move(*off).move(0, -self.scroll_offset)
                    can_repay = self.game_state.game.depot.money >= close_now
                    border_col = DARK_GREEN if can_repay else DARK_RED
                    pygame.draw.rect(surf, SANDY_BROWN, btn_r, border_radius=4)
                    pygame.draw.rect(surf, border_col, btn_r, 2, border_radius=4)
                    if btn_r.collidepoint(mouse) and can_repay:
                        ov = pygame.Surface(btn_r.size, pygame.SRCALPHA)
                        ov.fill((0, 0, 0, 30))
                        surf.blit(ov, btn_r)
                    ts = self.body_font.render("Repay Now" if can_repay else "Can't Afford", True, BLACK)
                    surf.blit(ts, ts.get_rect(center=btn_r.center))

                # -- Row divider (brown) --
                if i < len(loans) - 1:
                    div_y = y + self.ROW_H - 6
                    pygame.draw.line(surf, DARK_BROWN,
                                     (scroll_area.left + self.PAD, div_y),
                                     (scroll_area.right - self.PAD, div_y), 1)

            surf.set_clip(old_clip)

            # -- Scrollbar (only when needed) -----------------------------------
            max_scroll = self._max_scroll()
            if max_scroll > 0:
                # Inset 4px from the right panel border so it stays inside
                sb_x = p.right - 4 - self.SCROLLBAR_W
                sb_rect = pygame.Rect(sb_x, scroll_area.top, self.SCROLLBAR_W, scroll_area.height)
                pygame.draw.rect(surf, WHEAT, sb_rect, border_radius=3)
                handle_h = max(24, int(scroll_area.height * scroll_area.height / self._total_content_h()))
                handle_y = sb_rect.top + int(self.scroll_offset / max_scroll * (sb_rect.height - handle_h))
                pygame.draw.rect(surf, DARK_BROWN,
                                 pygame.Rect(sb_x, handle_y, self.SCROLLBAR_W, handle_h),
                                 border_radius=3)

            # -- Footer (black separator, always fully visible) -----------------
            footer_top = p.top + self.panel.height - self.FOOTER_H - self.PAD
            pygame.draw.line(surf, BLACK,
                             (p.left + self.PAD, footer_top),
                             (p.right - self.PAD, footer_top), 2)
            y = footer_top + 14
            val_x = p.right - self.PAD
            self._text(surf, "Total to close all now:", p.left + self.PAD, y, color=BLACK)
            val = self.body_font.render(f"{total_close_now:.2f} gold", True, DARK_RED)
            surf.blit(val, (val_x - val.get_width(), y))
            y += 22
            self._text(surf, "Total if all run to term:", p.left + self.PAD, y, color=BLACK)
            val = self.body_font.render(f"{total_let_run:.2f} gold", True, DARK_ORANGE)
            surf.blit(val, (val_x - val.get_width(), y))
            y += 22
            self._text(surf, "Interest saved by closing now:", p.left + self.PAD, y, color=BLACK)
            val = self.body_font.render(f"{total_interest_saved:.2f} gold", True, DARK_GREEN)
            surf.blit(val, (val_x - val.get_width(), y))

        if use_temp:
            surf.set_alpha(int(255 * alpha_scale))
            self.screen.blit(surf, (self.panel.left, self.panel.top))
