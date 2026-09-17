"""Animated map figurines: the player, human NPCs and animals.

The package mirrors the artwork tree under
``assets/map_sprites/figurines/``::

    figurines/
        humans/
            player/
            npcs/
                trader_butcher/
        animals/
            sheep/
"""

from .animator import DirectionalAnimator
from .figurine import Figurine, FIGURINE_SPRITE_ROOT

__all__ = ["DirectionalAnimator", "Figurine", "FIGURINE_SPRITE_ROOT"]
