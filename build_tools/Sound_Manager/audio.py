"""Hearing and measuring the sounds: decoding, length, level, waveform, and playing one at a time.

The game's sounds are small and are decoded whole, on a worker thread at
start-up (Decoder), for their length, levels and waveform, and kept. Music
tracks and raw recordings are large: they are decoded after the sounds for
their length, levels and waveform too, a second or so each, but not kept,
and streamed (pygame.mixer.music) while played.

Any file can be played from any point (Player.play's start): a stream is
started there, a kept sound is cut there and, when looping, followed by the
whole sound again.

Levels are in dBFS: the peak is the loudest sample, the loudness the RMS of
the whole file, which is what tells a sound far too quiet beside the others.
"""

import array
import math
import threading
from collections import namedtuple

import pygame

MIXER = (44100, -16, 2)           # what the game's mixer runs at too (pygame's default)
WAVE_BINS = 480                   # columns of a waveform, drawn stretched to any width
LEVEL_SAMPLES = 400_000           # at most this many samples are read for the loudness
SILENCE_DB = -96.0

Analysis = namedtuple('Analysis', 'length peak_db loud_db peaks')   # peaks: [(low, high)] in -1..1


def init_mixer():
    if not pygame.mixer.get_init():
        pygame.mixer.init(*MIXER)
    pygame.mixer.set_num_channels(16)


def to_db(level):
    return 20 * math.log10(level) if level > 0 else SILENCE_DB


def analyse(sound):
    """The Analysis of a decoded pygame Sound."""
    samples = array.array('h')
    samples.frombytes(sound.get_raw())
    if not samples:
        return Analysis(0.0, SILENCE_DB, SILENCE_DB, [(0.0, 0.0)] * WAVE_BINS)
    peak = max(max(samples), -min(samples)) / 32768
    step = max(1, len(samples) // LEVEL_SAMPLES)
    some = samples[::step]
    loud = math.sqrt(sum(v * v for v in some) / len(some)) / 32768
    peaks = []
    per_bin = len(samples) / WAVE_BINS
    # Every sample would be slow for the long loops and is not needed for a picture
    stride = max(1, int(per_bin) // 64)
    for index in range(WAVE_BINS):
        part = samples[int(index * per_bin):max(int((index + 1) * per_bin), int(index * per_bin) + 1):stride]
        peaks.append((min(part) / 32768, max(part) / 32768) if part else (0.0, 0.0))
    return Analysis(sound.get_length(), to_db(peak), to_db(loud), peaks)


class Decoder:
    """Decodes and analyses files on a worker thread; results appear in `done` as they come.

    Files already in `done` (from an earlier Decoder) are not decoded again.
    Those in `streamed` come after the others and keep only their Analysis:
    their Sound is None, being too big to keep.
    """

    def __init__(self, paths, done=None, streamed=()):
        self.streamed = set(streamed)
        self.paths = list(paths) + [path for path in streamed if path not in set(paths)]
        self.done = {} if done is None else done   # {path: (Sound, Analysis, mtime_ns)}
        self.failed = {}          # {path: error text}
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        for path in self.paths:
            if path in self.done:
                continue
            try:
                stamp = path.stat().st_mtime_ns
                sound = pygame.mixer.Sound(str(path))
                analysis = analyse(sound)
                self.done[path] = (None if path in self.streamed else sound, analysis, stamp)
            except (pygame.error, OSError, ValueError) as exc:
                self.failed[path] = str(exc)

    @property
    def busy(self):
        return self._thread.is_alive()

    def progress(self):
        """(files read, files to read)."""
        return sum(1 for path in self.paths if path in self.done or path in self.failed), len(self.paths)

    def get(self, path):
        return self.done.get(path)


def forget_changed(done):
    """Drop the results of files changed or gone since they were decoded, so they are decoded anew."""
    for path in list(done):
        try:
            stamp = path.stat().st_mtime_ns
        except OSError:
            stamp = None
        if stamp != done[path][2]:
            del done[path]


class Player:
    """Plays one file at a time: a decoded Sound on a channel, anything else streamed."""

    def __init__(self):
        self.file = None          # the SoundFile playing, or None
        self.channel = None       # its channel; None while streaming
        self.length = None        # seconds, if known
        self.looping = False
        self.start = 0            # pygame ticks when it would have begun, had it been played from the start
        self.sound = None         # the whole kept sound, while one plays from a point and loops
        self.tail = None          # the part of it played first

    def play(self, file, sound=None, length=None, loop=False, start=0.0):
        """Play *file* from *start* seconds: *sound* if it is kept, else streamed. *length* in seconds, if known."""
        self.stop()
        start = max(0.0, min(start, length or 0.0))
        if sound and start > 0:
            frequency, _size, channels = pygame.mixer.get_init()
            frame = 2 * channels
            raw = sound.get_raw()
            offset = min(len(raw), int(start * frequency) * frame)
            self.tail = pygame.mixer.Sound(buffer=raw[offset:])
            self.channel = self.tail.play()
            if loop and self.channel:
                self.sound = sound
                self.channel.queue(sound)
        elif sound:
            self.channel = sound.play(loops=-1 if loop else 0)
        else:
            pygame.mixer.music.load(str(file.path))
            pygame.mixer.music.play(loops=-1 if loop else 0, start=start)
        self.length = length
        self.file, self.looping = file, loop
        self.start = pygame.time.get_ticks() - round(start * 1000)

    def stop(self):
        if self.channel:
            self.channel.stop()
        pygame.mixer.music.stop()
        self.file = self.channel = self.sound = self.tail = None

    def tick(self):
        """Forget the file once it has ended by itself; keep a loop played from a point going."""
        if self.file is None:
            return
        if self.looping:
            if self.sound and self.channel and self.channel.get_queue() is None:
                self.channel.queue(self.sound)
            return
        busy = self.channel.get_busy() if self.channel else pygame.mixer.music.get_busy()
        if not busy:
            self.file = self.channel = None

    def is_playing(self, file):
        return self.file is file

    def elapsed(self):
        return (pygame.time.get_ticks() - self.start) / 1000

    def position(self):
        """How far through the file, 0..1, or None if its length is not known."""
        if self.file is None or not self.length:
            return None
        return (self.elapsed() % self.length) / self.length
