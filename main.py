import pygame
from src.game import Game
from src.ui.main_menu import MainMenu
from src.ui.loading_screen import run_loading_screen
from src.config import settings_store
from src.config.constants import SCREEN_WIDTH, SCREEN_HEIGHT, SIDEBAR_WIDTH

_NATIVE_W = SCREEN_WIDTH + SIDEBAR_WIDTH  # 1760
_NATIVE_H = SCREEN_HEIGHT                 # 1064

# The game always draws into this off-screen 1760x1064 surface. Each frame it
# is scaled to the physical window. Mouse coordinates and events are patched
# below so that every downstream consumer (mouse.get_pos, event.pos) sees the
# logical 1760x1064 coordinate space regardless of the actual window size.
_render_surf: pygame.Surface | None = None
_display_surf: pygame.Surface | None = None
_scale_x: float = 1.0
_scale_y: float = 1.0

_orig_display_flip = pygame.display.flip
_orig_display_get_surface = pygame.display.get_surface
_orig_mouse_get_pos = pygame.mouse.get_pos
_orig_event_get = pygame.event.get
_orig_event_poll = pygame.event.poll
_orig_event_wait = pygame.event.wait

_MOUSE_EVENT_TYPES = (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION)


def _present() -> None:
    if _render_surf is None or _display_surf is None:
        return
    if _render_surf.get_size() == _display_surf.get_size():
        _display_surf.blit(_render_surf, (0, 0))
    else:
        pygame.transform.smoothscale(_render_surf, _display_surf.get_size(), _display_surf)
    _orig_display_flip()


def _patched_update(*args, **kwargs) -> None:
    _present()


def _patched_flip() -> None:
    _present()


def _patched_get_surface() -> pygame.Surface:
    return _render_surf if _render_surf is not None else _orig_display_get_surface()


def _patched_mouse_get_pos() -> tuple[int, int]:
    x, y = _orig_mouse_get_pos()
    return (int(x * _scale_x), int(y * _scale_y))


def _translate_event(ev: pygame.event.Event) -> pygame.event.Event:
    if ev.type in _MOUSE_EVENT_TYPES:
        px, py = ev.pos
        new_pos = (int(px * _scale_x), int(py * _scale_y))
        if ev.type == pygame.MOUSEMOTION:
            rx, ry = ev.rel
            return pygame.event.Event(
                ev.type,
                pos=new_pos,
                rel=(int(rx * _scale_x), int(ry * _scale_y)),
                buttons=ev.buttons,
            )
        return pygame.event.Event(ev.type, pos=new_pos, button=ev.button)
    return ev


def _patched_event_get(*args, **kwargs):
    return [_translate_event(e) for e in _orig_event_get(*args, **kwargs)]


def _patched_event_poll() -> pygame.event.Event:
    return _translate_event(_orig_event_poll())


def _patched_event_wait(*args, **kwargs) -> pygame.event.Event:
    return _translate_event(_orig_event_wait(*args, **kwargs))


def _install_patches() -> None:
    pygame.display.update = _patched_update
    pygame.display.flip = _patched_flip
    pygame.display.get_surface = _patched_get_surface
    pygame.mouse.get_pos = _patched_mouse_get_pos
    pygame.event.get = _patched_event_get
    pygame.event.poll = _patched_event_poll
    pygame.event.wait = _patched_event_wait


def _setup_display() -> pygame.Surface:
    """Create the physical window and the logical 1760x1064 render surface."""
    global _render_surf, _display_surf, _scale_x, _scale_y

    res = settings_store.get("resolution")

    if res == "Fullscreen":
        _display_surf = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    else:
        try:
            win_w, win_h = (int(x) for x in res.split("x"))
        except Exception:
            win_w, win_h = _NATIVE_W, _NATIVE_H
        _display_surf = pygame.display.set_mode((win_w, win_h))

    pw, ph = _display_surf.get_size()
    _scale_x = _NATIVE_W / pw
    _scale_y = _NATIVE_H / ph

    if _render_surf is None or _render_surf.get_size() != (_NATIVE_W, _NATIVE_H):
        _render_surf = pygame.Surface((_NATIVE_W, _NATIVE_H)).convert()

    pygame.display.set_caption("Merchant's Rise")
    return _render_surf


def main() -> None:
    """Start the game."""
    pygame.init()
    _install_patches()

    while True:
        _setup_display()

        menu = MainMenu()
        choice, save_data = menu.run()

        if choice == "exit":
            break
        elif choice not in ("new_game", "load_game"):
            break
        elif choice == "load_game" and save_data is None:
            break

        # Re-apply resolution in case settings were changed during the menu session
        screen = _setup_display()
        run_loading_screen(screen)

        result = Game(save_data=save_data, screen=screen).run()

        if result != "main_menu":
            break

    pygame.quit()


if __name__ == "__main__":
    main()
