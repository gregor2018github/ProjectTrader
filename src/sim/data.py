"""The simulation's definitions, read from JSON in ``assets/data/`` and checked.

``goods.json`` lists the tradeable goods (their order is the order the market
creates them in, which the random generator's draws follow); ``recipes.json``
lists production recipes, which nothing runs yet (P1). Every mistake in a file
is reported as a ``DataError`` naming the file, the entry and the field, e.g.::

    goods.json, entry 3 ('Iron'): field 'start_price': expected a number > 0, got 'x'

The files live under ``assets/`` because the release build copies exactly the
tracked files there (``build_tools/Release/build_release.py``).
"""
import json
import os
from dataclasses import dataclass
from typing import Any, Collection, Dict, List, Optional, Tuple

from ..config.constants import DATA_PATH

GOODS_FILE = "goods.json"
RECIPES_FILE = "recipes.json"


class DataError(ValueError):
    """A definition file is missing, unreadable or breaks its schema."""


@dataclass(frozen=True)
class GoodDef:
    """A tradeable good as goods.json defines it."""
    name: str
    start_price: float          # the walk's starting price
    start_quantity: int         # the market's starting (and normal) volume
    color: str                  # a colour's name in src/config/colors.py, for the charts
    chart_index: int            # its place in the charts and lists
    show_in_charts: bool        # shown in the price chart when a game starts


@dataclass(frozen=True)
class RecipeDef:
    """A production recipe as recipes.json defines it: one batch's goods in and out.

    Nothing runs recipes yet; P1's workshops will.
    """
    id: str
    inputs: Dict[str, int]      # good -> units used per batch (empty for raw goods)
    outputs: Dict[str, int]     # good -> units made per batch
    labour: float               # worker-days a batch takes
    days: float                 # how long a batch takes
    name: str = ""
    description: str = ""


class _Entry:
    """Error messages for one entry of one file."""

    def __init__(self, file: str, index: int, label: str) -> None:
        self.where = f"{file}, entry {index}" + (f" ({label!r})" if label else "")

    def fail(self, field: str, problem: str) -> "DataError":
        return DataError(f"{self.where}: field {field!r}: {problem}")


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _require(entry: _Entry, data: Dict[str, Any], field: str) -> Any:
    if field not in data:
        raise entry.fail(field, "missing")
    return data[field]


def _string(entry: _Entry, data: Dict[str, Any], field: str, optional: bool = False) -> str:
    if optional and field not in data:
        return ""
    value = _require(entry, data, field)
    if not isinstance(value, str) or not value.strip():
        raise entry.fail(field, f"expected a non-empty string, got {value!r}")
    return value


def _number(entry: _Entry, data: Dict[str, Any], field: str, minimum: float, strict: bool) -> float:
    value = _require(entry, data, field)
    if not _is_number(value) or (value <= minimum if strict else value < minimum):
        relation = ">" if strict else ">="
        raise entry.fail(field, f"expected a number {relation} {minimum:g}, got {value!r}")
    return value


def _integer(entry: _Entry, data: Dict[str, Any], field: str, minimum: int) -> int:
    value = _require(entry, data, field)
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise entry.fail(field, f"expected a whole number >= {minimum}, got {value!r}")
    return value


def _boolean(entry: _Entry, data: Dict[str, Any], field: str) -> bool:
    value = _require(entry, data, field)
    if not isinstance(value, bool):
        raise entry.fail(field, f"expected true or false, got {value!r}")
    return value


def _no_unknown_fields(entry: _Entry, data: Dict[str, Any], known: Collection[str]) -> None:
    for field in data:
        if field not in known:
            raise entry.fail(field, f"unknown field (known: {', '.join(sorted(known))})")


def _read(path: str, file: str, key: str) -> List[Any]:
    """The list under *key* in the JSON file at *path*."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError as error:
        raise DataError(f"{file}: not found at {path}") from error
    except json.JSONDecodeError as error:
        raise DataError(f"{file}: not valid JSON: {error}") from error
    if not isinstance(data, dict) or not isinstance(data.get(key), list):
        raise DataError(f"{file}: expected an object with a list {key!r}")
    return data[key]


def _entries(items: List[Any], file: str, label_field: str) -> List[Tuple[_Entry, Dict[str, Any]]]:
    out = []
    for index, item in enumerate(items):
        label = item.get(label_field, "") if isinstance(item, dict) else ""
        entry = _Entry(file, index, label if isinstance(label, str) else "")
        if not isinstance(item, dict):
            raise DataError(f"{entry.where}: expected an object, got {item!r}")
        out.append((entry, item))
    return out


GOOD_FIELDS = ("name", "start_price", "start_quantity", "color", "chart_index", "show_in_charts")


def parse_goods(items: List[Any], file: str = GOODS_FILE) -> List[GoodDef]:
    """Check goods.json's ``"goods"`` list and turn it into definitions, in its order.

    Raises:
        DataError: On the first entry that breaks the schema, or a repeated name or chart index.
    """
    goods: List[GoodDef] = []
    names: Dict[str, int] = {}
    indices: Dict[int, int] = {}
    for entry, data in _entries(items, file, "name"):
        _no_unknown_fields(entry, data, GOOD_FIELDS)
        good = GoodDef(
            name=_string(entry, data, "name"),
            start_price=float(_number(entry, data, "start_price", 0, strict=True)),
            start_quantity=_integer(entry, data, "start_quantity", 1),
            color=_string(entry, data, "color"),
            chart_index=_integer(entry, data, "chart_index", 0),
            show_in_charts=_boolean(entry, data, "show_in_charts"),
        )
        if good.name in names:
            raise entry.fail("name", f"{good.name!r} is already entry {names[good.name]}")
        if good.chart_index in indices:
            raise entry.fail("chart_index", f"{good.chart_index} is already used by entry {indices[good.chart_index]}")
        names[good.name] = len(goods)
        indices[good.chart_index] = len(goods)
        goods.append(good)
    if not goods:
        raise DataError(f"{file}: no goods defined")
    return goods


RECIPE_FIELDS = ("id", "name", "description", "inputs", "outputs", "labour", "days")


def _amounts(entry: _Entry, data: Dict[str, Any], field: str, goods: Collection[str], allow_empty: bool) -> Dict[str, int]:
    value = _require(entry, data, field)
    if not isinstance(value, dict) or (not value and not allow_empty):
        raise entry.fail(field, f"expected an object of good -> units{'' if allow_empty else ' (at least one)'}, got {value!r}")
    for good, units in value.items():
        if good not in goods:
            raise entry.fail(field, f"unknown good {good!r} (not in {GOODS_FILE})")
        if not isinstance(units, int) or isinstance(units, bool) or units < 1:
            raise entry.fail(field, f"{good!r}: expected a whole number >= 1, got {units!r}")
    return dict(value)


def parse_recipes(items: List[Any], goods: Collection[str], file: str = RECIPES_FILE) -> List[RecipeDef]:
    """Check recipes.json's ``"recipes"`` list against the known goods.

    Raises:
        DataError: On the first entry that breaks the schema, names an unknown
            good, or repeats an id.
    """
    recipes: List[RecipeDef] = []
    ids: Dict[str, int] = {}
    for entry, data in _entries(items, file, "id"):
        _no_unknown_fields(entry, data, RECIPE_FIELDS)
        recipe = RecipeDef(
            id=_string(entry, data, "id"),
            name=_string(entry, data, "name", optional=True),
            description=_string(entry, data, "description", optional=True),
            inputs=_amounts(entry, data, "inputs", goods, allow_empty=True),
            outputs=_amounts(entry, data, "outputs", goods, allow_empty=False),
            labour=float(_number(entry, data, "labour", 0, strict=False)),
            days=float(_number(entry, data, "days", 0, strict=True)),
        )
        if recipe.id in ids:
            raise entry.fail("id", f"{recipe.id!r} is already entry {ids[recipe.id]}")
        ids[recipe.id] = len(recipes)
        recipes.append(recipe)
    return recipes


def load_goods(folder: Optional[str] = None) -> List[GoodDef]:
    """The goods in ``goods.json`` (in *folder*, ``assets/data/`` by default)."""
    folder = folder or DATA_PATH
    return parse_goods(_read(os.path.join(folder, GOODS_FILE), GOODS_FILE, "goods"))


def load_recipes(goods: Collection[str], folder: Optional[str] = None) -> List[RecipeDef]:
    """The recipes in ``recipes.json``, checked against the given good names."""
    folder = folder or DATA_PATH
    return parse_recipes(_read(os.path.join(folder, RECIPES_FILE), RECIPES_FILE, "recipes"), goods)
