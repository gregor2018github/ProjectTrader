"""Human NPCs — self-directed townsfolk."""

from .npc import NPC, NPC_SPRITE_ROOT
from .trader import Trader
from .trader_butcher import TraderButcher
from .trader_farmer import TraderFarmer
from .trader_fisherman import TraderFisherman
from .trader_potter import TraderPotter
from .trader_vintner import TraderVintner
from .trader_weaver import TraderWeaver

__all__ = [
    "NPC", "NPC_SPRITE_ROOT", "Trader", "TraderButcher", "TraderFarmer",
    "TraderFisherman", "TraderPotter", "TraderVintner", "TraderWeaver",
]
