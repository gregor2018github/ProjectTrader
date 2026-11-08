"""The fishing how-to sheet: when each page opens, that the game waits, and what its pictures show."""

import datetime
import os
import random
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from src.models.minigames import fishing
from src.models.minigames import fishing_tutorial as tutorial
from src.models.minigames.fishing import FishingMinigame
from src.models.minigames.fishing_pond import Fish, SPECIES, WATER_Y, bottom_y
from src.models.statistics import Statistics

DT = 1 / 60
BOTH_SEEN = (fishing.TIP_TUTORIAL_CAST, fishing.TIP_TUTORIAL_FIGHT)


@pytest.fixture(scope="module", autouse=True)
def screen():
    pygame.init()
    yield pygame.display.set_mode((1920, 1080))


def make(screen, tips_seen=()):
    stats = Statistics()
    stats.minigame_tips_seen = list(tips_seen)
    state = SimpleNamespace(date=datetime.datetime(1500, 1, 4, 10), coin_popups=[], screen=screen,
                            log_event=lambda *a: None)
    game = SimpleNamespace(state=state, sounds={}, weather=SimpleNamespace(),
                           depot=SimpleNamespace(stats=stats, book_labor_income=lambda *a: None))
    return FishingMinigame(screen, game, random.Random(1))


def hook_a_fish(minigame):
    fish = Fish(SPECIES["perch"], random.Random(1))
    fish.x, fish.y = 194.0, 90.0
    minigame.pond.fish.append(fish)
    minigame._start_fight(fish, 0.8, "GOOD STRIKE")
    return minigame.fight


def key(minigame, code):
    minigame.handle_event(pygame.event.Event(pygame.KEYDOWN, key=code))


def click(minigame, canvas_pos, kind=pygame.MOUSEBUTTONDOWN):
    pos = (canvas_pos[0] + minigame.canvas_rect.left, canvas_pos[1] + minigame.canvas_rect.top)
    minigame.handle_event(pygame.event.Event(kind, button=1, pos=pos))


def seen(minigame):
    return minigame.game.depot.stats.minigame_tips_seen


class TestWhenItOpens:
    def test_the_cast_page_opens_by_itself_only_the_first_time(self, screen):
        first = make(screen)
        assert first.tutorial is not None and first.tutorial.page == fishing.PAGE_CAST
        assert seen(first) == [fishing.TIP_TUTORIAL_CAST]
        assert make(screen, tips_seen=(fishing.TIP_TUTORIAL_CAST,)).tutorial is None

    def test_the_fight_page_waits_for_the_first_fish_hooked(self, screen):
        m = make(screen, tips_seen=(fishing.TIP_TUTORIAL_CAST,))
        assert fishing.TIP_TUTORIAL_FIGHT not in seen(m)
        hook_a_fish(m)
        assert m.tutorial is not None and m.tutorial.page == fishing.PAGE_FIGHT
        assert fishing.TIP_TUTORIAL_FIGHT in seen(m)

    def test_later_fish_do_not_open_it(self, screen):
        m = make(screen, tips_seen=BOTH_SEEN)
        hook_a_fish(m)
        assert m.tutorial is None

    def test_a_tip_seen_is_saved(self):
        stats = Statistics()
        stats.minigame_tips_seen.append(fishing.TIP_TUTORIAL_FIGHT)
        assert fishing.TIP_TUTORIAL_FIGHT in Statistics.from_dict(stats.to_dict()).minigame_tips_seen


class TestTheGameWaitsBehindIt:
    def test_the_first_fish_fight_stands_still_until_it_closes(self, screen):
        m = make(screen, tips_seen=(fishing.TIP_TUTORIAL_CAST,))
        fight = hook_a_fish(m)
        before = (fight.t, fight.bar_at, fight.fish_at, fight.catch, fight.fish.x, m.t)
        for _ in range(60):
            m.update(DT)
        assert (fight.t, fight.bar_at, fight.fish_at, fight.catch, fight.fish.x, m.t) == before
        key(m, pygame.K_RETURN)
        assert m.tutorial is None and m.phase == fishing.FIGHT
        m.update(DT)
        assert fight.t > before[0]

    def test_a_click_on_the_page_is_no_cast(self, screen):
        m = make(screen)
        click(m, (300, 300))
        assert m.tutorial is not None and m.phase == fishing.READY and not m.lmb

    @pytest.mark.parametrize("code", [pygame.K_RETURN, pygame.K_SPACE, pygame.K_ESCAPE])
    def test_a_key_closes_it_and_asks_nothing(self, screen, code):
        m = make(screen)
        key(m, code)
        assert m.tutorial is None and m.active and not m.exit_asked

    def test_its_button_closes_it_and_the_click_goes_no_further(self, screen):
        m = make(screen)
        click(m, m.tutorial.button.center)
        assert m.tutorial is None and m.phase == fishing.READY and not m.lmb
        click(m, m.help_rect.center, pygame.MOUSEBUTTONUP)
        assert m.phase == fishing.READY

    def test_closing_it_gives_a_moment_with_the_bar_over_the_fish(self, screen):
        m = make(screen, tips_seen=(fishing.TIP_TUTORIAL_CAST,))
        fight = hook_a_fish(m)
        fight.grace = 0.0
        click(m, m.tutorial.button.center)
        assert m.tutorial is None
        assert fight.fish_in_bar and fight.grace > 0


class TestOpeningItAgain:
    def test_the_title_bar_button_opens_it_and_the_click_is_no_twitch(self, screen):
        m = make(screen, tips_seen=BOTH_SEEN)
        m.phase = fishing.WAIT
        click(m, m.help_rect.center)
        assert m.tutorial is not None and not m.lmb
        key(m, pygame.K_ESCAPE)
        click(m, m.help_rect.center, pygame.MOUSEBUTTONUP)
        assert not m.twitches

    def test_before_the_first_fish_only_the_cast_page_can_be_seen(self, screen):
        m = make(screen, tips_seen=(fishing.TIP_TUTORIAL_CAST,))
        click(m, m.help_rect.center)
        assert m.tutorial.page == fishing.PAGE_CAST and not m.tutorial.can_turn
        key(m, pygame.K_RIGHT)
        assert m.tutorial.page == fishing.PAGE_CAST

    def test_after_it_both_pages_can_be_turned_to(self, screen):
        m = make(screen, tips_seen=BOTH_SEEN)
        click(m, m.help_rect.center)
        assert m.tutorial.page == fishing.PAGE_CAST and m.tutorial.can_turn
        key(m, pygame.K_RIGHT)
        assert m.tutorial.page == fishing.PAGE_FIGHT
        click(m, m.tutorial.turn_button.center)
        assert m.tutorial.page == fishing.PAGE_CAST

    def test_with_a_fish_on_the_line_it_opens_on_the_fight(self, screen):
        m = make(screen, tips_seen=BOTH_SEEN)
        hook_a_fish(m)
        click(m, m.help_rect.center)
        assert m.tutorial.page == fishing.PAGE_FIGHT

    def test_the_button_is_gone_when_the_worms_are_used_up(self, screen):
        m = make(screen, tips_seen=BOTH_SEEN)
        m.worms = 0
        assert not m.help_available
        click(m, m.help_rect.center)
        assert m.tutorial is None


def run(demo, seconds, watch):
    """Plays a picture, collecting what watch(demo) says, in order and without repeats."""
    said = []
    for _ in range(round(seconds / DT)):
        demo.update(DT)
        value = watch(demo)
        if value is not None and value not in said:
            said.append(value)
    return said


def verdict_text(demo):
    return demo.verdict[0] if demo.verdict else None


class TestThePictures:
    def test_they_are_silent_and_touch_nothing_of_the_real_session(self, screen):
        m = make(screen)
        for demo in m.tutorial.demos[fishing.PAGE_CAST]:
            assert demo.game.demo and demo.game.sounds == {} and demo.game.tutorial is None
        stats = m.game.depot.stats
        for _ in range(300):
            m.update(DT)
        assert (m.worms, m.coins, stats.fish_caught, stats.minigames_played) == (fishing.WORMS, 0.0, 0, 0)

    def test_a_demo_never_opens_a_sheet_of_its_own_on_hooking_a_fish(self, screen):
        assert tutorial.WholeDemo(screen, 26).game.tutorial is None

    def test_the_depths_shown_hang_free_but_the_last_is_too_deep(self):
        floor = bottom_y(tutorial._DEPTH_X) - 1
        assert all(WATER_Y + depth < floor for depth in tutorial._DEPTH_TRIES[:-1])
        assert WATER_Y + tutorial._DEPTH_TRIES[-1] >= floor
        assert all((depth - fishing.LEADER_START) % fishing.LEADER_STEP == 0 for depth in tutorial._DEPTH_TRIES)

    def test_the_depth_picture_hangs_free_then_rips_off_and_keeps_looping(self, screen):
        demo = tutorial.DepthDemo(screen)
        assert run(demo, 25, verdict_text) == ["Hangs free", "Hook ripped off!"]
        assert demo.game.worms > 0
        assert demo.index in range(len(tutorial._DEPTH_TRIES))

    def test_the_cast_picture_is_graded_by_the_game(self, screen):
        said = run(tutorial.CastDemo(screen), 25, verdict_text)
        assert said == ["Perfect Cast", "Too short!", "Poor Cast"]

    def test_a_harder_whip_at_the_mark_goes_farther(self, screen):
        demo = tutorial.CastDemo(screen)
        out = run(demo, 15, lambda d: d.landing)
        assert [int(text.split()[0]) for text in out] == sorted((int(t.split()[0]) for t in out), reverse=True)
        assert len(out) == 2

    def test_the_cast_picture_never_tangles_the_line(self, screen):
        assert not any(run(tutorial.CastDemo(screen), 25, lambda d: d.game.tangled or None))

    def test_the_strike_picture_shows_in_time_too_early_and_too_late(self, screen):
        said = run(tutorial.StrikeDemo(screen), 40, verdict_text)
        for text in ("Only a nibble: wait", "It takes!", "Perfect Strike", "Too early!",
                     "Too late: the worm is gone!"):
            assert text in said

    def test_the_meter_picture_fills_in_the_bar_and_drains_out_of_it(self, screen):
        demo = tutorial.MeterDemo(screen, 24)
        said = run(demo, 8, verdict_text)
        assert "In the bar: it fills" in said and "Out of it: it drains" in said
        assert demo.game.phase == fishing.FIGHT

    def test_the_meter_picture_never_ends_its_fight(self, screen):
        demo = tutorial.MeterDemo(screen, 24)
        first = demo.game.fight
        run(demo, 40, lambda d: None)
        assert demo.game.fight is first

    def test_the_hover_picture_rises_falls_and_hovers_with_the_fish_still(self, screen):
        demo = tutorial.HoverDemo(screen)
        fight = demo.game.fight
        said = run(demo, 7, verdict_text)
        assert said == ["Hold: it rises", "Let go: it falls", "Tap: it hovers"]
        assert fight.catch == pytest.approx(fight.catch_from)

    def test_the_hover_picture_really_hovers(self, screen):
        demo = tutorial.HoverDemo(screen)
        run(demo, 2.8, lambda d: None)              # well into the tapping
        spots = []
        for _ in range(60):
            demo.update(DT)
            spots.append(demo.game.fight.bar_at)
        assert max(spots) - min(spots) < 0.2

    def test_the_whole_fight_takes_its_chest_and_ends_in_the_net_soon_enough(self, screen):
        demo = tutorial.WholeDemo(screen, 26)
        said = run(demo, 60, verdict_text)
        assert "Netted!" in said and "A chest!" in said
        assert any(text.startswith("Chest: +") for text in said)
        assert "He broke free!" not in said


class TestDrawing:
    @pytest.mark.parametrize("page", [fishing.PAGE_CAST, fishing.PAGE_FIGHT])
    def test_each_page_draws_and_the_game_draws_after(self, screen, page):
        m = make(screen, tips_seen=BOTH_SEEN)
        m._open_tutorial(page)
        for _ in range(120):
            m.update(DT)
            m.draw()
        key(m, pygame.K_ESCAPE)
        m.update(DT)
        m.draw()

    def test_the_words_fit_their_cards(self, screen):
        m = make(screen)
        font = m.font_words
        for page, layout in tutorial._LAYOUTS.items():
            for card, (_, words) in zip(layout.card_rects(), tutorial.CARDS[page]):
                width, lines, x = card.width - 28, 1, 0
                for word in words.replace("*", "").split():
                    w = font.size(word)[0]
                    if x and x + w > width:
                        lines, x = lines + 1, 0
                    x += w + font.size(" ")[0]
                assert card.top + 50 + layout.picture_h + 16 + lines * 27 <= card.bottom

    def test_the_pictures_crops_lie_in_the_scene_and_keep_its_shape(self):
        scene = pygame.Rect(0, 0, 1200, 640)
        for crop in (tutorial._DEPTH_CROP, tutorial._CAST_CROP, tutorial._STRIKE_CROP,
                     tutorial._MARK_CROP, tutorial._WHOLE_CROP):
            assert scene.contains(crop)
        pictures = tutorial._LAYOUTS[fishing.PAGE_CAST].picture_rects()
        assert tutorial._DEPTH_CROP.size == pictures[0].size and tutorial._STRIKE_CROP.size == pictures[2].size
