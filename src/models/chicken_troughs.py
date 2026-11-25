"""The chicken pen's troughs: what is in each, how full, and how fast the flock gets through it.

A trough is a building of Tiled type "Trough" (models/trough.py draws it). It
is made empty and holds either water or grain, whichever the player puts in
first; it has to run dry, or be tipped out, before it takes the other.

- Water is free: "Pour in Water" fills it to the brim (carried from the well).
  Rain tops up a trough with water in it by RAIN_FILL_PER_HOUR at full rain
  (not an empty one, so it stays free for grain).
- Grain is the player's Wheat: a full trough holds FEED_WHEAT_FULL units, and
  "Fill with Grain" takes as many whole units as it has room for (at least one),
  out of the stock like bread held out to a sheep (Depot.use_goods).

The flock eats and drinks all day: FLOCK_SIZE hens empty a full trough of
grain in FEED_DAYS game days and one of water in WATER_DAYS, if it is the only
one; several troughs of the same share it evenly. A trough that runs dry is
empty again and takes either.

The chickens go to a trough with something in it now and then and peck at it
(chicken.py). With no grain in any trough, or no water, the hens lay far fewer
eggs (chicken_eggs.py); nothing goes hungry for it yet.


Saved under "troughs" by Tiled name: [kind, amount]; a save without it has
them empty. No pygame.
"""

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, List, Optional

WATER = "water"
FEED = "feed"
KINDS = (WATER, FEED)
#: The pictures: empty, then a quarter full to brim full (trough_<kind>_<level>.png)
LEVELS = 4
#: Units of Wheat a full trough holds
FEED_WHEAT_FULL = 2
#: The good its grain is
FEED_GOOD = "Wheat"
#: Game days a full trough lasts a flock of FLOCK_SIZE, as its only one of the kind
FEED_DAYS = 7.0
WATER_DAYS = 4.0
#: The flock the rates above are for (models/chickens.py's)
FLOCK_SIZE = 5
#: How much of a trough rain fills in a game hour at full rain (Weather.rain 1)
RAIN_FILL_PER_HOUR = 0.25
#: A longer jump of the clock than this (a rest, a minigame) is taken as this long
MAX_STEP_DAYS = 30.0
#: Below this, a trough is empty
EMPTY_BELOW = 1e-4


@dataclass
class TroughState:
    kind: Optional[str] = None       # WATER, FEED, or None while empty
    amount: float = 0.0              # 0 empty to 1 brim full

    @property
    def empty(self) -> bool:
        return self.kind is None or self.amount <= EMPTY_BELOW

    @property
    def full(self) -> bool:
        return not self.empty and self.amount >= 1.0 - 1e-6

    def level(self) -> int:
        """The picture's fill: 0 empty, then 1 (a little in it) to LEVELS (full or nearly)."""
        if self.empty:
            return 0
        return max(1, min(LEVELS, math.ceil(self.amount * LEVELS - 1e-6)))

    def picture(self) -> str:
        """The picture's name, without its folder or .png: trough_empty, trough_water_2, ..."""
        level = self.level()
        return "trough_empty" if level == 0 else f"trough_{self.kind}_{level}"

    def takes(self, kind: str) -> bool:
        """Whether `kind` may be put in: when it is empty or holds the same, and has room."""
        return (self.empty or self.kind == kind) and not self.full

    def _settle(self) -> None:
        self.amount = min(1.0, max(0.0, self.amount))
        if self.amount <= EMPTY_BELOW:
            self.kind, self.amount = None, 0.0


def describe_fill(state: TroughState) -> str:
    """How full it looks, in words."""
    if state.empty:
        return "Empty"
    a = state.amount
    words = ("Brim full" if a >= 0.97 else "Nearly full" if a >= 0.75 else "Half full" if a >= 0.4
             else "A little left" if a >= 0.15 else "Almost dry" if state.kind == WATER else "A few grains left")
    return words


def contents_name(state: TroughState) -> str:
    return "Nothing" if state.empty else "Water" if state.kind == WATER else "Grain (wheat)"


def trough_title(state: TroughState) -> str:
    """What it is called while it holds what it holds: its menu's and its sheet's title."""
    return "Empty Trough" if state.empty else "Water Trough" if state.kind == WATER else "Feed Trough"


class Troughs:
    """Every trough of the pen, by its Tiled name."""

    def __init__(self, names: Iterable[str] = ()) -> None:
        self.states: Dict[str, TroughState] = {name: TroughState() for name in names}
        self._last: Optional[datetime] = None

    def __getitem__(self, name: str) -> TroughState:
        return self.states.setdefault(name, TroughState())

    def add(self, names: Iterable[str]) -> None:
        """Make sure every trough on the map has a state (empty if it had none)."""
        for name in names:
            self.states.setdefault(name, TroughState())

    # -- what the player does -----------------------------------------------

    def pour_water(self, name: str) -> bool:
        """Fill it to the brim with water; False if it holds grain or is full already."""
        state = self[name]
        if not state.takes(WATER):
            return False
        state.kind, state.amount = WATER, 1.0
        return True

    def grain_needed(self, name: str) -> int:
        """The whole units of Wheat filling it up takes (at least one while it has room); 0 if it cannot
        take grain."""
        state = self[name]
        if not state.takes(FEED):
            return 0
        room = (1.0 - (0.0 if state.empty else state.amount)) * FEED_WHEAT_FULL
        return max(1, math.ceil(room - 1e-6))

    def add_grain(self, name: str, units: int) -> bool:
        """Put `units` of Wheat in (what does not fit is spilt for the chickens all the same)."""
        state = self[name]
        if units <= 0 or not state.takes(FEED):
            return False
        start = 0.0 if state.empty else state.amount
        state.kind, state.amount = FEED, min(1.0, start + units / FEED_WHEAT_FULL)
        return True

    def tip_out(self, name: str) -> bool:
        """Empty it, so it may take the other; False if it was empty."""
        state = self[name]
        if state.empty:
            return False
        state.kind, state.amount = None, 0.0
        return True

    # -- what the pen's keeper does (npcs/pen_keeper.py) -------------------------

    def holds(self, kind: str) -> bool:
        """Whether any trough has some of `kind` in it (the hens lay less without, chicken_eggs.py)."""
        return any(state.kind == kind and not state.empty for state in self.states.values())

    def empty_ones(self) -> List[str]:

        """The troughs with nothing in them, in name order: what the keeper sees to."""
        return sorted(name for name, state in self.states.items() if state.empty)

    def keeper_kind(self, name: str, preferred: str = FEED) -> str:
        """What the keeper puts into an empty trough: whichever of water and grain no trough holds,
        or, with both held or neither, the trough's own (`preferred`, its Tiled ``Keeper_fills``)."""
        held = {state.kind for other, state in self.states.items() if other != name and not state.empty}
        missing = [kind for kind in KINDS if kind not in held]
        return missing[0] if len(missing) == 1 else preferred

    def keeper_fill(self, name: str, preferred: str = FEED) -> Optional[str]:
        """The keeper fills an empty trough to the brim, from his own water and grain (no Wheat of
        the player's); the kind he filled it with, or None if it was not empty."""
        state = self[name]
        if not state.empty:
            return None
        kind = self.keeper_kind(name, preferred)
        state.kind, state.amount = kind, 1.0
        return kind

    # -- the flock and the weather ------------------------------------------

    def days_left(self, name: str, hens: int) -> Optional[float]:
        """Game days until it runs dry at the flock's pace (rain not counted); None if empty or no hens."""
        state = self[name]
        if state.empty or hens <= 0:
            return None
        return state.amount / self._rate(state.kind, hens)

    def _rate(self, kind: str, hens: int) -> float:
        """How much of a trough of `kind` the flock gets through a day, shared out among those holding it."""
        sharing = sum(1 for s in self.states.values() if not s.empty and s.kind == kind) or 1
        days = FEED_DAYS if kind == FEED else WATER_DAYS
        return hens / FLOCK_SIZE / days / sharing

    def update(self, now: datetime, hens: int, rain: float = 0.0) -> bool:
        """Let the flock eat and drink, and the rain fall in, from the last update to `now`.

        Returns:
            True if any trough's picture changed.
        """
        if self._last is None or now <= self._last:
            self._last = now if self._last is None else max(self._last, now)
            return False
        days = min(MAX_STEP_DAYS, (now - self._last).total_seconds() / 86400.0)
        self._last = now
        before = {name: state.picture() for name, state in self.states.items()}
        rates = {kind: self._rate(kind, hens) for kind in KINDS}
        for state in self.states.values():
            if not state.empty:
                state.amount -= rates[state.kind] * days
                state._settle()
            if rain > 0 and not state.empty and state.kind == WATER:
                state.amount += rain * RAIN_FILL_PER_HOUR * days * 24.0
                state._settle()
        return any(state.picture() != before[name] for name, state in self.states.items())

    def restart(self, now: datetime) -> None:
        """Count from `now` on (after loading a save)."""
        self._last = now

    # -- the save -------------------------------------------------------------

    def to_save(self) -> Dict[str, List]:
        return {name: [state.kind, round(state.amount, 5)] for name, state in self.states.items()}

    def load(self, data) -> None:
        """A save's troughs; one without them has every trough empty."""
        for state in self.states.values():
            state.kind, state.amount = None, 0.0
        for name, entry in (data or {}).items():
            try:
                kind, amount = entry
                state = self[str(name)]
                state.kind = kind if kind in KINDS else None
                state.amount = float(amount)
                state._settle()
            except (TypeError, ValueError):
                continue
        self._last = None
