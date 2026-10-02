"""How many sprites were made today, by the dates of their files.

A sprite in humans/ whose file was created since midnight is new today; one
created before but saved since is redone (an answer accepted over it, its
colours evened out, an edit in GIMP).
"""

import datetime
from collections import namedtuple

from theme import HUMANS_DIR

Today = namedtuple('Today', 'new redone')


def created(stat):
    """When a file was created; where the system does not keep that, when it was last saved."""
    return getattr(stat, 'st_birthtime', stat.st_mtime)


def made_today():
    """Today(new, redone) sprite counts."""
    midnight = datetime.datetime.combine(datetime.date.today(), datetime.time()).timestamp()
    new = redone = 0
    for path in HUMANS_DIR.rglob('*.png'):
        try:
            stat = path.stat()
        except OSError:  # gone since it was listed
            continue
        if created(stat) >= midnight:
            new += 1
        elif stat.st_mtime >= midnight:
            redone += 1
    return Today(new, redone)
