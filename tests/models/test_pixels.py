"""A map sprite keeps its place against its neighbours while the camera moves (src/models/pixels.py)."""

from src.models.pixels import screen_pixel

SCALE = 40 / 32          # the zoom 1.25: a tile 40 px on screen


def test_a_sprite_at_an_odd_pixel_keeps_its_distance_to_its_neighbour_as_the_camera_moves():
    odd, aligned = 4566, 4544            # world x: the south sheep gate's old point, a tile's
    gaps = set()
    for camera in range(5600, 5640):     # the camera's origin, a whole screen pixel as Camera.apply has it
        a = screen_pixel((odd * SCALE - camera, 0))[0]
        b = screen_pixel((aligned * SCALE - camera, 0))[0]
        gaps.add(a - b)
    assert gaps == {28}                  # 27.5 px, always rounded the same way


def test_round_would_have_wiggled_it():
    gaps = {round(4566 * SCALE - camera) - round(4544 * SCALE - camera) for camera in range(5600, 5640)}
    assert len(gaps) == 2


def test_halves_round_up_and_whole_pixels_stay():
    assert screen_pixel((2.5, -1.5)) == (3, -1)
    assert screen_pixel((7.0, 7.49)) == (7, 7)
