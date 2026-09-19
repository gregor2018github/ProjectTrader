"""The alewife, who sells the ale she brews at the Wine & Beer Market.

All of her behaviour comes from :class:`~.trader.Trader`; this class only says
what she looks like and where she stands in town.
"""

from .trader import Trader


class TraderAlewife(Trader):
    """An alewife who sells beer at the market."""

    SPRITE_FOLDER = 'trader_alewife'
    SPRITE_PREFIX = 'alewife'
    DEFAULT_NAME = "Alewife"
    TILED_PREFIX = "Alewife"
    MARKET_NAME = "Wine & Beer Market"
    # Brews in her own kitchen and sells by the jug: plain working folk.
    SOCIAL_CLASS = "Commons"
