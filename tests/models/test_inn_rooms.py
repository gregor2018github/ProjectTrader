"""Rooms at the inns: the prices, a night or a season from booking, lengthening, and the save."""

import datetime
from types import SimpleNamespace

from src.models import inn_rooms
from src.models.inn_rooms import NIGHT, ROOM_PRICES, SEASON, book_room, price_per_night, room_until
from src.models.player import Player
from src.models.rest import can_rest_until, default_end, latest_end, snap_end

NOW = datetime.datetime(1500, 1, 8, 14, 7)
INN = SimpleNamespace(name="House_28", tavern_class="low")
OTHER = SimpleNamespace(name="House_9", tavern_class="middle")


def test_the_prices_and_a_season_cheaper_a_night():
    assert ROOM_PRICES == {"low": {NIGHT: 10, SEASON: 60}, "middle": {NIGHT: 20, SEASON: 120},
                           "high": {NIGHT: 50, SEASON: 300}}
    for tavern_class, prices in ROOM_PRICES.items():
        assert price_per_night(tavern_class, SEASON) < prices[NIGHT]


def test_a_night_lasts_24_hours_and_a_season_7_days_from_booking():
    player = Player("p", 0)
    assert room_until(player, INN, NOW) is None
    assert book_room(player, INN, NIGHT, NOW) == NOW + datetime.timedelta(hours=24)
    assert room_until(player, INN, NOW) == NOW + datetime.timedelta(hours=24)
    assert room_until(player, OTHER, NOW) is None
    assert book_room(player, OTHER, SEASON, NOW) == NOW + datetime.timedelta(days=7)
    assert room_until(player, INN, NOW + datetime.timedelta(hours=24)) is None


def test_booking_again_lengthens_the_stay_from_its_end():
    player = Player("p", 0)
    book_room(player, INN, NIGHT, NOW)
    later = NOW + datetime.timedelta(hours=10)
    assert book_room(player, INN, NIGHT, later) == NOW + datetime.timedelta(hours=48)
    # Once it has run out, a new booking starts from the moment it is made
    much_later = NOW + datetime.timedelta(days=5)
    assert book_room(player, INN, NIGHT, much_later) == much_later + datetime.timedelta(hours=24)


def test_entering_ten_hours_into_a_night_leaves_fourteen_hours_to_rest():
    player = Player("p", 0)
    until = book_room(player, INN, NIGHT, NOW)
    later = NOW + datetime.timedelta(hours=10)
    assert latest_end(later, until) == until
    assert snap_end(later, later + datetime.timedelta(hours=20), until) == until
    assert (until - later) == datetime.timedelta(hours=14)
    assert default_end(later, until) <= until
    assert latest_end(later) > until                         # the uncle's shop has no such end


def test_no_rest_with_less_than_a_step_left():
    until = NOW + datetime.timedelta(minutes=5)
    assert not can_rest_until(NOW, until)
    assert can_rest_until(NOW, NOW + datetime.timedelta(minutes=30))
    assert can_rest_until(NOW, None)


def test_the_save_keeps_the_bookings():
    player = Player("p", 0)
    book_room(player, INN, SEASON, NOW)
    saved = inn_rooms.to_save(player)
    assert inn_rooms.from_save(saved) == player.rooms
    assert inn_rooms.from_save(None) == {}
