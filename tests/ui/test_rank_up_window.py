"""The sheet announcing a rise in rank: what it shows, that a stray click does not close it,
and that it waits its turn behind whatever else has the player's attention."""

import os
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from src.game import Game
from src.models.merchant_rank import Rank, RankRise
from src.ui.helper_modules import rank_up_window
from src.ui.helper_modules.rank_up_window import INPUT_DELAY_S, RankUpWindow, road_rows

RANKS = [Rank("First", 0, 0, 0, 0), Rank("Second", 100, 0, 100, 5), Rank("Third", 1000, 500, 1000, 20)]
STANDING = {"wealth": 400, "property_value": 500, "volume": 0, "reputation": 7}
RISE = RankRise(1, "Second", ("buy buildings",), False)


@pytest.fixture
def screen():
    pygame.init()
    return pygame.display.set_mode((1920, 1080))


def game_state(screen, **attributes):
    merchant_rank = SimpleNamespace(ranks=RANKS, standing=lambda: STANDING)
    return SimpleNamespace(screen=screen, game=SimpleNamespace(merchant_rank=merchant_rank), **attributes)


def opened(window, monkeypatch, seconds):
    """The window as it is that long after its first draw."""
    window._opened_at = 1000
    monkeypatch.setattr(pygame.time, "get_ticks", lambda: 1000 + round(seconds * 1000))
    return window


class TestTheRoad:
    def test_rows_set_what_the_player_has_against_the_next_rank(self):
        wealth, property_value, volume, reputation = road_rows(RANKS[2], STANDING)
        assert (wealth.have, wealth.need, wealth.met) == ("400", "1,000", False)
        assert wealth.share == pytest.approx(0.4)
        assert property_value.met and property_value.share == 1.0
        assert volume.share == 0.0
        assert reputation.need == "20.0"

    def test_a_debt_shows_as_no_progress(self):
        assert road_rows(RANKS[2], {**STANDING, "wealth": -300})[0].share == 0.0

    def test_a_condition_asking_nothing_counts_as_done(self):
        assert road_rows(RANKS[1], {**STANDING, "property_value": 0})[1].share == 1.0


class TestDrawing:
    def test_every_numeral_fits_inside_the_wreath(self):
        for numeral in rank_up_window.ROMAN:
            assert rank_up_window.numeral_width(numeral) + 6 <= 2 * (rank_up_window.WREATH_R - 12)

    @pytest.mark.parametrize("rise", [
        RISE,
        RankRise(1, "Second", (), True),            # regained, opening nothing
        RankRise(2, "Third", (), False),            # the top: nothing further to show
    ])
    def test_every_kind_of_rise_draws_on_the_screen(self, screen, rise):
        window = RankUpWindow(screen, game_state(screen), rise)
        window.draw()
        assert screen.get_rect().contains(window.panel)
        assert window.panel.contains(window.button_rect)

    def test_the_top_rank_has_no_road(self, screen):
        window = RankUpWindow(screen, game_state(screen), RankRise(2, "Third", (), False))
        assert window.next_rank is None and window.rows == []

    def test_what_it_opens_makes_room_for_itself(self, screen):
        without = RankUpWindow(screen, game_state(screen), RankRise(1, "Second", (), False))
        with_unlock = RankUpWindow(screen, game_state(screen), RISE)
        assert with_unlock.panel.height == without.panel.height + rank_up_window.PLAQUE_H

    def test_it_settles_at_full_opacity_and_shows_its_button_only_when_it_takes_input(self, screen, monkeypatch):
        window = opened(RankUpWindow(screen, game_state(screen), RISE), monkeypatch, INPUT_DELAY_S + 1)
        window.draw()
        assert window._sheet.get_alpha() == 255
        assert window.takes_input


class TestInput:
    def test_a_stray_click_right_after_it_opens_does_nothing(self, screen, monkeypatch):
        window = opened(RankUpWindow(screen, game_state(screen), RISE), monkeypatch, INPUT_DELAY_S / 2)
        assert window.handle_click(window.button_rect.center) is None
        assert window.handle_key(SimpleNamespace(key=pygame.K_SPACE)) is None

    def test_before_its_first_draw_it_takes_no_input(self, screen):
        window = RankUpWindow(screen, game_state(screen), RISE)
        assert window.handle_click(window.button_rect.center) is None

    def test_the_button_closes_it(self, screen, monkeypatch):
        window = opened(RankUpWindow(screen, game_state(screen), RISE), monkeypatch, INPUT_DELAY_S)
        assert window.handle_click(window.button_rect.center) == "OK"

    def test_a_click_elsewhere_does_not_close_it(self, screen, monkeypatch):
        window = opened(RankUpWindow(screen, game_state(screen), RISE), monkeypatch, INPUT_DELAY_S)
        assert window.handle_click((window.panel.left + 3, window.panel.top + 3)) is None
        assert window.handle_click((0, 0)) is None

    @pytest.mark.parametrize("key", [pygame.K_RETURN, pygame.K_SPACE, pygame.K_ESCAPE])
    def test_the_keys_close_it(self, screen, monkeypatch, key):
        window = opened(RankUpWindow(screen, game_state(screen), RISE), monkeypatch, INPUT_DELAY_S)
        assert window.handle_key(SimpleNamespace(key=key)) == "OK"


class TestItsTurn:
    """`Game._show_next_notice`, on a stand-in for the game."""

    @staticmethod
    def game(screen, **blocked):
        state = dict(info_window=None, minigame=None, contract_acquisition=None, menu_fade_window=None,
                     time_level=3)
        state.update(blocked)
        played = []
        fake = SimpleNamespace(state=game_state(screen, **state), _pending_notices=[RISE],
                               play_sound=played.append, played=played)
        return fake

    def test_it_opens_at_once_and_pauses_the_game(self, screen):
        game = self.game(screen)
        Game._show_next_notice(game)
        assert isinstance(game.state.info_window, RankUpWindow)
        assert game.state.time_level == 1 and game.state.info_window.restore_time_level == 3
        assert game.played == ["scroll_unroll"] and game._pending_notices == []

    @pytest.mark.parametrize("busy", ["info_window", "minigame", "contract_acquisition", "menu_fade_window"])
    def test_it_waits_for_what_is_open(self, screen, busy):
        game = self.game(screen, **{busy: object()})
        Game._show_next_notice(game)
        assert game._pending_notices == [RISE]
        assert game.state.time_level == 3

    def test_a_plain_notice_still_opens_as_before(self, screen):
        game = self.game(screen)
        game._pending_notices = ["A licence runs out."]
        game.state.font = pygame.font.SysFont("arial", 18)
        Game._show_next_notice(game)
        assert game.state.info_window.message == "A licence runs out."
