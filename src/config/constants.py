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

SCREEN_WIDTH = 1536
SCREEN_HEIGHT = 864
SIDEBAR_WIDTH = 110
MAX_RECULCULATIONS_PER_SEC = 60
TILE_SIZE = 32
PLAYER_SPEED = 120                  # pixels per second
MAX_FRAMES_PER_SEC = 60

# GAME BALANCE CONSTANTS AT START OF THE GAME

INITIAL_DAILY_COST_OF_LIVING = 2    # Initial daily cost of living for the player
STARTING_MONEY = 100                # Starting money for the player
INITIAL_TRANSACTION_COST = 2        # Cost per transaction at the market
INITIAL_STORAGE_CAPACITY = 100      # how many items the player can store at the start