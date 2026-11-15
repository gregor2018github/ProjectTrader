"""What a townsperson says to show the player a minigame, before it is played.

A minigame with an entry here is not open to the player until someone in town
has introduced it: the NPC whose profile names it as ``"introduces"`` (see
homebody.py). Talking to them plays the pages below in their speech bubble,
each answer leading to another page, or agreeing (the minigame is introduced
from then on, ``Statistics.minigames_introduced``) and perhaps starting it at
once. Afterwards the same NPC offers ``lend_option``, which starts the minigame
too, or says ``done_today`` once it has been played that day. The pieces of a
talk are in talks.py.

So far there is the woodhacking, introduced by Osric, the old woodcutter by the
wood shed, who wants a hand at the stump and never quite says why: he is
bored of it, busy, giving the player a chance to learn. Only his son tells
the truth (thanks.py). The texts are
not voiced.
"""

from dataclasses import dataclass
from typing import Dict

from .talks import Answer, Page

WOODHACKING = "woodhacking"


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
                "Ah, a young pair of arms! Forty winters I've split logs at that stump, and I could split "
                "forty more. Only it's grown dull, you see. There's no log in this yard left that can "
                "surprise me.",
                (Answer("Go on", "ask"),)),
            "ask": Page(
                "And a man has more important things to do than chop all day. My son's stock wants "
                "counting, the shed roof wants seeing to... So I thought, why not give a young one the "
                "chance to learn it properly? Take the stump for me. I pay for every clean blow.",
                (Answer("I'll lend a hand", "advice", agrees=True), Answer("Not now", "later"))),
            "advice": Page(
                "Good! You'll thank me for the lesson. It's not the strong arm that splits a log, it's "
                "the steady one: mind the swing and the aim, and land them together. Once a day, mind. "
                "I won't have you wearing out my stump.",
                (Answer("Hand me the axe", starts=True), Answer("Another time"))),
            "later": Page(
                "No matter, I'd only have done them myself anyway. Later. Once I've sorted the "
                "kindling. I'm out here every day, by the shed or under the trees.",
                (Answer("Farewell"),)),
        },
        done_today="That's enough for one day, friend. I'd finish the rest myself, only I've business "
                   "this afternoon. Come back tomorrow.",
    ),
}
