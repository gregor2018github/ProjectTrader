"""The fishing is once a day: opening it uses the day up, however the session then ends."""

import datetime
import os
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from src.models.minigames.fishing import FishingMinigame
from src.models.statistics import Statistics
from src.ui.helper_modules.water_click_menu import fishing_available, open_fishing

TODAY = datetime.datetime(1500, 1, 4, 10)


@pytest.fixture
def state():
    pygame.init()
    screen = pygame.display.set_mode((1920, 1080))
    warnings = []
    state = SimpleNamespace(date=TODAY, screen=screen, coin_popups=[], log_event=lambda *a: None,
                            time_level=3, previous_time_level=None, minigame=None,
                            info_window=object(), active_house_menu=object(),
                            warnings=warnings, show_warning=warnings.append)
    depot = SimpleNamespace(stats=Statistics(), book_labor_income=lambda *a: None)
    state.game = SimpleNamespace(state=state, sounds={}, weather=SimpleNamespace(), depot=depot)
    return state


def test_a_day_not_fished_yet_is_available(state):
    assert fishing_available(state)
    state.game.depot.stats.last_fishing_day = "1500-01-03"
    assert fishing_available(state)


def test_opening_starts_the_session_paused_and_uses_the_day_up(state):
    assert open_fishing(state)
    assert isinstance(state.minigame, FishingMinigame)
    assert state.game.depot.stats.last_fishing_day == TODAY.date().isoformat()
    assert not fishing_available(state)
    assert (state.time_level, state.previous_time_level) == (1, 3)
    assert state.info_window is None and state.active_house_menu is None
    assert state.warnings == []


def test_a_second_try_the_same_day_only_warns(state):
    state.game.depot.stats.last_fishing_day = TODAY.date().isoformat()
    assert not open_fishing(state)
    assert state.minigame is None
    assert state.time_level == 3
    assert state.info_window is None and state.active_house_menu is None
    assert len(state.warnings) == 1 and "tomorrow" in state.warnings[0]


def test_leaving_early_still_uses_the_day_up(state):
    open_fishing(state)
    state.minigame._leave()
    state.date = TODAY.replace(hour=20)
    assert not fishing_available(state)
    state.date = TODAY + datetime.timedelta(days=1)
    assert fishing_available(state)
