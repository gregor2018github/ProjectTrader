"""Snow falling on the map: flakes drifting down, swaying, and settling where they land.

Like the rain (models/rain.py), the flakes live in world space around the
view, so the snow stays put under a walking camera, and each falls for a
while towards a spot picked uniformly in the view. They fall slowly, sway
from side to side and are carried far more by the wind than raindrops are.
How many are in the air follows Weather.snow and the view's size
(SNOW_FLAKES_PER_MEGAPIXEL). As the snow eases off, no new flakes start, and
those in the air fall to the end rather than vanish.

There are three depths: far flakes are small, faint and slow and melt into
the snow before they are seen to land; the near ones settle where they land
and fade away there over SETTLE_SECONDS. A flake landing on a building's
wall (not its roof, models/roofs.py) or on water is gone at once. A new
flake fades in over FADE_IN_SECONDS, so none pops up in mid-air.

Settled flakes on the ground are drawn on the ground (draw_ground(), before
anything standing), so whoever stands in front hides them and the lighting
darkens them; the falling flakes and those settling on roofs are drawn over
everything (draw(), after the lighting), dimmed by *light* no further than
NIGHT_LIGHT_MIN, so the snow stays visible at night. Every sprite is made
once per zoom and brightness, each in ALPHA_STEPS steps of opacity for the
fades, and the frame's worth goes to the screen in one Surface.blits() call.
"""

import math
import random
from typing import Dict, List, Tuple

import pygame

from ..config.constants import SNOW_FLAKES_PER_MEGAPIXEL, TILE_SIZE

SNOW_COLOUR = (246, 249, 255)     # white with a breath of blue
NIGHT_LIGHT_MIN = 0.45            # how dim the falling snow gets in the dark (1.0 is daylight)
# The flake kinds: (pattern, opacity, fall speed in world px/s, settles). The far ones first.
# A pattern is the flake in the art's pixels: (x, y, share of the opacity).
FLAKE_KINDS = (
    (((0, 0, 1.0),), 120, 24, False),
    (((0, 0, 1.0), (1, 0, 0.5), (0, 1, 0.5), (1, 1, 0.35)), 170, 34, False),
    (((0, 0, 1.0), (1, 0, 0.75), (0, 1, 0.75), (1, 1, 0.75)), 215, 46, True),
    (((1, 1, 1.0), (0, 1, 0.65), (2, 1, 0.65), (1, 0, 0.65), (1, 2, 0.65),
      (0, 0, 0.25), (2, 0, 0.25), (0, 2, 0.25), (2, 2, 0.25)), 235, 58, True),
)
KIND_SHARES = (0.3, 0.3, 0.25, 0.15)   # how many of the flakes are of each kind
FALL_SECONDS = (1.6, 3.6)         # how long a flake is seen falling before it lands
SWAY_PX = (2.0, 7.0)              # how far a flake sways to each side, in world px
SWAY_HZ = (0.3, 0.9)              # how often it sways to and fro, per second
WIND_PUSH = 2.5                   # the wind carries snow this many times as far sideways as rain
FADE_IN_SECONDS = 0.35            # a new flake fades in over this long
SETTLE_SECONDS = 0.9              # a settled flake fades away over this long
ALPHA_STEPS = 6                   # the opacity steps the fades go through
SPAWN_MARGIN = 60                 # world px around the view flakes may land in, so its edges are not bare


def _scale_of(camera) -> float:
    """The camera's world-to-screen scale, as Camera.apply() works it out."""
    return round(TILE_SIZE * camera.zoom) / float(TILE_SIZE)


def _make_flake(pattern, alpha: int, pixel: int, colour) -> Tuple[pygame.Surface, Tuple[int, int]]:
    """A flake drawn in square pixels of *pixel* screen pixels; returned with its centre."""
    size = 3 * pixel
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    for x, y, share in pattern:
        surf.fill((*colour, round(alpha * share)), (x * pixel, y * pixel, pixel, pixel))
    width = (max(x for x, _y, _s in pattern) + 1) * pixel
    return surf, (width // 2, width // 2)


class Snowfall:
    """The flakes in the air and those settling on the ground, around the camera's view."""

    def __init__(self, rng: random.Random = None) -> None:
        self.rng = rng or random.Random()
        # Each flake: [x, y, vx, vy, seconds left, kind, sway phase, sway rate (radians/s), sway px, age]
        self.flakes: List[list] = []
        # Each settled flake: [x, y, age in seconds, kind, on a roof]
        self.settled: List[list] = []
        self._sprites: Dict[tuple, list] = {}

    def update(self, dt: float, snow: float, wind: float, camera, tmx_map) -> None:
        """Let *dt* seconds of snow fall in the camera's view (only call while the game runs)."""
        kept = []
        for flake in self.settled:
            flake[2] += dt
            if flake[2] < SETTLE_SECONDS:
                kept.append(flake)
        self.settled = kept

        rng = self.rng
        water = tmx_map.water_tiles
        tile = tmx_map.tile_size
        roofs = tmx_map.roofs
        alive = []
        for flake in self.flakes:
            flake[4] -= dt
            flake[9] += dt
            flake[6] += flake[7] * dt
            if flake[4] > 0:
                flake[0] += flake[2] * dt
                flake[1] += flake[3] * dt
                alive.append(flake)
            elif FLAKE_KINDS[flake[5]][3]:
                x, y = flake[0] + math.sin(flake[6]) * flake[8], flake[1]
                if roofs.on_building(x, y):
                    if roofs.on_roof(x, y):
                        self.settled.append([x, y, 0.0, flake[5], True])
                elif ((int(x // tile), int(y // tile)) not in water or tmx_map.bridge_at(x, y) is not None):
                    self.settled.append([x, y, 0.0, flake[5], False])

        # Top up to the wanted number; when the snow sets in, the new flakes start part way
        # down, so they do not all land at once
        scale = _scale_of(camera)
        wanted = int(SNOW_FLAKES_PER_MEGAPIXEL * camera.screen_width * camera.screen_height / 1e6 * snow)
        x0, y0 = camera.x - SPAWN_MARGIN, camera.y - SPAWN_MARGIN
        span_x = camera.screen_width / scale + 2 * SPAWN_MARGIN
        span_y = camera.screen_height / scale + 2 * SPAWN_MARGIN
        setting_in = len(self.flakes) < wanted // 2
        while len(alive) < wanted:
            kind = rng.choices(range(len(FLAKE_KINDS)), weights=KIND_SHARES)[0]
            vy = FLAKE_KINDS[kind][2] * rng.uniform(0.85, 1.15)
            vx = vy * wind * WIND_PUSH * rng.uniform(0.8, 1.2)
            seconds = rng.uniform(*FALL_SECONDS)
            if setting_in:
                seconds *= rng.random()
            land_x, land_y = x0 + rng.random() * span_x, y0 + rng.random() * span_y
            alive.append([land_x - vx * seconds, land_y - vy * seconds, vx, vy, seconds, kind,
                          rng.uniform(0.0, 2 * math.pi), 2 * math.pi * rng.uniform(*SWAY_HZ),
                          rng.uniform(*SWAY_PX), 0.0])
        self.flakes = alive

    def _sprites_for(self, scale: float, light: float) -> list:
        """Per flake kind, its sprite (with its centre) at each of ALPHA_STEPS opacities, faintest first."""
        key = (scale, light)
        cached = self._sprites.get(key)
        if cached is None:
            if len(self._sprites) > 48:
                self._sprites.clear()
            colour = tuple(round(c * light) for c in SNOW_COLOUR)
            pixel = max(1, round(scale))
            cached = self._sprites[key] = [
                [_make_flake(pattern, round(alpha * (step + 1) / ALPHA_STEPS), pixel, colour)
                 for step in range(ALPHA_STEPS)]
                for pattern, alpha, _speed, _settles in FLAKE_KINDS]
        return cached

    def _add_settled(self, add, sprites, scale: float, ox: int, oy: int, roof: bool) -> None:
        for x, y, age, kind, on_roof in self.settled:
            if on_roof != roof:
                continue
            step = min(ALPHA_STEPS - 1, int((1.0 - age / SETTLE_SECONDS) * ALPHA_STEPS))
            sprite, (ax, ay) = sprites[kind][step]
            add((sprite, (int(x * scale) + ox - ax, int(y * scale) + oy - ay)))

    def draw_ground(self, screen: pygame.Surface, camera, offset_x: int, offset_y: int) -> None:
        """Draw the flakes settling on the ground, at full brightness: the lighting drawn later darkens them."""
        if not self.settled:
            return
        scale = _scale_of(camera)
        batch = []
        self._add_settled(batch.append, self._sprites_for(scale, 1.0), scale,
                          offset_x - round(camera.x * scale), offset_y - round(camera.y * scale), roof=False)
        if batch:
            screen.blits(batch, doreturn=False)

    def draw(self, screen: pygame.Surface, camera, offset_x: int, offset_y: int, light: float) -> None:
        """Draw the falling flakes and those settling on roofs; *light* (0 to 1) is how bright the scene is."""
        if not self.flakes and not self.settled:
            return
        scale = _scale_of(camera)
        sprites = self._sprites_for(scale, round(max(NIGHT_LIGHT_MIN, min(1.0, light)) * 20) / 20)
        ox = offset_x - round(camera.x * scale)
        oy = offset_y - round(camera.y * scale)
        batch = []
        add = batch.append
        self._add_settled(add, sprites, scale, ox, oy, roof=True)
        last = ALPHA_STEPS - 1
        for x, y, _vx, _vy, _left, kind, phase, _rate, sway, age in self.flakes:
            step = last if age >= FADE_IN_SECONDS else int(age / FADE_IN_SECONDS * ALPHA_STEPS)
            sprite, (ax, ay) = sprites[kind][step]
            add((sprite, (int((x + math.sin(phase) * sway) * scale) + ox - ax, int(y * scale) + oy - ay)))
        screen.blits(batch, doreturn=False)
