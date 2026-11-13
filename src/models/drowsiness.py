"""What it does to the player to be worn out: from `TIRED_FROM` (80 %) of tiredness on.

Below that, tiredness does nothing (models/rest.py counts it). From there to
fully worn out, `fatigue` runs from 0 to 1, and with it:

- `penalty`: from `PENALTY_MIN` to `PENALTY_MAX`, the share the walk is slowed
  by and the minigames are made worse by: the woodhacking's swings earn that
  much fewer points, and a fish holds a taken bait that much shorter and the
  fight's bar is that much smaller.
- the view narrows (`Drowsiness`, `view_share`): the map darkens round the player
  from the edges in, the clear part shrinking from `VIEW_WIDE` to `VIEW_NARROW`
  of the view, and now and then (`BLINKS_PER_MINUTE`, more the more tired) the
  eyes fall shut for a moment and open again, the clear part closing to a slit
  (`LID_SHUT`) for `SHUT_S` and opening slower than it closed.

`Drowsiness` keeps the eyes, in real seconds, on its own random generator (it
is not the simulation's and nothing of it is saved). No pygame here; the map
view draws it (ui/layout_modules/drowsy_view.py) and the effect circles name it.
"""

import random
from typing import Optional, Tuple

#: Tiredness from which being worn out shows
TIRED_FROM = 0.8
#: The penalty at `TIRED_FROM` and at full tiredness
PENALTY_MIN = 0.05
PENALTY_MAX = 0.25
#: The clear part of the view (its radius, a share of half the view's diagonal), from `TIRED_FROM` to worn out
VIEW_WIDE = 0.95
VIEW_NARROW = 0.42
#: Eyes falling shut: how often a minute, from `TIRED_FROM` to worn out
BLINKS_PER_MINUTE = (0.6, 4.0)
#: Closing, held shut (from, to: longer the more tired) and opening again, in seconds
CLOSE_S = 0.35
SHUT_S = ((0.25, 0.6), (0.6, 1.4))
OPEN_S = 0.7
#: How far open the eyes are while shut, and how narrow the clear part then is
LID_SHUT = 0.06
SHUT_NARROWS = 0.55

OPEN, CLOSING, SHUT, OPENING = "open", "closing", "shut", "opening"


def fatigue(tiredness: float) -> float:
    """0 below `TIRED_FROM`, rising to 1 when worn out."""
    return max(0.0, min(1.0, (tiredness - TIRED_FROM) / (1.0 - TIRED_FROM)))


def is_tired(tiredness: float) -> bool:
    return tiredness >= TIRED_FROM


def penalty(tiredness: float) -> float:
    """The share the walk is slowed and the minigames worsened by: 0 while not tired."""
    if not is_tired(tiredness):
        return 0.0
    return PENALTY_MIN + (PENALTY_MAX - PENALTY_MIN) * fatigue(tiredness)


def player_penalty(player: object) -> float:
    return penalty(getattr(player, "tiredness", 0.0) or 0.0)


def game_penalty(game: object) -> float:
    """`penalty` for the game's player; 0 for a game without one (a minigame's demo)."""
    return player_penalty(getattr(game, "player", None))


def view_share(tiredness: float) -> float:
    """The clear part's radius with the eyes open, as a share of half the view's diagonal."""
    return VIEW_WIDE + (VIEW_NARROW - VIEW_WIDE) * fatigue(tiredness)


def _lerp(pair: Tuple[float, float], t: float) -> float:
    return pair[0] + (pair[1] - pair[0]) * t


def _smooth(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


class Drowsiness:
    """The player's eyes while worn out: open, now and then falling shut (see the module)."""

    def __init__(self, rng: Optional[random.Random] = None) -> None:
        self.rng = rng or random.Random()
        self.stage = OPEN
        self.stage_t = 0.0        # seconds into the stage
        self.shut_for = 0.0       # how long this blink stays shut

    def update(self, dt: float, tiredness: float) -> None:
        """`dt` real seconds on, while the map is shown and the game runs."""
        f = fatigue(tiredness)
        if not is_tired(tiredness):
            self.stage, self.stage_t = OPEN, 0.0
            return
        self.stage_t += dt
        if self.stage == OPEN:
            per_second = _lerp(BLINKS_PER_MINUTE, f) / 60.0
            if self.rng.random() < per_second * dt:
                self.stage, self.stage_t = CLOSING, 0.0
                low, high = _lerp((SHUT_S[0][0], SHUT_S[1][0]), f), _lerp((SHUT_S[0][1], SHUT_S[1][1]), f)
                self.shut_for = self.rng.uniform(low, high)
        elif self.stage == CLOSING and self.stage_t >= CLOSE_S:
            self.stage, self.stage_t = SHUT, 0.0
        elif self.stage == SHUT and self.stage_t >= self.shut_for:
            self.stage, self.stage_t = OPENING, 0.0
        elif self.stage == OPENING and self.stage_t >= OPEN_S:
            self.stage, self.stage_t = OPEN, 0.0

    @property
    def lid(self) -> float:
        """How far open the eyes are: 1 open, `LID_SHUT` shut."""
        if self.stage == CLOSING:
            closed = _smooth(self.stage_t / CLOSE_S)
        elif self.stage == SHUT:
            closed = 1.0
        elif self.stage == OPENING:
            closed = 1.0 - _smooth(self.stage_t / OPEN_S)
        else:
            closed = 0.0
        return 1.0 - (1.0 - LID_SHUT) * closed

    def view(self, tiredness: float) -> Optional[Tuple[float, float]]:
        """The clear part's half width and half height, as shares of half the view's diagonal;
        None while not tired (nothing to draw)."""
        if not is_tired(tiredness):
            return None
        share = view_share(tiredness)
        lid = self.lid
        shut = (1.0 - lid) / (1.0 - LID_SHUT)        # 0 open to 1 shut
        width = share * (1.0 - (1.0 - SHUT_NARROWS) * shut)
        return width, share * lid
