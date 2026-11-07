"""The chopping stump glows on the map while today's wood is still to be chopped."""

from types import SimpleNamespace

import pygame

from src.ui.helper_modules.house_click_menu import inject_available_glow_into_queue, woodhacking_available
from tests.fakes import START_DATE


def _state(last_day):
    stats = SimpleNamespace(last_woodhacking_day=last_day)
    return SimpleNamespace(date=START_DATE, game=SimpleNamespace(depot=SimpleNamespace(stats=stats)))


def test_the_wood_is_to_be_chopped_until_it_has_been_today():
    assert woodhacking_available(_state(None))
    assert woodhacking_available(_state("1400-01-01"))
    assert not woodhacking_available(_state(START_DATE.date().isoformat()))


def test_the_glow_goes_just_behind_the_stump_in_the_queue():
    stump = object()
    sprite = pygame.Surface((40, 30), pygame.SRCALPHA)
    sprite.fill((120, 80, 40, 255), (5, 5, 30, 20))
    queue = [{'sprite': sprite, 'pos': (100, 100), 'y_sort': 5.0},
             {'sprite': sprite, 'pos': (200, 200), 'y_sort': 9.0, 'owner': stump}]
    inject_available_glow_into_queue(queue, stump, SimpleNamespace(zoom=1.0))
    assert len(queue) == 3 and queue[2]['owner'] is stump
    glow = queue[1]
    assert glow['y_sort'] < queue[2]['y_sort']
    assert glow['sprite'].get_width() > sprite.get_width()           # larger, round it
    assert glow['pos'][0] < 200 and glow['pos'][1] < 200


def test_no_stump_in_view_no_glow():
    queue = [{'sprite': pygame.Surface((4, 4)), 'pos': (0, 0), 'y_sort': 1.0}]
    inject_available_glow_into_queue(queue, object(), SimpleNamespace(zoom=1.0))
    assert len(queue) == 1
