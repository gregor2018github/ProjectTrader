from ..house import House
from typing import TYPE_CHECKING, Tuple, List, Optional, Dict
from ...config.constants import (
    MARKET_CLOSE_WINDOW,
    MARKET_OPEN_WINDOW,
)
import datetime
import os
import random
import pygame

if TYPE_CHECKING:
    from ...game_state import GameState
    from ..figurines.humans.npcs.trader import Trader


class MarketHours:
    """When one trader packs up at night and comes back in the morning.

    Every trader packs up somewhere in ``MARKET_CLOSE_WINDOW`` and comes back
    somewhere in ``MARKET_OPEN_WINDOW``, drawn afresh at noon each day.
    """

    def __init__(self) -> None:
        # Switch times in minutes since noon, rescheduled every night
        self.close_minute: float = 0.0
        self.open_minute: float = 0.0
        self.last_schedule_date: Optional[str] = None

    def is_closed_at(self, current_time: datetime.datetime) -> bool:
        """Whether it is past closing time and not yet opening time.

        Args:
            current_time: The current in-game time.

        Returns:
            bool: True between this night's closing and opening time.
        """
        # Shift by 12 hours so one night belongs to one schedule (like the window lights)
        shifted = current_time - datetime.timedelta(hours=12)
        cycle_date = shifted.strftime("%Y-%m-%d")
        if self.last_schedule_date != cycle_date:
            self.close_minute = (random.uniform(*MARKET_CLOSE_WINDOW) - 12) * 60
            self.open_minute = (random.uniform(*MARKET_OPEN_WINDOW) + 12) * 60
            self.last_schedule_date = cycle_date

        minute_of_cycle = shifted.hour * 60 + shifted.minute + shifted.second / 60
        return self.close_minute <= minute_of_cycle < self.open_minute


class Market(House):
    """Represents a market institution in the game where goods can be traded.

    A booth is open for as long as one of its traders is minding it: it shuts
    when the last of them steps off the stall onto his way home, and opens
    again when the first one is back. At night the booth is shown with its
    closed (tarped) sprite.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.open_image: Optional[pygame.Surface] = self.image
        self.closed_image: Optional[pygame.Surface] = self._load_closed_image()
        self.open_image_cache: Dict[float, pygame.Surface] = self.scaled_image_cache
        self.closed_image_cache: Dict[float, pygame.Surface] = {}
        self.is_closed_sprite: bool = False

        #: The traders keeping this booth, filled in by the map loader.
        self.traders: List['Trader'] = []
        #: Hours kept by a booth nobody has been drawn in for.
        self.hours = MarketHours()

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

    def is_closed_at(self, current_time: datetime.datetime) -> bool:
        """Whether the booth is shut at the given time.

        Args:
            current_time: The current in-game time.

        Returns:
            bool: True once none of its traders is at his stall any more.
        """
        if not self.traders:
            return self.hours.is_closed_at(current_time)
        return not any(trader.is_at_stall(current_time) for trader in self.traders)

    def update_sprite(self, current_time: datetime.datetime) -> None:
        """Swap between open and closed sprite as the booth opens and shuts."""
        if self.closed_image is None:
            return

        closed = self.is_closed_at(current_time)
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
            goods = [part.strip() for part in parts]
        else:
            # Single good market
            # Sometimes the name might have extra spaces or ID numbers, checking for known goods?
            # User instruction says "Name of the good and then the word Market"
            # SO we just take the first word if it's "Wood Market", etc.
            goods = [core_name]

        # Plus whatever its traders sell that the name does not mention
        for trader in self.traders:
            goods.extend(good for good in trader.EXTRA_GOODS if good not in goods)
        return goods

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
