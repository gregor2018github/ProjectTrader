"""Save/load system for ProjectTrader.

Save files are binary: first 32 bytes are the HMAC-SHA256 digest of the
remaining bytes, which are gzip-compressed JSON.  Tampering with the data
invalidates the digest and causes the load to be rejected.

An autosave is written in the background (``save_game(..., background=True)``)
so play does not stutter: the game is copied on the main thread in a few
milliseconds (the plain dict, frozen with ``marshal``), and the slow part,
encoding, compressing and writing, runs in a thread with a pure-Python JSON
encoder, which hands the interpreter back to the game every few milliseconds
(``json.dumps``'s C encoder would hold it for the whole ~0.1 s). Everything here
that touches the saves folder first waits for that write (``wait_for_save``).
Files are written to a ``.tmp`` and renamed, so a crash mid-write never leaves
a broken save.
"""

import datetime
import gzip
import hashlib
import hmac
import json
import marshal
import os
import threading
from typing import Any, Dict, List, Optional

from ..models.meal_effects import MealEffect
from ..models import inn_rooms
from ..models.player_names import name_of_save
from ..models.figurines.humans.hair import DEFAULT_HAIR, hair_key
from ..models.statistics import Statistics

from ..config.constants import MARKET_FEE_RATE, PRICE_TICK_MINUTES, DEFAULT_QUICKTRADE_SLOTS, TOP_BAR_DEFAULT_PINS, SAVES_PATH, SAVE_SECRET_KEY, STARTING_STORAGE_SLOTS, PACK_SLOTS

SAVE_VERSION = 3   # 2: the price chart has a point per price tick (PRICE_TICK_MINUTES), no longer per hour
                   # 3: the economy is the "sim" block (src/sim/), with its own "sim_version"; "goods" keeps only how the UI shows them

# Slot number of the single autosave.  Manual slots start at 1, so 0 never
# collides; the autosave is stored as autosave.sav instead of slot_0.sav.
AUTOSAVE_SLOT = 0
AUTOSAVE_NAME = "Autosave"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _file_stem(slot: int) -> str:
    return "autosave" if slot == AUTOSAVE_SLOT else f"slot_{slot}"


def _slot_path(slot: int) -> str:
    return os.path.join(SAVES_PATH, f"{_file_stem(slot)}.sav")


def thumbnail_path(slot: int) -> str:
    """Path of the screenshot thumbnail belonging to *slot*."""
    return os.path.join(SAVES_PATH, f"{_file_stem(slot)}_thumb.png")


def _used_slots() -> List[int]:
    """Return the sorted slot numbers that have a save file in the saves folder."""
    try:
        names = os.listdir(SAVES_PATH)
    except OSError:
        return []
    slots = []
    for name in names:
        if name.startswith("slot_") and name.endswith(".sav"):
            number = name[len("slot_"):-len(".sav")]
            if number.isdigit() and int(number) > 0:
                slots.append(int(number))
    return sorted(slots)


def _hourly_to_ticks(prices: List[float]) -> List[float]:
    """An hourly price chart (saves before version 2) at one point per price tick, the ticks
    between two hours filled in on the straight line; the last point stays the latest price."""
    per_hour = max(1, 60 // PRICE_TICK_MINUTES)
    if per_hour == 1 or len(prices) < 2:
        return list(prices)
    ticks = []
    for a, b in zip(prices, prices[1:]):
        ticks.extend(a + (b - a) * k / per_hour for k in range(per_hour))
    ticks.append(prices[-1])
    return ticks


def _dt_to_str(dt: datetime.datetime) -> str:
    return dt.isoformat()


def _str_to_dt(s: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(s)


def _dt_list(records: list, key: str) -> list:
    """Convert a datetime key from ISO strings to datetime objects in-place."""
    for r in records:
        if key in r and isinstance(r[key], str):
            r[key] = _str_to_dt(r[key])
    return records


# zlib's level 6: 0.06 s instead of 0.7 s at 9 on a 6.5 MB save, for a file about 5 % larger
_COMPRESS_LEVEL = 6

# The background write still running, if any, and what the last one raised
_pending: Optional[threading.Thread] = None
_pending_error: Optional[BaseException] = None


def _pack(data: Dict[str, Any]) -> bytes:
    # The pure-Python encoder (iterencode without _one_shot) writes the same
    # text as json.dumps, but lets other threads run while it does
    text = "".join(json.JSONEncoder(ensure_ascii=False).iterencode(data))
    compressed = gzip.compress(text.encode("utf-8"), compresslevel=_COMPRESS_LEVEL)
    digest = hmac.new(
        SAVE_SECRET_KEY.encode("utf-8"), compressed, hashlib.sha256
    ).digest()
    return digest + compressed


def _unpack(blob: bytes) -> Dict[str, Any]:
    if len(blob) < 32:
        raise ValueError("Corrupted save file: too short.")
    digest_stored = blob[:32]
    compressed = blob[32:]
    digest_expected = hmac.new(
        SAVE_SECRET_KEY.encode("utf-8"), compressed, hashlib.sha256
    ).digest()
    if not hmac.compare_digest(digest_stored, digest_expected):
        raise ValueError("Save file has been tampered with or is corrupted.")
    json_bytes = gzip.decompress(compressed)
    return json.loads(json_bytes.decode("utf-8"))


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

def _serialize_game(game_state: Any, player: Any, depot: Any, goods: List[Any], save_name: str = "", sim: Any = None, fog: Any = None, weather: Any = None, merchant_rank: Any = None, intro: Any = None, council: Any = None, harvest: Any = None, lost_sheep: Any = None, chickens: Any = None) -> Dict[str, Any]:
    return {
        "save_version": SAVE_VERSION,
        "saved_at": _dt_to_str(datetime.datetime.now()),
        "save_name": save_name,
        "playtime_seconds": getattr(game_state, "playtime_seconds", 0.0),
        "game_state": {
            "date": _dt_to_str(game_state.date),
            "time_level": game_state.time_level,
            "left_side_mode": game_state.left_side_mode,
            "right_side_mode": game_state.right_side_mode,
            "input_fields": dict(game_state.input_fields),
            "depot_time_frame": game_state.depot_time_frame,
            "chart_selection_order": list(getattr(game_state, "chart_selection_order", [])),
            "quicktrade_slots": {k: list(v) for k, v in getattr(game_state, "quicktrade_slots", {}).items()},
            "good_quantities": dict(getattr(game_state, "good_quantities", {})),
            "pinned_goods": list(getattr(game_state, "pinned_goods", [])),
            "event_log": [
                {**e, "timestamp": _dt_to_str(e["timestamp"])}
                for e in getattr(game_state, "event_log", [])
            ],
        },
        "player": {
            "name": player.name,
            "hair": getattr(player, "hair", DEFAULT_HAIR),
            "score": player.score,
            "reputation": player.reputation,
            "tiredness": player.tiredness,
            "meal": player.meal.to_save() if getattr(player, "meal", None) is not None else None,
            "rooms": inn_rooms.to_save(player),
            "daily_cost_of_living": player.daily_cost_of_living,
            "position": list(player.position),
            "in_market_area": player.in_market_area,
        },
        "depot": {
            "money": depot.money,
            "fee_rate": depot.fee_rate,
            "storage_capacity": depot.storage_capacity,
            "warehouse_count": depot.warehouse_count,
            "good_stock": dict(depot.good_stock),
            "starting_slots": [dict(slot) for slot in depot.starting_slots],
            "starting_accepts": None if depot.starting_accepts is None else list(depot.starting_accepts),
            "pack_slots": [dict(slot) for slot in depot.pack_slots],
            "storage_order": list(depot.storage_order),
            "properties": {k: list(v) for k, v in depot.properties.items()},
            "expenditures": depot.expenditures,
            "income": depot.income,
            "transaction_expenditures": depot.transaction_expenditures,
            "donation_expenditures": depot.donation_expenditures,
            "cost_of_living_expenditures": depot.cost_of_living_expenditures,
            "license_expenditures": depot.license_expenditures,
            "donations": dict(depot.donations),
            "labor_income": dict(depot.labor_income),
            "cost_of_living": dict(depot.cost_of_living),
            "wealth": list(depot.wealth),
            "money_history": list(depot.money_history),
            "property_value_history": list(depot.property_value_history),
            "loan_history": list(depot.loan_history),
            "total_stock": list(depot.total_stock),
            "house_history": list(depot.house_history),
            "storage_capacity_history": list(depot.storage_capacity_history),
            "stock_history": {k: list(v) for k, v in depot.stock_history.items()},
            "trades": [
                {**t, "timestamp": _dt_to_str(t["timestamp"])}
                for t in depot.trades
            ],
            "expenditure_history": list(depot.expenditure_history),
            "income_history": list(depot.income_history),
            "transaction_expenditure_history": list(depot.transaction_expenditure_history),
            "donation_expenditure_history": list(depot.donation_expenditure_history),
            "cost_of_living_expenditure_history": list(depot.cost_of_living_expenditure_history),
            "license_expenditure_history": list(depot.license_expenditure_history),
            "loan_expenditure_history": list(depot.loan_expenditure_history),
            "overdraft_expenditure_history": list(depot.overdraft_expenditure_history),
            "miscellaneous_expenditure_history": list(depot.miscellaneous_expenditure_history),
            "miscellaneous_expenditures": depot.miscellaneous_expenditures,
            "property_expenditure_history": list(depot.property_expenditure_history),
            "property_expenditures": depot.property_expenditures,
            "active_loans": [dict(loan) for loan in depot.active_loans],
            "donation_history": {k: list(v) for k, v in depot.donation_history.items()},
            "labor_income_history": {k: list(v) for k, v in depot.labor_income_history.items()},
            "cost_of_living_history": {k: list(v) for k, v in depot.cost_of_living_history.items()},
            "purchase_history": {
                good_name: [
                    {**entry, "timestamp": _dt_to_str(entry["timestamp"])}
                    for entry in entries
                ]
                for good_name, entries in depot.purchase_history.items()
            },
            "trade_cycles": depot.trade_cycles,
            "trade_cycle_records": [
                {**r, "timestamp": _dt_to_str(r["timestamp"])}
                for r in depot.trade_cycle_records
            ],
            "trading_licenses": {
                k: _dt_to_str(v) for k, v in depot.trading_licenses.items()
            },
            "statistics": depot.stats.to_dict(),
        },
        # How the UI shows each good; its market numbers are in "sim"
        "goods": [
            {
                "name": g.name,
                "show_in_charts": g.show_in_charts,
                "color_current": list(g.color_current),
            }
            for g in goods
        ],
        # The economy (Simulation.to_dict): prices, volumes, people, the random generator
        "sim": sim.to_dict() if sim is not None else None,
        # Explored land; loaded by GameMap.restore_map_fog, missing means none
        "fog": fog.to_save() if fog is not None else None,
        # Loaded by Weather.load, missing means the weather goes on as it is
        "weather": weather.to_save() if weather is not None else None,
        # Loaded by MerchantRank.load, missing means the first rank
        "merchant_rank": merchant_rank.to_save() if merchant_rank is not None else None,
        # How far the intro has got (models/intro.py); a save without it has had it
        "intro": intro.to_save() if intro is not None else None,
        # How many plants of each field are cut this year (models/harvest.py); a save without it has none cut
        "harvest": harvest.to_save() if harvest is not None else None,
        # The town council (models/council.py); a save without it starts with the data file's council
        "council": council.to_save() if council is not None else None,
        # The quest for the shepherdess's black sheep (models/lost_sheep.py); a save without it has not begun it
        "lost_sheep": lost_sheep.to_save() if lost_sheep is not None else None,
        # The pen's chickens' looks (models/chickens.py); a save without them gets a flock drawn from its seed
        "chickens": chickens.to_save() if chickens is not None else None,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def wait_for_save() -> None:
    """Block until the background save, if one is running, has been written."""
    global _pending
    if _pending is not None:
        _pending.join()
        _pending = None


def save_in_progress() -> bool:
    """Whether a background save is still being written."""
    return _pending is not None and _pending.is_alive()


def take_save_error() -> Optional[BaseException]:
    """What the last finished background save raised (once), or None."""
    global _pending_error
    if save_in_progress():
        return None
    error, _pending_error = _pending_error, None
    return error


def _write_blob(slot: int, data: Dict[str, Any]) -> None:
    path = _slot_path(slot)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(_pack(data))
    os.replace(tmp, path)


def _write_frozen(slot: int, frozen: bytes) -> None:
    """The background thread: thaw the copy and write it."""
    global _pending_error
    try:
        _write_blob(slot, marshal.loads(frozen))
    except BaseException as e:   # reported by take_save_error()
        _pending_error = e


def save_game(slot: int, game_state: Any, player: Any, depot: Any, goods: List[Any], save_name: str = "", sim: Any = None, fog: Any = None, weather: Any = None, merchant_rank: Any = None, intro: Any = None, council: Any = None, harvest: Any = None,
              lost_sheep: Any = None, chickens: Any = None, background: bool = False) -> None:
    """Serialize the full game state and write it to the given slot file
    (1-based, or AUTOSAVE_SLOT).

    With *background*, only the copy of the game is made now and the file is
    written by a thread (see the module's docstring); its errors come from
    take_save_error() instead of being raised.
    """
    global _pending
    wait_for_save()
    os.makedirs(SAVES_PATH, exist_ok=True)
    data = _serialize_game(game_state, player, depot, goods, save_name, sim, fog, weather, merchant_rank, intro, council,
                           harvest, lost_sheep, chickens)
    if background:
        try:
            # A deep copy of plain data in a few ms, so the game may go on changing its own
            frozen = marshal.dumps(data)
        except ValueError:   # something marshal cannot take: write it here and now
            frozen = None
        if frozen is not None:
            # Not a daemon: quitting right after waits for the file to be written
            _pending = threading.Thread(target=_write_frozen, args=(slot, frozen), name="save-writer")
            _pending.start()
            return
    _write_blob(slot, data)


def load_game(slot: int) -> Dict[str, Any]:
    """Load and verify a save file. Returns the raw deserialized dict.

    Raises:
        FileNotFoundError: if the slot file does not exist.
        ValueError: if the file is tampered with or corrupted.
    """
    wait_for_save()
    path = _slot_path(slot)
    if not os.path.exists(path):
        raise FileNotFoundError(f"No save in slot {slot}.")
    with open(path, "rb") as f:
        blob = f.read()
    return _unpack(blob)


def get_save_slots() -> List[Dict[str, Any]]:
    """Return one slot-info dict per save file in the saves folder.

    The autosave (if present) comes first, then the manual slots by number.
    Every entry contains slot (int), autosave (bool) and corrupted (bool).
    Readable saves also contain saved_at (str), game_date (str), money,
    wealth, playtime_seconds, save_name and thumbnail_path.
    """
    wait_for_save()
    slots = _used_slots()
    if os.path.exists(_slot_path(AUTOSAVE_SLOT)):
        slots.insert(0, AUTOSAVE_SLOT)
    result: List[Dict[str, Any]] = []
    for slot in slots:
        autosave = slot == AUTOSAVE_SLOT
        try:
            with open(_slot_path(slot), "rb") as f:
                blob = f.read()
            data = _unpack(blob)
            thumb_path = thumbnail_path(slot)
            wealth_history = data["depot"].get("wealth", [])
            result.append({
                "slot": slot,
                "autosave": autosave,
                "corrupted": False,
                "saved_at": data["saved_at"],
                "game_date": data["game_state"]["date"],
                "money": data["depot"]["money"],
                "wealth": wealth_history[-1] if wealth_history else data["depot"]["money"],
                "playtime_seconds": data.get("playtime_seconds", 0.0),
                "save_name": data.get("save_name", ""),
                "player_name": name_of_save(data),
                "thumbnail_path": thumb_path if os.path.exists(thumb_path) else None,
            })
        except Exception:
            result.append({
                "slot": slot,
                "autosave": autosave,
                "corrupted": True,
                "save_name": AUTOSAVE_NAME if autosave else "",
            })
    return result


def next_free_slot() -> int:
    """Return the lowest slot number without a save file (for a new save)."""
    wait_for_save()
    used = set(_used_slots())
    slot = 1
    while slot in used:
        slot += 1
    return slot


def delete_save(slot: int) -> None:
    """Delete the save file and its thumbnail for the given slot, if they exist."""
    wait_for_save()
    for path in (_slot_path(slot), thumbnail_path(slot)):
        if os.path.exists(path):
            os.remove(path)


def _enforce_chart_limit(goods: List[Any], game_state: Any) -> None:
    """Enforce max-3 chart visibility and keep chart_selection_order consistent.

    Visible goods beyond three (sorted by index, highest closed first) are turned
    off.  The order list is then rebuilt: entries already in the list that are
    still visible stay in place; any remaining visible goods are appended in
    index order.  Entries in the order list that are no longer visible are
    removed, and duplicates are deduplicated.
    """
    visible = sorted([g for g in goods if g.show_in_charts], key=lambda g: g.index)
    while len(visible) > 3:
        visible[-1].show_in_charts = False
        visible.pop()

    visible_names = {g.name for g in visible}
    # Rebuild order: keep existing valid entries, then fill from visible by index
    existing_order = getattr(game_state, "chart_selection_order", [])
    seen: set = set()
    new_order: list = []
    for name in existing_order:
        if name in visible_names and name not in seen:
            new_order.append(name)
            seen.add(name)
    for g in visible:
        if g.name not in seen:
            new_order.append(g.name)
            seen.add(g.name)
    game_state.chart_selection_order = new_order
    if hasattr(game_state, 'sync_quicktrade_fields'):
        game_state.sync_quicktrade_fields()


def _migrate_property_expenses(depot: Any) -> None:
    """Rebuild the property bookkeeping for saves written before it existed.

    Those saves booked every building purchase as a miscellaneous expense
    ("Well Coins"), never recorded a property value, counted only
    depot.properties["houses"] (always empty) as owned buildings and kept no
    storage capacity history. Well coins cost 1g, so a day whose miscellaneous
    total covers a building's purchase price is safely attributed to that
    purchase; from that day onward the building's value, its storage and the
    building count are folded into the histories, so past days match how the
    game keeps books now.
    """
    n = len(depot.expenditure_history)
    depot.property_expenditure_history = [0.0] * n
    depot.property_expenditures = 0.0

    misc = depot.miscellaneous_expenditure_history
    if len(misc) < n:
        misc = [0.0] * (n - len(misc)) + list(misc)
    else:
        misc = list(misc[-n:])

    buildings = [
        building
        for category in depot.properties.values()
        for building in category
        if isinstance(building, dict) and building.get("buy_price", 0.0) > 0
    ]

    # Assign each building to the most recent day whose miscellaneous expenses
    # can still cover its price, most expensive building first.
    purchases_by_day: Dict[int, List[Dict[str, Any]]] = {}
    for building in sorted(buildings, key=lambda b: b.get("buy_price", 0.0), reverse=True):
        price = building.get("buy_price", 0.0)
        for i in range(n - 1, -1, -1):
            if misc[i] >= price:
                misc[i] -= price
                purchases_by_day.setdefault(i, []).append(building)
                depot.property_expenditure_history[i] += price
                break

    depot.miscellaneous_expenditure_history = misc

    # Running totals of value, storage and building count per day.
    base_storage = depot.storage_capacity - sum(b.get("buy_storage", 0) for b in buildings)
    value_by_day: List[float] = []
    storage_by_day: List[int] = []
    count_by_day: List[int] = []
    value, storage, count = 0.0, base_storage, 0
    for i in range(n):
        for building in purchases_by_day.get(i, []):
            value += building.get("buy_price", 0.0)
            storage += building.get("buy_storage", 0)
            count += 1
        value_by_day.append(value)
        storage_by_day.append(storage)
        count_by_day.append(count)

    depot.property_value_history = value_by_day
    depot.storage_capacity_history = storage_by_day
    depot.house_history = count_by_day

    # Fold the property value into the recorded wealth, which was written
    # before buildings counted toward it.
    offset = len(depot.wealth) - n  # both histories end on the same day
    for i in range(len(depot.wealth)):
        day = i - offset
        if 0 <= day < n:
            depot.wealth[i] += value_by_day[day]
        elif day >= n:
            depot.wealth[i] += value


def apply_save_data(data: Dict[str, Any], game_state: Any, player: Any, depot: Any, goods: List[Any], sim: Any = None) -> None:
    """Apply a loaded save dict to the live game objects in-place.

    The economy goes into *sim* (``Simulation.load``), from the save's ``"sim"``
    block or, for a save from before it (SAVE_VERSION < 3), from its old
    ``"goods"`` and ``"population"`` entries (``_legacy_sim_block``).
    """
    game_state.playtime_seconds = data.get("playtime_seconds", 0.0)

    gs = data["game_state"]
    game_state.date = _str_to_dt(gs["date"])
    game_state.time_level = gs["time_level"]
    game_state.previous_time_level = gs["time_level"]
    game_state.left_side_mode = gs["left_side_mode"]
    game_state.right_side_mode = gs["right_side_mode"]
    game_state.input_fields = gs["input_fields"]
    # Older saves may name a period the calendar no longer has ("Weekly", "Monthly")
    frame = gs["depot_time_frame"]
    game_state.depot_time_frame = frame if frame in game_state.depot_time_frames else "Daily"
    game_state.chart_selection_order = gs.get("chart_selection_order", [])
    # Saves from before each market square had its own slots start with the defaults
    game_state.quicktrade_slots = {
        area: list(slots) for area, slots in DEFAULT_QUICKTRADE_SLOTS.items()
    }
    game_state.quicktrade_slots.update({k: list(v) for k, v in gs.get("quicktrade_slots", {}).items()})
    game_state.event_log = _dt_list(gs.get("event_log", []), "timestamp")
    default_qtys = dict(getattr(game_state, "default_good_quantities", {}))
    saved_qtys = gs.get("good_quantities", {})
    default_qtys.update(saved_qtys)
    game_state.good_quantities = default_qtys
    # A save from before the pins starts with the first goods pinned, as a new game does
    good_names = list(getattr(game_state, "available_goods", []))
    pins = gs.get("pinned_goods", good_names[:TOP_BAR_DEFAULT_PINS])
    game_state.pinned_goods = [g for g in pins if g in good_names]
    # Sync time-tracker fields to restored date so hourly/daily events fire correctly
    game_state.sync_time_trackers()

    p = data["player"]
    player.name = name_of_save(data)   # a save from before names were chosen gets one of its own
    player.hair = hair_key(p.get("hair"))   # a save from before hair colours: the artwork's brown
    player.score = p["score"]
    player.reputation = float(p["reputation"])
    player.tiredness = float(p.get("tiredness", 0.0))   # a save from before tiredness: rested
    player.meal = MealEffect.from_save(p.get("meal"))    # a save from before meals' effects: none
    player.rooms = inn_rooms.from_save(p.get("rooms"))   # a save from before the inns' rooms: none booked
    player.daily_cost_of_living = p["daily_cost_of_living"]
    player.position = tuple(p["position"])
    player.in_market_area = p["in_market_area"]

    d = data["depot"]
    depot.money = d["money"]
    # Saves from before the fee became a share of the trade hold a flat "transaction_cost": they get today's rate
    depot.fee_rate = d.get("fee_rate", MARKET_FEE_RATE)
    depot.storage_capacity = d["storage_capacity"]
    depot.warehouse_count = d["warehouse_count"]
    depot.good_stock = d["good_stock"]
    # Saves from before storage slots have none; Game.restore_owned_buildings settles them
    depot.starting_slots = d.get("starting_slots") or depot.empty_slots(STARTING_STORAGE_SLOTS)
    depot.starting_accepts = d.get("starting_accepts")  # older saves: it takes all goods
    depot.pack_slots = d.get("pack_slots") or depot.empty_slots(PACK_SLOTS)
    # Older saves have no priority list: settle_storage() makes the default one
    depot.storage_order = d.get("storage_order") or []
    depot.properties = {k: list(v) for k, v in d["properties"].items()}
    depot.expenditures = d["expenditures"]
    depot.income = d["income"]
    depot.transaction_expenditures = d["transaction_expenditures"]
    depot.donation_expenditures = d["donation_expenditures"]
    depot.cost_of_living_expenditures = d["cost_of_living_expenditures"]
    depot.license_expenditures = d["license_expenditures"]
    depot.donations = d["donations"]
    depot.labor_income = d.get("labor_income", {})
    # A save from before cost of living had subcategories: all of it counts as base cost
    depot.cost_of_living = d.get("cost_of_living", {})
    depot.wealth = d["wealth"]
    depot.money_history = d["money_history"]
    depot.property_value_history = d.get("property_value_history", [0.0])
    depot.loan_history = d.get("loan_history", [0.0])
    depot.total_stock = d["total_stock"]
    depot.house_history = d["house_history"]
    depot.storage_capacity_history = d.get(
        "storage_capacity_history",
        [depot.storage_capacity] * len(depot.house_history),
    )
    depot.stock_history = d["stock_history"]
    depot.trades = _dt_list(d["trades"], "timestamp")
    depot.expenditure_history = d["expenditure_history"]
    depot.income_history = d["income_history"]
    depot.transaction_expenditure_history = d["transaction_expenditure_history"]
    depot.donation_expenditure_history = d["donation_expenditure_history"]
    depot.cost_of_living_expenditure_history = d["cost_of_living_expenditure_history"]
    depot.license_expenditure_history = d["license_expenditure_history"]
    depot.loan_expenditure_history = d.get("loan_expenditure_history", [0.0])
    depot.overdraft_expenditure_history = d.get("overdraft_expenditure_history", [0.0])
    # Older saves didn't persist miscellaneous history — pad with leading zeros
    # so it aligns with expenditure_history (tail = today).
    misc_hist = d.get("miscellaneous_expenditure_history")
    if misc_hist is None:
        depot.miscellaneous_expenditure_history = [0.0] * len(depot.expenditure_history)
    else:
        depot.miscellaneous_expenditure_history = list(misc_hist)
    depot.miscellaneous_expenditures = d.get("miscellaneous_expenditures", 0.0)
    prop_hist = d.get("property_expenditure_history")
    if prop_hist is None:
        _migrate_property_expenses(depot)
    else:
        depot.property_expenditure_history = list(prop_hist)
        depot.property_expenditures = d.get("property_expenditures", 0.0)
    depot.active_loans = d.get("active_loans", [])
    depot.donation_history = d["donation_history"]
    depot.labor_income_history = d.get("labor_income_history", {})
    depot.cost_of_living_history = d.get("cost_of_living_history", {})
    depot.purchase_history = {
        good_name: _dt_list(list(entries), "timestamp")
        for good_name, entries in d["purchase_history"].items()
    }
    depot.trade_cycles = d["trade_cycles"]
    depot.trade_cycle_records = _dt_list(d["trade_cycle_records"], "timestamp")
    depot.trading_licenses = {
        k: _str_to_dt(v) for k, v in d["trading_licenses"].items()
    }
    depot.stats = Statistics.from_dict(d.get("statistics", {}))
    # Older saves predate the statistics block, or were saved between the
    # trade and the stats increment — never let the counter undercount the
    # trade history that's actually there.
    if depot.stats.ledger_entries < len(depot.trades):
        depot.stats.ledger_entries = len(depot.trades)

    # The economy. Goods added to the game after this save was made get a
    # made-up price history as long as the saved goods' (Simulation.load).
    if sim is not None:
        sim.load(data.get("sim") or _legacy_sim_block(data, sim), now=game_state.date)
    depot.add_missing_goods([g.name for g in goods])

    good_by_name = {g.name: g for g in goods}
    for gd in data["goods"]:
        g = good_by_name.get(gd["name"])
        if g is None:
            continue
        g.show_in_charts = gd["show_in_charts"]
        g.color_current = tuple(gd["color_current"])
        g.color_temp = g.color_current
        g.color = g.color_temp

    # Enforce max-3 chart selection and sync the order list
    _enforce_chart_limit(goods, game_state)


def _legacy_sim_block(data: Dict[str, Any], sim: Any) -> Dict[str, Any]:
    """A ``"sim"`` block of sim_version 1 made from a save of before the simulation core (SAVE_VERSION < 3).

    Those kept the market in ``"goods"`` and the people in ``"population"``.
    Only what the living market still uses is carried over: each good's stock
    (with its normal volume, to keep how scarce it was) and price histories,
    and the people; ``Simulation.load`` then migrates the
    block like any of sim_version 1 (the prices jump to the new model). What
    the save lacks is taken from the freshly started *sim*: the classes' base
    head counts (the map's, never saved), and the random generator (left as it
    is; the block has no ``"rng"``).
    """
    goods_data = data.get("goods", [])
    if data.get("save_version", 1) < 2:
        # Hourly charts: fill in points between the hours, so they run at the price ticks' pace
        for gd in goods_data:
            gd["price_history_hourly"] = _hourly_to_ticks(gd["price_history_hourly"])
    goods = [
        {
            "name": gd["name"],
            "market_quantity": gd["market_quantity"],
            "normal_quantity": gd.get("normal_quantity"),     # missing in older saves still: stock at its target
            "price_history_ticks": list(gd["price_history_hourly"]),
            "price_history_daily": list(gd["price_history_daily"]),
        }
        for gd in goods_data if gd["name"] in sim.state.goods
    ]
    return {
        "sim_version": 1,
        "state": {"goods": goods, "population": _legacy_population(data.get("population"), sim)},
    }


def _legacy_population(pop_data: Optional[Dict[str, Any]], sim: Any) -> Optional[Dict[str, Any]]:
    """The ``"population"`` of a save of before the simulation core, as the sim's state has it."""
    current = sim.state.population
    if current is None:
        return None
    if not pop_data:
        return current.to_dict()
    town = pop_data["town"]
    classes = []
    for c in current.classes.values():
        classes.append({
            "name": c.name,
            "count": int(town["population_groups"].get(c.name, c.count)),
            "base": c.base,
            "happiness": town["happiness_groups"].get(c.name, c.happiness),
            "happiness_history": list(pop_data["happiness_history"].get(c.name, [])),
            "population_history": list(pop_data["population_history"].get(c.name, [])),
        })
    return {
        "classes": classes,
        "max_citizens": current.max_citizens,
        "happiness": town["happiness"],
        "average_happiness_history": list(pop_data["average_happiness_history"]),
        "total_population_history": list(pop_data["total_population_history"]),
    }
