"""What a townsperson says to show the player a minigame, before it is played.

A minigame with an entry here is not open to the player until someone in town
has introduced it: the NPC whose profile names it as ``"introduces"`` (see
homebody.py). Talking to them plays the pages below in their speech bubble,
each answer leading to another page, or agreeing (the minigame is introduced
from then on, ``Statistics.minigames_introduced``) and perhaps starting it at
once. Afterwards the same NPC offers ``lend_option``, which starts the minigame
too, or says ``done_today`` once it has been played that day.

So far there is the woodhacking, introduced by Osric, the old woodcutter by the
wood shed: too old to split logs all day, he is glad of a hand. The texts are
not voiced.
"""

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

WOODHACKING = "woodhacking"


@dataclass(frozen=True)
class Answer:
    """One of the player's answers on a page."""
    label: str
    next: Optional[str] = None   # the page it leads to; None ends the talk
    agrees: bool = False         # the minigame counts as introduced from here on
    starts: bool = False         # and opens at once (if it may be played today)


@dataclass(frozen=True)
class Page:
    text: str
    answers: Tuple[Answer, ...]


@dataclass(frozen=True)
class Introduction:
    """The talk that opens a minigame, and what its NPC offers after it."""
    talk_option: str                 # in the NPC's menu until it is introduced
    lend_option: str                 # in the NPC's menu once it is
    first: str                       # the talk's first page
    pages: Dict[str, Page]
    done_today: str                  # said instead of starting it once it was played today

    def page(self, name: str) -> Page:
        return self.pages[name]


INTRODUCTIONS: Dict[str, Introduction] = {
    WOODHACKING: Introduction(
        talk_option="Talk",
        lend_option="Lend a Hand",
        first="greeting",
        pages={
            "greeting": Page(
                "Ah, a young pair of arms! Forgive an old man for staring. Forty winters I split logs "
                "at that stump, and now my back creaks louder than the shed door.",
                (Answer("Go on", "ask"),)),
            "ask": Page(
                "My son sells the wood at the market, but the logs still want splitting, and these old "
                "hands won't do a day of it any more. Would you lend me a hand at the stump? I pay for "
                "every clean blow.",
                (Answer("I'll lend a hand", "advice", agrees=True), Answer("Not now", "later"))),
            "advice": Page(
                "Bless you! It's not the strong arm that splits a log, it's the steady one: mind the "
                "swing and the aim, and land them together. Once a day is all a back can stand, so come "
                "by whenever you like.",
                (Answer("Hand me the axe", starts=True), Answer("Another time"))),
            "later": Page(
                "No matter. I'm out here every day, by the shed or under the trees. The logs will wait "
                "for you, they're good at that.",
                (Answer("Farewell"),)),
        },
        done_today="That's enough for one day, friend. Come back tomorrow, the logs aren't going anywhere.",
    ),
}
