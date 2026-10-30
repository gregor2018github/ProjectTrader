"""Rain falling on the map: short slanted streaks, and where they land a splash.

Drops live in world space, like smoke and ripples, so the rain stays put
under a walking camera. Each falls for a fraction of a second towards a spot
picked uniformly in the view, and on landing becomes a little crown of
spray on land, or a widening ring on water or in a puddle (bridge decks are land).
On a building it only splashes on a roof (TMXMap.roofs, models/roofs.py). How many
are in the air follows Weather.rain and the view's size
(RAIN_DROPS_PER_MEGAPIXEL); their slant follows Weather.wind.

There are two depths: far drops are shorter, fainter and slower, and do not
splash; near ones do (RAIN_SPLASH_SHARE of them). Every sprite is made once
per zoom, slant and brightness and kept, and the whole frame's worth goes to
the screen in one Surface.blits() call; the clip of the map view cuts off
what hangs over its edge. Drawn after the day/night lighting, dimmed by
*light* instead: the falling drops no further than NIGHT_LIGHT_MIN, so the
rain stays visible at night, the splashes and rings on the ground down to
SPLASH_LIGHT_MIN, so they do not shine white in the dark.
"""

import random
from typing import Dict, List, Tuple

import pygame

from ..config.constants import RAIN_DROPS_PER_MEGAPIXEL, RAIN_SPLASH_SHARE, TILE_SIZE

RAIN_COLOUR = (200, 214, 232)     # pale blue-grey: water catching the overcast sky
NIGHT_LIGHT_MIN = 0.5             # how dim the falling rain gets in the dark (1.0 is daylight)...
SPLASH_LIGHT_MIN = 0.12           # ...and its splashes and rings on the ground, which follow the dark closely
# The drop kinds: (length, opacity, fall speed in world px/s, near). The far ones first.
DROP_KINDS = (
    (7, 85, 430, False),
    (9, 100, 470, False),
    (13, 150, 620, True),
    (17, 165, 680, True),
    (21, 180, 740, True),
)
FAR_SHARE = 0.4                   # share of the drops that are far ones
FALL_SECONDS = (0.15, 0.35)       # how long a drop is seen falling before it lands
SPLASH_FRAME_SECONDS = 0.06       # each frame of a splash on land
RING_FRAME_SECONDS = 0.11         # each frame of a ring on water
SPAWN_MARGIN = 40                 # world px around the view drops may land in, so its edges are not bare
_FAR = [i for i, kind in enumerate(DROP_KINDS) if not kind[3]]
_NEAR = [i for i, kind in enumerate(DROP_KINDS) if kind[3]]

# Splash frames on land, in pixels at zoom 1 around the landing spot: spray flying up and
# out, then a puddle ring spreading. Each is (dots (x, y, alpha), ring (w, h, alpha) or None).
_SPLASH_FRAMES = (
    (((0, 0, 190), (-1, -2, 150), (1, -2, 150)), None),
    (((-2, -3, 130), (2, -3, 130)), (5, 2, 120)),
    (((-3, -3, 70), (3, -3, 70)), (8, 3, 70)),
)
# Rings on water, each (w, h, alpha): wider and fainter
_RING_FRAMES = ((4, 2, 150), (7, 3, 120), (10, 4, 85), (13, 5, 45))


def _scale_of(camera) -> float:
    """The camera's world-to-screen scale, as Camera.apply() works it out."""
    return round(TILE_SIZE * camera.zoom) / float(TILE_SIZE)


def _shade(light: float) -> Tuple[int, int, int]:
    return tuple(round(c * light) for c in RAIN_COLOUR)


def _make_streak(length: float, alpha: int, width: int, wind: float,
                 colour: Tuple[int, int, int]) -> Tuple[pygame.Surface, Tuple[int, int]]:
    """A streak *length* px long slanting by *wind*, faint at its tail and brightest at its head.

    Returns it with the head's place on it, which is put on the drop's position.
    """
    dx = wind * length
    pad = width + 1
    w = int(abs(dx)) + 2 * pad
    h = int(length) + 2 * pad
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    head = (w - pad if dx > 0 else pad + int(abs(dx)) if dx < 0 else w // 2, h - pad)
    tail = (head[0] - dx, head[1] - length)
    segments = 4
    for i in range(segments):
        t0, t1 = i / segments, (i + 1) / segments
        start = (tail[0] + (head[0] - tail[0]) * t0, tail[1] + (head[1] - tail[1]) * t0)
        end = (tail[0] + (head[0] - tail[0]) * t1, tail[1] + (head[1] - tail[1]) * t1)
        pygame.draw.line(surf, (*colour, round(alpha * t1 ** 1.5)), start, end, width)
    return surf, head


def _make_splash(dots, ring, pixel: int, colour) -> Tuple[pygame.Surface, Tuple[int, int]]:
    """One splash frame drawn in square pixels of *pixel* screen pixels; returned with its centre."""
    size = 9 * pixel
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    cx = cy = size // 2
    for x, y, alpha in dots:
        surf.fill((*colour, alpha), (cx + x * pixel, cy + y * pixel, pixel, pixel))
    if ring:
        w, h, alpha = ring
        pygame.draw.ellipse(surf, (*colour, alpha),
                            (cx - w * pixel // 2, cy - h * pixel // 2, w * pixel, h * pixel), pixel)
    return surf, (cx, cy)


class Rainfall:
    """The drops in the air and the splashes on the ground, around the camera's view."""

    def __init__(self, rng: random.Random = None) -> None:
        self.rng = rng or random.Random()
        # Each drop: [x, y, vx, vy, seconds left, kind]; (x, y) is its head, in world px
        self.drops: List[list] = []
        # Each splash: [x, y, age in seconds, on water]
        self.splashes: List[list] = []
        self._sprites: Dict[tuple, tuple] = {}

    def update(self, dt: float, rain: float, wind: float, camera, tmx_map, puddles=None) -> None:
        """Let *dt* seconds of rain fall in the camera's view (only call while the game runs).

        A drop landing in one of the *puddles* rings on it, as on water.
        """
        scale = _scale_of(camera)
        view_w = camera.screen_width / scale
        view_h = camera.screen_height / scale
        wanted = int(RAIN_DROPS_PER_MEGAPIXEL * camera.screen_width * camera.screen_height / 1e6 * rain)

        frames_end = len(_SPLASH_FRAMES) * SPLASH_FRAME_SECONDS
        rings_end = len(_RING_FRAMES) * RING_FRAME_SECONDS
        kept = []
        for splash in self.splashes:
            splash[2] += dt
            if splash[2] < (rings_end if splash[3] else frames_end):
                kept.append(splash)
        self.splashes = kept

        rng = self.rng
        water = tmx_map.water_tiles
        tile = tmx_map.tile_size
        landed = []
        alive = []
        for drop in self.drops:
            drop[4] -= dt
            if drop[4] > 0:
                drop[0] += drop[2] * dt
                drop[1] += drop[3] * dt
                alive.append(drop)
            elif DROP_KINDS[drop[5]][3]:
                landed.append(drop)
        for drop in landed:
            if rng.random() < RAIN_SPLASH_SHARE:
                fell = drop[4] + dt   # what was left of its fall this frame
                x, y = drop[0] + drop[2] * fell, drop[1] + drop[3] * fell
                if not tmx_map.roofs.splashes_at(x, y):
                    continue   # on a wall, a window, a fence: only a roof is splashed on
                on_water = ((int(x // tile), int(y // tile)) in water and tmx_map.bridge_at(x, y) is None
                            or puddles is not None and puddles.puddle_at(x, y))
                self.splashes.append([x, y, 0.0, on_water])

        # Top up to the wanted number: the drops that landed fall anew, and one more than
        # there were (the rain setting in) starts part way down, so they do not land in step
        x0, y0 = camera.x - SPAWN_MARGIN, camera.y - SPAWN_MARGIN
        span_x, span_y = view_w + 2 * SPAWN_MARGIN, view_h + 2 * SPAWN_MARGIN
        while len(alive) < wanted:
            kind = rng.choice(_FAR if rng.random() < FAR_SHARE else _NEAR)
            vy = DROP_KINDS[kind][2] * rng.uniform(0.9, 1.1)
            vx = vy * wind
            seconds = rng.uniform(*FALL_SECONDS)
            if len(alive) >= len(self.drops):
                seconds *= rng.random()
            land_x, land_y = x0 + rng.random() * span_x, y0 + rng.random() * span_y
            alive.append([land_x - vx * seconds, land_y - vy * seconds, vx, vy, seconds, kind])
        if len(alive) > wanted:
            del alive[wanted:]   # the rain easing off: those drops simply are not there any more
        self.drops = alive

    def _sprites_for(self, scale: float, wind: float, light: float) -> tuple:
        """(streaks per drop kind, splash frames, ring frames), each sprite with its anchor, for a scene *light*."""
        key = (scale, round(wind, 2), round(light, 2))
        cached = self._sprites.get(key)
        if cached is None:
            if len(self._sprites) > 48:
                self._sprites.clear()
            colour = _shade(max(NIGHT_LIGHT_MIN, key[2]))
            ground = _shade(max(SPLASH_LIGHT_MIN, key[2]))
            width = max(1, round(scale))   # near drops: 2 px when zoomed in, like the art's pixels
            streaks = [_make_streak(length * scale, alpha, width if near else 1, key[1], colour)
                       for length, alpha, _speed, near in DROP_KINDS]
            pixel = max(1, round(scale))
            splashes = [_make_splash(dots, ring, pixel, ground) for dots, ring in _SPLASH_FRAMES]
            rings = [_make_splash((), ring, pixel, ground) for ring in _RING_FRAMES]
            cached = self._sprites[key] = (streaks, splashes, rings)
        return cached

    def draw(self, screen: pygame.Surface, camera, offset_x: int, offset_y: int,
             wind: float, light: float) -> None:
        """Draw the drops and splashes; *light* (0 to 1) is how bright the scene is."""
        if not self.drops and not self.splashes:
            return
        scale = _scale_of(camera)
        streaks, splashes, rings = self._sprites_for(scale, wind, round(min(1.0, light) * 20) / 20)
        ox = offset_x - round(camera.x * scale)
        oy = offset_y - round(camera.y * scale)
        batch = []
        add = batch.append
        for x, y, age, on_water in self.splashes:
            if on_water:
                sprite, (ax, ay) = rings[min(int(age / RING_FRAME_SECONDS), len(rings) - 1)]
            else:
                sprite, (ax, ay) = splashes[min(int(age / SPLASH_FRAME_SECONDS), len(splashes) - 1)]
            add((sprite, (int(x * scale) + ox - ax, int(y * scale) + oy - ay)))
        for drop in self.drops:
            sprite, (ax, ay) = streaks[drop[5]]
            add((sprite, (int(drop[0] * scale) + ox - ax, int(drop[1] * scale) + oy - ay)))
        screen.blits(batch, doreturn=False)
