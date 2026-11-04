"""Fires the simulation's systems on the calendar's ticks.

A system subscribes a handler to a kind of tick (``calendar.TICK_ORDER``:
price tick, hour, day, week, season, year). ``advance_to()`` walks the clock
from price tick to price tick up to the given moment and, at each, fires every
kind of tick whose number (``calendar.tick_numbers``) changed there, finest
first, each kind's handlers in the order they subscribed. So a moment that is a
new day is first a price tick, then an hour, then a day.

Nothing is fired for the moment the scheduler starts at, or is reset to: a
loaded game goes on from where it was saved without catching up.
"""
import datetime
from typing import Callable, Dict, List

from ..config.constants import PRICE_TICK_MINUTES
from . import calendar
from .calendar import TICK_ORDER

Handler = Callable[[datetime.datetime], None]

_EPOCH_MIDNIGHT = datetime.datetime.combine(calendar.EPOCH, datetime.time())


class Scheduler:
    """Calls subscribed handlers for every tick between where it is and where it is told to go."""

    def __init__(self, now: datetime.datetime) -> None:
        """Start the clock at *now*, firing nothing for it.

        Args:
            now: The simulation's current moment.
        """
        self._handlers: Dict[str, List[Handler]] = {tick: [] for tick in TICK_ORDER}
        self.now: datetime.datetime = now
        self._last: Dict[str, int] = calendar.tick_numbers(now)

    def subscribe(self, tick: str, handler: Handler) -> None:
        """Have *handler(moment)* called on every tick of the given kind.

        Args:
            tick: One of ``calendar.TICK_ORDER``.
            handler: Called with the moment of the tick.

        Raises:
            ValueError: For an unknown kind of tick.
        """
        if tick not in self._handlers:
            raise ValueError(f"unknown tick {tick!r}; expected one of {TICK_ORDER}")
        self._handlers[tick].append(handler)

    def reset(self, now: datetime.datetime) -> None:
        """Put the clock at *now* without firing anything (after loading a save)."""
        self.now = now
        self._last = calendar.tick_numbers(now)

    def advance_to(self, moment: datetime.datetime) -> None:
        """Fire every tick after ``now`` up to and including *moment*, in order.

        Args:
            moment: Where the clock goes; not before ``now``.

        Raises:
            ValueError: If *moment* lies before ``now``.
        """
        if moment < self.now:
            raise ValueError(f"the clock cannot go back from {self.now} to {moment}")
        step = datetime.timedelta(minutes=PRICE_TICK_MINUTES)
        boundary = _EPOCH_MIDNIGHT + (calendar.price_tick_number(self.now) + 1) * step
        while boundary <= moment:
            self._fire(boundary)
            boundary += step
        self.now = moment

    def _fire(self, moment: datetime.datetime) -> None:
        numbers = calendar.tick_numbers(moment)
        last = self._last
        for tick in TICK_ORDER:
            if numbers[tick] != last[tick]:
                for handler in self._handlers[tick]:
                    handler(moment)
        self._last = numbers
