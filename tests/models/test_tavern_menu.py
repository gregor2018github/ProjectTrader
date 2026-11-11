"""The tavern's daily menu: the dish file, fast days, and how the day's dishes are drawn."""

import datetime

import pytest

from src.models import tavern_menu
from src.sim.calendar import EPOCH
from src.models.statistics import Statistics
from src.models.tavern_menu import (
    COURSES, TAVERN_CLASSES, Dish, daily_menu, dish_key, dish_picture_path, load_dishes,
)

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
    # Pinned so that changing how much a tavern serves does not break the tests
    monkeypatch.setattr(tavern_menu, "MENU_SIZE", (2, 3))
    monkeypatch.setattr(tavern_menu, "HEARTY_COURSES", ("main", "pottage"))


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


DAYS = [MONDAY + datetime.timedelta(days=n) for n in range(28)]


def test_no_meat_in_lent_even_midweek():
    lent_thursday = EPOCH + datetime.timedelta(days=24)     # the 4th of Winter
    assert lent_thursday.weekday() == 3
    menu = daily_menu(lent_thursday, "middle", "inn", DISHES)
    served = names(menu)
    assert served["main"] == ["Eels in Green Sauce"]
    assert served.get("pottage", ["Funges"]) == ["Funges"]


def test_two_or_three_dishes_a_main_first_and_one_per_course():
    sizes = set()
    for day in DAYS:
        menu = daily_menu(day, "middle", "inn", DISHES)
        assert [course for course, _ in menu] == [c for c, _ in COURSES if c in dict(menu)]
        assert "main" in dict(menu)
        assert all(len(dishes) == 1 for _, dishes in menu)
        sizes.add(len(menu))
    assert sizes == {2, 3}


def test_the_whole_dish_file_serves_two_or_three_a_day():
    for tavern_class in TAVERN_CLASSES:
        for day in DAYS:
            assert 2 <= sum(len(d) for _, d in daily_menu(day, tavern_class, "inn")) <= 3


def test_no_meat_on_a_fast_day():
    menu = daily_menu(FRIDAY, "middle", "inn", DISHES)
    assert not any(dish.meat for _, dishes in menu for dish in dishes)
    assert names(menu)["main"] == ["Eels in Green Sauce"]


def test_the_menu_holds_all_day_and_changes_between_days():
    noon = daily_menu(MONDAY, "middle", "inn", DISHES)
    assert daily_menu(MONDAY, "middle", "inn", DISHES) == noon
    assert len({str(names(daily_menu(day, "middle", "inn", DISHES))) for day in DAYS[:4]}) > 1


def test_taverns_of_the_same_class_serve_differently():
    assert any(daily_menu(day, "middle", "inn", DISHES) != daily_menu(day, "middle", "alehouse", DISHES)
               for day in DAYS[:4])


def test_an_unknown_class_serves_nothing():
    assert daily_menu(MONDAY, "royal", "inn", DISHES) == []


def test_a_dish_picture_is_named_after_the_dish():
    pigeons = Dish("Roast Pigeons", "middle", "main", True, 5.0, "")
    assert dish_key(pigeons) == "roast_pigeons"
    assert dish_picture_path(pigeons).endswith("dish_roast_pigeons.png")
    assert dish_key(Dish("Eels in Green-Sauce!", "low", "main", False, 1.0, "")) == "eels_in_green_sauce"


def test_the_dishes_tried_are_counted_and_saved():
    stats = Statistics()
    assert stats.record_dish("roast_pigeons") is True
    assert stats.record_dish("roast_pigeons") is False
    assert stats.record_dish("ale") is True
    restored = Statistics.from_dict(stats.to_dict())
    assert restored.dishes_tried == {"roast_pigeons": 2, "ale": 1}
    assert Statistics.from_dict({}).dishes_tried == {}
