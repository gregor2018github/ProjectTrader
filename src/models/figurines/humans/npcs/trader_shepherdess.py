"""The shepherdess, who sells the wool of her flock at the Wool & Hide Market.

She shares the one stall with the weaver and the tanner and the three of them
take turns at it, so she names the weaver's shapes on the Tiled "Movements"
layer: the same walk around the stall, the same way home, and the same door
for whichever of them the rota sends out that morning.

While her black sheep Flip is lost (lost_sheep.py) she keeps the fold
instead, every day from the morning she finds him gone to the day she has
thanked the player for bringing him back: the rota passes her over
(``kept_away``), and she walks from her door through the fold's gate, opening
and shutting it behind her, to her round in it (the ``Shepherdess_Fold``
polygon, ``set_fold``), where she stands about as at a stall, and home again
in the evening, by the daylight (``FOLD_OUT_WINDOW``, ``FOLD_IN_WINDOW``). She
changes between the two only while indoors, or while the map is not shown.
Which days are fold days the game tells her (``keeps_fold``).

Otherwise all of her behaviour comes from :class:`~.trader.Trader`.
"""

import datetime
import random
from typing import Callable, Optional, Tuple

from ....daylight import sun_hour
from ...patrol_path import PatrolPath
from .trader import AT_HOME, Trader

#: When she goes out to the fold and comes home from it, in sun hours (daylight.sun_hour), drawn daily
FOLD_OUT_WINDOW = (6.0, 7.5)
FOLD_IN_WINDOW = (19.0, 20.5)


class TraderShepherdess(Trader):
    """A shepherdess who sells wool at the market, and keeps her flock while one of it is lost."""

    SPRITE_FOLDER = 'trader_shepherdess'
    SPRITE_PREFIX = 'shepherdess'
    DEFAULT_NAME = "Shepherdess"
    # Shares the weaver's stall and takes turns at it (see StallRota).
    TILED_PREFIX = "Weaver"
    MARKET_NAME = "Wool & Hide Market"
    # Tends the sheep out on the pastures: plain country folk.
    SOCIAL_CLASS = "Commons"
    GENDER = "female"

    def __init__(self, x: float, y: float, tile_size: int, name: Optional[str] = None) -> None:
        super().__init__(x, y, tile_size, name)
        #: Her round in the fold and her way between it and her door; None if the map has none
        self.fold_round: Optional[PatrolPath] = None
        self.fold_way: Optional[PatrolPath] = None
        #: Whether she keeps the fold on a day; set by the game (LostSheep.on_meadow)
        self.keeps_fold: Callable[[datetime.date], bool] = lambda day: False
        #: Whether she is about the fold rather than the stall now
        self.at_fold: bool = False
        # Her stall's paths, put by while she keeps the fold
        self._stall_post: Optional[Tuple[PatrolPath, PatrolPath, float]] = None
        self._fold_day: Optional[datetime.date] = None
        self._fold_hours: Tuple[float, float] = (FOLD_OUT_WINDOW[0], FOLD_IN_WINDOW[1])

    def set_fold(self, fold_round: PatrolPath, fold_way: PatrolPath) -> None:
        """Her round in the fold, and the way from it to her door (which ends where her way home does)."""
        self.fold_round = fold_round
        self.fold_way = fold_way

    @property
    def passes_gates(self) -> bool:
        return self.at_fold

    def kept_away(self, current_time: datetime.datetime) -> bool:
        return self.fold_round is not None and self.keeps_fold(current_time.date())

    def is_at_stall(self, current_time: datetime.datetime) -> bool:
        return False if self.at_fold else super().is_at_stall(current_time)

    def _off_duty(self, current_time: datetime.datetime) -> bool:
        if not self.at_fold:
            return super()._off_duty(current_time)
        if self._fold_day != current_time.date():
            self._fold_day = current_time.date()
            self._fold_hours = (random.uniform(*FOLD_OUT_WINDOW), random.uniform(*FOLD_IN_WINDOW))
        out_at, in_at = self._fold_hours
        return not (out_at <= sun_hour(current_time) < in_at)

    def _move_post(self, to_fold: bool) -> None:
        """Change between the stall and the fold: the paths she walks, and her place at home."""
        self._leave_gate()
        if to_fold:
            self._stall_post = (self.stall_path, self.homeway, self.stall_exit_distance)
            self.stall_path, self.homeway = self.fold_round, self.fold_way
            self.stall_exit_distance = self.fold_round.closest_distance(self.fold_way.points[0])
        elif self._stall_post is not None:
            self.stall_path, self.homeway, self.stall_exit_distance = self._stall_post
            self._stall_post = None
        self.at_fold = to_fold
        self.stop()
        if self.state == AT_HOME and self.homeway is not None:
            # Behind the same door either way: only her way out of it is another
            self.set_path(self.homeway, self.homeway.length)

    def update(self, dt: float, current_time: datetime.datetime) -> None:
        if self.fold_round is not None and self.talking_to is None:
            wanted = self.keeps_fold(current_time.date())
            if wanted != self.at_fold and (self.state == AT_HOME or self._is_unseen(current_time)):
                self._move_post(wanted)
        super().update(dt, current_time)

    def inspect_lines(self, observer=None):
        lines = super().inspect_lines(observer)
        if self.fold_round is not None:
            where = "the fold (lost sheep)" if self.at_fold else "her stall"
            lines.append(f"Keeps: {where}")
        return lines
