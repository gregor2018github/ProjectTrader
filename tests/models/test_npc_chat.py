"""What an NPC says in a chat: their class's lines, and now and then a rumour fitting them."""

import os
import re

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

from src.models.figurines.humans.npcs import npc as npc_module
from src.models.figurines.humans.npcs import sentences as sentences_module
from src.models.figurines.humans.npcs.npc import NPC
from src.models.figurines.humans.npcs.trader_tanner import TraderTanner
from src.models.figurines.humans.npcs.sentences import (
    ALMS_THANKS_FILE, CLASS_SENTENCE_FILES, RUMOUR_CHANCE, RUMOUR_FILE, TRADER_SENTENCE_FILE, TRADER_TAG,
    for_speaker, load_sentences, rumours, rumours_for, sentences_for,
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
    own_lines = [for_speaker(sentence, "male") for sentence in sentences_for(social_class, False)]
    assert Talker(social_class).chat_line() in own_lines


def test_with_no_rumour_for_them_they_say_their_own_lines(monkeypatch):
    monkeypatch.setattr(npc_module.random, "random", lambda: 0.0)
    monkeypatch.setattr(npc_module, "rumours_for", lambda social_class, is_trader: [])
    assert Talker("Poor").chat_line() in sentences_for("Poor", False)


def every_sentence():
    files = [*CLASS_SENTENCE_FILES.values(), TRADER_SENTENCE_FILE, ALMS_THANKS_FILE, RUMOUR_FILE]
    return [sentence for name in files for sentence in load_sentences(name)]


def test_a_man_speaks_of_his_wife_and_a_woman_of_her_husband():
    sentence = "Took my {spouse} along, and {spouse_pronoun} ran off to {love_rival}."
    assert for_speaker(sentence, "male") == "Took my wife along, and she ran off to the tanner."
    assert for_speaker(sentence, "female") == "Took my husband along, and he ran off to the miller's daughter."


def test_the_sentence_files_name_no_spouse_outright():
    for sentence in every_sentence():
        assert not re.search(r"\b(wife|husband)\b", sentence, re.IGNORECASE), sentence


@pytest.mark.parametrize("gender", ["male", "female"])
def test_no_placeholder_is_left_in_what_is_said(gender):
    for sentence in every_sentence():
        said = for_speaker(sentence, gender)
        assert "{" not in said and "}" not in said, sentence


def test_the_tanner_does_not_lose_his_wife_to_himself(monkeypatch):
    class Tanner(Talker, TraderTanner):
        pass

    monkeypatch.setattr(npc_module.random, "random", lambda: 1.0)
    rival_line = next(s for s in load_sentences(CLASS_SENTENCE_FILES["Commons"]) if "{love_rival}" in s)
    assert rival_line in sentences_for("Commons", True)
    npc = Tanner("Commons", is_trader=True)
    said = {npc.chat_line() for _ in range(500)}
    assert for_speaker(rival_line, "male") not in said
    assert len(said) > 1


def test_another_commoner_may_still_say_it(monkeypatch):
    monkeypatch.setattr(npc_module.random, "random", lambda: 1.0)
    rival_line = next(s for s in load_sentences(CLASS_SENTENCE_FILES["Commons"]) if "{love_rival}" in s)
    monkeypatch.setattr(npc_module, "sentences_for", lambda social_class, is_trader: [rival_line])
    assert "the tanner" in Talker("Commons").chat_line()


def test_a_woman_says_a_marriage_line_for_a_woman(monkeypatch):
    monkeypatch.setattr(npc_module.random, "random", lambda: 1.0)
    monkeypatch.setattr(npc_module, "sentences_for", lambda social_class, is_trader: ["My {spouse} snores."])
    npc = Talker("Commons")
    npc.GENDER = "female"
    assert npc.chat_line() == "My husband snores."


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
