"""The daily menu a tavern offers, drawn from the dishes in assets/texts/taverns/dishes.csv.

Each dish there has a class (low, middle or high: which kind of tavern serves
it), a course, whether it has meat and its price in coins. A tavern's class is the `Tavern`
property on its building in Tiled. Its menu is drawn anew each day from the
dishes of its class, `MENU_COURSES` of each course, the same all day and
different from tavern to tavern. On fast days, every Friday and Lent (both by the
game calendar, `game_calendar.is_fast_day`), no meat is served.
"""

import csv
import datetime
import os
import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from ..config.constants import MAIN_PATH
from .game_calendar import is_fast_day

DISHES_PATH = os.path.join(MAIN_PATH, "assets", "texts", "taverns", "dishes.csv")

TAVERN_CLASSES = ("low", "middle", "high")

# The courses in the order they are listed, with their heading on the menu
COURSES: Tuple[Tuple[str, str], ...] = (
    ("pottage", "Pottage"),
    ("main", "Dishes"),
    ("side", "Bread & Sides"),
    ("sweet", "Sweets"),
    ("drink", "To Drink"),
)

# How many dishes of each course a tavern of each class offers a day
MENU_COURSES: Dict[str, Dict[str, int]] = {
    "low": {"pottage": 1, "main": 1, "side": 1, "sweet": 1, "drink": 2},
    "middle": {"pottage": 1, "main": 2, "side": 1, "sweet": 1, "drink": 2},
    "high": {"pottage": 2, "main": 3, "side": 1, "sweet": 2, "drink": 2},
}


@dataclass(frozen=True)
class Dish:
    name: str
    tavern_class: str
    course: str
    meat: bool
    price: float
    description: str


_dishes: Optional[List[Dish]] = None


def load_dishes(path: str = DISHES_PATH) -> List[Dish]:
    """Every dish in the file; rows with an unknown class or course are skipped with a warning."""
    courses = {course for course, _ in COURSES}
    dishes = []
    with open(path, newline="", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            tavern_class = row["class"].strip().lower()
            course = row["course"].strip().lower()
            if tavern_class not in TAVERN_CLASSES or course not in courses:
                print(f"Warning: dish {row['dish']!r} has an unknown class or course, skipped")
                continue
            dishes.append(Dish(
                name=row["dish"].strip(),
                tavern_class=tavern_class,
                course=course,
                meat=row["meat"].strip().lower() == "yes",
                price=float(row["price"]),
                description=row["description"].strip(),
            ))
    return dishes


def all_dishes() -> List[Dish]:
    """The dishes, read once."""
    global _dishes
    if _dishes is None:
        _dishes = load_dishes()
    return _dishes


def daily_menu(day: datetime.date, tavern_class: str, tavern_key: str,
               dishes: Optional[List[Dish]] = None) -> List[Tuple[str, List[Dish]]]:
    """The courses a tavern offers on a day, each with its dishes, in menu order.

    tavern_key tells taverns of the same class apart, so they do not all serve
    the same. A course with fewer dishes on offer than asked for gets them all;
    one with none is left out.
    """
    if dishes is None:
        dishes = all_dishes()
    fasting = is_fast_day(day)
    rng = random.Random(f"{day.isoformat()}:{tavern_key}")
    menu = []
    for course, _heading in COURSES:
        wanted = MENU_COURSES.get(tavern_class, {}).get(course, 0)
        offer = [dish for dish in dishes
                 if dish.tavern_class == tavern_class and dish.course == course
                 and not (fasting and dish.meat)]
        chosen = rng.sample(offer, min(wanted, len(offer)))
        if chosen:
            menu.append((course, chosen))
    return menu
