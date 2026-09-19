"""The weaver, who sells the linen she weaves at the Wool & Hide Market.

The town has no linen market of its own, so her stall stands with the other
cloth and leather traders. All of her behaviour comes from
:class:`~.trader.Trader`; this class only says what she looks like and where
she stands in town.
"""

from .trader import Trader


class TraderWeaver(Trader):
    """A weaver who sells linen at the market."""

    SPRITE_FOLDER = 'trader_weaver'
    SPRITE_PREFIX = 'weaver'
    DEFAULT_NAME = "Weaver"
    TILED_PREFIX = "Weaver"
    MARKET_NAME = "Wool & Hide Market"
    EXTRA_GOODS = ("Linen",)
    # A skilled craftswoman working her own loom.
    SOCIAL_CLASS = "Commons"
