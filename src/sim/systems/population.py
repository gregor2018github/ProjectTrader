"""The town's people: head counts per social class, their happiness and migration.

Functions on a ``PopulationState``. Happiness glides each hour towards a
target per class: what its needs earned (``households.needs_happiness``) moved
by crowding, as before. Migration follows the average happiness, as before.
Nothing here draws from the random generator.
"""
from typing import Dict, List, Tuple

from ...config.constants import (
    HAPPINESS_GLIDE, HAPPINESS_START, HAPPINESS_THRESHOLD,
    MAX_DAILY_POPULATION_CHANGE, NEAR_CAPACITY_MALUS_PER_PERCENT, NEAR_CAPACITY_THRESHOLD,
    OVERPOP_MALUS_PER_PERCENT, POPULATION_MAX_FACTOR, POPULATION_MIN_FACTOR,
    POPULATION_SHARE_COMMONS, POPULATION_SHARE_MIDDLING_SORT, POPULATION_SHARE_NOBILITY,
    POPULATION_SHARE_POOR, STARTING_OCCUPANCY, UNDERPOP_BONUS_HIGH, UNDERPOP_BONUS_LOW,
    UNDERPOP_THRESHOLD_HIGH, UNDERPOP_THRESHOLD_LOW,
)
from ..state import ClassState, PopulationState, TownSpec


def class_shares() -> List[Tuple[str, float]]:
    """The social classes, poorest first, and their share of the town."""
    return [
        ("Poor", POPULATION_SHARE_POOR),
        ("Commons", POPULATION_SHARE_COMMONS),
        ("Middling Sort", POPULATION_SHARE_MIDDLING_SORT),
        ("Nobility", POPULATION_SHARE_NOBILITY),
    ]


def starting_inhabitants(capacity: int) -> int:
    """How many live in a house of this capacity when a game starts (0 for one nobody lives in)."""
    return round(capacity * STARTING_OCCUPANCY) if capacity > 0 else 0


def split_into_classes(total_population: int) -> Dict[str, int]:
    """Split a head count into the classes by their shares, largest remainders first."""
    group_shares = class_shares()
    exact_values = [(name, total_population * share) for name, share in group_shares]
    population_groups = {name: int(value) for name, value in exact_values}

    assigned = sum(population_groups.values())
    remainder = total_population - assigned

    if remainder > 0:
        fractions_sorted = sorted(
            exact_values,
            key=lambda item: item[1] - int(item[1]),
            reverse=True
        )
        for idx in range(remainder):
            group_name = fractions_sorted[idx % len(fractions_sorted)][0]
            population_groups[group_name] += 1

    return population_groups


def create_population(town: TownSpec) -> PopulationState:
    """The town's people as a new game has them: the houses STARTING_OCCUPANCY full, split by class."""
    residential = [c for c in town.house_capacities if c > 0]
    citizens = sum(starting_inhabitants(c) for c in residential)
    groups = split_into_classes(citizens)
    housing = split_into_classes(sum(residential))
    classes = {
        name: ClassState(name=name, count=count, base=count, capacity=housing[name],
                         happiness=float(HAPPINESS_START), happiness_target=float(HAPPINESS_START),
                         happiness_history=[float(HAPPINESS_START)], population_history=[count])
        for name, count in groups.items()
    }
    return PopulationState(
        classes=classes,
        max_citizens=sum(residential),
        happiness=HAPPINESS_START,
        average_happiness_history=[HAPPINESS_START],
        total_population_history=[citizens],
    )


def average_happiness(pop: PopulationState) -> float:
    """Population-weighted average happiness across all classes."""
    total_pop = sum(c.count for c in pop.classes.values())
    if total_pop == 0:
        groups = [c.happiness for c in pop.classes.values()]
        return sum(groups) / len(groups) if groups else float(HAPPINESS_START)
    weighted = sum(c.happiness * c.count for c in pop.classes.values())
    return weighted / total_pop


def average_target(pop: PopulationState) -> float:
    """Population-weighted average of the classes' target happiness."""
    total = sum(c.count for c in pop.classes.values())
    if total == 0:
        return float(HAPPINESS_START)
    return sum(c.happiness_target * c.count for c in pop.classes.values()) / total


def crowding_shift(cls: ClassState) -> float:
    """How crowding moves a class's target happiness: a bonus in half-empty housing, a penalty near and over full.

    Measured against the class's share of the town's housing (``capacity``), so a
    town at its starting size (STARTING_OCCUPANCY full) is neither. Two-stage:
    crowding starts at NEAR_CAPACITY_THRESHOLD % of the housing, the full
    penalty above 100 %.
    """
    if cls.capacity > 0:
        fill_pct = cls.count / cls.capacity * 100.0
        near_capacity_pct = max(0.0, min(fill_pct, 100.0) - NEAR_CAPACITY_THRESHOLD)
        overpop_pct = max(0.0, fill_pct - 100.0)
    else:
        fill_pct = 0.0
        near_capacity_pct = 0.0
        overpop_pct = 0.0
    if fill_pct < UNDERPOP_THRESHOLD_LOW:
        underpop_bonus = UNDERPOP_BONUS_LOW
    elif fill_pct < UNDERPOP_THRESHOLD_HIGH:
        underpop_bonus = UNDERPOP_BONUS_HIGH
    else:
        underpop_bonus = 0
    return (underpop_bonus
            - near_capacity_pct * NEAR_CAPACITY_MALUS_PER_PERCENT
            - overpop_pct * OVERPOP_MALUS_PER_PERCENT)


def give_housing(pop: PopulationState) -> None:
    """Each class's share of the town's housing, for a state saved before it was kept."""
    housing = split_into_classes(pop.max_citizens)
    for cls in pop.classes.values():
        if cls.capacity <= 0:
            cls.capacity = housing.get(cls.name, 0)


def set_target(cls: ClassState, from_needs: float) -> None:
    """A class's target happiness: what its needs earned, moved by crowding, within [0, 100]."""
    cls.happiness_target = max(0.0, min(100.0, from_needs + crowding_shift(cls)))


def glide_happiness(pop: PopulationState) -> None:
    """An hour's move of each class's happiness towards its target; the town's becomes the weighted average."""
    for cls in pop.classes.values():
        cls.happiness += HAPPINESS_GLIDE * (cls.happiness_target - cls.happiness)
    pop.happiness = average_happiness(pop)


def record_happiness(pop: PopulationState) -> None:
    """Append each class's and the town's happiness to the hourly histories."""
    for cls in pop.classes.values():
        cls.happiness_history.append(cls.happiness)
    pop.average_happiness_history.append(pop.happiness)


def update_population(pop: PopulationState) -> Tuple[int, int]:
    """A day's migration: people move in or out by the average happiness.

    The new total is split by the class shares again, and each class is held
    within [base × POPULATION_MIN_FACTOR, base × POPULATION_MAX_FACTOR].

    Returns:
        The head count before and after.
    """
    old_total = pop.citizens
    avg = average_happiness(pop)
    # Scale: threshold maps to 0, extremes map to ±MAX_DAILY_POPULATION_CHANGE.
    delta_rate = (avg - HAPPINESS_THRESHOLD) / (100.0 - HAPPINESS_THRESHOLD) * MAX_DAILY_POPULATION_CHANGE

    new_total = round(old_total * (1.0 + delta_rate))
    new_groups = split_into_classes(new_total)

    for cls in pop.classes.values():
        base = cls.base
        if base == 0:
            continue
        lo = round(base * POPULATION_MIN_FACTOR)
        hi = round(base * POPULATION_MAX_FACTOR)
        cls.count = max(lo, min(hi, new_groups.get(cls.name, 0)))

    return old_total, pop.citizens


def record_population(pop: PopulationState) -> None:
    """Append each class's and the town's head count to the daily histories."""
    for cls in pop.classes.values():
        cls.population_history.append(cls.count)
    pop.total_population_history.append(pop.citizens)
