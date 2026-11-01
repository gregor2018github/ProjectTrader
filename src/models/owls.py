"""Owls calling in the woods at night, now and then, from somewhere among the trees.

Once in OWL_EVERY_HOURS of game time on the map (about every two hours) an
owl calls, one of the owl_* recordings, never the same twice running. The
clock only runs at night (OWLS_BY_HOUR) and in the woods, measured as for the
birdsong by day (Ambience.trees, FOREST_FULL_COVER of it being a wood): at
the edge of a wood the owls call more seldom, out in the open or in town
never, and rain hushes them (RAIN_HUSHES_OWLS). Each call is near or far by
chance, OWL_VOLUME times a share drawn from OWL_LOUDNESS, and comes a little
from the left or the right (OWL_PAN).

Owned by Game and updated every frame.
"""

import datetime
import random
from typing import List, Optional

import pygame

from ..config.constants import (
    FOREST_FULL_COVER, OWL_EVERY_HOURS, OWL_LOUDNESS, OWL_PAN, OWL_VOLUME, OWLS_BY_HOUR, RAIN_HUSHES_OWLS,
)
from .ambience import Cover, by_steps

#: A jump in game time longer than this between two updates (loading a save,
#: the map shown again after a while) is not counted towards the next call.
LONGEST_STEP = datetime.timedelta(hours=1)


class Owls:
    """When the next owl calls, and how near it sounds.

    Args:
        sounds: The game's sounds; every one whose name starts with "owl_" is a call.
        trees: How wooded every spot of the map is (Ambience.trees).
        rng: Where the calls are drawn from (seed one in tests).
    """

    def __init__(self, sounds: dict, trees: Cover, rng: Optional[random.Random] = None) -> None:
        self.rng = rng or random.Random()
        self.calls: List[pygame.mixer.Sound] = [sound for name, sound in sorted(sounds.items())
                                                if name.startswith("owl_")]
        self.trees = trees
        self.last_call: Optional[pygame.mixer.Sound] = None
        self.wait = self.rng.uniform(*OWL_EVERY_HOURS)   # game hours of night in the woods to the next call
        self.last_time: Optional[datetime.datetime] = None

    def update(self, now: datetime.datetime, running: bool, player, rain: float = 0.0) -> None:
        """Count the game time since the last update while *running* (the map shown and not
        paused), as much of it as it is night in the woods around *player*, and call when due."""
        last, self.last_time = self.last_time, now
        if not running or last is None or not self.calls:
            return
        step = now - last
        if step <= datetime.timedelta(0) or step > LONGEST_STEP:
            return
        night = by_steps(OWLS_BY_HOUR, now.hour + now.minute / 60.0)
        if night <= 0:
            return
        wooded = min(1.0, self.trees.at(player.x + player.width / 2, player.y + player.height / 2)
                     / FOREST_FULL_COVER)
        self.wait -= step.total_seconds() / 3600 * night * wooded * (1.0 - RAIN_HUSHES_OWLS * rain)
        if self.wait <= 0:
            self.call()
            self.wait = self.rng.uniform(*OWL_EVERY_HOURS)

    def call(self) -> None:
        """An owl calls, near or far, a little to one side."""
        sound = self.rng.choice([s for s in self.calls if s is not self.last_call] or self.calls)
        self.last_call = sound
        channel = pygame.mixer.find_channel()
        if channel:
            volume = OWL_VOLUME * self.rng.uniform(*OWL_LOUDNESS)
            pan = self.rng.uniform(-OWL_PAN, OWL_PAN)   # -1 all left, 1 all right
            channel.set_volume(volume * min(1.0, 1.0 - pan), volume * min(1.0, 1.0 + pan))
            channel.play(sound)
