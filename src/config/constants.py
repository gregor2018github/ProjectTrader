"""Global constants and configuration settings for ProjectTrader.

This module contains system paths, screen dimensions, game balance parameters,
and other static values that define the game's environment.
"""

import os

# SYSTEM PATHS

MAIN_PATH = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
PICTURES_PATH = os.path.join(MAIN_PATH, "assets", "pictures")
FONTS_PATH = os.path.join(MAIN_PATH, "assets", "fonts")

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
CHURCH_BELL_VOLUME = 0.4              # Maximum volume for church music (1.0 is 100%)
MAP_START_ZOOM = 1.50                 # Initial zoom level for the map view (bigger = zoomed in)
START_X_POSITION = 1388               # Player starting X position on the map
START_Y_POSITION = 1316               # Player starting Y position on the map

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

# DEBUGGING
SHOW_MAP_DEBUG = True                 # Set to True to show FPS, position and zoom on map view
