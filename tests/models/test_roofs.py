"""The roofs rain splashes on, and their holes (src/models/roofs.py, roof_snow.py)."""

import pygame

from src.models.roof_snow import make_cap
from src.models.roofs import Roofs, match_holes

SQUARE = [(0, 0), (100, 0), (100, 100), (0, 100)]
MIDDLE = [(40, 40), (60, 40), (60, 60), (40, 60)]
CORNER = [(80, 80), (95, 80), (95, 95), (80, 95)]
ELSEWHERE = [(300, 300), (320, 300), (320, 320), (300, 320)]


def test_a_roof_without_holes_is_roof_throughout():
    roofs = Roofs([], match_holes([('Hall', SQUARE)], []))
    assert roofs.on_roof(50, 50)
    assert roofs.on_roof(10, 90)
    assert not roofs.on_roof(150, 50)


def test_a_hole_opens_the_roof_inside_it_only():
    roofs = Roofs([], match_holes([('Hall', SQUARE)], [('Hall', MIDDLE), ('Hall', CORNER)]))
    assert not roofs.on_roof(50, 50)
    assert not roofs.on_roof(90, 90)
    assert roofs.on_roof(20, 20)
    assert roofs.on_roof(70, 50)


def test_a_hole_belongs_to_the_roofs_named_after_its_building():
    shapes = match_holes([('Hall', SQUARE), ('Barn', SQUARE)], [('Hall', MIDDLE)])
    assert shapes[0][1] == [MIDDLE]
    assert shapes[1][1] == []
    # The barn's roof over the same spot still takes the rain
    assert Roofs([], shapes).on_roof(50, 50)


def test_a_hole_off_its_roof_cuts_nothing():
    shapes = match_holes([('Hall', SQUARE)], [('Hall', ELSEWHERE)])
    assert shapes[0][1] == []


def test_the_snow_cap_leaves_the_hole_open():
    image = pygame.Surface((100, 100), pygame.SRCALPHA)
    image.fill((150, 60, 40, 255))
    cap = make_cap(image, pygame.Rect(0, 0, 100, 100), match_holes([('Hall', SQUARE)], [('Hall', MIDDLE)]))
    assert cap.get_at((20, 20)).a == 255
    assert cap.get_at((50, 50)).a == 0


def test_no_snow_cap_when_the_holes_take_the_whole_roof():
    image = pygame.Surface((20, 20), pygame.SRCALPHA)
    image.fill((150, 60, 40, 255))
    roof = [(0, 0), (20, 0), (20, 20), (0, 20)]
    hole = [(-5, -5), (25, -5), (25, 25), (-5, 25)]
    assert make_cap(image, pygame.Rect(0, 0, 20, 20), match_holes([('Hut', roof)], [('Hut', hole)])) is None
