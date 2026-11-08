"""Player statistics — lifetime counters accumulated during a game session.

All fields default to 0 so old saves that lack this section start from scratch
rather than crashing. Increment calls are intentionally fire-and-forget at the
call site (no listeners, no callbacks).
"""

from typing import Any, Dict, List, Optional

from .minigames.fishing_pond import SPECIES

WOODHACKING_TOP_SCORES = 5       # how many of the best sessions are kept


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
        self.donations_total: float = 0.0       # cumulative gold donated, goods given at their value included
        self.goods_donated: int = 0             # units of goods given away (church feasts)
        self.goods_donated_value: float = 0.0   # their market value on the day they were given
        self.overdraft_count: int = 0           # days ending with a negative balance (penalty fired)

        # Minigames
        self.minigames_played: int = 0          # completed minigame sessions (all types)
        self.minigame_income_total: float = 0.0 # cumulative gold earned from minigames
        self.woodhacking_highscore: float = 0   # best score achieved in the woodhacking minigame (streak bonuses make it fractional)
        # The best sessions, best first: "score", "date" (ISO), "streak", "perfects", "blocks"; None for what was not tracked yet
        self.woodhacking_scores: List[Dict[str, Any]] = []
        # Over all sessions, empty until the first tracked one: best_streak, most_perfects, total_perfects, most_blocks, total_blocks
        self.woodhacking_bests: Dict[str, int] = {}
        self.last_woodhacking_day: Optional[str] = None  # ISO date (YYYY-MM-DD) last played, gates to once/day
        self.minigame_tips_seen: List[str] = []  # the minigames' one-time explanations already shown
        self.fishing_highscore: float = 0.0     # the most coins a fishing session brought in
        self.last_fishing_day: Optional[str] = None  # ISO date (YYYY-MM-DD) last fished, gates to once/day
        self.fish_caught: int = 0               # fish landed, all kinds
        self.fishing_records: Dict[str, float] = {}  # the biggest of each kind landed, in cm, by species key
        self.fish_tally: Dict[str, Dict[str, float]] = {}  # per species key: {"count": fish landed, "kg": their weight together}

        # Time
        self.days_played: int = 0               # in-game days elapsed this session

    def record_fish(self, species_key: str, cm: float, kg: float) -> bool:
        """A fish landed goes into the books; whether it is the biggest of its kind so far."""
        self.fish_caught += 1
        tally = self.fish_tally.setdefault(species_key, {"count": 0, "kg": 0.0})
        tally["count"] += 1
        tally["kg"] += kg
        if cm > self.fishing_records.get(species_key, 0):
            self.fishing_records[species_key] = cm
            return True
        return False

    def record_woodhacking(self, score: float, date: str, streak: int, perfects: int, blocks: int) -> None:
        """A finished session of woodhacking goes into the books: ``date`` is its ISO date."""
        self.woodhacking_scores.append({"score": score, "date": date, "streak": streak,
                                        "perfects": perfects, "blocks": blocks})
        self.woodhacking_scores.sort(key=lambda entry: entry["score"], reverse=True)   # stable: the older first on a tie
        del self.woodhacking_scores[WOODHACKING_TOP_SCORES:]
        bests = self.woodhacking_bests
        bests["best_streak"] = max(bests.get("best_streak", 0), streak)
        bests["most_perfects"] = max(bests.get("most_perfects", 0), perfects)
        bests["total_perfects"] = bests.get("total_perfects", 0) + perfects
        bests["most_blocks"] = max(bests.get("most_blocks", 0), blocks)
        bests["total_blocks"] = bests.get("total_blocks", 0) + blocks

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
            "goods_donated": self.goods_donated,
            "goods_donated_value": self.goods_donated_value,
            "overdraft_count": self.overdraft_count,
            "days_played": self.days_played,
            "minigames_played": self.minigames_played,
            "minigame_income_total": self.minigame_income_total,
            "woodhacking_highscore": self.woodhacking_highscore,
            "woodhacking_scores": [dict(entry) for entry in self.woodhacking_scores],
            "woodhacking_bests": dict(self.woodhacking_bests),
            "last_woodhacking_day": self.last_woodhacking_day,
            "minigame_tips_seen": list(self.minigame_tips_seen),
            "fishing_highscore": self.fishing_highscore,
            "last_fishing_day": self.last_fishing_day,
            "fish_caught": self.fish_caught,
            "fishing_records": dict(self.fishing_records),
            "fish_tally": {key: dict(entry) for key, entry in self.fish_tally.items()},
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
        obj.goods_donated = d.get("goods_donated", 0)
        obj.goods_donated_value = d.get("goods_donated_value", 0.0)
        obj.overdraft_count = d.get("overdraft_count", 0)
        obj.days_played = d.get("days_played", 0)
        obj.minigames_played = d.get("minigames_played", 0)
        obj.minigame_income_total = d.get("minigame_income_total", 0.0)
        obj.woodhacking_highscore = d.get("woodhacking_highscore", 0)
        obj.woodhacking_scores = [dict(entry) for entry in d.get("woodhacking_scores", [])]
        obj.woodhacking_bests = dict(d.get("woodhacking_bests", {}))
        # Saves from before the list only know the best score, not its date or what made it up
        if "woodhacking_scores" not in d and obj.woodhacking_highscore > 0:
            obj.woodhacking_scores = [{"score": obj.woodhacking_highscore, "date": None, "streak": None,
                                       "perfects": None, "blocks": None}]
        obj.last_woodhacking_day = d.get("last_woodhacking_day", None)
        obj.minigame_tips_seen = list(d.get("minigame_tips_seen", []))
        obj.fishing_highscore = d.get("fishing_highscore", 0.0)
        obj.last_fishing_day = d.get("last_fishing_day", None)
        obj.fish_caught = d.get("fish_caught", 0)
        obj.fishing_records = dict(d.get("fishing_records", {}))
        obj.fish_tally = {key: dict(entry) for key, entry in d.get("fish_tally", {}).items()}
        # Saves from before the tally only know each kind's biggest: that one, at least, was caught
        for key, cm in obj.fishing_records.items():
            if key not in obj.fish_tally and key in SPECIES:
                obj.fish_tally[key] = {"count": 1, "kg": SPECIES[key].kg(cm)}
        return obj
