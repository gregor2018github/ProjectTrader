import random
from typing import TYPE_CHECKING, Dict, List

from ..config.constants import (
    HAPPINESS_THRESHOLD,
    POPULATION_MIN_FACTOR,
    POPULATION_MAX_FACTOR,
    HAPPINESS_EQUILIBRIUM,
    HAPPINESS_DRIFT_SIGMA,
    MAX_DAILY_POPULATION_CHANGE,
    OVERPOP_MALUS_PER_PERCENT,
    NEAR_CAPACITY_THRESHOLD,
    NEAR_CAPACITY_MALUS_PER_PERCENT,
    UNDERPOP_THRESHOLD_LOW,
    UNDERPOP_THRESHOLD_HIGH,
    UNDERPOP_BONUS_LOW,
    UNDERPOP_BONUS_HIGH,
)

if TYPE_CHECKING:
    from .institutions.town import Town


class PopulationManager:
    """Drives hourly happiness drift and daily population changes for a town.

    Writes all results back into the Town's existing attributes so that the UI
    (population_stats.py, layout.py) requires no changes.

    History follows the same pattern as Good.price_history_*:
    - happiness_history / average_happiness_history: per-group and aggregate, hourly
    - population_history / total_population_history: per-group and aggregate, daily
    """

    def __init__(self, town: "Town") -> None:
        self.town = town

        # Store the map-defined 100% baseline so min/max clamping is always relative to it.
        self.base_groups: Dict[str, int] = dict(town.population_groups)

        # Per-group histories (same granularity as Good.price_history_*)
        self.happiness_history: Dict[str, List[float]] = {
            group: [happiness]
            for group, happiness in town.happiness_groups.items()
        }
        self.population_history: Dict[str, List[int]] = {
            group: [count]
            for group, count in town.population_groups.items()
        }

        # Aggregate histories for charting (single series each)
        self.average_happiness_history: List[float] = [town.happiness]
        self.total_population_history: List[int] = [town.citizens]

    @property
    def average_happiness(self) -> float:
        """Population-weighted average happiness across all groups."""
        total_pop = sum(self.town.population_groups.values())
        if total_pop == 0:
            groups = list(self.town.happiness_groups.values())
            return sum(groups) / len(groups) if groups else HAPPINESS_EQUILIBRIUM
        weighted = sum(
            self.town.happiness_groups[g] * self.town.population_groups[g]
            for g in self.town.happiness_groups
        )
        return weighted / total_pop

    def update_happiness(self) -> None:
        """Apply hourly happiness drift to each population group.

        Each group receives:
        - A small random nudge (normal distribution)
        - A weak pull toward the effective equilibrium
        - An overpopulation penalty: each 1% above the map-defined base
          shifts the equilibrium down by 1.5 points (per-group)

        Results are clamped to [0, 100] and written to Town so the UI
        reflects current values immediately.
        """
        for group in self.town.happiness_groups:
            current = self.town.happiness_groups[group]
            base_pop = self.base_groups.get(group, 0)
            current_pop = self.town.population_groups.get(group, 0)

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

            noise = random.normalvariate(0.0, HAPPINESS_DRIFT_SIGMA)
            reversion = 0.05 * (effective_equilibrium - current)
            new_happiness = current + noise + reversion
            self.town.happiness_groups[group] = max(0.0, min(100.0, new_happiness))

        self.town.happiness = self.average_happiness

    def record_happiness_history(self) -> None:
        """Append current per-group and aggregate happiness to the hourly history lists."""
        for group, happiness in self.town.happiness_groups.items():
            self.happiness_history[group].append(happiness)
        self.average_happiness_history.append(self.town.happiness)

    def update_population(self) -> None:
        """Adjust population based on average happiness (called daily).

        Computes the new total first, then redistributes it proportionally
        across groups using the configured shares so no single group absorbs
        all the rounding error.  Each group is hard-clamped to
        [base * MIN_FACTOR, base * MAX_FACTOR].
        """
        avg = self.average_happiness
        # Scale: threshold maps to 0, extremes map to ±MAX_DAILY_POPULATION_CHANGE.
        delta_rate = (avg - HAPPINESS_THRESHOLD) / (100.0 - HAPPINESS_THRESHOLD) * MAX_DAILY_POPULATION_CHANGE

        new_total = round(self.town.citizens * (1.0 + delta_rate))
        new_groups = self.town._split_population_into_groups(new_total)

        for group in self.town.population_groups:
            base = self.base_groups.get(group, 0)
            if base == 0:
                continue
            lo = round(base * POPULATION_MIN_FACTOR)
            hi = round(base * POPULATION_MAX_FACTOR)
            self.town.population_groups[group] = max(lo, min(hi, new_groups.get(group, 0)))

        self.town.citizens = sum(self.town.population_groups.values())

    def record_population_history(self) -> None:
        """Append current per-group and aggregate population counts to the daily history lists."""
        for group, count in self.town.population_groups.items():
            self.population_history[group].append(count)
        self.total_population_history.append(self.town.citizens)
