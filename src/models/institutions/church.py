from ..house import House
from typing import TYPE_CHECKING
import random
import pygame
from ...config.constants import CHURCH_FEAST_CATEGORY, CHURCH_FEASTS
from ...ui.transaction_feedback import on_money_donated, show_coin_popup

if TYPE_CHECKING:
    from ...game_state import GameState

class Church(House):
    """Represents a church institution in the game with donation functionality."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.treasury = 0

    def open_donation_menu(self, game_state: 'GameState', click_pos) -> None:
        """Opens the donation menu replacing the current menu.
        
        Args:
            game_state: The current game state.
            click_pos: The screen position where the user clicked.
        """
        # Local import to avoid circular dependency
        from ...ui.helper_modules.donation_menu import DonationMenu
        
        def donation_callback(amount: int):
            if not hasattr(game_state.game, 'depot'):
                return

            depot = game_state.game.depot
            
            if depot.book_donation(amount, category="Church Donations"):
                self.treasury += amount
                on_money_donated(game_state, amount)
                gain = game_state.game.merchant_rank.record_gift(amount)
                game_state.log_event("DONATION", f"Donated {amount:.0f}g to the Church (reputation +{gain:.2f})")
                # Close menu on success
                game_state.info_window = None
                game_state.active_house_menu = None
            else:
                # Show warning and keep menu open
                if hasattr(game_state, 'show_warning'):
                    game_state.show_warning("Not enough money!")
        
        # Replace current info window with new one
        game_state.info_window = DonationMenu(
            game_state.screen,
            self,
            game_state,
            callback=donation_callback,
            category="Church Donations"
        )
        game_state.active_house_menu = self

    def open_feast_menu(self, game_state: 'GameState') -> None:
        """Opens the window for giving goods for a meal for the poor, replacing the house menu."""
        from ...ui.helper_modules.feast_menu import FeastMenu

        game_state.info_window = FeastMenu(game_state.screen, game_state, self)
        game_state.active_house_menu = self

    def donate_feast(self, game_state: 'GameState', index: int) -> bool:
        """Give the goods for the feast CHURCH_FEASTS[index] out of the player's stock.

        Booked as a donation at today's market price, which also earns its reputation;
        if the stock falls short, a warning names what is missing and nothing is taken.

        Returns:
            True if the goods were given.
        """
        game = game_state.game
        name, needed = CHURCH_FEASTS[index]
        missing = game.depot.missing_goods(needed)
        if missing:
            short = ", ".join(f"{quantity} {good}" for good, quantity in missing.items())
            game_state.show_warning(f"Not enough goods in stock for the {name}: {short} missing.")
            return False

        value = game.depot.donate_goods(needed, game.goods, CHURCH_FEAST_CATEGORY)
        game.play_sound(random.choice(("sack_drop_1", "sack_drop_2", "sack_drop_3")))
        show_coin_popup(game_state, value, is_spent=True)
        gain = game.merchant_rank.record_gift(value)
        given = ", ".join(f"{quantity} {good}" for good, quantity in needed.items())
        game_state.log_event(
            "DONATION",
            f"Gave {given} to the Church for a {name} (worth {value:.0f}g, reputation +{gain:.2f})",
        )
        return True
