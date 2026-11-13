"""The player's silhouette: shown when scenery in front hides him, faded in and out."""

import pygame
import pytest

from src.models import player_silhouette as ps
from src.models.player_silhouette import PlayerSilhouette


class _Player:
    y_sort = 100.0


class _Walker:
    """Another figure: has a sprite getter, as Figurine does."""
    def _get_scaled_sprite(self, zoom):
        return None


def _solid(w, h):
    surface = pygame.Surface((w, h), pygame.SRCALPHA)
    surface.fill((10, 20, 30, 255))
    return surface


def _queue(player, cover_width, cover_y_sort=200.0, flags=0, owner=None):
    queue = [{'sprite': _solid(10, 20), 'pos': (50, 50), 'y_sort': player.y_sort, 'owner': player}]
    cover = {'sprite': _solid(cover_width, 20), 'pos': (50, 50), 'y_sort': cover_y_sort}
    if flags:
        cover['flags'] = flags
    if owner is not None:
        cover['owner'] = owner
    queue.append(cover)
    return queue


def test_hidden_share_counts_scenery_in_front():
    player = _Player()
    assert PlayerSilhouette().hidden_share(_queue(player, 10), player) == pytest.approx(1.0)
    assert PlayerSilhouette().hidden_share(_queue(player, 5), player) == pytest.approx(0.5)


def test_lights_figures_behind_and_own_splashes_do_not_hide():
    player = _Player()
    sil = PlayerSilhouette()
    assert sil.hidden_share(_queue(player, 10, flags=pygame.BLEND_ADD), player) == 0.0
    assert sil.hidden_share(_queue(player, 10, owner=_Walker()), player) == 0.0
    assert sil.hidden_share(_queue(player, 10, cover_y_sort=player.y_sort + 0.01), player) == 0.0


def test_not_in_view_is_not_hidden():
    assert PlayerSilhouette().hidden_share([], _Player()) == 0.0


def test_fades_in_while_hidden_and_out_after():
    player = _Player()
    sil = PlayerSilhouette()
    hidden, clear = _queue(player, 10), _queue(player, 2)
    delay_ms = round(ps.SILHOUETTE_DELAY_S * 1000)
    for t in range(0, delay_ms + 1, 100):
        sil.update(hidden, player, now_ms=t)
    assert sil.alpha == 0.0                     # still waiting
    sil.update(hidden, player, now_ms=delay_ms + 100)
    assert sil.alpha == pytest.approx(ps.SILHOUETTE_FADE_IN_PER_S * 0.1)
    for t in range(delay_ms + 200, delay_ms + 1200, 100):
        sil.update(hidden, player, now_ms=t)
    assert sil.alpha == 1.0
    sil.update(clear, player, now_ms=delay_ms + 1300)
    assert sil.alpha == pytest.approx(1.0 - ps.SILHOUETTE_FADE_OUT_PER_S * 0.1)


def test_passing_behind_briefly_shows_nothing():
    player = _Player()
    sil = PlayerSilhouette()
    hidden, clear = _queue(player, 10), _queue(player, 2)
    half = round(ps.SILHOUETTE_DELAY_S * 500)
    for t in range(0, half + 1, 50):
        sil.update(hidden, player, now_ms=t)
    sil.update(clear, player, now_ms=half + 50)   # out again: the wait starts over
    for t in range(half + 100, 2 * half + 101, 50):
        sil.update(hidden, player, now_ms=t)
    assert sil.alpha == 0.0


def test_partly_hidden_shows_nothing():
    player = _Player()
    sil = PlayerSilhouette()
    for t in range(0, 1000, 100):
        sil.update(_queue(player, 8), player, now_ms=t)   # 80 %, under SILHOUETTE_FROM
    assert sil.alpha == 0.0


def test_draws_a_faint_outline_round_him():
    player = _Player()
    sil = PlayerSilhouette()
    sil.alpha = 1.0
    sil.hidden_share(_queue(player, 10), player)
    screen = pygame.Surface((200, 200))
    screen.fill((0, 0, 0))
    sil.draw(screen, zoom=1.0)
    edge = screen.get_at((49, 60))       # just left of the sprite: the outline
    inside = screen.get_at((55, 60))     # inside: the fainter fill
    assert 0 < inside.r < edge.r < 255


def test_dimmer_at_night():
    player = _Player()
    def edge(light):
        sil = PlayerSilhouette()
        sil.alpha = 1.0
        sil.hidden_share(_queue(player, 10), player)
        screen = pygame.Surface((200, 200))
        screen.fill((0, 0, 0))
        sil.draw(screen, zoom=1.0, light=light)
        return screen.get_at((49, 60)).r
    day, night = edge((255, 255, 255)), edge((40, 50, 90))
    assert 0 < night < day
    assert day == edge(None)
