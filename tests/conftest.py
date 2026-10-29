"""Shared test setup: pygame runs headless, so nothing opens a window or plays a sound."""

import os

# Must be set before pygame is first imported, which src/ does at module level
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
