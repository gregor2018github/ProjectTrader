"""The herbalist, who sells dried herbs at the Herbs Market on the new square.

All of her behaviour comes from :class:`~.trader.Trader`; this class only says
what she looks like and where she stands in town.
"""

from .trader import Trader


class TraderHerbalist(Trader):
    """An old herb-wife who sells herbs at the market."""

    SPRITE_FOLDER = 'trader_herbalist'
    SPRITE_PREFIX = 'herbalist'
    DEFAULT_NAME = "Herbalist"
    TILED_PREFIX = "Herbalist"
    MARKET_NAME = "Herbs Market"
    # Gathers and dries her wares herself and sells them by the bunch: plain
    # working folk.
    SOCIAL_CLASS = "Commons"
