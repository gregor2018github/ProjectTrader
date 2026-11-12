"""The sheet showing a session of the council the player had a part in (`Game._show_next_notice`).

The vote is played out as it went in the hall: the candidates with their arms side by
side, then the voters one after another, each going to the one he voted for or, if he
was not there, greyed with what kept him; the counts rise with them. Then the verdict,
what else came of it (a purse talked of, a grudge), and the council's other
business in a line. A click before the last vote is in shows the rest at once; the
button comes only then.
"""

import os
from typing import List, Optional, Tuple, TYPE_CHECKING

import pygame

from .council_window import FAINT_INK, GOOD_INK, arms_of, wrap
from .info_window import _dim_overlay
from .loan_dialog import _BaseDialog
from .records_window import _leaf
from ..heraldry import draw_arms
from ...config.colors import GOLD
from ...config.constants import FONTS_PATH
from ...models.council import Council, PLAYER, Result, SessionReport
from ...models.minigames.tutorial_sheet import (
    BUTTON_SIZE, INK, RUBRIC, draw_button, framed_sheet, inked,
)
from ...models.minigames.woodhacking import draw_divider
from ...sim.calendar import format_long

if TYPE_CHECKING:
    from ...game_state import GameState

BUTTON_LABEL = "Onward"
FIRST_VOTE_S = 0.9               # how long after opening the first vote comes
VOTE_EVERY_S = 0.75              # and each one after it
VERDICT_AFTER_S = 0.7            # the pause between the last vote and the verdict

W = 860
MARGIN = 44
TITLE_Y, DIVIDER_Y = 50, 84
DATE_Y, SEAT_Y = 108, 140
CANDIDATES_TOP = 170
CANDIDATE_H = 132
VOTES_TOP = CANDIDATES_TOP + CANDIDATE_H + 14
VOTE_ROW = 34
VERDICT_H = 96
NOTE_H = 24
BUTTON_GAP, FOOT = 16, 34


def verdict_text(council: Council, result: Result) -> Tuple[str, bool]:
    """The verdict in a line, and whether it is good news for the player."""
    office = council.offices[result.office].name
    held = result.holder_before == PLAYER
    if result.forfeited:
        return (f"Your seat as {office} is forfeit" if held else "Your name was struck from the list"), False
    if result.winner == PLAYER:
        return (f"You keep your seat as {office}" if held else f"You are elected {office}"), True
    winner = council.name_of(result.winner)
    if held:
        return f"{winner} takes your seat", False
    return (f"{winner} keeps the seat" if result.winner == result.holder_before else f"{winner} wins the seat"), False


def other_business(council: Council, result: Result) -> str:
    office = council.offices[result.office].name
    winner = council.name_of(result.winner)
    if len(result.candidates) == 1:
        return f"{winner} was confirmed as {office}, unopposed."
    loser = next(council.name_of(c) for c in result.candidates if c != result.winner)
    if result.winner == result.holder_before:
        return f"{winner} kept the seat of {office} against {loser}."
    return f"{winner} took the seat of {office} from {loser}."


class SessionWindow(_BaseDialog):
    def __init__(self, screen: pygame.Surface, game_state: 'GameState', report: SessionReport) -> None:
        self.council: Council = game_state.game.council
        self.report = report
        self.result: Result = next(result for result in report.results if result.concerns_player)
        self.others: List[Result] = [result for result in report.results if result is not self.result]
        self.verdict, self.good = verdict_text(self.council, self.result)

        self.small_font = self._font("Augusta.ttf", 17)
        self.note_lines: List[str] = []
        for note in self.result.notes:
            self.note_lines += wrap(note, self.small_font, W - 2 * MARGIN - 40)
        self.other_lines: List[str] = []
        for result in self.others:
            self.other_lines += wrap("Also decided: " + other_business(self.council, result), self.small_font,
                                     W - 2 * MARGIN - 40)

        self.votes_h = max(1, len(self.result.votes)) * VOTE_ROW + 16
        self.verdict_top = VOTES_TOP + self.votes_h + 10
        self.notes_top = self.verdict_top + VERDICT_H
        notes_h = (len(self.note_lines) + len(self.other_lines)) * NOTE_H
        height = self.notes_top + notes_h + BUTTON_GAP + BUTTON_SIZE[1] + FOOT
        super().__init__(screen, game_state, W, height)

        self.h1_font = self._font("Medici Text.ttf", 46)
        self.name_font = self._font("Medici Text.ttf", 26)
        self.count_font = self._font("Medici Text.ttf", 44)
        self.verdict_font = self._font("Medici Text.ttf", 36)
        self.button_rect = pygame.Rect((0, 0), BUTTON_SIZE)
        self.button_rect.midtop = (self.panel.centerx, self.panel.top + self.notes_top + notes_h + BUTTON_GAP)
        self._sheet: Optional[pygame.Surface] = None
        self._opened_at: Optional[int] = None
        self._skipped = False

    @staticmethod
    def _font(name: str, size: int) -> pygame.font.Font:
        try:
            return pygame.font.Font(os.path.join(FONTS_PATH, name), size)
        except Exception:
            return pygame.font.SysFont("arial", size - 4)

    # -- how far the vote has got ------------------------------------------

    def _seconds_open(self) -> float:
        if self._opened_at is None:
            return 0.0
        return (pygame.time.get_ticks() - self._opened_at) / 1000.0

    @property
    def reveal_ends_s(self) -> float:
        """When the verdict shows, in seconds after opening."""
        votes = len(self.result.votes)
        return (FIRST_VOTE_S + (votes - 1) * VOTE_EVERY_S + VERDICT_AFTER_S) if votes else FIRST_VOTE_S

    def votes_shown(self, seconds: Optional[float] = None) -> int:
        if self._skipped:
            return len(self.result.votes)
        seconds = self._seconds_open() if seconds is None else seconds
        if seconds < FIRST_VOTE_S:
            return 0
        return min(len(self.result.votes), 1 + int((seconds - FIRST_VOTE_S) / VOTE_EVERY_S))

    @property
    def finished(self) -> bool:
        return self._skipped or self._seconds_open() >= self.reveal_ends_s

    def skip(self) -> None:
        self._skipped = True

    # -- input -------------------------------------------------------------

    def handle_click(self, pos: Tuple[int, int]) -> Optional[str]:
        if not self.finished:
            self.skip()
            return None
        return "OK" if self.button_rect.collidepoint(pos) else None

    def handle_key(self, event: pygame.event.Event) -> Optional[str]:
        if event.key not in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE, pygame.K_ESCAPE):
            return None
        if not self.finished:
            self.skip()
            return None
        return "OK"

    # -- the sheet ---------------------------------------------------------

    def _centred(self, surf: pygame.Surface, label: pygame.Surface, y: int, x: int = W // 2) -> None:
        surf.blit(label, label.get_rect(center=(x, y)))

    def candidate_x(self, candidate: str) -> int:
        """The middle of a candidate's column on the sheet."""
        candidates = self.result.candidates
        step = (W - 2 * MARGIN) / len(candidates)
        return round(MARGIN + step * (candidates.index(candidate) + 0.5))

    def _build_sheet(self) -> pygame.Surface:
        """All that does not move: the title, the seat, the candidates and the leaf the votes fall on."""
        council = self.council
        sheet = framed_sheet((W, self.panel.height))
        self._centred(sheet, inked("The Council Sits", self.h1_font, GOLD), TITLE_Y)
        draw_divider(sheet, (W // 2, DIVIDER_Y), 170)
        self._centred(sheet, self.body_font.render(format_long(self.report.date), True, FAINT_INK), DATE_Y)
        office = council.offices[self.result.office]
        self._centred(sheet, self.name_font.render(f"The vote on the seat of {office.name}", True, INK), SEAT_Y)

        for candidate in self.result.candidates:
            x = self.candidate_x(candidate)
            draw_arms(sheet, pygame.Rect(x - 32, CANDIDATES_TOP, 64, 76), arms_of(council, candidate))
            name = self.body_font.render(council.name_of(candidate), True, RUBRIC if candidate == PLAYER else INK)
            self._centred(sheet, name, CANDIDATES_TOP + 92, x)
            if candidate == self.result.holder_before:
                self._centred(sheet, self.small_font.render("holds the seat", True, FAINT_INK), CANDIDATES_TOP + 112, x)

        _leaf(sheet, pygame.Rect(MARGIN, VOTES_TOP, W - 2 * MARGIN, self.votes_h))
        if not self.result.votes:
            words = "No vote was taken." if self.result.forfeited else "Nobody stood against you: no vote was needed."
            self._centred(sheet, self.body_font.render(words, True, INK), VOTES_TOP + self.votes_h // 2)
        return sheet

    def _draw_votes(self, surf: pygame.Surface, top_left: Tuple[int, int], shown: int) -> None:
        """The votes cast so far, each under the candidate it went to, and the counts over them."""
        council = self.council
        ox, oy = top_left
        counts = {candidate: 0 for candidate in self.result.candidates}
        for index, vote in enumerate(self.result.votes[:shown]):
            y = oy + VOTES_TOP + 8 + index * VOTE_ROW + VOTE_ROW // 2
            arms = council.notables[vote.voter].arms
            if vote.choice is None:
                draw_arms(surf, pygame.Rect(ox + MARGIN + 16, y - 14, 23, 28), arms, lit=False)
                words = self.small_font.render(f"{council.name_of(vote.voter)} {vote.reason}", True, FAINT_INK)
                surf.blit(words, words.get_rect(midleft=(ox + MARGIN + 48, y)))
                continue
            counts[vote.choice] += 1
            x = ox + self.candidate_x(vote.choice)
            name = self.body_font.render(council.name_of(vote.voter), True,
                                         GOOD_INK if vote.choice == PLAYER else INK)
            left = x - 104
            draw_arms(surf, pygame.Rect(left, y - 14, 23, 28), arms)
            surf.blit(name, name.get_rect(midleft=(left + 32, y)))
        if self.result.votes:
            for candidate, count in counts.items():
                number = inked(str(count), self.count_font, GOLD)
                surf.blit(number, number.get_rect(center=(ox + self.candidate_x(candidate) + 78, oy + CANDIDATES_TOP + 40)))

    def _draw_verdict(self, surf: pygame.Surface, top_left: Tuple[int, int]) -> None:
        ox, oy = top_left
        centre = (ox + W // 2, oy + self.verdict_top + VERDICT_H // 2 - 8)
        label = inked(self.verdict, self.verdict_font, GOLD) if self.good else self.verdict_font.render(
            self.verdict, True, RUBRIC)
        surf.blit(label, label.get_rect(center=centre))
        draw_divider(surf, (centre[0], centre[1] + 32), 150)
        y = oy + self.notes_top + NOTE_H // 2
        for line in self.note_lines:
            words = self.small_font.render(line, True, RUBRIC)
            surf.blit(words, words.get_rect(center=(ox + W // 2, y)))
            y += NOTE_H
        for line in self.other_lines:
            words = self.small_font.render(line, True, FAINT_INK)
            surf.blit(words, words.get_rect(center=(ox + W // 2, y)))
            y += NOTE_H

    def draw(self, alpha_scale: float = 1.0) -> None:
        if self._sheet is None:
            self._sheet = self._build_sheet()
        if self._opened_at is None:
            self._opened_at = pygame.time.get_ticks()
        self.screen.blit(_dim_overlay(self.screen.get_size()), (0, 0))
        self._sheet.set_alpha(round(255 * alpha_scale))
        self.screen.blit(self._sheet, self.panel)
        if alpha_scale < 1.0:
            return
        self._draw_votes(self.screen, self.panel.topleft, self.votes_shown())
        if self.finished:
            self._draw_verdict(self.screen, self.panel.topleft)
            hovered = self.button_rect.collidepoint(pygame.mouse.get_pos())
            draw_button(self.screen, self.button_rect, BUTTON_LABEL, self.body_font, hovered)
