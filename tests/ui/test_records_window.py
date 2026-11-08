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
    NOT_TRACKED, PAGE_FISHING, PAGE_WOODHACKING, RecordsWindow, UNKNOWN_NAME, date_text, fish_records,
    open_records_window, overall_lines, portrait, score_details,
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


class TestWoodhackingBooks:
    def test_only_the_five_best_are_kept_best_first(self):
        stats = Statistics()
        for score in (10, 50, 30, 20, 40, 60, 5):
            stats.record_woodhacking(score, "1500-01-03", 1, 1, 1)
        assert [entry["score"] for entry in stats.woodhacking_scores] == [60, 50, 40, 30, 20]

    def test_the_bests_and_totals_count_every_session_even_one_off_the_list(self):
        stats = Statistics()
        for score in (60, 50, 40, 30, 20):
            stats.record_woodhacking(score, "1500-01-03", 3, 2, 10)
        stats.record_woodhacking(1, "1500-01-04", 9, 4, 12)
        assert stats.woodhacking_bests == {"best_streak": 9, "most_perfects": 4, "total_perfects": 14,
                                           "most_blocks": 12, "total_blocks": 62}

    def test_they_survive_a_save(self):
        stats = Statistics()
        stats.record_woodhacking(40, "1500-01-03", 3, 2, 10)
        loaded = Statistics.from_dict(stats.to_dict())
        assert loaded.woodhacking_scores == stats.woodhacking_scores
        assert loaded.woodhacking_bests == stats.woodhacking_bests

    def test_an_older_save_keeps_its_best_score_with_nothing_else_known(self):
        stats = Statistics.from_dict({"woodhacking_highscore": 77.5})
        assert stats.woodhacking_scores == [{"score": 77.5, "date": None, "streak": None, "perfects": None, "blocks": None}]
        assert stats.woodhacking_bests == {}

    def test_an_older_save_without_a_score_lists_nothing(self):
        assert Statistics.from_dict({}).woodhacking_scores == []


class TestWoodhackingPage:
    def make(self, screen, stats):
        state = SimpleNamespace(screen=screen, info_window=None, game=SimpleNamespace(depot=SimpleNamespace(stats=stats)))
        open_records_window(state)
        return state.info_window

    def test_what_was_not_tracked_shows_a_dash(self):
        old = Statistics.from_dict({"woodhacking_highscore": 77.5})
        entry = old.woodhacking_scores[0]
        assert date_text(entry) == NOT_TRACKED
        assert [value for _, value in score_details(entry)] == [NOT_TRACKED] * 3
        assert [value for _, value in overall_lines(old)] == [NOT_TRACKED] * 5

    def test_a_score_has_its_calendar_date_and_values(self):
        stats = Statistics()
        stats.record_woodhacking(40, "1500-01-03", 3, 2, 10)
        entry = stats.woodhacking_scores[0]
        assert date_text(entry) == "3 Spring 1500"
        assert score_details(entry) == [("Best streak", "3"), ("Perfect hits", "2"), ("Blocks chopped", "10")]
        assert [value for _, value in overall_lines(stats)] == ["3", "2", "2", "10", "10"]

    def test_a_tab_turns_the_page_and_keeps_the_window_open(self, screen):
        window = self.make(screen, Statistics())
        assert window.page == PAGE_FISHING
        assert window.handle_click(window.tab_rects[PAGE_WOODHACKING].center)
        assert window.page == PAGE_WOODHACKING
        assert window.game_state.info_window is window

    def test_only_a_row_holding_a_score_can_be_hovered_and_only_on_its_page(self, screen):
        stats = Statistics()
        stats.record_woodhacking(40, "1500-01-03", 3, 2, 10)
        window = self.make(screen, stats)
        first, second = window.score_row_rect(0).center, window.score_row_rect(1).center
        assert window.hovered_score(first) is None
        window.page = PAGE_WOODHACKING
        assert window.hovered_score(first) == 0
        assert window.hovered_score(second) is None

    def test_the_rows_and_labels_fit_their_panels(self, screen):
        window = self.make(screen, Statistics())
        assert window.score_row_rect(4).bottom <= window.scores_rect.bottom
        assert window.overall_rect.top + window.PANEL_HEAD + 5 * window.OVERALL_ROW_H <= window.overall_rect.bottom
        assert window.overall_rect.right <= window.panel.right - window.PAD
        for label, _ in overall_lines(Statistics()):
            assert window.body_font.size(label)[0] <= window.overall_rect.width - 18 - 90

    @pytest.mark.parametrize("alpha", (1.0, 0.5))
    def test_it_draws_with_a_tooltip(self, screen, monkeypatch, alpha):
        stats = Statistics()
        stats.record_woodhacking(40, "1500-01-03", 3, 2, 10)
        window = self.make(screen, stats)
        window.page = PAGE_WOODHACKING
        monkeypatch.setattr(pygame.mouse, "get_pos", lambda: window.score_row_rect(0).center)
        window.draw(alpha)
