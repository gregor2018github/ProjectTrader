"""The autosave written in the background (save_manager.save_game(..., background=True))."""

import os

import pytest

from src.persistence import save_manager as sm


@pytest.fixture
def saves(tmp_path, monkeypatch):
    """Saves into a folder of the test's own, with a made-up game to serialize."""
    monkeypatch.setattr(sm, "SAVES_PATH", str(tmp_path))
    game = {"save_version": sm.SAVE_VERSION, "history": [0.5 * i for i in range(50_000)],
            "nested": {"a": [1, 2, {"b": "ü"}]}, "pair": (1, 2)}
    monkeypatch.setattr(sm, "_serialize_game", lambda *args, **kwargs: game)
    yield tmp_path, game
    sm.wait_for_save()
    sm.take_save_error()


def _save(slot, background):
    sm.save_game(slot, None, None, None, [], background=background)


def test_background_save_writes_what_a_save_in_place_writes(saves):
    _save(1, background=False)
    _save(2, background=True)
    assert sm.load_game(2) == sm.load_game(1)   # load_game waits for the write


def test_the_game_may_change_while_the_save_is_written(saves):
    tmp_path, game = saves
    _save(sm.AUTOSAVE_SLOT, background=True)
    game["history"].clear()
    game["nested"]["a"].append("later")
    data = sm.load_game(sm.AUTOSAVE_SLOT)
    assert len(data["history"]) == 50_000
    assert data["nested"]["a"] == [1, 2, {"b": "ü"}]
    assert data["pair"] == [1, 2]


def test_nothing_but_the_save_is_left_in_the_folder(saves):
    tmp_path, _ = saves
    _save(sm.AUTOSAVE_SLOT, background=True)
    sm.wait_for_save()
    assert not sm.save_in_progress()
    assert os.listdir(tmp_path) == ["autosave.sav"]
    assert sm.take_save_error() is None


def test_a_failed_background_save_is_reported_once(saves, monkeypatch):
    def broken(slot, data):
        raise OSError("disk full")
    monkeypatch.setattr(sm, "_write_blob", broken)
    _save(sm.AUTOSAVE_SLOT, background=True)
    sm.wait_for_save()
    error = sm.take_save_error()
    assert isinstance(error, OSError) and "disk full" in str(error)
    assert sm.take_save_error() is None


def test_what_marshal_cannot_copy_is_written_in_place(saves, monkeypatch):
    class Odd(float):
        pass
    tmp_path, game = saves
    game["odd"] = Odd(1.5)
    _save(3, background=True)
    assert not sm.save_in_progress()
    assert sm.load_game(3)["odd"] == 1.5
