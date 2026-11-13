"""What a meal at a tavern does for the player for some hours after it.

Every dish gives one effect (`effect_kind`), decided by its course and whether it
has meat, so the 83 dishes of dishes.csv need no hand-tuning:

- a main dish with meat: Strong Hand, more points for every swing at the woodhacking;
- a main dish without meat, a pottage or bread and sides: Well Fed, the player tires
  more slowly;
- a sweet: Light Step, the player walks faster;
- a drink: Steady Hand, a fish that has taken the bait holds on to it longer before
  it spits it out, so there is more time to strike (graded as a late strike: the
  extra time is only a second chance, not an easier perfect one).

How strong it is follows the price (`effect_strength`), on a log scale from
`STRENGTH_MIN` for the cheapest dish (`PRICE_FLOOR`) to `STRENGTH_MAX` (15 %) for the
dearest (`PRICE_CEILING`): a rye bread gives 2 %, a mid tavern's roast about 9 %,
only the high tavern's grandest mains come near 15 %. Strong Hand never comes on a
fast day, as no meat is served then.

How long it lasts (`meal_hours`) is `MEAL_HOURS_MIN` (6) to `MEAL_HOURS_MAX` (12) hours
of game time: mostly by how filling its course is (`COURSE_STAYING`: a main dish
the longest, a drink the shortest), then by its price, and a little by the dish
itself (`_dish_variation`, the same for a dish every time), in half hours.

The player has one meal's effect at a time (`Player.meal`, saved): a new dish
replaces whatever the last one gave, the same dish again starts its hours afresh.
No pygame here.
"""

import datetime
import math
import zlib
from dataclasses import dataclass
from typing import Any, Dict, Optional

STRONG_HAND = "strong_hand"
STEADY_HAND = "steady_hand"
WELL_FED = "well_fed"
LIGHT_STEP = "light_step"

#: Each effect's name and what it does, "{pct}" standing for its strength
EFFECTS: Dict[str, Dict[str, str]] = {
    STRONG_HAND: {"name": "Strong Hand", "does": "+{pct} points at woodhacking"},
    STEADY_HAND: {"name": "Steady Hand", "does": "+{pct} time to strike a biting fish"},
    WELL_FED: {"name": "Well Fed", "does": "{pct} slower to tire"},
    LIGHT_STEP: {"name": "Light Step", "does": "Walk {pct} faster"},
}

#: The weakest and strongest effect, and the prices they come at (coins)
STRENGTH_MIN = 0.02
STRENGTH_MAX = 0.15
PRICE_FLOOR = 0.25
PRICE_CEILING = 60.0
#: Game hours a meal's effect lasts, the shortest and the longest
MEAL_HOURS_MIN = 6.0
MEAL_HOURS_MAX = 12.0
#: How filling each course is, 0 to 1: what decides most of how long a dish lasts
COURSE_STAYING: Dict[str, float] = {"main": 1.0, "pottage": 0.8, "side": 0.5, "sweet": 0.3, "drink": 0.0}
#: The shares of the span between the shortest and longest set by the course, the price and the dish
DURATION_WEIGHTS = (0.5, 0.3, 0.2)


def effect_kind(dish: Any) -> str:
    """The effect a dish gives, by its course and meat (see the module)."""
    if dish.course == "main":
        return STRONG_HAND if dish.meat else WELL_FED
    if dish.course == "sweet":
        return LIGHT_STEP
    if dish.course == "drink":
        return STEADY_HAND
    return WELL_FED   # pottage, side


def _price_share(price: float) -> float:
    """Where a price lies between `PRICE_FLOOR` and `PRICE_CEILING`, on a log scale, 0 to 1."""
    share = math.log(max(price, PRICE_FLOOR) / PRICE_FLOOR) / math.log(PRICE_CEILING / PRICE_FLOOR)
    return min(1.0, max(0.0, share))


def effect_strength(price: float) -> float:
    """How strong a dish's effect is, by its price: `STRENGTH_MIN` to `STRENGTH_MAX`."""
    return round(STRENGTH_MIN + (STRENGTH_MAX - STRENGTH_MIN) * _price_share(price), 3)


def _dish_variation(name: str) -> float:
    """0 to 1, fixed for a dish's name: dishes of a course and price do not all last alike."""
    return (zlib.crc32(name.encode("utf-8")) % 1000) / 999.0


def meal_hours(dish: Any) -> float:
    """How long a dish's effect lasts, `MEAL_HOURS_MIN` to `MEAL_HOURS_MAX`, in half hours."""
    course_w, price_w, dish_w = DURATION_WEIGHTS
    share = (course_w * COURSE_STAYING.get(dish.course, 0.5) + price_w * _price_share(dish.price)
             + dish_w * _dish_variation(dish.name))
    return round((MEAL_HOURS_MIN + (MEAL_HOURS_MAX - MEAL_HOURS_MIN) * share) * 2) / 2


def describe_hours(hours: float) -> str:
    """'6 hours', '7.5 hours'."""
    return f"{hours:g} hours"


def percent(strength: float) -> str:
    return f"{strength * 100:.0f}%"


def describe(kind: str, strength: float) -> str:
    """'Light Step: Walk 8% faster'."""
    effect = EFFECTS[kind]
    return f"{effect['name']}: {effect['does'].format(pct=percent(strength))}"


@dataclass
class MealEffect:
    dish: str
    kind: str
    strength: float
    until: datetime.datetime
    hours: float = MEAL_HOURS_MIN    # how long it lasts in all

    def active(self, now: datetime.datetime) -> bool:
        return now < self.until

    def hours_left(self, now: datetime.datetime) -> float:
        return max(0.0, (self.until - now).total_seconds() / 3600.0)

    def share_left(self, now: datetime.datetime) -> float:
        """How much of its time is left, 1 just eaten to 0 run out."""
        return min(1.0, self.hours_left(now) / self.hours) if self.hours > 0 else 0.0

    def describe(self) -> str:
        return describe(self.kind, self.strength)

    def to_save(self) -> Dict[str, Any]:
        return {"dish": self.dish, "kind": self.kind, "strength": self.strength,
                "until": self.until.isoformat(), "hours": self.hours}

    @classmethod
    def from_save(cls, data: Optional[Dict[str, Any]]) -> Optional["MealEffect"]:
        """The saved effect, or None for nothing saved or anything not understood."""
        if not data:
            return None
        try:
            kind = data["kind"]
            if kind not in EFFECTS:
                return None
            # A save from before the durations varied: they all lasted the shortest
            return cls(str(data["dish"]), kind, float(data["strength"]),
                       datetime.datetime.fromisoformat(data["until"]), float(data.get("hours", MEAL_HOURS_MIN)))
        except (KeyError, TypeError, ValueError):
            return None


def meal_effect(dish: Any, now: datetime.datetime) -> MealEffect:
    """The effect of eating `dish` at `now`."""
    hours = meal_hours(dish)
    return MealEffect(dish.name, effect_kind(dish), effect_strength(dish.price),
                      now + datetime.timedelta(hours=hours), hours)


def eat(player: Any, dish: Any, now: datetime.datetime) -> MealEffect:
    """The player eats a dish: its effect replaces the last meal's."""
    player.meal = meal_effect(dish, now)
    return player.meal


def current_meal(player: Any, now: datetime.datetime) -> Optional[MealEffect]:
    """The meal's effect the player has at `now`, or None."""
    meal = getattr(player, "meal", None)
    if meal is not None and meal.active(now):
        return meal
    return None


def bonus(player: Any, kind: str, now: datetime.datetime) -> float:
    """The strength of the player's effect of this kind at `now`, 0 without one."""
    meal = current_meal(player, now)
    return meal.strength if meal is not None and meal.kind == kind else 0.0


def game_bonus(game: Any, kind: str) -> float:
    """`bonus` for the game's player at the game's date; 0 for a game without them (a minigame's demo)."""
    player = getattr(game, "player", None)
    state = getattr(game, "state", None)
    now = getattr(state, "date", None)
    if player is None or now is None:
        return 0.0
    return bonus(player, kind, now)
