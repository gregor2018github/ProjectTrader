"""What an NPC says in a chat: their class's lines, and now and then a rumour anyone may pass on."""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

from src.models.figurines.humans.npcs import npc as npc_module
from src.models.figurines.humans.npcs.npc import NPC
from src.models.figurines.humans.npcs.sentences import (
    CLASS_SENTENCE_FILES, RUMOUR_CHANCE, RUMOUR_FILE, load_sentences, sentences_for,
)


class Talker(NPC):
    """An NPC without its sprites, as much of one as a chat asks of it."""

    def __init__(self, social_class):  # Skips the sprite loading
        self.SOCIAL_CLASS = social_class
        self._last_chat_line = None

    def update(self, *args):
        pass


@pytest.mark.parametrize("social_class", CLASS_SENTENCE_FILES)
def test_anyone_may_pass_on_a_rumour(monkeypatch, social_class):
    monkeypatch.setattr(npc_module.random, "random", lambda: RUMOUR_CHANCE - 0.01)
    assert Talker(social_class).chat_line() in load_sentences(RUMOUR_FILE)


@pytest.mark.parametrize("social_class", CLASS_SENTENCE_FILES)
def test_otherwise_they_say_their_own_classs_lines(monkeypatch, social_class):
    monkeypatch.setattr(npc_module.random, "random", lambda: RUMOUR_CHANCE)
    assert Talker(social_class).chat_line() in sentences_for(social_class, False)


def test_the_rumours_are_in_their_file():
    rumours = load_sentences(RUMOUR_FILE)
    assert len(rumours) >= 20
    assert len(set(rumours)) == len(rumours)


def test_a_line_is_not_said_twice_running():
    npc = Talker("Poor")
    said = [npc.chat_line() for _ in range(100)]
    assert all(first != second for first, second in zip(said, said[1:]))
