"""Rooms at the inns: booked for a night or a season, and rested in while the booking lasts.

Every tavern (a building with a `Tavern` property, `House.tavern_class`) lets
rooms. Its house menu has "Book a Room" (`ui/helper_modules/room_booking_window.py`),
offering two stays at the tavern's class's prices (`ROOM_PRICES`): a night,
`NIGHT_HOURS` (24) from the moment it is booked, or a season, `DAYS_PER_SEASON`
days, a little cheaper a night. Booking again while a room is still held
lengthens it from where it ends.

While the booking lasts, the house menu also has "Rest": the same clock as at
Uncle Gared's shop, but its hand cannot go past the moment the room must be
given up (`rest_until`), so a night booked and entered ten hours later leaves
fourteen hours to rest. The uncle's shop has no such end.

The bookings are kept on the player (`Player.rooms`: the tavern's Tiled name to
the moment the room is up), saved in the player's block (`to_save`, `from_save`);
those run out are dropped. No pygame here.
"""

import datetime
from typing import Any, Dict, Optional

from ..sim.calendar import DAYS_PER_SEASON

NIGHT = "night"
SEASON = "season"
STAYS = (NIGHT, SEASON)

#: A room's price in coins, by the tavern's class and the stay: a season of seven nights for
#: about six, a night 10, 20 or 50 coins
ROOM_PRICES: Dict[str, Dict[str, int]] = {
    "low": {NIGHT: 10, SEASON: 60},
    "middle": {NIGHT: 20, SEASON: 120},
    "high": {NIGHT: 50, SEASON: 300},
}
NIGHT_HOURS = 24
STAY_LENGTH = {
    NIGHT: datetime.timedelta(hours=NIGHT_HOURS),
    SEASON: datetime.timedelta(days=DAYS_PER_SEASON),
}
STAY_NAMES = {NIGHT: "One night", SEASON: "One season"}


def tavern_key(house: Any) -> str:
    """What a booking is filed under: the tavern's Tiled name."""
    return str(getattr(house, "name", "") or "")


def room_price(tavern_class: str, stay: str) -> int:
    return ROOM_PRICES[tavern_class][stay]


def price_per_night(tavern_class: str, stay: str) -> float:
    return room_price(tavern_class, stay) / (STAY_LENGTH[stay] / datetime.timedelta(hours=NIGHT_HOURS))


def _rooms(player: Any) -> Dict[str, datetime.datetime]:
    rooms = getattr(player, "rooms", None)
    if rooms is None:
        rooms = {}
        player.rooms = rooms
    return rooms


def room_until(player: Any, house: Any, now: datetime.datetime) -> Optional[datetime.datetime]:
    """When the player's room at this tavern is up, or None if they hold none there now."""
    until = _rooms(player).get(tavern_key(house))
    return until if until is not None and until > now else None


def book_room(player: Any, house: Any, stay: str, now: datetime.datetime) -> datetime.datetime:
    """Book (or lengthen) a room for the stay; returns when it is up. Paying is the caller's."""
    rooms = _rooms(player)
    for key in [k for k, until in rooms.items() if until <= now]:
        del rooms[key]                                   # run out
    start = max(now, rooms.get(tavern_key(house), now))
    rooms[tavern_key(house)] = start + STAY_LENGTH[stay]
    return rooms[tavern_key(house)]


def to_save(player: Any) -> Dict[str, str]:
    return {key: until.isoformat() for key, until in _rooms(player).items()}


def from_save(data: Optional[Dict[str, str]]) -> Dict[str, datetime.datetime]:
    """The bookings of a saved player (a save from before the inns' rooms has none)."""
    rooms: Dict[str, datetime.datetime] = {}
    for key, value in (data or {}).items():
        try:
            rooms[str(key)] = datetime.datetime.fromisoformat(value)
        except (TypeError, ValueError):
            continue
    return rooms
