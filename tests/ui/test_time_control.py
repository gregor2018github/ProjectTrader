"""The time control hides its slower and faster buttons while the speed is locked (the map)."""
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame

from src.ui.helper_modules.time_control import TimeControl


def _control():
    pygame.init()
    images = {f"button_{n}_150": pygame.Surface((40, 40))
              for n in ("slower", "start_stop", "faster")}
    return TimeControl(1920, 1080, pygame.font.Font(None, 20), images)


def test_speed_buttons_work_when_unlocked():
    tc = _control()
    assert tc.handle_click(tc.buttons["faster"].center, 3) == 4
    assert tc.handle_click(tc.buttons["slower"].center, 3) == 2


def test_speed_buttons_ignored_and_not_drawn_when_locked():
    tc = _control()
    assert tc.handle_click(tc.buttons["faster"].center, 3, speed_locked=True) is None
    assert tc.handle_click(tc.buttons["slower"].center, 3, speed_locked=True) is None
    assert tc.handle_click(tc.buttons["start_stop"].center, 3, speed_locked=True) == 1
    screen = pygame.Surface((1920, 1080))
    screen.fill((255, 0, 255))
    tc.draw(screen, 3, speed_locked=True)
    assert screen.get_at(tc.buttons["faster"].center)[:3] != (0, 0, 0)
    assert screen.get_at(tc.buttons["start_stop"].center)[:3] == (0, 0, 0)
