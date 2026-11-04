"""goods.json and recipes.json load, and every mistake names its file, entry and field."""
import json

import pytest

from src.sim.data import (
    DataError, GoodDef, load_goods, load_recipes, parse_goods, parse_recipes,
)

WOOD = {"name": "Wood", "start_price": 1, "start_quantity": 5000, "color": "PALE_BROWN",
        "chart_index": 0, "show_in_charts": True}
STONE = {"name": "Stone", "start_price": 2, "start_quantity": 2000, "color": "GRAY",
         "chart_index": 1, "show_in_charts": False}
RECIPE = {"id": "cut_stone", "inputs": {"Wood": 1}, "outputs": {"Stone": 2}, "labour": 1, "days": 0.5}


def test_the_games_files_load():
    goods = load_goods()
    assert [g.name for g in goods][:3] == ["Wood", "Stone", "Iron"]
    assert len({g.chart_index for g in goods}) == len(goods)
    recipes = load_recipes([g.name for g in goods])
    assert recipes and all(r.outputs for r in recipes)


def test_a_good_entry_becomes_a_definition():
    assert parse_goods([WOOD]) == [GoodDef("Wood", 1.0, 5000, "PALE_BROWN", 0, True)]


@pytest.mark.parametrize("change, field, problem", [
    ({"start_price": "x"}, "start_price", "expected a number > 0, got 'x'"),
    ({"start_price": 0}, "start_price", "expected a number > 0"),
    ({"start_quantity": 2.5}, "start_quantity", "expected a whole number >= 1"),
    ({"show_in_charts": 1}, "show_in_charts", "expected true or false"),
    ({"color": ""}, "color", "expected a non-empty string"),
    ({"colour": "RED"}, "colour", "unknown field"),
])
def test_a_bad_field_is_named_with_its_entry(change, field, problem):
    with pytest.raises(DataError) as error:
        parse_goods([WOOD, {**STONE, **change}])
    message = str(error.value)
    assert message.startswith(f"goods.json, entry 1 ('Stone'): field '{field}': ")
    assert problem in message


def test_a_missing_field_is_named():
    stone = dict(STONE)
    del stone["start_quantity"]
    with pytest.raises(DataError, match=r"entry 1 \('Stone'\): field 'start_quantity': missing"):
        parse_goods([WOOD, stone])


def test_repeated_names_and_chart_places_are_refused():
    with pytest.raises(DataError, match="'Wood' is already entry 0"):
        parse_goods([WOOD, {**STONE, "name": "Wood"}])
    with pytest.raises(DataError, match="0 is already used by entry 0"):
        parse_goods([WOOD, {**STONE, "chart_index": 0}])


def test_a_recipe_must_name_known_goods_and_make_something():
    assert parse_recipes([RECIPE], {"Wood", "Stone"})[0].days == 0.5
    with pytest.raises(DataError, match=r"recipes.json, entry 0 \('cut_stone'\): field 'inputs': unknown good 'Gold'"):
        parse_recipes([{**RECIPE, "inputs": {"Gold": 1}}], {"Wood", "Stone"})
    with pytest.raises(DataError, match="field 'outputs': expected an object of good -> units \\(at least one\\)"):
        parse_recipes([{**RECIPE, "outputs": {}}], {"Wood", "Stone"})
    with pytest.raises(DataError, match="field 'days': expected a number > 0"):
        parse_recipes([{**RECIPE, "days": 0}], {"Wood", "Stone"})
    with pytest.raises(DataError, match="field 'inputs': 'Wood': expected a whole number >= 1"):
        parse_recipes([{**RECIPE, "inputs": {"Wood": -1}}], {"Wood", "Stone"})


def test_broken_and_missing_files_say_which(tmp_path):
    (tmp_path / "goods.json").write_text("{ not json", encoding="utf-8")
    with pytest.raises(DataError, match="goods.json: not valid JSON"):
        load_goods(str(tmp_path))
    (tmp_path / "goods.json").write_text(json.dumps({"goods": {}}), encoding="utf-8")
    with pytest.raises(DataError, match="goods.json: expected an object with a list 'goods'"):
        load_goods(str(tmp_path))
    with pytest.raises(DataError, match="recipes.json: not found"):
        load_recipes({"Wood"}, str(tmp_path))
