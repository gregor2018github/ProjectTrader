"""The shepherdess, who sells the wool of her flock at the Wool & Hide Market.

All of her behaviour comes from :class:`~.trader.Trader`; this class only says
what she looks like and where she stands in town.
"""

from .trader import Trader


class TraderShepherdess(Trader):
    """A shepherdess who sells wool at the market."""

    SPRITE_FOLDER = 'trader_shepherdess'
    SPRITE_PREFIX = 'shepherdess'
    DEFAULT_NAME = "Shepherdess"
    TILED_PREFIX = "Shepherdess"
    MARKET_NAME = "Wool & Hide Market"
    # Tends the sheep out on the pastures: plain country folk.
    SOCIAL_CLASS = "Commons"
