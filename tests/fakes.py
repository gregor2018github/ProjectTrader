"""Stand-ins for the game's big objects, holding only what the code under test touches.

They record what they are told (warnings, ledger entries) so tests can check it.
When code under test starts using a new member of the real object, add it here.
"""

import datetime
from types import SimpleNamespace
from typing import List, Optional, Set, Tuple

START_DATE = datetime.datetime(1450, 3, 1, 10, 0)


class FakeGameState:
    """The parts of GameState the models use: the date, the market's booths, warnings and the ledger.

    Every good is sold here and open unless the test says otherwise. `game` is
    None, so the coin sounds and popups of transaction_feedback stay silent.
    """

    def __init__(self, date: datetime.datetime = START_DATE) -> None:
        self.date: datetime.datetime = date
        self.game = None
        self.sold_here: Optional[Set[str]] = None  # None: every good has a booth here
        self.closed: Set[str] = set()              # goods whose booths are shut
        self.warnings: List[str] = []
        self.events: List[Tuple[str, str]] = []
        self.money_feedback: List[Tuple[str, float]] = []  # filled where a test reroutes the coin feedback

    def is_good_sold_here(self, good_name: str) -> bool:
        return self.sold_here is None or good_name in self.sold_here

    def is_good_tradable(self, good_name: str) -> bool:
        return good_name not in self.closed

    def not_sold_here_message(self, good_name: str) -> str:
        return f"{good_name} is not traded at this market."

    def good_closed_message(self, good_name: str) -> str:
        return f"The {good_name} booth is closed."

    def show_warning(self, text: str) -> None:
        self.warnings.append(text)

    def log_event(self, category: str, text: str) -> None:
        self.events.append((category, text))


def fake_warehouse(tmx_id: int = 101, buy_price: int = 500, slots: int = 3, slot_size: int = 30,
                   name: str = "Warehouse_A") -> SimpleNamespace:
    """A buyable warehouse as Depot.buy_warehouse() sees it, without a map behind it."""
    return SimpleNamespace(
        tmx_id=tmx_id, name=name, display_name=None, buy_price=buy_price,
        buy_slots=slots, buy_slot_size=slot_size, buy_storage=slots * slot_size, is_owned=False,
    )
