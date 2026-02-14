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
        from ...ui.helper_modules.house_click_menu import HouseMenu
        
        options = ["Donate 10", "Donate 100", "Donate 1000"]
        
        def donation_callback(option_text: str):
            try:
                amount = int(option_text.split()[1])
            except (IndexError, ValueError):
                return

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

    def open_license_view(self, game_state: 'GameState', click_pos: Tuple[int, int]) -> None:
        """Opens a view showing all current trading licenses and their remaining days.
        
        Args:
            game_state: The current game state.
            click_pos: The screen position where the user clicked.
        """
        from ...ui.helper_modules.house_click_menu import HouseMenu

        depot = game_state.game.depot
        licenses = depot.get_licenses(game_state.date)

        if not licenses:
            options = ["No licenses owned"]
        else:
            # Sort: active first (by days left desc), then expired
            licenses.sort(key=lambda l: l["days_left"], reverse=True)
            options = []
            for lic in licenses:
                if lic["days_left"] > 0:
                    options.append(f"{lic['good']}: {lic['days_left']} days left")
                else:
                    options.append(f"{lic['good']}: expired")

        def license_callback(option_text: str):
            # Read-only view, clicking any entry just closes the menu
            game_state.info_window = None
            game_state.active_house_menu = None

        game_state.info_window = HouseMenu(
            game_state.screen,
            self,
            options,
            game_state.font,
            game_state,
            click_pos=click_pos,
            callback=license_callback,
        )
        game_state.active_house_menu = self
