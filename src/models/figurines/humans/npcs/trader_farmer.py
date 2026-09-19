"""The farmer, who sells the grain from her fields at the Wheat Market.

All of her behaviour comes from :class:`~.trader.Trader`; this class only says
what she looks like and where she stands in town.
"""

from .trader import Trader


class TraderFarmer(Trader):
    """A farm woman who sells wheat at the market."""

    SPRITE_FOLDER = 'trader_farmer'
    SPRITE_PREFIX = 'farmer'
    DEFAULT_NAME = "Farmer"
    TILED_PREFIX = "Farmer"
    MARKET_NAME = "Wheat Market"
    # Works her own land and brings the harvest to town: plain country folk.
    SOCIAL_CLASS = "Commons"
