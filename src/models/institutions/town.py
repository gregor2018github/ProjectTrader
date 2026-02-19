from ..house import House
from typing import TYPE_CHECKING, Tuple, List, Optional
import pygame

if TYPE_CHECKING:
    from ...game_state import GameState

class Town(House):
    """Represents a town hall institution in the game with donation functionality."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.treasury = 0

    def open_donation_menu(self, game_state: 'GameState', click_pos: Tuple[int, int]) -> None:
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
            
            if depot.book_donation(amount, category="Town Donations"):
                self.treasury += amount
                
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
            click_pos=click_pos, 
            callback=donation_callback,
            category="Town Donations"
        )
        game_state.active_house_menu = self

    def open_license_view(self, game_state: 'GameState', click_pos: Tuple[int, int]) -> None:
        """Opens the full contract overview showing all trading licenses.
        
        Args:
            game_state: The current game state.
            click_pos: The screen position where the user clicked.
        """
        from ...ui.helper_modules.contract_overview import ContractOverview

        game_state.info_window = ContractOverview(
            game_state.screen,
            game_state,
            house=self
        )
        game_state.active_house_menu = self
