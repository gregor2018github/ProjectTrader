"""Lightning in a thunderstorm: flashes over the map, and the thunder after them.

While the weather's storm level (Weather.storm) is at least
LIGHTNING_FROM_STORM, strikes come at random, every LIGHTNING_EVERY_S at
full storm and less often in a weaker one. A strike flickers once to three
times in under half a second (`flash`, 0 to 1, which map_view adds over the
map, up to LIGHTNING_FLASH_ADD); THUNDER_CHANCE of them are followed by one
of the thunder_* recordings, never the same twice running. The thunder comes
THUNDER_DELAY_S after the flash, near to far, and the farther the softer
(THUNDER_VOLUME).

Real seconds, not game time: a strike is over in a moment. Owned by Game and
updated every frame, it only runs while the map is shown and the game not
paused; the thunder still rolling is paused with it.
"""

import random
from typing import List, Optional, Tuple

import pygame

from ..config.constants import (
    LIGHTNING_EVERY_S, LIGHTNING_FLASH_ADD, LIGHTNING_FROM_STORM, THUNDER_CHANCE, THUNDER_DELAY_S, THUNDER_VOLUME,
)

#: A flicker's pulses: (start, length, brightness), in seconds from the strike
FLICKERS = (
    ((0.0, 0.12, 1.0),),
    ((0.0, 0.07, 0.7), (0.12, 0.14, 1.0)),
    ((0.0, 0.06, 0.6), (0.1, 0.08, 1.0), (0.26, 0.16, 0.8)),
)


class Lightning:
    """The strikes of a thunderstorm and their thunder.

    Args:
        sounds: The game's sounds; every one whose name starts with "thunder_" may be heard.
        rng: Where the strikes are drawn from (seed one in tests).
    """

    def __init__(self, sounds: dict, rng: Optional[random.Random] = None) -> None:
        self.rng = rng or random.Random()
        self.thunder = [sound for name, sound in sorted(sounds.items()) if name.startswith("thunder_")]
        self.last_thunder: Optional[pygame.mixer.Sound] = None
        self.wait = 0.0                               # seconds to the next strike
        self.since_strike: Optional[float] = None    # seconds since the last strike began, None when over
        self.pulses: Tuple[Tuple[float, float, float], ...] = ()
        self.thunder_in: Optional[float] = None      # seconds to the thunder of the last strike
        self.thunder_volume = 0.0
        self.rolling: List[pygame.mixer.Channel] = []   # channels the thunder is rolling on
        self.flash = 0.0                              # how bright the flash is now, 0 to 1

    def update(self, dt: float, storm: float, running: bool) -> None:
        """Advance by *dt* seconds in a storm of *storm*; held (thunder paused) while not *running*."""
        self.rolling = [channel for channel in self.rolling if channel.get_busy()]
        if not running:
            self.flash = 0.0
            for channel in self.rolling:
                channel.pause()
            return
        for channel in self.rolling:
            channel.unpause()

        if storm >= LIGHTNING_FROM_STORM:
            self.wait -= dt * storm
            if self.wait <= 0:
                self.strike()
        elif self.wait <= 0:
            self.wait = self.rng.uniform(*LIGHTNING_EVERY_S) / 2   # a storm opens with a pause

        self.flash = 0.0
        if self.since_strike is not None:
            self.since_strike += dt
            t = self.since_strike
            for start, length, brightness in self.pulses:
                if start <= t < start + length:
                    self.flash = brightness * (1.0 - (t - start) / length) ** 2   # a jolt, dying away
            if t > max(start + length for start, length, _ in self.pulses):
                self.since_strike = None

        if self.thunder_in is not None:
            self.thunder_in -= dt
            if self.thunder_in <= 0:
                self.thunder_in = None
                self._roll_thunder()

    def strike(self) -> None:
        """A strike now (also the debug page's), and its thunder on the way if it is near enough."""
        self.wait = self.rng.uniform(*LIGHTNING_EVERY_S)
        self.since_strike = 0.0
        self.pulses = self.rng.choice(FLICKERS)
        if self.thunder and self.rng.random() < THUNDER_CHANCE:
            near, far = THUNDER_DELAY_S
            distance = self.rng.random()                 # 0 overhead, 1 as far as is heard
            self.thunder_in = near + (far - near) * distance
            loud, soft = THUNDER_VOLUME
            self.thunder_volume = loud + (soft - loud) * distance

    def _roll_thunder(self) -> None:
        choices = [sound for sound in self.thunder if sound is not self.last_thunder] or self.thunder
        sound = self.rng.choice(choices)
        self.last_thunder = sound
        channel = pygame.mixer.find_channel()
        if channel:
            channel.set_volume(self.thunder_volume)
            channel.play(sound)
            self.rolling.append(channel)

    @property
    def flash_add(self) -> int:
        """What the flash adds to the map's colours now (0 to LIGHTNING_FLASH_ADD)."""
        return round(LIGHTNING_FLASH_ADD * self.flash)

    def stop(self) -> None:
        for channel in self.rolling:
            channel.stop()
        self.rolling = []
