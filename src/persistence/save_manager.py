"""Save/load system for ProjectTrader.

Save files are binary: first 32 bytes are the HMAC-SHA256 digest of the
remaining bytes, which are gzip-compressed JSON.  Tampering with the data
invalidates the digest and causes the load to be rejected.
"""

import datetime
import gzip
import hashlib
import hmac
import json
import os
from typing import Any, Dict, List, Optional

from ..config.constants import SAVES_PATH, SAVE_SECRET_KEY

SAVE_VERSION = 1
NUM_SLOTS = 3


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _slot_path(slot: int) -> str:
    return os.path.join(SAVES_PATH, f"slot_{slot}.sav")


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


def _pack(data: Dict[str, Any]) -> bytes:
    json_bytes = json.dumps(data, ensure_ascii=False).encode("utf-8")
    compressed = gzip.compress(json_bytes)
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

def _serialize_game(game_state: Any, player: Any, depot: Any, goods: List[Any], save_name: str = "", population_manager: Any = None) -> Dict[str, Any]:
    return {
        "save_version": SAVE_VERSION,
        "saved_at": _dt_to_str(datetime.datetime.now()),
        "save_name": save_name,
        "game_state": {
            "date": _dt_to_str(game_state.date),
            "time_level": game_state.time_level,
            "left_side_mode": game_state.left_side_mode,
            "right_side_mode": game_state.right_side_mode,
            "input_fields": dict(game_state.input_fields),
            "depot_time_frame": game_state.depot_time_frame,
        },
        "player": {
            "name": player.name,
            "score": player.score,
            "reputation": player.reputation,
            "daily_cost_of_living": player.daily_cost_of_living,
            "position": list(player.position),
            "in_market_area": player.in_market_area,
        },
        "depot": {
            "money": depot.money,
            "transaction_cost": depot.transaction_cost,
            "storage_capacity": depot.storage_capacity,
            "warehouse_count": depot.warehouse_count,
            "good_stock": dict(depot.good_stock),
            "properties": {k: list(v) for k, v in depot.properties.items()},
            "expenditures": depot.expenditures,
            "income": depot.income,
            "transaction_expenditures": depot.transaction_expenditures,
            "donation_expenditures": depot.donation_expenditures,
            "cost_of_living_expenditures": depot.cost_of_living_expenditures,
            "license_expenditures": depot.license_expenditures,
            "donations": dict(depot.donations),
            "wealth": list(depot.wealth),
            "money_history": list(depot.money_history),
            "property_value_history": list(depot.property_value_history),
            "loan_history": list(depot.loan_history),
            "total_stock": list(depot.total_stock),
            "house_history": list(depot.house_history),
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
            "donation_history": {k: list(v) for k, v in depot.donation_history.items()},
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
        },
        "goods": [
            {
                "name": g.name,
                "price": g.price,
                "market_quantity": g.market_quantity,
                "price_history_daily": list(g.price_history_daily),
                "price_history_hourly": list(g.price_history_hourly),
                "show_in_charts": g.show_in_charts,
                "color_current": list(g.color_current),
            }
            for g in goods
        ],
        "population": _serialize_population(population_manager),
    }


def _serialize_population(pm: Any) -> Optional[Dict[str, Any]]:
    """Return a serializable dict for the population manager, or None if absent."""
    if pm is None:
        return None
    return {
        "happiness_history":         {k: list(v) for k, v in pm.happiness_history.items()},
        "average_happiness_history": list(pm.average_happiness_history),
        "population_history":        {k: list(v) for k, v in pm.population_history.items()},
        "total_population_history":  list(pm.total_population_history),
        "town": {
            "citizens":          pm.town.citizens,
            "happiness":         pm.town.happiness,
            "population_groups": dict(pm.town.population_groups),
            "happiness_groups":  dict(pm.town.happiness_groups),
        },
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def save_game(slot: int, game_state: Any, player: Any, depot: Any, goods: List[Any], save_name: str = "", population_manager: Any = None) -> None:
    """Serialize the full game state and write it to the given slot file (1-based)."""
    os.makedirs(SAVES_PATH, exist_ok=True)
    data = _serialize_game(game_state, player, depot, goods, save_name, population_manager)
    blob = _pack(data)
    with open(_slot_path(slot), "wb") as f:
        f.write(blob)


def load_game(slot: int) -> Dict[str, Any]:
    """Load and verify a save file. Returns the raw deserialized dict.

    Raises:
        FileNotFoundError: if the slot file does not exist.
        ValueError: if the file is tampered with or corrupted.
    """
    path = _slot_path(slot)
    if not os.path.exists(path):
        raise FileNotFoundError(f"No save in slot {slot}.")
    with open(path, "rb") as f:
        blob = f.read()
    return _unpack(blob)


def get_save_slots() -> List[Optional[Dict[str, Any]]]:
    """Return a list of NUM_SLOTS slot-info dicts (or None for empty/corrupted slots).

    Each non-None entry contains: slot (int), saved_at (str), game_date (str), money (float).
    """
    result: List[Optional[Dict[str, Any]]] = []
    for slot in range(1, NUM_SLOTS + 1):
        path = _slot_path(slot)
        if not os.path.exists(path):
            result.append(None)
            continue
        try:
            with open(path, "rb") as f:
                blob = f.read()
            data = _unpack(blob)
            result.append({
                "slot": slot,
                "saved_at": data["saved_at"],
                "game_date": data["game_state"]["date"],
                "money": data["depot"]["money"],
                "save_name": data.get("save_name", ""),
            })
        except Exception:
            result.append(None)
    return result


def delete_save(slot: int) -> None:
    """Delete the save file for the given slot, if it exists."""
    path = _slot_path(slot)
    if os.path.exists(path):
        os.remove(path)


def apply_save_data(data: Dict[str, Any], game_state: Any, player: Any, depot: Any, goods: List[Any], population_manager: Any = None) -> None:
    """Apply a loaded save dict to the live game objects in-place."""
    gs = data["game_state"]
    game_state.date = _str_to_dt(gs["date"])
    game_state.time_level = gs["time_level"]
    game_state.previous_time_level = gs["time_level"]
    game_state.left_side_mode = gs["left_side_mode"]
    game_state.right_side_mode = gs["right_side_mode"]
    game_state.input_fields = gs["input_fields"]
    game_state.depot_time_frame = gs["depot_time_frame"]
    # Sync time-tracker fields to restored date so hourly/daily events fire correctly
    game_state.last_minute = game_state.date.minute
    game_state.last_hour = game_state.date.hour
    game_state.last_day = game_state.date.day
    game_state.last_week = game_state.date.isocalendar()[1]
    game_state.last_month = game_state.date.month
    game_state.last_year = game_state.date.year

    p = data["player"]
    player.name = p["name"]
    player.score = p["score"]
    player.reputation = p["reputation"]
    player.daily_cost_of_living = p["daily_cost_of_living"]
    player.position = tuple(p["position"])
    player.in_market_area = p["in_market_area"]

    d = data["depot"]
    depot.money = d["money"]
    depot.transaction_cost = d["transaction_cost"]
    depot.storage_capacity = d["storage_capacity"]
    depot.warehouse_count = d["warehouse_count"]
    depot.good_stock = d["good_stock"]
    depot.properties = {k: list(v) for k, v in d["properties"].items()}
    depot.expenditures = d["expenditures"]
    depot.income = d["income"]
    depot.transaction_expenditures = d["transaction_expenditures"]
    depot.donation_expenditures = d["donation_expenditures"]
    depot.cost_of_living_expenditures = d["cost_of_living_expenditures"]
    depot.license_expenditures = d["license_expenditures"]
    depot.donations = d["donations"]
    depot.wealth = d["wealth"]
    depot.money_history = d["money_history"]
    depot.property_value_history = d.get("property_value_history", [0.0])
    depot.loan_history = d.get("loan_history", [0.0])
    depot.total_stock = d["total_stock"]
    depot.house_history = d["house_history"]
    depot.stock_history = d["stock_history"]
    depot.trades = _dt_list(d["trades"], "timestamp")
    depot.expenditure_history = d["expenditure_history"]
    depot.income_history = d["income_history"]
    depot.transaction_expenditure_history = d["transaction_expenditure_history"]
    depot.donation_expenditure_history = d["donation_expenditure_history"]
    depot.cost_of_living_expenditure_history = d["cost_of_living_expenditure_history"]
    depot.license_expenditure_history = d["license_expenditure_history"]
    depot.donation_history = d["donation_history"]
    depot.purchase_history = {
        good_name: _dt_list(list(entries), "timestamp")
        for good_name, entries in d["purchase_history"].items()
    }
    depot.trade_cycles = d["trade_cycles"]
    depot.trade_cycle_records = _dt_list(d["trade_cycle_records"], "timestamp")
    depot.trading_licenses = {
        k: _str_to_dt(v) for k, v in d["trading_licenses"].items()
    }

    good_by_name = {g.name: g for g in goods}
    for gd in data["goods"]:
        g = good_by_name.get(gd["name"])
        if g is None:
            continue
        g.price = gd["price"]
        g.market_quantity = gd["market_quantity"]
        g.price_history_daily = gd["price_history_daily"]
        g.price_history_hourly = gd["price_history_hourly"]
        g.show_in_charts = gd["show_in_charts"]
        g.color_current = tuple(gd["color_current"])
        g.color_temp = g.color_current
        g.color = g.color_temp

    pop_data = data.get("population")
    if pop_data and population_manager is not None:
        population_manager.happiness_history         = {k: list(v) for k, v in pop_data["happiness_history"].items()}
        population_manager.average_happiness_history = list(pop_data["average_happiness_history"])
        population_manager.population_history        = {k: list(v) for k, v in pop_data["population_history"].items()}
        population_manager.total_population_history  = list(pop_data["total_population_history"])
        td = pop_data["town"]
        population_manager.town.citizens          = td["citizens"]
        population_manager.town.happiness         = td["happiness"]
        population_manager.town.population_groups = dict(td["population_groups"])
        population_manager.town.happiness_groups  = dict(td["happiness_groups"])
