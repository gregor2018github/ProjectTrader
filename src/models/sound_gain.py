"""Sounds recorded too quietly: a Sound plays at most at volume 1.0, so a quiet file is made
louder by scaling its samples once, when it is loaded."""
from __future__ import annotations
from array import array

import pygame

SOUND_GAIN: dict[str, float] = {
    "bubble_1": 2.0,   # goods received for nothing
    "clock_ticking": 2.5,   # the rest's clock turning
}


def amplified(sound: pygame.mixer.Sound, gain: float) -> pygame.mixer.Sound:
    """A copy of `sound` with its samples times `gain` (clipped); the sound itself when the
    mixer's format is not 16-bit signed."""
    init = pygame.mixer.get_init()
    if init is None or init[1] != -16 or gain == 1.0:
        return sound
    samples = array("h")
    samples.frombytes(sound.get_raw())
    top = 32767
    scaled = array("h", (max(-top - 1, min(top, int(v * gain))) for v in samples))
    return pygame.mixer.Sound(buffer=scaled.tobytes())
