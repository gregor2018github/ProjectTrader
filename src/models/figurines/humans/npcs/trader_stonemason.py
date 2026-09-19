"""The stonemason, who sells cut stone at the Stone Market.

All of his behaviour comes from :class:`~.trader.Trader`; this class only says
what he looks like and where he stands in town.
"""

from .trader import Trader


class TraderStonemason(Trader):
    """A stonemason who sells stone at the market."""

    SPRITE_FOLDER = 'trader_stonemason'
    SPRITE_PREFIX = 'stonemason'
    DEFAULT_NAME = "Stonemason"
    TILED_PREFIX = "Stonemason"
    MARKET_NAME = "Stone Market"
    # A skilled craftsman, but stone is the cheapest good on the market.
    SOCIAL_CLASS = "Commons"
