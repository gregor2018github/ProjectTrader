"""The settings: a window size saved before the frame became 16:9 is mapped to the new presets."""

import pytest

from src.config import settings_store
from src.config.constants import SCREEN_WIDTH, SCREEN_HEIGHT, SIDEBAR_WIDTH


@pytest.fixture
def stored(monkeypatch):
    """Settings held in memory only, never read from or written to settings.json."""
    data = {}
    monkeypatch.setattr(settings_store, "_cache", data)
    monkeypatch.setattr(settings_store, "_save_raw", lambda new: (data.clear(), data.update(new)))
    return data


def test_the_frame_is_16_by_9():
    assert (SCREEN_WIDTH + SIDEBAR_WIDTH) * 9 == SCREEN_HEIGHT * 16


def test_every_windowed_preset_is_16_by_9():
    for preset in settings_store.RESOLUTION_PRESETS:
        if preset != "Fullscreen":
            w, h = (int(x) for x in preset.split("x"))
            assert w * 9 == h * 16, preset


@pytest.mark.parametrize("old, new", [
    ("1760x1064", "1920x1080"), ("1540x931", "1600x900"),
    ("1320x798", "1440x810"), ("1100x665", "1280x720"),
])
def test_an_old_window_size_becomes_the_preset_in_its_place(stored, old, new):
    stored["resolution"] = old
    assert settings_store.get("resolution") == new
    assert settings_store.get_all()["resolution"] == new


def test_a_current_preset_and_fullscreen_are_kept(stored):
    for preset in settings_store.RESOLUTION_PRESETS:
        stored["resolution"] = preset
        assert settings_store.get("resolution") == preset


def test_an_unknown_size_falls_back_to_the_default(stored):
    stored["resolution"] = "800x600"
    assert settings_store.get("resolution") == "1920x1080"
