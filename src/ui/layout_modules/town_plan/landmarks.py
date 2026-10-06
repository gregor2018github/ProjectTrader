"""What the plan shows of the map's buildings, and where it writes its names.

Turns the map's ``House`` objects into ``PlanBuilding`` entries: what kind of
place each one is, what it is called on the plan, and the footprint its roof
covers seen from above. Also finds spots for the names of the bay, the wood
and the fields, from the map itself rather than from fixed coordinates.
"""

from collections import deque
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import pygame

from ....models.house import House
from ....models.institutions.bank import Bank
from ....models.institutions.church import Church
from ....models.institutions.market import Market
from ....models.institutions.mill import Mill
from ....models.institutions.town import Town
from ....models.institutions.warehouse import Warehouse
from ....models.institutions.well import Well
from .style import FIELDS_NAME, SEA_NAME, WOOD_NAME

#: Kinds whose name is written on the plan from the first zoom level on.
MAJOR_KINDS = ("townhall", "church", "bank", "mill", "workshop")
#: Kinds whose name is written once the plan is zoomed in far enough.
MINOR_KINDS = ("well", "warehouse")


@dataclass
class PlanBuilding:
    """One building as the plan shows it."""
    house: House
    kind: str                    # dwelling, townhall, church, bank, mill, well, market, warehouse, workshop
    name: str
    footprint: pygame.Rect       # World pixels, seen from above

    def describe(self) -> str:
        """A second line for the tooltip, or an empty string."""
        house = self.house
        if self.kind == "dwelling" and house.max_inhabitants:
            return f"Room for {house.max_inhabitants} souls"
        if self.kind == "warehouse":
            if getattr(house, "is_owned", False):
                return "Your property"
            price = getattr(house, "buy_price", 0)
            return f"For sale: {price:,} coins" if price else ""
        return ""


@dataclass
class PlanFence:
    start: Tuple[float, float]   # World pixels
    end: Tuple[float, float]


@dataclass
class RegionLabel:
    text: str
    position: Tuple[float, float]  # World pixels
    style: str                     # "water" or "land"


@dataclass
class Landmarks:
    buildings: List[PlanBuilding] = field(default_factory=list)
    fences: List[PlanFence] = field(default_factory=list)
    market_area: Optional[pygame.Rect] = None
    regions: List[RegionLabel] = field(default_factory=list)
    ship_position: Optional[Tuple[float, float]] = None


def gather(tmx_map, water_mask: pygame.Mask) -> Landmarks:
    """Read the plan's buildings, fences and place names off a ``TMXMap``.

    Args:
        tmx_map: The loaded map.
        water_mask: The map's water, one bit per tile.
    """
    marks = Landmarks()
    for house in tmx_map.houses:
        if house.name.startswith("Fence"):
            marks.fences.append(_fence(house.collision_rect))
            continue
        kind = _kind(house)
        if kind is None:
            continue
        marks.buildings.append(PlanBuilding(house, kind, _name(house, kind), _footprint(house, kind)))

    marks.market_area = tmx_map.areas.get("Market_Area")
    tile = tmx_map.tile_size

    sea, ship = _open_water_spots(water_mask)
    if sea is not None:
        marks.regions.append(RegionLabel(SEA_NAME, ((sea[0] + 0.5) * tile, (sea[1] + 0.5) * tile), "water"))
    if ship is not None:
        marks.ship_position = ((ship[0] + 0.5) * tile, (ship[1] + 0.5) * tile)

    wood = _densest_trees(tmx_map.trees, tile)
    if wood is not None:
        marks.regions.append(RegionLabel(WOOD_NAME, wood, "land"))

    # The name goes under the fields with a crop on them; bare ploughland is
    # just more of the same farm
    sown = [f for f in tmx_map.fields if f.images] or tmx_map.fields
    if sown:
        union = pygame.Rect(sown[0].x, sown[0].y, sown[0].width, sown[0].height)
        for f in sown[1:]:
            union.union_ip(pygame.Rect(f.x, f.y, f.width, f.height))
        marks.regions.append(RegionLabel(FIELDS_NAME, (union.centerx, union.bottom + tile * 2), "land"))
    return marks


def _kind(house: House) -> Optional[str]:
    if isinstance(house, Town):
        return "townhall"
    if isinstance(house, Church):
        return "church"
    if isinstance(house, Bank):
        return "bank"
    if isinstance(house, Mill):
        return "mill"
    if isinstance(house, Well):
        return "well"
    if isinstance(house, Market):
        return "market"
    if isinstance(house, Warehouse):
        return "warehouse"
    # Invisible collision boxes, stumps and scattered deco are not buildings
    if house.image is None or house.house_class not in ("House_Frontal", "House_Profile"):
        return None
    if house.name.startswith("Stomp"):
        return None
    if not house.name.startswith("House"):
        return "workshop"
    return "dwelling"


def _name(house: House, kind: str) -> str:
    if house.display_name:
        return house.display_name
    return {
        "townhall": "Town Hall",
        "church": "Church",
        "bank": "Bank",
        "mill": "Mill",
        "well": "Well",
        "market": house.name,
        "warehouse": getattr(house, "buy_type", "") or "Warehouse",
        "workshop": "Woodcutter's Hut" if house.name == "Wood Chopper" else house.name,
        "dwelling": "Dwelling",
    }[kind]


def _footprint(house: House, kind: str) -> pygame.Rect:
    """The ground a building's roof covers, in world pixels.

    The collision box is only the strip of wall a walker bumps into; a roof
    seen from above reaches further back, roughly half as deep as the
    building is wide, but never deeper than the sprite is tall.
    """
    rect = house.collision_rect.copy()
    if kind in ("market", "well"):
        return rect
    # The image is already loaded at the house's scale
    sprite_height = house.image.get_height() if house.image else rect.height
    depth = max(rect.height, min(rect.width * 0.5, sprite_height * 0.45))
    return pygame.Rect(rect.left, rect.bottom - round(depth), rect.width, round(depth))


def _fence(rect: pygame.Rect) -> PlanFence:
    if rect.width >= rect.height:
        return PlanFence((rect.left, rect.centery), (rect.right, rect.centery))
    return PlanFence((rect.centerx, rect.top), (rect.centerx, rect.bottom))


def _open_water_spots(water: pygame.Mask) -> Tuple[Optional[Tuple[int, int]], Optional[Tuple[int, int]]]:
    """The tile of water farthest from any shore, and a second one apart from it.

    The first is where the bay's name has the most room; the second is a
    good place for a ship. Distances are counted in tiles by a breadth-first
    walk out from every bit of land.
    """
    width, height = water.get_size()
    distance = [[-1] * width for _ in range(height)]
    queue = deque()
    for y in range(height):
        for x in range(width):
            if not water.get_at((x, y)):
                distance[y][x] = 0
                queue.append((x, y))
    if not queue:
        return None, None
    while queue:
        x, y = queue.popleft()
        d = distance[y][x] + 1
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < width and 0 <= ny < height and distance[ny][nx] < 0:
                distance[ny][nx] = d
                queue.append((nx, ny))

    # Water running off the map's edge has no shore there; leave a margin so
    # the name is not written against the frame
    margin = 24
    best, best_d = None, 0
    for y in range(margin, height - margin):
        for x in range(margin, width - margin):
            if distance[y][x] > best_d:
                best, best_d = (x, y), distance[y][x]
    if best is None:
        return None, None

    ship, ship_d = None, 0
    for y in range(margin, height - margin):
        for x in range(margin, width - margin):
            d = distance[y][x]
            if d > ship_d and d >= 5 and abs(x - best[0]) + abs(y - best[1]) > 22:
                ship, ship_d = (x, y), d
    return best, ship


def _densest_trees(trees, tile: int) -> Optional[Tuple[float, float]]:
    """The middle of the thickest stand of trees, in world pixels."""
    if len(trees) < 8:
        return None
    cell = tile * 12
    counts = {}
    for tree in trees:
        key = (int(tree.x // cell), int(tree.y // cell))
        counts[key] = counts.get(key, 0) + 1

    def around(key):
        return sum(counts.get((key[0] + dx, key[1] + dy), 0) for dx in (-1, 0, 1) for dy in (-1, 0, 1))

    densest = max(counts, key=around)
    near = [t for t in trees
            if abs(t.x // cell - densest[0]) <= 1 and abs(t.y // cell - densest[1]) <= 1]
    return (sum(t.x for t in near) / len(near), sum(t.y for t in near) / len(near))
