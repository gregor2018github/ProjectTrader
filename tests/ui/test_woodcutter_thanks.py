"""The woodcutter thanks the player for chopping wood for his father, Osric.

Once a session of woodhacking has been finished, the woodcutter at the wood
market offers "Talk" (and glows for it): his thanks, and three logs to take or
turn down for a little reputation, each answer showing what it brings beside
it. Either way it is over for good; without room for the logs nothing is taken
and he offers them again another time.
"""

import datetime
import json
import os
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from src.models.depot import Depot
from src.models.player import Player
from src.models.figurines.humans.npcs.trader_woodcutter import TraderWoodcutter
from src.models.statistics import Statistics
from src.models.thanks import THANKS
from src.ui.helper_modules.figurine_bubbles import FigurineConversation
from src.ui.helper_modules.figurine_talks import open_thanks, waiting_thanks
from src.ui.transaction_feedback import GoodsPopup

TODAY = datetime.datetime(1500, 1, 4, 10)
THANKS_FOR_FATHER = THANKS["woodcutter_father"]
VIEW = pygame.Rect(0, 0, 1810, 960)


@pytest.fixture
def son():
    pygame.init()
    pygame.display.set_mode((1920, 1080))
    npc = TraderWoodcutter(400.0, 400.0, 32)
    npc.opacity = 1.0
    return npc


@pytest.fixture
def state(son):
    camera = SimpleNamespace(zoom=1.0, apply=lambda x, y: (x, y))
    player = SimpleNamespace(x=390.0, y=380.0, width=32, height=54)
    depot = Depot(money=100, fee_rate=0.02, storage_capacity=100, goods=("Wood", "Stone"))
    warnings, events = [], []
    state = SimpleNamespace(date=TODAY, screen=pygame.display.get_surface(), font=pygame.font.Font(None, 20),
                            info_window=None, active_house_menu=None, is_map_visible=True,
                            menu_fade_window=None, menu_fade_timer=0, menu_fade_duration=0.2,
                            warnings=warnings, events=events, coin_popups=[],
                            show_warning=warnings.append, log_event=lambda c, t: events.append((c, t)))
    state.game = SimpleNamespace(depot=depot, player=Player(name="Tester", cost_of_living=0),
                                 game_map=SimpleNamespace(camera=camera, map_player=player,
                                                          tmx_map=SimpleNamespace(npcs=[son])))
    return state


def chopped(state):
    state.game.depot.stats.record_woodhacking(12.0, TODAY.date().isoformat(), 3, 1, 4)


def answer(state, label):
    window = state.info_window
    row = next(rect for rect, text in window.answer_rows if text == label)
    window.handle_click(row.center)


def test_his_gift_is_a_good_of_the_game_and_every_answer_leads_somewhere():
    with open(os.path.join("assets", "data", "goods.json"), encoding="utf-8") as f:
        goods = {good["name"] for good in json.load(f)["goods"]}
    assert set(THANKS_FOR_FATHER.gift) <= goods
    for thanks in THANKS.values():
        answers = [a for page in thanks.pages.values() for a in page.answers]
        assert thanks.first in thanks.pages
        assert all(a.next is None or a.next in thanks.pages for a in answers)
        assert any(a.accepts for a in answers) and any(a.declines for a in answers)


def test_he_has_nothing_to_say_till_the_player_has_chopped_for_his_father(state, son):
    assert waiting_thanks(state, son) is None
    chopped(state)
    assert waiting_thanks(state, son) is THANKS_FOR_FATHER


def test_only_the_woodcutter_thanks_for_it(state):
    chopped(state)
    assert waiting_thanks(state, SimpleNamespace(TILED_PREFIX="Butcher")) is None


def test_accepting_puts_three_logs_in_the_storage_and_ends_it(state, son):
    chopped(state)
    open_thanks(state, son, THANKS_FOR_FATHER, THANKS_FOR_FATHER.first, VIEW)
    assert isinstance(state.info_window, FigurineConversation)
    answer(state, "Accept his gift")
    depot = state.game.depot
    assert depot.good_stock["Wood"] == 3 and depot.money == 100
    assert state.events and state.events[0][0] == "TRADE"
    assert [type(p) for p in state.coin_popups] == [GoodsPopup]   # "+3" and the wood, rising
    assert isinstance(state.info_window, FigurineConversation)      # his last words
    answer(state, "Farewell")
    assert state.info_window is None
    assert waiting_thanks(state, son) is None


def test_no_thanks_needed_takes_nothing_and_ends_it(state, son):
    chopped(state)
    open_thanks(state, son, THANKS_FOR_FATHER, THANKS_FOR_FATHER.first, VIEW)
    answer(state, "No thanks needed!")
    assert state.game.depot.good_stock["Wood"] == 0
    assert state.game.player.reputation == THANKS_FOR_FATHER.reputation > 0
    assert state.coin_popups == []
    assert waiting_thanks(state, son) is None


def test_accepting_earns_no_reputation(state, son):
    chopped(state)
    open_thanks(state, son, THANKS_FOR_FATHER, THANKS_FOR_FATHER.first, VIEW)
    answer(state, "Accept his gift")
    assert state.game.player.reputation == 0


def test_each_answer_shows_what_it_brings_beside_it(state, son):
    chopped(state)
    open_thanks(state, son, THANKS_FOR_FATHER, THANKS_FOR_FATHER.first, VIEW)
    window = state.info_window
    assert [amount for amount, _ in window.badges["Accept his gift"]] == ["+3"]
    assert [amount for amount, _ in window.badges["No thanks needed!"]] == ["+1"]
    for row, label in window.answer_rows:        # the badges fit in their rows, inside the bubble
        assert window._answer_width(label) <= row.width and window.rect.contains(row)
    window.draw()
    answer(state, "No thanks needed!")
    assert state.info_window.badges == {}       # his last words bring nothing more


def test_without_room_for_the_logs_nothing_is_taken_and_he_asks_again(state, son):
    chopped(state)
    depot = state.game.depot
    full = [{"good": "Stone", "qty": 20} for _ in depot.starting_slots]
    depot.starting_slots[:] = full
    depot.pack_slots[:] = [{"good": "Stone", "qty": 1} for _ in depot.pack_slots]
    open_thanks(state, son, THANKS_FOR_FATHER, THANKS_FOR_FATHER.first, VIEW)
    answer(state, "Accept his gift")
    assert state.warnings and depot.good_stock["Wood"] == 0 and state.coin_popups == []
    assert state.info_window is None
    assert waiting_thanks(state, son) is THANKS_FOR_FATHER


def test_it_is_saved_once_over():
    stats = Statistics()
    stats.talks_done.append("woodcutter_father")
    assert Statistics.from_dict(stats.to_dict()).talks_done == ["woodcutter_father"]
    assert Statistics.from_dict({}).talks_done == []
