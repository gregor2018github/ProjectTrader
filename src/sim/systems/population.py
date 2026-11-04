"""The town's people: hourly happiness drift and daily migration, per social class.

Functions on a ``PopulationState`` (and the simulation's random generator where
they draw), the rules ``PopulationManager`` had before the simulation core was
split out, kept to the last bit. They are placeholders: P1 (``docs/roadmap.md``)
replaces the random drift with needs met from the market.
"""
import random
from typing import Dict, List, Tuple

from ...config.constants import (
    HAPPINESS_DRIFT_SIGMA, HAPPINESS_EQUILIBRIUM, HAPPINESS_START, HAPPINESS_THRESHOLD,
    MAX_DAILY_POPULATION_CHANGE, NEAR_CAPACITY_MALUS_PER_PERCENT, NEAR_CAPACITY_THRESHOLD,
    OVERPOP_MALUS_PER_PERCENT, POPULATION_MAX_FACTOR, POPULATION_MIN_FACTOR,
    POPULATION_SHARE_COMMONS, POPULATION_SHARE_MIDDLING_SORT, POPULATION_SHARE_NOBILITY,
    POPULATION_SHARE_POOR, STARTING_OCCUPANCY, UNDERPOP_BONUS_HIGH, UNDERPOP_BONUS_LOW,
    UNDERPOP_THRESHOLD_HIGH, UNDERPOP_THRESHOLD_LOW,
)
from ..state import ClassState, PopulationState, TownSpec

HAPPINESS_REVERSION = 0.05      # share of the gap to the equilibrium a class's happiness closes each hour


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
    classes = {
        name: ClassState(name=name, count=count, base=count, happiness=float(HAPPINESS_START),
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
        return sum(groups) / len(groups) if groups else HAPPINESS_EQUILIBRIUM
    weighted = sum(c.happiness * c.count for c in pop.classes.values())
    return weighted / total_pop


def update_happiness(pop: PopulationState, rng: random.Random) -> None:
    """An hour's happiness drift for each class (one draw from *rng* per class).

    Each class gets a small random nudge, a weak pull towards its equilibrium,
    and a crowding penalty on that equilibrium (from NEAR_CAPACITY_THRESHOLD %
    of its base, harder past 100 %) or a bonus when it is well under its base.
    Clamped to [0, 100]; the town's happiness becomes the weighted average.
    """
    for cls in pop.classes.values():
        current = cls.happiness
        base_pop = cls.base
        current_pop = cls.count

        # Overpopulation penalty shifts the happiness equilibrium downward.
        # Two-stage: crowding starts at NEAR_CAPACITY_THRESHOLD%, full penalty above 100%.
        if base_pop > 0:
            fill_pct = current_pop / base_pop * 100.0
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
        effective_equilibrium = (HAPPINESS_EQUILIBRIUM
                                 + underpop_bonus
                                 - near_capacity_pct * NEAR_CAPACITY_MALUS_PER_PERCENT
                                 - overpop_pct * OVERPOP_MALUS_PER_PERCENT)

        noise = rng.normalvariate(0.0, HAPPINESS_DRIFT_SIGMA)
        reversion = HAPPINESS_REVERSION * (effective_equilibrium - current)
        new_happiness = current + noise + reversion
        cls.happiness = max(0.0, min(100.0, new_happiness))

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
