"""The woodcutter, who sells timber and firewood at the Wood Market.

All of his behaviour comes from :class:`~.trader.Trader`; this class only says
what he looks like and where he stands in town.
"""

from .trader import Trader


class TraderWoodcutter(Trader):
    """A woodcutter who sells wood at the market."""

    SPRITE_FOLDER = 'trader_woodcutter'
    SPRITE_PREFIX = 'woodcutter'
    DEFAULT_NAME = "Woodcutter"
    TILED_PREFIX = "Woodcutter"
    MARKET_NAME = "Wood Market"
    # Fells trees in the forest with his own axe: plain working folk.
    SOCIAL_CLASS = "Commons"
