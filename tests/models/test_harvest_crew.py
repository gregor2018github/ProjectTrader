"""The harvest's workers (models/harvest_crew.py) and their ways through gates (models/gate_passing.py),
on a made-up map: a pen fenced in on a 20 x 20 tile map, a gate in its north side, three plants in
it and a door outside. Also the shocks (models/shock.py), a field's plants while it is cut, and the
real map's shocks and gate.

The worker is a real townsperson walked frame by frame at normal speed (3 game minutes a real second),
his hours and the time a plant takes pinned."""

import datetime
import os
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from src.models import harvest as harvest_module
from src.models import harvest_crew as crew_module
from src.models.field import Field
from src.models.figurines.humans.npcs.townsperson import AT_HOME, Townsperson
from src.models.gate import Gate
from src.models.gate_passing import GateKeeper, gate_stops
from src.models.gate_ways import GateWays, Walk
from src.models.harvest import FieldHarvest, Harvest
from src.models.harvest_crew import (
    AT_GATE, CUTTING, DONE, GOING_IN, HarvestCrew, SHUTTING_GATE, WAITING, WALKING, WALKING_HOME,
)
from src.models.navigation import NavGrid
from src.models.shock import Shock
from src.sim.calendar import EPOCH

TILE = 32
FRAME = 1 / 60
MINUTES_PER_FRAME = 3.0 * FRAME          # normal speed: a game day in 8 real minutes
# The pen: walls from x 160 to 480 and y 320 to 496, its north side open at x 320..352 for the gate
WALLS = [pygame.Rect(160, 320, 160, 16), pygame.Rect(352, 320, 128, 16), pygame.Rect(160, 480, 320, 16),
         pygame.Rect(160, 320, 16, 176), pygame.Rect(464, 320, 16, 176)]
PLANTS = [(240.0, 448.0), (272.0, 448.0), (304.0, 448.0)]


@pytest.fixture(autouse=True)
def pinned(monkeypatch):
    pygame.display.init()
    pygame.display.set_mode((1, 1))
    for module in (harvest_module, crew_module):
        monkeypatch.setattr(module, "HARVEST_MINUTES_PER_PLANT", 2.5, raising=False)
    monkeypatch.setattr(harvest_module, "WORK_START_HOURS", (6.0, 6.0))
    monkeypatch.setattr(harvest_module, "WORK_END_HOURS", (8.0, 8.0))
    monkeypatch.setattr(harvest_module, "COMMUTE_HOURS", 0.0)


def day(number, hour=0.0):
    return datetime.datetime.combine(EPOCH, datetime.time()) + datetime.timedelta(days=number, hours=hour)


def make_gate():
    # Its gateway the pen's gap: (320, 320) 32 x 16
    return Gate(320, 336, "", 1, 1, 1, 1, TILE, name="Gate_Pen", house_class="Gate", col_margin_up_pixel=-16)


def make_nav(gate):
    walls = [SimpleNamespace(collision_rects=[wall], image=None) for wall in WALLS]
    tmx = SimpleNamespace(tile_size=TILE, width=20, height=20, houses=walls + [gate], trees=[], waters=[],
                          water_tiles=set(), bridges=[])
    return NavGrid(tmx)


class World:
    """The pen, its gate, a field of three plants in it, a door outside and one worker behind it."""

    def __init__(self, plants=PLANTS):
        self.gate = make_gate()
        self.nav = make_nav(self.gate)
        self.ways = GateWays(self.nav)
        self.bodies = []
        self.keeper = GateKeeper([self.gate], lambda: self.bodies)
        self.door = SimpleNamespace(id=1, entry=(240.0, 200.0), step=(240.0, 212.0),
                                    facing_in="back", facing_out="front")
        self.harvest = Harvest([(1, plants)])
        self.cut = []
        self.field = SimpleNamespace(tmx_id=1, plants=[(x, y, 0.0, 0.0) for x, y in plants],
                                     harvest=self.harvest.fields[1], update_growth=lambda now: None,
                                     mark_cut=lambda plant, now: self.cut.append(plant))
        self.person = Townsperson("poor_roland", "Roland", TILE, "male")
        self.person.speed = 52.0                                    # pinned: each person's own pace is drawn
        self.person.gate_keeper = self.keeper
        self.person.go_indoors(self.door)
        self.crew = HarvestCrew(self.harvest, [self.field], [], [self.person], self.ways)
        self.gate_events = []
        self.states = []

    @property
    def job(self):
        return self.crew.jobs.get(1)

    def run(self, start, minutes, until=None, heavy_rain=lambda now: False):
        """Frames at normal speed from `start` for `minutes` of game time, as the game drives them."""
        now = start
        for _ in range(int(minutes / MINUTES_PER_FRAME)):
            now += datetime.timedelta(minutes=MINUTES_PER_FRAME)
            self.step(now, heavy_rain(now))
            if until is not None and until(self):
                break
        return now

    def step(self, now, heavy_rain=False):
        self.crew.heavy_rain = heavy_rain
        changed = self.harvest.update(now, self.crew.live_fields(now), heavy_rain)
        self.crew.refresh(now, changed)
        self.crew.update(now)
        was_open = self.gate.is_open
        self.person.update(FRAME, now)
        if self.gate.is_open != was_open:
            self.gate_events.append("open" if self.gate.is_open else "shut")
        if self.job is not None and (not self.states or self.states[-1] != self.job.state):
            self.states.append(self.job.state)


# ---------------------------------------------------------------------------
# Ways through gates

def test_the_grid_takes_no_notice_of_the_gate_so_the_way_into_the_pen_runs_through_it():
    world = World()
    assert not world.gate.is_open and world.nav.is_free_at(336, 328)          # the gateway, shut
    [leg] = world.ways.plan((240.0, 212.0), (240.0, 454.0))
    assert isinstance(leg, Walk) and leg.points[0] == (240.0, 212.0) and leg.points[-1] == (240.0, 454.0)
    [stop] = gate_stops(leg.points, [world.gate])
    assert stop.gate is world.gate and 0 < stop.lo < stop.hi


def test_a_way_past_the_pen_meets_no_gate():
    world = World()
    [leg] = world.ways.plan((240.0, 212.0), (400.0, 212.0))
    assert gate_stops(leg.points, [world.gate]) == []


# ---------------------------------------------------------------------------
# A worker's day

def test_he_waits_indoors_for_his_hour_walks_through_the_gate_shutting_it_cuts_and_goes_home():
    world = World()
    world.run(day(18, 5.0), 55)
    assert world.job.state == WAITING and world.person.state == AT_HOME and world.person.is_out is False
    world.run(day(18, 5.0 + 55 / 60), 180, until=lambda w: w.job.is_over)
    assert world.cut == [0, 1, 2] and world.harvest.fields[1].done
    assert world.gate_events == ["open", "shut", "open", "shut"]
    assert not world.gate.is_open
    assert world.person.state == AT_HOME and world.person.home_door is world.door
    assert world.states.index(AT_GATE) < world.states.index(SHUTTING_GATE) < world.states.index(CUTTING)
    assert world.states[-3:] == [WALKING_HOME, GOING_IN, WAITING] or world.states[-1] == DONE


def test_a_gate_he_finds_open_he_shuts_behind_him_all_the_same():
    world = World()
    world.gate.set_open(True)
    world.run(day(18, 5.9), 45, until=lambda w: w.job.state == CUTTING)
    assert world.job.state == CUTTING and not world.gate.is_open and world.gate_events == ["shut"]


def test_he_does_not_shut_the_gate_on_someone_in_the_gateway():
    world = World()
    world.bodies = [pygame.Rect(320, 322, 32, 14)]                 # somebody stands in it
    world.run(day(18, 5.9), 30, until=lambda w: w.job.state == SHUTTING_GATE)
    world.run(day(18, 6.2), 3)
    assert world.gate.is_open and world.job.state == SHUTTING_GATE
    world.bodies = []
    world.run(day(18, 6.25), 3)
    assert not world.gate.is_open and world.gate_events == ["open", "shut"]


def test_heavy_rain_sends_him_home_and_he_comes_out_again_when_it_stops():
    world = World([(240.0 + 32 * i, 448.0) for i in range(6)] + [(240.0 + 32 * i, 416.0) for i in range(6)])
    now = world.run(day(18, 5.9), 45, until=lambda w: w.job.state == CUTTING)
    now = world.run(now, 60, heavy_rain=lambda t: True, until=lambda w: w.person.state == AT_HOME)
    assert world.person.state == AT_HOME and world.job.state == WAITING
    cut = world.harvest.fields[1].cut
    now = world.run(now, 20, heavy_rain=lambda t: True)
    assert world.harvest.fields[1].cut == cut                     # nothing cut in the rain
    world.run(now, 30, until=lambda w: w.job.state == CUTTING)
    assert world.job.state == CUTTING                             # out again


def test_a_word_with_the_player_holds_his_cutting_and_he_carries_on_after():
    world = World()
    now = world.run(day(18, 5.9), 45, until=lambda w: w.job.state == CUTTING)
    world.person.talking_to = SimpleNamespace(x=228.0, y=470.0, width=24, height=40)
    left = world.job.work_left
    now = world.run(now, 10)
    assert world.job.work_left == left and world.cut == []
    world.person.talking_to = None
    world.run(now, 3)
    assert world.cut == [0]


def test_after_a_jump_of_the_clock_he_is_at_the_next_plant_or_indoors_after_his_hours():
    world = World([(240.0 + 32 * i, 448.0) for i in range(6)] + [(240.0 + 32 * i, 416.0) for i in range(6)])
    now = world.run(day(18, 5.9), 45, until=lambda w: w.job.state == CUTTING)
    before = world.harvest.fields[1].cut
    world.step(now + datetime.timedelta(minutes=45))               # longer than CATCH_UP_MINUTES
    field = world.harvest.fields[1]
    assert field.cut >= before + 9                                 # cut by the clock meanwhile
    plant = field.next_plant()
    x, y, _, _ = world.field.plants[plant]
    assert world.job.state == CUTTING and world.person.feet == pytest.approx((x, y + crew_module.STAND_BELOW_PX))
    world.step(day(18, 9.0))
    assert world.person.state == AT_HOME and world.job.state in (WAITING, DONE)


def test_with_the_map_hidden_the_field_is_cut_by_the_clock_and_he_is_put_at_the_next_plant():
    # Another view open: the clock runs on in small steps, as the game's, but the map runs no workers
    world = World([(240.0 + 32 * i, 448.0) for i in range(6)] + [(240.0 + 32 * i, 416.0) for i in range(6)])
    now = world.run(day(18, 5.9), 45, until=lambda w: w.job.state == CUTTING)
    before = world.harvest.fields[1].cut
    for _ in range(int(45 / MINUTES_PER_FRAME)):
        now += datetime.timedelta(minutes=MINUTES_PER_FRAME)
        world.harvest.update(now, world.crew.live_fields(now))
    field = world.harvest.fields[1]
    assert field.cut >= before + 8                                 # cut by the clock meanwhile
    world.step(now + datetime.timedelta(minutes=MINUTES_PER_FRAME))  # the map shown again
    x, y, _, _ = world.field.plants[field.next_plant()]
    assert world.job.state == CUTTING and world.person.feet == pytest.approx((x, y + crew_module.STAND_BELOW_PX))


def test_with_the_map_hidden_over_the_night_the_next_days_fields_are_cut_all_the_same():
    # 40 plants, some 3 hours of work: more than one day's 2 hours
    world = World([(208.0 + 32 * i, 448.0 - 32 * row) for row in range(5) for i in range(8)])
    now = world.run(day(18, 5.9), 30, until=lambda w: w.job.state == CUTTING)
    cut_on_the_map = world.harvest.fields[1].cut
    end = day(19, 8.0)
    while now < end:
        now += datetime.timedelta(minutes=1.0)
        world.harvest.update(now, world.crew.live_fields(now))
    assert world.harvest.fields[1].done and cut_on_the_map < world.harvest.fields[1].total


def test_the_crew_sends_the_poor_and_commons_and_street_life_leaves_them_be():
    world = World()
    noble = Townsperson("nobility_alison", "Alison", TILE, "female")
    noble.go_indoors(world.door)
    world.crew.townsfolk.append(noble)
    world.step(day(18, 5.0))
    assert world.job.person is world.person and noble.job is None
    assert world.person.on_job and not world.person.is_available
    world.crew.update(day(17, 5.0))                               # not a harvest day: nobody is sent
    assert world.crew.jobs == {} and world.person.job is None


# ---------------------------------------------------------------------------
# The shocks and the field

def make_shock():
    return Shock(100, 200, "Deco_27.png", 2, 3, 2, 2, TILE, name="Wheat_Shock_T", house_class="Shock",
                 col_margin_right_pixel=-23, col_margin_up_pixel=-43)


def test_a_hidden_shock_is_neither_drawn_nor_in_the_way_and_shown_it_is_both():
    shock = make_shock()
    shock.set_collision_gap(0, 0)                                  # the map does this for every house
    assert not shock.shown and shock.image is None and shock.collision_rects == []
    assert shock.get_scaled_sprite(1.0) is None
    shock.set_shown(True)
    assert shock.image is not None and shock.collision_rects == [shock.collision_rect]
    left, top, right, bottom = shock.picture_box()
    assert bottom == 200 and right - left == shock.picture.get_width()


def test_the_shocks_stand_as_the_harvest_reaches_them_and_all_for_three_days_after():
    world = World()
    first, last = make_shock(), make_shock()
    for shock, threshold in ((first, 1), (last, 3)):
        shock.field_id, shock.threshold = 1, threshold
    world.crew.shocks = [first, last]
    world.harvest.update(day(18, 6.0))
    world.crew.refresh_shocks(day(18, 6.0))
    assert not first.shown and not last.shown
    world.harvest.fields[1].cut = 1
    world.crew.refresh_shocks(day(18, 9.0))
    assert first.shown and not last.shown
    world.crew.refresh_shocks(day(21, 1.0))                        # the harvest is over: all stand
    assert first.shown and last.shown
    world.crew.refresh_shocks(day(24, 1.0))
    assert not first.shown and not last.shown


def test_a_ripe_field_shows_its_plants_until_cut_and_none_once_the_harvest_is_over():
    field = Field(0, 0, 6 * TILE, 5 * TILE, "Wheat", tmx_id=9)
    field.harvest = FieldHarvest(9, [(cx, by) for cx, by, _, _ in field.plants])
    field.update_growth(day(18, 9.0))
    assert all(sprite is not None for _, _, sprite in field.sprite_placements)
    field.harvest.start_year(day(18, 9.0))
    plant = field.harvest.cut_next()
    field.mark_cut(plant, day(18, 9.0))
    assert field.sprite_placements[plant][2] is None
    assert field.furrow_alpha == pytest.approx(1 / field.harvest.total)
    field.update_growth(day(20, 23.9))                             # late on the last day: still standing uncut
    assert sum(sprite is None for _, _, sprite in field.sprite_placements) == 1
    field.update_growth(day(21, 0.5))                              # into Winter: cleared, all of it
    assert all(sprite is None for _, _, sprite in field.sprite_placements)


# ---------------------------------------------------------------------------
# The real map

@pytest.mark.slow
def test_the_maps_shocks_belong_to_its_two_fields_and_the_fenced_one_is_reached_through_its_gate():
    from src.models.map import TMXMap
    tmx = TMXMap("assets/tiles/Map1.tmx")
    assert len(tmx.shocks) == 14 and not any(shock.shown for shock in tmx.shocks)
    by_field = {}
    for shock in tmx.shocks:
        by_field.setdefault(shock.field_id, []).append(shock.threshold)
    assert sorted(by_field) == [305, 763] and all(min(t) == 1 for t in by_field.values())
    gate = next(house for house in tmx.houses if house.name == "Gate_Farm_Field_North")
    field = next(field for field in tmx.fields if field.tmx_id == 763)
    [leg] = tmx.harvest_crew.ways.plan((4432.0, 5990.0), crew_module.stand_spot(field, field.harvest.order[0]))
    assert [stop.gate for stop in gate_stops(leg.points, tmx.gate_keeper.gates)] == [gate]
