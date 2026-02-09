import datetime
import pygame
from collections import namedtuple
from typing import Dict, List, Optional, Any, Tuple, TYPE_CHECKING
from .ui.helper_modules.warning_message import WarningMessage
from .config.constants import (
    START_DATE, 
    START_TIME,
    TIME_STEP_LEVEL_1, 
    TIME_STEP_LEVEL_2, 
    TIME_STEP_LEVEL_3, 
    TIME_STEP_LEVEL_4, 
    TIME_STEP_LEVEL_5
)

if TYPE_CHECKING:
    from .game import Game
    from .ui.helper_modules.dropdown import Dropdown
    from .ui.helper_modules.info_window import InfoWindow
    from .ui.layout_modules.depot_view_detail import DepotViewDetail
    from .models.map import GameMap

# Named tuple for tracking which time units have changed in a tick
TimeChanges = namedtuple('TimeChanges', ['minute', 'hour', 'day', 'week', 'month', 'year'])

class GameState:
    """Central repository for game session data and transient UI states.
    
    Attributes:
        screen: The main pygame display surface.
        date: Current simulation date and time.
        time_level: Simulation speed level (1-5).
        tick_counter: Number of game engine ticks elapsed.
        chart_state: Boolean indicating if the price chart is visible.
        info_state: Boolean for info panel visibility.
        depot_state: Boolean for depot panel visibility.
        mouse_clicked_on: Key of the UI element currently being clicked.
        input_fields: Dictionary of text content for various input fields.
        image_boxes: List of clickable areas for images (deprecated/placeholder).
        message: Current status message text.
        message_timer: Ticks remaining for the current message.
        active_dropdown: Reference to the currently open Dropdown.
        dropdowns: Dictionary mapping dropdown keys to Dropdown instances.
        info_window: Currently active InfoWindow modal.
        warning: Currently active WarningMessage pop-up.
        cursor_visible: Blink state of the text cursor.
        cursor_timer: Ticks elapsed since last cursor toggle.
        cursor_blink_rate: Ticks between cursor blink toggles.
        cursor_position: Index within active input field text.
        available_goods: List of all valid commodity names.
        money_effect_timer: Duration of money change highlight.
        money_effect_color: Color of money change highlight.
        button_click_effects: Active click animation timers.
        detail_panel: Reference to the DepotViewDetail panel.
    """

    def __init__(self) -> None:
        """Initialize the game state with default values."""
        self.screen: Optional[pygame.Surface] = None  # Will be set by Game class
        self.game: Optional['Game'] = None # Will be set by Game class
        self.font: Optional[pygame.font.Font] = None # Will be set by Game class
        
        # Parse start date and time from constants
        start_date_parts = START_DATE.split(".")
        start_time_parts = START_TIME.split(":")
        day, month, year = int(start_date_parts[0]), int(start_date_parts[1]), int(start_date_parts[2])
        hour, minute = int(start_time_parts[0]), int(start_time_parts[1])
        
        self.date: datetime.datetime = datetime.datetime(year, month, day, hour, minute, 0)
        self.time_level: int = 3
        self.previous_time_level: int = 3  # Stores the speed before pausing
        self.tick_counter: int = 0
        self.chart_state: bool = True
        self.info_state: bool = False
        self.depot_state: bool = False
        self.left_side_mode: str = "market"
        self.left_side_prev_mode: str = "market"
        self.right_side_mode: str = "depot"
        self.right_side_prev_mode: str = "depot"
        
        self.map_view_mode: Optional[str] = None  # Deprecated
        self.market_view_mode: Optional[str] = None  # Deprecated
        self.depot_view_mode: Optional[str] = None  # Deprecated
        self.mouse_clicked_on: str = "none"
        
        # Input fields for quick trading at the bottom of the screen
        self.input_fields: Dict[str, str] = {
            'good_one': "Wood",
            'good_two': "Stone",
            'good_three': "Iron",
            'quantity_one': "6",
            'quantity_two': "4",
            'quantity_three': "3"
        }
        
        self.image_boxes: List[Any] = []
        self.message: Optional[str] = None
        self.message_timer: int = 0
        
        self.active_dropdown: Optional['Dropdown'] = None  # Stores the currently open dropdown
        self.dropdowns: Dict[str, Any] = {}  # Stores all dropdown instances
        self.info_window: Optional['InfoWindow'] = None  # For modal dialogs like quit confirmation
        self.warning: Optional[WarningMessage] = None      # For warning messages
        self.cursor_visible: bool = True
        self.cursor_timer: int = 0
        self.cursor_blink_rate: int = 30
        self.cursor_position: int = 0
        self.current_day: int = 1
        
        # List of available goods for dropdown
        self.available_goods: List[str] = [
            "Wood", "Stone", "Iron", "Wool", "Hide", "Fish",
            "Wheat", "Wine", "Beer", "Meat", "Linen", "Pottery"
        ]
        self.contract_view: Optional[Any] = None
        
        # Initialize the time trackers from the start date
        self.last_minute: int = self.date.minute
        self.last_hour: int = self.date.hour
        self.last_day: int = self.date.day
        self.last_week: int = self.date.isocalendar()[1]
        self.last_month: int = self.date.month
        self.last_year: int = self.date.year
        
        self.depot_time_frame: str = "Daily"
        self.depot_time_frames: List[str] = ["Daily", "Weekly", "Monthly", "Yearly", "Total"]
        
        # Money glow effect and button click animations
        self.money_effect_timer: int = 0
        self.money_effect_color: Optional[Tuple[int, int, int]] = None
        self.button_click_effects: Dict[str, int] = {}
        
        self.detail_panel: Optional['DepotViewDetail'] = None
        self.small_font: Optional[pygame.font.Font] = None # Will be set by Game class
        self.depot_scroll_offset: int = 0
        self.depot_plus_buttons: Dict[str, Tuple[int, int, int, int]] = {}
        self.depot_plus_rects: Dict[str, pygame.Rect] = {}
        self.depot_buttons: Dict[str, pygame.Rect] = {}
        
        # State for the depot chart view
        self.depot_active_chart: str = "Wealth"
        self.depot_chart_buttons: Dict[str, pygame.Rect] = {}
        self.active_house_menu = None
        self.house_last_hovered = None
        self.house_hover_fade_house = None
        self.house_hover_fade_duration = 12
        self.house_hover_fade_timer = 0

    @property
    def is_map_visible(self) -> bool:
        """Check if the map is currently being displayed on either side of the screen."""
        return self.left_side_mode == 'map' or self.right_side_mode == 'map'
        
    def update_time(self) -> None:
        """Advance the game simulation time based on current speed level."""
        # Enforce map view time restriction: only paused (1) or normal (3) allowed
        if self.is_map_visible and self.time_level not in [1, 3]:
            # If map is visible, we force invalid speeds to Normal (3)
            self.time_level = 3

        self.tick_counter += 1
        if self.time_level == 1:
                self.date += datetime.timedelta(minutes=TIME_STEP_LEVEL_1)
        elif self.time_level == 2:
                self.date += datetime.timedelta(minutes=TIME_STEP_LEVEL_2)
        elif self.time_level == 3:
                self.date += datetime.timedelta(minutes=TIME_STEP_LEVEL_3)
        elif self.time_level == 4:
                self.date += datetime.timedelta(minutes=TIME_STEP_LEVEL_4)
        elif self.time_level == 5:
            self.date += datetime.timedelta(minutes=TIME_STEP_LEVEL_5)
  
    def show_warning(self, text: str) -> None:
        """Display a transient warning message on the UI.
        
        Args:
            text: The message content.
        """
        if self.screen and self.font:
            self.warning = WarningMessage(self.screen, text, self.font, self.game)
        
    def update(self) -> TimeChanges:
        """Update game state timers and check for time interval changes.
        
        Returns:
            TimeChanges: Named tuple indicating which time units changed.
        """
        self.update_time()
        current_minute = self.date.minute
        current_hour = self.date.hour
        current_day = self.date.day
        current_week = self.date.isocalendar()[1]
        current_month = self.date.month
        current_year = self.date.year

        minute_changed = current_minute != self.last_minute
        hour_changed = current_hour != self.last_hour
        day_changed = current_day != self.last_day
        week_changed = current_week != self.last_week
        month_changed = current_month != self.last_month
        year_changed = current_year != self.last_year

        self.last_minute = current_minute
        self.last_hour = current_hour
        self.last_day = current_day
        self.last_week = current_week
        self.last_month = current_month
        self.last_year = current_year
        
        if self.message_timer > 0:
            self.message_timer -= 1
            if self.message_timer == 0:
                self.message = None
        
        # NEW: Update money effect timer and reset color if finished
        if self.money_effect_timer > 0:
            self.money_effect_timer -= 1
            if self.money_effect_timer <= 0:
                self.money_effect_color = None

        # Update cursor blink
        self.cursor_timer += 1
        if self.cursor_timer >= self.cursor_blink_rate:
            self.cursor_timer = 0
            self.cursor_visible = not self.cursor_visible

        # NEW: Update button click effects and remove finished ones
        remove_keys = []
        for key in self.button_click_effects:
            self.button_click_effects[key] -= 1
            if self.button_click_effects[key] <= 0:
                remove_keys.append(key)
        for key in remove_keys:
            del self.button_click_effects[key]
                
        return TimeChanges(minute_changed, hour_changed, day_changed, week_changed, month_changed, year_changed)
