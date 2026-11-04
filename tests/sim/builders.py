"""Small, obvious definitions for the sim tests: goods with a still outside price, a town, plain needs."""
import datetime
from typing import Dict, List, Optional, Sequence

from src.sim import ClassNeedsDef, GoodDef, NeedDef, Simulation, TownSpec
from src.sim.data import TIERS

START = datetime.datetime(1500, 1, 1, 8, 0)
CLASSES = ("Poor", "Commons", "Middling Sort", "Nobility")
TOWN = TownSpec([6, 8, 0, 12, 5, 20])


def good_def(name: str = "Wood", price: float = 10.0, index: int = 0, **changes) -> GoodDef:
    """A good whose outside price stands still at *price*, without noise, 1g transport each way."""
    fields = dict(name=name, color="BLACK", chart_index=index, show_in_charts=True, outside_price=price,
                  outside_reversion=0.0, outside_volatility=0.0, transport_cost=1.0, import_limit=120.0,
                  export_limit=120.0, target_stock_days=10.0, min_target_stock=100.0, noise_sigma=0.0)
    fields.update(changes)
    return GoodDef(**fields)


def class_needs(name: str, income: float = 5.0, basic: Optional[Dict[str, float]] = None,
                comfort: Optional[Dict[str, float]] = None, luxury: Optional[Dict[str, float]] = None,
                weights: Sequence[float] = (0.6, 0.3, 0.1)) -> ClassNeedsDef:
    tiers = {"basic": basic or {}, "comfort": comfort or {}, "luxury": luxury or {}}
    return ClassNeedsDef(
        name=name, base_income=income, labour_share=0.5,
        happiness_weights=dict(zip(TIERS, weights)),
        tiers={t: [NeedDef(g, u) for g, u in tiers[t].items()] for t in TIERS},
    )


def plain_needs(basic: Optional[Dict[str, float]] = None, income: float = 5.0) -> List[ClassNeedsDef]:
    """Every class wanting the same basic goods per head and nothing else."""
    return [class_needs(c, income, basic=basic or {}) for c in CLASSES]


def simulation(goods: Optional[Sequence[GoodDef]] = None, needs: Optional[Sequence[ClassNeedsDef]] = None,
               town: Optional[TownSpec] = TOWN, seed: int = 7) -> Simulation:
    goods = goods or [good_def("Wood", 1.0, 0), good_def("Wine", 10.0, 1)]
    needs = needs or plain_needs({"Wood": 0.5, "Wine": 0.05})
    return Simulation(goods, needs, now=START, seed=seed, town=town)
