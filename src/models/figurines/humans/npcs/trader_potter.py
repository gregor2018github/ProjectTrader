"""The potter, who sells jugs, bowls and pots at the Pottery Market.

All of his behaviour comes from :class:`~.trader.Trader`; this class only says
what he looks like and where he stands in town.
"""

from .trader import Trader


class TraderPotter(Trader):
    """A potter who sells pottery at the market."""

    SPRITE_FOLDER = 'trader_potter'
    SPRITE_PREFIX = 'potter'
    DEFAULT_NAME = "Potter"
    TILED_PREFIX = "Potter"
    MARKET_NAME = "Pottery Market"
    # A craftsman selling cheap everyday wares from his own wheel.
    SOCIAL_CLASS = "Commons"
