"""What the simulation reports: events put on a queue for the game to read.

The simulation never calls into the game or its UI. When something happens
that the game may want to show or log, a system pushes an event here, and the
game drains the queue (``Simulation.events.drain()``) once a frame. A headless
run may simply let them go.
"""
import datetime
from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class SimEvent:
    """Something that happened in the simulation, and when."""
    when: datetime.datetime


@dataclass(frozen=True)
class PriceShockEnded(SimEvent):
    """A well wish's price shock ran out: the good's corridor is back where it was."""
    good: str


@dataclass(frozen=True)
class PopulationChanged(SimEvent):
    """The town's head count changed at the daily migration."""
    old_total: int
    new_total: int


class EventQueue:
    """Events in the order they happened, until the game takes them."""

    def __init__(self, limit: int = 1000) -> None:
        """Args:
            limit: The most events kept; the oldest go first, so an unread queue stays small.
        """
        self._events: List[SimEvent] = []
        self._limit = limit

    def push(self, event: SimEvent) -> None:
        self._events.append(event)
        if len(self._events) > self._limit:
            del self._events[: len(self._events) - self._limit]

    def drain(self) -> List[SimEvent]:
        """Every event not yet taken, oldest first; the queue is empty afterwards."""
        events, self._events = self._events, []
        return events

    def __len__(self) -> int:
        return len(self._events)


@dataclass(frozen=True)
class CapacityChanged(SimEvent):
    """A workshop grew (it was busy and could pay) or shrank (it kept losing money)."""
    workshop: str
    old_capacity: float
    new_capacity: float
