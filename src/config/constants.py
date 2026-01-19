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
MAX_FRAMES_PER_SEC = 60

# TIME STEP CONSTANTS (minutes per tick for each speed level)
TIME_STEP_LEVEL_1 = 0.0             # Level 1: Paused
TIME_STEP_LEVEL_2 = 0.02             # Level 2: Slow
TIME_STEP_LEVEL_3 = 0.10             # Level 3: Normal
TIME_STEP_LEVEL_4 = 1.00            # Level 4: Fast
TIME_STEP_LEVEL_5 = 6.00            # Level 5: Fastest

# GAME BALANCE CONSTANTS AT START OF THE GAME

START_DATE = "01.01.1500"           # When the simulation time starts, format: dd.mm.yyyy
START_TIME = "12:00"                # When the simulation time starts, format: HH:MM
INITIAL_DAILY_COST_OF_LIVING = 2    # Initial daily cost of living for the player
STARTING_MONEY = 100                # Starting money for the player
INITIAL_TRANSACTION_COST = 2        # Cost per transaction at the market
INITIAL_STORAGE_CAPACITY = 100      # how many items the player can store at the start

# UI CONSTANTS
CHART_TIME_MARKER_UNIT = "Month"      # Units for vertical chart lines: "Day", "Week", "Month"

# MAP AND SOUND CONSTANTS

FOOT_STEP_VOLUME = 0.25               # Volume for footstep sounds (1.0 is 100%)
MAP_START_ZOOM = 1.25                 # Initial zoom level for the map view (bigger = zoomed in)

# DEBUGGING
SHOW_MAP_DEBUG = True                 # Set to True to show FPS, position and zoom on map view
