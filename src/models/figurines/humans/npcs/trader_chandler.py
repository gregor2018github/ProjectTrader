"""The chandler, who sells candles at the Candle Market on the new square.

All of his behaviour comes from :class:`~.trader.Trader`; this class only says
what he looks like and where he stands in town.
"""

from .trader import Trader


class TraderChandler(Trader):
    """A chandler who sells candles at the market."""

    SPRITE_FOLDER = 'trader_chandler'
    SPRITE_PREFIX = 'chandler'
    DEFAULT_NAME = "Chandler"
    TILED_PREFIX = "Chandler"
    MARKET_NAME = "Candle Market"
    # A tallow chandler dipping candles in his own workshop: a craftsman of
    # the commons.
    SOCIAL_CLASS = "Commons"
