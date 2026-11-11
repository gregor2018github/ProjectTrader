"""The pieces of a scripted talk an NPC gives in their speech bubble.

A talk is pages: what the NPC says, and the player's answers under it, each
leading to another page or ending the talk, and some doing something on the
way (introducing a minigame, starting it, taking a gift). The talks themselves
are in their own modules, one per kind: introductions.py (an NPC showing the
player a minigame) and thanks.py (an NPC thanking them, with a gift). They are
played by src/ui/helper_modules/figurine_talks.py. The texts are not voiced.
"""

from dataclasses import dataclass
from typing import Dict, Optional, Tuple


@dataclass(frozen=True)
class Answer:
    """One of the player's answers on a page."""
    label: str
    next: Optional[str] = None   # the page it leads to; None ends the talk
    agrees: bool = False         # introductions: the minigame counts as introduced from here on
    starts: bool = False         # introductions: and opens at once (if it may be played today)
    accepts: bool = False        # thanks: the gift is taken, and the thanks is over
    declines: bool = False       # thanks: the gift is turned down, and the thanks is over


@dataclass(frozen=True)
class Page:
    text: str
    answers: Tuple[Answer, ...]


Pages = Dict[str, Page]
