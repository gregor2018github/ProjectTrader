"""Cheerful rising chimes, made from sine waves rather than read from a file.

The big one says a whole run of sheets sent to the browser is done; the small
one, each answer of that run coming in on the way.
"""

import array
import math
import sys

import pygame

FULL = ((523.25, 659.25, 783.99, 1046.50), 0.28)   # C5 E5 G5 C6, a major arpeggio upwards
SMALL = ((783.99, 1046.50), 0.16)                  # G5 C6, its last two notes, softer
NOTE_S = 0.11            # each note starts this long after the last
RING_S = 0.45            # and rings this long, fading out
ATTACK_S = 0.008         # a short fade in, so no note clicks

_sounds = {}             # {(notes, volume): pygame Sound}, made when first played


def chime_samples(rate, notes, volume):
    """A chime as signed 16-bit mono samples at `rate` Hz."""
    total = int(rate * (NOTE_S * (len(notes) - 1) + RING_S))
    mix = [0.0] * total
    for index, freq in enumerate(notes):
        start = int(rate * NOTE_S * index)
        for i in range(min(int(rate * RING_S), total - start)):
            t = i / rate
            envelope = min(1.0, t / ATTACK_S) * math.exp(-t * 7)
            # A touch of the octave above makes it bell-like
            tone = math.sin(2 * math.pi * freq * t) + 0.3 * math.sin(4 * math.pi * freq * t)
            mix[start + i] += tone * envelope
    peak = max(abs(v) for v in mix) or 1.0
    return [int(v / peak * volume * 32767) for v in mix]


def play_chime(chime=FULL):
    """Play FULL or SMALL; plain system beeps if the mixer is not to be had."""
    notes, volume = chime
    try:
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        if chime not in _sounds:
            rate, size, channels = pygame.mixer.get_init()
            if size != -16:
                raise pygame.error(f'mixer is {size}-bit')
            samples = array.array('h', (v for v in chime_samples(rate, notes, volume) for _ in range(channels)))
            _sounds[chime] = pygame.mixer.Sound(buffer=samples.tobytes())
        _sounds[chime].play()
    except pygame.error:
        if sys.platform == 'win32':
            import winsound  # noqa: PLC0415
            for freq in notes:
                winsound.Beep(int(freq), int(NOTE_S * 1000))
