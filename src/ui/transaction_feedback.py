from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..game_state import GameState


def on_money_spent(game_state: "GameState", amount: float = 0.0) -> None:
    """Trigger feedback for any action where the player spends money."""
    if game_state.game:
        game_state.game.play_sound("falling_coins_buy")


def on_money_received(game_state: "GameState", amount: float = 0.0) -> None:
    """Trigger feedback for any action where the player receives money."""
    if game_state.game:
        game_state.game.play_sound("falling_coins_sell")
