"""The harbour cranes' ropes, hooks, loads and barges, drawn into the map's render queue.

What each crane is doing is models/crane_hoist.py's ``Hoist``; this only
draws it. The pictures are assets/map_sprites/cranes/ (painted by
build_tools/Sprite_Manager/cargo_painter.py at ``RES`` times their world size).

Everything of one crane sorts on its barge's waterline, in the order the
barge's back, the loads in it and on the hook, the rope, the barge's front:
so a load lowered into the barge has its feet hidden by the near side, and
whatever stands in front of the quay is drawn over all of it. Without a barge
it sorts just over the crane. The lighting then darkens it with the rest at
night. A gate crane's rope, hook and load are cut off at the floor of its
hood (``Hoist.stow_y``), so a load hoisted up goes in out of sight.
"""

import math
import os
from typing import Any, Dict, List, Optional, Tuple

import pygame

from ...models.crane_hoist import HOOK_HEIGHT, HANG, LOAD_SIZES, Hoist

CRANE_SPRITES = os.path.join('assets', 'map_sprites', 'cranes')
#: Picture pixels per world pixel (cargo_painter.RES)
RES = 2
#: The barge picture's size and waterline, world px (cargo_painter's BARGE_*)
BARGE_WIDTH = 154
BARGE_WATERLINE = 34

ROPE = (150, 108, 62)
ROPE_DARK = (64, 44, 26)
#: The rope's width at zoom 1, world px
ROPE_WIDTH = 1.4
#: How far the sling's ropes take hold in from a load's top corners, world px
SLING_INSET = 3
#: The barge bobbing on the water: world px up and down, and its period in seconds
BOB_PX = 0.8
BOB_PERIOD_S = 3.4
#: A load hanging is turned in steps of this many degrees (so the turned pictures can be kept)
ANGLE_STEP = 1.0

_pictures: Dict[str, pygame.Surface] = {}
_scaled: Dict[Tuple[str, float, float], pygame.Surface] = {}


def _picture(name: str) -> Optional[pygame.Surface]:
    if name not in _pictures:
        path = os.path.join(CRANE_SPRITES, f'{name}.png')
        try:
            _pictures[name] = pygame.image.load(path).convert_alpha()
        except (pygame.error, FileNotFoundError):
            print(f"Crane picture not found: {path}")
            _pictures[name] = None
    return _pictures[name]


def _sprite(name: str, scale: float, degrees: float = 0.0) -> Optional[pygame.Surface]:
    """A picture at the screen's scale (screen px per world px), turned by degrees (counter-clockwise)."""
    key = (name, round(scale, 3), degrees)
    if key not in _scaled:
        picture = _picture(name)
        if picture is None:
            return None
        size = (max(1, round(picture.get_width() * scale / RES)), max(1, round(picture.get_height() * scale / RES)))
        surf = pygame.transform.smoothscale(picture, size)
        if degrees:
            surf = pygame.transform.rotate(surf, degrees)
        if len(_scaled) > 600:
            _scaled.clear()
        _scaled[key] = surf
    return _scaled[key]


def _cut(sprite: pygame.Surface, x: float, y: float, clip_y: Optional[float]):
    """The part of a sprite at (x, y) below clip_y (screen px): (sprite, x, y), or None if nothing is."""
    if clip_y is None or y >= clip_y:
        return sprite, x, y
    hidden = math.ceil(clip_y - y)
    if hidden >= sprite.get_height():
        return None
    return sprite.subsurface((0, hidden, sprite.get_width(), sprite.get_height() - hidden)), x, y + hidden


def crane_entries(game_map: Any, offset_x: int, offset_y: int) -> List[Dict[str, Any]]:
    """The render queue's entries for every crane's hoist in view."""
    tmx_map = game_map.tmx_map
    hoists = getattr(tmx_map, 'hoists', None)
    if not hoists:
        return []
    camera = game_map.camera
    origin_x, origin_y = camera.apply(0.0, 0.0)
    scale = camera.apply(1.0, 0.0)[0] - origin_x
    base_x, base_y = origin_x + offset_x, origin_y + offset_y
    view = game_map.world_view()
    entries: List[Dict[str, Any]] = []
    for hoist in hoists:
        left, top, right, bottom = hoist.area()
        if not view.colliderect(pygame.Rect(left, top, right - left, bottom - top)):
            continue
        entries.extend(_hoist_entries(hoist, scale, base_x, base_y))
    return entries


def _hoist_entries(hoist: Hoist, scale: float, base_x: float, base_y: float) -> List[Dict[str, Any]]:
    def screen(wx: float, wy: float) -> Tuple[float, float]:
        return base_x + wx * scale, base_y + wy * scale

    sort = hoist.waterline_y if hoist.barge else max(hoist.base_y, hoist.waterline_y)
    entries: List[Dict[str, Any]] = []

    def add(sprite: Optional[pygame.Surface], x: float, y: float, order: int, clip_y: Optional[float] = None):
        if sprite is None:
            return
        cut = _cut(sprite, x, y, clip_y)
        if cut is not None:
            entries.append({'sprite': cut[0], 'pos': (cut[1], cut[2]), 'y_sort': sort + order * 0.001})

    bob = BOB_PX * math.sin(hoist.clock * 2 * math.pi / BOB_PERIOD_S + hoist.barge_x * 0.01) if hoist.barge else 0.0
    if hoist.barge:
        bx, by = screen(hoist.barge_x - BARGE_WIDTH / 2, hoist.waterline_y - BARGE_WATERLINE + bob)
        add(_sprite('barge_back', scale), bx, by, 0)
        for slot, kind in enumerate(hoist.slots):
            if kind is not None:
                _add_standing(add, screen, scale, kind, hoist.slot_x(slot), hoist.floor_y + bob)
        if hoist.slide is not None:
            a, b, kind, t = hoist.slide
            eased = t * t * (3 - 2 * t)
            x = hoist.slot_x(a) + (hoist.slot_x(b) - hoist.slot_x(a)) * eased
            _add_standing(add, screen, scale, kind, x, hoist.floor_y + bob)

    clip_y = screen(0, hoist.stow_y)[1] if hoist.stow_y is not None else None
    end_x, end_y = hoist.hook_point()
    down = (math.sin(hoist.angle), math.cos(hoist.angle))
    across = (math.cos(hoist.angle), -math.sin(hoist.angle))
    degrees = round(math.degrees(hoist.angle) / ANGLE_STEP) * ANGLE_STEP

    # The load in its sling, turned with the rope
    sling: List[Tuple[Tuple[float, float], Tuple[float, float]]] = []
    hooking = hoist.hooking
    if hooking is not None:
        # Down on a load in the barge, the sling being made fast to it
        w, h = LOAD_SIZES[hooking]
        meet = (end_x, end_y + HOOK_HEIGHT - 1)
        load_top = hoist.floor_y + bob - h
        for side in (-1, 1):
            sling.append((meet, (hoist.rope_x + side * (w / 2 - SLING_INSET), load_top)))
    if hoist.load is not None:
        w, h = LOAD_SIZES[hoist.load]
        cx = end_x + down[0] * (HANG + h / 2)
        cy = end_y + down[1] * (HANG + h / 2)
        sprite = _sprite(hoist.load, scale, degrees)
        if sprite is not None:
            sx, sy = screen(cx, cy)
            add(sprite, sx - sprite.get_width() / 2, sy - sprite.get_height() / 2, 1, clip_y)
        meet = (end_x + down[0] * (HOOK_HEIGHT - 1), end_y + down[1] * (HOOK_HEIGHT - 1))
        for side in (-1, 1):
            reach = side * (w / 2 - SLING_INSET)
            sling.append((meet, (end_x + down[0] * HANG + across[0] * reach,
                                 end_y + down[1] * HANG + across[1] * reach)))

    # The rope and the sling as lines on one small sheet
    rope_top = (hoist.rope_x, hoist.rope_top)
    lines = [(rope_top, (end_x, end_y))] + sling
    sheet = _lines_sheet(lines, screen, scale)
    if sheet is not None:
        add(sheet[0], sheet[1], sheet[2], 2, clip_y)

    # The hook block at the rope's end
    hook = _sprite('hook', scale)
    if hook is not None:
        hx, hy = screen(end_x, end_y)
        add(hook, hx - hook.get_width() / 2, hy, 3, clip_y)

    if hoist.barge:
        add(_sprite('barge_front', scale), bx, by, 4)
    return entries


def _add_standing(add, screen, scale: float, kind: str, x: float, floor: float) -> None:
    """A load standing on the barge's floor with its middle at x."""
    w, h = LOAD_SIZES[kind]
    sx, sy = screen(x - w / 2, floor - h)
    add(_sprite(kind, scale), sx, sy, 1)


def _lines_sheet(lines, screen, scale: float):
    """Ropes drawn on a sheet just big enough: (sheet, x, y) on screen, or None."""
    points = [screen(*p) for line in lines for p in line]
    width = max(1, round(ROPE_WIDTH * scale))
    pad = width + 2
    left = math.floor(min(x for x, _ in points)) - pad
    top = math.floor(min(y for _, y in points)) - pad
    right = math.ceil(max(x for x, _ in points)) + pad
    bottom = math.ceil(max(y for _, y in points)) + pad
    if right - left > 3000 or bottom - top > 3000:
        return None
    sheet = pygame.Surface((right - left, bottom - top), pygame.SRCALPHA)
    for i, (a, b) in enumerate(lines):
        (ax, ay), (bx, by) = screen(*a), screen(*b)
        a_local, b_local = (ax - left, ay - top), (bx - left, by - top)
        thick = width if i == 0 else max(1, width - 1)
        if thick >= 2:
            pygame.draw.line(sheet, ROPE_DARK, a_local, b_local, thick + 1)
        pygame.draw.line(sheet, ROPE if thick >= 2 else ROPE_DARK, a_local, b_local, thick)
    return sheet, left, top
