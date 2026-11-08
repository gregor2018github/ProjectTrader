"""The woodhacking how-to page: when it opens, that the game waits, and what its pictures show."""

import datetime
from types import SimpleNamespace

import pygame
import pytest

from src.models.minigames import woodhacking as wh
from src.models.minigames import woodhacking_tutorial as tutorial
from src.models.minigames.woodhacking_scene import SPLIT
from src.models.statistics import Statistics

DT = 1 / 60


@pytest.fixture(scope="module", autouse=True)
def display():
    pygame.init()
    screen = pygame.display.set_mode((1920, 1080))
    yield screen
    pygame.quit()


def _minigame(screen, tips_seen=()):
    stats = Statistics()
    stats.minigame_tips_seen = list(tips_seen)
    depot = SimpleNamespace(stats=stats, book_labor_income=lambda coins, name: None)
    game = SimpleNamespace(depot=depot, state=SimpleNamespace(log_event=lambda *a: None, date=datetime.datetime(1500, 1, 3, 10)),
                           sounds={}, play_sound=lambda name: None)
    return wh.WoodhackingMinigame(screen, game)


def _click(minigame, canvas_pos, kind=pygame.MOUSEBUTTONDOWN):
    pos = (canvas_pos[0] + minigame.canvas_rect.left, canvas_pos[1] + minigame.canvas_rect.top)
    return pygame.event.Event(kind, button=1, pos=pos)


def test_it_opens_by_itself_only_the_first_time(display):
    first = _minigame(display)
    assert first.tutorial is not None
    assert wh.TIP_TUTORIAL in first.game.depot.stats.minigame_tips_seen
    assert _minigame(display, tips_seen=(wh.TIP_TUTORIAL,)).tutorial is None


def test_the_game_waits_behind_the_page(display):
    m = _minigame(display)
    aim = m.aim
    for _ in range(30):
        m.update(DT)
    assert m.aim == aim
    m.handle_event(_click(m, (300, 300)))        # a click on the page is no swing
    assert not m.charging and m.tutorial is not None


@pytest.mark.parametrize("key", [pygame.K_RETURN, pygame.K_SPACE, pygame.K_ESCAPE])
def test_a_key_closes_the_page_and_escape_does_not_leave_the_game(display, key):
    m = _minigame(display)
    m.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key))
    assert m.tutorial is None and m.active


def test_its_button_closes_it_and_the_click_is_not_a_swing(display):
    m = _minigame(display)
    m.update(DT)
    m.draw()                                     # places the button
    button = m.tutorial.button.center
    m.handle_event(_click(m, button))
    assert m.tutorial is None and not m.charging
    m.handle_event(_click(m, button, pygame.MOUSEBUTTONUP))
    assert m.attempt == 0


def test_the_title_bar_button_opens_it_again_until_the_last_swing(display):
    m = _minigame(display, tips_seen=(wh.TIP_TUTORIAL,))
    m.handle_event(_click(m, m.help_rect.center))
    assert m.tutorial is not None and not m.charging
    m.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    m._ending = True
    assert not m.help_available
    m.handle_event(_click(m, m.help_rect.center))
    assert m.tutorial is None


def test_the_power_picture_says_how_each_try_went_and_moves_the_green():
    demo = tutorial.PowerDemo()
    said, centres = [], {demo.centre}
    for _ in range(round(30 / DT)):
        demo.update(DT)
        centres.add(round(demo.centre, 2))
        if demo.verdict and demo.verdict[0] not in said:
            said.append(demo.verdict[0])
    assert said == ["Just right!", "Too weak!", "Too strong!"]
    assert {0.64, 0.36} <= centres


def test_the_bob_picture_swings_faster_while_held():
    demo = tutorial.BobDemo()
    for _ in range(round(1 / DT)):
        demo.update(DT)
    free = abs(tutorial.next_aim(0.0, 1, 0.0, demo.power, DT)[0])
    while not demo.held:
        demo.update(DT)
    for _ in range(round(1 / DT)):
        demo.update(DT)
    assert abs(tutorial.next_aim(0.0, 1, 0.0, demo.power, DT)[0]) > 2 * free


def test_the_scene_picture_lets_go_with_the_bob_where_its_try_wants_it():
    demo = tutorial.SceneDemo(pygame.font.SysFont(None, 20))
    seen = []
    for _ in range(round(90 / DT)):
        demo.update(DT)
        if demo.held and abs(demo.power - demo.current.release) < tutorial.POWER_RATE * DT:
            demo.update(DT)                      # the frame it lets go on
            try_made = tutorial._SCENE_TRIES[len(seen) % len(tutorial._SCENE_TRIES)]
            assert abs(abs(demo.aim) - try_made.aim) < 0.15
            seen.append(try_made)
            if len(seen) == 2 * len(tutorial._SCENE_TRIES):
                break
    assert len(seen) == 2 * len(tutorial._SCENE_TRIES), "the picture keeps looping"


def test_a_good_try_of_the_scene_picture_is_truly_good_by_the_game_rules():
    for t in tutorial._SCENE_TRIES:
        lo, hi = tutorial._zone(t.zone)
        aim_pts, _, _, aim_miss = wh._grade_aim(t.aim)
        pow_pts, _, _, pow_miss = wh._grade_power(t.release, lo, hi)
        points = 0 if aim_miss or pow_miss else aim_pts + pow_pts
        assert wh.swing_outcome(points, t.release, lo) == t.outcome
        assert t.good == (t.outcome == SPLIT)


def test_the_exit_question_draws(display):
    m = _minigame(display, tips_seen=(wh.TIP_TUTORIAL,))
    m.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    m.update(DT)
    m.draw()
    assert m.exit_asked


def test_the_page_draws_and_leaves_the_game_drawing_after(display):
    m = _minigame(display)
    for _ in range(120):
        m.update(DT)
        m.draw()
    m.tutorial.closed = True
    m.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    m.update(DT)
    m.draw()


def test_the_words_fit_their_cards(display):
    font = _minigame(display).font_words
    for card, (_, words) in zip(tutorial._LAYOUT.card_rects(), tutorial.CARDS):
        width, lines, x = card.width - 28, 1, 0
        for word in words.replace("*", "").split():
            w = font.size(word)[0]
            if x and x + w > width:
                lines, x = lines + 1, 0
            x += w + font.size(" ")[0]
        assert card.top + 50 + tutorial._LAYOUT.picture_h + 16 + lines * 27 <= card.bottom
