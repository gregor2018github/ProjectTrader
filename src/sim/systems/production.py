"""Workshops: each runs its building's recipe for its owner, as hard as its margin says.

Functions on a ``WorkshopState`` with its ``BuildingDef`` and ``RecipeDef``,
and on ``OwnerState``. Nothing here draws from the random generator, and
nothing reads an owner's ``kind``: a town's workshop runs on the same rules a
player's or a rival's will (``docs/roadmap.md``, pillar 1).
``docs/p1_living_market.md`` ("Workshops", "Owners") is the specification.

A day: the workshop pays yesterday's workers, its owner covers a loss or takes
the profit above the working capital, and it plans: the margin of a batch at
today's prices sets the utilisation it glides to, which (with the workers it
can hire and the cash it has) sets today's batches. Capacity grows after a run
of busy days and shrinks, more slowly, after a run of losses. During market
hours each slice buys the inputs for its share of the batches, runs what the
inputs allow, and sells the outputs into the market.
"""
from typing import Dict, Mapping, Optional, Tuple

from ...config.constants import (
    GROWTH_AFTER_DAYS, GROWTH_DESIRE, GROWTH_MIN_STEP, GROWTH_STEP, MARGIN_FLOOR, MARGIN_FULL,
    SHRINK_AFTER_DAYS, SHRINK_STEP, TREASURY_CAP_DAYS, TREASURY_INCOME_GLIDE, UTILISATION_GLIDE, WAGE_GLIDE,
)
from ..data import BuildingDef, RecipeDef
from ..state import OwnerState, WorkshopState


def batch_cost(recipe: RecipeDef, wage: float, prices: Mapping[str, float]) -> float:
    """What one batch costs at these prices and this wage: its inputs and its labour."""
    return sum(units * prices[good] for good, units in recipe.inputs.items()) + recipe.labour * wage


def batch_margin(recipe: RecipeDef, wage: float, prices: Mapping[str, float]) -> float:
    """What one batch earns on its costs at these prices, byproducts counted: (revenue − cost) / cost."""
    revenue = sum(units * prices[good] for good, units in recipe.outputs.items())
    cost = batch_cost(recipe, wage, prices)
    if cost <= 0:
        return MARGIN_FULL if revenue > 0 else MARGIN_FLOOR
    return (revenue - cost) / cost


def wanted_utilisation(margin: float) -> float:
    """The utilisation a margin calls for: none at MARGIN_FLOOR or below, full from MARGIN_FULL, linear between."""
    return min(1.0, max(0.0, (margin - MARGIN_FLOOR) / (MARGIN_FULL - MARGIN_FLOOR)))


def settle_day(ws: WorkshopState, building: BuildingDef, owner: OwnerState) -> float:
    """The workshop's day ends: it pays yesterday's workers, and its owner settles with it.

    The owner tops the workshop's cash up to its working capital, as far as the
    owner's own cash goes (so a workshop that spent its cash on growth, or ran
    at a loss, can still buy and hire), and takes whatever is above it.

    Returns:
        The wages paid (to its workers' class).
    """
    ws.done_yesterday = ws.done
    wages = ws.workers * ws.wage
    ws.cash -= wages
    shortfall = building.working_capital - ws.cash
    if shortfall > 0 and owner.cash > 0:
        cover = min(owner.cash, shortfall)
        owner.cash -= cover
        ws.cash += cover
        owner.topped_up_today += cover
    surplus = ws.cash - building.working_capital
    if surplus > 0:
        ws.cash -= surplus
        owner.cash += surplus
        owner.profits_today += surplus
    return wages


def treasury_cap(owner: OwnerState) -> float:
    """The most a "treasury_with_tribute" owner keeps: TREASURY_CAP_DAYS of its average net income, or its reserve."""
    return max(owner.reserve, TREASURY_CAP_DAYS * max(0.0, owner.income_avg))


def owner_day(owner: OwnerState) -> Tuple[float, float]:
    """An owner's day, after its workshops settled: its average income moves, and its surplus rule acts.

    - ``keep``: it keeps everything.
    - ``townsfolk``: cash above its reserve is paid out per head to the classes.
    - ``treasury_with_tribute``: it keeps up to ``treasury_cap``; above that is
      tribute to the lord, gone out of town.

    Returns:
        What it pays the townsfolk, and what it pays as tribute.
    """
    owner.income_avg += TREASURY_INCOME_GLIDE * (owner.profits_today - owner.topped_up_today - owner.income_avg)
    if owner.surplus_to == "townsfolk" and owner.cash > owner.reserve:
        surplus = owner.cash - owner.reserve
        owner.cash -= surplus
        owner.paid_out_today += surplus
        return surplus, 0.0
    if owner.surplus_to == "treasury_with_tribute" and owner.cash > treasury_cap(owner):
        tribute = owner.cash - treasury_cap(owner)
        owner.cash -= tribute
        owner.tribute_today += tribute
        return 0.0, tribute
    return 0.0, 0.0


def plan_wants(ws: WorkshopState, recipe: RecipeDef, prices: Mapping[str, float], wage: float) -> float:
    """The first half of planning: the batches the workshop wants today, before it knows how many it can hire.

    The margin of a batch at today's prices and its class's wage sets the
    utilisation it glides to; it wants capacity × utilisation batches, as far
    as its cash goes.

    Returns:
        The workers those batches would take.
    """
    ws.margin = batch_margin(recipe, wage, prices)
    ws.utilisation += UTILISATION_GLIDE * (wanted_utilisation(ws.margin) - ws.utilisation)
    ws.unprofitable_days = ws.unprofitable_days + 1 if ws.margin < 0 else 0
    batches = ws.capacity * ws.utilisation
    cost = batch_cost(recipe, wage, prices)
    if cost > 0:
        batches = min(batches, max(0.0, ws.cash) / cost)
    ws.planned = batches
    return batches * recipe.labour


def hire(ws: WorkshopState, recipe: RecipeDef, share: float, wage: float) -> float:
    """The second half: the workshop gets *share* of the workers it wanted (all of them unless its class runs short).

    Every workshop hiring from a class gets the same share, as buyers in a short
    market do; nobody is first in line. It pays them *wage* each, at the end of
    the day.

    Returns:
        The workers it hires.
    """
    wanted = wanted_utilisation(ws.margin)
    ws.planned *= share
    ws.done = 0.0
    ws.workers = ws.planned * recipe.labour
    ws.wage = wage
    # Busy: it wants (nearly) full capacity and could plan it, workers and cash allowing
    busy = wanted >= GROWTH_DESIRE and ws.planned >= GROWTH_DESIRE * ws.capacity
    ws.busy_days = ws.busy_days + 1 if busy else 0
    return ws.workers


def change_capacity(ws: WorkshopState, building: BuildingDef, owner: OwnerState) -> Tuple[float, float]:
    """Grow after GROWTH_AFTER_DAYS busy days, if the workshop and its owner can pay; shrink after SHRINK_AFTER_DAYS of losses.

    Growth is paid to builders out of town (``building.growth_cost`` per batch a
    day), first from the workshop's cash, the rest from its owner's.

    Returns:
        The capacity change, and what the growth cost (0 when it shrank or stayed).
    """
    if ws.busy_days >= GROWTH_AFTER_DAYS and ws.capacity < building.max_capacity:
        step = min(max(GROWTH_STEP * ws.capacity, GROWTH_MIN_STEP), building.max_capacity - ws.capacity)
        cost = step * building.growth_cost
        if ws.cash + max(0.0, owner.cash) >= cost:
            from_workshop = min(max(0.0, ws.cash), cost)
            ws.cash -= from_workshop
            owner.cash -= cost - from_workshop
            ws.capacity += step
            ws.busy_days = 0
            return step, cost
    if ws.unprofitable_days >= SHRINK_AFTER_DAYS and ws.capacity > 0:
        step = ws.capacity * SHRINK_STEP
        ws.capacity -= step
        ws.unprofitable_days = 0
        return -step, 0.0
    return 0.0, 0.0


def input_wants(ws: WorkshopState, recipe: RecipeDef) -> Dict[str, float]:
    """What the day's planned batches use, input by input."""
    return {good: units * ws.planned for good, units in recipe.inputs.items()}


def slice_orders(ws: WorkshopState, recipe: RecipeDef, slices_left: int, prices: Mapping[str, float]) -> Dict[str, float]:
    """The inputs this slice's share of the batches still needs, less what is in stock, as far as the cash goes."""
    batches = max(0.0, ws.planned - ws.done) / slices_left
    orders = {}
    for good, units in recipe.inputs.items():
        missing = units * batches - ws.input_stock.get(good, 0.0)
        if missing > 1e-9:
            orders[good] = missing
    cost = sum(units * prices[good] for good, units in orders.items())
    if cost > ws.cash:
        scale = max(0.0, ws.cash) / cost if cost > 0 else 0.0
        orders = {good: units * scale for good, units in orders.items()}
    return orders


def run_slice(ws: WorkshopState, recipe: RecipeDef, slices_left: int) -> Dict[str, float]:
    """Run this slice's share of the batches, as far as the inputs in stock allow.

    Returns:
        The outputs made, good by good.
    """
    batches = max(0.0, ws.planned - ws.done) / slices_left
    for good, units in recipe.inputs.items():
        batches = min(batches, ws.input_stock.get(good, 0.0) / units)
    if batches <= 0:
        return {}
    for good, units in recipe.inputs.items():
        ws.input_stock[good] = max(0.0, ws.input_stock.get(good, 0.0) - units * batches)
    ws.done += batches
    return {good: units * batches for good, units in recipe.outputs.items()}


def move_wage(wage: float, wanted: float, hands: float, floor: float, cap: float) -> float:
    """A class's wage after a day of its workshops wanting *wanted* workers from its *hands*.

    The tension is how far the wanting overshoots the hands (as a share of
    them, within [−1, 1]). Short of hands, the wage moves WAGE_GLIDE × tension
    of the way to *cap*; with hands to spare, the same of the way down to
    *floor* (its base income: below it nobody would take the job).
    """
    if hands <= 0:
        return max(floor, min(cap, wage))
    tension = max(-1.0, min(1.0, (wanted - hands) / hands))
    if tension > 0:
        wage += WAGE_GLIDE * tension * (cap - wage)
    else:
        wage += WAGE_GLIDE * tension * (wage - floor)
    return max(floor, min(cap, wage))


def labour_share_given(labour_share: float, count: int, wanted: float) -> float:
    """The share of the workers wanted that a class can give: all of them, or as many as it has hands for."""
    hands = labour_share * count
    return 1.0 if wanted <= hands else (hands / wanted if wanted > 0 else 1.0)


def owner_of(ws: WorkshopState, owners: Mapping[str, OwnerState]) -> Optional[OwnerState]:
    return owners.get(ws.owner_id)
