"""Global constants and configuration settings for ProjectTrader.

This module contains system paths, screen dimensions, game balance parameters,
and other static values that define the game's environment.
"""

import os

# SYSTEM PATHS

MAIN_PATH = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
PICTURES_PATH = os.path.join(MAIN_PATH, "assets", "pictures")
FONTS_PATH = os.path.join(MAIN_PATH, "assets", "fonts")
SAVES_PATH = os.path.join(MAIN_PATH, "saves")
SAVE_SECRET_KEY = "MerchantsRise_sv1_k9xP"

# SIMULATION CONSTANTS

SCREEN_WIDTH = 1650
SCREEN_HEIGHT = 1064
SIDEBAR_WIDTH = 110
MODULE_WIDTH = (SCREEN_WIDTH) // 2  # 734 pixels per module
MAX_RECULCULATIONS_PER_SEC = 60
TILE_SIZE = 32
PLAYER_SPEED = 120                  # pixels per second
MAX_FRAMES_PER_SEC = 100

# TIME STEP CONSTANTS (minutes per tick for each speed level)
TIME_STEP_LEVEL_1 = 0.0             # Level 1: Paused
TIME_STEP_LEVEL_2 = 0.02             # Level 2: Slow
TIME_STEP_LEVEL_3 = 0.10             # Level 3: Normal
TIME_STEP_LEVEL_4 = 1.00            # Level 4: Fast
TIME_STEP_LEVEL_5 = 6.00            # Level 5: Fastest

# GAME BALANCE CONSTANTS AT START OF THE GAME

MARKET_PRESIMULATION_DAYS = 60      # Days of price history to simulate before the game starts
START_DATE = "01.01.1500"           # When the simulation time starts, format: dd.mm.yyyy
START_TIME = "08:00"                # When the simulation time starts, format: HH:MM
INITIAL_DAILY_COST_OF_LIVING = 2    # Initial daily cost of living for the player
STARTING_MONEY = 100                # Starting money for the player
INITIAL_TRANSACTION_COST = 2        # Cost per transaction at the market
INITIAL_STORAGE_CAPACITY = 100      # how many items the player can store at the start

# TRADING LICENSE CONSTANTS
# Each entry: (good_name, duration_in_months)
STARTING_LICENSES = [
    ("Wood", 2),
    ("Stone", 1),
]

# POPULATION GROUP SHARES
# The values represent the target share of total population per social group.
POPULATION_SHARE_POOR = 0.25
POPULATION_SHARE_COMMONS = 0.52
POPULATION_SHARE_MIDDLING_SORT = 0.20
POPULATION_SHARE_NOBILITY = 0.03

# POPULATION SIMULATION CONSTANTS
HAPPINESS_THRESHOLD = 70.0          # Below this average happiness, people move out; above, they move in
HAPPINESS_EQUILIBRIUM = 70.0        # Natural happiness setpoint for mean-reversion
POPULATION_MIN_FACTOR = 0.4         # A group can shrink to at most 40% of its map-defined base
POPULATION_MAX_FACTOR = 1.2         # A group can grow to at most 120% of its map-defined base
HAPPINESS_DRIFT_SIGMA = 1.5         # Std dev of hourly happiness noise (points)
MAX_DAILY_POPULATION_CHANGE = 0.01  # Max daily population change rate (1% per day at extreme happiness)
OVERPOP_MALUS_PER_PERCENT = 3       # Each 1% of overpopulation reduces happiness score by this many points
NEAR_CAPACITY_THRESHOLD = 90.0      # Fill grade (%) above which crowding penalty begins (before full overpopulation)
NEAR_CAPACITY_MALUS_PER_PERCENT = 1 # Each 1% fill grade above threshold reduces happiness equilibrium by this many points
UNDERPOP_THRESHOLD_LOW = 60.0       # Fill grade (%) below which the strong underpopulation bonus applies
UNDERPOP_THRESHOLD_HIGH = 75.0      # Fill grade (%) below which the mild underpopulation bonus applies
UNDERPOP_BONUS_LOW = 3              # Happiness equilibrium bonus when fill grade is below UNDERPOP_THRESHOLD_LOW
UNDERPOP_BONUS_HIGH = 1             # Happiness equilibrium bonus when fill grade is below UNDERPOP_THRESHOLD_HIGH

# monthly base contract fees for each good, used in contract overview and license acquisition
BASE_CONTRACT_FEE = 50
MONTHLY_CONTRACT_FEES = {
    "Wood": 50,
    "Stone": 50,
    "Iron": 100,
    "Wool": 100,
    "Hide": 100,
    "Fish": 50,
    "Wheat": 70,
    "Wine": 500,
    "Beer": 200,
    "Meat": 200,
    "Linen": 150,
    "Pottery": 150,
}

# UI CONSTANTS
CHART_TIME_MARKER_UNIT = "Month"      # Units for vertical chart lines: "Day", "Week", "Month"

# MAP AND SOUND CONSTANTS

FOOT_STEP_VOLUME = 0.25               # Volume for footstep sounds (1.0 is 100%)
CHURCH_BELL_VOLUME = 0.25             # Maximum volume for church music (1.0 is 100%)
SHEEP_VOLUME = 0.65                   # Maximum volume for sheep sounds (1.0 is 100%)
KNOCK_VOLUME = 0.8                    # Volume for door knock sounds (1.0 is 100%)
SHEEP_SOUND_MAX_DISTANCE = 1200.0     # World pixels beyond which sheep are completely silent
MAP_START_ZOOM = 1.75                 # Initial zoom level for the map view (bigger = zoomed in)
START_X_POSITION = 4298               # Player starting X position on the map
START_Y_POSITION = 4533               # Player starting Y position on the map

# LIGHTING CONSTANTS (Hours are decimal, for example 18.5 = 18:30)

# Regular windows
LIGHT_PROBABILITY = 0.4
LIGHT_START_HOUR_MIN = 18.5
LIGHT_START_HOUR_RANGE = 4.5
LIGHT_DURATION_MIN = 2.0
LIGHT_DURATION_RANGE = 4.0

# Building lights (Townhall, Church, etc.)
BUILDING_LIGHT_PROBABILITY = 1.0     # 1.0 = lights turn on every night
BUILDING_LIGHT_START_HOUR_MIN = 18.5
BUILDING_LIGHT_START_HOUR_RANGE = 3.0
BUILDING_LIGHT_DURATION_MIN = 4.0
BUILDING_LIGHT_DURATION_RANGE = 4.0

# Chimney smoke — ~1/3 of chimneys active each night
SMOKE_PROBABILITY = 0.33
SMOKE_START_HOUR_MIN = 17.5          # earliest activation: 17:30
SMOKE_START_HOUR_RANGE = 3.5         # latest activation: 21:00
SMOKE_DURATION_MIN = 4.0             # burns at least 4 hours
SMOKE_DURATION_RANGE = 5.0           # burns at most 9 hours

# DEBUGGING
SHOW_MAP_DEBUG = True                 # Set to True to show FPS, position and zoom on map view
