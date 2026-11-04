"""The merchant's rank: a ladder of titles the player climbs and can fall down again.

Each rank of MERCHANT_RANKS asks for four things at once: net wealth, property
value, lifetime trade volume and reputation. Once a day (`daily_check`) the
player rises at once to the highest rank all four allow. When the rank held
stops being met, the player has RANK_GRACE_DAYS to put it right before falling
back one rank (and then again, if that one is not met either).

What a rank opens (RANK_UNLOCKS) follows the highest rank ever reached, so it is
never taken away; bonuses that follow the rank held can be added on `level`.

Reputation is the player's (`Player.reputation`). For now only gifts raise it:
a gift is measured against the giver's wealth, and the more given in a season
the less each coin adds, so a rich man has to give a great deal to be thought
well of. It fades by REPUTATION_SEASONAL_DECAY at the start of every season.
"""

import datetime
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from ..config.constants import (
    DONATION_REPUTATION_SCALE, DONATION_REPUTATION_WEALTH_FLOOR, MERCHANT_RANKS,
    RANK_GRACE_DAYS, RANK_UNLOCKS, REPUTATION_SEASONAL_DECAY,
)

CONDITIONS = ("wealth", "property_value", "volume", "reputation")
CONDITION_LABELS = {
    "wealth": "Net wealth",
    "property_value": "Property value",
    "volume": "Trade volume",
    "reputation": "Reputation",
}
UNLOCK_TEXTS = {                 # how each of RANK_UNLOCKS reads after "you may now"
    "buy_buildings": "buy buildings",
}


@dataclass(frozen=True)
class Rank:
    name: str
    wealth: float
    property_value: float
    volume: float
    reputation: float

    def unmet(self, standing: Dict[str, float]) -> List[str]:
        """The conditions of this rank the standing falls short of, in CONDITIONS order."""
        return [c for c in CONDITIONS if standing[c] < getattr(self, c)]


def ranks() -> List[Rank]:
    return [Rank(*row) for row in MERCHANT_RANKS]


def rank_index(name: str) -> int:
    return [rank.name for rank in ranks()].index(name)


def format_amount(condition: str, value: float) -> str:
    if condition == "reputation":
        return f"{value:,.1f}"
    return f"{value:,.0f}"


class MerchantRank:
    """The rank the player holds, the highest reached, and the grace period of a slipping one."""

    def __init__(self, depot: Any, player: Any, goods: List[Any]) -> None:
        self.depot = depot
        self.player = player
        self.goods = goods
        self.ranks: List[Rank] = ranks()
        self.level: int = 0                                  # index of the rank held
        self.highest: int = 0                                # index of the highest rank ever held
        self.grace_since: Optional[datetime.date] = None     # when the rank held stopped being met
        self.given_this_season: float = 0.0                   # gifts so far this season, for their falling worth

    @property
    def rank(self) -> Rank:
        return self.ranks[self.level]

    @property
    def next_rank(self) -> Optional[Rank]:
        return self.ranks[self.level + 1] if self.level + 1 < len(self.ranks) else None

    def standing(self) -> Dict[str, float]:
        """What the player has of each condition right now."""
        return {
            "wealth": self.depot.net_wealth(self.goods),
            "property_value": self.depot.get_property_value(),
            "volume": self.depot.trade_volume(),
            "reputation": self.player.reputation,
        }

    def qualified_level(self, standing: Dict[str, float]) -> int:
        """The highest rank the standing meets every condition of (the first always)."""
        for index in range(len(self.ranks) - 1, 0, -1):
            if not self.ranks[index].unmet(standing):
                return index
        return 0

    def has_unlocked(self, unlock: str) -> bool:
        return self.highest >= rank_index(RANK_UNLOCKS[unlock])

    def grace_days_left(self, today: datetime.date) -> Optional[int]:
        if self.grace_since is None:
            return None
        return max(0, RANK_GRACE_DAYS - (today - self.grace_since).days)

    # DAILY AND SEASONAL

    def daily_check(self, today: datetime.date) -> Optional[Tuple[str, str]]:
        """Promote, warn or demote; returns (ledger line, message to show) when something happened."""
        standing = self.standing()
        qualified = self.qualified_level(standing)
        if qualified > self.level:
            opened = [UNLOCK_TEXTS[unlock] for unlock, name in RANK_UNLOCKS.items()
                      if self.highest < rank_index(name) <= qualified]
            self.level = qualified
            self.highest = max(self.highest, qualified)
            self.grace_since = None
            name = self.rank.name
            message = f"The town now speaks of you as a **{name}**."
            if opened:
                message += f"\nAs a {name} you may now {' and '.join(opened)}."
            return f"Risen to the rank of {name}", message

        unmet = self.rank.unmet(standing)
        if not unmet:
            if self.grace_since is not None:
                self.grace_since = None
                return (f"Standing as {self.rank.name} secured again", "")
            return None

        if self.grace_since is None:
            self.grace_since = today
            return (f"Standing as {self.rank.name} slipping: {', '.join(CONDITION_LABELS[c] for c in unmet)}",
                    self._slipping_message(standing, unmet))

        if (today - self.grace_since).days < RANK_GRACE_DAYS:
            return None

        fallen_from = self.rank.name
        self.level -= 1
        # Falling further takes another grace period of its own
        self.grace_since = today if self.rank.unmet(standing) else None
        return (f"Fallen from {fallen_from} to {self.rank.name}",
                f"You are no longer counted a {fallen_from}.\n"
                f"The town now speaks of you as a **{self.rank.name}**.")

    def _slipping_message(self, standing: Dict[str, float], unmet: List[str]) -> str:
        lines = "\n".join(
            f"**  - {CONDITION_LABELS[c]}: {format_amount(c, standing[c])} of "
            f"{format_amount(c, getattr(self.rank, c))}**"
            for c in unmet
        )
        return (f"Your standing as a {self.rank.name} is slipping:\n{lines}\n"
                f"Put it right within {RANK_GRACE_DAYS} days, or you will fall back "
                f"to {self.ranks[self.level - 1].name}.")

    def new_season(self) -> None:
        """Let the reputation fade, and start counting this season's gifts afresh."""
        self.player.reputation *= 1.0 - REPUTATION_SEASONAL_DECAY
        self.given_this_season = 0.0

    # REPUTATION

    def reputation_for_gift(self, amount: float, paid: bool = False) -> float:
        """The reputation a gift of this size earns; `paid` if it has already left the purse.

        All of a season's gifts are measured together against what the giver was
        worth before them, W (net wealth or money, whichever is more, plus this
        season's gifts; at least DONATION_REPUTATION_WEALTH_FLOOR), and earn
        SCALE * ln(1 + given / W): each coin is worth less than the one before
        it, and giving away as much as one had earns SCALE * ln 2.
        """
        if amount <= 0:
            return 0.0
        before = self.given_this_season
        wealth = max(self.depot.net_wealth(self.goods), self.depot.money) + before + (amount if paid else 0.0)
        wealth = max(DONATION_REPUTATION_WEALTH_FLOOR, wealth)
        return DONATION_REPUTATION_SCALE * (math.log1p((before + amount) / wealth) - math.log1p(before / wealth))

    def record_gift(self, amount: float) -> float:
        """Credit the reputation of a gift that has just been paid; returns what it earned."""
        gain = self.reputation_for_gift(amount, paid=True)
        self.given_this_season += amount
        self.player.change_reputation(gain)
        return gain

    # SAVING

    def to_save(self) -> Dict[str, Any]:
        return {
            "level": self.level,
            "highest": self.highest,
            "grace_since": self.grace_since.isoformat() if self.grace_since else None,
            "given_this_season": self.given_this_season,
        }

    def load(self, saved: Optional[Dict[str, Any]]) -> None:
        """Take over a save's rank; a save without one starts at the first rank and rises on the next day."""
        saved = saved or {}
        top = len(self.ranks) - 1
        self.level = min(max(int(saved.get("level", 0)), 0), top)
        self.highest = min(max(int(saved.get("highest", self.level)), self.level), top)
        grace = saved.get("grace_since")
        self.grace_since = datetime.date.fromisoformat(grace) if grace else None
        self.given_this_season = float(saved.get("given_this_season", saved.get("given_this_month", 0.0)))
