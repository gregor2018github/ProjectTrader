"""Touching up frames by hand in GIMP, and noticing when they were saved back."""

import os
import shutil
import subprocess
from pathlib import Path

import pygame

ENV_GIMP = 'GIMP_PATH'   # the executable, if it is somewhere unusual
GIMP_NAMES = ('gimp', 'gimp-3', 'gimp-2.10')
GIMP_GLOBS = ('GIMP*/bin/gimp.exe', 'GIMP*/bin/gimp-*.exe')
WATCH_EVERY_MS = 1000    # how often the watched files are checked for edits


def find_gimp():
    """The GIMP executable, or None if it cannot be found.

    GIMP_PATH wins, then the PATH, then the usual install folders - the
    newest version first, since the folder name carries it (GIMP 2, GIMP 3).
    """
    named = os.environ.get(ENV_GIMP, '')
    if named and Path(named).is_file():
        return Path(named)
    for name in GIMP_NAMES:
        found = shutil.which(name)
        if found:
            return Path(found)
    for root in {os.environ.get('ProgramFiles', ''), os.environ.get('ProgramFiles(x86)', ''),
                 os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Programs')}:
        if not root or not Path(root).is_dir():
            continue
        for pattern in GIMP_GLOBS:
            # gimp-console / gimp-debug-tool share the prefix but are not the editor
            found = [p for p in sorted(Path(root).glob(pattern), reverse=True)
                     if 'console' not in p.name and 'debug' not in p.name and 'test' not in p.name]
            if found:
                return found[0]
    return None


def open_in_gimp(gimp, path):
    """Start GIMP on a file without waiting for it.

    Raises:
        OSError: If GIMP cannot be started.
    """
    subprocess.Popen([str(gimp), str(path)])


def modification_times(paths):
    """{path: modification time, or None for a file that is not there}."""
    times = {}
    for path in paths:
        try:
            times[path] = path.stat().st_mtime
        except OSError:
            times[path] = None
    return times


class FileWatcher:
    """Notices files changed outside the tool, e.g. saved back from GIMP.

    A program saving a file replaces it in steps - gone, half written, done -
    so a change is only reported once two checks in a row agree on it.
    Reporting earlier would have the file read in the middle of the save.
    """

    def __init__(self):
        self.known = {}    # {path: modification time} last reported
        self.seen = {}     # the same at the last check, to see a save settle
        self.checked_at = 0

    def reset(self):
        self.known = self.seen = {}

    def changed(self, paths):
        """The paths whose files changed and settled since the last report.

        Checks at most every WATCH_EVERY_MS; a different set of paths than
        last time starts the watch over without reporting anything.
        """
        now = pygame.time.get_ticks()
        if now - self.checked_at < WATCH_EVERY_MS:
            return []
        self.checked_at = now
        times = modification_times(paths)
        if times.keys() != self.known.keys():
            self.known = self.seen = times
            return []
        settled = times == self.seen
        self.seen = times
        if not settled or times == self.known:
            return []
        changed = [path for path in times if times[path] != self.known[path]]
        self.known = times
        return changed
