"""The tanner, who sells leather hides at the Wool & Hide Market.

He shares the one stall with the weaver and the shepherdess and the three of
them take turns at it, so he names her shapes on the Tiled "Movements" layer:
the same walk around the stall, the same way home, and the same door for
whichever of them the rota sends out that morning.

All of his behaviour comes from :class:`~.trader.Trader`; this class only says
what he looks like and where he stands in town.
"""

from .trader import Trader


class TraderTanner(Trader):
    """A tanner who sells hides at the market."""

    SPRITE_FOLDER = 'trader_tanner'
    SPRITE_PREFIX = 'tanner'
    DEFAULT_NAME = "Tanner"
    # Shares the weaver's stall and takes turns at it (see StallRota).
    TILED_PREFIX = "Weaver"
    MARKET_NAME = "Wool & Hide Market"
    # A stinking trade kept at the edge of town: plain working folk.
    SOCIAL_CLASS = "Commons"
