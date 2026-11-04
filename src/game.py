import pygame
import os
import random
import datetime
import time
from typing import Dict, List, Optional, Any, Tuple
from .game_state import GameState, quick_trade_quantity
from .handlers.event_handler import EventHandler
from .ui.general_layout.layout import draw_layout, draw_right_bar, prescan_quicktrade_hover
from .models.institutions.market import Market
from .ui.layout_modules.chart_view import draw_chart
from .ui.layout_modules.map_view import draw_map_view, draw_map_debug_ui
from .ui.layout_modules.depot_view_chart import draw_depot_chart
from .ui.layout_modules.town_plan import TownPlan
from .ui import cursor
from .models.good import Good
from .models.depot import Depot
from .models.player import Player
from .models.merchant_rank import MerchantRank
from .models.map import GameMap
from .models.institutions.town import Town
from .models.population import PopulationManager
from .sim import DataError, GoodDef, Simulation, load_definitions, load_scenario
from .sim.systems.population import class_shares
from .sim.rng import new_seed
from .sim.events import SimEvent
from .config import colors
from .models.ambience import AMBIENCE_FIRST_CHANNEL, Ambience
from .models.lightning import Lightning
from .models.coughs import Coughs
from .models.owls import Owls
from .models.dogs import Dogs
from .ui.view_transition import ViewTransition
from .models.weather import Weather
from .config.constants import STROLL_RAIN_FROM
from .config.colors import *
from .ui.layout_modules.depot_view import draw_depot_view
from .ui.helper_modules.menu import Menu
from .ui.helper_modules.time_control import TimeControl
from .ui.helper_modules.sound_control import SoundControl  # Add import for SoundControl
from .ui.helper_modules.contract_acquisition import ContractView
from .ui.helper_modules.info_window import InfoWindow
from .ui.helper_modules.save_indicator import SaveIndicator
from .ui.helper_modules.figurine_click_menu import iter_figurines, release_ended_conversations
from .config.constants import PICTURES_PATH, FONTS_PATH, MAX_RECULCULATIONS_PER_SEC, SCREEN_WIDTH, SCREEN_HEIGHT, SIDEBAR_WIDTH, MODULE_WIDTH
from .config.constants import INITIAL_DAILY_COST_OF_LIVING, TOP_BAR_DEFAULT_PINS, STARTING_MONEY, INITIAL_TRANSACTION_COST, INITIAL_STORAGE_CAPACITY, CHURCH_BELL_VOLUME, SHEEP_VOLUME, SHEEP_SOUND_MAX_DISTANCE, DOOR_VOLUME, DOOR_SOUND_MAX_DISTANCE, MARKET_PRESIMULATION_DAYS, OVERDRAFT_DAILY_RATE
from .config import settings_store
from .persistence.save_manager import (
    AUTOSAVE_NAME, AUTOSAVE_SLOT, apply_save_data, save_game, thumbnail_path,
)

HOME_TOWN_SCENARIO = "home_town"   # assets/data/scenarios/<name>.json: the workshops a new game starts with
GAME_FADE_IN_SECONDS = 0.9   # the loading screen fading away over the first frames
MIXER_FREE_CHANNELS = 16     # channels for one-off sounds (voices, doors, coins), besides the reserved ones


class Game:
    """The central class that manages the main game loop, initialization, and resource loading.

    This class orchestrates components like GameState, EventHandler, Depot, and UI elements
    to provide the Merchant's Rise game experience.
    """

    def __init__(self, save_data: Optional[Dict[str, Any]] = None,
                 screen: Optional[pygame.Surface] = None) -> None:
        """Initialize the game engine, UI, assets, and game objects.

        Args:
            save_data: Optional save dict from save_manager.load_game(). When provided,
                       the live game objects are overwritten with the saved state after
                       normal initialization completes.
            screen: Optional pre-created display surface. When provided the display
                    mode is not changed.
        """
        self.init_pygame()

        # Use the provided surface or create the display for the first time.
        self.screen: pygame.Surface = screen if screen is not None else pygame.display.set_mode(
            (SCREEN_WIDTH + SIDEBAR_WIDTH, SCREEN_HEIGHT)
        )
        
        # Initialize basic components
        self.state: GameState = GameState()
        self.state.screen = self.screen  # Set screen reference in GameState
        self.state.game = self  # Add reference to self (Game instance)
        self.event_handler: EventHandler = EventHandler()
        self.clock: pygame.time.Clock = pygame.time.Clock()
        
        # Window caption and icon are set by run(), on the main thread
        self.icon: pygame.Surface = pygame.image.load(os.path.join(PICTURES_PATH, 'Icon.png'))
        self._fade_cover: Optional[pygame.Surface] = None   # see fade_in_from()
        self._fade_start: Optional[float] = None

        # Initialize font
        self.font: pygame.font.Font = pygame.font.Font(os.path.join(FONTS_PATH, "RomanAntique.ttf"), 24)
        self.small_font: pygame.font.Font = pygame.font.Font(os.path.join(FONTS_PATH, "RomanAntique.ttf"), 19)
        self.pause_font: pygame.font.Font = pygame.font.Font(os.path.join(FONTS_PATH, "RomanAntique.ttf"), 52)
        self.state.font = self.font  # Set font reference in GameState
        self.state.small_font = self.small_font  # Set small font reference in GameState
        self.chart_border: Tuple[int, int] = (50, self.screen.get_size()[1]-150)

        # The economy (src/sim/): goods, needs, recipes and building types from
        # assets/data/, on a fresh seed (shown on the weather debug page, so a bug
        # report can name it). It is run ahead once the town is founded, below.
        definitions = load_definitions([name for name, _ in class_shares()])
        self.sim: Simulation = Simulation(definitions, now=self.state.date, seed=new_seed())
        self.goods: List[Good] = self._initialize_goods(definitions.goods)
        self.state.chart_selection_order = [g.name for g in self.goods if g.show_in_charts]

        # Clear sky, cloud and rain, going on with the game's clock
        self.weather: Weather = Weather(partway=True)

        # Initialize depot
        # Every list of goods comes from goods.json: the depot's accounts, the licences
        # (a guild's, covering its chain), the booths' extra goods, the quick-trade quantities
        names = [d.name for d in definitions.goods]
        licenses = definitions.licenses()
        self.state.available_goods = names
        self.state.licenses = licenses
        self.state.default_good_quantities = {d.name: quick_trade_quantity(d.outside_price) for d in definitions.goods}
        self.state.good_quantities = dict(self.state.default_good_quantities)
        self.state.pinned_goods = names[:TOP_BAR_DEFAULT_PINS]
        Market.SOLD_AT = {}
        for d in definitions.goods:
            for market_name in d.sold_at:
                Market.SOLD_AT.setdefault(market_name, []).append(d.name)
        self.depot: Depot = Depot(money=STARTING_MONEY, transaction_cost=INITIAL_TRANSACTION_COST,
                                  storage_capacity=INITIAL_STORAGE_CAPACITY, goods=names)
        self.depot.license_of = {d.name: d.license_name for d in definitions.goods}
        self.depot.init_starting_licenses(self.state.date, [(l.name, l.starting_seasons) for l in licenses.values()
                                                            if l.starting_seasons > 0])

        # Initialize player
        self.player: Player = Player(name="New Player", cost_of_living=INITIAL_DAILY_COST_OF_LIVING)
        self.merchant_rank: MerchantRank = MerchantRank(self.depot, self.player, self.goods)

        # Initialize game map (for the 2D map view)
        # Map viewport is the left half of the screen minus borders
        map_view_width = SCREEN_WIDTH // 2 - 10
        map_view_height = SCREEN_HEIGHT - 130  # Account for top and bottom bars
        self.game_map: GameMap = GameMap(map_view_width, map_view_height)
        # The crops on the fields, as far grown as the season has them
        self.game_map.tmx_map.update_crops(self.state.date)
        # The paper plan of the town shown in the "building" view
        self.town_plan: TownPlan = TownPlan(self.game_map)
        self.town_plan.prepare()   # now, behind the loading screen, not when first opened
        self.game_map.puddles.set_trodden(self.town_plan.trodden_tiles())   # puddles gather on roads and paving
        self.game_map.wet_ground.set_ground(self.town_plan.ground_masks(self.game_map.wet_ground.size))
        self.game_map.snow_cover.set_ground(self.town_plan.ground_masks(self.game_map.snow_cover.size))

        # The town's people live in the simulation; the town hall and the charts show them
        self.town: Optional[Town] = None
        for house in self.game_map.tmx_map.houses:
            if isinstance(house, Town):
                town_spec = house.initialize_population(self.game_map.tmx_map.houses)
                self.town = house
        if self.town is not None:
            self.sim.found_town(town_spec)
            self.town.attach(self.sim)
        # The town's workshops and who owns them (assets/data/scenarios/home_town.json)
        self.sim.establish(load_scenario(HOME_TOWN_SCENARIO, [b.type for b in definitions.buildings]))
        # The economy runs ahead, so the charts open with a history and the town on its feet
        self.sim.presimulate(MARKET_PRESIMULATION_DAYS)

        self.population_manager: Optional[PopulationManager] = (
            PopulationManager(self.sim, self.town) if self.town else None
        )
        
        # Initial check for area
        self._update_player_market_area()

        # Queue of notices (license expiry, rank changes) to be shown as info dialogs one at a time
        self._pending_notices: List[str] = []

        # Autosave — settings can only change in the main menu, so read them once
        self.autosave_enabled: bool = bool(settings_store.get("autosave_enabled"))
        self.autosave_interval: float = 60.0 * float(settings_store.get("autosave_minutes"))
        self._autosave_elapsed: float = 0.0
        # 0 lets the frame rate run free
        self.fps_limit: int = int(settings_store.get("fps_limit"))
        self.save_indicator: SaveIndicator = SaveIndicator(self.small_font)

        # Load images
        self.images: Dict[str, Any] = self._load_images()
        
        # Load sounds
        self.sounds: Dict[str, pygame.mixer.Sound] = self._load_sounds()
        
        # Initialize footstep sounds for map player
        footstep_keys = ['Map_foot_steps_1', 'Map_foot_steps_2', 'Map_foot_steps_3', 'Map_foot_steps_4']
        footstep_sounds = [self.sounds[k] for k in footstep_keys if k in self.sounds]
        self.game_map.map_player.set_footstep_sounds(footstep_sounds)
        
        # Load music
        self.music_paths: Dict[str, str] = self._load_music()
        
        self.church_bell_channel: Optional[pygame.mixer.Channel] = None
        self.church_bell_sound: Optional[pygame.mixer.Sound] = None
        self.church_bell_audible: bool = False  # True once the bell has been heard
        self.sheep_sounds: list = [s for k, s in self.sounds.items() if k.lower().startswith('sheep_')]
        self.door_sounds: list = [s for k, s in self.sounds.items() if k.lower().startswith('door_')]
        # The map's ambient loops (mill, birds in the woods), on channels 1 and on, see init_pygame()
        self.ambience: Ambience = Ambience(self.sounds, AMBIENCE_FIRST_CHANNEL, self.game_map.tmx_map)
        # A thunderstorm's flashes and thunder (models/lightning.py), drawn by map_view
        self.lightning: Lightning = Lightning(self.sounds)
        # Now and then someone out in town near the player coughs (models/coughs.py)
        self.coughs: Coughs = Coughs(self.sounds)
        # Owls calling in the woods at night (models/owls.py)
        self.owls: Owls = Owls(self.sounds, self.ambience.trees)
        # Dogs barking in town now and then (models/dogs.py)
        self.dogs: Dogs = Dogs(self.sounds, self.ambience.town)
        # A sheet of parchment unrolled over a module whose view changed, with a page turning
        self.view_transition: ViewTransition = ViewTransition(self.sounds)
        self.view_transition.prepare()

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
        
        # If loading from a save file, restore all game state now that every object exists
        if save_data is not None:
            self.restore_loaded_save(save_data)

        # Everything the map view draws at the starting zoom, made now behind
        # the loading screen rather than in the first frames (map_warmup.py);
        # the view is the full width, as a game starts with the map on both sides
        self.game_map.warmup.prepare((MODULE_WIDTH * 2 - 10, SCREEN_HEIGHT - 120 - 10))

    def restore_loaded_save(self, save_data: Dict[str, Any]) -> None:
        """Put a loaded save into the running game: the saved state, and everything
        on the map that follows from it. Used both when the game starts from a
        save and when one is loaded while playing."""
        apply_save_data(save_data, self.state, self.player, self.depot, self.goods, sim=self.sim)
        self.game_map.map_player.x = self.player.position[0]
        self.game_map.map_player.y = self.player.position[1]
        self.game_map.restore_map_fog(save_data.get("fog"))
        self.weather.load(save_data.get("weather"))
        # The crops follow the calendar, so they need nothing from the save (older saves' "fields" is ignored)
        self.game_map.tmx_map.update_crops(self.state.date)
        self.merchant_rank.load(save_data.get("merchant_rank"))
        self.restore_owned_buildings()
        self._update_player_market_area()
        self.state.sync_quicktrade_fields()  # the saved fields may predate per-market slots

    @staticmethod
    def init_pygame() -> None:
        """Start pygame and the mixer; does nothing the second time.

        main.py calls it on the main thread before the game is built on the
        loading screen's worker thread, so that build finds it done.
        """
        pygame.init()
        pygame.mixer.init()
        # Reserve channel 0 exclusively for footstep sounds and the next ones
        # for the ambient loops (models/ambience.py), so that Sound.play()
        # calls (e.g. knock, church bell) can never steal them. The mixer only
        # has 8 channels to begin with: open enough that the one-off sounds
        # keep MIXER_FREE_CHANNELS of their own after the reserved ones.
        reserved = AMBIENCE_FIRST_CHANNEL + Ambience.CHANNELS
        pygame.mixer.set_num_channels(reserved + MIXER_FREE_CHANNELS)
        pygame.mixer.set_reserved(reserved)

    def fade_in_from(self, cover: pygame.Surface) -> None:
        """Have the first frames of run() fade in from *cover*, e.g. the loading screen."""
        self._fade_cover = cover.convert()
        self._fade_start = None

    def _draw_fade_cover(self) -> None:
        """Lay the cover of fade_in_from() over the frame, fainter every frame.

        Timed from the first frame drawn, so a slow first frame does not eat the fade.
        """
        if self._fade_cover is None:
            return
        now = time.monotonic()
        if self._fade_start is None:
            self._fade_start = now
        progress = (now - self._fade_start) / GAME_FADE_IN_SECONDS
        if progress >= 1:
            self._fade_cover = None
            return
        eased = progress * progress * (3 - 2 * progress)
        self._fade_cover.set_alpha(round(255 * (1 - eased)))
        self.screen.blit(self._fade_cover, (0, 0))

    def restore_owned_buildings(self) -> None:
        """After loading a save, mark the Warehouse objects on the map as owned or
        not by the tmx_ids stored in depot.properties["warehouses"] (both ways: a
        save loaded while playing may own fewer than the session did), and settle
        the goods into their storage slots."""
        from .models.institutions.warehouse import Warehouse
        owned_ids = {
            entry["tmx_id"]
            for entry in self.depot.properties.get("warehouses", [])
            if isinstance(entry, dict) and "tmx_id" in entry
        }
        layouts = {}
        for house in self.game_map.tmx_map.houses:
            if isinstance(house, Warehouse):
                layouts[house.tmx_id] = (house.buy_slots, house.buy_slot_size)
                house.is_owned = house.tmx_id in owned_ids
        self.depot.settle_storage(layouts)

    def _update_player_market_area(self) -> None:
        """Note which market square, if any, the player stands in, and the goods sold there."""
        area = self.game_map.market_area_at_player()
        self.player.in_market_area = area is not None
        if area == self.player.market_area and self.state.market_area_goods:
            return
        self.player.market_area = area
        self.state.market_area = area
        self.state.market_area_goods = (
            self.game_map.tmx_map.goods_at_market_area(area) if area else set()
        )
        self.state.sync_quicktrade_fields()

    def _handle_sim_events(self, events: List[SimEvent]) -> None:
        """What the simulation reported since the last update (src/sim/events.py).

        Nothing is shown for them yet, so the game looks as it did before the
        simulation core; this is where a notice or a ledger line would go.
        """
        del events

    def _initialize_goods(self, definitions: List[GoodDef]) -> List[Good]:
        """The goods as the UI shows them, one view per good of the simulation.

        Args:
            definitions: The goods from goods.json, in their order.

        Returns:
            List[Good]: A view per good, with its chart colour from colors.py.

        Raises:
            DataError: If a good names a colour colors.py does not have.
        """
        goods = []
        for d in definitions:
            color = getattr(colors, d.color, None)
            if not (isinstance(color, tuple) and len(color) == 3):
                raise DataError(f"goods.json, good {d.name!r}: field 'color': "
                                f"{d.color!r} is not a colour in src/config/colors.py")
            goods.append(Good(self.sim, d.name, color, d.chart_index, d.show_in_charts))
        return goods

    def _load_images(self) -> Dict[str, Any]:
        """Load and scale all visual assets for the game.
        
        Returns:
            Dict[str, Any]: A dictionary containing loaded surfaces and nested image dictionaries.
        """
        images = {'goods_30': {}, 'goods_icon': {}}
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
        
        # Load all good icons, including those only listed in the top bar so far
        for good_name in [good.name for good in self.goods]:
            img_path = os.path.join(PICTURES_PATH, f"{good_name.lower()}_30.png")
            images['goods_30'][good_name] = pygame.image.load(img_path)

        # Larger cut-out good pictures for bigger UI, made by build_tools/Good_Icons
        for good in self.goods:
            img_path = os.path.join(PICTURES_PATH, f"{good.name.lower()}_icon.png")
            if os.path.isfile(img_path):
                images['goods_icon'][good.name] = pygame.image.load(img_path)

        # Load pictograms for the side menu
        pictogram_names = ["map", "market", "depot", "politics", "trade_routes", "building"]
        # View keys whose picture is named after the button's label instead
        pictogram_files = {"map": "explore", "building": "town_map"}
        for name in pictogram_names:
            img_path = os.path.join(PICTURES_PATH, f"pictogram_{pictogram_files.get(name, name)}_100.png")
            images[f'pictogram_{name}'] = pygame.image.load(img_path)

        # Load population pictogram for the bottom bar (scaled to fit the 44px panel)
        pop_icon_path = os.path.join(PICTURES_PATH, "pictogram_population.png")
        raw = pygame.image.load(pop_icon_path).convert_alpha()
        images['pictogram_population'] = pygame.transform.smoothscale(raw, (34, 34))

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
            if os.path.isdir(sound_path):
                continue
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
        
        if os.path.isdir(music_dir):
            for filename in sorted(os.listdir(music_dir)):
                name, ext = os.path.splitext(filename)
                if ext.lower() in (".mp3", ".ogg", ".wav"):
                    music_paths[name] = os.path.join(music_dir, filename)
        
        return music_paths
        
    def _play_door_sounds(self) -> None:
        """Play a door for every NPC that went in or out of a house this frame.

        Quieter the further away from the player it is, and silent beyond
        DOOR_SOUND_MAX_DISTANCE.
        """
        player = self.game_map.map_player
        px = player.x + player.width / 2
        py = player.y + player.height / 2
        for npc in self.game_map.tmx_map.npcs:
            if not npc.wants_door_sound:
                continue
            npc.wants_door_sound = False
            if not self.door_sounds:
                continue
            nx = npc.x + npc.sprite_width / 2
            ny = npc.y + npc.sprite_height / 2
            dist = ((px - nx) ** 2 + (py - ny) ** 2) ** 0.5
            if dist >= DOOR_SOUND_MAX_DISTANCE:
                continue
            channel = pygame.mixer.find_channel()
            if channel:
                channel.set_volume(DOOR_VOLUME * (1.0 - dist / DOOR_SOUND_MAX_DISTANCE))
                channel.play(random.choice(self.door_sounds))

    def play_sound(self, sound_name: str) -> Optional[pygame.mixer.Channel]:
        """Play a sound effect by name.
        
        Args:
            sound_name: The key of the sound in self.sounds.
            
        Returns:
            The Channel object the sound is playing on, or None if it failed.
        """
        if sound_name in self.sounds:
            try:
                return self.sounds[sound_name].play()
            except Exception as e:
                print(f"Failed to play sound {sound_name}: {e}")
                return None
        else:
            print(f"Sound {sound_name} not found")
            return None

    def run(self) -> Optional[str]:
        """Execute the main game loop, handling updates, rendering, and events."""
        running = True
        buttons = {}
        # Window things are done here, on the main thread: the game may have been built on another
        pygame.display.set_caption("Merchant's Rise")
        pygame.display.set_icon(self.icon)
        cursor.use("hand")
        try:
            while running:

                # Limit to X frames per second
                delta_time = self.clock.tick(self.fps_limit) / 1000.0  # Convert milliseconds to seconds
                self.state.playtime_seconds += delta_time
                current_time = pygame.time.get_ticks()

                # Keep SDL input state updated before render-time input reads.
                pygame.event.pump()
                
                if current_time - self.last_update >= self.update_delay:
                    self.last_update = current_time
                    minute_changed, _price_tick_changed, hour_changed, day_changed, season_changed, year_changed = self.state.update()
                    self.weather.update(self.state.date)
                    self.game_map.tmx_map.street_life.raining = max(self.weather.rain, self.weather.snow) >= STROLL_RAIN_FROM
                    self.game_map.puddles.update(self.weather.puddle_level)

                    # The economy catches up with the clock: prices every PRICE_TICK_MINUTES,
                    # happiness every hour, migration and the well shock every day (src/sim/)
                    self.sim.advance_to(self.state.date)
                    self._handle_sim_events(self.sim.events.drain())

                    if hour_changed:
                        self.game_map.tmx_map.update_crops(self.state.date)

                        # Check if church bell should ring (midday or midnight)
                        if self.state.date.hour in (0, 12):
                            self.church_bell_channel = self.play_sound("church_bell_12_rings")
                            self.church_bell_sound = self.sounds.get("church_bell_12_rings")
                            self.church_bell_audible = False
                            # Start silent; the per-frame volume update sets the correct level.
                            # Without this, pygame resets the channel to 1.0 on play().
                            if self.church_bell_channel:
                                self.church_bell_channel.set_volume(0.0)

                    # update wealth, stock and bookkeeping price history once per day
                    if day_changed:
                        self.depot.stats.days_played += 1
                        self.depot.update_income_and_expenditures() # archive yesterday's counters first
                        # Snapshot wealth and stock while they still hold yesterday's
                        # close: today's cost of living and loan payments are booked
                        # below, and counting them here would put them in yesterday's
                        # figures as well as today's counters.
                        self.depot.update_wealth(self.goods)
                        self.depot.update_total_stock()
                        self.depot.update_stock_history()
                        cost = self.player.daily_cost_of_living
                        self.depot.book_cost_of_living(cost) # then charge today's cost of living
                        self.state.log_event("FINANCE", f"Daily costs: {cost:.0f}g")

                        # Process active loans: daily principal + interest, settlement at maturity
                        for loan in list(self.depot.active_loans):
                            loan["days_elapsed"] += 1

                            # Daily principal repayment (reduces remaining balance, not an expense)
                            daily_principal = loan.get("daily_principal", 0.0)
                            if daily_principal > 0:
                                self.depot.money -= daily_principal
                                loan["remaining_principal"] = max(
                                    0.0, loan.get("remaining_principal", 0.0) - daily_principal
                                )

                            # Daily interest (recorded as loan expenditure)
                            daily_interest = loan.get("daily_interest", 0.0)
                            if daily_interest > 0:
                                self.depot.book_loan_interest(daily_interest)

                            if daily_principal > 0 or daily_interest > 0:
                                self.state.log_event(
                                    "LOAN",
                                    f"Daily loan payment — principal: {daily_principal:.2f}g, interest: {daily_interest:.2f}g"
                                )

                            # At maturity: settlement principal closes out the loan
                            if loan["days_elapsed"] >= loan["duration_days"]:
                                settlement = loan.get("settlement_principal", loan.get("remaining_principal", 0.0))
                                if settlement > 0:
                                    self.depot.money -= settlement
                                self.state.log_event(
                                    "LOAN",
                                    f"Loan settled — final payment {settlement:.0f}g"
                                )
                                self.depot.active_loans.remove(loan)

                        # Overdraft penalty: 2% of negative balance per day
                        if self.depot.money < 0:
                            penalty = max(0.01, round(abs(self.depot.money) * OVERDRAFT_DAILY_RATE, 2))
                            self.depot.book_overdraft_penalty(penalty)
                            self.state.log_event("LOAN", f"Overdraft penalty: {penalty:.2f}g")

                        # Warn about trading licenses that expire tomorrow
                        tomorrow = self.state.date.date() + datetime.timedelta(days=1)
                        expiring = sorted(
                            gname for gname, expiry in self.depot.trading_licenses.items()
                            if expiry.date() == tomorrow
                        )
                        if expiring:
                            plural = "licenses" if len(expiring) > 1 else "license"
                            goods_lines = "\n".join(f"**  - {name}**" for name in expiring)
                            msg = (
                                f"The following {plural} expire{'' if len(expiring) > 1 else 's'} tomorrow:\n"
                                f"{goods_lines}\n"
                                f"Please renew to continue trading."
                            )
                            self._pending_notices.append(msg)

                        if season_changed:
                            self.merchant_rank.new_season()
                        rank_change = self.merchant_rank.daily_check(self.state.date.date())
                        if rank_change:
                            ledger_line, message = rank_change
                            self.state.log_event("RANK", ledger_line)
                            if message:
                                self._pending_notices.append(message)

                # Show one queued license warning if no dialog is currently open
                if self._pending_notices and not self.state.info_window:
                    msg = self._pending_notices.pop(0)
                    window = InfoWindow(
                        self.state.screen, msg, ["OK"], self.state.font, self
                    )
                    window.restore_time_level = self.state.time_level
                    self.state.time_level = 1
                    self.state.info_window = window

                # Reset hover states and UI boxes at the beginning of each frame
                self.state.image_boxes = []
                self.state.depot_chart_buttons = {}
                for good in self.goods:
                    if hasattr(good, '_external_hover') and not good._external_hover:
                        good.hovered = False
                
                # Before the screen is cleared: it still holds the old view, should the view have changed
                self.view_transition.begin_frame(self.screen, self.state.left_side_mode,
                                                 self.state.right_side_mode, delta_time)

                # 1. Fill base background
                self.screen.fill(BEIGE)
                # The plan only takes input while it is drawn this frame
                self.town_plan.begin_frame()
                
                # 2. Draw content modules based on view states
                # Calculate view rectangles for left and right modules
                left_module_rect = pygame.Rect(0, 60, MODULE_WIDTH, SCREEN_HEIGHT - 120)
                right_module_rect = pygame.Rect(MODULE_WIDTH, 60, MODULE_WIDTH, SCREEN_HEIGHT - 120)
                full_module_rect = pygame.Rect(0, 60, MODULE_WIDTH * 2, SCREEN_HEIGHT - 120)
                
                # Handle map view updates based on visibility
                # Map is visible if either left or right side is map
                is_map_visible = (self.state.left_side_mode == 'map' or self.state.right_side_mode == 'map')
                
                if is_map_visible:
                    # Update map with player movement
                    if self.state.time_level > 1:  # Only update if game is not paused
                        if (self.state.mouse_clicked_on.startswith("quantity_")
                                or getattr(self.state.info_window, "takes_text", False)):
                            # Keys typed into a text field (a quantity, a save's name) don't walk
                            self.game_map.map_player.set_movement(0.0, 0.0)
                        else:
                            keys = pygame.key.get_pressed()
                            self.game_map.handle_movement_keys(keys)
                        # Anyone the player is talking to stands still; the
                        # rest walk on (see figurine_click_menu)
                        release_ended_conversations(self.state, self.game_map)
                        self.game_map.update(delta_time, self.state.date)
                        self.game_map.rain.update(delta_time, self.weather.rain, self.weather.wind,
                                                  self.game_map.camera, self.game_map.tmx_map,
                                                  self.game_map.puddles, iter_figurines(self.game_map))
                        self.game_map.snow.update(delta_time, self.weather.snow, self.weather.wind,
                                                  self.game_map.camera, self.game_map.tmx_map)
                        self.game_map.fog.update(delta_time, self.weather.fog, self.weather.wind, self.game_map.camera)
                        self.game_map.puddles.update_walkers(delta_time, iter_figurines(self.game_map))
                        tile_size = self.game_map.tmx_map.tile_size
                        self.depot.stats.tiles_walked += self.game_map.map_player.frame_distance_px / tile_size
                        if self.sheep_sounds:
                            px = self.game_map.map_player.x + self.game_map.map_player.width / 2
                            py = self.game_map.map_player.y + self.game_map.map_player.height / 2
                            for sheep in self.game_map.tmx_map.sheep:
                                if sheep.wants_sound:
                                    sx = sheep.x + sheep.sprite_width / 2
                                    sy = sheep.y + sheep.sprite_height / 2
                                    dist = ((px - sx) ** 2 + (py - sy) ** 2) ** 0.5
                                    if dist < SHEEP_SOUND_MAX_DISTANCE:
                                        volume = SHEEP_VOLUME * (1.0 - dist / SHEEP_SOUND_MAX_DISTANCE)
                                        sound = random.choice(self.sheep_sounds)
                                        channel = pygame.mixer.find_channel()
                                        if channel:
                                            channel.set_volume(volume)
                                            channel.play(sound)
                        self._play_door_sounds()
                    else:
                        self.game_map.map_player.stop_footstep_sound()
                    
                    # Update player area status
                    self._update_player_market_area()
                else:
                    self.game_map.map_player.stop_footstep_sound()
                self.ambience.update(self.game_map.tmx_map, self.game_map.map_player, self.state.date,
                                     is_map_visible and self.state.time_level > 1, self.weather.rain)
                self.lightning.update(delta_time, self.weather.storm, is_map_visible and self.state.time_level > 1)
                self.coughs.update(self.state.date, is_map_visible and self.state.time_level > 1,
                                   self.game_map.tmx_map.npcs, self.game_map.map_player)
                self.owls.update(self.state.date, is_map_visible and self.state.time_level > 1,
                                 self.game_map.map_player, self.weather.rain)
                self.dogs.update(delta_time, self.state.date, is_map_visible and self.state.time_level > 1,
                                 self.game_map.map_player)

                # Update church bell volume if it's playing
                if self.church_bell_channel and self.church_bell_channel.get_sound() is self.church_bell_sound:
                    if self.state.time_level == 1:
                        self.church_bell_channel.pause()
                    else:
                        self.church_bell_channel.unpause()
                        # Allow audible playback if already ringing, or if still within the
                        # bell hour. Once past hour 0/12 without having been heard, keep it
                        # silent so it runs out without suddenly starting on map return.
                        if is_map_visible and (self.church_bell_audible or self.state.date.hour in (0, 12)):
                            from .models.institutions.church import Church
                            church = next((h for h in self.game_map.tmx_map.houses if isinstance(h, Church)), None)
                            if church:
                                # Calculate distance
                                player_center_x = self.game_map.map_player.x + self.game_map.map_player.width / 2
                                player_center_y = self.game_map.map_player.y + self.game_map.map_player.height / 2
                                col_rect = church.collision_rect
                                closest_x = max(col_rect.left, min(player_center_x, col_rect.right))
                                closest_y = max(col_rect.top, min(player_center_y, col_rect.bottom))
                                dx = player_center_x - closest_x
                                dy = player_center_y - closest_y
                                distance = (dx * dx + dy * dy) ** 0.5

                                # Max distance to hear the bell
                                max_distance = 1500.0
                                if distance < max_distance:
                                    # Scale linearly from CHURCH_BELL_VOLUME (close) to 0.0 (far)
                                    volume = CHURCH_BELL_VOLUME * (1.0 - distance / max_distance)
                                    self.church_bell_channel.set_volume(volume)
                                    if volume > 0:
                                        self.church_bell_audible = True
                                else:
                                    self.church_bell_channel.set_volume(0.0)
                            else:
                                self.church_bell_channel.set_volume(0.0)
                        else:
                            self.church_bell_channel.set_volume(0.0)
                elif self.church_bell_channel:
                    self.church_bell_channel = None
                    self.church_bell_sound = None
                    self.church_bell_audible = False

                # Helper function to render a module in a specific rect
                mouse_pos = pygame.mouse.get_pos()
                prescan_quicktrade_hover(self.goods, self.state.input_fields, self.depot, self.state, mouse_pos)
                suppress_chart_hover = (
                    bool(self.state.info_window)
                    or any(
                        d.is_open and d.dropdown_rect.collidepoint(mouse_pos)
                        for d in self.state.dropdowns.values()
                    )
                )

                def render_module(mode, rect):
                    if mode == 'map':
                        draw_map_view(self.screen, self.game_map, rect, self.state)
                    elif mode == 'market':
                        self.state.image_boxes = draw_chart(self.screen, self.font, self.chart_border,
                                                          self.goods, self.images['goods_30'], self.state.date,
                                                          rect, self.depot, suppress_chart_hover,
                                                          self.state.chart_goods_offset,
                                                          pinned=self.state.pinned_goods)
                    elif mode == 'depot':
                        draw_depot_view(self.screen, self.font, self.depot, self.state, rect)
                    elif mode == 'building':
                        self.town_plan.draw(self.screen, rect, self.state)
                    elif mode in ['politics', 'trade_routes']:
                        # Placeholders for future modules
                        pass

                # Render content based on view modes
                if self.state.left_side_mode == self.state.right_side_mode:
                    # Full View (Same module on both sides)
                    mode = self.state.left_side_mode
                    if mode == 'depot':
                        # Special case for Depot Full View: Chart on left, List on right
                        draw_depot_chart(self.screen, left_module_rect, self.font, self.depot, self.state, self.population_manager, self.goods)
                        draw_depot_view(self.screen, self.font, self.depot, self.state, right_module_rect)
                    else:
                        # Standard full view (Map, Market, etc.)
                        render_module(mode, full_module_rect)
                else:
                    # Split View (Different modules)
                    if self.state.left_side_mode == 'depot':
                        draw_depot_view(self.screen, self.font, self.depot, self.state, left_module_rect)
                    else:
                        render_module(self.state.left_side_mode, left_module_rect)
                    
                    if self.state.right_side_mode == 'depot':
                        draw_depot_view(self.screen, self.font, self.depot, self.state, right_module_rect)
                    else:
                        render_module(self.state.right_side_mode, right_module_rect)

                # 3. The parchment rolling over a view that has just changed
                self.view_transition.draw(self.screen)


                # 4. Draw persistent UI elements (Top and Bottom Bars)
                buttons = draw_layout(self.screen, self.goods, self.depot, self.font, 
                                    self.state.date, self.state.input_fields, 
                                    self.state.mouse_clicked_on, self.images, self.state)
                
                # 5. Draw right sidebar and other overlays
                draw_right_bar(screen=self.screen, images=self.images, buttons=buttons, main_font=self.font, game_state=self.state)

                # Debug overlay drawn after sidebar so it appears on top
                if settings_store.get("show_map_debug"):
                    draw_map_debug_ui(self.screen, self.game_map, self.font, self.state)
                # Draw menu above the right sidebar
                self.menu.draw(self.screen)
                
                # Draw time controls in bottom bar
                self.time_control.draw(self.screen, self.state.time_level)
                
                # Draw sound control button
                self.sound_control.draw(self.screen)
                
                # Draw pause overlay when map is visible and time is paused
                if self.state.time_level == 1 and is_map_visible:
                    self._draw_pause_overlay()

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
                
                # Draw fading menu if present
                if getattr(self.state, "menu_fade_window", None) and self.state.menu_fade_timer > 0:
                    alpha = self.state.menu_fade_timer / self.state.menu_fade_duration
                    self.state.menu_fade_window.draw(alpha_scale=alpha)
                    self.state.menu_fade_timer -= 1
                    if self.state.menu_fade_timer <= 0:
                        self.state.menu_fade_window = None
                
                # Draw contract view if active
                if self.state.contract_acquisition:
                    self.state.contract_acquisition.update(delta_time)
                    if not self.state.contract_acquisition.active:
                        self.state.contract_acquisition = None
                        self.state.time_level = self.state.previous_time_level
                    else:
                        self.state.contract_acquisition.draw()

                # Draw minigame overlay if active (e.g. woodhacking)
                if self.state.minigame:
                    self.state.minigame.update(delta_time)
                    if not self.state.minigame.active:
                        self.state.minigame = None
                        self.state.time_level = self.state.previous_time_level
                    else:
                        self.state.minigame.draw()

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
                
                # Update and draw coin popups (above all UI, below cursor)
                if self.state.coin_popups:
                    for popup in self.state.coin_popups:
                        popup.update(delta_time)
                        popup.draw()
                    self.state.coin_popups = [p for p in self.state.coin_popups if p.alive]

                # Get ahead on the map's drawing with a little of each frame (map_warmup.py)
                self.game_map.warmup.step()

                # Autosave before the cursor is drawn so it stays out of the thumbnail
                self._tick_autosave(delta_time)
                self.save_indicator.update(delta_time)
                self.save_indicator.draw(self.screen)

                self._draw_fade_cover()

                # The pointer is a system cursor, so it shows over the black bars too
                if self.state.contract_acquisition:
                    cursor.use(self.state.contract_acquisition.cursor_pointer())
                else:
                    cursor.use("hand")

                pygame.display.update()
        except KeyboardInterrupt:
            pass
        self.ambience.stop()
        self.lightning.stop()

        if getattr(self.state, 'return_to_main_menu', False):
            return "main_menu"
        return None

    def write_save(self, slot: int, save_name: str,
                   screenshot: Optional[pygame.Surface]) -> None:
        """Write the current game to *slot*, with *screenshot* as its thumbnail.

        Raises whatever save_game raises; a failed thumbnail is ignored.
        """
        if screenshot is not None:
            try:
                thumb_file = thumbnail_path(slot)
                os.makedirs(os.path.dirname(thumb_file), exist_ok=True)
                thumb = pygame.transform.smoothscale(screenshot, (576, 348))
                pygame.image.save(thumb, thumb_file)
            except Exception:
                pass
        # Sync map player position into the player model before serialising
        mp = self.game_map.map_player
        self.player.position = (int(mp.x), int(mp.y))
        save_game(slot, self.state, self.player, self.depot, self.goods,
                  save_name=save_name, sim=self.sim,
                  fog=self.game_map.map_fog, weather=self.weather,
                  merchant_rank=self.merchant_rank)

    def reset_autosave_timer(self) -> None:
        """Start a full autosave interval from now (e.g. after loading a save)."""
        self._autosave_elapsed = 0.0

    def _tick_autosave(self, delta_time: float) -> None:
        """Count play time and write the autosave once the interval has passed.

        When due while a dialog or exclusive overlay is open, the save waits
        until it closes so the thumbnail shows the game itself.
        """
        if not self.autosave_enabled:
            return
        self._autosave_elapsed += delta_time
        if self._autosave_elapsed < self.autosave_interval:
            return
        if self.state.info_window or self.state.contract_acquisition or self.state.minigame:
            return
        self._autosave_elapsed = 0.0
        try:
            self.write_save(AUTOSAVE_SLOT, AUTOSAVE_NAME, self.screen.copy())
            self.save_indicator.show()
        except Exception as e:
            self.state.show_warning(f"Autosave failed: {e}")

    def _draw_pause_overlay(self) -> None:
        text_surf = self.pause_font.render("Paused", True, (220, 200, 160))
        pad_x, pad_y = 28, 12
        w = text_surf.get_width() + pad_x * 2
        h = text_surf.get_height() + pad_y * 2
        # Center in the map content area
        cx = MODULE_WIDTH
        cy = 60 + (SCREEN_HEIGHT - 120) // 2
        x = cx - w // 2
        y = cy - h // 2
        bg = pygame.Surface((w, h), pygame.SRCALPHA)
        bg.fill((30, 20, 10, 160))
        self.screen.blit(bg, (x, y))
        pygame.draw.rect(self.screen, (180, 150, 100, 180), pygame.Rect(x, y, w, h), 1)
        self.screen.blit(text_surf, (x + pad_x, y + pad_y))

    def _draw_message(self, message):
        # Draw message in center of screen
        message_font = pygame.font.Font(None, 36)
        text = message_font.render(message, True, (255, 0, 0))
        text_rect = text.get_rect(center=(self.screen.get_width()/2, self.screen.get_height()/2))
        pygame.draw.rect(self.screen, (255, 255, 255), text_rect.inflate(20, 20))
        pygame.draw.rect(self.screen, (0, 0, 0), text_rect.inflate(20, 20), 2)
        self.screen.blit(text, text_rect)
