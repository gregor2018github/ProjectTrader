"""The tanner, who sells leather hides at the Wool & Hide Market.

All of his behaviour comes from :class:`~.trader.Trader`; this class only says
what he looks like and where he stands in town.
"""

from .trader import Trader


class TraderTanner(Trader):
    """A tanner who sells hides at the market."""

    SPRITE_FOLDER = 'trader_tanner'
    SPRITE_PREFIX = 'tanner'
    DEFAULT_NAME = "Tanner"
    TILED_PREFIX = "Tanner"
    MARKET_NAME = "Wool & Hide Market"
    # A stinking trade kept at the edge of town: plain working folk.
    SOCIAL_CLASS = "Commons"
