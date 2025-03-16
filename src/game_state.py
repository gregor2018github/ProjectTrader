import datetime
from collections import namedtuple
from .ui.warning_message import WarningMessage

class GameState:
    def __init__(self):
        self.screen = None  # Will be set by Game class
        self.date = datetime.datetime(1500, 1, 1, 0, 0, 0)
        self.time_level = 3
        self.tick_counter = 0
        self.chart_state = True
        self.info_state = False
        self.depot_state = False
        self.mouse_clicked_on = "none"
        
        # Input fields for quick trading at the bottom of the screen
        self.input_fields = {
            'good_one': "Wood",
            'good_two': "Stone",
            'good_three': "Iron",
            'quantity_one': "4",
            'quantity_two': "3",
            'quantity_three': "2"
        }
        
        self.image_boxes = []
        self.message = None
        self.message_timer = 0
        
        self.active_dropdown = None  # Stores the currently open dropdown
        self.dropdowns = {}  # Stores all dropdown instances
        self.info_window = None  # For modal dialogs like quit confirmation
        self.warning = None      # For warning messages
        self.cursor_visible = True
        self.cursor_timer = 0
        self.cursor_blink_rate = 30
        self.cursor_position = 0
        self.current_day = 1
        
        # List of available goods for dropdown
        self.available_goods = [
            "Wood", "Stone", "Iron", "Wool", "Hide", "Fish",
            "Wheat", "Wine", "Beer", "Meat", "Linen", "Pottery"
        ]
        
        self.last_hour = 0
        self.last_day = 1
        self.last_week = 1
        self.last_month = 1
        self.last_year = 1500
        
        self.depot_time_frame = "Daily"
        self.depot_time_frames = ["Daily", "Weekly", "Monthly", "Yearly", "Total"]
        
        # NEW: For money glow effect and button click animations
        self.money_effect_timer = 0
        self.money_effect_color = None
        self.button_click_effects = {}
        
    def update_time(self):
        self.tick_counter += 1
        if self.time_level == 1:
                self.date += datetime.timedelta(hours=0)
        elif self.time_level == 2:
                self.date += datetime.timedelta(hours=0.005)
        elif self.time_level == 3:
                self.date += datetime.timedelta(hours=0.01)
        elif self.time_level == 4:
                self.date += datetime.timedelta(hours=0.1)
        elif self.time_level == 5:
            self.date += datetime.timedelta(hours=1)
                
    def show_message(self, text):
        self.message = text
        self.message_timer = 120  # Show message for 2 seconds (120 frames at 60fps)
        
    def show_warning(self, text):
        self.warning = WarningMessage(self.screen, text, self.font, self.game)  # pass game reference
        
    def update(self):
        self.update_time()
        current_hour = self.date.hour
        current_day = self.date.day
        current_week = self.date.isocalendar()[1]
        current_month = self.date.month
        current_year = self.date.year

        hour_changed = current_hour != self.last_hour
        day_changed = current_day != self.last_day
        week_changed = current_week != self.last_week
        month_changed = current_month != self.last_month
        year_changed = current_year != self.last_year

        self.last_hour = current_hour
        self.last_day = current_day
        self.last_week = current_week
        self.last_month = current_month
        self.last_year = current_year
        
        if self.message_timer > 0:
            self.message_timer -= 1
            if self.message_timer == 0:
                self.message = None
        
        # NEW: Update money glow effect timer
        if self.money_effect_timer > 0:
            self.money_effect_timer -= 1
            if self.money_effect_timer == 0:
                self.money_effect_color = None

        # NEW: Update button click effects and remove finished ones
        remove_keys = []
        for key in self.button_click_effects:
            self.button_click_effects[key] -= 1
            if self.button_click_effects[key] <= 0:
                remove_keys.append(key)
        for key in remove_keys:
            del self.button_click_effects[key]
                
        TimeChanges = namedtuple('TimeChanges', ['hour', 'day', 'week', 'month', 'year'])
        return TimeChanges(hour_changed, day_changed, week_changed, month_changed, year_changed)
