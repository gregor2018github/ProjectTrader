"""The fisherman, who sells his catch at the Fish Market.

All of his behaviour comes from :class:`~.trader.Trader`; this class only says
what he looks like and where he stands in town.
"""

from .trader import Trader


class TraderFisherman(Trader):
    """A fisherman who sells fish at the market."""

    SPRITE_FOLDER = 'trader_fisherman'
    SPRITE_PREFIX = 'fisherman'
    DEFAULT_NAME = "Fisherman"
    TILED_PREFIX = "Fisher"
    MARKET_NAME = "Fish Market"
    # Lives off the river and his daily catch: plain working folk.
    SOCIAL_CLASS = "Commons"
