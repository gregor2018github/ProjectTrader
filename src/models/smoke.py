"""Lightweight chimney smoke effect.

Each SmokeEmitter corresponds to one Smoke object in the Tiled map.
It manages a list of SmokeParticles that rise from the chimney outlet.
Roughly one third of emitters are randomly chosen to be active each night
(same daily-schedule pattern as window lights).
"""

import datetime
import random
import pygame
from typing import Dict, List, Tuple

from ..config.constants import (
    SMOKE_PROBABILITY,
    SMOKE_START_HOUR_MIN, SMOKE_START_HOUR_RANGE,
    SMOKE_DURATION_MIN, SMOKE_DURATION_RANGE,
)

# Surface cache keyed by (radius_px, alpha_quantized) to avoid per-frame allocations.
_surf_cache: Dict[Tuple[int, int], pygame.Surface] = {}


def _get_smoke_surf(radius_px: int, alpha: int) -> pygame.Surface:
    alpha_q = (alpha // 8) * 8  # quantize to 32 levels
    key = (radius_px, alpha_q)
    if key not in _surf_cache:
        size = radius_px * 2 + 2
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.circle(surf, (210, 210, 210, alpha_q),
                           (radius_px + 1, radius_px + 1), radius_px)
        _surf_cache[key] = surf
    return _surf_cache[key]


class SmokeParticle:
    __slots__ = ('x', 'y', 'vx', 'vy', 'radius', 'lifetime', 'max_lifetime')

    def __init__(self, x: float, y: float, vx: float, vy: float,
                 radius: float, lifetime: float) -> None:
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.radius = radius
        self.lifetime = lifetime
        self.max_lifetime = lifetime

    def update(self, dt: float) -> bool:
        """Move particle and age it. Returns False when lifetime expires."""
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.lifetime -= dt
        return self.lifetime > 0

    @property
    def alpha(self) -> int:
        return int(160 * (self.lifetime / self.max_lifetime))

    def get_render_data(self, camera, zoom: float) -> Tuple[pygame.Surface, Tuple[float, float]]:
        radius_px = max(1, round(self.radius * zoom))
        surf = _get_smoke_surf(radius_px, self.alpha)
        sx, sy = camera.apply(self.x, self.y)
        return surf, (sx - radius_px - 1, sy - radius_px - 1)


class SmokeEmitter:
    """Emits smoke particles from a chimney outlet rectangle's bottom edge.

    Active on roughly 1/3 of nights, during evening/night hours.
    The schedule is re-rolled each in-game day (same pattern as Light).
    """

    def __init__(self, outlet_x: float, outlet_y: float,
                 outlet_width: float, y_sort: float) -> None:
        # outlet_y = bottom edge of the Tiled Smoke rectangle (chimney mouth)
        self.outlet_x = outlet_x
        self.outlet_y = outlet_y
        self.outlet_width = outlet_width
        self.y_sort = y_sort        # same as parent house — drives z-ordering

        self.particles: List[SmokeParticle] = []
        self._timer: float = random.uniform(0.0, 0.8)   # stagger initial bursts
        self._next_interval: float = random.uniform(0.5, 1.0)

        # Nightly schedule (same pattern as Light._schedule_for_night)
        self._active_tonight: bool = False
        self._start_hour: float = 0.0
        self._end_hour: float = 0.0
        self._last_date_check: str = ""

    # ------------------------------------------------------------------
    # Scheduling
    # ------------------------------------------------------------------

    def _schedule_for_night(self) -> None:
        self._active_tonight = random.random() < SMOKE_PROBABILITY
        if self._active_tonight:
            self._start_hour = SMOKE_START_HOUR_MIN + random.random() * SMOKE_START_HOUR_RANGE
            duration = SMOKE_DURATION_MIN + random.random() * SMOKE_DURATION_RANGE
            self._end_hour = self._start_hour + duration

    def _check_schedule(self, current_time: datetime.datetime) -> None:
        """Re-roll the schedule once per in-game day (same cycle as lights)."""
        # Shift by 12 h so the day boundary falls at noon, not midnight
        scheduling_time = current_time - datetime.timedelta(hours=12)
        cycle_date = scheduling_time.strftime("%Y-%m-%d")
        if self._last_date_check != cycle_date:
            self._schedule_for_night()
            self._last_date_check = cycle_date

    def is_active(self, current_time: datetime.datetime) -> bool:
        """True when the chimney should be smoking right now."""
        if not self._active_tonight:
            return False
        hour = current_time.hour + current_time.minute / 60.0
        effective_hour = hour + 24 if hour < 12 else hour
        return self._start_hour <= effective_hour <= self._end_hour

    # ------------------------------------------------------------------
    # Simulation
    # ------------------------------------------------------------------

    def update(self, dt: float, current_time: datetime.datetime) -> None:
        """Advance particles and (conditionally) spawn new ones."""
        self._check_schedule(current_time)
        # Always age/remove existing particles so they fade out naturally
        self.particles = [p for p in self.particles if p.update(dt)]
        # Only spawn while active
        if self.is_active(current_time):
            self._timer += dt
            while self._timer >= self._next_interval:
                self._timer -= self._next_interval
                self._next_interval = random.uniform(0.5, 1.0)
                self._spawn()
        else:
            self._timer = 0.0

    def _spawn(self) -> None:
        x = self.outlet_x + random.uniform(0.1, 0.9) * self.outlet_width
        y = self.outlet_y
        vx = random.uniform(-3.0, 3.0)
        vy = random.uniform(-18.0, -10.0)   # negative = rising
        radius = random.uniform(2.5, 5.5)
        lifetime = random.uniform(3.0, 5.5)
        self.particles.append(SmokeParticle(x, y, vx, vy, radius, lifetime))
