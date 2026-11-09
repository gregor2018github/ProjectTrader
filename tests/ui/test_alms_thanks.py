"""A coin for one of the poor: the coin's feedback, and their thanks in the speech bubble."""

import os
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from src.config.constants import ALMS_CATEGORY, ALMS_COIN
from src.models.figurines.humans.npcs.npc import NPC
from src.models.figurines.humans.npcs.sentences import ALMS_THANKS_FILE, load_sentences
from src.ui.helper_modules.figurine_click_menu import (
    GIVE_COIN_OPTION, FigurineMenu, FigurineSpeech, show_figurine_menu,
)

VIEW = pygame.Rect(0, 0, 900, 900)


class Beggar(NPC):
    """An NPC without its sprites, as much of one as the bubbles ask of it."""

    SOCIAL_CLASS = "Poor"
    sprite_draw_offset = (0, 0)
    is_hidden = False

    def __init__(self):  # Skips the sprite loading
        self.name = "Beggar"
        self.x, self.y, self.width, self.height = 400, 400, 32, 32
        self.talking_to = None
        self._last_chat_line = None

    @property
    def collision_rect(self):
        return pygame.Rect(self.x, self.y, self.width, self.height)

    def update(self, *args):
        pass

    def _get_scaled_sprite(self, zoom):
        return pygame.Surface((32, 64), pygame.SRCALPHA)


@pytest.fixture
def state():
    pygame.init()
    screen = pygame.display.set_mode((1920, 1080))
    warnings, donations, sounds = [], [], []

    def book_donation(amount, category):
        if state.coins < amount:
            return False
        state.coins -= amount
        donations.append((amount, category))
        return True

    player = SimpleNamespace(x=420, y=420, width=32, height=32)
    camera = SimpleNamespace(zoom=1.0, apply=lambda x, y: (x, y))
    state = SimpleNamespace(
        screen=screen, coins=10, coin_popups=[], info_window=None, active_house_menu=None,
        is_map_visible=True, menu_fade_window=None, menu_fade_timer=0, menu_fade_duration=0.2,
        font=pygame.font.Font(None, 24), warnings=warnings, show_warning=warnings.append,
        donations=donations, sounds=sounds, log_event=lambda *a: None,
    )
    state.game = SimpleNamespace(
        game_map=SimpleNamespace(map_player=player, camera=camera),
        depot=SimpleNamespace(book_donation=book_donation),
        merchant_rank=SimpleNamespace(record_gift=lambda amount: 0.0),
        play_sound=sounds.append,
    )
    return state


def give_coin(state, npc):
    assert show_figurine_menu(state, npc, VIEW)
    menu = state.info_window
    assert isinstance(menu, FigurineMenu)
    rect = next(rect for rect, text in menu.buttons if text == GIVE_COIN_OPTION)
    menu.handle_click(rect.center)


def test_the_coin_is_given_with_its_feedback_and_the_bubble_opens_with_thanks(state):
    npc = Beggar()
    give_coin(state, npc)
    assert state.donations == [(ALMS_COIN, ALMS_CATEGORY)]
    assert len(state.sounds) == 1
    assert len(state.coin_popups) == 1
    speech = state.info_window
    assert isinstance(speech, FigurineSpeech)
    assert npc._last_chat_line in load_sentences(ALMS_THANKS_FILE)
    assert npc.talking_to is state.game.game_map.map_player
    speech.draw()
    assert state.info_window is speech


def test_without_a_coin_there_is_a_warning_and_no_thanks(state):
    state.coins = 0
    npc = Beggar()
    give_coin(state, npc)
    assert state.warnings
    assert not state.coin_popups
    assert state.info_window is None
    assert npc.talking_to is None


def test_thanks_are_not_said_twice_running():
    npc = Beggar()
    said = [npc.thanks_line() for _ in range(50)]
    assert all(first != second for first, second in zip(said, said[1:]))


def test_the_thanks_are_in_their_file():
    sentences = load_sentences(ALMS_THANKS_FILE)
    assert len(sentences) >= 20
    assert len(set(sentences)) == len(sentences)
    assert not any(line.startswith("•") for line in sentences)
