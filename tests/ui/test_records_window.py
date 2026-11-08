"""The guild's records: a fish's weight, the tally of what was landed, and the cards showing it."""

import os
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from src.models.minigames.fishing_pond import SPECIES, format_kg
from src.models.statistics import Statistics
from src.ui.helper_modules.records_window import (
    RecordsWindow, UNKNOWN_NAME, fish_records, open_records_window, portrait,
)


@pytest.fixture
def screen():
    pygame.init()
    return pygame.display.set_mode((1920, 1080))


class TestWeight:
    def test_it_follows_the_cube_of_the_length(self):
        carp = SPECIES["carp"]
        assert carp.kg(80) == pytest.approx(carp.kg(40) * 8)

    def test_the_same_length_weighs_by_kind(self):
        assert SPECIES["eel"].kg(80) < SPECIES["pike"].kg(80) < SPECIES["carp"].kg(80)

    @pytest.mark.parametrize("key, cm, low, high", [("roach", 30, 0.2, 0.6), ("pike", 100, 5, 11), ("carp", 80, 6, 13),
                                                    ("eel", 90, 0.8, 2.5)])
    def test_the_big_ones_weigh_what_a_big_one_does(self, key, cm, low, high):
        assert low < SPECIES[key].kg(cm) < high

    def test_small_fish_keep_their_second_decimal(self):
        assert format_kg(0.036) == "0.04 kg"
        assert format_kg(12.34) == "12.3 kg"


class TestTally:
    def test_a_fish_goes_into_the_books(self):
        stats = Statistics()
        assert stats.record_fish("carp", 50, 2.0) is True
        assert stats.record_fish("carp", 40, 1.0) is False
        assert stats.record_fish("carp", 60, 3.0) is True
        assert stats.fish_caught == 3
        assert stats.fish_tally["carp"] == {"count": 3, "kg": 6.0}
        assert stats.fishing_records["carp"] == 60

    def test_it_survives_a_save(self):
        stats = Statistics()
        stats.record_fish("pike", 70, 2.5)
        assert Statistics.from_dict(stats.to_dict()).fish_tally == {"pike": {"count": 1, "kg": 2.5}}

    def test_an_older_save_knows_its_biggest_was_caught(self):
        stats = Statistics.from_dict({"fishing_records": {"pike": 100.0, "gone_fish": 9.0}, "fish_caught": 7})
        assert stats.fish_tally == {"pike": {"count": 1, "kg": SPECIES["pike"].kg(100.0)}}


class TestCards:
    def test_every_kind_but_the_minnows_has_one(self):
        assert [r.species.key for r in fish_records(Statistics())] == [k for k in SPECIES if k != "minnow"]

    def test_a_kind_not_caught_shows_only_a_question_mark(self):
        record = fish_records(Statistics())[0]
        assert not record.caught
        assert record.name == UNKNOWN_NAME
        assert not any(ch.isdigit() for line in record.lines() for ch in line)

    def test_a_caught_kind_shows_its_name_and_numbers(self):
        stats = Statistics()
        stats.record_fish("carp", 80, SPECIES["carp"].kg(80))
        stats.record_fish("carp", 40, SPECIES["carp"].kg(40))
        record = next(r for r in fish_records(stats) if r.species.key == "carp")
        assert record.name == "Carp"
        assert record.lines() == ["Caught: 2", f"Total: {format_kg(SPECIES['carp'].kg(80) + SPECIES['carp'].kg(40))}",
                                  f"Biggest: 80 cm, {format_kg(SPECIES['carp'].kg(80))}"]

    def test_a_kind_not_caught_has_a_grey_portrait(self, screen):
        grey = portrait(SPECIES["golden_carp"], False)
        colours = [grey.get_at((x, y)) for x in range(grey.get_width()) for y in range(grey.get_height())]
        assert all(c.r == c.g == c.b for c in colours if c.a)
        assert any(c.a for c in colours)
        coloured = portrait(SPECIES["golden_carp"], True)
        assert any(coloured.get_at((x, y)).r != coloured.get_at((x, y)).b
                   for x in range(coloured.get_width()) for y in range(coloured.get_height()))


class TestWindow:
    def make(self, screen):
        stats = Statistics()
        stats.record_fish("pike", 100, SPECIES["pike"].kg(100))
        state = SimpleNamespace(screen=screen, info_window=None, game=SimpleNamespace(depot=SimpleNamespace(stats=stats)))
        open_records_window(state)
        return state

    def test_all_cards_fit_the_panel_and_their_text_the_card(self, screen):
        window = self.make(screen).info_window
        assert isinstance(window, RecordsWindow)
        assert window.H <= screen.get_height() and window.W <= screen.get_width()
        for record in fish_records(window.game_state.game.depot.stats):
            for line in record.lines():
                assert window.body_font.size(line)[0] <= window.CARD_W - 146 - 6
            assert window.name_font.size(record.species.name)[0] <= window.CARD_W - 146 - 6

    def test_it_draws_also_while_fading(self, screen):
        window = self.make(screen).info_window
        window.draw()
        window.draw(0.5)
