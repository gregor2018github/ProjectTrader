"""Dogs barking somewhere in town now and then, by day and by night.

Once in DOG_EVERY_HOURS of game time on the map (2 to 3 a day) a dog barks.
The clock runs as fast as the player stands in town, measured as for the
crickets (Ambience.town, TOWN_FULL_COVER of it being town): at the edge of
town the dogs are heard more seldom, out in the country never. A bark is
one of three things:

- a dog farther off barking a few times (one dog_bark_far_* recording);
- a dog barking DOG_BOUT_BARKS times, a single dog_bark_distant_* each,
  DOG_BOUT_GAP_S apart, all from the same spot;
- at night (DOG_CHORUS_HOURS), now and then (DOG_CHORUS_CHANCE), the
  village's dogs answering each other far off (dogs_far_village_night).

Each is near or far by chance, DOG_VOLUME times a share drawn from
DOG_LOUDNESS, and comes a little from the left or the right (DOG_PAN).
The barks of a bout are timed in real seconds and held while the map is
not running.

Owned by Game and updated every frame.
"""

import datetime
import random
from typing import List, Optional, Tuple

import pygame

from ..config.constants import (
    DOG_BOUT_BARKS, DOG_BOUT_GAP_S, DOG_CHORUS_CHANCE, DOG_CHORUS_HOURS, DOG_EVERY_HOURS, DOG_LOUDNESS, DOG_PAN,
    DOG_VOLUME, TOWN_FULL_COVER,
)
from .ambience import Cover
from .map_clock import MapClock


class Dogs:
    """When the next dog barks, and how.

    Args:
        sounds: The game's sounds; "dog_bark_far_*", "dog_bark_distant_*" and
            "dogs_far_village_night" are the dogs.
        town: How much town there is around every spot of the map (Ambience.town).
        rng: Where the barks are drawn from (seed one in tests).
    """

    def __init__(self, sounds: dict, town: Cover, rng: Optional[random.Random] = None) -> None:
        self.rng = rng or random.Random()
        self.far = [sound for name, sound in sorted(sounds.items()) if name.startswith("dog_bark_far_")]
        self.single = [sound for name, sound in sorted(sounds.items()) if name.startswith("dog_bark_distant_")]
        self.chorus = sounds.get("dogs_far_village_night")
        self.town = town
        self.last_bark: Optional[pygame.mixer.Sound] = None
        self.wait = self.rng.uniform(*DOG_EVERY_HOURS)   # game hours in town to the next bark
        self.clock = MapClock()
        #: The rest of a bout: (seconds to it, sound), and the volume of the dog barking it
        self.bout: List[Tuple[float, pygame.mixer.Sound]] = []
        self.bout_volume: Tuple[float, float] = (0.0, 0.0)

    def update(self, dt: float, now: datetime.datetime, running: bool, player) -> None:
        """Advance by *dt* real seconds to game time *now*; the time counts while *running*
        (the map shown and not paused), as much of it as *player* stands in town."""
        hours = self.clock.hours(now, running)
        if not running:
            return
        while self.bout and self.bout[0][0] <= dt:
            self.play(self.bout.pop(0)[1], self.bout_volume)
        self.bout = [(wait - dt, sound) for wait, sound in self.bout]

        if hours <= 0:
            return
        town = min(1.0, self.town.at(player.x + player.width / 2, player.y + player.height / 2) / TOWN_FULL_COVER)
        self.wait -= hours * town
        if self.wait <= 0:
            self.bark(now)
            self.wait = self.rng.uniform(*DOG_EVERY_HOURS)

    def bark(self, now: datetime.datetime) -> None:
        """A dog barks somewhere in town, or at night now and then the village's dogs."""
        volume = DOG_VOLUME * self.rng.uniform(*DOG_LOUDNESS)
        pan = self.rng.uniform(-DOG_PAN, DOG_PAN)   # -1 all left, 1 all right
        stereo = (volume * min(1.0, 1.0 - pan), volume * min(1.0, 1.0 + pan))
        start, end = DOG_CHORUS_HOURS
        night = now.hour >= start or now.hour < end
        if self.chorus and night and self.rng.random() < DOG_CHORUS_CHANCE:
            self.play(self.chorus, stereo)
        elif self.single and (not self.far or self.rng.random() < 0.5):
            self.bout_volume = stereo
            wait = 0.0
            for _ in range(self.rng.randint(*DOG_BOUT_BARKS)):
                self.bout.append((wait, self.pick(self.single)))
                wait += self.rng.uniform(*DOG_BOUT_GAP_S)
        elif self.far:
            self.play(self.pick(self.far), stereo)

    def pick(self, sounds: List[pygame.mixer.Sound]) -> pygame.mixer.Sound:
        """One of *sounds*, not the one heard last."""
        sound = self.rng.choice([s for s in sounds if s is not self.last_bark] or sounds)
        self.last_bark = sound
        return sound

    @staticmethod
    def play(sound: pygame.mixer.Sound, stereo: Tuple[float, float]) -> None:
        channel = pygame.mixer.find_channel()
        if channel:
            channel.set_volume(*stereo)
            channel.play(sound)
