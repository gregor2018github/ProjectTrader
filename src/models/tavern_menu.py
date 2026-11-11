"""The daily menu a tavern offers, drawn from the dishes in assets/texts/taverns/dishes.csv.

Each dish there has a class (low, middle or high: which kind of tavern serves
it), a course, whether it has meat and its price in coins. A tavern's class is the `Tavern`
property on its building in Tiled. Its menu is drawn anew each day from the
dishes of its class: `MENU_SIZE` dishes (2 or 3), the first a main dish
(`HEARTY_COURSES`) and the rest each from another course, the same all day and
different from tavern to tavern. On fast days, every Friday and Lent (both by the
game calendar, `game_calendar.is_fast_day`), no meat is served.

A dish may have a picture, `assets/pictures/dish_<name in snake case>.png`
(`dish_picture_path`), shown when the player orders it.
"""

import csv
import datetime
import os
import random
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from ..config.constants import MAIN_PATH, PICTURES_PATH
from ..sim.calendar import is_fast_day

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

# How many dishes a tavern offers a day, drawn anew each day between the two
MENU_SIZE: Tuple[int, int] = (2, 3)

# The courses the first dish of the day comes from, the first with something on offer
HEARTY_COURSES: Tuple[str, ...] = ("main", "pottage")


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


def dish_key(dish: Dish) -> str:
    """The dish's name in snake case, as its picture's file is named and the tried dishes are kept."""
    return re.sub(r"[^a-z0-9]+", "_", dish.name.lower()).strip("_")


def dish_picture_path(dish: Dish) -> str:
    """Where the dish's picture would be; it need not exist."""
    return os.path.join(PICTURES_PATH, f"dish_{dish_key(dish)}.png")


def daily_menu(day: datetime.date, tavern_class: str, tavern_key: str,
               dishes: Optional[List[Dish]] = None) -> List[Tuple[str, List[Dish]]]:
    """The courses a tavern offers on a day, each with its dish, in menu order.

    Between `MENU_SIZE`'s two dishes: one from the first of `HEARTY_COURSES`
    with something on offer, the rest each from another course (never two of a
    course). tavern_key tells taverns of the same class apart, so they do not
    all serve the same. Fewer courses on offer than wanted give fewer dishes.
    """
    if dishes is None:
        dishes = all_dishes()
    fasting = is_fast_day(day)
    rng = random.Random(f"{day.isoformat()}:{tavern_key}")
    offers = {}
    for course, _heading in COURSES:
        offer = [dish for dish in dishes
                 if dish.tavern_class == tavern_class and dish.course == course
                 and not (fasting and dish.meat)]
        if offer:
            offers[course] = offer
    if not offers:
        return []
    size = rng.randint(*MENU_SIZE)
    hearty = next((course for course in HEARTY_COURSES if course in offers), None)
    others = [course for course in offers if course != hearty]
    courses = ([hearty] if hearty else []) + rng.sample(others, min(len(others), size - (1 if hearty else 0)))
    chosen = {course: rng.choice(offers[course]) for course in courses}
    return [(course, [chosen[course]]) for course, _heading in COURSES if course in chosen]
