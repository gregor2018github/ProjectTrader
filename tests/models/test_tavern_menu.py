"""The tavern's daily menu: the dish file, fast days, and how the day's dishes are drawn."""

import datetime

import pytest

from src.models import tavern_menu
from src.sim.calendar import EPOCH
from src.models.tavern_menu import COURSES, TAVERN_CLASSES, Dish, daily_menu, load_dishes

# Pinned so that changing how much a tavern serves does not break the tests
MENU = {
    "middle": {"pottage": 1, "main": 2, "side": 0, "sweet": 0, "drink": 1},
}

DISHES = [
    Dish("Hochepot", "middle", "pottage", True, 1.0, ""),
    Dish("Funges", "middle", "pottage", False, 1.0, ""),
    Dish("Beef Y-stewed", "middle", "main", True, 1.0, ""),
    Dish("Bratwurst", "middle", "main", True, 1.0, ""),
    Dish("Eels in Green Sauce", "middle", "main", False, 1.0, ""),
    Dish("Ale", "middle", "drink", False, 1.0, ""),
    Dish("Hippocras", "high", "drink", False, 1.0, ""),
]

MONDAY = datetime.date(1500, 1, 8)
FRIDAY = datetime.date(1500, 1, 5)


@pytest.fixture(autouse=True)
def pinned_menu(monkeypatch):
    monkeypatch.setattr(tavern_menu, "MENU_COURSES", MENU)


def names(menu):
    return {course: [dish.name for dish in dishes] for course, dishes in menu}


def test_the_dish_file_reads_and_serves_every_class_every_course():
    dishes = load_dishes()
    for tavern_class in TAVERN_CLASSES:
        for course, _ in COURSES:
            offer = [d for d in dishes if d.tavern_class == tavern_class and d.course == course]
            assert offer, f"no {course} for a {tavern_class} tavern"
            # Something to serve on fast days too
            assert any(not d.meat for d in offer), f"no meatless {course} for a {tavern_class} tavern"
    assert all(dish.price > 0 for dish in dishes)


def test_no_meat_in_lent_even_midweek():
    lent_thursday = EPOCH + datetime.timedelta(days=24)     # the 4th of Winter
    assert lent_thursday.weekday() == 3
    menu = daily_menu(lent_thursday, "middle", "inn", DISHES)
    assert names(menu) == {"pottage": ["Funges"], "main": ["Eels in Green Sauce"], "drink": ["Ale"]}


def test_a_tavern_serves_its_class_in_menu_order():
    menu = daily_menu(MONDAY, "middle", "inn", DISHES)
    assert [course for course, _ in menu] == ["pottage", "main", "drink"]
    served = names(menu)
    assert len(served["pottage"]) == 1
    assert len(served["main"]) == 2
    assert served["drink"] == ["Ale"]


def test_no_meat_on_a_fast_day():
    menu = daily_menu(FRIDAY, "middle", "inn", DISHES)
    assert names(menu) == {"pottage": ["Funges"], "main": ["Eels in Green Sauce"], "drink": ["Ale"]}


def test_the_menu_holds_all_day_and_changes_between_days():
    noon = daily_menu(MONDAY, "middle", "inn", DISHES)
    assert daily_menu(MONDAY, "middle", "inn", DISHES) == noon
    days = [MONDAY + datetime.timedelta(days=n) for n in range(4)]  # Monday to Thursday
    assert len({str(names(daily_menu(day, "middle", "inn", DISHES))) for day in days}) > 1


def test_taverns_of_the_same_class_serve_differently():
    days = [MONDAY + datetime.timedelta(days=n) for n in range(4)]
    assert any(daily_menu(day, "middle", "inn", DISHES) != daily_menu(day, "middle", "alehouse", DISHES)
               for day in days)


def test_an_unknown_class_serves_nothing():
    assert daily_menu(MONDAY, "royal", "inn", DISHES) == []
