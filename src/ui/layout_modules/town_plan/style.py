"""Inks, paper and tuning of the town plan.

Everything that decides how the plan *looks* lives here, so it can be tuned
without reading the drawing code. Colours are RGB; an alpha, where one is
needed, is given separately.
"""

import os

from ....config.constants import FONTS_PATH

# --- Paper ---------------------------------------------------------------

PAPER = (236, 222, 186)            # Base colour of the parchment
PAPER_DARK = (196, 168, 118)       # Speckles, fibres and the browned edges
PAPER_STAIN = (170, 130, 80)       # Old water stains
PAPER_EDGE_DEPTH = 46              # How far in from the edge the paper browns

# --- Inks ----------------------------------------------------------------

INK = (58, 38, 24)                 # Iron-gall ink, gone brown with age
INK_FADED = (112, 84, 54)          # Thinner strokes: hatching, tufts, ruling
INK_PALE = (150, 120, 84)          # Lightest strokes: ripples far out at sea
RED_INK = (158, 34, 26)            # The player's mark
GOLD_INK = (184, 134, 32)          # Property the player owns

WATER_WASH = (118, 152, 156)       # Faded blue-green watercolour
WATER_WASH_ALPHA = 120
WATER_LINE = (62, 86, 96)          # Shoreline and the ripples along it
SAND_DOT = (176, 138, 78)
ROAD_WASH = (182, 140, 88)
ROAD_WASH_ALPHA = 150
PLAZA_WASH = (170, 156, 128)
PLAZA_WASH_ALPHA = 170
FIELD_WASH = (204, 168, 78)
FIELD_WASH_ALPHA = 120
WOOD_WASH = (128, 140, 84)         # Forest floor under the trees
WOOD_WASH_ALPHA = 60
TREE_WASH = (112, 128, 72)
ROOF_WASH = (172, 72, 54)          # Carmine, as on old town plans
ROOF_WASH_ALPHA = 200
STALL_WASH = (212, 172, 92)
SHADOW = (90, 64, 40)
SHADOW_ALPHA = 70

# --- Ground recognised in the map's tiles --------------------------------
# Reference colour and per-channel tolerance of each kind of ground, as it
# averages out over the ground tile layers (see terrain.py).

GROUND_WATER = ((22, 104, 168), (30, 30, 34))
GROUND_SAND = ((202, 160, 88), (26, 24, 26))
GROUND_ROAD = ((74, 42, 18), (30, 24, 18))
GROUND_PLAZA = ((104, 100, 88), (26, 26, 22))
GROUND_WOOD = ((84, 100, 32), (22, 22, 20))

#: Ground layers left out of the composite: scattered flowers are no ground.
IGNORED_GROUND_LAYERS = {"Ground_Flowers_Mushrooms"}

# --- Scale ---------------------------------------------------------------

#: Resolution the ground tiles are sampled at before being scaled to a level.
SAMPLE_PX_PER_TILE = 8

#: Zoom levels, in screen pixels per map tile. The first is the whole map at
#: a glance; each level is engraved once, when first shown.
ZOOM_LEVELS = (2.5, 3.6, 5.2, 7.5)

#: From this level on, smaller places (the well, sheds) are labelled too.
DETAIL_LABEL_LEVEL = 2

#: One map tile is one pace on the scale bar.
SCALE_UNIT = "Paces"

# --- Names ---------------------------------------------------------------

TITLE = "Blackwater Harbor"
SUBTITLE = "A Plan of the Town & its Environs"
SEA_NAME = "Blackwater Bay"
WOOD_NAME = "The Pinewood"
FIELDS_NAME = "Fields"

# --- Fonts ---------------------------------------------------------------

FONT_TITLE = os.path.join(FONTS_PATH, "Medici Text.ttf")
FONT_SCRIPT = os.path.join(FONTS_PATH, "Augusta.ttf")
FONT_PLAIN = os.path.join(FONTS_PATH, "RomanAntique.ttf")

# --- Layout --------------------------------------------------------------

FRAME_MARGIN = 10                  # Paper left free outside the ruled frame
FRAME_BAND = 9                     # Width of the chequered band of the frame
#: Room the legend needs beside the plan before it is shown.
LEGEND_MIN_SIDE_ROOM = 230
