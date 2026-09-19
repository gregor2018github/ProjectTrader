"""The blacksmith, who sells iron at the Iron Market.

All of his behaviour comes from :class:`~.trader.Trader`; this class only says
what he looks like and where he stands in town.
"""

from .trader import Trader


class TraderBlacksmith(Trader):
    """A blacksmith who sells iron at the market."""

    SPRITE_FOLDER = 'trader_blacksmith'
    SPRITE_PREFIX = 'blacksmith'
    DEFAULT_NAME = "Blacksmith"
    TILED_PREFIX = "Blacksmith"
    MARKET_NAME = "Iron Market"
    # A master smith owns his forge, anvil and tools and belongs to a guild:
    # a respectable burgher.
    SOCIAL_CLASS = "Middling Sort"
