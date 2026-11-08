"""When the fish bite: by the hour and the weather for all, and each kind's own hours."""

import random

import pytest

from src.models.minigames import fishing_pond
from src.models.minigames.fishing_pond import Hook, Pond, SPECIES, bite_mood, time_of_day

DAY, NOON, DAWN, BEST, DUSK, NIGHT = 10.0, 13.0, 8.0, 6.5, 19.0, 23.0
DAWN_AT, DAY_AT, DUSK_AT, NIGHT_AT = 0, 1, 2, 3


def mood(hour, season=0, rain=0.0, storm=0.0, clouds=0.0):
    return bite_mood(hour, season, rain, storm, 0.0, clouds)[0]


class TestTheHours:
    @pytest.mark.parametrize("hour, time", ((3.0, NIGHT_AT), (DAWN, DAWN_AT), (BEST, DAWN_AT), (DAY, DAY_AT),
                                            (NOON, DAY_AT), (DUSK, DUSK_AT), (NIGHT, NIGHT_AT)))
    def test_time_of_day(self, hour, time):
        assert time_of_day(hour) == time

    def test_noon_is_way_calmer_than_a_day_and_that_than_the_best_morning_hour(self):
        assert mood(NOON) <= 0.5 * mood(DAY)
        assert mood(DAY) <= 0.6 * mood(BEST)

    def test_the_best_morning_hour_is_the_best_of_a_dry_day(self):
        assert mood(BEST) == max(mood(hour) for hour in (DAY, NOON, DAWN, DUSK, NIGHT, BEST))

    def test_rain_brings_an_ordinary_day_up_to_the_best_morning_hour(self):
        assert mood(DAY, rain=0.5) == pytest.approx(mood(BEST))

    def test_clouds_or_rain_take_the_calm_off_noon(self):
        assert mood(NOON, clouds=0.8) == mood(DAY)
        assert mood(NOON, rain=0.5) > mood(DAY)

    def test_a_storm_bites_most_but_within_bounds(self):
        assert mood(DAY, storm=0.5) > mood(DAY, rain=0.5)
        assert mood(BEST, storm=0.5) == fishing_pond.MOOD_MAX

    def test_winter_is_slower_and_summer_a_little_keener(self):
        assert mood(DAY, season=3) < mood(DAY) < mood(DAY, season=1)


def hours(key):
    return SPECIES[key].hours


class TestEachKindsHours:
    def test_the_pike_is_keenest_by_night_and_poorest_by_day(self):
        pike = hours("pike")
        assert pike[NIGHT_AT] == max(pike) and pike[DAY_AT] == min(pike)
        assert pike[NIGHT_AT] >= 4 * pike[DAY_AT]

    def test_the_perch_bites_by_day_and_hardly_by_night(self):
        perch = hours("perch")
        assert perch[DAY_AT] >= 1.0 and perch[NIGHT_AT] == min(perch)

    def test_by_day_the_perch_beats_the_pike_and_by_night_the_pike_the_perch(self):
        assert hours("perch")[DAY_AT] > 2 * hours("pike")[DAY_AT]
        assert hours("pike")[NIGHT_AT] > 5 * hours("perch")[NIGHT_AT]

    def test_the_tench_is_a_dawn_fish(self):
        assert hours("tench")[DAWN_AT] == max(hours("tench"))

    @pytest.mark.parametrize("key", ("carp", "bream"))
    def test_the_big_bottom_fish_come_on_as_the_light_goes(self, key):
        assert hours(key)[NIGHT_AT] > hours(key)[DAY_AT]

    @pytest.mark.parametrize("key", ("roach", "rudd"))
    def test_the_little_surface_fish_rest_at_night(self, key):
        assert hours(key)[NIGHT_AT] == min(hours(key))

    def test_the_golden_carp_keeps_the_carps_hours(self):
        assert hours("golden_carp") == hours("carp")

    def test_every_kind_has_hours_for_each_time(self):
        assert all(len(sp.hours) == 4 and min(sp.hours) > 0 for sp in SPECIES.values())


def test_the_pond_hands_each_fish_its_own_keenness():
    """As the pond lives, each fish gets the pond's mood times its kind's hours."""
    pond = Pond(random.Random(1), hour=NIGHT)
    seen = {}
    for fish in pond.fish:
        fish.update = lambda dt, hook, rng, mood, kind=fish.species.key: seen.setdefault(kind, mood) and []
    pond.update(1 / 60, Hook())
    assert seen["pike"] == pytest.approx(pond.mood * hours("pike")[NIGHT_AT])
    assert seen["perch"] == pytest.approx(pond.mood * hours("perch")[NIGHT_AT])
