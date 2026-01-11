import pygame
import os
from typing import Dict, List, Optional, Any, Tuple
from .game_state import GameState
from .handlers.event_handler import EventHandler
from .ui.general_layout.layout import draw_layout, draw_right_bar
from .ui.layout_modules.chart_view import draw_chart
from .ui.layout_modules.map_view import draw_map_view
from .models.good import Good
from .models.depot import Depot
from .models.player import Player
from .models.map import GameMap
from .config.colors import *
from .ui.layout_modules.depot_view import draw_depot_view
from .ui.helper_modules.menu import Menu
from .ui.helper_modules.time_control import TimeControl
from .ui.helper_modules.sound_control import SoundControl  # Add import for SoundControl
from .config.constants import PICTURES_PATH, FONTS_PATH, MAX_RECULCULATIONS_PER_SEC, SCREEN_WIDTH, SCREEN_HEIGHT, SIDEBAR_WIDTH, MODULE_WIDTH
from .config.constants import INITIAL_DAILY_COST_OF_LIVING, STARTING_MONEY, MAX_FRAMES_PER_SEC, INITIAL_TRANSACTION_COST, INITIAL_STORAGE_CAPACITY

class Game:
    """The central class that manages the main game loop, initialization, and resource loading.
    
    This class orchestrates components like GameState, EventHandler, Depot, and UI elements
    to provide the Merchant's Rise game experience.
    """
    
    def __init__(self) -> None:
        """Initialize the game engine, UI, assets, and game objects."""
        pygame.init()
        
        # Initialize mixer for sound playback
        pygame.mixer.init()
        
        # Initialize screen first
        self.screen: pygame.Surface = pygame.display.set_mode((SCREEN_WIDTH + SIDEBAR_WIDTH, SCREEN_HEIGHT))
        
        # Initialize basic components
        self.state: GameState = GameState()
        self.state.screen = self.screen  # Set screen reference in GameState
        self.state.game = self  # Add reference to self (Game instance)
        self.event_handler: EventHandler = EventHandler()
        self.clock: pygame.time.Clock = pygame.time.Clock()
        
        # Set up window properties
        pygame.display.set_caption("Merchant's Rise")
        icon = pygame.image.load(os.path.join(PICTURES_PATH, 'Icon.png'))
        pygame.display.set_icon(icon)
        
        # Initialize font
        self.font: pygame.font.Font = pygame.font.Font(os.path.join(FONTS_PATH, "RomanAntique.ttf"), 24)
        self.small_font: pygame.font.Font = pygame.font.Font(os.path.join(FONTS_PATH, "RomanAntique.ttf"), 19)
        self.state.font = self.font  # Set font reference in GameState
        self.state.small_font = self.small_font  # Set small font reference in GameState
        self.chart_border: Tuple[int, int] = (50, self.screen.get_size()[1]-150)
        
        # Initialize goods
        self.goods: List[Good] = self._initialize_goods()
        
        # Initialize depot
        self.depot: Depot = Depot(money=STARTING_MONEY, transaction_cost=INITIAL_TRANSACTION_COST, storage_capacity=INITIAL_STORAGE_CAPACITY)

        # Initialize player
        self.player: Player = Player(name="New Player", cost_of_living=INITIAL_DAILY_COST_OF_LIVING)
        
        # Initialize game map (for the 2D map view)
        # Map viewport is the left half of the screen minus borders
        map_view_width = SCREEN_WIDTH // 2 - 10
        map_view_height = SCREEN_HEIGHT - 130  # Account for top and bottom bars
        self.game_map: GameMap = GameMap(map_view_width, map_view_height)
        
        # Load images
        self.images: Dict[str, Any] = self._load_images()
        
        # Load sounds
        self.sounds: Dict[str, pygame.mixer.Sound] = self._load_sounds()
        
        # Load music
        self.music_paths: Dict[str, str] = self._load_music()
        
        self.update_delay: int = 1000 // MAX_RECULCULATIONS_PER_SEC  # milliseconds between updates
        self.last_update: int = 0
        
        self.menu: Menu = Menu(self.screen.get_width(), self.font)  # Add menu initialization
        
        # Load images for time control
        time_control_images = {
            'button_start_stop_150': self.images['button_start_stop_150'],
            'button_faster_150': self.images['button_faster_150'],
            'button_slower_150': self.images['button_slower_150']
        }

        # load image for info window background frame
        self.pic_info_window: pygame.Surface = pygame.image.load(os.path.join(PICTURES_PATH, "info_window_frame.png"))

        # Load portraits for encountable characters and places
        self.pic_portraits: Dict[str, pygame.Surface] = {
            "portrait_merchant": pygame.image.load(os.path.join(PICTURES_PATH, "portrait_merchant.png")),
            "portrait_harbor": pygame.image.load(os.path.join(PICTURES_PATH, "portrait_harbor.png")),
            "portrait_shop": pygame.image.load(os.path.join(PICTURES_PATH, "portrait_shop.png"))
        }
        
        self.time_control: TimeControl = TimeControl(
            SCREEN_WIDTH, 
            self.screen.get_height(), 
            self.font,
            time_control_images
        )
        
        # Initialize sound control
        self.sound_control: SoundControl = SoundControl(
            SCREEN_WIDTH,
            self.screen.get_height(),
            self.font,
            self.images['button_sound_80']
        )

    def _initialize_goods(self) -> List[Good]:
        """Create and initialize the default list of goods for the market.
        
        Returns:
            List[Good]: A list of initialized Good objects.
        """
        goods = []
        goods_data = [
            ("Wood", 1, 5000, PALE_BROWN, 0, True),
            ("Stone", 2, 2000, GRAY, 1, True),
            ("Iron", 5, 900, STEELE_BLUE, 2, True),
            ("Wool", 3, 2500, WHITE, 3, False),
            ("Hide", 4, 1000, DARK_GRAY, 4, False),
            ("Fish", 2, 5000, LIGHT_BLUE, 5, False),
            ("Wheat", 1, 5000, YELLOW, 6, False),
            ("Wine", 10, 500, RED, 7, False),
            ("Beer", 5, 500, PALE_BROWN, 8, False),
            ("Meat", 5, 800, ROSE, 9, False),
            ("Pottery", 3, 3500, DARK_ORANGE, 10, False),
            ("Linen", 3, 2000, WHITE, 11, False)
        ]
        for name, price, quantity, color, index, show in goods_data:
            goods.append(Good(name=name, price=price, market_quantity=quantity,
                            color=color, index=index, show_in_charts=show))
        return goods

    def _load_images(self) -> Dict[str, Any]:
        """Load and scale all visual assets for the game.
        
        Returns:
            Dict[str, Any]: A dictionary containing loaded surfaces and nested image dictionaries.
        """
        images = {'goods_30': {}}
        # Load bigger images for general stats
        images['money_50'] = pygame.image.load(os.path.join(PICTURES_PATH, "money_50.png"))
        images['stock_1024'] = pygame.image.load(os.path.join(PICTURES_PATH, "total_stock_full.png"))
        images['warehouses_1024'] = pygame.image.load(os.path.join(PICTURES_PATH, "warehouses_full.png"))
        
        # Downscale the 1024x1024 images to 30x30 for the top bar
        images['stock_30'] = pygame.transform.smoothscale(images['stock_1024'], (30, 30))
        images['warehouses_30'] = pygame.transform.smoothscale(images['warehouses_1024'], (30, 30))

        
        # Load buttons for time settings
        images['button_start_stop_150'] = pygame.image.load(os.path.join(PICTURES_PATH, "button_start_stop_150.png"))
        images['button_faster_150'] = pygame.image.load(os.path.join(PICTURES_PATH, "button_faster_150.png"))
        images['button_slower_150'] = pygame.image.load(os.path.join(PICTURES_PATH, "button_slower_150.png"))

        # Load the button for toggling the sound
        images['button_sound_80'] = pygame.image.load(os.path.join(PICTURES_PATH, "button_sound_80.png"))
        
        # Load all good icons
        for good in self.goods:
            img_path = os.path.join(PICTURES_PATH, f"{good.name.lower()}_30.png")
            images['goods_30'][good.name] = pygame.image.load(img_path)

        # Load pictograms for the side menu
        pictogram_names = ["map", "market", "depot", "politics", "trade_routes", "building"]
        for name in pictogram_names:
            img_path = os.path.join(PICTURES_PATH, f"pictogram_{name}_100.png")
            images[f'pictogram_{name}'] = pygame.image.load(img_path)
        
        return images
    
    def _load_sounds(self) -> Dict[str, pygame.mixer.Sound]:
        """Load game sound effects from the sound directory.
        
        Returns:
            Dict[str, pygame.mixer.Sound]: A dictionary mapping sound names to Sound objects.
        """
        sounds = {}
        
        # Define the sound directory
        sound_dir = os.path.join(os.path.dirname(PICTURES_PATH), "sound")

        # simply load in all files in the sound directory
        for sound_file in os.listdir(sound_dir):
            sound_path = os.path.join(sound_dir, sound_file)
            sound_name = os.path.splitext(sound_file)[0]
            try:
                sounds[sound_name] = pygame.mixer.Sound(sound_path)
            except Exception as e:
                print(f"Failed to load sound {sound_path}: {e}")
    
        return sounds
    
    def _load_music(self) -> Dict[str, str]:
        """Identify paths for music tracks in the music directory.
        
        Returns:
            Dict[str, str]: A dictionary mapping music track identifiers to file paths.
        """
        music_paths = {}
        
        # Define the music directory
        music_dir = os.path.join(os.path.dirname(PICTURES_PATH), "music")
        
        # Define the music tracks we want to load
        music_tracks = ["song_1", "song_2", "song_3", "song_4", "song_5"]
        
        # Load each music track
        for track in music_tracks:
            for ext in [".mp3", ".ogg", ".wav"]:
                music_path = os.path.join(music_dir, f"{track}{ext}")
                if os.path.exists(music_path):
                    music_paths[track] = music_path
                    break
            if track not in music_paths:
                print(f"Could not find music track {track}")
        
        return music_paths
        
    def play_sound(self, sound_name: str) -> None:
        """Play a sound effect by name.
        
        Args:
            sound_name: The key of the sound in self.sounds.
        """
        if sound_name in self.sounds:
            try:
                self.sounds[sound_name].play()
            except Exception as e:
                print(f"Failed to play sound {sound_name}: {e}")
        else:
            print(f"Sound {sound_name} not found")

    def run(self) -> None:
        """Execute the main game loop, handling updates, rendering, and events."""
        running = True
        buttons = {}
        while running:

            # Limit to X frames per second
            delta_time = self.clock.tick(MAX_FRAMES_PER_SEC) / 1000.0  # Convert milliseconds to seconds
            current_time = pygame.time.get_ticks()
            
            if current_time - self.last_update >= self.update_delay:
                self.last_update = current_time
                hour_changed, day_changed, week_changed, month_changed, year_changed = self.state.update()

                # update prices once per hour
                if hour_changed:
                    for good in self.goods:
                        good.update_price()
                        # Update chart price history hourly
                        good.update_price_history_chart()

                # update wealth, stock and bookkeeping price history once per day
                if day_changed:
                    self.depot.book_cost_of_living(self.player.daily_cost_of_living) # first pay your bread
                    self.depot.update_wealth(self.goods)
                    self.depot.update_total_stock()
                    self.depot.update_stock_history()
                    self.depot.update_income_and_expenditures()
                    for good in self.goods:
                        good.update_price_history()  # Bookkeeping price history, actual prices recorded hourly
            
            # Reset hover states at the beginning of each frame
            for good in self.goods:
                if hasattr(good, '_external_hover') and not good._external_hover:
                    good.hovered = False
            
            # 1. Fill base background
            self.screen.fill(BEIGE)
            
            # 2. Draw content modules based on view states
            # Calculate view rectangles for left and right modules
            left_module_rect = pygame.Rect(0, 60, MODULE_WIDTH, SCREEN_HEIGHT - 120)
            right_module_rect = pygame.Rect(MODULE_WIDTH, 60, MODULE_WIDTH, SCREEN_HEIGHT - 120)
            full_module_rect = pygame.Rect(0, 60, MODULE_WIDTH * 2, SCREEN_HEIGHT - 120)
            
            # Handle map view updates based on visibility
            is_map_visible = self.state.map_view_mode in ['left', 'right', 'full']
            if is_map_visible:
                # Update map with player movement
                if self.state.time_level > 1:  # Only update if game is not paused
                    keys = pygame.key.get_pressed()
                    self.game_map.handle_movement_keys(keys)
                    self.game_map.update(delta_time)
            
            # Render content based on view modes
            if self.state.map_view_mode == 'full':
                # Map takes both left and right
                draw_map_view(self.screen, self.game_map, full_module_rect, self.font)
            elif self.state.market_view_mode == 'full':
                # Chart takes both left and right
                self.state.image_boxes = draw_chart(self.screen, self.font, self.chart_border, 
                                                    self.goods, self.images['goods_30'], self.state.date, 
                                                    full_module_rect)
            else:
                # Handle LEFT side
                if self.state.map_view_mode == 'left':
                    draw_map_view(self.screen, self.game_map, left_module_rect, self.font)
                elif self.state.market_view_mode == 'right':
                    # If market is on right, we can show depot or something else on left?
                    # For now, let's just not draw chart on left if it's on right.
                    pass
                else: 
                    # Default: chart on left
                    self.state.image_boxes = draw_chart(self.screen, self.font, self.chart_border, 
                                                        self.goods, self.images['goods_30'], self.state.date, 
                                                        left_module_rect)
                
                # Handle RIGHT side
                if self.state.map_view_mode == 'right':
                    draw_map_view(self.screen, self.game_map, right_module_rect, self.font)
                elif self.state.market_view_mode == 'right':
                    self.state.image_boxes = draw_chart(self.screen, self.font, self.chart_border, 
                                                        self.goods, self.images['goods_30'], self.state.date, 
                                                        right_module_rect)
                else:
                    # Default: depot on right
                    draw_depot_view(self.screen, self.font, self.depot, self.state)

            # 4. Draw persistent UI elements (Top and Bottom Bars)
            buttons = draw_layout(self.screen, self.goods, self.depot, self.font, 
                                self.state.date, self.state.input_fields, 
                                self.state.mouse_clicked_on, self.images, self.state)
            
            # 5. Draw right sidebar and other overlays
            draw_right_bar(screen=self.screen, images=self.images, buttons=buttons, main_font=self.font)
            # Draw menu above the right sidebar
            self.menu.draw(self.screen)
            
            # Draw time controls in bottom bar
            self.time_control.draw(self.screen, self.state.time_level)
            
            # Draw sound control button
            self.sound_control.draw(self.screen)
            
            # Draw dropdowns after everything else
            for dropdown in self.state.dropdowns.values():
                if dropdown.is_open:  # Changed from checking active_dropdown
                    dropdown.draw(self.screen)

            # Draw dialogue if active
            if hasattr(self.state, 'dialogue') and self.state.dialogue:
                self.state.dialogue.draw()
            
            # Draw info window if active
            if self.state.info_window:
                self.state.info_window.draw()
            # UPDATE AND DRAW WARNING MESSAGE IF PRESENT
            if self.state.warning:
                # Update warning timer with actual elapsed time
                self.state.warning.update(delta_time)
                self.state.warning.draw()
                if self.state.warning.timer <= 0:
                    self.state.warning = None
            # Draw message only if no warning is active
            if self.state.message and not self.state.warning:
                self._draw_message(self.state.message)
                
            for event in pygame.event.get():
                if event.type == pygame.MOUSEMOTION:
                    # Clear any hover states that aren't from the current frame
                    for good in self.goods:
                        if not hasattr(good, '_external_hover'):
                            good._external_hover = False
                        good._external_hover = False
                
                running = self.event_handler.handle_events(event, self.state, 
                                                        self.goods, self.depot, buttons)
                
            pygame.display.update()

    def _draw_message(self, message):
        # Draw message in center of screen
        message_font = pygame.font.Font(None, 36)
        text = message_font.render(message, True, (255, 0, 0))
        text_rect = text.get_rect(center=(self.screen.get_width()/2, self.screen.get_height()/2))
        pygame.draw.rect(self.screen, (255, 255, 255), text_rect.inflate(20, 20))
        pygame.draw.rect(self.screen, (0, 0, 0), text_rect.inflate(20, 20), 2)
        self.screen.blit(text, text_rect)
