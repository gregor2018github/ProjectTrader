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

The player has one meal's effect at a time (`Player.meal`, saved): a new dish
replaces whatever the last one gave, the same dish again starts its hours afresh.
It lasts `MEAL_HOURS` of game time. No pygame here.
"""

import datetime
import math
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
#: Game hours a meal's effect lasts
MEAL_HOURS = 6.0


def effect_kind(dish: Any) -> str:
    """The effect a dish gives, by its course and meat (see the module)."""
    if dish.course == "main":
        return STRONG_HAND if dish.meat else WELL_FED
    if dish.course == "sweet":
        return LIGHT_STEP
    if dish.course == "drink":
        return STEADY_HAND
    return WELL_FED   # pottage, side


def effect_strength(price: float) -> float:
    """How strong a dish's effect is, by its price: `STRENGTH_MIN` to `STRENGTH_MAX`."""
    share = math.log(max(price, PRICE_FLOOR) / PRICE_FLOOR) / math.log(PRICE_CEILING / PRICE_FLOOR)
    share = min(1.0, max(0.0, share))
    return round(STRENGTH_MIN + (STRENGTH_MAX - STRENGTH_MIN) * share, 3)


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

    def active(self, now: datetime.datetime) -> bool:
        return now < self.until

    def hours_left(self, now: datetime.datetime) -> float:
        return max(0.0, (self.until - now).total_seconds() / 3600.0)

    def describe(self) -> str:
        return describe(self.kind, self.strength)

    def to_save(self) -> Dict[str, Any]:
        return {"dish": self.dish, "kind": self.kind, "strength": self.strength,
                "until": self.until.isoformat()}

    @classmethod
    def from_save(cls, data: Optional[Dict[str, Any]]) -> Optional["MealEffect"]:
        """The saved effect, or None for nothing saved or anything not understood."""
        if not data:
            return None
        try:
            kind = data["kind"]
            if kind not in EFFECTS:
                return None
            return cls(str(data["dish"]), kind, float(data["strength"]),
                       datetime.datetime.fromisoformat(data["until"]))
        except (KeyError, TypeError, ValueError):
            return None


def meal_effect(dish: Any, now: datetime.datetime) -> MealEffect:
    """The effect of eating `dish` at `now`."""
    return MealEffect(dish.name, effect_kind(dish), effect_strength(dish.price),
                      now + datetime.timedelta(hours=MEAL_HOURS))


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
