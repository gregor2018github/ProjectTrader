"""Human NPCs — self-directed townsfolk."""

from .npc import NPC, NPC_SPRITE_ROOT
from .trader import Trader
from .trader_alewife import TraderAlewife
from .trader_blacksmith import TraderBlacksmith
from .trader_butcher import TraderButcher
from .trader_farmer import TraderFarmer
from .trader_fisherman import TraderFisherman
from .trader_potter import TraderPotter
from .trader_shepherdess import TraderShepherdess
from .trader_stonemason import TraderStonemason
from .trader_tanner import TraderTanner
from .trader_vintner import TraderVintner
from .trader_weaver import TraderWeaver
from .trader_woodcutter import TraderWoodcutter

__all__ = [
    "NPC", "NPC_SPRITE_ROOT", "Trader", "TraderAlewife", "TraderBlacksmith",
    "TraderButcher", "TraderFarmer", "TraderFisherman", "TraderPotter",
    "TraderShepherdess", "TraderStonemason", "TraderTanner", "TraderVintner",
    "TraderWeaver", "TraderWoodcutter",
]
