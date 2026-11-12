"""The council's window and the sheet of a session: the pages, the buttons passing the
clicks on to the model, the vote played out, and the arms."""

import datetime
import os
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from src.models import council as council_module
from src.models.council import Council, PLAYER, Result, SessionReport, Vote
from src.models.depot import Depot
from src.models.merchant_rank import rank_index
from src.models.player import Player
from src.ui import heraldry
from src.ui.helper_modules import council_window as window_module
from src.ui.helper_modules.council_window import (
    CouncilWindow, PAGE_ELECTION, PAGE_NOTABLES, PAGE_OFFICES, PAGES, open_council_window, wrap,
)
from src.ui.helper_modules.session_window import (
    FIRST_VOTE_S, SessionWindow, VOTE_EVERY_S, other_business, verdict_text,
)

START = datetime.datetime(1500, 1, 1, 8)
GOODS = ("Wine", "Cloth", "Spices")


@pytest.fixture
def screen():
    pygame.init()
    return pygame.display.set_mode((1920, 1080))


@pytest.fixture(autouse=True)
def quiet(monkeypatch):
    """No coins fall and no third candidate turns up; the rest is the game's own council."""
    monkeypatch.setattr(window_module, "on_money_spent", lambda game_state, amount=0.0: None)
    monkeypatch.setattr(council_module, "THIRD_CANDIDATE_CHANCE", 0.0)


@pytest.fixture
def game_state(screen):
    depot = Depot(money=5_000, fee_rate=0.01, storage_capacity=100, goods=GOODS)
    player = Player(name="Tester", cost_of_living=0)
    goods = [SimpleNamespace(name=name, get_price=lambda: 10.0) for name in GOODS]
    council = Council(depot, player, SimpleNamespace(level=rank_index("Chapman")), goods, seed=5)
    game = SimpleNamespace(depot=depot, council=council, images={})
    return SimpleNamespace(screen=screen, date=START, game=game, info_window=None, active_house_menu=None,
                           menu_fade_window=None, menu_fade_timer=0.0, menu_fade_duration=0.2)


@pytest.fixture
def window(game_state):
    return CouncilWindow(game_state.screen, game_state)


def click(window, key):
    window.draw()
    rect = window.button_rect(key)
    assert rect is not None, f"{key} is not drawn"
    window.handle_click(rect.center)


class TestWindow:
    def test_it_opens_on_the_offices(self, game_state):
        open_council_window(game_state, house="hall")
        assert isinstance(game_state.info_window, CouncilWindow)
        assert game_state.info_window.page == PAGE_OFFICES
        assert game_state.active_house_menu == "hall"

    def test_it_opens_on_the_election_when_there_is_one(self, game_state):
        game_state.game.council.stand("market_warden", START)
        assert CouncilWindow(game_state.screen, game_state).page == PAGE_ELECTION

    @pytest.mark.parametrize("page", PAGES)
    def test_every_page_draws(self, window, page):
        window.page = page
        window.draw()
        window.draw(alpha_scale=0.5)

    def test_every_page_draws_with_an_election_on(self, window, game_state):
        council = game_state.game.council
        council.stand("market_warden", START)
        council.notables["isolde"].grudge = 50
        for page in PAGES:
            window.page = page
            window.notable_key = "isolde" if page == PAGE_NOTABLES else window.notable_key
            window.draw()

    def test_a_tab_turns_the_page(self, window):
        window.draw()
        window.handle_click(window.tab_rects[PAGE_NOTABLES].move(window.panel.topleft).center)
        assert window.page == PAGE_NOTABLES

    def test_the_cards_make_a_pyramid(self, window):
        council = window.council
        tops = {council.offices[key].tier: window.card_rect(key).top for key in council.offices}
        assert tops[3] < tops[2] < tops[1]
        for key in council.offices:
            assert window.body.contains(window.card_rect(key))

    def test_no_two_cards_overlap(self, window):
        rects = [window.card_rect(key) for key in window.council.offices]
        assert all(rects[i].collidelist(rects[i + 1:]) == -1 for i in range(len(rects)))

    def test_a_card_is_chosen_by_a_click(self, window):
        click(window, "office:town_clerk")
        assert window.office_key == "town_clerk"

    def test_standing_puts_the_name_down_and_shows_the_election(self, window, game_state):
        click(window, "office:market_warden")
        click(window, "stand")
        council = game_state.game.council
        assert council.candidacy.office == "market_warden"
        assert window.page == PAGE_ELECTION and window.message.ok
        assert game_state.game.depot.money == 5_000 - council_module.COUNCIL_FILING_FEE[1]

    def test_a_seat_out_of_reach_has_no_button(self, window):
        click(window, "office:mayor")
        window.draw()
        assert window.button_rect("stand") is None

    def test_the_name_can_be_taken_off_again(self, window, game_state):
        click(window, "office:market_warden")
        click(window, "stand")
        click(window, "withdraw")
        assert game_state.game.council.candidacy is None

    def test_a_gift_is_a_click(self, window, game_state):
        window.page = PAGE_NOTABLES
        click(window, "notable:piers")
        click(window, "gift:1")
        council = game_state.game.council
        assert council.notables["piers"].favour > 0
        assert game_state.game.depot.money < 5_000
        assert window.message.ok

    def test_what_cannot_be_paid_cannot_be_clicked(self, window, game_state):
        game_state.game.depot.money = 0
        window.page = PAGE_NOTABLES
        window.draw()
        assert window.button_rect("gift:0") is None and window.button_rect("banquet") is None

    def test_a_voter_in_the_election_leads_to_his_page(self, window, game_state):
        council = game_state.game.council
        council.stand("market_warden", START)
        window.page = PAGE_ELECTION
        voter = council.electorate("market_warden", council.candidacy.candidates)[0]
        click(window, f"voter:{voter}")
        assert window.page == PAGE_NOTABLES and window.notable_key == voter
        window.draw()
        assert window.button_rect("purse") is not None and window.button_rect("delay") is not None

    def test_a_click_outside_closes_it(self, window, game_state):
        game_state.info_window = window
        window.handle_click((5, 5))
        assert game_state.info_window is None

    def test_long_words_are_broken_to_the_width(self, window):
        lines = wrap("one two three four five six seven eight nine ten", window.small_font, 90)
        assert len(lines) > 1 and all(window.small_font.size(line)[0] <= 90 for line in lines)


def report_of(council, votes, winner, holder="hilda", candidates=(PLAYER, "hilda"), **more):
    result = Result("market_warden", list(candidates), votes, winner, holder, concerns_player=True, **more)
    return SessionReport(0, START, [result])


class TestSession:
    VOTES = [Vote("godwin", PLAYER), Vote("edith", "hilda"), Vote("piers", None, "kept to bed with a fever"),
             Vote("osbert", PLAYER)]

    def make(self, game_state, **more):
        council = game_state.game.council
        return SessionWindow(game_state.screen, game_state, report_of(council, self.VOTES, PLAYER, **more))

    def test_the_votes_come_one_after_another(self, game_state):
        sheet = self.make(game_state)
        assert sheet.votes_shown(0.0) == 0
        assert sheet.votes_shown(FIRST_VOTE_S) == 1
        assert sheet.votes_shown(FIRST_VOTE_S + VOTE_EVERY_S * 2.5) == 3
        assert sheet.votes_shown(100.0) == 4

    def test_a_click_shows_the_rest_and_only_then_the_button_counts(self, game_state):
        sheet = self.make(game_state)
        sheet.draw()
        assert not sheet.finished
        assert sheet.handle_click(sheet.button_rect.center) is None
        assert sheet.finished and sheet.votes_shown() == 4
        sheet.draw()
        assert sheet.handle_click((5, 5)) is None
        assert sheet.handle_click(sheet.button_rect.center) == "OK"

    def test_a_key_does_the_same(self, game_state):
        sheet = self.make(game_state)
        key = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN)
        assert sheet.handle_key(key) is None
        assert sheet.handle_key(key) == "OK"

    def test_it_draws_with_notes_and_other_business(self, game_state):
        council = game_state.game.council
        report = report_of(council, self.VOTES, PLAYER, notes=["Hilda Fenwick will not forget this."])
        report.results.append(Result("town_clerk", ["piers", "maud"], [], "piers", "piers"))
        sheet = SessionWindow(game_state.screen, game_state, report)
        sheet.skip()
        sheet.draw()
        assert sheet.note_lines and sheet.other_lines
        assert game_state.screen.get_rect().contains(sheet.panel)

    def test_three_candidates_have_a_column_each(self, game_state):
        sheet = self.make(game_state, candidates=(PLAYER, "hilda", "maud"))
        xs = [sheet.candidate_x(c) for c in (PLAYER, "hilda", "maud")]
        assert xs == sorted(xs) and len(set(xs)) == 3
        sheet.skip()
        sheet.draw()

    def test_an_unopposed_seat_has_no_vote_to_show(self, game_state):
        council = game_state.game.council
        sheet = SessionWindow(game_state.screen, game_state,
                              report_of(council, [], PLAYER, holder=PLAYER, candidates=(PLAYER,)))
        sheet.draw()
        assert sheet.votes_shown(100.0) == 0

    def test_the_verdict_says_what_it_means_for_the_player(self, game_state):
        council = game_state.game.council

        def verdict(winner, holder, **more):
            return verdict_text(council, report_of(council, [], winner, holder=holder, **more).results[0])

        assert verdict(PLAYER, "hilda") == ("You are elected Market Warden", True)
        assert verdict(PLAYER, PLAYER) == ("You keep your seat as Market Warden", True)
        assert verdict("hilda", "hilda") == ("Hilda Fenwick keeps the seat", False)
        assert verdict("maud", "hilda") == ("Maud Pennyfeather wins the seat", False)
        assert verdict("maud", PLAYER) == ("Maud Pennyfeather takes your seat", False)
        assert verdict("maud", PLAYER, forfeited=True) == ("Your seat as Market Warden is forfeit", False)

    def test_the_councils_other_business_reads_in_a_line(self, game_state):
        council = game_state.game.council
        kept = Result("town_clerk", ["piers", "maud"], [], "piers", "piers")
        lost = Result("town_clerk", ["piers", "maud"], [], "maud", "piers")
        alone = Result("town_clerk", ["piers"], [], "piers", "piers")
        assert other_business(council, kept) == "Piers Quillon kept the seat of Town Clerk against Maud Pennyfeather."
        assert other_business(council, lost) == "Maud Pennyfeather took the seat of Town Clerk from Piers Quillon."
        assert other_business(council, alone) == "Piers Quillon was confirmed as Town Clerk, unopposed."


class TestArms:
    @pytest.mark.parametrize("charge", sorted(heraldry.CHARGES))
    def test_every_charge_makes_a_shield(self, screen, charge):
        arms = {"field": [30, 60, 110], "charge": charge, "metal": "silver"}
        shield = heraldry.shield((40, 48), arms)
        assert shield.get_size() == (40, 48)
        assert shield.get_at((20, 6))[3] == 255             # painted near its top
        assert shield.get_at((1, 46))[3] == 0               # and cut away beside its point

    def test_a_shield_is_made_once(self, screen):
        arms = {"field": [30, 60, 110], "charge": "pale", "metal": "gold"}
        assert heraldry.shield((40, 48), arms) is heraldry.shield((40, 48), dict(arms))
        assert heraldry.shield((40, 48), arms, lit=False) is not heraldry.shield((40, 48), arms)

    def test_the_players_arms_are_drawable(self, screen):
        heraldry.draw_arms(screen, pygame.Rect(0, 0, 50, 60), heraldry.PLAYER_ARMS)
