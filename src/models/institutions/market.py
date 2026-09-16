from ..house import House
from typing import TYPE_CHECKING, Tuple, List, Optional, Dict
from ...config.constants import (
    MARKET_OPEN_HOUR,
    MARKET_CLOSE_HOUR,
    MARKET_SPRITE_SWITCH_JITTER_MINUTES,
)
import datetime
import os
import random
import pygame

if TYPE_CHECKING:
    from ...game_state import GameState

class Market(House):
    """Represents a market institution in the game where goods can be traded.

    At night the booth is shown with its closed (tarped) sprite. Each booth
    switches at a slightly random time around closing and opening hour.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.open_image: Optional[pygame.Surface] = self.image
        self.closed_image: Optional[pygame.Surface] = self._load_closed_image()
        self.open_image_cache: Dict[float, pygame.Surface] = self.scaled_image_cache
        self.closed_image_cache: Dict[float, pygame.Surface] = {}
        self.is_closed_sprite: bool = False

        # Switch times in minutes since noon, rescheduled every night
        self.close_minute: float = 0.0
        self.open_minute: float = 0.0
        self.last_schedule_date: Optional[str] = None

    def _load_closed_image(self) -> Optional[pygame.Surface]:
        """Load the booth's closed sprite; None if the booth has none (it keeps its open sprite)."""
        if not self.file_name:
            return None
        stem = os.path.splitext(self.file_name)[0]
        path = os.path.join('assets', 'map_sprites', 'houses', f"{stem}_closed.png")
        if os.path.exists(path):
            try:
                return pygame.image.load(path).convert_alpha()
            except pygame.error as e:
                print(f"Failed to load closed market image: {path} - {e}")
        return None

    def update_sprite(self, current_time: datetime.datetime) -> None:
        """Swap between open and closed sprite depending on the time of day."""
        if self.closed_image is None:
            return

        # Shift by 12 hours so one night belongs to one schedule (like the window lights)
        shifted = current_time - datetime.timedelta(hours=12)
        cycle_date = shifted.strftime("%Y-%m-%d")
        if self.last_schedule_date != cycle_date:
            jitter = MARKET_SPRITE_SWITCH_JITTER_MINUTES
            self.close_minute = (MARKET_CLOSE_HOUR - 12) * 60 + random.uniform(-jitter, jitter)
            self.open_minute = (MARKET_OPEN_HOUR + 12) * 60 + random.uniform(-jitter, jitter)
            self.last_schedule_date = cycle_date

        minute_of_cycle = shifted.hour * 60 + shifted.minute + shifted.second / 60
        closed = self.close_minute <= minute_of_cycle < self.open_minute
        if closed != self.is_closed_sprite:
            self.is_closed_sprite = closed
            self.image = self.closed_image if closed else self.open_image
            self.scaled_image_cache = self.closed_image_cache if closed else self.open_image_cache

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
        from ...ui.helper_modules.quick_trade_menu import TradeMenu
        
        # Replace current info window with new trade menu
        game_state.info_window = TradeMenu(
            game_state.screen, 
            game_state, 
            good_name,
            click_pos
        )
        game_state.active_house_menu = self
