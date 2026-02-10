from ..house import House
from typing import TYPE_CHECKING, Tuple, List, Optional
import pygame

if TYPE_CHECKING:
    from ...game_state import GameState

class Church(House):
    """Represents a church institution in the game with donation functionality."""
    
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
        from ...ui.helper_modules.house_click_menu import HouseMenu
        
        options = ["Donate 1", "Donate 10", "Donate 100"]
        
        def donation_callback(option_text: str):
            try:
                amount = int(option_text.split()[1])
            except (IndexError, ValueError):
                return

            if not hasattr(game_state.game, 'depot'):
                return

            depot = game_state.game.depot
            
            if depot.money >= amount:
                depot.money -= amount
                self.treasury += amount
                
                # Close menu on success
                game_state.info_window = None 
                game_state.active_house_menu = None
            else:
                # Show warning and keep menu open
                if hasattr(game_state, 'show_warning'):
                    game_state.show_warning("Not enough money!")
        
        # Replace current info window with new one
        game_state.info_window = HouseMenu(
            game_state.screen, 
            self, 
            options, 
            game_state.font, 
            game_state, 
            click_pos=click_pos, 
            callback=donation_callback
        )
        game_state.active_house_menu = self
