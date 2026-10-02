"""Engraves the unchanging part of the plan, once per zoom level.

The result is a see-through surface the size of the whole map at that level:
ink and washes only, laid onto the paper by the view. Everything here is
drawn at the level's own resolution rather than scaled from one big
picture, so a line is as fine zoomed out as zoomed in. What changes while
playing (the player, open stalls, owned property, names) is drawn on top by
the view each frame.
"""

import random
from typing import Tuple

import pygame

from . import glyphs
from .landmarks import Landmarks
from .style import (
    INK, INK_FADED, INK_PALE, PLAZA_WASH, PLAZA_WASH_ALPHA, ROAD_WASH, ROAD_WASH_ALPHA,
    SAND_DOT, WATER_LINE, WATER_WASH, WATER_WASH_ALPHA, WOOD_WASH, WOOD_WASH_ALPHA,
)
from .terrain import Ground, dilate, erode, rim

_CLEAR = (0, 0, 0, 0)


def engrave(tmx_map, ground: Ground, marks: Landmarks, px_per_tile: float) -> pygame.Surface:
    """The plan's ink at ``px_per_tile`` screen pixels per map tile."""
    scale = px_per_tile / tmx_map.tile_size
    size = (round(ground.tiles_wide * px_per_tile), round(ground.tiles_high * px_per_tile))
    masks = ground.masks(size)
    plan = pygame.Surface(size, pygame.SRCALPHA)
    plan.fill(_CLEAR)

    _wood_floor(plan, masks["wood"], px_per_tile)
    _sand(plan, masks["sand"], px_per_tile)
    _paved(plan, masks["road"], ROAD_WASH, ROAD_WASH_ALPHA, hatch=0)
    _paved(plan, masks["plaza"], PLAZA_WASH, PLAZA_WASH_ALPHA, hatch=max(3, round(px_per_tile * 0.9)))
    for f in tmx_map.fields:
        glyphs.field(plan, _to_plan(pygame.Rect(f.x, f.y, f.width, f.height), scale),
                     spacing=max(3, round(px_per_tile * 1.1)))
    _water(plan, masks["water"], ground.masks((ground.tiles_wide, ground.tiles_high))["water"], px_per_tile)
    _grass(plan, masks, marks, scale, px_per_tile)

    if marks.ship_position is not None:
        sx, sy = marks.ship_position
        glyphs.ship(plan, sx * scale, sy * scale, px_per_tile * 5.5)

    if marks.market_area is not None:
        _dotted_rect(plan, _to_plan(marks.market_area, scale), INK_FADED, max(2, round(px_per_tile * 0.7)))

    _trees(plan, tmx_map.trees, scale)

    for fence in marks.fences:
        glyphs.palisade(plan, (fence.start[0] * scale, fence.start[1] * scale),
                        (fence.end[0] * scale, fence.end[1] * scale), tick=px_per_tile * 0.35)

    for building in sorted(marks.buildings, key=lambda b: b.footprint.bottom):
        _building(plan, building, scale, px_per_tile)
    return plan


def _to_plan(rect: pygame.Rect, scale: float) -> pygame.Rect:
    return pygame.Rect(round(rect.x * scale), round(rect.y * scale),
                       max(1, round(rect.width * scale)), max(1, round(rect.height * scale)))


def _masked(mask: pygame.Mask, color: Tuple[int, int, int], alpha: int = 255) -> pygame.Surface:
    return mask.to_surface(setcolor=(*color, alpha), unsetcolor=_CLEAR)


def _pattern(mask: pygame.Mask, pattern: pygame.Surface) -> pygame.Surface:
    """``pattern`` kept only where ``mask`` is set."""
    keep = mask.to_surface(setcolor=(255, 255, 255, 255), unsetcolor=_CLEAR)
    keep.blit(pattern, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    return keep


def _water(plan: pygame.Surface, water: pygame.Mask, water_by_tile: pygame.Mask, ppt: float) -> None:
    size = water.get_size()
    land = water.copy()
    land.invert()

    plan.blit(_masked(water, WATER_WASH, WATER_WASH_ALPHA), (0, 0))

    # Fine level hatching, as an engraver shades water, thickest near the shore
    near = dilate(land, max(3, round(ppt * 4)))
    shore_band = water.overlap_mask(near, (0, 0))
    lines = pygame.Surface(size, pygame.SRCALPHA)
    spacing = max(3, round(ppt * 1.1))
    for y in range(0, size[1], spacing):
        pygame.draw.line(lines, (*WATER_LINE, 110), (0, y), (size[0], y))
    plan.blit(_pattern(shore_band, lines), (0, 0))

    # Ripple lines following the shore outwards, paler as they go
    for step, color in ((1.6, WATER_LINE), (3.4, INK_FADED), (5.6, INK_PALE)):
        distance = max(2, round(ppt * step))
        ring = dilate(land, distance)
        ring.erase(dilate(land, distance - 1), (0, 0))
        plan.blit(_masked(ring, color), (0, 0))

    # The shoreline itself, in full ink
    shore = rim(land, 0, 1 if ppt < 4 else 2).overlap_mask(water, (0, 0))
    plan.blit(_masked(shore, INK), (0, 0))

    # Wave marks scattered over open water, well away from any shore
    rng = random.Random(77)
    open_sea = erode(water_by_tile, 9)
    tiles_w, tiles_h = open_sea.get_size()
    for _ in range(tiles_w * tiles_h // 196):
        tx, ty = rng.uniform(0, tiles_w), rng.uniform(0, tiles_h)
        if open_sea.get_at((int(tx), int(ty))):
            glyphs.wavelet(plan, tx * ppt, ty * ppt, max(2.0, ppt * 0.8))


def _sand(plan: pygame.Surface, sand: pygame.Mask, ppt: float) -> None:
    size = sand.get_size()
    dots = pygame.Surface(size, pygame.SRCALPHA)
    rng = random.Random(31)
    for _ in range(int(sand.count() / max(2.0, ppt * 0.8))):
        dots.set_at((rng.randrange(size[0]), rng.randrange(size[1])), (*SAND_DOT, 255))
    plan.blit(_masked(sand, SAND_DOT, 40), (0, 0))
    plan.blit(_pattern(sand, dots), (0, 0))


def _wood_floor(plan: pygame.Surface, wood: pygame.Mask, ppt: float) -> None:
    size = wood.get_size()
    plan.blit(_masked(wood, WOOD_WASH, WOOD_WASH_ALPHA), (0, 0))
    dots = pygame.Surface(size, pygame.SRCALPHA)
    rng = random.Random(53)
    for _ in range(int(wood.count() / max(4.0, ppt * 2.5))):
        dots.set_at((rng.randrange(size[0]), rng.randrange(size[1])), (*INK_FADED, 150))
    plan.blit(_pattern(wood, dots), (0, 0))


def _paved(plan: pygame.Surface, mask: pygame.Mask, color, alpha: int, hatch: int) -> None:
    """Roads and squares: a wash, cross-hatched for cobbles, edged in ink."""
    plan.blit(_masked(mask, color, alpha), (0, 0))
    if hatch:
        size = mask.get_size()
        lines = pygame.Surface(size, pygame.SRCALPHA)
        for offset in range(-size[1], size[0], hatch):
            pygame.draw.line(lines, (*INK_FADED, 120), (offset, size[1]), (offset + size[1], 0))
            pygame.draw.line(lines, (*INK_FADED, 120), (offset, 0), (offset + size[1], size[1]))
        plan.blit(_pattern(mask, lines), (0, 0))
    edge = mask.copy()
    edge.erase(erode(mask, 1), (0, 0))
    plan.blit(_masked(edge, INK_FADED), (0, 0))


def _grass(plan: pygame.Surface, masks, marks: Landmarks, scale: float, ppt: float) -> None:
    """Tufts of grass scattered over open ground, the same spots at every level."""
    taken = masks["water"].copy()
    for name in ("road", "plaza", "sand", "wood"):
        taken.draw(dilate(masks[name], 2), (0, 0))
    size = taken.get_size()
    tile_w, tile_h = size[0] / ppt, size[1] / ppt
    rng = random.Random(97)
    tuft = max(2.0, ppt * 0.8)
    buildings = [b.footprint.inflate(64, 64) for b in marks.buildings]
    # In clumps of a few, as grass grows, rather than sown evenly
    for _ in range(int(tile_w * tile_h / 260)):
        cx, cy = rng.uniform(0, tile_w), rng.uniform(0, tile_h)
        for _ in range(rng.randint(1, 4)):
            tx, ty = cx + rng.uniform(-1.6, 1.6), cy + rng.uniform(-0.8, 0.8)
            x, y = int(tx * ppt), int(ty * ppt)
            if not (0 <= x < size[0] and 0 <= y < size[1]) or taken.get_at((x, y)):
                continue
            wx, wy = x / scale, y / scale
            if any(r.collidepoint(wx, wy) for r in buildings):
                continue
            glyphs.grass_tuft(plan, x, y, tuft * rng.uniform(0.7, 1.15))


def _trees(plan: pygame.Surface, trees, scale: float) -> None:
    for tree in sorted(trees, key=lambda t: t.y):
        rect = tree.collision_rect
        foot_x, foot_y = rect.centerx * scale, rect.bottom * scale
        sprite_h = tree.image.get_height() if tree.image is not None else 200
        height = sprite_h * scale * 0.55
        if tree.file_name == "Tree_23.png":
            glyphs.broadleaf(plan, foot_x, foot_y, height)
        else:
            glyphs.conifer(plan, foot_x, foot_y, height)


def _building(plan: pygame.Surface, building, scale: float, ppt: float) -> None:
    rect = _to_plan(building.footprint, scale)
    kind = building.kind
    if kind == "market":
        glyphs.stall(plan, rect)
    elif kind == "well":
        glyphs.well(plan, rect.center, max(rect.width, rect.height) * 0.5)
    elif kind == "warehouse":
        glyphs.roof(plan, rect, color=(150, 104, 70))
    else:
        glyphs.roof(plan, rect)

    if kind == "church":
        # A bell tower at the west end, the cross over the nave
        tower = pygame.Rect(0, 0, round(rect.height * 0.62), round(rect.height * 0.62))
        tower.midleft = (rect.left - round(tower.width * 0.25), rect.centery)
        glyphs.roof(plan, tower, color=(142, 58, 44))
        glyphs.cross(plan, (rect.centerx + rect.width * 0.12, rect.centery), rect.height * 0.55, INK)
    elif kind == "mill":
        glyphs.mill_sails(plan, rect.center, max(rect.width, rect.height) * 0.62)
    elif kind == "townhall":
        # A small square belfry on the ridge
        belfry = pygame.Rect(0, 0, max(3, round(rect.height * 0.3)), max(3, round(rect.height * 0.3)))
        belfry.center = rect.center
        pygame.draw.rect(plan, INK, belfry)


def _dotted_rect(surface: pygame.Surface, rect: pygame.Rect, color, gap: int) -> None:
    for x in range(rect.left, rect.right, gap * 2):
        pygame.draw.line(surface, color, (x, rect.top), (min(x + gap, rect.right), rect.top))
        pygame.draw.line(surface, color, (x, rect.bottom), (min(x + gap, rect.right), rect.bottom))
    for y in range(rect.top, rect.bottom, gap * 2):
        pygame.draw.line(surface, color, (rect.left, y), (rect.left, min(y + gap, rect.bottom)))
        pygame.draw.line(surface, color, (rect.right, y), (rect.right, min(y + gap, rect.bottom)))
