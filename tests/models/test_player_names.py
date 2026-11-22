"""The player's name (models/player_names.py): rolled for a new game, typed names
cleaned, and a name made up, always the same, for a save from before names."""

import random

from src.models import player_names as mod
from src.models.player_names import clean_name, is_legacy, name_of_save, random_name


def test_constants_the_tests_rely_on():
    assert mod.MAX_NAME_LENGTH == 24
    assert "new player" in mod.LEGACY_NAMES


def test_a_rolled_name_is_a_first_name_and_a_family_name_or_a_place():
    rng = random.Random(3)
    for _ in range(300):
        name = random_name(rng)
        first, rest = name.split(" ", 1)
        assert first in mod.FIRST_NAMES
        assert rest in mod.FAMILY_NAMES or (rest.startswith("of ") and rest[3:] in mod.PLACES)
        assert len(name) <= mod.MAX_NAME_LENGTH


def test_the_uncles_and_the_woodcutters_names_are_not_rolled():
    assert "Gared" not in mod.FIRST_NAMES and "Osric" not in mod.FIRST_NAMES


def test_a_reroll_never_gives_the_name_shown():
    rng = random.Random(1)
    name = random_name(rng)
    for _ in range(100):
        assert random_name(rng, avoid=name) != name


def test_a_typed_name_is_trimmed_and_cut_to_length():
    assert clean_name("  Hans   Sachs ") == "Hans Sachs"
    assert clean_name("x" * 40) == "x" * mod.MAX_NAME_LENGTH
    assert clean_name("   ") == ""


def test_new_player_and_nothing_are_names_never_chosen():
    assert is_legacy("New Player") and is_legacy("") and is_legacy(None)
    assert not is_legacy("Konrad Weber")


def test_a_save_keeps_its_own_name():
    assert name_of_save({"player": {"name": "Konrad Weber"}, "sim": {"seed": 5}}) == "Konrad Weber"


def test_an_old_save_gets_a_name_the_same_every_time_by_its_seed():
    old = {"player": {"name": "New Player"}, "sim": {"seed": 12345}}
    name = name_of_save(old)
    assert not is_legacy(name)
    assert name_of_save(old) == name
    names = {name_of_save({"player": {"name": "New Player"}, "sim": {"seed": s}}) for s in range(20)}
    assert len(names) > 10


def test_a_save_without_seed_or_player_still_gets_a_name():
    assert not is_legacy(name_of_save({"saved_at": "2026-01-01T10:00:00"}))
