"""Player statistics — lifetime counters accumulated during a game session.

All fields default to 0 so old saves that lack this section start from scratch
rather than crashing. Increment calls are intentionally fire-and-forget at the
call site (no listeners, no callbacks).
"""

from typing import Any, Dict, Optional


class Statistics:
    """Lifetime counters for a single game session."""

    def __init__(self) -> None:
        # Movement
        self.tiles_walked: float = 0.0          # world pixels / tile_size, accumulated each frame

        # Good trades
        self.goods_bought: int = 0              # successful buy() calls
        self.goods_sold: int = 0                # successful sell() calls
        self.money_received: float = 0.0        # gross revenue from all sales
        self.money_spent_goods: float = 0.0     # gross spend on buying goods (excl. transaction fees)
        self.ledger_entries: int = 0            # GameState.log_event() calls — one per line in the Ledger window

        # Properties & licenses
        self.properties_bought: int = 0         # warehouses (and future buildings) purchased
        self.licenses_acquired: int = 0         # trading licenses granted

        # Finance
        self.loans_taken: int = 0               # take_loan() calls
        self.donations_total: float = 0.0       # cumulative gold donated
        self.overdraft_count: int = 0           # days ending with a negative balance (penalty fired)

        # Minigames
        self.minigames_played: int = 0          # completed minigame sessions (all types)
        self.minigame_income_total: float = 0.0 # cumulative gold earned from minigames
        self.woodhacking_highscore: int = 0     # best score achieved in the woodhacking minigame
        self.last_woodhacking_day: Optional[str] = None  # ISO date (YYYY-MM-DD) last played, gates to once/day

        # Time
        self.days_played: int = 0               # in-game days elapsed this session

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tiles_walked": self.tiles_walked,
            "goods_bought": self.goods_bought,
            "goods_sold": self.goods_sold,
            "money_received": self.money_received,
            "money_spent_goods": self.money_spent_goods,
            "ledger_entries": self.ledger_entries,
            "properties_bought": self.properties_bought,
            "licenses_acquired": self.licenses_acquired,
            "loans_taken": self.loans_taken,
            "donations_total": self.donations_total,
            "overdraft_count": self.overdraft_count,
            "days_played": self.days_played,
            "minigames_played": self.minigames_played,
            "minigame_income_total": self.minigame_income_total,
            "woodhacking_highscore": self.woodhacking_highscore,
            "last_woodhacking_day": self.last_woodhacking_day,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Statistics":
        """Restore from a saved dict; missing keys default to 0 (old saves)."""
        obj = cls()
        obj.tiles_walked = d.get("tiles_walked", 0.0)
        obj.goods_bought = d.get("goods_bought", 0)
        obj.goods_sold = d.get("goods_sold", 0)
        obj.money_received = d.get("money_received", 0.0)
        obj.money_spent_goods = d.get("money_spent_goods", 0.0)
        obj.ledger_entries = d.get("ledger_entries", 0)
        obj.properties_bought = d.get("properties_bought", 0)
        obj.licenses_acquired = d.get("licenses_acquired", 0)
        obj.loans_taken = d.get("loans_taken", 0)
        obj.donations_total = d.get("donations_total", 0.0)
        obj.overdraft_count = d.get("overdraft_count", 0)
        obj.days_played = d.get("days_played", 0)
        obj.minigames_played = d.get("minigames_played", 0)
        obj.minigame_income_total = d.get("minigame_income_total", 0.0)
        obj.woodhacking_highscore = d.get("woodhacking_highscore", 0)
        obj.last_woodhacking_day = d.get("last_woodhacking_day", None)
        return obj
