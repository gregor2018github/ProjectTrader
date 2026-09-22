"""The alewife, who sells the ale she brews at the Wine & Beer Market.

She shares the one stall with the vintner and they take turns at it, so she
names his shapes on the Tiled "Movements" layer: the same walk around the
stall, the same way home, and the same door for whichever of them the rota
sends out that morning.

All of her behaviour comes from :class:`~.trader.Trader`; this class only says
what she looks like and where she stands in town.
"""

from .trader import Trader


class TraderAlewife(Trader):
    """An alewife who sells beer at the market."""

    SPRITE_FOLDER = 'trader_alewife'
    SPRITE_PREFIX = 'alewife'
    DEFAULT_NAME = "Alewife"
    # Shares the vintner's stall and takes turns at it (see StallRota).
    TILED_PREFIX = "Vintner"
    MARKET_NAME = "Wine & Beer Market"
    # Brews in her own kitchen and sells by the jug: plain working folk.
    SOCIAL_CLASS = "Commons"
