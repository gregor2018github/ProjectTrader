from ..house import House
from typing import TYPE_CHECKING, Tuple, List
import pygame

if TYPE_CHECKING:
    from ...game_state import GameState

class Market(House):
    """Represents a market institution in the game where goods can be traded."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def get_trade_options(self) -> List[str]:
        """Returns a list of goods that can be traded at this market based on its name."""
        if not self.name:
            return []
            
        # Parse name to find goods
        # Example names: "Wood Market", "Wine & Beer Market"
        
        # Remove "Market" and trim
        core_name = self.name.replace("Market", "").strip()
        
        if "&" in core_name:
            # Handle dual markets e.g. "Wine & Beer"
            parts = core_name.split("&")
            return [part.strip() for part in parts]
        else:
            # Single good market
            # Sometimes the name might have extra spaces or ID numbers, checking for known goods?
            # User instruction says "Name of the good and then the word Market"
            # SO we just take the first word if it's "Wood Market", etc.
            return [core_name]

    def open_trade_menu(self, game_state: 'GameState', click_pos: Tuple[int, int], good_name: str) -> None:
        """Opens the trade menu for a specific good.
        
        Args:
            game_state: The current game state.
            click_pos: The screen position where the user clicked.
            good_name: The name of the good to trade.
        """
        # Local import to avoid circular dependency
        from ...ui.helper_modules.trade_menu import TradeMenu
        
        # Replace current info window with new trade menu
        game_state.info_window = TradeMenu(
            game_state.screen, 
            game_state, 
            good_name,
            click_pos
        )
        game_state.active_house_menu = self
