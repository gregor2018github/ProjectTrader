"""What an NPC says in a chat: their class's lines, and now and then a rumour fitting them."""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

from src.models.figurines.humans.npcs import npc as npc_module
from src.models.figurines.humans.npcs import sentences as sentences_module
from src.models.figurines.humans.npcs.npc import NPC
from src.models.figurines.humans.npcs.sentences import (
    CLASS_SENTENCE_FILES, RUMOUR_CHANCE, TRADER_TAG, rumours, rumours_for, sentences_for,
)

MIN_RUMOURS_EACH = 10


class Talker(NPC):
    """An NPC without its sprites, as much of one as a chat asks of it."""

    def __init__(self, social_class, is_trader=False):  # Skips the sprite loading
        self.SOCIAL_CLASS = social_class
        self.IS_TRADER = is_trader
        self._last_chat_line = None

    def update(self, *args):
        pass


@pytest.fixture
def toy_rumours(monkeypatch):
    monkeypatch.setattr(sentences_module, "load_sentences", lambda filename: (
        "Anyone says this.",
        "[Poor, Commons] The low say this.",
        "[Middling Sort,Nobility] The high say this.",
        f"[{TRADER_TAG}] Traders say this.",
    ))


def test_the_brackets_say_who_may_say_a_rumour(toy_rumours):
    assert rumours_for("Poor", False) == ["Anyone says this.", "The low say this."]
    assert rumours_for("Nobility", False) == ["Anyone says this.", "The high say this."]


def test_a_trader_may_say_their_classs_rumours_and_the_traders(toy_rumours):
    assert rumours_for("Commons", True) == ["Anyone says this.", "The low say this.", "Traders say this."]


@pytest.mark.parametrize("social_class", CLASS_SENTENCE_FILES)
def test_a_chat_passes_on_only_a_rumour_of_their_own(monkeypatch, social_class):
    monkeypatch.setattr(npc_module.random, "random", lambda: RUMOUR_CHANCE - 0.01)
    assert Talker(social_class).chat_line() in rumours_for(social_class, False)


@pytest.mark.parametrize("social_class", CLASS_SENTENCE_FILES)
def test_otherwise_they_say_their_own_classs_lines(monkeypatch, social_class):
    monkeypatch.setattr(npc_module.random, "random", lambda: RUMOUR_CHANCE)
    assert Talker(social_class).chat_line() in sentences_for(social_class, False)


def test_with_no_rumour_for_them_they_say_their_own_lines(monkeypatch):
    monkeypatch.setattr(npc_module.random, "random", lambda: 0.0)
    monkeypatch.setattr(npc_module, "rumours_for", lambda social_class, is_trader: [])
    assert Talker("Poor").chat_line() in sentences_for("Poor", False)


def test_the_rumour_files_tags_are_real():
    known = {*CLASS_SENTENCE_FILES, TRADER_TAG}
    for tags, sentence in rumours():
        assert set(tags) <= known, sentence


def test_the_rumours_are_not_repeated():
    sentences = [sentence for _, sentence in rumours()]
    assert len(set(sentences)) == len(sentences)


@pytest.mark.parametrize("social_class", CLASS_SENTENCE_FILES)
def test_every_class_has_rumours_to_tell(social_class):
    assert len(rumours_for(social_class, False)) >= MIN_RUMOURS_EACH


def test_a_line_is_not_said_twice_running():
    npc = Talker("Poor")
    said = [npc.chat_line() for _ in range(100)]
    assert all(first != second for first, second in zip(said, said[1:]))
