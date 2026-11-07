"""The outdoors around a minigame's scene: the sky at the hour it is played, its light, and the weather.

Shared by the minigames that are played out of doors (the woodhacking; the
fishing and others to come). A scene makes one ``Outdoors`` for its size, its
horizon, the moment and the weather (``Conditions.of(game.weather)``), and the
places of any lamps of its own, and then, each frame:

  1. ``update(dt)``: the rain, snow, fog banks and lightning move on; returns
     the sounds to play now ("thunder").
  2. draws everything that stands in the world on a see-through layer (where
     nothing is drawn, the sky will show), then ``draw_weather(world)``, the
     falling rain and snow, over it,
  3. ``light(world)``: multiplies it by the light of the hour (the map's own,
     ``daylight.ambient_light``, dimmed by clouds and storm like the map's,
     ``daylight.overcast``, lifted a little at night by ``NIGHT_LIFT`` so a
     game stays playable), with the warm pools of its lamps once it is dark,
  4. ``compose(frame, world)``: the sky behind the world, then the fog over
     both and a lightning flash over all,
  5. its own lamps' flames and anything that should not be lit (texts, plates).

The game stands still while a minigame is open, so the hour and the weather
are fixed for a session; only the drops, flakes, banks and flashes move.

The sky's colours follow the sun hour (``SKY_KEYFRAMES``) and the season's
tint; the sun crosses it from left to right by day, the moon by night (waxing
and waning once a season, full in its middle), with the stars; clouds grey the
sky, hide the stars and dim the sun or moon, and drift over it as puffs.
"""

import datetime
import math
import random
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import pygame

from ..daylight import ambient_light, day_of_year, overcast, season_tint, sun_hour

Colour = Tuple[int, int, int]

# The sky by sun hour, top and bottom of its gradient (the day's is parchment)
SKY_DAY_TOP, SKY_DAY_LOW = (214, 205, 176), (236, 226, 194)
_NIGHT_TOP, _NIGHT_LOW = (14, 18, 42), (36, 42, 74)
SKY_KEYFRAMES = (
    (0.0, _NIGHT_TOP, _NIGHT_LOW),
    (4.0, _NIGHT_TOP, _NIGHT_LOW),
    (5.5, (40, 44, 82), (112, 92, 112)),
    (6.5, (122, 120, 160), (238, 172, 132)),
    (8.0, SKY_DAY_TOP, SKY_DAY_LOW),
    (17.0, SKY_DAY_TOP, SKY_DAY_LOW),
    (18.5, (176, 152, 160), (246, 186, 124)),
    (20.0, (60, 56, 98), (150, 102, 112)),
    (21.0, _NIGHT_TOP, _NIGHT_LOW),
    (24.0, _NIGHT_TOP, _NIGHT_LOW),
)
NIGHT_LIFT = 0.3                    # the night lifted this far towards daylight, to keep a game playable
SUN_HOURS = (5.6, 19.4)             # sun hours the sun is up (it rises and sets behind the hills)
_SUN, _SUN_LOW = (255, 246, 222), (250, 158, 92)
_MOON, _MOON_DARK = (238, 236, 218), (204, 202, 188)
_MOON_RADIUS = 15
_STARS = 80
LAMP_LIGHT = (255, 186, 110)        # what a lamp adds to the light at its middle

# The weather
_RAIN_DROPS = 320                   # drops in the air at full rain
_RAIN_SPEED = (820, 1050)           # px a second
_RAIN_COLOUR = (206, 214, 230)
_SNOW_FLAKES = 260                  # at full snow
_SNOW_SPEED = (34, 80)
_WIND_SLANT = 0.35                  # how far the wind (1 = a gale) drives the rain sideways, of its fall
_FOG_VEIL = 0.42                    # the even veil at full fog, as alpha out of 1
_FOG_BANKS = 6
_FOG_COLOUR = (214, 218, 222)       # in full daylight; the light of the hour tints it
_CLOUD_PUFFS = 9
_STRIKE_FROM_STORM = 0.45           # lightning only from this much storm on
_STRIKE_EVERY_S = (7.0, 16.0)       # between strikes at full storm
_THUNDER_DELAY_S = (0.5, 2.6)


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def radial(strength: float, radius: int, colour: Colour) -> pygame.Surface:
    """A round glow to add over something (BLEND_RGB_ADD), brightest in its middle."""
    glow = pygame.Surface((radius * 2, radius * 2))
    glow.fill((0, 0, 0))
    for r in range(radius, 0, -2):
        k = strength * (1 - r / radius) ** 1.5
        pygame.draw.circle(glow, tuple(round(c * k) for c in colour), (radius, radius), r)
    return glow


def _soft_blob(width: int, height: int, colour: Colour, alpha: int) -> pygame.Surface:
    """A soft-edged flat ellipse (a fog bank, a cloud puff): rings of rising alpha towards its middle."""
    blob = pygame.Surface((width, height), pygame.SRCALPHA)
    steps = 10
    for i in range(steps):
        f = i / steps
        a = round(alpha * (1 - (1 - f) ** 2) / steps * 2.2)
        rect = pygame.Rect(0, 0, width * (1 - 0.8 * f), height * (1 - 0.8 * f))
        rect.center = (width // 2, height // 2)
        layer = pygame.Surface((width, height), pygame.SRCALPHA)
        pygame.draw.ellipse(layer, (*colour, min(255, a)), rect)
        blob.blit(layer, (0, 0))
    return blob


@dataclass(frozen=True)
class Conditions:
    """The weather a scene is played in, each 0 to 1 (wind may be negative: blowing to the left)."""
    rain: float = 0.0
    snow: float = 0.0
    clouds: float = 0.0
    fog: float = 0.0
    storm: float = 0.0
    wind: float = 0.0
    snow_cover: float = 0.0     # how deep snow lies on the ground


    @classmethod
    def of(cls, weather) -> "Conditions":
        """The conditions of the game's Weather (models/weather.py); clear without one."""
        if weather is None:
            return cls()
        return cls(**{name: float(getattr(weather, name, 0.0) or 0.0)
                      for name in ("rain", "snow", "clouds", "fog", "storm", "wind", "snow_cover")})


class Outdoors:
    """The sky, the light and the weather of a scene of that size with that horizon (see the module)."""

    def __init__(self, size: Tuple[int, int], horizon: int, when: Optional[datetime.datetime] = None,
                 conditions: Optional[Conditions] = None,
                 lamps: Sequence[Tuple[Tuple[float, float], int]] = (),
                 rng: Optional[random.Random] = None) -> None:
        self.width, self.height = size
        self.horizon = horizon
        self.conditions = conditions or Conditions()
        self.rng = rng or random.Random()
        c = self.conditions

        if when is None:   # full daylight at noon, a full moon should anyone ask
            hour, light, tint, moon_day = 12.0, (255, 255, 255), (255, 255, 255), 3.5
        else:
            hour, light, tint, moon_day = sun_hour(when), ambient_light(when), season_tint(when), day_of_year(when)
        self.hour = hour
        light = overcast(light, c.clouds, c.storm)
        brightness = sum(light) / (3 * 255)
        self.lamps = _clamp((0.62 - brightness) / 0.3)          # how brightly lamps burn: 0 by day, 1 at night
        self.night = _clamp((0.45 - brightness) / 0.25)         # how dark it is: the stars show
        self.light_colour = tuple(round(ch + (255 - ch) * NIGHT_LIFT * (1 - brightness)) for ch in light)

        self.lightmap = pygame.Surface(size)
        self.lightmap.fill(self.light_colour)
        if self.lamps > 0:
            for (x, y), radius in lamps:
                glow = radial(self.lamps, radius, LAMP_LIGHT)
                self.lightmap.blit(glow, glow.get_rect(center=(x, y)), special_flags=pygame.BLEND_RGB_ADD)
        self.lit = self.light_colour != (255, 255, 255) or self.lamps > 0

        self.sky = self._build_sky(hour, tint, moon_day)
        self._layer = pygame.Surface(size, pygame.SRCALPHA)   # the falling rain and snow, drawn each frame

        self._drops = [self._new_drop(anywhere=True) for _ in range(int(_RAIN_DROPS * c.rain))]
        self._splashes: List[List[float]] = []               # x, y, age
        self._flakes = [self._new_flake(anywhere=True) for _ in range(int(_SNOW_FLAKES * c.snow))]

        self.fog_colour = tuple(round(f * l / 255) for f, l in zip(_FOG_COLOUR, self.light_colour))
        self._veil = None
        self._banks: List[List] = []
        if c.fog > 0:
            self._veil = pygame.Surface(size, pygame.SRCALPHA)
            self._veil.fill((*self.fog_colour, round(255 * _FOG_VEIL * c.fog)))
            for _ in range(_FOG_BANKS):
                w, h = self.rng.randint(380, 720), self.rng.randint(60, 130)
                bank = _soft_blob(w, h, self.fog_colour, round(220 * c.fog))
                y = self.rng.uniform(horizon - 40, self.height - h / 2)
                self._banks.append([bank, self.rng.uniform(-w, self.width), y, self.rng.uniform(8, 22)])

        self.snow_ground = self._build_snow_ground() if c.snow_cover > 0.02 else None

        self._flash = 0.0
        self._flickers: List[float] = []                     # when, from now, each flicker of a strike comes
        self._thunder_in: Optional[float] = None
        self._next_strike = self._strike_wait()

    # ------------------------------------------------------------------
    # The sky
    # ------------------------------------------------------------------

    def _build_sky(self, hour: float, tint: Colour, moon_day: float) -> pygame.Surface:
        c = self.conditions
        top, low = SKY_KEYFRAMES[0][1], SKY_KEYFRAMES[0][2]
        for (h0, top0, low0), (h1, top1, low1) in zip(SKY_KEYFRAMES, SKY_KEYFRAMES[1:]):
            if h0 <= hour <= h1:
                t = (hour - h0) / (h1 - h0)
                top = tuple(_lerp(a, b, t) for a, b in zip(top0, top1))
                low = tuple(_lerp(a, b, t) for a, b in zip(low0, low1))
                break

        def weathered(colour):
            """The season's mood at half strength; clouds grey it, a storm darkens it."""
            colour = tuple(ch * (255 + k) / 510 for ch, k in zip(colour, tint))
            grey = sum(colour) / 3 * 0.86
            colour = tuple(_lerp(ch, grey * f, 0.85 * c.clouds) for ch, f in zip(colour, (0.97, 0.99, 1.05)))
            return tuple(round(ch * (1 - 0.35 * c.storm)) for ch in colour)

        top, low = weathered(top), weathered(low)
        sky = pygame.Surface((self.width, self.height))
        bottom = self.horizon + 10
        for y in range(bottom):
            sky.fill(tuple(round(_lerp(a, b, y / bottom)) for a, b in zip(top, low)), (0, y, self.width, 1))
        sky.fill(low, (0, bottom, self.width, self.height - bottom))

        clear = 1 - c.clouds
        if self.night > 0 and clear > 0.05:
            rng = random.Random(3)
            layer = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
            for _ in range(_STARS):
                x, y = rng.uniform(0, self.width), rng.uniform(0, self.horizon - 40) ** 1.1 / 1.4
                alpha = int(self.night * clear * rng.uniform(90, 230))
                pygame.draw.circle(layer, (236, 236, 255, alpha), (x, y), rng.choice((1, 1, 1.5)))
            sky.blit(layer, (0, 0))

        rise, set_ = SUN_HOURS
        if rise <= hour <= set_:
            p = (hour - rise) / (set_ - rise)
            x, y = self._arc(p)
            height = math.sin(math.pi * p)
            colour = tuple(round(_lerp(a, b, min(1.0, height * 1.6))) for a, b in zip(_SUN_LOW, _SUN))
            glow = radial(0.55 * (1 - 0.8 * c.clouds), 110, colour)
            sky.blit(glow, glow.get_rect(center=(x, y)), special_flags=pygame.BLEND_RGB_ADD)
            disc = pygame.Surface((60, 60), pygame.SRCALPHA)
            pygame.draw.circle(disc, (*colour, round(255 * (1 - 0.85 * c.clouds))), (30, 30), 18 + 7 * (1 - height))
            sky.blit(disc, (x - 30, y - 30))
        else:
            p = ((hour - set_) % 24) / (24 - (set_ - rise))
            x, y = self._arc(p)
            glow = radial(0.35 * (1 - 0.8 * c.clouds), 80, (150, 160, 190))
            sky.blit(glow, glow.get_rect(center=(x, y)), special_flags=pygame.BLEND_RGB_ADD)
            moon = self._moon((moon_day % 7) / 7)
            moon.set_alpha(round(255 * (1 - 0.85 * c.clouds)))
            sky.blit(moon, moon.get_rect(center=(x, y)))

        if c.clouds > 0.05:
            self._draw_cloud_puffs(sky, top, low)
        return sky

    def _arc(self, p: float) -> Tuple[float, float]:
        """Across the sky from left to right as p goes from 0 to 1, highest in the middle."""
        return _lerp(-30, self.width + 30, p), self.horizon - 6 - math.sin(math.pi * p) * (self.horizon - 40)

    @staticmethod
    def _moon(phase: float) -> pygame.Surface:
        """The moon at that phase (0 new, 0.5 full), on its own see-through surface: the
        unlit part is not painted at all, so the sky and the glow show there."""
        r = _MOON_RADIUS
        size = r * 2 + 2
        moon = pygame.Surface((size, size), pygame.SRCALPHA)
        centre = (r + 1, r + 1)
        pygame.draw.circle(moon, _MOON, centre, r)
        for dx, dy, rr in ((-5, -3, 4), (4, 4, 3), (2, -6, 2)):
            pygame.draw.circle(moon, _MOON_DARK, (centre[0] + dx, centre[1] + dy), rr)
        # The shadow, cut out: a disc offset sideways, far off at full moon, over it at new
        offset = r * (2.2 - 3.4 * abs(phase - 0.5))
        if offset < 2 * r:
            side = 1 if phase < 0.5 else -1
            pygame.draw.circle(moon, (0, 0, 0, 0), (centre[0] + side * offset, centre[1]), r + 1)
        return moon

    def _draw_cloud_puffs(self, sky: pygame.Surface, top: Colour, low: Colour) -> None:
        """Soft puffs of cloud drifting over the sky, a shade lighter and darker than it."""
        c = self.conditions
        rng = random.Random(5)
        for _ in range(round(_CLOUD_PUFFS * c.clouds) + 1):
            w, h = rng.randint(180, 380), rng.randint(40, 80)
            y = rng.uniform(10, self.horizon - 80)
            base = tuple(_lerp(a, b, y / self.horizon) for a, b in zip(top, low))
            light = rng.random() < 0.6
            colour = tuple(round(min(255, ch * (1.10 if light else 0.86))) for ch in base)
            puff = _soft_blob(w, h, colour, round(200 * c.clouds))
            sky.blit(puff, (rng.uniform(-w / 2, self.width - w / 2), y))

    # ------------------------------------------------------------------
    # The weather
    # ------------------------------------------------------------------

    def _build_snow_ground(self) -> pygame.Surface:
        """Snow lying on the ground below the horizon: an even white as deep as it lies, and
        patches of it thicker and thinner, so it lies unevenly. A scene lays it over its ground,
        under whatever stands on it."""
        cover = self.conditions.snow_cover
        layer = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        top = self.horizon + 8
        layer.fill((236, 240, 248, round(150 * cover)), (0, top, self.width, self.height - top))
        rng = random.Random(9)
        for _ in range(160):
            y = rng.uniform(top, self.height)
            depth = (y - top) / (self.height - top)
            w = rng.uniform(30, 120) * (0.5 + depth)
            colour = (246, 248, 252, round(rng.uniform(40, 110) * cover)) if rng.random() < 0.7                 else (196, 204, 214, round(rng.uniform(20, 60) * cover))
            pygame.draw.ellipse(layer, colour, (rng.uniform(-40, self.width), y, w, w * (0.12 + 0.12 * depth)))
        return layer

    def _new_drop(self, anywhere: bool = False) -> List[float]:
        """A raindrop: x, y, speed, length, the ground it ends on."""
        ground = self.rng.uniform(self.horizon + 12, self.height + 20)
        y = self.rng.uniform(-40, ground) if anywhere else self.rng.uniform(-60, -10)
        x = self.rng.uniform(-80, self.width + 80)
        return [x, y, self.rng.uniform(*_RAIN_SPEED), self.rng.uniform(12, 22), ground]

    def _new_flake(self, anywhere: bool = False) -> List[float]:
        """A snowflake: x, y, speed, size, sway phase, the ground it settles on, settled for."""
        ground = self.rng.uniform(self.horizon + 12, self.height + 10)
        y = self.rng.uniform(-20, ground) if anywhere else self.rng.uniform(-30, -5)
        return [self.rng.uniform(-40, self.width + 40), y, self.rng.uniform(*_SNOW_SPEED),
                self.rng.choice((1.6, 2.0, 2.4, 3.0)), self.rng.uniform(0, math.tau), ground, 0.0]

    def _strike_wait(self) -> float:
        storm = self.conditions.storm
        if storm < _STRIKE_FROM_STORM:
            return math.inf
        return self.rng.uniform(*_STRIKE_EVERY_S) / storm

    def update(self, dt: float) -> List[str]:
        """Move the weather on; returns the sounds to play now ("thunder")."""
        sounds: List[str] = []
        c = self.conditions
        slant = _WIND_SLANT * c.wind
        for d in self._drops:
            d[0] += d[2] * slant * dt
            d[1] += d[2] * dt
            if d[1] >= d[4]:
                if d[4] < self.height and self.rng.random() < 0.6:
                    self._splashes.append([d[0], d[4], 0.0])
                d[:] = self._new_drop()
        for sp in self._splashes:
            sp[2] += dt
        self._splashes = [sp for sp in self._splashes if sp[2] < 0.14]
        for f in self._flakes:
            if f[6] > 0:                                   # settled: fading where it landed
                f[6] += dt
                if f[6] > 0.8:
                    f[:] = self._new_flake()
                continue
            f[4] += dt * 1.7
            f[0] += (math.sin(f[4]) * 14 + c.wind * 40) * dt
            f[1] += f[2] * dt
            if f[1] >= f[5]:
                f[6] = 1e-6
        for bank in self._banks:
            bank[1] += bank[3] * (0.4 + abs(c.wind)) * (1 if c.wind >= 0 else -1) * dt
            w = bank[0].get_width()
            if bank[1] > self.width:
                bank[1] = -w
            elif bank[1] < -w:
                bank[1] = self.width

        # Lightning: a strike flickers once to three times; its thunder follows
        self._next_strike -= dt
        if self._next_strike <= 0:
            self._flickers = sorted(self.rng.uniform(0, 0.35) for _ in range(self.rng.randint(1, 3)))
            self._thunder_in = self.rng.uniform(*_THUNDER_DELAY_S)
            self._next_strike = self._strike_wait()
        self._flash = max(0.0, self._flash - dt * 5)
        if self._flickers:
            self._flickers = [t - dt for t in self._flickers]
            while self._flickers and self._flickers[0] <= 0:
                self._flickers.pop(0)
                self._flash = 1.0
        if self._thunder_in is not None:
            self._thunder_in -= dt
            if self._thunder_in <= 0:
                self._thunder_in = None
                sounds.append("thunder")
        return sounds

    def draw_weather(self, world: pygame.Surface) -> None:
        """The falling rain and snow, and the rain's splashes, over what stands in the world."""
        if not (self._drops or self._flakes or self._splashes):
            return
        layer = self._layer
        layer.fill((0, 0, 0, 0))
        slant = _WIND_SLANT * self.conditions.wind
        for x, y, speed, length, _ in self._drops:
            pygame.draw.line(layer, (*_RAIN_COLOUR, 160), (x, y), (x - slant * length, y - length), 1)
        for x, y, age in self._splashes:
            spread = 2 + 18 * age
            alpha = round(150 * (1 - age / 0.14))
            pygame.draw.line(layer, (*_RAIN_COLOUR, alpha), (x - spread, y - 2 - 10 * age), (x - spread / 2, y), 1)
            pygame.draw.line(layer, (*_RAIN_COLOUR, alpha), (x + spread, y - 2 - 10 * age), (x + spread / 2, y), 1)
        for x, y, _, size, _, _, settled in self._flakes:
            alpha = 230 if settled == 0 else round(230 * (1 - settled / 0.8))
            pygame.draw.circle(layer, (250, 250, 255, alpha), (x, y), size)
        world.blit(layer, (0, 0))

    def light(self, world: pygame.Surface) -> None:
        """Multiply the world layer by the light of the hour and its lamps."""
        if self.lit:
            world.blit(self.lightmap, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

    def compose(self, frame: pygame.Surface, world: pygame.Surface) -> None:
        """The sky, the lit world over it, the fog over both and a lightning flash over all."""
        frame.blit(self.sky, (0, 0))
        frame.blit(world, (0, 0))
        if self._veil is not None:
            frame.blit(self._veil, (0, 0))
            for bank, x, y, _ in self._banks:
                frame.blit(bank, (x, y - bank.get_height() / 2))
        if self._flash > 0:
            k = round(110 * self._flash)
            frame.fill((k, k, k), special_flags=pygame.BLEND_RGB_ADD)
