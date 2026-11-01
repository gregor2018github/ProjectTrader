"""Game time spent on the map, for the sounds that come now and then (coughs, owls, dogs).

Only game time that passes while the map is shown and running counts: the
game racing through the night on the market screen does not save up sounds
for the player's return, and neither does a jump longer than LONGEST_STEP
between two updates (loading a save).
"""

import datetime
from typing import Optional

LONGEST_STEP = datetime.timedelta(hours=1)


class MapClock:
    """Game hours on the map since it was last asked."""

    def __init__(self) -> None:
        self.last_time: Optional[datetime.datetime] = None

    def hours(self, now: datetime.datetime, running: bool) -> float:
        """Game hours since the last call, if *running* (the map shown and not paused), else 0."""
        last, self.last_time = self.last_time, now
        if not running or last is None:
            return 0.0
        step = now - last
        if step <= datetime.timedelta(0) or step > LONGEST_STEP:
            return 0.0
        return step.total_seconds() / 3600
