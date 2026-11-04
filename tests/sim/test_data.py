"""goods.json, needs.json and recipes.json load, and every mistake names its file, entry and field."""
import json

import pytest

from src.sim.data import (
    DataError, load_buildings, load_goods, load_needs, load_recipes, load_scenario, parse_buildings,
    parse_goods, parse_needs, parse_recipes, parse_scenario,
)
from src.sim.systems.population import class_shares

WOOD = {"name": "Wood", "color": "PALE_BROWN", "chart_index": 0, "show_in_charts": True,
        "outside_price": 1, "outside_reversion": 0.03, "outside_volatility": 0.03,
        "transport_cost": 0.3, "import_limit": 100, "export_limit": 100,
        "target_stock_days": 14, "min_target_stock": 50, "noise_sigma": 0.004}
STONE = {**WOOD, "name": "Stone", "chart_index": 1, "outside_price": 2}
RECIPE = {"id": "cut_stone", "inputs": {"Wood": 1, "Stone": 0.05}, "outputs": {"Stone": 2}, "labour": 1.5}
BUILDING = {"type": "mason", "name": "Mason", "recipe": "cut_stone", "workers_class": "Commons",
            "max_capacity": 10, "growth_cost": 100, "working_capital": 50}
SCENARIO = {"owners": [{"id": "town", "kind": "town", "name": "The town", "cash": 100, "reserve": 50,
                        "surplus_to": "townsfolk"}],
            "workshops": [{"id": "mason", "owner": "town", "building": "mason", "capacity": 2, "cash": 50}]}
POOR = {"class": "Poor", "base_income": 0.5, "labour_share": 0.6, "wage_cap": 1.0,
        "happiness_weights": {"basic": 0.75, "comfort": 0.2, "luxury": 0.05},
        "basic": {"Wood": 0.1}, "comfort": {}, "luxury": {"Stone": {"units": 0.01, "seasons": {"Winter": 2}}}}
CLASSES = [c for c, _ in class_shares()]


def test_the_games_files_load():
    goods = load_goods()
    names = [g.name for g in goods]
    assert names[:3] == ["Wood", "Stone", "Iron"]
    assert len({g.chart_index for g in goods}) == len(goods)
    needs = load_needs(names, CLASSES)
    assert [n.name for n in needs] == CLASSES
    recipes = load_recipes(names)
    buildings = load_buildings([r.id for r in recipes], CLASSES)
    scenario = load_scenario("home_town", [b.type for b in buildings])
    assert scenario.workshops and all(w.owner == "town" for w in scenario.workshops)


def test_a_good_entry_becomes_a_definition():
    wood = parse_goods([{**WOOD, "outside_seasons": {"Winter": 1.2}}])[0]
    assert (wood.name, wood.outside_price, wood.transport_cost, wood.outside_seasons) == ("Wood", 1.0, 0.3, {"Winter": 1.2})


@pytest.mark.parametrize("change, field, problem", [
    ({"outside_price": "x"}, "outside_price", "expected a number > 0, got 'x'"),
    ({"outside_price": 0}, "outside_price", "expected a number > 0"),
    ({"outside_reversion": 1.5}, "outside_reversion", "expected a number >= 0 and <= 1"),
    ({"import_limit": -1}, "import_limit", "expected a number >= 0"),
    ({"show_in_charts": 1}, "show_in_charts", "expected true or false"),
    ({"color": ""}, "color", "expected a non-empty string"),
    ({"colour": "RED"}, "colour", "unknown field"),
    ({"outside_seasons": {"Monsoon": 1.1}}, "outside_seasons", "unknown season 'Monsoon'"),
])
def test_a_bad_good_field_is_named_with_its_entry(change, field, problem):
    with pytest.raises(DataError) as error:
        parse_goods([WOOD, {**STONE, **change}])
    message = str(error.value)
    assert message.startswith(f"goods.json, entry 1 ('Stone'): field '{field}': ")
    assert problem in message


def test_a_missing_field_is_named():
    stone = dict(STONE)
    del stone["target_stock_days"]
    with pytest.raises(DataError, match=r"entry 1 \('Stone'\): field 'target_stock_days': missing"):
        parse_goods([WOOD, stone])


def test_repeated_names_and_chart_places_are_refused():
    with pytest.raises(DataError, match="'Wood' is already entry 0"):
        parse_goods([WOOD, {**STONE, "name": "Wood"}])
    with pytest.raises(DataError, match="0 is already used by entry 0"):
        parse_goods([WOOD, {**STONE, "chart_index": 0}])


def test_a_class_entry_becomes_needs_with_seasons():
    poor = parse_needs([POOR], {"Wood", "Stone"})[0]
    assert poor.tiers["basic"][0].units == 0.1
    assert poor.tiers["luxury"][0].seasons == {"Winter": 2.0}


@pytest.mark.parametrize("change, field, problem", [
    ({"basic": {"Gold": 0.1}}, "basic", "unknown good 'Gold'"),
    ({"basic": {"Wood": 0}}, "basic", "'Wood': expected a number > 0"),
    ({"basic": {"Wood": {"units": 0.1, "seasons": {"Winter": -1}}}}, "basic.Wood.seasons", "'Winter': expected a number > 0"),
    ({"happiness_weights": {"basic": 0.5, "comfort": 0.2, "luxury": 0.1}}, "happiness_weights", "must add up to 1"),
    ({"happiness_weights": {"basic": 1.0}}, "happiness_weights", "expected an object with exactly basic, comfort, luxury"),
    ({"labour_share": 2}, "labour_share", "expected a number >= 0 and <= 1"),
    ({"wage_cap": 0.4}, "wage_cap", "expected a number >= 0.5"),             # never below its base income
])
def test_a_bad_class_field_is_named(change, field, problem):
    with pytest.raises(DataError) as error:
        parse_needs([{**POOR, **change}], {"Wood", "Stone"})
    assert str(error.value).startswith(f"needs.json, entry 0 ('Poor'): field '{field}': ")
    assert problem in str(error.value)


def test_unknown_and_missing_classes_are_refused():
    with pytest.raises(DataError, match="unknown class 'Peasants'"):
        parse_needs([{**POOR, "class": "Peasants"}], {"Wood", "Stone"}, CLASSES)
    with pytest.raises(DataError, match="no entry for the class\\(es\\) Commons, Middling Sort, Nobility"):
        parse_needs([POOR], {"Wood", "Stone"}, CLASSES)


def test_a_recipe_must_name_known_goods_and_make_something():
    assert parse_recipes([RECIPE], {"Wood", "Stone"})[0].inputs == {"Wood": 1.0, "Stone": 0.05}   # wear as a fraction
    with pytest.raises(DataError, match=r"recipes.json, entry 0 \('cut_stone'\): field 'inputs': unknown good 'Gold'"):
        parse_recipes([{**RECIPE, "inputs": {"Gold": 1}}], {"Wood", "Stone"})
    with pytest.raises(DataError, match="field 'outputs': expected an object of good -> units \\(at least one\\)"):
        parse_recipes([{**RECIPE, "outputs": {}}], {"Wood", "Stone"})
    with pytest.raises(DataError, match="field 'inputs': 'Wood': expected a number > 0"):
        parse_recipes([{**RECIPE, "inputs": {"Wood": 0}}], {"Wood", "Stone"})
    with pytest.raises(DataError, match="field 'days': unknown field"):
        parse_recipes([{**RECIPE, "days": 1}], {"Wood", "Stone"})


def test_a_building_must_name_a_known_recipe_and_class():
    assert parse_buildings([BUILDING], {"cut_stone"}, CLASSES)[0].max_capacity == 10.0
    with pytest.raises(DataError, match=r"buildings.json, entry 0 \('mason'\): field 'recipe': unknown recipe 'carve'"):
        parse_buildings([{**BUILDING, "recipe": "carve"}], {"cut_stone"}, CLASSES)
    with pytest.raises(DataError, match="field 'workers_class': unknown class 'Serfs'"):
        parse_buildings([{**BUILDING, "workers_class": "Serfs"}], {"cut_stone"}, CLASSES)


def test_a_scenario_must_name_known_owners_and_buildings():
    assert parse_scenario(SCENARIO, {"mason"}, "scenarios/t.json").workshops[0].capacity == 2.0
    bad_owner = {**SCENARIO, "workshops": [{**SCENARIO["workshops"][0], "owner": "guild"}]}
    with pytest.raises(DataError, match=r"scenarios/t.json workshops, entry 0 \('mason'\): field 'owner': unknown owner 'guild'"):
        parse_scenario(bad_owner, {"mason"}, "scenarios/t.json")
    bad_rule = {**SCENARIO, "owners": [{**SCENARIO["owners"][0], "surplus_to": "church"}]}
    with pytest.raises(DataError, match="field 'surplus_to': expected one of keep, townsfolk"):
        parse_scenario(bad_rule, {"mason"}, "scenarios/t.json")


def test_broken_and_missing_files_say_which(tmp_path):
    (tmp_path / "goods.json").write_text("{ not json", encoding="utf-8")
    with pytest.raises(DataError, match="goods.json: not valid JSON"):
        load_goods(str(tmp_path))
    (tmp_path / "goods.json").write_text(json.dumps({"goods": {}}), encoding="utf-8")
    with pytest.raises(DataError, match="goods.json: expected an object with a list 'goods'"):
        load_goods(str(tmp_path))
    with pytest.raises(DataError, match="needs.json: not found"):
        load_needs({"Wood"}, folder=str(tmp_path))
