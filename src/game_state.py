import datetime

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
        
        # Input fields
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
        
        self.last_day = 1  # Add this line to track the last day
        
    def update_time(self):
        self.tick_counter += 1
        if self.tick_counter % 15 == 0:
            if self.time_level == 3:
                self.date += datetime.timedelta(hours=1)
            elif self.time_level == 4:
                self.date += datetime.timedelta(hours=5)
            elif self.time_level == 5:
                self.date += datetime.timedelta(hours=24)
                
    def show_message(self, text):
        self.message = text
        self.message_timer = 120  # Show message for 2 seconds (120 frames at 60fps)
        
    def update(self):
        self.update_time()
        current_day = self.date.day
        day_changed = current_day != self.last_day
        self.last_day = current_day
        
        if self.message_timer > 0:
            self.message_timer -= 1
            if self.message_timer == 0:
                self.message = None
                
        return day_changed  # Return whether the day has changed
