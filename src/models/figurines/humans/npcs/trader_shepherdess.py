"""The shepherdess, who sells the wool of her flock at the Wool & Hide Market.

She shares the one stall with the weaver and the tanner and the three of them
take turns at it, so she names the weaver's shapes on the Tiled "Movements"
layer: the same walk around the stall, the same way home, and the same door
for whichever of them the rota sends out that morning.

All of her behaviour comes from :class:`~.trader.Trader`; this class only says
what she looks like and where she stands in town.
"""

from .trader import Trader


class TraderShepherdess(Trader):
    """A shepherdess who sells wool at the market."""

    SPRITE_FOLDER = 'trader_shepherdess'
    SPRITE_PREFIX = 'shepherdess'
    DEFAULT_NAME = "Shepherdess"
    # Shares the weaver's stall and takes turns at it (see StallRota).
    TILED_PREFIX = "Weaver"
    MARKET_NAME = "Wool & Hide Market"
    # Tends the sheep out on the pastures: plain country folk.
    SOCIAL_CLASS = "Commons"
