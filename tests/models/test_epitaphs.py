"""The gravestones' inscriptions: the list, the years in Roman numerals, and the stones on the map naming them."""

import re
from pathlib import Path

from src.models.epitaphs import BY_KEY, EPITAPHS, epitaph, roman, years_line
from src.sim.calendar import CALENDAR_START_YEAR

MAP = Path(__file__).resolve().parents[2] / 'assets' / 'tiles' / 'Map1.tmx'


def test_fifteen_with_their_own_keys():
    assert len(EPITAPHS) == 15
    assert len(BY_KEY) == len(EPITAPHS)


def test_everyone_died_before_the_game_begins():
    for e in EPITAPHS:
        assert e.died < CALENDAR_START_YEAR, e.key
        if e.born is not None:
            assert 0 < e.died - e.born < 100, e.key
        assert e.name and e.lines, e.key


def test_roman_years_as_the_masons_carved_them():
    assert roman(1485) == 'MCCCCLXXXV'
    assert roman(1499) == 'MCCCCXCIX'
    assert roman(1416) == 'MCCCCXVI'
    assert years_line(BY_KEY['sweat']) == 'Anno Domini MCCCCLXXXV'
    assert years_line(BY_KEY['knight']) == 'MCCCCXL – MCCCCLXXXV'


def test_unknown_or_empty_key():
    assert epitaph('') is None
    assert epitaph('nobody') is None
    assert epitaph(' knight ') is BY_KEY['knight']


def test_every_stone_on_the_map_names_a_known_inscription_once():
    keys = re.findall(r'<property name="Epitaph" value="([^"]*)"', MAP.read_text(encoding='utf-8'))
    assert keys, 'no gravestone on the map'
    assert all(key in BY_KEY for key in keys), keys
    assert len(set(keys)) == len(keys), 'two stones say the same'
