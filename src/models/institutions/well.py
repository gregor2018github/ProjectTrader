import random
from typing import TYPE_CHECKING

from ..house import House
from ...config.constants import SPLASH_VOLUME, COIN_THROW_COST

if TYPE_CHECKING:
    from ...game_state import GameState


class Well(House):
    """Represents a well on the map where the player can throw coins or rocks."""

    def throw_coin(self, game_state: 'GameState') -> None:
        """Deduct a coin from the player's money and play a splash sound.

        Shows a warning if the player cannot afford it.
        """
        depot = game_state.game.depot if game_state.game else None
        if depot is None:
            return

        if not depot.book_miscellaneous(COIN_THROW_COST):
            game_state.show_warning("Not enough money!")
            return
        self._play_splash(game_state)

        game_state.info_window = None
        game_state.active_house_menu = None

    def throw_rock(self, game_state: 'GameState') -> None:
        """Play a splash sound without any cost."""
        self._play_splash(game_state)

        game_state.info_window = None
        game_state.active_house_menu = None

    def _play_splash(self, game_state: 'GameState') -> None:
        """Play a random splash sound."""
        if not game_state.game:
            return
        splash_num = random.randint(1, 4)
        channel = game_state.game.play_sound(f"splash_{splash_num}")
        if channel:
            channel.set_volume(SPLASH_VOLUME)
