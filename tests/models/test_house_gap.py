"""A passage through a building's collision box (House.set_collision_gap), as
under the Golden Sheaf's archway: two boxes either side, the whole one kept."""

import pygame

from src.models.house import House


def _house(scale=1.0):
    # A box 10 tiles wide and 2 deep, its bottom-left at (100, 500); no sprite
    return House(100, 500, "", 10, 4, 10, 2, 32, scale=scale)


def test_a_house_blocks_with_its_whole_box_by_default():
    house = _house()
    assert house.collision_rects == [house.collision_rect]


def test_a_gap_leaves_two_boxes_either_side_and_the_whole_one_for_the_rest():
    house = _house()
    whole = house.collision_rect.copy()
    house.set_collision_gap(100, 40)
    left, right = house.collision_rects
    assert (left.left, left.right) == (100, 200)
    assert (right.left, right.right) == (240, whole.right)
    assert left.top == right.top == whole.top and left.height == right.height == whole.height
    assert house.collision_rect == whole
    feet = pygame.Rect(204, 470, 32, 14)
    assert feet.collidelist(house.collision_rects) < 0


def test_the_gap_is_in_sprite_pixels_and_scales_with_the_sprite():
    house = _house(scale=0.5)
    house.set_collision_gap(100, 40)
    left, right = house.collision_rects
    assert left.right == 150 and right.left == 170


def test_a_gap_of_no_width_leaves_the_box_whole():
    house = _house()
    house.set_collision_gap(100, 0)
    assert house.collision_rects == [house.collision_rect]
