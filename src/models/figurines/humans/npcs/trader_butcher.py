"""The butcher — the first trader, who will sell meat at the market.

All of his behaviour comes from :class:`~.trader.Trader`; this class only says
what he looks like and where he stands in town.
"""

from .trader import Trader


class TraderButcher(Trader):
    """A butcher who sells meat at the market."""

    SPRITE_FOLDER = 'trader_butcher'
    SPRITE_PREFIX = 'butcher'
    DEFAULT_NAME = "Butcher"
    # A master butcher is a guild member who owns his stall and tools: a
    # respectable burgher, well above the commons but no gentleman.
    SOCIAL_CLASS = "Middling Sort"
