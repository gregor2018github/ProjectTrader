"""The chickens in the pen: how many there are and how each one looks.

A new game draws FLOCK_SIZE looks at random (chicken_look.random_chicken: head
and tail evenly, the colour by its odds), from a generator seeded by the game's
seed, so every new game has a flock of its own. The looks are saved under
"chickens"; a save without them gets the flock drawn the same way from its
seed on loading, and keeps it from its next save on.

Where the chickens are is not saved: they are put at random spots of their pen
(the "Chickens" rectangle on the Movements layer) whenever the game starts or
is loaded. No pygame.
"""

import random
from dataclasses import dataclass
from typing import Any, List, Optional

from .figurines.animals.chicken_look import COLOURS, HEADS, TAILS, random_chicken

FLOCK_SIZE = 5


@dataclass(frozen=True)
class ChickenLook:
    head: str
    tail: str
    colour: str

    def to_save(self) -> dict:
        return {"head": self.head, "tail": self.tail, "colour": self.colour}

    @classmethod
    def from_save(cls, data: Any) -> Optional["ChickenLook"]:
        """The look saved, or None if it names a part or colour there is not (any more)."""
        if not isinstance(data, dict):
            return None
        head, tail, colour = data.get("head"), data.get("tail"), data.get("colour")
        if head in HEADS and tail in TAILS and colour in COLOURS:
            return cls(head, tail, colour)
        return None


def draw_flock(seed: int, size: int = FLOCK_SIZE) -> List[ChickenLook]:
    """The looks of a flock drawn for a game of this seed: the same seed, the same flock.

    No two chickens of it look the same: a look drawn twice is drawn again (the colours keep their odds)."""
    rng = random.Random(f"chickens/{seed}")
    looks: List[ChickenLook] = []
    while len(looks) < size:
        look = ChickenLook(*random_chicken(rng))
        if look not in looks:
            looks.append(look)
    return looks


class Flock:
    """The looks of the pen's chickens, saved with the game."""

    def __init__(self, looks: Optional[List[ChickenLook]] = None) -> None:
        self.looks: List[ChickenLook] = list(looks or [])

    @classmethod
    def new(cls, seed: int) -> "Flock":
        """A new game's flock."""
        return cls(draw_flock(seed))

    def to_save(self) -> list:
        return [look.to_save() for look in self.looks]

    def load(self, data: Any, seed: int) -> None:
        """The saved flock; a save without one (or with none of it readable) gets one drawn from its seed.

        A look that names a part no longer there is drawn afresh in its place."""
        if not isinstance(data, list) or not data:
            self.looks = draw_flock(seed)
            return
        spare = draw_flock(seed, len(data))
        self.looks = [ChickenLook.from_save(item) or spare[i] for i, item in enumerate(data)]
