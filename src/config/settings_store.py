"""Persistent user settings stored in a JSON file next to the saves directory."""

import json
import os
from typing import Any, Dict, Optional

from .constants import MAIN_PATH, MAX_FRAMES_PER_SEC

_SETTINGS_PATH = os.path.join(MAIN_PATH, "settings.json")
_cache: Optional[Dict[str, Any]] = None   # the file's contents, see _load_raw

_DEFAULTS: Dict[str, Any] = {
    "show_map_debug": True,
    "resolution": "1760x1064",
    "autosave_enabled": True,
    "autosave_minutes": 5,
    "fps_limit": MAX_FRAMES_PER_SEC,
}

# Autosave intervals (minutes of play time) selectable in the settings UI.
AUTOSAVE_MINUTE_OPTIONS = [1, 2, 3, 5, 10, 15, 20, 30]

# FPS limits selectable in the settings UI; 0 is no limit.
FPS_OPTIONS = [30, 60, 75, 100, 120, 144, 165, 240, 0]


def fps_label(fps: int) -> str:
    return "Unlimited" if fps == 0 else f"{fps} FPS"


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
    """The settings as stored, read from disk only the first time.

    Every write goes through _save_raw, which keeps this copy in step; some
    settings are asked for every frame, and reading the file each time can
    stall a frame on a slow disk or under a virus scanner.
    """
    global _cache
    if _cache is None:
        _cache = {}
        try:
            with open(_SETTINGS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                _cache = data
        except Exception:
            pass
    return _cache


def _save_raw(data: Dict[str, Any]) -> None:
    global _cache
    _cache = dict(data)
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
    raw = dict(_load_raw())
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
