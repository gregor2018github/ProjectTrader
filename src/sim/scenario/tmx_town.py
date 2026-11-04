"""Reads a town for the simulation out of a Tiled map, without pytmx or pygame.

An adapter for the headless runner only: the simulation core takes a plain
``TownSpec`` and never knows about TMX (the towns of the strategic map will
have no map file at all). The game builds its ``TownSpec`` from the houses its
own map loader made (``Town.initialize_population``); a slow test checks the
two agree.

What it reads is what ``TMXMap._load_houses`` makes a house of: every object on
the visible ``Houses`` object layer, with its ``Max_inhabitants`` (0 if unset).
"""
import xml.etree.ElementTree as ET
from typing import List, Optional

from ...config.constants import MAP_PATH
from ..state import TownSpec

HOUSES_LAYER = "Houses"
CAPACITY_PROPERTY = "Max_inhabitants"


def house_capacities(path: Optional[str] = None) -> List[int]:
    """Every house's ``Max_inhabitants`` on the map, in the map's object order.

    Args:
        path: The ``.tmx`` file; the game's map by default.

    Raises:
        ValueError: If the map has no visible ``Houses`` layer, or a capacity is not a whole number.
    """
    path = path or MAP_PATH
    root = ET.parse(path).getroot()
    layers = [g for g in root.iter("objectgroup")
              if g.get("name") == HOUSES_LAYER and g.get("visible", "1") != "0"]
    if not layers:
        raise ValueError(f"{path}: no visible object layer {HOUSES_LAYER!r}")
    capacities: List[int] = []
    for layer in layers:
        for obj in layer.iter("object"):
            value = "0"
            for prop in obj.iter("property"):
                if prop.get("name") == CAPACITY_PROPERTY:
                    value = prop.get("value", "0")
            try:
                capacities.append(max(0, int(value)))
            except ValueError as error:
                raise ValueError(f"{path}: object {obj.get('id')} ({obj.get('name')!r}): "
                                 f"{CAPACITY_PROPERTY} {value!r} is not a whole number") from error
    return capacities


def load_town(path: Optional[str] = None) -> TownSpec:
    """The map's town as the simulation founds it."""
    return TownSpec(house_capacities=house_capacities(path), name="Town")
