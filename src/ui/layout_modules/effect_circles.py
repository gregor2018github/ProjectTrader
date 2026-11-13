"""What is acting on the player, as small circles in the top left corner of the Explore map.

One circle per effect (`player_effects`): the meal's (models/meal_effects.py),
being worn out (from `drowsiness.TIRED_FROM` of tiredness on) and the weather's
slowing of the walk (`Weather.walking_slowdown`). Each is a
pictogram (`ui/effect_pictograms.py`) on a parchment disc in a ring. A meal's ring
is gold and runs out as its hours do: the part left starts at the top and grows
shorter clockwise. The weather's ring is red and whole, as it lasts as long as the
weather does. Hovering a circle shows what it does, where it came from and the
time it has left.

Drawn only with the map (`draw_map_view` calls `draw_effect_circles` last, inside
the map's clip); the circles' rects are kept in `game_state.effect_circle_rects`
so a click on them does not go through to the map.
"""

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import pygame

from ...config.colors import BLACK, DARK_BROWN, WHITE
from ...models import drowsiness, meal_effects
from ..effect_pictograms import pictogram

#: A circle's size, its ring's width and the pictogram's box inside it
CIRCLE_SIZE = 56
RING_WIDTH = 5
PICTOGRAM_SIZE = 36
#: From the map's top left corner, and between circles
MARGIN = 12
GAP = 8
#: How finely the ring's length is drawn (the rings are made once per step)
RING_STEPS = 120
SUPERSAMPLE = 4

DISC = (238, 222, 184)
DISC_EDGE = (204, 182, 138)
RING_TRACK = (84, 64, 44)
RING_GOOD = (190, 156, 84)
RING_BAD = (146, 62, 48)
TITLE_GOOD = (40, 96, 40)
TITLE_BAD = (150, 30, 24)

#: The weather's hindrances: name, and what it does to the walk
HINDRANCES: Dict[str, str] = {"rain": "Rain", "mud": "Mud", "snow": "Snow"}


@dataclass
class PlayerEffect:
    key: str                 # its pictogram
    title: str
    lines: List[str]         # what the tooltip says under the title
    share_left: float        # of its time, 1 for one that does not run out
    harmful: bool


def _duration(hours: float) -> str:
    minutes = max(0, round(hours * 60))
    return f"{minutes // 60}h {minutes % 60:02d}m" if minutes >= 60 else f"{minutes}m"


def player_effects(game: Any, now) -> List[PlayerEffect]:
    """What acts on the player at `now`: the meal's effect first, then the weather's slowing."""
    effects = []
    player = getattr(game, "player", None)
    meal = meal_effects.current_meal(player, now) if player is not None else None
    if meal is not None:
        info = meal_effects.EFFECTS[meal.kind]
        effects.append(PlayerEffect(
            meal.kind, info["name"],
            [info["does"].format(pct=meal_effects.percent(meal.strength)),
             f"From the {meal.dish}",
             f"{_duration(meal.hours_left(now))} left of {meal.hours:g}h",
             "A new meal takes its place."],
            meal.share_left(now), False))
    if player is not None and drowsiness.is_tired(player.tiredness):
        pct = round(drowsiness.penalty(player.tiredness) * 100)
        effects.append(PlayerEffect(
            "tired", "Tired",
            [f"Tiredness {player.tiredness * 100:.0f}%: your eyes keep falling shut",
             f"Walk {pct}% slower, minigames {pct}% worse",
             "Rest to recover; a filling meal slows it."],
            1.0, True))
    weather = getattr(game, "weather", None)
    if weather is not None:
        slowdown = weather.walking_slowdown()
        if slowdown >= 0.005:
            hindrances = weather.walking_hindrances()
            worst = max(hindrances, key=hindrances.get)
            parts = ", ".join(f"{HINDRANCES[k].lower()} {v * 100:.0f}%" for k, v in hindrances.items() if v >= 0.005)
            effects.append(PlayerEffect(
                worst, f"{HINDRANCES[worst]} underfoot" if worst != "rain" else "Rain",
                [f"Walk {slowdown * 100:.0f}% slower", f"From the weather: {parts}",
                 "Lasts as long as the weather does."],
                1.0, True))
    return effects


# ── Drawing ──────────────────────────────────────────────────────────────────

_discs: Dict[str, pygame.Surface] = {}
_rings: Dict[Tuple[bool, int], pygame.Surface] = {}


def _disc(key: str) -> pygame.Surface:
    """The parchment disc with the pictogram on it, the ring's track round it (made once)."""
    disc = _discs.get(key)
    if disc is None:
        big_size = CIRCLE_SIZE * SUPERSAMPLE
        big = pygame.Surface((big_size, big_size), pygame.SRCALPHA)
        centre = (big_size // 2, big_size // 2)
        radius = big_size // 2
        pygame.draw.circle(big, (0, 0, 0, 90), (centre[0], centre[1] + SUPERSAMPLE * 2), radius - SUPERSAMPLE)  # shadow
        pygame.draw.circle(big, RING_TRACK, centre, radius - SUPERSAMPLE)
        pygame.draw.circle(big, DISC_EDGE, centre, radius - SUPERSAMPLE * (RING_WIDTH + 1))
        pygame.draw.circle(big, DISC, centre, radius - SUPERSAMPLE * (RING_WIDTH + 2))
        disc = pygame.transform.smoothscale(big, (CIRCLE_SIZE, CIRCLE_SIZE))
        picture = pictogram(key, PICTOGRAM_SIZE)
        disc.blit(picture, picture.get_rect(center=(CIRCLE_SIZE // 2, CIRCLE_SIZE // 2)))
        _discs[key] = disc
    return disc


def _ring(harmful: bool, share: float) -> Optional[pygame.Surface]:
    """The ring's part left: from the top, clockwise, `share` of the way round (made once per step)."""
    step = max(0, min(RING_STEPS, math.ceil(share * RING_STEPS)))
    if step == 0:
        return None
    ring = _rings.get((harmful, step))
    if ring is None:
        big_size = CIRCLE_SIZE * SUPERSAMPLE
        big = pygame.Surface((big_size, big_size), pygame.SRCALPHA)
        c = big_size / 2
        outer = c - SUPERSAMPLE * 1.5
        inner = outer - SUPERSAMPLE * (RING_WIDTH - 1)
        colour = RING_BAD if harmful else RING_GOOD
        end = 2 * math.pi * step / RING_STEPS
        n = max(2, step * 2)
        angles = [end * i / n for i in range(n + 1)]
        # Clockwise from the top: x = sin, y = -cos
        points = ([(c + outer * math.sin(a), c - outer * math.cos(a)) for a in angles]
                  + [(c + inner * math.sin(a), c - inner * math.cos(a)) for a in reversed(angles)])
        pygame.draw.polygon(big, colour, points)
        ring = pygame.transform.smoothscale(big, (CIRCLE_SIZE, CIRCLE_SIZE))
        _rings[(harmful, step)] = ring
    return ring


def draw_effect_circles(screen: pygame.Surface, map_rect: pygame.Rect, game_state: Any) -> None:
    """The circles in the map's top left corner, and the tooltip of the one hovered."""
    game = getattr(game_state, "game", None)
    effects = player_effects(game, game_state.date)
    rects = []
    for i, effect in enumerate(effects):
        rect = pygame.Rect(map_rect.left + MARGIN + i * (CIRCLE_SIZE + GAP), map_rect.top + MARGIN,
                           CIRCLE_SIZE, CIRCLE_SIZE)
        screen.blit(_disc(effect.key), rect)
        ring = _ring(effect.harmful, effect.share_left)
        if ring is not None:
            screen.blit(ring, rect)
        rects.append(rect)
    game_state.effect_circle_rects = rects
    if not rects or getattr(game_state, "info_window", None) or getattr(game_state, "minigame", None):
        return
    mouse_pos = pygame.mouse.get_pos()
    for effect, rect in zip(effects, rects):
        # Round, so the corners between circles are the map's
        if math.dist(mouse_pos, rect.center) <= CIRCLE_SIZE / 2:
            _draw_tooltip(screen, game_state, effect, rect, map_rect)
            break


def _draw_tooltip(screen: pygame.Surface, game_state: Any, effect: PlayerEffect, circle: pygame.Rect,
                  map_rect: pygame.Rect) -> pygame.Rect:
    """Under the circle: the effect's name, in green or red, and its lines. Where it was drawn."""
    font = getattr(game_state, "small_font", None) or game_state.font
    title_font = getattr(game_state, "font", None) or font
    lines = [(title_font.render(effect.title, True, TITLE_BAD if effect.harmful else TITLE_GOOD), title_font)]
    lines += [(font.render(line, True, BLACK), font) for line in effect.lines]
    pad = 10
    height = sum(line_pitch(f) for _, f in lines)
    tip = pygame.Rect(0, 0, max(s.get_width() for s, _ in lines) + 2 * pad, height + 2 * pad)
    tip.topleft = (circle.left, circle.bottom + 8)
    tip.right = min(tip.right, map_rect.right - 4)
    pygame.draw.rect(screen, WHITE, tip, border_radius=4)
    pygame.draw.rect(screen, DARK_BROWN, tip, 1, border_radius=4)
    y = tip.top + pad
    for surf, f in lines:
        screen.blit(surf, (tip.left + pad, y))
        y += line_pitch(f)
    return tip


#: Characters reaching as far down as any: the game's fonts have old-style figures, 3, 4, 5, 7
#: and 9 hanging below the line, and a line is rendered only as deep as its own characters go
_DEEPEST = "Hgjpqy()0123456789"
_pitches: Dict[pygame.font.Font, int] = {}


def line_pitch(font: pygame.font.Font) -> int:
    """How far apart the font's lines are put: as deep as its deepest characters render, plus a gap,
    the same whatever a line holds, so the time counting down does not make the lines jump."""
    pitch = _pitches.get(font)
    if pitch is None:
        pitch = _pitches[font] = font.render(_DEEPEST, True, BLACK).get_height() + 2
    return pitch
