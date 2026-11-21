"""The quest for Flip in the UI (lost_sheep_talks.py): the shepherdess's talks and coaxing Flip.

At the fold she offers "Talk" while she has something to say: lying costs 3
reputation and owning up half a point, each shown in red beside its answer;
she gives her bread once the player has found Flip won't come without it;
coaxing him without bread has the player say so, with it uses one Bread and
puts him on the leash, after which the buildings are closed to the player; her
thanks gives her wool or, turned down, reputation, and is over.
"""

import datetime
import os
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from src.models import lost_sheep as ls
from src.models.depot import Depot
from src.models.figurines.animals.sheep import Sheep
from src.models.figurines.humans.npcs.trader import WALKING_TO_WORK, WORKING
from src.models.figurines.humans.npcs.trader_shepherdess import TraderShepherdess
from src.models.lost_sheep import LostSheep
from src.models.player import Player
from src.ui.helper_modules import lost_sheep_talks as talks
from src.ui.helper_modules.figurine_bubbles import BADGE_LOSS_COLOR, FigurineConversation, FigurineSpeech
from src.ui.helper_modules.figurine_click_menu import show_figurine_menu

TODAY = datetime.datetime(1500, 1, 5, 10)
VIEW = pygame.Rect(0, 0, 1810, 960)


@pytest.fixture
def world():
    pygame.init()
    pygame.display.set_mode((1920, 1080))
    her = TraderShepherdess(400.0, 400.0, 32)
    her.opacity, her.at_fold, her.state = 1.0, True, WORKING
    flip = Sheep(380.0, 380.0, 200, 32, 32, "dark", ls.FLIP)
    quest = LostSheep()
    quest.load({"stage": ls.ESCAPED, "missed_on": TODAY.date().isoformat()})
    leashed = []
    on_map = SimpleNamespace(ready=True, shepherdess=her, flip=flip, quest=quest,
                             sync=lambda feet: None, put_on_leash=lambda feet: (flip.lead(), leashed.append(feet)))
    camera = SimpleNamespace(zoom=1.0, apply=lambda x, y: (x, y))
    player = SimpleNamespace(x=390.0, y=380.0, width=32, height=54, feet=(406.0, 434.0),
                             display_name="You", sprite_draw_offset=(0, 0), is_hidden=False,
                             collision_rect=pygame.Rect(390, 420, 32, 14), y_sort=434.0,
                             _get_scaled_sprite=lambda zoom: pygame.Surface((32, 54)))
    depot = Depot(money=100, fee_rate=0.02, storage_capacity=100, goods=("Bread", "Wool", "Wood"))
    warnings, events = [], []
    state = SimpleNamespace(date=TODAY, screen=pygame.display.get_surface(), font=pygame.font.Font(None, 20),
                            info_window=None, active_house_menu=None, is_map_visible=True,
                            menu_fade_window=None, menu_fade_timer=0, menu_fade_duration=0.2,
                            left_side_mode="map", right_side_mode="map",
                            warnings=warnings, events=events, coin_popups=[],
                            show_warning=warnings.append, log_event=lambda c, t: events.append((c, t)))
    state.game = SimpleNamespace(depot=depot, play_sound=lambda name: None, sheep_sounds=[],
                                 player=Player(name="Tester", cost_of_living=0),
                                 lost_sheep=quest, lost_sheep_map=on_map,
                                 game_map=SimpleNamespace(camera=camera, map_player=player,
                                                          tmx_map=SimpleNamespace(npcs=[her], sheep=[flip])))
    return SimpleNamespace(state=state, her=her, flip=flip, quest=quest, depot=depot, leashed=leashed)


def talk(world):
    first = talks.shepherdess_talk(world.state, world.her)
    talks.open_shepherdess_talk(world.state, world.her, first, VIEW)
    return world.state.info_window


def test_she_has_news_at_the_fold_only(world):
    assert talks.has_news(world.state, world.her)
    world.her.at_fold = False
    assert talks.shepherdess_talk(world.state, world.her) is None


def test_her_marker_waits_till_she_is_on_her_round_in_the_fold(world):
    world.her.state = WALKING_TO_WORK
    assert not talks.has_news(world.state, world.her)
    assert talks.shepherdess_talk(world.state, world.her) == ls.MISSING     # she can still be spoken to
    world.her.state = WORKING
    assert talks.has_news(world.state, world.her)


def test_lying_costs_three_shown_in_red(world):
    bubble = talk(world)
    assert isinstance(bubble, FigurineConversation)
    lie, confess = bubble.answers
    assert bubble.badges[lie][0][0] == "-3" and bubble.badges[confess][0][0] == "-0.5"
    bubble.on_answer(lie)
    assert world.state.game.player.reputation == pytest.approx(-3.0)
    assert world.quest.stage == ls.SEARCHING
    assert world.state.coin_popups                         # "-3" rising from the player's head
    # She saw through it: the farmer's page follows, then her request
    assert "farmer saw you" in ls.PAGES["lie"].text
    assert world.state.info_window.answers == ["I'm sorry"]


def test_owning_up_costs_half_a_point(world):
    talk(world).on_answer("It might have been me...")
    assert world.state.game.player.reputation == pytest.approx(-0.5)
    assert world.quest.confessed is True


def test_without_bread_the_player_says_so_and_she_gives_hers_once(world):
    talk(world).on_answer("It might have been me...")
    world.flip.x = 420.0                                     # right of the player, room to his right
    talks.coax_flip(world.state, world.flip, VIEW)
    assert isinstance(world.state.info_window, FigurineSpeech)
    assert world.state.info_window.figurine is world.state.game.game_map.map_player
    assert world.quest.needs_bread and not world.flip.leashed
    # No heart for an empty hand: he turns his back and walks off along his strip
    assert world.flip.heart_age is None
    assert world.flip.direction == "right" and world.flip.walk_target is not None
    assert world.flip.walk_target[0] > world.flip.feet[0]
    bubble = talk(world)
    assert bubble.answers == ["Take the bread"] and bubble.badges["Take the bread"][0][0] == "+1"
    bubble.on_answer("Take the bread")
    assert world.depot.good_stock["Bread"] == 1 and world.quest.bread_given
    assert not talks.has_news(world.state, world.her)        # she has nothing new to say now


def test_with_no_room_to_back_away_he_only_turns_his_back(world):
    world.flip.x = world.flip.zone_right                      # at the end of his strip, the player left of him
    world.flip.shy_away(world.flip.zone_right - 100.0)
    assert world.flip.walk_target is None and not world.flip.is_moving
    assert world.flip.direction == "right" and world.flip.heart_age is None


def test_with_bread_he_follows_and_the_buildings_wait(world):
    talk(world).on_answer("It might have been me...")
    world.depot.receive_goods("Bread", 2, TODAY)
    assert talks.can_coax(world.state, world.flip)
    talks.coax_flip(world.state, world.flip, VIEW)
    assert world.quest.leading and world.flip.leashed and world.leashed
    assert world.flip.heart_age == 0.0                      # the bread wins him over
    assert world.depot.good_stock["Bread"] == 1
    assert talks.blocks_buildings(world.state)
    assert not talks.can_coax(world.state, world.flip)


def test_flips_menu_offers_to_coax_him_only_while_he_is_to_be_found(world):
    world.state.game.game_map.map_player.x, world.state.game.game_map.map_player.y = 380.0, 380.0
    assert show_figurine_menu(world.state, world.flip, VIEW)
    assert talks.COAX_OPTION not in world.state.info_window.options
    world.quest.answer_missing(confess=True)
    show_figurine_menu(world.state, world.flip, VIEW)
    assert talks.COAX_OPTION in world.state.info_window.options
    show_figurine_menu(world.state, world.her, VIEW)
    assert world.state.info_window.options[0] == talks.TALK_OPTION


@pytest.mark.parametrize("answer, wool, reputation", [
    ("Accept the wool", 2, 0.0),
    ("Keep it, it was my doing", 0, 1.0),
])
def test_her_thanks_gives_wool_or_reputation_and_ends_it(world, answer, wool, reputation):
    world.quest.load({"stage": ls.RETURNED, "missed_on": TODAY.date().isoformat()})
    bubble = talk(world)
    bubble.on_answer(answer)
    assert world.depot.good_stock.get("Wool", 0) == wool
    assert world.state.game.player.reputation == pytest.approx(reputation)
    assert world.quest.stage == ls.DONE and world.quest.done_on == TODAY.date()


def test_without_room_for_her_wool_the_thanks_waits(world, monkeypatch):
    world.quest.load({"stage": ls.RETURNED, "missed_on": TODAY.date().isoformat()})
    monkeypatch.setattr(world.depot, "room_to_receive", lambda name: 0)
    talk(world).on_answer("Accept the wool")
    assert world.state.warnings and world.quest.stage == ls.RETURNED


def test_a_loss_badge_is_red():
    assert BADGE_LOSS_COLOR[0] > BADGE_LOSS_COLOR[1]
