"""The pen's hens lay into the coop's nesting box and the keeper fetches the eggs once a day and sells them
(models/chicken_eggs.py, npcs/pen_keeper.py, Simulation.sell_from_townsfolk), and the nesting box's sheet
(ui/helper_modules/nest_window.py)."""

import datetime
import os
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from src.models import chicken_eggs as ce
from src.models.chicken_eggs import Nest, laying_rate
from src.models.chicken_troughs import FEED, WATER, Troughs
from src.models.figurines.humans.npcs import homebody as homebody_module
from src.models.figurines.humans.npcs import pen_keeper as keeper_module
from src.models.figurines.humans.npcs.homebody import IN_YARD, LINGERING
from src.models.figurines.humans.npcs.pen_keeper import NestBox, PenKeeper
from src.models.figurines.patrol_path import PatrolPath

ROOT = Path(__file__).resolve().parents[2]
SPRING = datetime.datetime(1500, 1, 1, 6, 0)            # the calendar's first day: Spring
FRAME = 1 / 30


@pytest.fixture(autouse=True)
def pinned(monkeypatch):
    monkeypatch.setattr(ce, "LAY_PER_DAY", {"Spring": 0.8, "Summer": 0.7, "Autumn": 0.5, "Winter": 0.2})
    monkeypatch.setattr(ce, "STAGE_SHARE", {"Chick": 0.0, "Young hen": 0.5, "Hen": 1.0, "Old hen": 0.5})
    monkeypatch.setattr(ce, "HUNGRY_SHARE", 0.3)
    monkeypatch.setattr(ce, "THIRSTY_SHARE", 0.3)
    monkeypatch.setattr(ce, "NEST_CAP", 40)
    monkeypatch.setattr(ce, "EGGS_PER_UNIT", 12)
    monkeypatch.setattr(homebody_module, "sun_hour", lambda t: t.hour + t.minute / 60.0)
    monkeypatch.setattr(homebody_module, "OUT_WINDOW", (7.0, 7.0))
    monkeypatch.setattr(homebody_module, "IN_WINDOW", (19.0, 19.0))
    monkeypatch.setattr(homebody_module, "IDLE_MIN_MINUTES", 5)
    monkeypatch.setattr(homebody_module, "IDLE_MAX_MINUTES", 5)
    monkeypatch.setattr(keeper_module, "COLLECT_HOURS", (9.0, 9.0))
    monkeypatch.setattr(keeper_module, "COLLECT_MINUTES", (4.0, 4.0))


# -- laying -----------------------------------------------------------------------------

def test_hens_lay_by_season_and_stage_and_fewer_without_grain_or_water():
    hens = ["Hen", "Hen", "Young hen", "Old hen", "Chick"]
    assert laying_rate(hens, "Spring") == pytest.approx(0.8 * 3)
    assert laying_rate(hens, "Winter") == pytest.approx(0.2 * 3)
    assert laying_rate(hens, "Spring", fed=False) == pytest.approx(0.8 * 3 * 0.3)
    assert laying_rate(hens, "Spring", fed=False, watered=False) == pytest.approx(0.8 * 3 * 0.09)
    assert laying_rate(["Chick"] * 5, "Spring") == 0


def test_the_eggs_gather_in_the_nest_up_to_its_cap():
    nest = Nest()
    nest.update(SPRING, ["Hen"] * 5)                     # the first update only starts the count
    assert nest.eggs == 0
    nest.update(SPRING + datetime.timedelta(days=1), ["Hen"] * 5)
    assert nest.eggs == pytest.approx(4.0) and nest.whole == 4 and nest.rate == pytest.approx(4.0)
    nest.update(SPRING + datetime.timedelta(days=30), ["Hen"] * 5)
    assert nest.eggs == 40


def test_the_keeper_fetches_the_whole_eggs_once_a_day():
    nest = Nest()
    nest.eggs = 5.6
    day = SPRING.date()
    assert nest.collect(day) == 5 and nest.eggs == pytest.approx(0.6)
    nest.eggs = 3.0
    assert not nest.can_collect(day) and nest.collect(day) == 0 and nest.eggs == 3.0
    assert nest.collect(day + datetime.timedelta(days=1)) == 3
    assert (nest.last_collected, nest.collected_total) == (3, 8)


def test_the_save_keeps_the_nest_and_an_older_save_has_it_empty():
    nest = Nest()
    nest.eggs = 2.5
    nest.collect(SPRING.date())
    again = Nest()
    again.load(nest.to_save())
    assert (again.eggs, again.collected_on, again.last_collected, again.collected_total) == \
        (pytest.approx(0.5), SPRING.date(), 2, 2)
    again.load(None)
    assert again.eggs == 0 and again.collected_on is None
    again.load({"eggs": "lots"})
    assert again.eggs == 0


def test_the_troughs_say_whether_they_hold_grain_or_water():
    troughs = Troughs(["a", "b"])
    assert not troughs.holds(FEED) and not troughs.holds(WATER)
    troughs.keeper_fill("a", FEED)
    assert troughs.holds(FEED) and not troughs.holds(WATER)


# -- the keeper ---------------------------------------------------------------------------

def _keeper(nest, got):
    pygame.display.init()
    pygame.display.set_mode((1, 1))
    door = SimpleNamespace(id=7, entry=(100.0, 100.0), step=(100.0, 110.0), facing_in="back", facing_out="front")
    keeper = PenKeeper("commons_testric", {"name": "Testric", "gender": "male", "home": "Shed",
                                           "keeps": "chicken_pen", "stand_in": "commons_edric"}, 32)
    yard = PatrolPath([(60.0, 140.0), (340.0, 140.0), (340.0, 300.0), (60.0, 300.0)], closed=True)
    keeper.settle(door, yard, [], lambda a, b: [a, b])
    pen = Troughs([])
    keeper.look_after(pen)
    keeper.fetch_eggs((250.0, 170.0), nest, got.append)
    return keeper


def _work_day(keeper):
    day = SPRING
    while keeper.day_off(day.date()):
        day += datetime.timedelta(days=1)
    return day


def _run(keeper, now, minutes, until):
    step = datetime.timedelta(minutes=1) / 12
    for _ in range(minutes * 12):
        keeper.update(FRAME, now)
        if until(keeper):
            break
        now += step
    return now


def test_from_his_hour_he_walks_to_the_nesting_box_and_fetches_the_eggs_once():
    nest = Nest()
    nest.eggs = 6.3
    got = []
    keeper = _keeper(nest, got)
    day = _work_day(keeper)
    now = _run(keeper, day.replace(hour=8), 2, lambda k: False)
    now = _run(keeper, now, 50, lambda k: k.chore is not None)
    assert keeper.chore is None and not got                  # not before nine
    now = _run(keeper, now, 300, lambda k: isinstance(k.chore, NestBox))
    assert now.hour >= 9
    now = _run(keeper, now, 300, lambda k: k.state == LINGERING)
    assert keeper.feet == pytest.approx((250.0, 170.0), abs=1.5) and got == [6]
    keeper.update(FRAME, now)
    assert keeper.animator.current_direction == "back"         # facing the nesting box
    nest.eggs = 4.0
    _run(keeper, now, 400, lambda k: False)
    assert got == [6] and keeper.state == IN_YARD             # once a day


def test_unseen_he_fetches_them_at_once_but_only_after_his_hour():
    nest = Nest()
    nest.eggs = 3.0
    got = []
    keeper = _keeper(nest, got)
    day = _work_day(keeper)
    keeper.see_to_unseen(day.replace(hour=8))
    assert not got
    keeper.see_to_unseen(day.replace(hour=10))
    assert got == [3]
    keeper.see_to_unseen(day.replace(hour=11))
    assert got == [3]


# -- the market ----------------------------------------------------------------------------

def test_his_eggs_are_sold_to_the_merchants_for_his_class_and_the_books_still_balance():
    from src.sim import Simulation
    from src.sim.run import load_definitions
    from tests.sim.builders import START, TOWN
    definitions, scenario = load_definitions()
    sim = Simulation(definitions, now=START, seed=1, town=TOWN, scenario=scenario)
    sim.presimulate(2)
    commons = sim.state.population.classes["Commons"]
    purse, stock = commons.purse, sim.good("Eggs").stock
    paid = sim.sell_from_townsfolk("Eggs", 0.5, "Commons")
    assert paid > 0 and commons.purse == pytest.approx(purse + paid)
    assert sim.good("Eggs").stock == pytest.approx(stock + 0.5)
    assert sim.sell_from_townsfolk("Eggs", 0, "Commons") == 0 and sim.sell_from_townsfolk("Amber", 1, "Commons") == 0
    sim.advance(datetime.timedelta(days=1))
    assert abs(sim.state.money_yesterday.market_balance) < 1e-6


# -- the map and the sheet -------------------------------------------------------------------

def test_the_coop_on_the_map_has_its_nesting_box():
    root = ET.parse(ROOT / "assets/tiles/Map1.tmx").getroot()
    coop = next(o for o in root.iter("object") if o.get("name") == "Chicken_Coop" and o.get("type"))
    props = {p.get("name"): p.get("value") for p in coop.iter("property")}
    x, y = (float(v) for v in props["Nest_box"].split(","))
    assert 0 <= x <= 327 and 0 <= y <= 335                   # in the coop sprite's own pixels


def test_the_coop_menu_opens_the_nesting_box_sheet_which_tells_what_lies_in_it():
    from src.models.chicken_coop import Coop
    from src.ui.helper_modules.nest_window import OPTION, NestWindow, is_nest_coop
    pygame.init()
    screen = pygame.display.set_mode((1, 1))
    nest = Nest()
    nest.eggs = 7.2
    nest.collect(SPRING.date())
    nest.eggs = 2.0
    coop = Coop("Chicken_Coop", 20, (0, 0), (0, 0), 0.0, (0, 0, 1, 1), (10.0, 10.0))
    troughs = Troughs(["a"])
    game = SimpleNamespace(nest=nest, troughs=troughs,
                           game_map=SimpleNamespace(tmx_map=SimpleNamespace(chicken_coop=coop,
                                                                            pen_keeper=SimpleNamespace(name="Edric"))))
    house = SimpleNamespace(name="Chicken_Coop")
    state = SimpleNamespace(game=game, date=SPRING, screen=pygame.Surface((1920, 1080)), info_window=None,
                            active_house_menu=None, menu_fade_window=None, menu_fade_timer=0, menu_fade_duration=0.2)
    window = NestWindow(state.screen, state, house)
    told = dict(window.lines())
    assert told["In the nest"] == "2 eggs" and told["Fetched"] == "7 eggs by Edric, today"
    assert "grain or water" in window.note()
    troughs.keeper_fill("a", FEED)
    assert "water" in window.note() and "grain" not in window.note()
    state.info_window = window
    window.draw()
    assert window.handle_click(window.button_rect().center) and state.info_window is None
    assert is_nest_coop(state, house) and not is_nest_coop(state, SimpleNamespace(name="Barn")) and OPTION == "Look in the Nesting Box"
