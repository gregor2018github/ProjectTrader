"""The vintner, who sells wine at the Wine & Beer Market.

All of his behaviour comes from :class:`~.trader.Trader`; this class only says
what he looks like and where he stands in town.
"""

from .trader import Trader


class TraderVintner(Trader):
    """A vintner who sells wine at the market."""

    SPRITE_FOLDER = 'trader_vintner'
    SPRITE_PREFIX = 'vintner'
    DEFAULT_NAME = "Vintner"
    TILED_PREFIX = "Vintner"
    MARKET_NAME = "Wine & Beer Market"
    # Wine is the dearest good on the market and its trade needs capital for
    # casks and cellars: a well-off burgher.
    SOCIAL_CLASS = "Middling Sort"
