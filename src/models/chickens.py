"""The chickens in the pen: who they are, how old, how big, and when one is replaced.

The pen's owner always keeps FLOCK_SIZE chickens. Each is a Hen: a look (head,
tail and colour, chicken_look.random_chicken: head and tail evenly, the colour
by its odds), the day it hatched, the days it will live (LIFESPAN_DAYS, in game
time: a year is 28 days) and the size it grows to (ADULT_SIZE: most near 1,
big and small ones rare). A chick takes ADULT_DAYS to grow up: it starts at
CHICK_SIZE, pale (youth), and grows and takes on its colour as it ages. Once a
hen has lived her days, the owner puts a newly hatched chick in her place
(Flock.update), drawn from the seed and the day she died, so the same game
goes the same way whenever it is played or loaded.

A new game draws its flock from its seed at ages spread over their lives, so
now and then one is still a chick. The flock is saved under "chickens"; a save
without it gets the flock its seed draws, one with only the looks keeps them
and gets the rest drawn. Where the chickens are is not saved. No pygame.
"""

import datetime
import math
import random
from dataclasses import dataclass
from typing import Any, List, Optional

from ..sim.calendar import DAYS_PER_SEASON, DAYS_PER_YEAR, SEASONS
from .figurines.animals.chicken_look import COLOUR_ODDS, COLOURS, HEADS, TAILS, random_chicken

FLOCK_SIZE = 5
#: How long a chicken lives, game days: 2 to 5 years
LIFESPAN_DAYS = (2 * DAYS_PER_YEAR, 5 * DAYS_PER_YEAR)
#: Grown up after half a year (two seasons)
ADULT_DAYS = DAYS_PER_YEAR / 2
#: A chick's size, of the size it grows to
CHICK_SIZE = 0.5
#: The size a chicken grows to, 1 the usual: drawn about 1 by ADULT_SIZE_SPREAD, kept within ADULT_SIZE
ADULT_SIZE = (0.82, 1.2)
ADULT_SIZE_SPREAD = 0.07
#: A new game's flock is up to this share of their lives old
START_AGE_SHARE = 0.9
#: What a grown hen of size 1 weighs; a chicken's weight goes by its size cubed, and a chick's
#: by how far it has grown, from HATCHLING_SHARE of it
ADULT_KG = 2.2
HATCHLING_SHARE = 0.025

# What the player is told when they observe one (observation)
HEAD_NAMES = {"A": "Square, with a double comb", "B": "Square, with a three-spiked comb",
              "D": "Round, with a domed comb and a stubby beak", "E": "Round, with a domed comb",
              "F": "Round, with a notched comb"}
TAIL_NAMES = {"short": "A short tuft", "tall": "Tall and pointed", "fan": "A rounded fan",
              "plume": "A big plume", "sickle": "A curling sickle", "swept": "Low, swept back"}
COLOUR_NAMES = {"buff": "Buff", "white": "White", "black": "Black", "red": "Rust red", "blue": "Blue grey",
                "barred": "Barred", "speckled": "Speckled", "lavender": "Lavender", "mint": "Mint",
                "rose": "Rose", "golden": "Golden", "midnight": "Midnight blue", "lava": "Lava",
                "ghost": "Ghostly white", "rainbow": "Rainbow", "calico": "Calico"}
#: A colour's rarity by its odds in 10,000 (COLOUR_ODDS): the first tier it reaches
RARITY = (("Common", 1500), ("Uncommon", 500), ("Rare", 100), ("Very rare", 20), ("Legendary", 0))
#: Its build by the size it grows to: the first that is at least as big
BUILDS = (("Very large", 1.12), ("Large", 1.05), ("Average", 0.95), ("Smallish", 0.88), ("Small", 0.0))


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


@dataclass(frozen=True)
class Hen:
    """One chicken of the flock: its look, when it hatched, how long it lives and how big it grows."""
    look: ChickenLook
    hatched: datetime.datetime
    lifespan_days: float
    adult_size: float

    def age_days(self, now: datetime.datetime) -> float:
        return max(0.0, (now - self.hatched).total_seconds() / 86400.0)

    @property
    def dies(self) -> datetime.datetime:
        return self.hatched + datetime.timedelta(days=self.lifespan_days)

    def growth(self, now: datetime.datetime) -> float:
        """0 hatched to 1 grown up."""
        return min(1.0, self.age_days(now) / ADULT_DAYS)

    def youth(self, now: datetime.datetime) -> float:
        """How pale its feathers still are: 1 a chick, 0 grown up (its own colour)."""
        return 1.0 - self.growth(now)

    def size(self, now: datetime.datetime) -> float:
        """Its size now, 1 the usual grown chicken: chicks grow fastest at first."""
        return CHICK_SIZE + (self.adult_size - CHICK_SIZE) * math.sqrt(self.growth(now))

    def weight_kg(self, now: datetime.datetime) -> float:
        """What it weighs now: a grown one by its size cubed, a chick from a few dozen grams up."""
        grown = ADULT_KG * self.adult_size ** 3
        return grown * (HATCHLING_SHARE + (1 - HATCHLING_SHARE) * self.growth(now) ** 1.5)

    def stage(self, now: datetime.datetime) -> str:
        """Chick, young hen, hen, or old hen in the last fifth of its days."""
        age = self.age_days(now)
        if age < ADULT_DAYS / 3:
            return "Chick"
        if age < ADULT_DAYS:
            return "Young hen"
        return "Old hen" if age > 0.8 * self.lifespan_days else "Hen"

    def to_save(self) -> dict:
        return {**self.look.to_save(), "hatched": self.hatched.isoformat(),
                "lifespan_days": round(self.lifespan_days, 3), "adult_size": round(self.adult_size, 4)}

    @classmethod
    def from_save(cls, data: Any, spare: "Hen") -> "Hen":
        """The hen saved; what is missing or unreadable taken from `spare` (drawn from the seed)."""
        look = ChickenLook.from_save(data) or spare.look
        if not isinstance(data, dict):
            return spare
        try:
            hatched = datetime.datetime.fromisoformat(data["hatched"])
        except (KeyError, TypeError, ValueError):
            hatched = spare.hatched
        lifespan = data.get("lifespan_days")
        size = data.get("adult_size")
        return cls(look, hatched,
                   float(lifespan) if isinstance(lifespan, (int, float)) and lifespan > 0 else spare.lifespan_days,
                   float(size) if isinstance(size, (int, float)) and size > 0 else spare.adult_size)


def _draw_size(rng: random.Random) -> float:
    return min(max(rng.gauss(1.0, ADULT_SIZE_SPREAD), ADULT_SIZE[0]), ADULT_SIZE[1])


def _draw_look(rng: random.Random, taken: List[ChickenLook]) -> ChickenLook:
    """A look not among `taken`: no two chickens alive look the same (the colours keep their odds)."""
    while True:
        look = ChickenLook(*random_chicken(rng))
        if look not in taken:
            return look


def draw_flock(seed: int, now: datetime.datetime, size: int = FLOCK_SIZE) -> List[Hen]:
    """The flock of a game of this seed starting at `now`, its hens of all ages: the same seed, the same flock."""
    rng = random.Random(f"chickens/{seed}")
    hens: List[Hen] = []
    for _ in range(size):
        look = _draw_look(rng, [hen.look for hen in hens])
        lifespan = rng.uniform(*LIFESPAN_DAYS)
        age = rng.uniform(0.0, START_AGE_SHARE * lifespan)
        hens.append(Hen(look, now - datetime.timedelta(days=age), lifespan, _draw_size(rng)))
    return hens


def hatchling(seed: int, slot: int, hatched: datetime.datetime, others: List[Hen]) -> Hen:
    """The chick put in `slot` when its hen died at `hatched`, drawn from the seed, the slot and the day."""
    rng = random.Random(f"chickens/{seed}/{slot}/{hatched.isoformat()}")
    look = _draw_look(rng, [hen.look for hen in others])
    return Hen(look, hatched, rng.uniform(*LIFESPAN_DAYS), _draw_size(rng))


class Flock:
    """The pen's chickens, saved with the game."""

    def __init__(self, hens: Optional[List[Hen]] = None, seed: int = 0) -> None:
        self.hens: List[Hen] = list(hens or [])
        self.seed = seed

    @property
    def looks(self) -> List[ChickenLook]:
        return [hen.look for hen in self.hens]

    @classmethod
    def new(cls, seed: int, now: datetime.datetime) -> "Flock":
        """A new game's flock."""
        return cls(draw_flock(seed, now), seed)

    def update(self, now: datetime.datetime) -> List[int]:
        """Replace every hen whose days are over by a chick hatched the day she died (again, if that
        chick's days are over too, as after a long time unseen). Returns the slots replaced."""
        replaced = []
        for slot, hen in enumerate(self.hens):
            while hen.dies <= now:
                others = [h for i, h in enumerate(self.hens) if i != slot]
                hen = hatchling(self.seed, slot, hen.dies, others)
                self.hens[slot] = hen
                if slot not in replaced:
                    replaced.append(slot)
        return replaced

    def to_save(self) -> list:
        return [hen.to_save() for hen in self.hens]

    def load(self, data: Any, seed: int, now: datetime.datetime) -> None:
        """The saved flock; a save without one gets the flock its seed draws (as a new game's, at
        `now`). What a saved hen lacks (an older save kept only the looks) is drawn from the seed."""
        self.seed = seed
        spare = draw_flock(seed, now, max(FLOCK_SIZE, len(data) if isinstance(data, list) else 0))
        if not isinstance(data, list) or not data:
            self.hens = spare[:FLOCK_SIZE]
            return
        self.hens = [Hen.from_save(item, spare[i]) for i, item in enumerate(data)]


def rarity(colour: str) -> str:
    """How rare a colour is, in words, by its odds."""
    odds = COLOUR_ODDS.get(colour, 0)
    return next(name for name, least in RARITY if odds >= least)


def build(adult_size: float) -> str:
    return next(name for name, least in BUILDS if adult_size >= least)


def describe_age(days: float) -> str:
    """An age in the calendar's terms: '3 days', '1 season and 2 days', '2 years and 1 season'."""
    whole = int(days)
    if whole < 1:
        return "Hatched today"
    years, rest = divmod(whole, DAYS_PER_YEAR)
    seasons, days_left = divmod(rest, DAYS_PER_SEASON)
    parts = [f"{n} {word if n == 1 else word + 's'}"
             for n, word in ((years, "year"), (seasons, "season"), (days_left, "day")) if n]
    if years:
        parts = parts[:2]                       # a year old: the days no longer matter
    return " and ".join(parts) if len(parts) <= 2 else f"{parts[0]}, {parts[1]} and {parts[2]}"


def describe_weight(kg: float) -> str:
    return f"{round(kg * 1000, -1):.0f} g" if kg < 1 else f"{kg:.1f} kg"


def observation(hen: Hen, now: datetime.datetime) -> List[tuple]:
    """What the player sees of a hen when they observe it: (label, words) lines."""
    look = hen.look
    growing = hen.growth(now) < 1
    return [
        ("Age", f"{describe_age(hen.age_days(now))} old" if hen.age_days(now) >= 1 else "Hatched today"),
        ("Weight", describe_weight(hen.weight_kg(now))),
        ("Build", "Still growing" if growing else build(hen.adult_size)),
        ("Colour", f"{COLOUR_NAMES.get(look.colour, look.colour)} ({rarity(look.colour)})"
                   + (", still pale" if growing and hen.youth(now) > 0.2 else "")),
        ("Head", HEAD_NAMES.get(look.head, look.head)),
        ("Tail", TAIL_NAMES.get(look.tail, look.tail)),
    ]

