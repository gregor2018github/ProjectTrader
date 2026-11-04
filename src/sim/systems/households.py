"""The households: each social class earns, plans its day's shopping by tier, buys, and rates how it did.

Functions on a ``ClassState`` and its ``ClassNeedsDef`` (``needs.json``).
Nothing here draws from the random generator. ``docs/p1_living_market.md``
("Households", "Happiness and migration") is the specification.

A day: income into the purse, savings above the cap leak out of town,
yesterday's shopping is rated per tier (fulfilment, 0..1), and today's is
planned: the wanted units of each tier, basic first, as far as the budget
reaches at today's prices. During market hours the plan is bought in slices
(``slice_orders``, ``receive``), each slice asking for an equal share of what is
still missing, so a short slice is made up later in the day if stock returns.
"""
import datetime
from typing import Dict, List, Mapping, Optional

from ...config.constants import (
    HAPPINESS_FROM_NEEDS_MAX, HAPPINESS_FROM_NEEDS_MIN, HUNGER_PENALTY, HUNGER_THRESHOLD,
    PURSE_START_DAYS, SAVINGS_CAP_DAYS, SAVINGS_RELEASE,
)
from ..calendar import season_factor
from ..data import TIERS, ClassNeedsDef
from ..state import ClassFlows, ClassState, PlanItem


def daily_income(cls: ClassState, needs: ClassNeedsDef) -> float:
    """The class's base income: every head not working in a workshop earns it (those who do earn wages instead)."""
    return max(0.0, cls.count - cls.employed) * needs.base_income


def give_start_purse(cls: ClassState, needs: ClassNeedsDef) -> None:
    """A class's purse when a game starts: PURSE_START_DAYS of its income."""
    cls.purse = PURSE_START_DAYS * daily_income(cls, needs)


def wanted_units(cls: ClassState, needs: ClassNeedsDef, moment: datetime.datetime) -> List[PlanItem]:
    """What the whole class wants today, item by item in tier order (prices and plans not yet set)."""
    items = []
    for tier in TIERS:
        for need in needs.tiers[tier]:
            units = need.units * cls.count * season_factor(need.seasons, moment)
            items.append(PlanItem(good=need.good, tier=tier, wanted=units, planned=0.0, price=0.0))
    return items


def fulfilment(plan: List[PlanItem]) -> Dict[str, float]:
    """Per tier, the share of what was wanted that was got, weighted by the planning prices.

    A tier nothing was wanted in counts as fully met.
    """
    result = {}
    for tier in TIERS:
        wanted = sum(p.wanted * p.price for p in plan if p.tier == tier)
        got = sum(min(p.bought, p.wanted) * p.price for p in plan if p.tier == tier)
        result[tier] = got / wanted if wanted > 0 else 1.0
    return result


def start_day(cls: ClassState, needs: ClassNeedsDef, prices: Mapping[str, float],
              moment: datetime.datetime, wages: float = 0.0, payouts: float = 0.0,
              outside: Optional[Mapping[str, float]] = None) -> None:
    """The class's day begins: rate yesterday, earn, cap the savings, plan today's shopping.

    Args:
        cls: The class.
        needs: Its definition.
        prices: Today's price of every good.
        moment: The start of the day (for the seasons).
        wages: Paid by workshops for yesterday's work (its workers earned no base income).
        payouts: Its share of owners' surplus paid out to the townsfolk.
        outside: Each good's outside price, which dearness is measured against (none: nothing is dear).
    """
    if cls.plan:
        cls.fulfilment = fulfilment(cls.plan)
    cls.yesterday = cls.today
    cls.today = ClassFlows()

    income = daily_income(cls, needs) + wages + payouts
    savings = cls.purse
    cls.purse += income
    cls.today.income = income
    cls.today.wages = wages
    cls.today.payouts = payouts
    cap = SAVINGS_CAP_DAYS * income
    if cls.purse > cap:
        cls.today.leaked = cls.purse - cap
        cls.purse = cap
        savings = max(0.0, cap - income)

    unmet = any(f < 1.0 for f in cls.fulfilment.values())
    budget = min(cls.purse, income + (SAVINGS_RELEASE * savings if unmet else 0.0))
    plan(cls, needs, prices, moment, budget, outside)


def dearness_factor(price: float, outside: float, elasticity: float) -> float:
    """How much of its basket amount a class buys at *price*: (price / outside) ^ −elasticity above the outside price, all below it."""
    if outside <= 0 or price <= outside or elasticity <= 0:
        return 1.0
    return (price / outside) ** -elasticity


def plan(cls: ClassState, needs: ClassNeedsDef, prices: Mapping[str, float],
         moment: datetime.datetime, budget: float, outside: Optional[Mapping[str, float]] = None) -> None:
    """Plan the day's shopping, tier by tier.

    Of each good it means to buy the basket amount, less the dearer the good is
    above its outside price (``dearness_factor``, the tier's elasticity or the
    need's own); then all of that if the budget reaches, else the same share of
    each good. What a tier did not cost, because it bought less or it was
    cheap, is left for the next tier. Fulfilment still counts against the whole
    basket (``PlanItem.wanted``).
    """
    items = wanted_units(cls, needs, moment)
    elasticities = [needs.elasticity_of(tier, need) for tier in TIERS for need in needs.tiers[tier]]
    for item, elasticity in zip(items, elasticities):
        item.price = prices[item.good]
        item.planned = item.wanted * dearness_factor(item.price, outside.get(item.good, 0.0) if outside else 0.0,
                                                     elasticity)
    remaining = budget
    for tier in TIERS:
        tier_items = [i for i in items if i.tier == tier]
        cost = sum(i.planned * i.price for i in tier_items)
        share = min(1.0, remaining / cost) if cost > 0 else 1.0
        for i in tier_items:
            i.planned *= share
        remaining = max(0.0, remaining - cost * share)
    cls.plan = items


def slice_orders(cls: ClassState, slices_left: int, prices: Mapping[str, float]) -> Dict[str, float]:
    """What the class asks for in this slice: an equal share of what is still missing, as far as the purse goes.

    Args:
        cls: The class.
        slices_left: Slices left today, this one included.
        prices: The current price of every good.

    Returns:
        Good -> units.
    """
    orders: Dict[str, float] = {}
    for item in cls.plan:
        missing = item.planned - item.bought
        if missing > 1e-9:
            orders[item.good] = orders.get(item.good, 0.0) + missing / slices_left
    cost = sum(units * prices[good] for good, units in orders.items())
    if cost > cls.purse:
        scale = cls.purse / cost if cost > 0 else 0.0
        orders = {good: units * scale for good, units in orders.items()}
    return orders


def receive(cls: ClassState, good: str, units: float, paid: float) -> None:
    """Book units bought and their price: into the plan's items for that good, basic tier first."""
    cls.purse -= paid
    cls.today.spent += paid
    for item in cls.plan:
        if units <= 0:
            break
        if item.good == good:
            take = min(units, max(0.0, item.planned - item.bought))
            item.bought += take
            units -= take


def needs_happiness(cls: ClassState, needs: ClassNeedsDef) -> float:
    """The happiness yesterday's fulfilment earns, before crowding: weighted by tier, less a hunger penalty."""
    score = sum(needs.happiness_weights[t] * cls.fulfilment.get(t, 1.0) for t in TIERS)
    target = HAPPINESS_FROM_NEEDS_MIN + (HAPPINESS_FROM_NEEDS_MAX - HAPPINESS_FROM_NEEDS_MIN) * score
    if cls.fulfilment.get("basic", 1.0) < HUNGER_THRESHOLD:
        target -= HUNGER_PENALTY
    return target
