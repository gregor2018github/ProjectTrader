"""Someone in town coughing now and then, a man's cough or a woman's by who it is.

Only game time spent on the map counts, so it is the player out in town who
hears one every COUGH_EVERY_HOURS (1 to 2 a game day), not the game racing
through the night on the market screen. When a cough is due, one of the NPCs
out of doors within COUGH_MAX_DISTANCE of the player is picked at random, near
or far alike, and coughs with their gender's voice (cough_man_* or
cough_woman_*, never the same recording twice running), the farther the softer
(COUGH_VOLUME, COUGH_FALLOFF). If nobody is out near the player it tries again
COUGH_RETRY_HOURS later.

Owned by Game and updated every frame.
"""

import datetime
import random
from typing import Dict, Iterable, List, Optional

import pygame

from ..config.constants import (
    COUGH_EVERY_HOURS, COUGH_FALLOFF, COUGH_MAX_DISTANCE, COUGH_RETRY_HOURS, COUGH_VOLUME,
)
from .map_clock import MapClock


class Coughs:
    """When the next cough comes, and who coughs it.

    Args:
        sounds: The game's sounds; those named "cough_man_*" and "cough_woman_*" are the voices.
        rng: Where the coughs are drawn from (seed one in tests).
    """

    def __init__(self, sounds: dict, rng: Optional[random.Random] = None) -> None:
        self.rng = rng or random.Random()
        self.voices: Dict[str, List[pygame.mixer.Sound]] = {
            "male": [sound for name, sound in sorted(sounds.items()) if name.startswith("cough_man_")],
            "female": [sound for name, sound in sorted(sounds.items()) if name.startswith("cough_woman_")],
        }
        self.last_cough: Optional[pygame.mixer.Sound] = None
        self.wait = self.rng.uniform(*COUGH_EVERY_HOURS)   # game hours on the map to the next cough
        self.clock = MapClock()

    def update(self, now: datetime.datetime, running: bool, npcs: Iterable, player) -> None:
        """Count the game time since the last update while *running* (the map shown and
        not paused), and when a cough is due, have someone near *player* cough."""
        hours = self.clock.hours(now, running)
        if hours <= 0:
            return
        self.wait -= hours
        if self.wait > 0:
            return
        if self.cough(npcs, player):
            self.wait = self.rng.uniform(*COUGH_EVERY_HOURS)
        else:
            self.wait = COUGH_RETRY_HOURS

    def cough(self, npcs: Iterable, player) -> bool:
        """Have a random NPC out of doors near *player* cough; False if there was nobody."""
        px = player.x + player.width / 2
        py = player.y + player.height / 2
        near = []
        for npc in npcs:
            if npc.is_hidden or not self.voices.get(npc.GENDER):
                continue
            dx = npc.x + npc.sprite_width / 2 - px
            dy = npc.y + npc.sprite_height / 2 - py
            distance = (dx * dx + dy * dy) ** 0.5
            if distance < COUGH_MAX_DISTANCE:
                near.append((npc, distance))
        if not near:
            return False
        npc, distance = self.rng.choice(near)
        voices = self.voices[npc.GENDER]
        sound = self.rng.choice([s for s in voices if s is not self.last_cough] or voices)
        self.last_cough = sound
        channel = pygame.mixer.find_channel()
        if channel:
            channel.set_volume(COUGH_VOLUME * (1.0 - distance / COUGH_MAX_DISTANCE) ** COUGH_FALLOFF)
            channel.play(sound)
        return True
