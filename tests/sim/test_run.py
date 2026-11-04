"""The headless runner: same seed, same files byte for byte; another seed, other files."""
import json

import pytest

from src.sim import TownSpec
from src.sim.run import (
    GOODS_FILE, META_FILE, POPULATION_FILE, TOWN_FILE, WORKSHOPS_FILE, load_definitions, main, write_run,
)
from src.sim.scenario import tmx_town

TOWN = TownSpec([6, 8, 4, 12, 5, 7, 9, 3, 10])


DEFINITIONS, SCENARIO = load_definitions()


def run(path, seed):
    write_run(str(path), years=0.5, seed=seed, definitions=DEFINITIONS, town=TOWN, scenario=SCENARIO, presim_days=2)
    return {name: (path / name).read_bytes() for name in (GOODS_FILE, POPULATION_FILE, WORKSHOPS_FILE, TOWN_FILE)}


def test_the_same_seed_writes_the_same_files_and_another_seed_others(tmp_path):
    first = run(tmp_path / "a", seed=1)
    again = run(tmp_path / "b", seed=1)
    other = run(tmp_path / "c", seed=2)
    assert first == again
    assert first[GOODS_FILE] != other[GOODS_FILE]
    assert first[POPULATION_FILE] != other[POPULATION_FILE]


def test_the_files_are_tidy_and_the_meta_complete(tmp_path):
    write_run(str(tmp_path), years=0.25, seed=5, definitions=DEFINITIONS, town=TOWN, scenario=SCENARIO, presim_days=0)
    goods_lines = (tmp_path / GOODS_FILE).read_text(encoding="utf-8").splitlines()
    assert goods_lines[0].startswith("day,year,season,day_of_season,good,price,outside_price")
    days, n_goods = 7, len(DEFINITIONS.goods)
    assert len(goods_lines) == 1 + days * n_goods
    pop_lines = (tmp_path / POPULATION_FILE).read_text(encoding="utf-8").splitlines()
    assert len(pop_lines) == 1 + days * 5                         # four classes and "All"
    meta = json.loads((tmp_path / META_FILE).read_text(encoding="utf-8"))
    assert meta["seed"] == 5 and meta["days"] == days
    assert "MARKET_VOLUME_ELASTICITY" in meta["constants"] and "SAVINGS_CAP_DAYS" in meta["constants"]
    assert [n["name"] for n in meta["definitions"]["needs"]] == ["Poor", "Commons", "Middling Sort", "Nobility"]
    assert meta["scenario"]["name"] == "home_town"
    workshop_lines = (tmp_path / WORKSHOPS_FILE).read_text(encoding="utf-8").splitlines()
    assert len(workshop_lines) == 1 + days * len(SCENARIO.workshops)
    assert len((tmp_path / TOWN_FILE).read_text(encoding="utf-8").splitlines()) == 1 + days
    assert meta["runtime_seconds"]["total"] >= 0


def test_the_command_line_runs_on_the_maps_town(tmp_path, capsys):
    assert main(["--years", "0.25", "--seed", "3", "--out", str(tmp_path), "--presim-days", "0"]) == 0
    assert "7 days" in capsys.readouterr().out
    assert (tmp_path / GOODS_FILE).exists()


def test_the_map_reader_finds_the_houses():
    capacities = tmx_town.house_capacities()
    assert sum(1 for c in capacities if c > 0) > 0


@pytest.mark.slow
def test_the_map_reader_agrees_with_the_games_map_loader():
    """The runner's town (read with xml.etree) is the game's town (read with pytmx)."""
    import pygame
    from src.config.constants import MAP_PATH
    from src.models.map import TMXMap

    pygame.display.init()
    pygame.display.set_mode((1, 1))
    tmx_map = TMXMap(MAP_PATH)
    from_game = sorted(h.max_inhabitants for h in tmx_map.houses if h.max_inhabitants > 0)
    assert sorted(c for c in tmx_town.house_capacities() if c > 0) == from_game
