"""Persistent user settings stored in a JSON file next to the saves directory."""

import json
import os
from typing import Any, Dict

from .constants import MAIN_PATH

_SETTINGS_PATH = os.path.join(MAIN_PATH, "settings.json")

_DEFAULTS: Dict[str, Any] = {
    "show_map_debug": True,
    "resolution": "1760x1064",
}

# Ordered list of windowed resolution presets shown in the settings UI.
# "Fullscreen" is always appended as the final option.
RESOLUTION_PRESETS = [
    "1760x1064",
    "1540x931",
    "1320x798",
    "1100x665",
    "Fullscreen",
]


def _load_raw() -> Dict[str, Any]:
    try:
        with open(_SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def _save_raw(data: Dict[str, Any]) -> None:
    try:
        with open(_SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def get(key: str) -> Any:
    """Return the current value for *key*, falling back to the default."""
    raw = _load_raw()
    return raw.get(key, _DEFAULTS.get(key))


def set(key: str, value: Any) -> None:
    """Persist *key* = *value* to disk immediately."""
    raw = _load_raw()
    raw[key] = value
    _save_raw(raw)


def get_all() -> Dict[str, Any]:
    """Return all settings merged with defaults."""
    merged = dict(_DEFAULTS)
    merged.update(_load_raw())
    return merged


def save_all(data: Dict[str, Any]) -> None:
    """Persist the full settings dict to disk."""
    _save_raw(data)
