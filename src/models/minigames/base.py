"""Shared contract and payout helper for minigames that earn early-game income.

A minigame is a full-screen overlay stored on ``game_state.minigame``, following
the same lifecycle already used by ``game_state.contract_acquisition``:

- The launcher pauses the sim (``previous_time_level`` / ``time_level = 1``) and
  assigns the instance to ``game_state.minigame``.
- Each frame, ``Game.run()`` calls ``update(delta_time)`` then ``draw()`` while
  ``self.active`` is True.
- ``EventHandler`` routes every input event to ``handle_event()`` first and
  swallows it, so the minigame has exclusive input focus.
- Setting ``self.active = False`` tells the main loop to drop the reference and
  restore the previous simulation speed.

Additional minigames (2-4 are planned) should subclass ``MinigameOverlay`` and
book their payout through ``Depot.book_labor_income`` using ``score_to_coins``
for a consistent risk/reward curve across all of them.
"""

import math
from typing import Any


class MinigameOverlay:
    """Base class documenting the lifecycle contract for minigame overlays."""

    active: bool = True

    def update(self, delta_time: float) -> None:
        raise NotImplementedError

    def handle_event(self, event: Any) -> None:
        raise NotImplementedError

    def draw(self) -> None:
        raise NotImplementedError


#: What a perfect session (the score its minigame calls its max) pays
COINS_AT_MAX = 20.0
#: Beyond that score the pay grows only slowly, by the logarithm of how far beyond it:
#: COINS_BEYOND_SCALE * ln(1 + COINS_BEYOND_RATE * (ratio - 1)), so a tenth more pays
#: about 0.7 coins more, half as much again about 2.2 and twice the max about 3.2
COINS_BEYOND_SCALE = 2.0
COINS_BEYOND_RATE = 4.0


def score_to_coins(score: float, max_score: float) -> float:
    """Non-linear payout curve shared by all minigames.

    Poor skill earns little, mastery COINS_AT_MAX (20) at the minigame's max
    score; a score above it (streak bonuses, extra swings) earns more, but
    ever more slowly. Returns cent precision (2 decimals) rather than rounding
    down to whole coins.
    """
    if max_score == 0:
        return 0.0
    ratio = max(0.0, score / max_score)
    if ratio <= 1.0:
        return round(COINS_AT_MAX * ratio ** 2.5, 2)
    return round(COINS_AT_MAX + COINS_BEYOND_SCALE * math.log(1 + COINS_BEYOND_RATE * (ratio - 1)), 2)


def score_to_display(score: float, max_score: float) -> int:
    """Displayed score, reshaped onto the same curve as ``score_to_coins``.

    The raw score is a plain linear sum of per-swing hit points, but the
    payout it earns is not — near-perfect play is worth disproportionately
    more coin than the raw score gap suggests (e.g. 110/150 pays far more
    than 100/150). Showing the raw score alongside that payout reads as
    unintuitive, so the on-screen score is passed through the identical
    curve purely for display: it does not affect scoring, highscores, or
    payout, which all keep using the real linear score.

    The score is not capped at the max: above it the displayed score goes on
    rising in a straight line, as steeply as the curve meets it there (2.5
    displayed points for each raw one), so it neither jumps nor stalls.
    """
    if max_score == 0:
        return 0
    ratio = max(0.0, score / max_score)
    if ratio <= 1.0:
        return round(max_score * ratio ** 2.5)
    return round(max_score * (1.0 + 2.5 * (ratio - 1.0)))
