"""Petting a sheep: a little reputation, but only the first time each game day."""

import datetime
import os
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

from src.config.constants import SHEEP_PET_REPUTATION
from src.models.statistics import Statistics
from src.ui.helper_modules.figurine_click_menu import _pet_sheep

assert SHEEP_PET_REPUTATION == 0.2


class Player:
    x, y, width = 0, 0, 32

    def __init__(self):
        self.reputation = 0.0

    def change_reputation(self, amount):
        self.reputation += amount


@pytest.fixture
def state():
    log = []
    player = Player()
    state = SimpleNamespace(date=datetime.datetime(1500, 3, 1, 10, 0),
                            log_event=lambda category, text: log.append(category), log=log)
    state.game = SimpleNamespace(
        game_map=SimpleNamespace(map_player=player), player=player,
        depot=SimpleNamespace(stats=Statistics()), sheep_sounds=[],
    )
    return state


def pet(state):
    _pet_sheep(state, SimpleNamespace(pet=lambda x: None))


def test_the_first_petting_of_the_day_earns_reputation_and_the_rest_nothing(state):
    pet(state)
    pet(state)
    state.date += datetime.timedelta(hours=10)
    pet(state)
    assert state.game.player.reputation == pytest.approx(SHEEP_PET_REPUTATION)
    assert state.log == ["RANK"]


def test_the_next_day_earns_it_again(state):
    pet(state)
    state.date += datetime.timedelta(days=1)
    pet(state)
    assert state.game.player.reputation == pytest.approx(2 * SHEEP_PET_REPUTATION)


def test_the_day_is_saved():
    stats = Statistics()
    stats.last_sheep_pet_day = "1500-03-01"
    assert Statistics.from_dict(stats.to_dict()).last_sheep_pet_day == "1500-03-01"
    assert Statistics.from_dict({}).last_sheep_pet_day is None
