"""The woodhacking is introduced by the old woodcutter by the wood shed.

Until he has asked the player for a hand the stump is not to be used and he
glows instead of it; his talk is pages of a speech bubble with answers, agreeing
introduces the woodhacking and "Hand me the axe" starts it; afterwards he offers
"Lend a Hand", or says the day's chopping is done. Saves from before that, of a
player who has chopped wood, count it as introduced.
"""

import datetime
import os
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from src.models.figurines.humans.npcs.homebody import Homebody
from src.models.introductions import INTRODUCTIONS, WOODHACKING
from src.models.statistics import Statistics
from src.ui.helper_modules import figurine_talks as talks_module
from src.ui.helper_modules.figurine_bubbles import FigurineConversation, FigurineSpeech
from src.ui.helper_modules.figurine_talks import lend_a_hand, open_introduction
from src.ui.helper_modules.house_click_menu import minigame_host, minigame_introduced

TODAY = datetime.datetime(1500, 1, 4, 10)
PROFILE = {"name": "Testric", "home": "Shed", "stand_in": "trader_woodcutter", "introduces": WOODHACKING}


@pytest.fixture
def host():
    pygame.init()
    pygame.display.set_mode((1920, 1080))
    npc = Homebody("commons_testric", PROFILE, 32)
    npc.opacity = 1.0
    npc.place_feet(400.0, 400.0)
    return npc


@pytest.fixture
def state(host):
    camera = SimpleNamespace(zoom=1.0, apply=lambda x, y: (x, y))
    player = SimpleNamespace(x=390.0, y=380.0, width=32, height=54)
    stats = Statistics()
    state = SimpleNamespace(date=TODAY, screen=pygame.display.get_surface(), font=pygame.font.Font(None, 20),
                            info_window=None, active_house_menu=None, is_map_visible=True,
                            menu_fade_window=None, menu_fade_timer=0, menu_fade_duration=0.2)
    state.game = SimpleNamespace(depot=SimpleNamespace(stats=stats),
                                 game_map=SimpleNamespace(camera=camera, map_player=player,
                                                          tmx_map=SimpleNamespace(npcs=[host])))
    return state


@pytest.fixture
def opened(monkeypatch):
    """The woodhacking's opener, recording instead of starting the minigame."""
    started = []
    monkeypatch.setitem(talks_module.MINIGAME_OPENERS, WOODHACKING,
                        (lambda gs: started.append(gs) or True,
                         lambda gs: gs.game.depot.stats.last_woodhacking_day != gs.date.date().isoformat()))
    return started


def answer(state, label):
    window = state.info_window
    row = next(rect for rect, text in window.answer_rows if text == label)
    window.handle_click(row.center)


def test_every_answer_leads_somewhere_and_one_agrees_and_starts():
    for introduction in INTRODUCTIONS.values():
        answers = [a for page in introduction.pages.values() for a in page.answers]
        assert introduction.first in introduction.pages
        assert all(a.next is None or a.next in introduction.pages for a in answers)
        assert any(a.agrees for a in answers) and any(a.starts for a in answers)


def test_until_he_has_asked_the_woodhacking_is_not_introduced(state, host):
    assert minigame_host(state, WOODHACKING) is host
    assert not minigame_introduced(state, WOODHACKING)
    state.game.depot.stats.minigames_introduced.append(WOODHACKING)
    assert minigame_introduced(state, WOODHACKING)


def test_with_nobody_on_the_map_to_introduce_it_it_is_open(state):
    state.game.game_map.tmx_map.npcs = []
    assert minigame_introduced(state, WOODHACKING)


def test_agreeing_introduces_it_and_the_axe_starts_it(state, host, opened):
    open_introduction(state, host, INTRODUCTIONS[WOODHACKING].first, pygame.Rect(0, 0, 1810, 960))
    assert isinstance(state.info_window, FigurineConversation)
    assert host.talking_to is state.game.game_map.map_player
    answer(state, "Go on")
    answer(state, "I'll lend a hand")
    assert WOODHACKING in state.game.depot.stats.minigames_introduced
    assert opened == []
    answer(state, "Hand me the axe")
    assert opened == [state]


def test_not_now_leaves_it_unintroduced(state, host, opened):
    open_introduction(state, host, "ask", pygame.Rect(0, 0, 1810, 960))
    answer(state, "Not now")
    answer(state, "Farewell")
    assert state.info_window is None and opened == []
    assert WOODHACKING not in state.game.depot.stats.minigames_introduced


def test_once_chopped_today_he_says_so_instead(state, host, opened):
    state.game.depot.stats.last_woodhacking_day = TODAY.date().isoformat()
    lend_a_hand(state, host, pygame.Rect(0, 0, 1810, 960))
    assert opened == []
    assert isinstance(state.info_window, FigurineSpeech)
    assert not isinstance(state.info_window, FigurineConversation)


def test_the_answers_sit_under_the_line_inside_the_bubble(state, host):
    open_introduction(state, host, "ask", pygame.Rect(0, 0, 1810, 960))
    window = state.info_window
    rows = [rect for rect, _ in window.answer_rows]
    assert len(rows) == 2 and rows[0].bottom <= rows[1].top
    assert all(window.rect.contains(row) for row in rows)
    window.draw()


def test_saves_from_before_count_a_player_who_has_chopped_as_introduced():
    assert WOODHACKING in Statistics.from_dict({"last_woodhacking_day": "1500-01-01"}).minigames_introduced
    assert WOODHACKING not in Statistics.from_dict({}).minigames_introduced
    assert Statistics.from_dict({"last_woodhacking_day": "1500-01-01",
                                 "minigames_introduced": []}).minigames_introduced == []
    stats = Statistics()
    stats.minigames_introduced.append(WOODHACKING)
    assert Statistics.from_dict(stats.to_dict()).minigames_introduced == [WOODHACKING]
