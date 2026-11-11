"""An NPC thanking the player for something they did, with a gift to take or turn down.

Once the player has done what a thanks is for (``Thanks.earned``), its NPC, the
trader whose ``TILED_PREFIX`` is its ``giver``, offers ``talk_option`` in their
menu and glows for it on the map. The talk is pages of their speech bubble like
an introduction's (talks.py); an answer that ``accepts`` hands the player the
gift into their storage, or their pack if the storage is full (all of it or,
without the room, nothing, and the thanks waits), one that ``declines`` leaves
it and earns the player a little ``reputation`` for their modesty instead. Either
way the thanks is over for good (``Statistics.talks_done``, saved). What each
answer brings is shown beside it in the bubble.

So far there is the woodcutter's, at the wood market: Osric's son, thanking the
player for the first time they chopped wood for his father. The texts are not
voiced.
"""

from dataclasses import dataclass
from typing import Callable, Dict, Optional, TYPE_CHECKING

from .introductions import WOODHACKING
from .talks import Answer, Page

if TYPE_CHECKING:
    from .statistics import Statistics


#: Whether the player has finished a session of a minigame at least once
MINIGAME_PLAYED: Dict[str, Callable[['Statistics'], bool]] = {
    WOODHACKING: lambda stats: bool(stats.woodhacking_scores),
}


@dataclass(frozen=True)
class Thanks:
    """A thanks one NPC gives once, and the gift that goes with it."""
    key: str                         # kept in Statistics.talks_done once it is over
    giver: str                       # the TILED_PREFIX of the trader who gives it
    after: str                       # the minigame whose first finished session earns it
    gift: Dict[str, int]             # good name -> units
    reputation: float                # earned instead by turning the gift down
    first: str                       # the talk's first page
    pages: Dict[str, Page]
    talk_option: str = "Talk"        # in the NPC's menu while the thanks waits

    def page(self, name: str) -> Page:
        return self.pages[name]

    def earned(self, stats: 'Statistics') -> bool:
        """Whether the player has done what it is for and has not had it yet."""
        return self.key not in stats.talks_done and MINIGAME_PLAYED[self.after](stats)


THANKS: Dict[str, Thanks] = {
    "woodcutter_father": Thanks(
        key="woodcutter_father",
        giver="Woodcutter",
        after=WOODHACKING,
        gift={"Wood": 3},
        # A small kindness: a fifth of what Hawker asks for, as much as two coins
        # given to the poor early in the game
        reputation=1.0,
        first="thanks",
        pages={
            "thanks": Page(
                "So you're the one who's been splitting logs for my father! He's talked of nothing else. "
                "His back isn't what it was, and he's far too proud to ask me. Here, three logs from my "
                "stack, for your trouble.",
                (Answer("Accept his gift", "accepted", accepts=True),
                 Answer("No thanks needed!", "declined", declines=True))),
            "accepted": Page(
                "They're yours, I've had them put with your goods. And look in on the old man now and "
                "then, would you? He likes the company more than he lets on.",
                (Answer("Farewell"),)),
            "declined": Page(
                "Ha! You're as stubborn as he is. Then at least know you've a friend at the wood market.",
                (Answer("Farewell"),)),
        },
    ),
}


def thanks_for(giver: Optional[str], stats: 'Statistics') -> Optional[Thanks]:
    """The thanks waiting with the trader of this TILED_PREFIX, if any."""
    if not giver:
        return None
    return next((t for t in THANKS.values() if t.giver == giver and t.earned(stats)), None)
