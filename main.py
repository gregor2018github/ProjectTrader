import gc
import os
import sys
import traceback

# Many asset paths are relative ('assets/...'), so start from the game's own
# folder: next to main.py, or in the release build (MerchantsRise.exe, see
# build_tools/Release) the _internal folder PyInstaller unpacked it all into
FROZEN = getattr(sys, "frozen", False)
os.chdir(sys._MEIPASS if FROZEN else os.path.dirname(os.path.abspath(__file__)))

# Set by build_tools/Release to the seconds to play: skips the main menu,
# starts a new game, quits after that long and exits 1 on any error
SMOKE_TEST_SECONDS = os.environ.get("MERCHANTS_RISE_SMOKE_TEST")

# Smooth GPU scaling in fullscreen and the smaller windows (pygame's SCALED
# would pick "nearest"), as the smoothscale of the CPU fallback looks
os.environ.setdefault("SDL_RENDER_SCALE_QUALITY", "linear")

import pygame
from src.game import Game
from src.ui.main_menu import MainMenu
from src.ui.loading_screen import run_loading_screen
from src.ui import cursor
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
_scale_x: float = 1.0   # logical = (physical - _offset_*) / _scale_uniform
_scale_y: float = 1.0
_offset_x: int = 0      # black-bar offset in physical pixels
_offset_y: int = 0
_scale_uniform: float = 1.0
# (SCALED, fullscreen) of the window made last: get_flags() does not show SCALED
_display_kind: tuple[bool, bool] | None = None
# The resolution setting the window was made for
_display_res: str | None = None

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
    if _render_surf is _display_surf:
        pass  # drawn in place; with SCALED the GPU does the scaling
    elif _offset_x == 0 and _offset_y == 0 and _scale_uniform == 1.0:
        _display_surf.blit(_render_surf, (0, 0))
    else:
        fit_w = int(_NATIVE_W * _scale_uniform)
        fit_h = int(_NATIVE_H * _scale_uniform)
        _display_surf.fill((0, 0, 0))
        scaled = pygame.transform.smoothscale(_render_surf, (fit_w, fit_h))
        _display_surf.blit(scaled, (_offset_x, _offset_y))
    _orig_display_flip()


def _patched_update(*args, **kwargs) -> None:
    _present()


def _patched_flip() -> None:
    _present()


def _patched_get_surface() -> pygame.Surface:
    return _render_surf if _render_surf is not None else _orig_display_get_surface()


def _patched_mouse_get_pos() -> tuple[int, int]:
    x, y = _orig_mouse_get_pos()
    lx = int((x - _offset_x) * _scale_x)
    ly = int((y - _offset_y) * _scale_y)
    return (max(0, min(lx, _NATIVE_W - 1)), max(0, min(ly, _NATIVE_H - 1)))


def _translate_event(ev: pygame.event.Event) -> pygame.event.Event:
    if ev.type in _MOUSE_EVENT_TYPES:
        px, py = ev.pos
        lx = int((px - _offset_x) * _scale_x)
        ly = int((py - _offset_y) * _scale_y)
        if ev.type == pygame.MOUSEBUTTONDOWN and not (0 <= lx < _NATIVE_W and 0 <= ly < _NATIVE_H):
            # A press on the black bars beside the game clicks nothing, rather
            # than whatever is at the frame's edge
            return pygame.event.Event(pygame.NOEVENT)
        new_pos = (max(0, min(lx, _NATIVE_W - 1)), max(0, min(ly, _NATIVE_H - 1)))
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
    events = (_translate_event(e) for e in _orig_event_get(*args, **kwargs))
    return [e for e in events if e.type != pygame.NOEVENT]


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


def _scaled_window(size: tuple[int, int]) -> pygame.Surface | None:
    """A window of *size* the logical 1760x1064 surface is shrunk into on the GPU.

    pygame's SCALED does that for fullscreen, but 2.6.1 neither lets the
    window be smaller than the logical size (it sets that as the window's
    minimum) nor scale below 1x (it turns on SDL's integer scaling). Both are
    undone here through SDL itself, the one pygame already loaded. SDL then
    letterboxes and maps the mouse back to logical coordinates, as in
    fullscreen. None if any of it fails: the CPU fallback is used instead.
    """
    surface = pygame.display.set_mode((_NATIVE_W, _NATIVE_H), pygame.SCALED)
    try:
        import ctypes
        from pygame._sdl2.video import Window, WINDOWPOS_CENTERED

        # By bare name Windows hands back the SDL2.dll already loaded by pygame
        candidates = ["SDL2", os.path.join(os.path.dirname(pygame.__file__), "SDL2.dll")]
        window = Window.from_display_module()
        for candidate in candidates:
            try:
                sdl = ctypes.CDLL(candidate)
            except OSError:
                continue
            sdl.SDL_GetWindowFromID.restype = ctypes.c_void_p
            sdl.SDL_GetRenderer.restype = ctypes.c_void_p
            handle = sdl.SDL_GetWindowFromID(ctypes.c_uint32(window.id))
            renderer = sdl.SDL_GetRenderer(ctypes.c_void_p(handle)) if handle else None
            if renderer:
                break
        else:
            return None
        if sdl.SDL_RenderSetIntegerScale(ctypes.c_void_p(renderer), 0) != 0:
            return None
        sdl.SDL_SetWindowMinimumSize(ctypes.c_void_p(handle), 1, 1)
        window.size = size
        window.position = WINDOWPOS_CENTERED
        pygame.event.pump()
        if tuple(window.size) != tuple(size):
            return None
    except Exception as e:
        print(f"GPU scaling of the window failed, scaling on the CPU: {e}")
        return None
    return surface


def _setup_display() -> pygame.Surface:
    """Create the physical window and the logical 1760x1064 render surface."""
    global _render_surf, _display_surf, _scale_x, _scale_y, _offset_x, _offset_y, _scale_uniform
    global _display_kind, _display_res

    res = settings_store.get("resolution")
    # Remaking the window shows the desktop for a moment (a SCALED one restarts
    # the whole display), so keep it unless the setting has changed
    if res == _display_res and _render_surf is not None:
        return _render_surf
    _display_res = res
    fullscreen = res == "Fullscreen"
    win_w, win_h = _NATIVE_W, _NATIVE_H
    if not fullscreen:
        try:
            win_w, win_h = (int(x) for x in res.split("x"))
        except Exception:
            pass
    # Fullscreen and the smaller windows are SCALED: SDL stretches the logical
    # surface to the window on the GPU, letterboxed, and maps the mouse back to
    # logical coordinates itself. Scaling with smoothscale on the CPU instead
    # cost 3-6 ms a frame here, far more on a slow PC.
    scaled = fullscreen or (win_w, win_h) != (_NATIVE_W, _NATIVE_H)

    # pygame cannot switch a window back to SCALED once it has been plain
    # ("failed to create renderer"), so start the display afresh for a SCALED
    # window, and on any change of kind of window
    if _display_kind is not None and (scaled or _display_kind != (scaled, fullscreen)):
        pygame.display.quit()
        pygame.display.init()

    if fullscreen:
        _display_surf = pygame.display.set_mode(
            (_NATIVE_W, _NATIVE_H), pygame.FULLSCREEN | pygame.SCALED)
    else:
        _display_surf = _scaled_window((win_w, win_h)) if scaled else None
        if _display_surf is None:
            if scaled:
                pygame.display.quit()
                pygame.display.init()
            # The native size, or the CPU fallback: smoothscaled in _present()
            _display_surf = pygame.display.set_mode((win_w, win_h))
            scaled = False
    _display_kind = (scaled, fullscreen)

    pw, ph = _display_surf.get_size()
    _scale_uniform = min(pw / _NATIVE_W, ph / _NATIVE_H)
    fit_w = int(_NATIVE_W * _scale_uniform)
    fit_h = int(_NATIVE_H * _scale_uniform)
    _offset_x = (pw - fit_w) // 2
    _offset_y = (ph - fit_h) // 2
    # Inverse scale: physical → logical (accounting for black-bar offset)
    _scale_x = _NATIVE_W / fit_w
    _scale_y = _NATIVE_H / fit_h

    if (pw, ph) == (_NATIVE_W, _NATIVE_H):
        # Native window, or a SCALED one: draw straight onto it
        _render_surf = _display_surf
    else:
        # Made anew: the one before may have belonged to a display since quit
        _render_surf = pygame.Surface((_NATIVE_W, _NATIVE_H)).convert()

    pygame.display.set_caption("Merchant's Rise")
    cursor.reset()
    return _render_surf


def main() -> None:
    """Start the game."""
    pygame.init()
    _install_patches()

    while True:
        _setup_display()

        if SMOKE_TEST_SECONDS:
            choice, save_data = "new_game", None
        else:
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
        # The game is built behind the loading screen, which keeps moving meanwhile
        Game.init_pygame()
        game, last_frame = run_loading_screen(
            screen, work=lambda: Game(save_data=save_data, screen=screen), duration=1.5)
        game.fade_in_from(last_frame)
        # The loaded game is a quarter of a million objects that live as long
        # as it does: kept out of the garbage collector's way, a full collection
        # takes nothing instead of 15 ms here (several times that on a slow PC)
        gc.collect()
        gc.freeze()

        if SMOKE_TEST_SECONDS:
            pygame.time.set_timer(pygame.QUIT, int(float(SMOKE_TEST_SECONDS) * 1000), loops=1)

        result = game.run()
        # Back to the main menu: this game's objects may be collected again
        gc.unfreeze()

        if result != "main_menu" or SMOKE_TEST_SECONDS:
            break

    pygame.quit()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        if not FROZEN:
            raise
        # The exe has no console: leave the error next to it for whoever runs it
        crash_log = os.path.join(os.path.dirname(sys.executable), "crash.log")
        with open(crash_log, "w", encoding="utf-8") as f:
            traceback.print_exc(file=f)
        if SMOKE_TEST_SECONDS:
            sys.exit(1)
        raise
