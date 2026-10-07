"""The salter, who sells salt at the Salt Market on the new square.

All of his behaviour comes from :class:`~.trader.Trader`; this class only says
what he looks like and where he stands in town.
"""

from .trader import Trader


class TraderSalter(Trader):
    """A salter who sells salt at the market."""

    SPRITE_FOLDER = 'trader_salter'
    SPRITE_PREFIX = 'salter'
    DEFAULT_NAME = "Salter"
    TILED_PREFIX = "Salter"
    MARKET_NAME = "Salt Market"
    # Salt comes from afar and is dear, and dealing in it takes money for
    # stock and carriage: a well-off burgher.
    SOCIAL_CLASS = "Middling Sort"
