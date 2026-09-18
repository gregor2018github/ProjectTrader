"""Human NPCs — self-directed townsfolk."""

from .npc import NPC, NPC_SPRITE_ROOT
from .trader import Trader
from .trader_butcher import TraderButcher

__all__ = ["NPC", "NPC_SPRITE_ROOT", "Trader", "TraderButcher"]
