"""The simulation's definitions, read from JSON in ``assets/data/`` and checked.

- ``goods.json``: the tradeable goods, their outside price and its walk, the
  cost of bringing them in, how much merchants move a day, and how much stock
  the market likes to hold. Their order is the order the market keeps them in,
  which the random generator's draws follow.
- ``needs.json``: per social class, its income and what a head wants a day,
  in three tiers (basic, comfort, luxury), and how much each tier weighs on
  its happiness.
- ``recipes.json``: production recipes: a batch's goods in and out, and the
  labour it takes.
- ``buildings.json``: building types: the recipe a workshop of that type runs,
  who works there and for what wage, how far it can grow and at what cost.
- ``scenarios/<name>.json``: who owns what in a town: the owners, and the
  workshops that stand there when a game starts.

Every mistake in a file is reported as a ``DataError`` naming the file, the
entry and the field, e.g.::

    goods.json, entry 3 ('Iron'): field 'outside_price': expected a number > 0, got 'x'

The files live under ``assets/`` because the release build copies exactly the
tracked files there (``build_tools/Release/build_release.py``).
"""
import json
import os
from dataclasses import dataclass, field
from typing import Any, Collection, Dict, List, Optional, Tuple

from ..config.constants import DATA_PATH
from .calendar import SEASONS

GOODS_FILE = "goods.json"
NEEDS_FILE = "needs.json"
RECIPES_FILE = "recipes.json"

TIERS = ("basic", "comfort", "luxury")      # bought in this order


class DataError(ValueError):
    """A definition file is missing, unreadable or breaks its schema."""


@dataclass(frozen=True)
class GoodDef:
    """A tradeable good as goods.json defines it."""
    name: str
    color: str                  # a colour's name in src/config/colors.py, for the charts
    chart_index: int            # its place in the charts and lists
    show_in_charts: bool        # shown in the price chart when a game starts
    outside_price: float        # the long-run mean of the price outside the town
    outside_reversion: float = 0.03     # share of the outside price's log deviation undone a day
    outside_volatility: float = 0.03    # the outside price's daily log step
    transport_cost: float = 0.0         # per unit, between the town and outside, either way
    import_limit: float = 0.0           # units merchants bring in a day at most (0: none)
    export_limit: float = 0.0           # units merchants take out a day at most (0: none)
    target_stock_days: float = 14.0     # days of the town's demand the market likes to hold
    min_target_stock: float = 50.0      # ...and at least this many units, demand or not
    noise_sigma: float = 0.004          # the price noise's log step per price tick
    outside_seasons: Dict[str, float] = field(default_factory=dict)   # season -> factor on the outside price


@dataclass(frozen=True)
class NeedDef:
    """One good a class wants, in units per head per day."""
    good: str
    units: float
    seasons: Dict[str, float] = field(default_factory=dict)   # season -> factor on the units (e.g. firewood in Winter)


@dataclass(frozen=True)
class ClassNeedsDef:
    """A social class as needs.json defines it."""
    name: str
    base_income: float                      # per head per day, from all the work that is not simulated
    labour_share: float                     # share of its heads that can take a job (phase 2)
    happiness_weights: Dict[str, float]     # tier -> weight; they add up to 1
    tiers: Dict[str, List[NeedDef]]         # tier -> what a head wants, in TIERS order


@dataclass(frozen=True)
class RecipeDef:
    """A production recipe as recipes.json defines it: one batch's goods in and out.

    Several outputs make byproducts (cattle: meat and hide). Amounts may be
    fractions (a tool wearing out by 0.05 a batch).
    """
    id: str
    inputs: Dict[str, float]    # good -> units used per batch (empty for raw goods)
    outputs: Dict[str, float]   # good -> units made per batch
    labour: float               # worker-days a batch takes
    name: str = ""
    description: str = ""


@dataclass(frozen=True)
class BuildingDef:
    """A type of workshop building as buildings.json defines it."""
    type: str
    name: str
    recipe: str                 # the recipe its workshops run
    workers_class: str          # the social class it hires from
    wage: float                 # per worker-day
    max_capacity: float         # batches a day it can grow to
    growth_cost: float          # money per batch a day of capacity added (paid out of town, to builders)
    working_capital: float      # cash a workshop keeps; profits above it go to its owner


@dataclass(frozen=True)
class OwnerDef:
    """Someone who owns workshops (the town now; the player and rival dynasties later)."""
    id: str
    kind: str                   # "town" | "player" | "dynasty": a label; no rule reads it
    name: str
    cash: float
    reserve: float              # cash it keeps; above it, surplus_to decides
    surplus_to: str             # "keep" (it stays the owner's) or "townsfolk" (paid out per head to the classes)


@dataclass(frozen=True)
class WorkshopSeed:
    """A workshop standing in a town when a game starts."""
    id: str
    owner: str
    building: str
    capacity: float             # batches a day
    cash: float


@dataclass(frozen=True)
class ScenarioDef:
    """Who owns what in a town when a game starts."""
    name: str
    owners: List[OwnerDef]
    workshops: List[WorkshopSeed]


@dataclass(frozen=True)
class Definitions:
    """Everything the simulation is defined by, as loaded from assets/data/."""
    goods: List[GoodDef]
    needs: List[ClassNeedsDef]
    recipes: List[RecipeDef] = field(default_factory=list)
    buildings: List[BuildingDef] = field(default_factory=list)


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


def _number(entry: _Entry, data: Dict[str, Any], field: str, minimum: float, strict: bool,
            maximum: Optional[float] = None) -> float:
    value = _require(entry, data, field)
    too_low = not _is_number(value) or (value <= minimum if strict else value < minimum)
    if too_low or (maximum is not None and value > maximum):
        relation = ">" if strict else ">="
        upper = f" and <= {maximum:g}" if maximum is not None else ""
        raise entry.fail(field, f"expected a number {relation} {minimum:g}{upper}, got {value!r}")
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


def _seasons(entry: _Entry, value: Any, field: str) -> Dict[str, float]:
    """A ``{season: factor}`` object; seasons left out have the factor 1."""
    if not isinstance(value, dict):
        raise entry.fail(field, f"expected an object of season -> factor, got {value!r}")
    for season, factor in value.items():
        if season not in SEASONS:
            raise entry.fail(field, f"unknown season {season!r} (known: {', '.join(SEASONS)})")
        if not _is_number(factor) or factor <= 0:
            raise entry.fail(field, f"{season!r}: expected a number > 0, got {factor!r}")
    return {s: float(f) for s, f in value.items()}


def _no_unknown_fields(entry: _Entry, data: Dict[str, Any], known: Collection[str]) -> None:
    for field_name in data:
        if field_name not in known:
            raise entry.fail(field_name, f"unknown field (known: {', '.join(sorted(known))})")


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


GOOD_FIELDS = ("name", "color", "chart_index", "show_in_charts", "outside_price", "outside_reversion",
               "outside_volatility", "outside_seasons", "transport_cost", "import_limit", "export_limit",
               "target_stock_days", "min_target_stock", "noise_sigma")


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
            color=_string(entry, data, "color"),
            chart_index=_integer(entry, data, "chart_index", 0),
            show_in_charts=_boolean(entry, data, "show_in_charts"),
            outside_price=float(_number(entry, data, "outside_price", 0, strict=True)),
            outside_reversion=float(_number(entry, data, "outside_reversion", 0, strict=False, maximum=1)),
            outside_volatility=float(_number(entry, data, "outside_volatility", 0, strict=False)),
            transport_cost=float(_number(entry, data, "transport_cost", 0, strict=False)),
            import_limit=float(_number(entry, data, "import_limit", 0, strict=False)),
            export_limit=float(_number(entry, data, "export_limit", 0, strict=False)),
            target_stock_days=float(_number(entry, data, "target_stock_days", 0, strict=True)),
            min_target_stock=float(_number(entry, data, "min_target_stock", 0, strict=True)),
            noise_sigma=float(_number(entry, data, "noise_sigma", 0, strict=False)),
            outside_seasons=_seasons(entry, data.get("outside_seasons", {}), "outside_seasons"),
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


CLASS_FIELDS = ("class", "base_income", "labour_share", "happiness_weights") + TIERS


def _need_items(entry: _Entry, data: Dict[str, Any], tier: str, goods: Collection[str]) -> List[NeedDef]:
    value = _require(entry, data, tier)
    if not isinstance(value, dict):
        raise entry.fail(tier, f"expected an object of good -> units per head per day, got {value!r}")
    items = []
    for good, amount in value.items():
        if good not in goods:
            raise entry.fail(tier, f"unknown good {good!r} (not in {GOODS_FILE})")
        seasons: Dict[str, float] = {}
        if isinstance(amount, dict):
            unknown = set(amount) - {"units", "seasons"}
            if unknown:
                raise entry.fail(tier, f"{good!r}: unknown field {sorted(unknown)[0]!r} (known: seasons, units)")
            seasons = _seasons(entry, amount.get("seasons", {}), f"{tier}.{good}.seasons")
            amount = amount.get("units")
        if not _is_number(amount) or amount <= 0:
            raise entry.fail(tier, f"{good!r}: expected a number > 0 (units per head per day), got {amount!r}")
        items.append(NeedDef(good, float(amount), seasons))
    return items


def parse_needs(items: List[Any], goods: Collection[str], classes: Optional[Collection[str]] = None,
                file: str = NEEDS_FILE) -> List[ClassNeedsDef]:
    """Check needs.json's ``"classes"`` list against the known goods (and classes, if given).

    Raises:
        DataError: On the first entry that breaks the schema, names an unknown
            good or class, repeats a class, or leaves out one of *classes*.
    """
    out: List[ClassNeedsDef] = []
    seen: Dict[str, int] = {}
    for entry, data in _entries(items, file, "class"):
        _no_unknown_fields(entry, data, CLASS_FIELDS)
        name = _string(entry, data, "class")
        if classes is not None and name not in classes:
            raise entry.fail("class", f"unknown class {name!r} (known: {', '.join(classes)})")
        if name in seen:
            raise entry.fail("class", f"{name!r} is already entry {seen[name]}")
        weights = _require(entry, data, "happiness_weights")
        if not isinstance(weights, dict) or set(weights) != set(TIERS):
            raise entry.fail("happiness_weights", f"expected an object with exactly {', '.join(TIERS)}, got {weights!r}")
        for tier, w in weights.items():
            if not _is_number(w) or w < 0:
                raise entry.fail("happiness_weights", f"{tier!r}: expected a number >= 0, got {w!r}")
        if abs(sum(weights.values()) - 1.0) > 1e-6:
            raise entry.fail("happiness_weights", f"the weights must add up to 1, they add up to {sum(weights.values()):g}")
        seen[name] = len(out)
        out.append(ClassNeedsDef(
            name=name,
            base_income=float(_number(entry, data, "base_income", 0, strict=False)),
            labour_share=float(_number(entry, data, "labour_share", 0, strict=False, maximum=1)),
            happiness_weights={t: float(weights[t]) for t in TIERS},
            tiers={t: _need_items(entry, data, t, goods) for t in TIERS},
        ))
    if classes is not None:
        missing = [c for c in classes if c not in seen]
        if missing:
            raise DataError(f"{file}: no entry for the class(es) {', '.join(missing)}")
    return out


RECIPE_FIELDS = ("id", "name", "description", "inputs", "outputs", "labour")


def _amounts(entry: _Entry, data: Dict[str, Any], field_name: str, goods: Collection[str],
             allow_empty: bool) -> Dict[str, float]:
    value = _require(entry, data, field_name)
    if not isinstance(value, dict) or (not value and not allow_empty):
        raise entry.fail(field_name, f"expected an object of good -> units{'' if allow_empty else ' (at least one)'}, got {value!r}")
    for good, units in value.items():
        if good not in goods:
            raise entry.fail(field_name, f"unknown good {good!r} (not in {GOODS_FILE})")
        if not _is_number(units) or units <= 0:
            raise entry.fail(field_name, f"{good!r}: expected a number > 0, got {units!r}")
    return {good: float(units) for good, units in value.items()}


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
        )
        if recipe.id in ids:
            raise entry.fail("id", f"{recipe.id!r} is already entry {ids[recipe.id]}")
        ids[recipe.id] = len(recipes)
        recipes.append(recipe)
    return recipes


BUILDING_FIELDS = ("type", "name", "recipe", "workers_class", "wage", "max_capacity", "growth_cost",
                   "working_capital")
BUILDINGS_FILE = "buildings.json"


def parse_buildings(items: List[Any], recipes: Collection[str], classes: Collection[str],
                    file: str = BUILDINGS_FILE) -> List[BuildingDef]:
    """Check buildings.json's ``"buildings"`` list against the known recipes and classes."""
    out: List[BuildingDef] = []
    seen: Dict[str, int] = {}
    for entry, data in _entries(items, file, "type"):
        _no_unknown_fields(entry, data, BUILDING_FIELDS)
        building = BuildingDef(
            type=_string(entry, data, "type"),
            name=_string(entry, data, "name"),
            recipe=_string(entry, data, "recipe"),
            workers_class=_string(entry, data, "workers_class"),
            wage=float(_number(entry, data, "wage", 0, strict=False)),
            max_capacity=float(_number(entry, data, "max_capacity", 0, strict=True)),
            growth_cost=float(_number(entry, data, "growth_cost", 0, strict=False)),
            working_capital=float(_number(entry, data, "working_capital", 0, strict=False)),
        )
        if building.recipe not in recipes:
            raise entry.fail("recipe", f"unknown recipe {building.recipe!r} (not in {RECIPES_FILE})")
        if building.workers_class not in classes:
            raise entry.fail("workers_class", f"unknown class {building.workers_class!r} (known: {', '.join(classes)})")
        if building.type in seen:
            raise entry.fail("type", f"{building.type!r} is already entry {seen[building.type]}")
        seen[building.type] = len(out)
        out.append(building)
    return out


OWNER_FIELDS = ("id", "kind", "name", "cash", "reserve", "surplus_to")
WORKSHOP_FIELDS = ("id", "owner", "building", "capacity", "cash")
SURPLUS_RULES = ("keep", "townsfolk")


def parse_scenario(data: Any, buildings: Collection[str], file: str) -> ScenarioDef:
    """Check a scenario file: its owners, and its workshops against the owners and building types."""
    if not isinstance(data, dict) or not isinstance(data.get("owners"), list) or not isinstance(data.get("workshops"), list):
        raise DataError(f"{file}: expected an object with lists 'owners' and 'workshops'")
    owners: List[OwnerDef] = []
    owner_ids: Dict[str, int] = {}
    for entry, item in _entries(data["owners"], f"{file} owners", "id"):
        _no_unknown_fields(entry, item, OWNER_FIELDS)
        owner = OwnerDef(
            id=_string(entry, item, "id"),
            kind=_string(entry, item, "kind"),
            name=_string(entry, item, "name"),
            cash=float(_number(entry, item, "cash", 0, strict=False)),
            reserve=float(_number(entry, item, "reserve", 0, strict=False)),
            surplus_to=_string(entry, item, "surplus_to"),
        )
        if owner.surplus_to not in SURPLUS_RULES:
            raise entry.fail("surplus_to", f"expected one of {', '.join(SURPLUS_RULES)}, got {owner.surplus_to!r}")
        if owner.id in owner_ids:
            raise entry.fail("id", f"{owner.id!r} is already entry {owner_ids[owner.id]}")
        owner_ids[owner.id] = len(owners)
        owners.append(owner)
    workshops: List[WorkshopSeed] = []
    workshop_ids: Dict[str, int] = {}
    for entry, item in _entries(data["workshops"], f"{file} workshops", "id"):
        _no_unknown_fields(entry, item, WORKSHOP_FIELDS)
        seed = WorkshopSeed(
            id=_string(entry, item, "id"),
            owner=_string(entry, item, "owner"),
            building=_string(entry, item, "building"),
            capacity=float(_number(entry, item, "capacity", 0, strict=False)),
            cash=float(_number(entry, item, "cash", 0, strict=False)),
        )
        if seed.owner not in owner_ids:
            raise entry.fail("owner", f"unknown owner {seed.owner!r}")
        if seed.building not in buildings:
            raise entry.fail("building", f"unknown building type {seed.building!r} (not in {BUILDINGS_FILE})")
        if seed.id in workshop_ids:
            raise entry.fail("id", f"{seed.id!r} is already entry {workshop_ids[seed.id]}")
        workshop_ids[seed.id] = len(workshops)
        workshops.append(seed)
    return ScenarioDef(name=os.path.splitext(os.path.basename(file))[0], owners=owners, workshops=workshops)


def load_goods(folder: Optional[str] = None) -> List[GoodDef]:
    """The goods in ``goods.json`` (in *folder*, ``assets/data/`` by default)."""
    folder = folder or DATA_PATH
    return parse_goods(_read(os.path.join(folder, GOODS_FILE), GOODS_FILE, "goods"))


def load_needs(goods: Collection[str], classes: Optional[Collection[str]] = None,
               folder: Optional[str] = None) -> List[ClassNeedsDef]:
    """The classes' needs in ``needs.json``, checked against the given goods (and classes)."""
    folder = folder or DATA_PATH
    return parse_needs(_read(os.path.join(folder, NEEDS_FILE), NEEDS_FILE, "classes"), goods, classes)


def load_recipes(goods: Collection[str], folder: Optional[str] = None) -> List[RecipeDef]:
    """The recipes in ``recipes.json``, checked against the given good names."""
    folder = folder or DATA_PATH
    return parse_recipes(_read(os.path.join(folder, RECIPES_FILE), RECIPES_FILE, "recipes"), goods)


def load_buildings(recipes: Collection[str], classes: Collection[str], folder: Optional[str] = None) -> List[BuildingDef]:
    """The building types in ``buildings.json``, checked against the given recipes and classes."""
    folder = folder or DATA_PATH
    return parse_buildings(_read(os.path.join(folder, BUILDINGS_FILE), BUILDINGS_FILE, "buildings"), recipes, classes)


def load_definitions(classes: Collection[str], folder: Optional[str] = None) -> Definitions:
    """Goods, needs, recipes and building types from *folder* (``assets/data/`` by default), each checked."""
    goods = load_goods(folder)
    names = [g.name for g in goods]
    recipes = load_recipes(names, folder)
    return Definitions(
        goods=goods,
        needs=load_needs(names, classes, folder),
        recipes=recipes,
        buildings=load_buildings([r.id for r in recipes], classes, folder),
    )


def load_scenario(name: str, buildings: Collection[str], folder: Optional[str] = None) -> ScenarioDef:
    """The scenario ``scenarios/<name>.json``: who owns which workshops when a game starts."""
    folder = folder or DATA_PATH
    file = f"scenarios/{name}.json"
    path = os.path.join(folder, "scenarios", f"{name}.json")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError as error:
        raise DataError(f"{file}: not found at {path}") from error
    except json.JSONDecodeError as error:
        raise DataError(f"{file}: not valid JSON: {error}") from error
    return parse_scenario(data, buildings, file)
