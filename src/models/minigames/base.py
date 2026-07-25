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


def score_to_coins(score: int, max_score: int) -> float:
    """Non-linear payout curve shared by all minigames.

    Poor skill earns little, mastery earns up to 20 coins. Returns cent
    precision (2 decimals) rather than rounding down to whole coins.
    """
    if max_score == 0:
        return 0.0
    ratio = max(0.0, min(1.0, score / max_score))
    return round(20 * ratio ** 2.5, 2)


def score_to_display(score: int, max_score: int) -> int:
    """Displayed score, reshaped onto the same curve as ``score_to_coins``.

    The raw score is a plain linear sum of per-swing hit points, but the
    payout it earns is not — near-perfect play is worth disproportionately
    more coin than the raw score gap suggests (e.g. 110/150 pays far more
    than 100/150). Showing the raw score alongside that payout reads as
    unintuitive, so the on-screen score is passed through the identical
    curve purely for display: it does not affect scoring, highscores, or
    payout, which all keep using the real linear score.
    """
    if max_score == 0:
        return 0
    ratio = max(0.0, min(1.0, score / max_score))
    return round(max_score * ratio ** 2.5)
