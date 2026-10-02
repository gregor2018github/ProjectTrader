"""Putting the tool window into the left half of the screen, as Windows snaps it (Win+Left).

That leaves the right half for the Gemini web view in a browser. The window
fills the left half of its monitor's work area - the screen without the
taskbar - with the invisible resize borders of Windows 10 and 11 reaching
past it, as a snapped window's do. Anywhere but Windows, or if a call fails,
the window stays where it opened.
"""

import ctypes
import sys
from ctypes import wintypes

import pygame

SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
MONITOR_DEFAULTTONEAREST = 2
DWMWA_EXTENDED_FRAME_BOUNDS = 9   # the window as it is drawn, without its invisible borders


class MonitorInfo(ctypes.Structure):
    _fields_ = [('cbSize', wintypes.DWORD), ('rcMonitor', wintypes.RECT),
                ('rcWork', wintypes.RECT), ('dwFlags', wintypes.DWORD)]


def snap_left():
    """Move and size the pygame window to the left half of its monitor; False if that did not work."""
    if sys.platform != 'win32':
        return False
    try:
        hwnd = pygame.display.get_wm_info()['window']
        user32 = ctypes.windll.user32
        info = MonitorInfo(cbSize=ctypes.sizeof(MonitorInfo))
        monitor = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
        if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            return False
        work = info.rcWork

        outer, drawn = wintypes.RECT(), wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(outer))
        if ctypes.windll.dwmapi.DwmGetWindowAttribute(
                hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(drawn), ctypes.sizeof(drawn)):
            drawn = outer   # no DWM: no invisible borders either
        left, top = drawn.left - outer.left, drawn.top - outer.top
        right, bottom = outer.right - drawn.right, outer.bottom - drawn.bottom

        width = (work.right - work.left) // 2
        height = work.bottom - work.top
        return bool(user32.SetWindowPos(hwnd, None, work.left - left, work.top - top,
                                        width + left + right, height + top + bottom,
                                        SWP_NOZORDER | SWP_NOACTIVATE))
    except (AttributeError, KeyError, OSError):
        return False
