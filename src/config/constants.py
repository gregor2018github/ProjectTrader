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
DATA_PATH = os.path.join(MAIN_PATH, "assets", "data")     # goods.json, recipes.json (src/sim/data.py)
MAP_PATH = os.path.join(MAIN_PATH, "assets", "tiles", "Map1.tmx")
SAVE_SECRET_KEY = "MerchantsRise_sv1_k9xP"

# SIMULATION CONSTANTS

SCREEN_WIDTH = 1650
SCREEN_HEIGHT = 1064
SIDEBAR_WIDTH = 110
MODULE_WIDTH = (SCREEN_WIDTH) // 2  # 734 pixels per module
MAX_RECULCULATIONS_PER_SEC = 60
TILE_SIZE = 32
PLAYER_SPEED = 120                  # pixels per second
PLAYER_DIAGONAL_SPEED_FACTOR = 0.8  # per-axis multiplier when moving diagonally (0.707 = same speed as straight)
MAX_FRAMES_PER_SEC = 100           # default for the "FPS Limit" setting (settings_store "fps_limit")

# TIME STEP CONSTANTS (game minutes per tick for each speed level; MAX_RECULCULATIONS_PER_SEC ticks a second)
TIME_STEP_LEVEL_1 = 0.0             # Level 1: Paused
TIME_STEP_LEVEL_2 = 0.02             # Level 2: Slow
TIME_STEP_LEVEL_3 = 0.05             # Level 3: Normal (3 game minutes a second: a day takes 8 real minutes)
TIME_STEP_LEVEL_4 = 1.00            # Level 4: Fast
TIME_STEP_LEVEL_5 = 6.00            # Level 5: Fastest

# MARKET OPENING HOURS (trading is only possible while the market is open)
# Each trader draws his own times from these windows every night (hours of the day, 24 = midnight).
# A booth shuts once its last trader has left the stall and opens when the first is back.
MARKET_CLOSE_WINDOW = (22.0, 24.0)  # Traders pack up and walk home between 22:00 and midnight
MARKET_OPEN_WINDOW = (4.75, 6.75)   # Traders set off for their stalls between 04:45 and 06:45

# TOWNSFOLK OUT WALKING (see src/models/town_life.py)
# Townsfolk stroll from one front door on the Tiled "Doors" layer to another.
# The town tops the streets back up whenever fewer than this many are out;
# anyone already walking when night falls still finishes their way home.
STROLLERS_BY_DAY = 9                # People out on the streets during the day...
STROLLERS_BY_NIGHT = 3              # ...and at night,
STROLLERS_IN_RAIN_BY_DAY = 5        # and as many while it rains (no new ones go out till fewer are)
STROLLERS_IN_RAIN_BY_NIGHT = 2
STROLL_RAIN_FROM = 0.15             # Rain this hard (Weather.rain, 0 to 1) keeps people in; a passing sprinkle does not
STROLL_NIGHT_START_HOUR = 21.0      # From 21:00 the streets thin out
STROLL_NIGHT_END_HOUR = 6.0         # From 06:00 they fill up again
STROLL_RELEASE_SECONDS_MIN = 1.0    # Shortest real-time gap between two people stepping out
STROLL_RELEASE_SECONDS_MAX = 5.0    # Longest such gap
# Knocking on a house someone is in may bring them to the door for a moment.
KNOCK_ANSWER_CHANCE = 0.50          # Chance that a knock is answered at all
KNOCK_ANSWER_SECONDS = 5.0          # Real seconds they stand outside before going back in
# Giving a coin to one of the town's poor, from the figurine menu.
ALMS_COIN = 1                       # Coins handed over per gift
ALMS_CATEGORY = "Alms"              # Bookkeeping subcategory a gift is booked under
# Meals for the poor, given to the church in goods from the player's stock (name, goods and how many of each).
# They are booked as donations at the goods' market price on the day.
CHURCH_FEASTS = [
    ("Meal for the Poor", {"Bread": 45, "Fish": 20, "Beer": 15}),
    ("Feast for the Poor", {"Bread": 45, "Meat": 30, "Wine": 15, "Beer": 48}),
]
CHURCH_FEAST_CATEGORY = "Church Feasts"  # Bookkeeping subcategory the goods given for them are booked under

# GAME BALANCE CONSTANTS AT START OF THE GAME

MARKET_PRESIMULATION_DAYS = 224     # Days the whole economy runs before the game starts (two years, about 0.9 s of loading at
                                    # 4 ms a day), so the charts open with a history and wages, purses and workshops have
                                    # nearly settled (after 60 the commons' wage was still climbing and they bought no luxuries)

# MARKET VOLUME: a good's price is its reference (outside) price times a factor from how much of it the
# market holds, measured against its target stock (days of demand), times a little noise. See docs/pricing.md.
MARKET_VOLUME_SCARCE_RATIO = 0.9    # Below this share of the normal volume the good is scarce and dearer
MARKET_VOLUME_GLUT_RATIO = 1.1      # Above this share of the normal volume the good is glutted and cheaper
MARKET_VOLUME_ELASTICITY = 0.7      # How strongly the price answers a volume past those thresholds
MARKET_VOLUME_FACTOR_MIN = 0.4      # The cheapest a glut can make a good, as a factor on its price
MARKET_VOLUME_FACTOR_MAX = 3.0      # The dearest scarcity can make a good, as a factor on its price
PRICE_TICK_MINUTES = 30             # Prices move (and the price chart gets a point) every this many game minutes
PRICE_TICKS_PER_DAY = 24 * 60 // PRICE_TICK_MINUTES

# THE LIVING MARKET (src/sim/, docs/p1_living_market.md); per-good and per-class values are in assets/data/
MARKET_OPEN_HOUR = 6                # Households, workshops and merchants trade in hourly slices from this hour...
MARKET_CLOSE_HOUR = 18              # ...to this one (12 slices a day)
PRICE_NOISE_PERSISTENCE = 0.98      # Share of the price noise's log kept each price tick (half-life about 17 game hours)
PRICE_NOISE_CLAMP = 0.1             # The noise never moves a price more than this far (as a log, so about ±10 %)
TARGET_STOCK_GLIDE = 0.1            # Share of the gap to yesterday's demand the demand average closes each day (target stock follows it)
PURSE_START_DAYS = 5                # A class's purse when a game starts, in days of its income
SAVINGS_CAP_DAYS = 10               # A class saves at most this many days of income; the rest leaves town (rents and dues)
SAVINGS_RELEASE = 0.2               # Share of its savings a class adds to a day's budget after a day its needs went unmet
# Workshops (src/sim/systems/production.py); per building type in assets/data/buildings.json
MARGIN_FLOOR = 0.0                  # A workshop whose batch earns this margin (or less) on its costs wants to run at nothing...
MARGIN_FULL = 0.3                   # ...and at full capacity from this margin up, linearly between
UTILISATION_GLIDE = 0.2             # Share of the gap to that a workshop's utilisation closes each day
GROWTH_DESIRE = 0.9                 # A workshop wanting at least this utilisation, and able to plan it (hands, cash), has a busy day...
GROWTH_BUSY_DAYS = 14               # ...and after this many busy days...
GROWTH_WINDOW_DAYS = 21             # ...within the last this many it grows, if it (or its owner) can pay (a window, so one slack day doesn't reset it)
GROWTH_STEP = 0.1                   # Growth as a share of its capacity...
GROWTH_MIN_STEP = 0.5               # ...but at least this many batches a day (so a workshop shrunk to nothing can come back)
SHRINK_LOSS_DAYS = 42               # A workshop losing money on this many days...
SHRINK_WINDOW_DAYS = 56             # ...within the last this many (two seasons; slower than growth) shrinks...
SHRINK_STEP = 0.05                  # ...by this share of its capacity
HIRING_MARGIN_FLOOR = 0.01          # A class short of hands shares them by workers wanted x margin, the margin counted at least this
                                    # (so a workshop at a loss still gets a few); a stand-in for wage offers per workshop (P3)
WAGE_GLIDE = 0.1                    # Each day a class's wage moves this share of the way to its cap when hands are short (all
                                    # its free hands wanted twice over), or to its base income when nobody is hired; less, the less tense
# Owners with surplus_to "treasury_with_tribute" (the town): profits kept up to a cap, the rest paid to the lord
TREASURY_CAP_DAYS = 56              # The treasury holds at most this many days of the owner's average net income (two seasons)...
TREASURY_INCOME_GLIDE = 1 / 28      # ...that average following each day's net income by this share (about a year's memory)
START_DATE = "01.01.1500"           # Where the clock starts, format: dd.mm.yyyy; the game calendar's first day (see below)
# CALENDAR (src/sim/calendar.py): the clock runs on as an ordinary datetime, but the
# calendar shown is compressed so a game can span generations: a year is four seasons
# (Spring, Summer, Autumn, Winter) of one week each, START_DATE being the 1st of Spring.
DAYS_PER_SEASON = 7                 # Days in a season, Monday to Sunday
CALENDAR_START_YEAR = 1500          # The year of START_DATE in the game calendar
START_TIME = "08:00"                # When the simulation time starts, format: HH:MM
INITIAL_DAILY_COST_OF_LIVING = 2    # Initial daily cost of living for the player
STARTING_MONEY = 100                # Starting money for the player
INITIAL_TRANSACTION_COST = 2        # Cost per transaction at the market
# MERCHANT RANK: titles the player climbs and can lose again, see src/models/merchant_rank.py.
# A rank asks for all four at once: net wealth, property value (buildings at their buy price),
# lifetime trade volume (goods bought plus goods sold, in coins) and reputation.
MERCHANT_RANKS = (
    # name,        net wealth, property,    volume, reputation
    ("Peddler",            0,        0,          0,     0),
    ("Hawker",           500,        0,      1_000,     5),   # no property: buildings are first bought as a Hawker
    ("Chapman",        1_800,      350,      4_000,    15),
    ("Trader",         6_300,    1_250,     17_000,    30),
    ("Merchant",      22_000,    4_500,     70_000,    60),
    ("Burgher",       80_000,   16_000,    290_000,   100),
    ("Guildmaster",  280_000,   56_000,  1_200_000,   160),
    ("Patrician",  1_000_000,  200_000,  5_000_000,   250),
)
RANK_GRACE_DAYS = 14                # Days a rank's conditions may stay unmet before it is lost
RANK_UNLOCKS = {                    # What a rank opens, by the rank first reaching it; never taken away again
    "buy_buildings": "Hawker",
}
REPUTATION_SEASONAL_DECAY = 0.025   # Share of the reputation that fades at the start of each season (about 10% a 30 days, as before)
DONATION_REPUTATION_SCALE = 100.0   # Reputation for giving away as much as one's wealth (ln 2 of it, see MerchantRank)
DONATION_REPUTATION_WEALTH_FLOOR = 200.0  # The least wealth a gift is measured against, so a poor man's coin counts but not endlessly
SLOT_SIZE = 20                      # units of one good a storage slot holds, unless a warehouse's Buy_slot_size says otherwise
STARTING_STORAGE_SLOTS = 5          # slots of the starting storage, which is no building
INITIAL_STORAGE_CAPACITY = STARTING_STORAGE_SLOTS * SLOT_SIZE  # how many items the player can store at the start
PACK_SLOTS = 10                     # slots of the pack the player carries goods in
PACK_SLOT_SIZE = 1                  # units of one good a pack slot holds: what the player carries by hand

# TRADING LICENSE CONSTANTS
# A new game's licences (and every licence's fee per season) are in assets/data/goods.json
LICENSE_SEASON_OPTIONS = [1, 2, 4, 8, 12]  # Durations a license can be bought for, in seasons (4 make a year)

# POPULATION GROUP SHARES
# The values represent the target share of total population per social group.
POPULATION_SHARE_POOR = 0.25
POPULATION_SHARE_COMMONS = 0.52
POPULATION_SHARE_MIDDLING_SORT = 0.20
POPULATION_SHARE_NOBILITY = 0.03

# POPULATION SIMULATION CONSTANTS
STARTING_OCCUPANCY = 0.8            # Share of each house's Max_inhabitants living in it when a game starts (rounded per house)
HAPPINESS_START = 80                # Every class's happiness, and the town's, when a game starts
HAPPINESS_THRESHOLD = 70.0          # Below this average happiness, people move out; above, they move in
HAPPINESS_FROM_NEEDS_MIN = 10.0     # Target happiness of a class that got nothing it needs
HAPPINESS_FROM_NEEDS_MAX = 85.0     # Target happiness of a class that got all it needs, every tier
HUNGER_THRESHOLD = 0.6              # Below this basic fulfilment a class goes hungry...
HUNGER_PENALTY = 20.0               # ...and its target happiness drops by this much more
HAPPINESS_GLIDE = 0.05              # Share of the gap to its target a class's happiness closes each hour
POPULATION_MIN_FACTOR = 0.3         # A class can shrink to 30 % of its share of the town's housing at the least...
POPULATION_MAX_FACTOR = 1.05        # ...and grow to 105 % of it at the most (crowding, not this, should set its size)
MAX_DAILY_POPULATION_CHANGE = 0.01  # Max daily population change rate (1% per day at extreme happiness)
OVERPOP_MALUS_PER_PERCENT = 3       # Each 1% of overpopulation reduces happiness score by this many points
NEAR_CAPACITY_THRESHOLD = 90.0      # Fill grade (%) above which crowding penalty begins (before full overpopulation)
NEAR_CAPACITY_MALUS_PER_PERCENT = 1 # Each 1% fill grade above threshold reduces happiness equilibrium by this many points
UNDERPOP_THRESHOLD_LOW = 60.0       # Fill grade (%) below which the strong underpopulation bonus applies
UNDERPOP_THRESHOLD_HIGH = 75.0      # Fill grade (%) below which the mild underpopulation bonus applies
UNDERPOP_BONUS_LOW = 3              # Happiness equilibrium bonus when fill grade is below UNDERPOP_THRESHOLD_LOW
UNDERPOP_BONUS_HIGH = 1             # Happiness equilibrium bonus when fill grade is below UNDERPOP_THRESHOLD_HIGH

# The fee every license costs once, whatever its length; each licence's license_fee in goods.json adds its price per season
BASE_CONTRACT_FEE = 50
# The goods in the bottom bar's three quick-trade slots at each market square
# (an "Areas" rectangle named Market_Area...) when a game starts. A square not
# listed starts with the first three goods its booths sell.
# The quick-trade quantity a good starts with: the units worth about QUICK_TRADE_LOT_VALUE at its
# outside price, rounded to the nearest of QUICK_TRADE_STEPS (by ratio), at least 1
QUICK_TRADE_LOT_VALUE = 15
QUICK_TRADE_STEPS = (1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 20, 25, 30, 40, 50)
# A new game (and a save without pins) starts with this many goods pinned to the top bar, the first
# of goods.json; it holds as many, so it is full without scrolling
TOP_BAR_DEFAULT_PINS = 10
DEFAULT_QUICKTRADE_SLOTS = {
    "Market_Area": ["Wood", "Stone", "Iron"],
    "Market_Area_Northwest": ["Herbs", "Salt", "Candle"],
}


# UI CONSTANTS
CHART_TIME_MARKER_UNIT = "Season"     # Units for vertical chart lines: "Day", "Season" (one week), "Year"

# MAP AND SOUND CONSTANTS

MUSIC_VOLUME = 0.25                   # Default background music volume (1.0 is 100%)
FOOT_STEP_VOLUME = 0.25               # Volume for footstep sounds (1.0 is 100%)
CHURCH_BELL_VOLUME = 0.25             # Maximum volume for church music (1.0 is 100%)
SHEEP_VOLUME = 0.65                   # Maximum volume for sheep sounds (1.0 is 100%)
KNOCK_VOLUME = 0.8                    # Volume for door knock sounds (1.0 is 100%)
SPLASH_VOLUME = 0.9                   # Volume for well splash sounds (1.0 is 100%)
DOOR_VOLUME = 0.45                    # Maximum volume for NPCs opening/closing their front doors (1.0 is 100%)
COIN_THROW_COST = 1                   # Gold coins deducted when throwing a coin into the well
WELL_WISH_PROBABILITY = 0.05          # Probability of triggering a wish when throwing a coin (1.0 = 100% for testing)
WELL_WISH_SHOCK_FACTOR = 0.4          # Price shock magnitude from a well wish (40%)
WELL_WISH_DURATION_DAYS = 5           # Number of days the well price shock lasts
SHEEP_SOUND_MAX_DISTANCE = 900.0     # World pixels beyond which sheep are completely silent
DOOR_SOUND_MAX_DISTANCE = 700.0      # World pixels beyond which NPC doors are completely silent
# Someone out in town coughing now and then (models/coughs.py): game hours on the map
# between two coughs (1 to 2 a day), and when nobody is near, how long until it tries again
COUGH_EVERY_HOURS = (12.0, 24.0)
COUGH_RETRY_HOURS = 0.5
COUGH_VOLUME = 0.5                    # Volume of a cough right beside the player (1.0 is 100%)
COUGH_MAX_DISTANCE = 800.0            # World pixels; NPCs farther off are never the ones coughing
COUGH_FALLOFF = 1.6                   # Volume is (1 - distance / max) to this power: far coughs barely audible
# Volume of the mill's gear loop (1.0 is 100%) by distance from its walls in tiles,
# blended linearly between the steps; silent beyond the last
MILL_VOLUME_BY_DISTANCE = ((0, 0.5), (2, 0.34), (5, 0.16), (10, 0.06), (15, 0.02), (20, 0.0))
FOREST_BIRDS_VOLUME = 0.6             # Volume of the birdsong deep in a wood by day (1.0 is 100%)
FOREST_RADIUS_TILES = 8.0             # Trees this near the player count towards a wood, the nearer the more
FOREST_FULL_COVER = 3.0               # That many trees' worth around the player is a wood; fewer, softer birds
# How much the birds sing by hour of the day (0 to 1), blended linearly between the
# steps: from first light at 5:00 to full song by 6:30, fading out from 19:00 into nightfall at 20:30
BIRDS_BY_HOUR = ((5.0, 0.0), (6.5, 1.0), (19.0, 1.0), (20.5, 0.0))
CRICKETS_VOLUME = 0.5                 # Volume of the crickets out in nature at night (1.0 is 100%)
TOWN_RADIUS_TILES = 12.0              # Buildings this near the player make it town, the nearer the more
TOWN_FULL_COVER = 2.0                 # That many buildings' worth around the player silences the crickets
# How much the crickets chirp by hour of the day (0 to 1): taking over from the birds at
# dusk, from 19:30 to full by 21:00, and falling silent at dawn, from 4:30 to 6:00
CRICKETS_BY_HOUR = ((4.5, 1.0), (6.0, 0.0), (19.5, 0.0), (21.0, 1.0))
# Owls in the woods at night (models/owls.py): game hours of night deep in a wood between two
# calls (fewer trees, longer), how loud the nearest call is (1.0 is 100%), the share of that a
# call gets, drawn at random (near or far), and how far to one side it may come from (0 to 1)
OWL_EVERY_HOURS = (1.0, 3.0)
OWL_VOLUME = 0.5
OWL_LOUDNESS = (0.15, 1.0)
OWL_PAN = 0.6
# How much the owls call by hour of the day (0 to 1): from 20:00, all night from 21:30, falling silent from 5:00 to 6:00
OWLS_BY_HOUR = ((5.0, 1.0), (6.0, 0.0), (20.0, 0.0), (21.5, 1.0))
# Dogs barking in town (models/dogs.py): game hours in town between two barks (2 to 3 a day;
# at the edge of town longer), how loud the nearest is (1.0 is 100%), the share of that a bark
# gets, drawn at random (near or far), and how far to one side it may come from (0 to 1)
DOG_EVERY_HOURS = (8.0, 12.0)
DOG_VOLUME = 0.5
DOG_LOUDNESS = (0.25, 1.0)
DOG_PAN = 0.7
DOG_BOUT_BARKS = (2, 5)               # A dog barking single barks barks this many times,
DOG_BOUT_GAP_S = (0.35, 1.1)          # this many real seconds apart
DOG_CHORUS_HOURS = (21, 5)            # From and to which hour the village's dogs may answer each other far off,
DOG_CHORUS_CHANCE = 0.35              # in this share of the barks then
# Volume of the rivers' and the sea's loops (1.0 is 100%) by distance from the nearest water of each,
# in tiles from the water tile's centre (so about 1 standing on the bank), blended linearly; silent beyond the last
RIVER_VOLUME_BY_DISTANCE = ((1, 0.35), (3, 0.25), (6, 0.12), (10, 0.04), (14, 0.0))
SEA_VOLUME_BY_DISTANCE = ((1, 0.5), (4, 0.4), (8, 0.22), (14, 0.08), (20, 0.0))
# Volume of the market crowd (1.0 is 100%) by distance from the nearest open booth's walls, in tiles,
# blended linearly; silent beyond the last, and once every booth near is shut
MARKET_VOLUME_BY_DISTANCE = ((0, 0.4), (4, 0.32), (11, 0.15), (20, 0.05), (28, 0.0))
# Game hours a booth's crowd takes to swell to its full after the booth opens, and to die away after it shuts
# (an S-curve, so it starts and ends gently)
MARKET_SWELL_HOURS = 1.0
MARKET_GROUP_TILES = 12               # Booths this near one another (in tiles) stand in one market
# Each market's crowd recording, given out from the market with the most booths down (and round again if there are more markets)
MARKET_LOOPS = ("amb_town_market_A_loop", "amb_town_market_B_loop")
# Volume of the quiet streets (1.0 is 100%) by how many houses are around, counted as the crickets' town is
# (each within TOWN_RADIUS_TILES counting 1 on the spot down to 0 at that radius, booths not counted),
# blended linearly: one house on its own comes to 1 at most, so it stays silent; it gives way to a market's crowd
STREETS_BY_HOUSES = ((1.4, 0.0), (2.5, 0.1), (4.0, 0.18))
MAP_START_ZOOM = 1.75                 # Initial zoom level for the map view (bigger = zoomed in)
START_X_POSITION = 4308               # Player starting X position on the map
START_Y_POSITION = 4553               # Player starting Y position on the map
FOG_REVEAL_RADIUS_TILES = 7.0         # Fog of war: land within this many tiles of the player is fully revealed
FOG_FADE_TILES = 3.0                  # Fog of war: beyond that radius, revealing fades out over this many tiles
FOG_CELLS_PER_TILE = 4                # Fog of war: explored cells per tile each way (finer = rounder edge)

# LIGHTING CONSTANTS (Hours are decimal, for example 18.5 = 18:30)

# The length of the day over the year (src/models/daylight.py): what goes by daylight is set out for a day of
# Spring or Autumn (full daylight 8:00 to 17:00, night 21:00 to 4:00, the window lights from 18:30); in the middle
# of Summer the dawn comes this much earlier and the dusk this much later, in the middle of Winter the other way
# round, and in between by degrees
DAYLIGHT_DAWN_SHIFT_HOURS = 1.0      # Midsummer: full daylight from 7:00; midwinter: from 9:00
DAYLIGHT_DUSK_SHIFT_HOURS = 1.5      # Midsummer: night from 22:30; midwinter: from 19:30 (the sun setting from 15:30)
# The light's mood by season, multiplied into the map's light at every hour (255 leaves a colour as it is);
# full in the middle of each season and blended between them, so a season's turn shows no jump
SEASON_LIGHT_TINT = {
    "Spring": (255, 255, 255),       # clear
    "Summer": (255, 255, 255),       # clear
    "Autumn": (255, 218, 182),       # warm, reddish
    "Winter": (184, 208, 255),       # cold, bluish
}
DAYLIGHT_TWILIGHT_STRETCH = 0.5      # In Autumn and Winter the dawns and dusks last up to this much longer (0.5: 6 hours, not 4),
                                     # the most where Autumn turns to Winter, none in Spring and Summer

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

# WEATHER CONSTANTS (models/weather.py; hours are game hours, 20 s each at normal speed)

# The spells the weather goes through: how hard it rains (0 to 1), how overcast it is (0 to 1),
# how much the wind slants the rain (sideways per unit fallen), how thick the fog is (0 to 1,
# before FOG_BY_HOUR), how long a spell lasts (shortest, longest hours, and optionally the median:
# then half are shorter than that and the long ones grow rarer the longer they are) and the
# weights of what comes after it.
# A shower is one run through drizzle, rain, now and then a downpour, and clearing (a last
# light drizzle): mostly 6 to 12 hours, now and then most of a day of rain. It only comes out of an
# overcast sky, which brings one about every other time; with the clear spells between, that is
# 1 to 2 showers a week.
# A thunderstorm ("storm", the only spell with a "storm" level, 0 when left out) now and then breaks out
# of the rain or a downpour: as hard as it rains, a darker sky (STORM_TINT in daylight.py) and lightning.
# Mist comes out of a clear sky or after a shower, still air either way, and now and then
# thickens into fog; both hang longest at night and in the early morning (FOG_BY_HOUR).
WEATHER_SPELLS = {
    "clear":    {"rain": 0.0,  "clouds": 0.0,  "wind": 0.05, "fog": 0.0, "hours": (30.0, 80.0),
                 "next": {"overcast": 0.8, "mist": 0.2}},
    "overcast": {"rain": 0.0,  "clouds": 0.6,  "wind": 0.10, "fog": 0.0, "hours": (2.0, 5.0),
                 "next": {"clear": 0.45, "drizzle": 0.55}},
    "drizzle":  {"rain": 0.3,  "clouds": 0.75, "wind": 0.08, "fog": 0.1, "hours": (1.0, 2.5),
                 "next": {"rain": 1.0}},
    "rain":     {"rain": 0.65, "clouds": 0.9,  "wind": 0.18, "fog": 0.0, "hours": (3.0, 24.0, 5.0),
                 "next": {"clearing": 0.6, "downpour": 0.3, "storm": 0.1}},
    "downpour": {"rain": 1.0,  "clouds": 1.0,  "wind": 0.30, "fog": 0.0, "hours": (1.5, 3.5),
                 "next": {"clearing": 0.8, "storm": 0.2}},
    "storm":    {"rain": 1.0,  "clouds": 1.0,  "wind": 0.40, "fog": 0.0, "storm": 1.0, "hours": (1.0, 3.0),
                 "next": {"rain": 0.6, "clearing": 0.4}},
    "clearing": {"rain": 0.2,  "clouds": 0.6,  "wind": 0.08, "fog": 0.2, "hours": (1.0, 1.5),
                 "next": {"clear": 0.65, "mist": 0.35}},
    "mist":     {"rain": 0.0,  "clouds": 0.25, "wind": 0.02, "fog": 0.45, "hours": (4.0, 9.0),
                 "next": {"clear": 0.5, "overcast": 0.15, "fog": 0.35}},
    "fog":      {"rain": 0.0,  "clouds": 0.4,  "wind": 0.01, "fog": 1.0, "hours": (6.0, 12.0),
                 "next": {"mist": 1.0}},
}
# How the seasons (game_calendar.py) bend the weather: per season, factors on the weights of the spells
# that may come next ("next": how often a kind follows), on how long a kind lasts ("hours") and on all fog
# ("fog": the spells' and the wet ground's, so 0 keeps every mist away); a kind or season not named keeps
# its WEATHER_SPELLS values. Showers start from an overcast sky (drizzle), so their weight sets how often it
# rains, and longer or shorter clear spells space them out. A thunderstorm comes only out of rain or a
# downpour, so its weight decides which showers turn stormy: none but in Summer, and there most of them.
# Spring and Winter are WEATHER_SPELLS without the storms. Summer is drier, without mist or fog, and its
# showers mostly end in thunder; Autumn is wetter and foggy. Over many years that makes about this share
# of hours with rain / with fog, and storms a season:
# Spring 8% / 6%, none; Summer 6% / 0%, 0.5 (one every other summer); Autumn 16% / 16%, none; Winter 9% / 8%,
# none. A fog spell running on into Summer, with nothing allowed to follow it, clears up (WEATHER_START).
WEATHER_BY_SEASON = {
    "Spring": {"next": {"storm": 0.0}},
    "Summer": {"next": {"drizzle": 0.35, "mist": 0.0, "fog": 0.0, "storm": 10.0, "rain": 0.5}, "hours": {"clear": 1.4},
               "fog": 0.0},
    "Autumn": {"next": {"drizzle": 4.5, "overcast": 2.0, "mist": 2.0, "fog": 2.0, "storm": 0.0},
               "hours": {"clear": 0.5, "mist": 1.2, "fog": 1.2}},
    "Winter": {"next": {"storm": 0.0}},
}
WEATHER_START = "clear"              # The weather a new game starts in, somewhere along the spell (not always at its start)
WEATHER_GLIDE_PER_HOUR = 0.6         # How fast rain, clouds and wind change towards a new spell's, per game hour (1.0 is all of it)
RAIN_FROM_CLOUDS = 0.4               # Rain only sets in once the sky is this overcast, and is at full strength when the spell's clouds are there
WEATHER_WIND_TURN_CHANCE = 0.2        # Chance a new spell's wind blows from the other side

# Crops on the fields (crop_growth.py) follow the seasons: bare (ploughed) through the winter, sown at FIELD_SOW_DAY,
# growing through its crop.json's stages in equal parts and harvested at FIELD_HARVEST_DAY. Days of the year count
# from the 1st of Spring (0); a year is 28 days (game_calendar.py). A field's Tiled object may set its own Sow_day
# and Harvest_day; otherwise each field is sown and harvested a little earlier or later than the others.
FIELD_SOW_DAY = 0.0                  # Sown on the 1st of Spring; the sprouts come up from here
FIELD_HARVEST_DAY = 21.0             # Harvested at the end of Autumn, so the field lies bare all Winter
FIELD_SEASON_JITTER_DAYS = 1.0       # Each field is sown and harvested up to this many days earlier or later, the same every game
FIELD_PLANT_SPREAD_DAYS = 2.0        # The plants of a field change stage within this many days of each other; the furrows fade over as long
FIELD_STILL_STAGES = 2               # The first stages with sprites (sprouts, young) stand still in the wind
RAIN_DROPS_PER_MEGAPIXEL = 520        # Drops in the air per million pixels of map view at full rain
RAIN_SPLASH_SHARE = 0.6               # Share of the near drops that are seen to splash where they land
# Lightning (models/lightning.py), in real seconds while the map runs, at full storm
LIGHTNING_FROM_STORM = 0.5           # No lightning until the storm level is this high; more often the higher it is
LIGHTNING_EVERY_S = (6.0, 30.0)      # Seconds between strikes at full storm, shortest and longest
LIGHTNING_FLASH_ADD = 150            # How much a flash at its brightest adds to the map's colours (0 to 255)
THUNDER_CHANCE = 0.85                # Share of the strikes heard as thunder; the rest are too far
THUNDER_DELAY_S = (0.3, 5.0)         # Seconds from flash to thunder, near to far
THUNDER_VOLUME = (0.9, 0.35)         # Volume of the thunder (1.0 is 100%), near and far
RAIN_VOLUME = 0.45                    # Volume of the rain loops at their fullest (1.0 is 100%)
# The rain's recordings, lightest first, each with its share of RAIN_VOLUME by how hard it rains
# (Weather.rain: clearing 0.2, drizzle 0.3, rain 0.65, downpour 1.0), blended linearly between the
# steps, so one fades into the next as the rain grows heavier or eases off
RAIN_LAYERS = (
    ("amb_rain_light_2_loop", ((0.0, 0.0), (0.03, 0.6), (0.15, 1.0), (0.25, 1.0), (0.4, 0.0))),
    ("amb_rain_light_loop",   ((0.15, 0.0), (0.3, 1.0), (0.45, 0.85), (0.6, 0.0))),
    ("amb_rain_medium_loop",  ((0.4, 0.0), (0.55, 0.8), (0.7, 1.0), (0.85, 0.7), (1.0, 0.35))),
    ("amb_rain_heavy_loop",   ((0.7, 0.0), (0.85, 0.7), (1.0, 1.0))),
)
PUDDLE_FILL_PER_HOUR = 0.6           # How fast full rain wets the ground for puddles, per game hour (1.0 is soaked)
PUDDLE_DRY_PER_HOUR = 0.3            # How fast the ground dries without rain, per game hour, in sunshine (half as fast under full cloud)
PUDDLE_PATH_TILES_EACH = 24          # One puddle for about every that many tiles of road and paving
PUDDLE_OFF_PATH_SHARE = 0.08         # Off the roads and paving (grass, sand) only this share of that
PUDDLE_SIZE_TILES = (0.8, 1.6)       # A full puddle's width in tiles, smallest and largest
PUDDLE_WIDE_SHARE = 0.2              # Share of the puddles that are longer, no taller than the largest above
PUDDLE_WIDE_TILES = (1.8, 3.2)       # Their width in tiles, smallest and largest
FOG_GLIDE_PER_HOUR = 0.35            # How fast the fog thickens or lifts towards its target, per game hour (slower than the rain)
# How much of a spell's fog there is at each hour (hour, share), between them smoothly: it
# hangs at night and in the early morning, and the sun mostly burns it off by noon
FOG_BY_HOUR = ((0.0, 1.0), (7.0, 1.0), (10.0, 0.6), (13.0, 0.35), (17.0, 0.4), (20.0, 0.75), (23.0, 1.0), (24.0, 1.0))
FOG_FROM_WETNESS = 0.3               # Soaked ground breathes this much fog of its own (before FOG_BY_HOUR), whatever the spell
FOG_DRIFT_TILES_PER_S = 0.35         # How fast the fog banks drift, in tiles per second, still air included
FOG_WISPS_PER_MEGAPIXEL = 16         # Loose wisps of fog drifting about per million pixels of map view at full fog
FOG_CLEAR_RADIUS_TILES = 6.0         # Round the player the fog is thinner, out to this far
# Snow (models/weather.py, snow.py, snow_cover.py, roof_snow.py). In Winter the rain falls as snow: the share of it
# that does, by the day of the year (0 the 1st of Spring, 28 days a year; between the points in straight lines, the
# year wrapping round), so the first and last days of Winter bring sleet, half rain and half snow, and it thaws on
# the last day of Winter.
SNOW_BY_DAY_OF_YEAR = ((0.0, 0.0), (21.0, 0.0), (21.75, 1.0), (27.25, 1.0), (28.0, 0.0))
SNOW_FILL_PER_HOUR = 0.12            # How fast full snowfall covers the ground, per game hour (1.0 is deep snow everywhere)
SNOW_MELT_PER_HOUR = 0.1             # How fast the snow thaws where none would fall any more, per game hour
SNOW_RAIN_MELT_PER_HOUR = 0.25       # How much faster full rain washes it away, per game hour
SNOW_MELT_WETS = 1.5                 # Thawing snow wets the ground by this much per unit of cover melted (puddles after a thaw)
SNOW_FLAKES_PER_MEGAPIXEL = 900      # Flakes in the air per million pixels of map view at full snowfall
SNOW_ROOFS_FROM = (0.08, 0.4)        # The roofs whiten from this much snow on the ground and are fully white at the second
# How much rain hushes the birds and the crickets (0 none, 1 silent at full rain)
RAIN_HUSHES_BIRDS = 0.9
RAIN_HUSHES_CRICKETS = 0.7
RAIN_HUSHES_OWLS = 0.9

# LOAN SYSTEM CONSTANTS

OVERDRAFT_DAILY_RATE = 0.02          # 2% of negative balance charged per day as penalty
LOAN_BASE_RATES = [                  # (wealth_threshold, rate per LOAN_RATE_DAYS) — lower wealth = higher rate
    (200,  0.54),
    (500,  0.42),
    (2000, 0.30),
    (float('inf'), 0.21),
]
LOAN_DURATION_FACTORS = [            # (max_days, factor) — longer term = higher total interest
    (10,  1.0),
    (30,  1.1),
    (60,  1.2),
    (90,  1.35),
]
LOAN_EQUITY_RATIOS = [               # (wealth_threshold, equity_ratio) — determines max loan size
    (200,  0.50),
    (500,  0.60),
    (2000, 0.70),
    (float('inf'), 0.80),
]
LOAN_RATE_DAYS = 365                # The days LOAN_BASE_RATES are a rate for; the loan dialog shows them per game year
LOAN_MAX_DURATION_DAYS = 90         # Maximum loan term in days
LOAN_MIN_AMOUNT = 50                # Minimum loan amount
LOAN_MIN_DAILY_PCT = 5              # Minimum % of principal repaid through daily installments
LOAN_SETTLEMENT_RATE_PENALTY = 0.5  # Additional interest multiplier at maximum settlement (0 = no penalty, 0.5 = +50%)

# DEBUGGING
SHOW_MAP_DEBUG = True                 # Set to True to show FPS, position and zoom on map view
